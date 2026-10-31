"""One bounded projection pass with durable quarantine for rejected observations."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from ufm.application.dto.worker_protocol import JobMessage, decode_worker_message
from ufm.application.job_conflicts import projection_rejection_key, run_quarantine_key_for_scope
from ufm.application.job_projection import JobProjectionCommands, ProjectionRejected
from ufm.application.ports.persistence import UnitOfWork
from ufm.domain.entities import AuditEvent, ExternalEventReceipt, ReconciliationTask
from ufm.domain.enums import ReceiptState, ReconciliationState, Severity
from ufm.domain.value_objects import EntityId, UtcDateTime


@dataclass(frozen=True, slots=True)
class DrainResult:
    applied: int
    ignored: int
    conflicts: int
    quarantined: int


class ProjectionDrain:
    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work
        self._commands = JobProjectionCommands(unit_of_work)

    def run_once(self, *, actor_device_id: EntityId, limit: int = 100,
                 at: UtcDateTime | None = None) -> DrainResult:
        now = at or UtcDateTime.now()
        applied = ignored = conflicts = quarantined = 0
        for receipt in self._commands.pending(limit):
            try:
                marker = self._commands.apply(receipt_id=receipt.id,
                    actor_device_id=actor_device_id, at=now)
            except ProjectionRejected:
                if self._quarantine_rejected(receipt.id, actor_device_id, now):
                    quarantined += 1
                continue
            if marker.outcome == "APPLIED":
                applied += 1
            elif marker.outcome == "IGNORED_STALE":
                ignored += 1
            else:
                conflicts += 1
        return DrainResult(applied, ignored, conflicts, quarantined)

    def _quarantine_rejected(
        self, receipt_id: EntityId, actor_device_id: EntityId, now: UtcDateTime,
    ) -> bool:
        """Recheck under the SQLite writer lock before persisting quarantine."""
        with self._unit_of_work() as work:
            receipt = work.receipts.get(receipt_id)
            if (work.projections.by_receipt(receipt_id) is not None
                    or receipt.state is not ReceiptState.PENDING or receipt.deleted_at is not None):
                return False

            receipt_key = projection_rejection_key(receipt.id)
            if work.reconciliations.open_task_by_dedupe(receipt_key) is None:
                work.reconciliations.add_task(ReconciliationTask(
                    id=EntityId.new(), device_id=actor_device_id,
                    created_at=now, updated_at=now, revision=1,
                    reason_code="PROJECTION_OBSERVATION_REJECTED",
                    severity=Severity.ERROR, state=ReconciliationState.OPEN,
                    dedupe_key=receipt_key, suggested_action="review_projection_observation",
                ))

            run_scope = self._validated_job_scope(receipt)
            if run_scope is not None:
                provider, printer, source_type, epoch, occurrence = run_scope
                run_key = run_quarantine_key_for_scope(
                    provider, printer, source_type, epoch, occurrence)
                if work.reconciliations.open_task_by_dedupe(run_key) is None:
                    job = work.jobs.by_occurrence_scope(
                        provider, printer, source_type, epoch, occurrence)
                    work.reconciliations.add_task(ReconciliationTask(
                        id=EntityId.new(), device_id=actor_device_id,
                        created_at=now, updated_at=now, revision=1,
                        reason_code="PROJECTION_RUN_QUARANTINED",
                        severity=Severity.ERROR, state=ReconciliationState.OPEN,
                        dedupe_key=run_key, print_job_id=job.id if job is not None else None,
                        suggested_action="review_projection_run_and_retry",
                    ))
                    work.audit.append(AuditEvent(
                        id=EntityId.new(), device_id=actor_device_id, created_at=now,
                        actor_device_id=actor_device_id,
                        event_code="printer.job_observation_quarantined",
                        correlation_id=f"receipt:{receipt.id}:projection-quarantine",
                        entity_type="print_job" if job is not None else "external_event_receipt",
                        entity_id=job.id if job is not None else receipt.id,
                        parameters_json=json.dumps({"run_key": run_key,
                            "reason": "PROJECTION_OBSERVATION_REJECTED"}, sort_keys=True),
                    ))
            work.commit()
            return True

    @staticmethod
    def _validated_job_scope(
        receipt: ExternalEventReceipt,
    ) -> tuple[EntityId, EntityId, str, str, str] | None:
        if receipt.sanitized_metadata is None:
            return None
        try:
            message = decode_worker_message(receipt.sanitized_metadata.encode())
        except ValueError:
            return None
        if (not isinstance(message, JobMessage)
                or message.printer_id != receipt.printer_id.value
                or message.source_epoch != receipt.source_epoch
                or receipt.event_type != "PRINT_" + message.state.upper()):
            return None
        return (receipt.provider_instance_id, receipt.printer_id, "PRINTER",
                receipt.source_epoch, message.occurrence_key)


class ProjectionQuarantineResolution:
    """Explicitly resolve one projection quarantine task after human review."""

    _RUN_KEY = re.compile(r"run:[0-9a-f]{64}:projection_rejected")
    _RECEIPT_KEY = re.compile(r"receipt:[0-9a-f-]{36}:projection_rejected")

    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def resolve_task(
        self, *, task_id: EntityId, actor_device_id: EntityId,
        resolution_notes: str, at: UtcDateTime | None = None,
    ) -> ReconciliationTask:
        if (type(resolution_notes) is not str or not resolution_notes.strip()
                or len(resolution_notes) > 500):
            raise ValueError("projection_quarantine.resolution_notes_invalid")
        now = at or UtcDateTime.now()
        with self._unit_of_work() as work:
            task = work.reconciliations.get(task_id)
            valid_key = (task.reason_code == "PROJECTION_RUN_QUARANTINED"
                         and self._RUN_KEY.fullmatch(task.dedupe_key) is not None) or (
                         task.reason_code == "PROJECTION_OBSERVATION_REJECTED"
                         and self._RECEIPT_KEY.fullmatch(task.dedupe_key) is not None)
            if (not valid_key or task.state not in {
                    ReconciliationState.OPEN, ReconciliationState.IN_REVIEW}):
                raise ValueError("projection_quarantine.resolution_not_allowed")
            if task.updated_at > now:
                raise ValueError("projection_quarantine.resolution_time_invalid")
            resolved = replace(task, state=ReconciliationState.RESOLVED,
                updated_at=now, revision=task.revision + 1, resolved_at=now,
                resolved_by=actor_device_id, resolution_notes=resolution_notes.strip())
            work.reconciliations.save_task(resolved, task.revision)
            work.audit.append(AuditEvent(
                id=EntityId.new(), device_id=actor_device_id, created_at=now,
                actor_device_id=actor_device_id, event_code="printer.projection_quarantine_resolved",
                correlation_id=f"reconciliation:{task.id}:manual-resolution",
                entity_type="reconciliation_task", entity_id=task.id,
                parameters_json=json.dumps({"dedupe_key": task.dedupe_key,
                    "reason_code": task.reason_code}, sort_keys=True),
            ))
            work.commit()
            return resolved
