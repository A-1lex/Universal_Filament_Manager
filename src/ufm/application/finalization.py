"""Atomic finalization of one complete, verified single-spool print.

This service consumes persisted receipts/evidence; it does not infer job identity
from progress, poll a printer, or treat slicer estimates as actual consumption.
Unsupported/ambiguous cases retain their pending evidence and require review.
"""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from ufm.application.costing import with_cost_snapshot
from ufm.application.job_conflicts import (
    lifecycle_conflict_key,
    projection_rejection_key,
    run_quarantine_key,
)
from ufm.application.ports.persistence import IdempotencyConflict, UnitOfWork
from ufm.application.receipt_ingestion import receipt_conflict_key
from ufm.domain.entities import (
    AlertEvent,
    AuditEvent,
    ConsumptionDecision,
    ConsumptionEvidence,
    DecisionEvidence,
    ExternalEventReceipt,
    FilamentTransaction,
    FinalizationRecord,
    MaterialUsageSegment,
    PrintJob,
    Reservation,
    Spool,
)
from ufm.domain.enums import (
    EvidenceMode,
    EvidenceSource,
    FinalizationState,
    InventoryHealth,
    PrintStatus,
    QuantityKind,
    ReceiptState,
    ReservationState,
    Severity,
    SlotAssignment,
    SpoolLifecycle,
    TransactionType,
)
from ufm.domain.policies.accounting import reservation_settlement, validate_decision_scope
from ufm.domain.policies.transitions import validate_transition
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime

POLICY_VERSION = "single-segment-verified-mass-v1"
_EVENT = "print.finalized"


class FinalizationRejected(ValueError):
    """The persisted facts are insufficient for automatic stock changes."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _Scope:
    job: PrintJob
    segment: MaterialUsageSegment
    spool: Spool
    claims: tuple[Reservation, ...]


class FinalizationCommands:
    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def finalize_single(
        self,
        *,
        job_id: EntityId,
        segment_id: EntityId,
        evidence_id: EntityId,
        receipt_id: EntityId,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> FinalizationRecord:
        if not command_key.strip() or len(command_key) > 500:
            raise FinalizationRejected("finalization.command_key_invalid")
        occurred_at = at or UtcDateTime.now()
        with self._unit_of_work() as work:
            evidence = work.evidence.get_consumption(evidence_id)
            receipt = work.receipts.get(receipt_id)
            fingerprint = self._request_hash(
                job_id, segment_id, evidence, receipt, actor_device_id,
            )
            prior = work.finalizations.by_job(job_id)
            keyed = work.finalizations.by_key(command_key)
            events = work.audit.for_command(command_key)
            if prior is not None:
                if (
                    keyed != prior or prior.idempotency_key != command_key
                    or prior.request_hash != fingerprint
                    or len(events) != 1 or events[0].event_code != _EVENT
                    or events[0].entity_id != job_id
                    or events[0].actor_device_id != actor_device_id
                    or receipt.state is not ReceiptState.PROCESSED
                    or receipt.reason_code != "PRINT_FINALIZED"
                ):
                    raise IdempotencyConflict()
                self._verify_result(work, prior, segment_id, evidence, receipt, command_key)
                return prior
            if keyed is not None or events or work.ledger.by_command(command_key) is not None:
                raise IdempotencyConflict()

            scope = self._verify_scope(work, job_id, segment_id, evidence, receipt, occurred_at)
            assert evidence.mass is not None
            actual = evidence.mass
            finalization_id, decision_id = EntityId.new(), EntityId.new()
            entry = self._entry(scope, actual, decision_id, receipt.id,
                                actor_device_id, command_key, occurred_at)
            result_hash = self._result_hash(job_id, segment_id, scope.spool.id,
                                            decision_id, actual, entry)
            record = FinalizationRecord(
                id=finalization_id, device_id=actor_device_id, created_at=occurred_at,
                print_job_id=job_id, idempotency_key=command_key, request_hash=fingerprint,
                started_at=occurred_at, completed_at=occurred_at, result_hash=result_hash,
            )
            decision = ConsumptionDecision(
                id=decision_id, device_id=actor_device_id, created_at=occurred_at,
                finalization_record_id=record.id, material_usage_segment_id=segment_id,
                selected_mass=actual, confidence_bp=evidence.confidence_bp,
                strategy="verified_printer_total", policy_version=POLICY_VERSION,
                reason_code="finalization.complete_segment_mass", finalized_at=occurred_at,
            )
            validate_decision_scope(scope.segment, decision)

            running = replace(
                scope.job, finalization_state=validate_transition(
                    scope.job.finalization_state, FinalizationState.IN_PROGRESS,
                ), updated_at=occurred_at, revision=scope.job.revision + 1,
            )
            work.jobs.save(running, scope.job.revision)
            work.finalizations.add(record)
            work.decisions.add(decision)
            work.decisions.add_evidence_link(DecisionEvidence(
                id=EntityId.new(), device_id=actor_device_id, created_at=occurred_at,
                decision_id=decision.id, evidence_id=evidence.id, role="SELECTED_TOTAL",
            ))
            if entry is not None:
                work.ledger.append(entry)
                updated = replace(
                    scope.spool, effective_remaining=entry.new_effective,
                    estimated_remaining=entry.new_estimated, ledger_sequence=entry.sequence,
                    updated_at=occurred_at, revision=scope.spool.revision + 1,
                )
                work.spools.save(updated, scope.spool.revision)
                self._low_stock_alert(work, updated, actor_device_id, occurred_at)
            self._settle(work, scope.claims, record.id, actual, occurred_at)
            finished = replace(
                running, finalization_state=validate_transition(
                    running.finalization_state, FinalizationState.FINALIZED,
                ), revision=running.revision + 1,
            )
            work.jobs.save(finished, running.revision)
            work.receipts.save(replace(
                receipt, state=validate_transition(receipt.state, ReceiptState.PROCESSED),
                processed_at=occurred_at, reason_code="PRINT_FINALIZED",
                updated_at=occurred_at, revision=receipt.revision + 1,
            ), receipt.revision)
            work.audit.append(AuditEvent(
                id=EntityId.new(), device_id=actor_device_id, created_at=occurred_at,
                event_code=_EVENT, actor_device_id=actor_device_id, correlation_id=command_key,
                entity_type="print_job", entity_id=job_id,
                parameters_json=json.dumps({"request_hash_v1": fingerprint,
                                            "finalization_id": str(record.id),
                                            "policy_version": POLICY_VERSION,
                                            "selected_mass_mg": actual.milligrams}, sort_keys=True),
            ))
            work.commit()
            return record

    @staticmethod
    def _verify_scope(
        work: UnitOfWork, job_id: EntityId, segment_id: EntityId,
        evidence: ConsumptionEvidence, receipt: ExternalEventReceipt, at: UtcDateTime,
    ) -> _Scope:
        job = work.jobs.get(job_id)
        materials = work.jobs.materials_for_job(job_id)
        segments = work.segments.for_job(job_id)
        if (job.deleted_at is not None or job.status is not PrintStatus.COMPLETED
            or job.started_at is None or job.completed_at is None
            or job.detected_at > job.started_at or job.completed_at < job.started_at
            or job.finalization_state not in (
                FinalizationState.NOT_STARTED, FinalizationState.NEEDS_RECONCILIATION,
            )):
            raise FinalizationRejected("finalization.job_not_ready")
        if len(materials) != 1 or len(segments) != 1:
            raise FinalizationRejected("finalization.single_segment_required")
        material, segment = materials[0], segments[0]
        if (material.deleted_at is not None or segment.deleted_at is not None
            or segment.id != segment_id or segment.print_job_material_id != material.id
            or segment.assignment_state is not SlotAssignment.ASSIGNED
            or segment.spool_id is None or segment.spool_mount_id is None
            or segment.feed_slot_id is None or segment.confidence_bp != 10_000
            or segment.started_at != job.started_at or segment.ended_at != job.completed_at
            or segment.tool_index != material.tool_index):
            raise FinalizationRejected("finalization.segment_unresolved")
        mount = work.mounts.get(segment.spool_mount_id)
        slot = work.slots.get(segment.feed_slot_id)
        system = work.feed_systems.get(slot.feed_system_id)
        printer = work.printers.get(job.printer_id)
        if (mount.deleted_at is not None or slot.deleted_at is not None
            or system.deleted_at is not None or printer.deleted_at is not None
            or not printer.enabled or mount.spool_id != segment.spool_id
            or mount.feed_slot_id != slot.id or system.printer_id != job.printer_id
            or mount.confidence_bp != 10_000 or mount.mounted_at > segment.started_at
            or (mount.unmounted_at is not None and mount.unmounted_at < job.completed_at)
            or slot.tool_index not in (None, segment.tool_index)):
            raise FinalizationRejected("finalization.mount_scope_invalid")
        if (receipt.deleted_at is not None or receipt.state is not ReceiptState.PENDING
            or receipt.printer_id != job.printer_id or receipt.event_type != "PRINT_COMPLETED"
            or re.fullmatch(r"[0-9a-f]{64}", receipt.payload_hash) is None):
            raise FinalizationRejected("finalization.receipt_invalid")
        if work.reconciliations.open_task_by_dedupe(receipt_conflict_key(receipt.id)) is not None:
            raise FinalizationRejected("finalization.receipt_conflict")
        if work.reconciliations.open_task_by_dedupe(lifecycle_conflict_key(job.id)) is not None:
            raise FinalizationRejected("finalization.lifecycle_conflict")
        if work.reconciliations.open_task_by_dedupe(projection_rejection_key(receipt.id)) is not None:
            raise FinalizationRejected("finalization.projection_quarantined")
        if (evidence.source is not EvidenceSource.PRINTER
            or evidence.quantity_kind is not QuantityKind.CONSUMED_MASS
            or evidence.mode is not EvidenceMode.ABSOLUTE or evidence.mass is None
            or evidence.confidence_bp != 10_000 or evidence.includes_purge is not True
            or evidence.segment_id != segment.id
            or evidence.print_job_material_id != material.id
            or evidence.source_receipt_id != receipt.id
            or evidence.scope_key != f"segment:{segment.id}"
            or evidence.interval_start != segment.started_at
            or evidence.interval_end != segment.ended_at
            or evidence.captured_at < job.completed_at
            or evidence.received_at < evidence.captured_at):
            raise FinalizationRejected("finalization.evidence_unverified")
        aliases = work.jobs.aliases_for_job(job.id)
        matching_aliases = [alias for alias in aliases if
            alias.provider_instance_id == receipt.provider_instance_id
            and alias.printer_id == receipt.printer_id
            and alias.source_epoch == receipt.source_epoch and alias.source_type == job.source_type
            and alias.occurrence_key == evidence.external_reference
            and (alias.started_at is None or alias.started_at == job.started_at)
        ]
        if not matching_aliases:
            raise FinalizationRejected("finalization.job_identity_unverified")
        if any(work.reconciliations.open_task_by_dedupe(run_quarantine_key(alias)) is not None
               for alias in matching_aliases):
            raise FinalizationRejected("finalization.projection_run_quarantined")
        spool = work.spools.get(segment.spool_id)
        if (spool.deleted_at is not None or spool.lifecycle is SpoolLifecycle.ARCHIVED
            or spool.inventory_health is not InventoryHealth.CONSISTENT
            or spool.effective_remaining is None or spool.ledger_sequence == 0):
            raise FinalizationRejected("finalization.stock_unavailable")
        history = work.ledger.for_spool(spool.id)
        if not history or history[0].created_at > job.started_at:
            raise FinalizationRejected("finalization.opening_after_print_start")
        if any(
            item.created_at >= job.started_at and (
                item.transaction_type is TransactionType.MEASUREMENT_CORRECTION
                or item.inventory_reconciliation_id is not None
            ) for item in history
        ):
            # A later accepted weighing may already include this print's usage.
            # It needs reconciliation against the measurement cutoff, not a debit.
            raise FinalizationRejected("finalization.measurement_overlap")
        reservations = work.reservations.for_material(material.id)
        if any(claim.state is ReservationState.PENDING or claim.settled_finalization_id is not None
               for claim in reservations):
            raise FinalizationRejected("finalization.reservation_unresolved")
        claims = tuple(claim for claim in reservations if claim.state is ReservationState.ACTIVE)
        if (len(claims) > 1 or any(
            claim.spool_id != spool.id or claim.deleted_at is not None for claim in claims
        )):
            raise FinalizationRejected("finalization.reservation_scope_invalid")
        own_ids = {claim.id for claim in claims}
        others = sum(claim.reserved.milligrams
                     for claim in work.reservations.active_for_spool(spool.id)
                     if claim.id not in own_ids)
        if evidence.mass.milligrams > spool.effective_remaining.milligrams - others:
            raise FinalizationRejected("finalization.insufficient_available_stock")
        times = [job.updated_at, job.completed_at, segment.updated_at, spool.updated_at,
                 receipt.updated_at, receipt.received_at, evidence.received_at,
                 *(claim.updated_at for claim in claims)]
        if any(value > at for value in times):
            raise FinalizationRejected("finalization.time_invalid")
        return _Scope(job, segment, spool, claims)

    @staticmethod
    def _entry(
        scope: _Scope, actual: Mass, decision_id: EntityId,
        receipt_id: EntityId, actor: EntityId, key: str, at: UtcDateTime,
    ) -> FilamentTransaction | None:
        if actual.milligrams == 0:
            return None
        spool = scope.spool
        assert spool.effective_remaining is not None
        cost, currency, metadata = with_cost_snapshot(spool, actual, "{}")
        return FilamentTransaction(
            id=EntityId.new(), device_id=actor, created_at=at, spool_id=spool.id,
            sequence=spool.ledger_sequence + 1, transaction_type=TransactionType.PRINT_CONSUMPTION,
            delta=Mass(-actual.milligrams), previous_effective=spool.effective_remaining,
            new_effective=spool.effective_remaining - actual,
            previous_estimated=spool.estimated_remaining,
            new_estimated=(None if spool.estimated_remaining is None else
                           spool.estimated_remaining - actual),
            command_key=key, command_item=0, source_type="PRINTER", confidence_bp=10_000,
            estimate_policy_version=POLICY_VERSION, print_job_id=scope.job.id,
            decision_id=decision_id, source_receipt_id=receipt_id,
            reservation_id=None if not scope.claims else scope.claims[0].id,
            unit_cost=cost, currency=currency, metadata_json=metadata,
        )

    @staticmethod
    def _settle(
        work: UnitOfWork, claims: tuple[Reservation, ...], finalization_id: EntityId,
        actual: Mass, at: UtcDateTime,
    ) -> None:
        for claim in claims:
            allocated, released = reservation_settlement(claim.reserved, actual)
            zero = allocated.milligrams == 0
            state = validate_transition(claim.state, ReservationState.RELEASED if zero else
                                        ReservationState.CONSUMED)
            settled = replace(
                claim, state=state, allocated_consumption=allocated, released=released,
                settled_finalization_id=finalization_id, consumed_at=None if zero else at,
                released_at=at if zero else None, reason="zero_consumption" if zero else None,
                updated_at=at, revision=claim.revision + 1,
            )
            work.reservations.save(settled, claim.revision)

    @staticmethod
    def _request_hash(
        job_id: EntityId, segment_id: EntityId, evidence: ConsumptionEvidence,
        receipt: ExternalEventReceipt, actor: EntityId,
    ) -> str:
        # Evidence is immutable; receipt source identity is included to detect
        # changed payloads even when a caller reuses the same receipt identifier.
        payload = {
            "policy": POLICY_VERSION, "job": str(job_id), "segment": str(segment_id),
            "evidence": str(evidence.id), "receipt": str(receipt.id), "actor": str(actor),
            "provider": str(receipt.provider_instance_id), "printer": str(receipt.printer_id),
            "epoch": receipt.source_epoch, "event": receipt.event_key,
            "event_type": receipt.event_type, "payload_hash": receipt.payload_hash,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _result_hash(
        job: EntityId, segment: EntityId, spool: EntityId, decision: EntityId, mass: Mass,
        entry: FilamentTransaction | None,
    ) -> str:
        payload = {"job": str(job), "segment": str(segment), "spool": str(spool),
                   "decision": str(decision), "mass_mg": mass.milligrams,
                   "ledger_id": None if entry is None else str(entry.id),
                   "ledger_sequence": None if entry is None else entry.sequence}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @classmethod
    def _verify_result(
        cls, work: UnitOfWork, record: FinalizationRecord, segment: EntityId,
        evidence: ConsumptionEvidence, receipt: ExternalEventReceipt, key: str,
    ) -> None:
        decisions = work.decisions.for_finalization(record.id)
        entry = work.ledger.by_command(key)
        job = work.jobs.get(record.print_job_id)
        if (len(decisions) != 1 or evidence.mass is None
            or job.finalization_state is not FinalizationState.FINALIZED):
            raise IdempotencyConflict()
        decision = decisions[0]
        scope = work.segments.get(segment)
        if (scope.spool_id is None or decision.material_usage_segment_id != segment
            or decision.selected_mass != evidence.mass
            or (evidence.mass.milligrams == 0) != (entry is None)):
            raise IdempotencyConflict()
        if entry is not None and (
            entry.decision_id != decision.id or entry.print_job_id != record.print_job_id
            or entry.source_receipt_id != receipt.id or entry.delta != Mass(-evidence.mass.milligrams)
        ):
            raise IdempotencyConflict()
        if record.result_hash != cls._result_hash(
            record.print_job_id, segment, scope.spool_id, decision.id, evidence.mass, entry,
        ):
            raise IdempotencyConflict()

    @staticmethod
    def _low_stock_alert(work: UnitOfWork, spool: Spool, actor: EntityId, at: UtcDateTime) -> None:
        if (spool.low_threshold is None or spool.effective_remaining is None
            or spool.effective_remaining > spool.low_threshold):
            return
        key = f"spool:{spool.id}:low-stock"
        if work.alerts.open_by_dedupe(key) is None:
            work.alerts.add(AlertEvent(
                id=EntityId.new(), device_id=actor, created_at=at, updated_at=at, revision=1,
                severity=Severity.WARNING, message_key="inventory.low_stock", dedupe_key=key,
                raised_at=at, spool_id=spool.id,
            ))
