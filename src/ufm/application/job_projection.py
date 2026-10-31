"""Durable receipt→job observations; never creates materials or consumption."""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from ufm.application.dto.worker_protocol import (
    JobMessage,
    MaterialSlotMappingFact,
    decode_worker_message,
)
from ufm.application.job_conflicts import lifecycle_conflict_key
from ufm.application.ports.persistence import IdempotencyConflict, UnitOfWork
from ufm.application.receipt_ingestion import receipt_conflict_key
from ufm.domain.entities import (
    AuditEvent,
    ExternalEventReceipt,
    JobIdentityAlias,
    JobProjectionState,
    JobReceiptApplication,
    PrintJob,
    ReconciliationTask,
)
from ufm.domain.entities.job_projection import JOB_PROJECTION_VERSION, TERMINAL_OBSERVATIONS
from ufm.domain.enums import (
    FinalizationState,
    PrintStatus,
    ReceiptState,
    ReconciliationState,
    Severity,
)
from ufm.domain.value_objects import EntityId, UtcDateTime

_STATUSES = {"started": PrintStatus.PREPARING, "running": PrintStatus.RUNNING,
             "paused": PrintStatus.PAUSED, "completed": PrintStatus.COMPLETED,
             "failed": PrintStatus.FAILED, "cancelled": PrintStatus.CANCELLED}
_HISTORY_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class JobMappingObservation:
    """An accepted, immutable mapping snapshot reconstructed from its receipt."""

    print_job_id: EntityId
    receipt_id: EntityId
    source_epoch: str
    source_sequence: int
    observed_at: UtcDateTime
    received_at: UtcDateTime
    state: str
    file_sha256: str | None
    completed_layers: int | None
    current_layer: int | None
    progress_bp: int | None
    exact_started_at: UtcDateTime | None
    exact_started_at_source: str | None
    exact_ended_at: UtcDateTime | None
    exact_ended_at_source: str | None
    material_slot_mappings: tuple[MaterialSlotMappingFact, ...]


def _projection_fingerprint(receipt: ExternalEventReceipt, message: JobMessage) -> str:
    return hashlib.sha256(json.dumps({
        "contract": JOB_PROJECTION_VERSION, "receipt": str(receipt.id),
        "provider": str(receipt.provider_instance_id), "printer": str(receipt.printer_id),
        "epoch": receipt.source_epoch, "key": receipt.event_key, "hash": receipt.payload_hash,
        "observed": message.model_dump(mode="json"),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ProjectionRejected(ValueError):
    pass


class JobProjectionCommands:
    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def pending(self, limit: int = 100) -> Sequence[ExternalEventReceipt]:
        with self._unit_of_work() as work:
            return tuple(work.projections.pending(limit))

    def mapping_history(self, *, print_job_id: EntityId) -> tuple[JobMappingObservation, ...]:
        """Return accepted mapping-bearing job observations in verified source order.

        The immutable receipt stores the complete observation and the immutable
        application marker binds that receipt to one projected job. This query
        materializes that existing durable history; it does not duplicate the
        payload or create a stock/accounting fact.
        """
        with self._unit_of_work() as work:
            job = work.jobs.get(print_job_id)
            if job.deleted_at is not None:
                raise ProjectionRejected("projection.history_job_unavailable")
            applications = work.projections.applications_for_job(print_job_id, _HISTORY_LIMIT + 1)
            if len(applications) > _HISTORY_LIMIT:
                raise ProjectionRejected("projection.history_limit_exceeded")
            observations: list[JobMappingObservation] = []
            for application in applications:
                if application.outcome != "APPLIED":
                    continue
                receipt = work.receipts.get(application.receipt_id)
                if receipt.sanitized_metadata is None:
                    raise ProjectionRejected("projection.history_observation_missing")
                try:
                    message = decode_worker_message(receipt.sanitized_metadata.encode())
                except ValueError:
                    raise ProjectionRejected("projection.history_observation_invalid") from None
                if (not isinstance(message, JobMessage)
                        or message.printer_id != receipt.printer_id.value
                        or message.source_epoch != receipt.source_epoch
                        or receipt.event_type != "PRINT_" + message.state.upper()
                        or receipt.printer_id != job.printer_id
                        or application.print_job_id != job.id
                        or application.request_hash != _projection_fingerprint(receipt, message)):
                    raise ProjectionRejected("projection.history_scope_invalid")
                observations.append(JobMappingObservation(
                    print_job_id=job.id, receipt_id=receipt.id, source_epoch=message.source_epoch,
                    source_sequence=message.sequence, observed_at=UtcDateTime(message.observed_at),
                    received_at=receipt.received_at, state=message.state, file_sha256=message.file_sha256,
                    completed_layers=message.completed_layers,
                    current_layer=message.current_layer, progress_bp=message.progress_bp,
                    exact_started_at=(None if message.exact_started_at is None
                                      else UtcDateTime(message.exact_started_at)),
                    exact_started_at_source=message.exact_started_at_source,
                    exact_ended_at=(None if message.exact_ended_at is None
                                    else UtcDateTime(message.exact_ended_at)),
                    exact_ended_at_source=message.exact_ended_at_source,
                    material_slot_mappings=message.material_slot_mappings,
                ))
            observations.sort(key=lambda item: (item.source_sequence, item.received_at.value, item.receipt_id.value))
            previous: JobMappingObservation | None = None
            for current in observations:
                if previous is not None and (
                    current.source_epoch != previous.source_epoch
                    or current.source_sequence <= previous.source_sequence
                    or current.observed_at < previous.observed_at
                    or (previous.completed_layers is not None and current.completed_layers is not None
                        and current.completed_layers < previous.completed_layers)
                    or (previous.current_layer is not None and current.current_layer is not None
                        and current.current_layer < previous.current_layer)
                    or (previous.progress_bp is not None and current.progress_bp is not None
                        and current.progress_bp < previous.progress_bp)
                ):
                    raise ProjectionRejected("projection.history_order_invalid")
                previous = current
            return tuple(observations)

    def apply(self, *, receipt_id: EntityId, actor_device_id: EntityId,
              at: UtcDateTime | None = None) -> JobReceiptApplication:
        now = at or UtcDateTime.now()
        with self._unit_of_work() as work:
            receipt = work.receipts.get(receipt_id)
            if receipt.sanitized_metadata is None:
                raise ProjectionRejected("projection.observation_required")
            try:
                message = decode_worker_message(receipt.sanitized_metadata.encode())
            except ValueError:
                raise ProjectionRejected("projection.observation_invalid") from None
            if (not isinstance(message, JobMessage) or message.printer_id != receipt.printer_id.value
                    or message.source_epoch != receipt.source_epoch
                    or receipt.event_type != "PRINT_" + message.state.upper()):
                raise ProjectionRejected("projection.observation_scope_invalid")
            fingerprint = _projection_fingerprint(receipt, message)
            previous = work.projections.by_receipt(receipt.id)
            if previous is not None:
                if previous.request_hash != fingerprint:
                    raise IdempotencyConflict()
                return previous
            printer = work.printers.get(receipt.printer_id)
            if (receipt.deleted_at is not None or receipt.state is not ReceiptState.PENDING
                    or printer.deleted_at is not None or not printer.enabled
                    or receipt.received_at > now or UtcDateTime(message.observed_at) > now
                    or any(value is not None and UtcDateTime(value) > now for value in (
                        message.exact_started_at, message.exact_ended_at,
                    ))):
                raise ProjectionRejected("projection.receipt_unavailable")
            if work.reconciliations.open_task_by_dedupe(receipt_conflict_key(receipt.id)) is not None:
                raise ProjectionRejected("projection.receipt_conflict")
            alias = JobIdentityAlias(
                id=EntityId.new(), device_id=actor_device_id, created_at=now,
                print_job_id=EntityId.new(), provider_instance_id=receipt.provider_instance_id,
                printer_id=receipt.printer_id, source_type="PRINTER", source_epoch=receipt.source_epoch,
                occurrence_key=message.occurrence_key, file_hash=message.file_sha256,
                started_at=(None if message.exact_started_at is None
                            else UtcDateTime(message.exact_started_at)),
            )
            job = work.jobs.by_alias(alias)
            if job is None:
                return self._create(work, receipt, message, alias, fingerprint, actor_device_id, now)
            if job.deleted_at is not None or job.updated_at > now:
                raise ProjectionRejected("projection.job_unavailable")
            state = work.projections.for_job(job.id)
            if state is None:
                # Existing/manual jobs are not adopted by an observation-only reducer.
                self._incident(work, job, actor_device_id, now, "projection.legacy_run_unmanaged", mutate=False)
                return self._finish(work, receipt, job, fingerprint, actor_device_id, now,
                                    "CONFLICT", "projection.legacy_run_unmanaged")
            if state.deleted_at is not None or state.updated_at > now or state.print_job_id != job.id:
                raise ProjectionRejected("projection.cursor_unavailable")
            previous_receipt = work.receipts.get(state.last_receipt_id)
            if previous_receipt.sanitized_metadata is None:
                raise ProjectionRejected("projection.cursor_unavailable")
            try:
                previous_message = decode_worker_message(previous_receipt.sanitized_metadata.encode())
            except ValueError:
                raise ProjectionRejected("projection.cursor_unavailable") from None
            if not isinstance(previous_message, JobMessage):
                raise ProjectionRejected("projection.cursor_unavailable")
            reason = self._conflict_reason(job, state, message, previous_message)
            if reason is not None:
                self._incident(work, job, actor_device_id, now, reason)
                return self._finish(work, receipt, job, fingerprint, actor_device_id, now, "CONFLICT", reason)
            observed = UtcDateTime(message.observed_at)
            if state.first_terminal_state is not None or observed <= state.observed_at:
                return self._finish(work, receipt, job, fingerprint, actor_device_id, now,
                                    "IGNORED_STALE", "projection.non_regressing_observation")
            if job.finalization_state is FinalizationState.FINALIZED:
                self._incident(work, job, actor_device_id, now, "projection.after_finalization")
                return self._finish(work, receipt, job, fingerprint, actor_device_id, now,
                                    "CONFLICT", "projection.after_finalization")
            terminal = message.state in TERMINAL_OBSERVATIONS
            work.projections.save_state(replace(
                state, last_receipt_id=receipt.id, observed_state=message.state, observed_at=observed,
                source_sequence=message.sequence,
                completed_layers=message.completed_layers if message.completed_layers is not None else state.completed_layers,
                first_terminal_receipt_id=receipt.id if terminal else None,
                first_terminal_state=message.state if terminal else None,
                terminal_seen_at=observed if terminal else None, revision=state.revision + 1, updated_at=now,
            ), state.revision)
            work.jobs.save(replace(job, status=_STATUSES[message.state],
                file_hash=job.file_hash or message.file_sha256,
                started_at=(job.started_at if message.exact_started_at is None
                            else UtcDateTime(message.exact_started_at)),
                completed_at=(job.completed_at if message.state != "completed"
                              or message.exact_ended_at is None else UtcDateTime(message.exact_ended_at)),
                failed_at=(job.failed_at if message.state != "failed"
                           or message.exact_ended_at is None else UtcDateTime(message.exact_ended_at)),
                cancelled_at=(job.cancelled_at if message.state != "cancelled"
                              or message.exact_ended_at is None else UtcDateTime(message.exact_ended_at)),
                current_layer=(message.current_layer if message.current_layer is not None else job.current_layer),
                progress_bp=(message.progress_bp if message.progress_bp is not None else job.progress_bp),
                updated_at=now, revision=job.revision + 1), job.revision)
            return self._finish(work, receipt, job, fingerprint, actor_device_id, now,
                                "APPLIED", "projection.observation_applied")

    def _create(self, work: UnitOfWork, receipt: ExternalEventReceipt, message: JobMessage,
                alias: JobIdentityAlias, fingerprint: str, actor: EntityId, now: UtcDateTime) -> JobReceiptApplication:
        active = work.jobs.active_for_printer(receipt.printer_id)
        missing = message.state != "started" and message.exact_started_at is None
        job = PrintJob(id=alias.print_job_id, device_id=actor, created_at=now, updated_at=now, revision=1,
            printer_id=receipt.printer_id, source_type="PRINTER", status=_STATUSES[message.state],
            finalization_state=FinalizationState.NEEDS_RECONCILIATION if missing or active else FinalizationState.NOT_STARTED,
            detected_at=UtcDateTime(message.observed_at), file_hash=message.file_sha256,
            started_at=(None if message.exact_started_at is None
                        else UtcDateTime(message.exact_started_at)),
            completed_at=(None if message.state != "completed" or message.exact_ended_at is None
                          else UtcDateTime(message.exact_ended_at)),
            failed_at=(None if message.state != "failed" or message.exact_ended_at is None
                       else UtcDateTime(message.exact_ended_at)),
            cancelled_at=(None if message.state != "cancelled" or message.exact_ended_at is None
                          else UtcDateTime(message.exact_ended_at)),
            current_layer=message.current_layer, progress_bp=message.progress_bp)
        work.jobs.add(job)
        work.jobs.add_alias(alias)
        terminal = message.state in TERMINAL_OBSERVATIONS
        observed = UtcDateTime(message.observed_at)
        work.projections.add_state(JobProjectionState(
            id=EntityId.new(), device_id=actor, created_at=now, updated_at=now, revision=1,
            print_job_id=job.id, last_receipt_id=receipt.id, observed_state=message.state,
            observed_at=observed, source_sequence=message.sequence, completed_layers=message.completed_layers,
            first_terminal_receipt_id=receipt.id if terminal else None,
            first_terminal_state=message.state if terminal else None,
            terminal_seen_at=observed if terminal else None,
        ))
        if missing:
            self._incident(work, job, actor, now, "projection.missing_start")
        for other in active:
            self._incident(work, other, actor, now, "projection.overlapping_occurrence")
        if active:
            self._incident(work, job, actor, now, "projection.overlapping_occurrence")
        return self._finish(work, receipt, job, fingerprint, actor, now, "APPLIED", "projection.observation_applied")

    @staticmethod
    def _conflict_reason(job: PrintJob, state: JobProjectionState, message: JobMessage,
                         previous_message: JobMessage) -> str | None:
        observed = UtcDateTime(message.observed_at)
        if (message.exact_started_at is not None and job.started_at is not None
                and UtcDateTime(message.exact_started_at) != job.started_at):
            return "projection.exact_start_conflict"
        if (message.exact_started_at is not None and previous_message.exact_started_at is not None
                and message.exact_started_at_source != previous_message.exact_started_at_source):
            return "projection.exact_start_provenance_conflict"
        end_field = {"completed": job.completed_at, "failed": job.failed_at,
                     "cancelled": job.cancelled_at}.get(message.state)
        if (message.exact_ended_at is not None and end_field is not None
                and UtcDateTime(message.exact_ended_at) != end_field):
            return "projection.exact_end_conflict"
        if (message.exact_ended_at is not None and previous_message.exact_ended_at is not None
                and message.exact_ended_at_source != previous_message.exact_ended_at_source):
            return "projection.exact_end_provenance_conflict"
        if (message.exact_ended_at is not None and job.started_at is not None
                and UtcDateTime(message.exact_ended_at) < job.started_at):
            return "projection.exact_interval_invalid"
        if job.file_hash is not None and message.file_sha256 is not None and job.file_hash != message.file_sha256:
            return "projection.file_identity_conflict"
        if state.first_terminal_state is not None:
            if message.state in TERMINAL_OBSERVATIONS and message.state != state.first_terminal_state:
                return "projection.terminal_conflict"
            if message.state not in TERMINAL_OBSERVATIONS and observed >= state.observed_at:
                return "projection.restart_after_terminal"
            if (message.state == state.first_terminal_state and state.completed_layers is not None
                    and message.completed_layers is not None and message.completed_layers != state.completed_layers):
                return "projection.terminal_count_conflict"
            if (message.state == state.first_terminal_state
                    and ((message.current_layer is not None and job.current_layer is not None
                          and message.current_layer != job.current_layer)
                         or (message.progress_bp is not None and job.progress_bp is not None
                             and message.progress_bp != job.progress_bp))):
                return "projection.terminal_snapshot_conflict"
            if message.material_slot_mappings != previous_message.material_slot_mappings:
                return "projection.terminal_mapping_conflict"
            return None
        if observed < state.observed_at:
            if message.sequence < state.source_sequence:
                return "projection.terminal_before_progress" if message.state in TERMINAL_OBSERVATIONS else None
            return "projection.sequence_time_conflict"
        if message.sequence < state.source_sequence:
            return "projection.sequence_regression"
        if message.sequence == state.source_sequence:
            same_observation = (
                message.state == previous_message.state
                and message.occurrence_key == previous_message.occurrence_key
                and message.file_sha256 == previous_message.file_sha256
                and message.completed_layers == previous_message.completed_layers
                and message.current_layer == previous_message.current_layer
                and message.progress_bp == previous_message.progress_bp
                and message.material_slot_mappings == previous_message.material_slot_mappings
            )
            if observed != state.observed_at or not same_observation:
                return "projection.sequence_reuse_conflict"
            return None
        if (state.completed_layers is not None and message.completed_layers is not None
                and message.completed_layers < state.completed_layers):
            return "projection.layer_counter_reset"
        if (job.current_layer is not None and message.current_layer is not None
                and message.current_layer < job.current_layer):
            return "projection.layer_counter_reset"
        if (job.progress_bp is not None and message.progress_bp is not None
                and message.progress_bp < job.progress_bp):
            return "projection.progress_regression"
        # Within one source epoch the worker's sequence orders same-time changes.
        if message.state == "started" and state.observed_state != "started":
            return "projection.occurrence_reused"
        if job.total_layers is not None and message.completed_layers is not None and message.completed_layers > job.total_layers:
            return "projection.layer_count_out_of_range"
        return None

    @staticmethod
    def _incident(work: UnitOfWork, job: PrintJob, actor: EntityId, now: UtcDateTime,
                  reason: str, *, mutate: bool = True) -> None:
        key = lifecycle_conflict_key(job.id)
        if work.reconciliations.open_task_by_dedupe(key) is None:
            work.reconciliations.add_task(ReconciliationTask(
                id=EntityId.new(), device_id=actor, created_at=now, updated_at=now, revision=1,
                print_job_id=job.id, reason_code="JOB_LIFECYCLE_CONFLICT", severity=Severity.ERROR,
                state=ReconciliationState.OPEN, dedupe_key=key, suggested_action=reason,
            ))
        if mutate and job.finalization_state not in {FinalizationState.FINALIZED, FinalizationState.NEEDS_RECONCILIATION}:
            if job.updated_at > now:
                raise ProjectionRejected("projection.job_time_invalid")
            work.jobs.save(replace(job, finalization_state=FinalizationState.NEEDS_RECONCILIATION,
                                   updated_at=now, revision=job.revision + 1), job.revision)

    @staticmethod
    def _finish(work: UnitOfWork, receipt: ExternalEventReceipt, job: PrintJob, fingerprint: str,
                actor: EntityId, now: UtcDateTime, outcome: str, reason: str) -> JobReceiptApplication:
        marker = JobReceiptApplication(id=EntityId.new(), device_id=actor, created_at=now,
            receipt_id=receipt.id, print_job_id=job.id, contract_version=JOB_PROJECTION_VERSION,
            outcome=outcome, reason_code=reason, request_hash=fingerprint)
        work.projections.add_application(marker)
        work.audit.append(AuditEvent(id=EntityId.new(), device_id=actor, created_at=now,
            actor_device_id=actor, event_code="printer.job_observation_projected",
            correlation_id=f"receipt:{receipt.id}:projection", entity_type="print_job", entity_id=job.id,
            parameters_json=json.dumps({"application_id": str(marker.id), "outcome": outcome,
                                        "reason": reason, "request_hash": fingerprint}, sort_keys=True)))
        work.commit()
        return marker
