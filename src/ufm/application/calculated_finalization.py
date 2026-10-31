"""Opt-in atomic estimated print batches from persisted, verified 3MF evidence.

The legacy verified-printer path remains unchanged. Calculation happens outside
the writer transaction; all persisted scopes are rechecked before any mutation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from ufm.application.costing import with_cost_snapshot
from ufm.application.dto.slice_facts import VerifiedSliceFacts
from ufm.application.dto.worker_protocol import (
    Digest,
    LogicalId,
    Nonnegative,
    ProposalMessage,
    Token,
    WireModel,
    WorkerScope,
)
from ufm.application.finalization import FinalizationCommands, FinalizationRejected
from ufm.application.job_conflicts import (
    lifecycle_conflict_key,
    projection_rejection_key,
    run_quarantine_key,
)
from ufm.application.ports.calculation import SliceCalculator, SliceFileReader
from ufm.application.ports.persistence import IdempotencyConflict, UnitOfWork
from ufm.application.receipt_ingestion import receipt_conflict_key
from ufm.domain.entities import (
    AuditEvent,
    ConsumptionDecision,
    ConsumptionEvidence,
    DecisionEvidence,
    ExternalEventReceipt,
    FilamentTransaction,
    FinalizationRecord,
    MaterialUsageSegment,
    PrintJob,
    PrintJobMaterial,
    Reservation,
    Spool,
)
from ufm.domain.enums import (
    EvidenceMode,
    EvidenceSource,
    FinalizationState,
    InventoryHealth,
    PrinterAccountingMode,
    PrintStatus,
    QuantityKind,
    ReceiptState,
    ReservationState,
    SlotAssignment,
    SpoolLifecycle,
    TransactionType,
)
from ufm.domain.policies.accounting import reservation_settlement
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime
from ufm.domain.value_objects.json_object import json_object

POLICY_VERSION = "verified-three-mf-estimate-v1"
EVENT = "print.calculated_finalized"
LABEL: Literal["Розрахункова витрата"] = "Розрахункова витрата"


def _require_ufm_accounting_authority(work: UnitOfWork, printer_id: EntityId) -> None:
    authority = work.printer_accounting_authorities.for_printer(printer_id)
    if authority is None or authority.mode is not PrinterAccountingMode.UFM_ACTIVE:
        raise FinalizationRejected("calculated.accounting_authority_required")


def _materials_by_logical_index(
    materials: Sequence[PrintJobMaterial],
    logical_indexes: set[int],
) -> dict[int, PrintJobMaterial]:
    """Keep file materials separate from tools; permit only unambiguous legacy fallback."""
    indices = [item.logical_material_index for item in materials]
    if all(index is None for index in indices):
        if len(materials) == 1 and len(logical_indexes) == 1:
            return {next(iter(logical_indexes)): materials[0]}
        raise FinalizationRejected("calculated.material_logical_mapping_required")
    if any(index is None for index in indices):
        raise FinalizationRejected("calculated.material_logical_mapping_incomplete")
    mapped = {
        index: item for item in materials if (index := item.logical_material_index) is not None
    }
    if len(mapped) != len(materials) or set(mapped) != logical_indexes:
        raise FinalizationRejected("calculated.material_logical_mapping_conflict")
    return mapped


@dataclass(frozen=True, slots=True)
class EstimatedUsagePolicy:
    enabled: bool = False
    allow_unknown_purge: bool = False
    allow_range_partial: bool = False
    allow_manual_splits: bool = False

    def __post_init__(self) -> None:
        if any(type(value) is not bool for value in asdict(self).values()):
            raise ValueError("calculated.policy_invalid")


class EstimateProvenance(WireModel):
    v: Annotated[int, Field(strict=True, ge=1, le=1)]
    quantity: Literal["estimate"]
    label: Literal["Розрахункова витрата"]
    unit: Literal["mg"]
    file_sha256: Digest
    metadata_sha256: Digest
    gcode_sha256: Digest
    parser_version: Token
    calculation_policy: Token
    plate: Annotated[int, Field(strict=True, ge=1, le=1_000_000)]
    logical_material: LogicalId
    logical_total_mg: Nonnegative
    allocation_mg: Nonnegative
    completed_layer: Annotated[int, Field(strict=True, ge=-1, le=1_000_000)] | None


def estimate_provenance(
    facts: VerifiedSliceFacts,
    proposal: ProposalMessage,
    *,
    logical_material: int,
    allocation_mg: int,
    completed_layer: int | None,
) -> str:
    totals = {item.logical_material: item.mass_mg for item in proposal.materials}
    return EstimateProvenance(
        v=1,
        quantity="estimate",
        label=LABEL,
        unit="mg",
        file_sha256=facts.file_sha256,
        metadata_sha256=facts.metadata_sha256,
        gcode_sha256=facts.gcode_sha256,
        parser_version=facts.parser_version,
        calculation_policy=proposal.policy_version,
        plate=facts.plate,
        logical_material=logical_material,
        logical_total_mg=totals[logical_material],
        allocation_mg=allocation_mg,
        completed_layer=completed_layer,
    ).model_dump_json()


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _terminal(job: PrintJob) -> tuple[UtcDateTime, str]:
    stamps = (job.completed_at, job.failed_at, job.cancelled_at)
    values = {
        PrintStatus.COMPLETED: (job.completed_at, "PRINT_COMPLETED"),
        PrintStatus.FAILED: (job.failed_at, "PRINT_FAILED"),
        PrintStatus.CANCELLED: (job.cancelled_at, "PRINT_CANCELLED"),
    }
    if job.status not in values or sum(value is not None for value in stamps) != 1:
        raise FinalizationRejected("calculated.job_not_terminal")
    end, event = values[job.status]
    if (
        end is None
        or job.started_at is None
        or job.detected_at > job.started_at
        or end < job.started_at
    ):
        raise FinalizationRejected("calculated.job_time_invalid")
    return end, event


@dataclass(frozen=True)
class _Loaded:
    job: PrintJob
    receipt: ExternalEventReceipt
    evidence: tuple[ConsumptionEvidence, ...]


@dataclass(frozen=True, slots=True)
class CalculatedMaterialPreview:
    logical_material: int
    estimated_mass_mg: int


@dataclass(frozen=True, slots=True)
class CalculatedUsagePreview:
    """Read-only estimate; it carries no decision or inventory authority."""

    job_id: EntityId
    file_sha256: str
    plate: int
    quantity_label: Literal["Розрахункова витрата"]
    partial: bool
    completed_layer: int | None
    policy_version: str
    automatic_policy_enabled: bool
    materials: tuple[CalculatedMaterialPreview, ...]


class CalculatedFinalizationCommands:
    def __init__(
        self,
        unit_of_work: Callable[[], UnitOfWork],
        calculator: SliceCalculator,
        policy: EstimatedUsagePolicy | None = None,
        *,
        file_reader: SliceFileReader,
    ) -> None:
        self._unit_of_work, self._calculator = unit_of_work, calculator
        self.policy = policy if policy is not None else EstimatedUsagePolicy()
        self._file_reader = file_reader

    async def preview(
        self,
        *,
        job_id: EntityId,
        evidence_ids: tuple[EntityId, ...],
        receipt_id: EntityId,
        actor_device_id: EntityId,
        plate: int,
        file_path: Path | None,
        at: UtcDateTime | None = None,
    ) -> CalculatedUsagePreview:
        """Calculate a reviewable estimate without writing any application state.

        Unlike ``finalize``, this works while automatic estimated usage is
        disabled. It still binds the result to a terminal job, its receipt,
        occurrence key and a matching verified file digest.
        """
        if (
            not evidence_ids
            or len(evidence_ids) > 1024
            or len(set(evidence_ids)) != len(evidence_ids)
            or type(plate) is not int
            or not 1 <= plate <= 1_000_000
        ):
            raise FinalizationRejected("calculated.request_invalid")
        now = at or UtcDateTime.now()
        with self._unit_of_work() as work:
            loaded = self._load(work, job_id, receipt_id, evidence_ids)
            job, receipt = loaded.job, loaded.receipt
            end, event = _terminal(job)
            if (
                job.deleted_at is not None
                or job.finalization_state not in {
                    FinalizationState.NOT_STARTED, FinalizationState.NEEDS_RECONCILIATION,
                }
                or work.ledger.for_job(job.id)
            ):
                raise FinalizationRejected("calculated.job_not_ready")
            if (
                receipt.deleted_at is not None
                or receipt.state is not ReceiptState.PENDING
                or receipt.printer_id != job.printer_id
                or receipt.event_type != event
                or receipt.received_at < end
                or re.fullmatch(r"[0-9a-f]{64}", receipt.payload_hash) is None
                or any(item.source_receipt_id != receipt.id for item in loaded.evidence)
            ):
                raise FinalizationRejected("calculated.receipt_invalid")
            if (
                work.reconciliations.open_task_by_dedupe(receipt_conflict_key(receipt.id))
                is not None
                or work.reconciliations.open_task_by_dedupe(lifecycle_conflict_key(job.id))
                is not None
                or work.reconciliations.open_task_by_dedupe(
                    projection_rejection_key(receipt.id)
                ) is not None
            ):
                raise FinalizationRejected("calculated.reconciliation_required")
            if (
                file_path is None
                or job.file_hash is None
                or re.fullmatch(r"[0-9a-f]{64}", job.file_hash) is None
            ):
                raise FinalizationRejected("calculated.file_required")
            if job.plate_name != str(plate):
                raise FinalizationRejected("calculated.plate_mismatch")
            if not loaded.evidence or not loaded.evidence[0].external_reference:
                raise FinalizationRejected("calculated.identity_unverified")
            if any(
                item.external_reference != loaded.evidence[0].external_reference
                for item in loaded.evidence
            ):
                raise FinalizationRejected("calculated.identity_unverified")
            fingerprint = self._fingerprint(loaded, plate, actor_device_id)
            occurrence = loaded.evidence[0].external_reference
            partial = job.status is not PrintStatus.COMPLETED
            if partial and job.current_layer is None:
                raise FinalizationRejected("calculated.partial_layer_unavailable")
            if partial:
                assert job.current_layer is not None
                layer = max(-1, job.current_layer - 2)
            else:
                layer = None

        try:
            facts = await asyncio.to_thread(
                self._file_reader, file_path, plate=plate, expected_sha256=job.file_hash,
            )
            proposal = await self._calculator.calculate(
                facts,
                scope=WorkerScope(job.printer_id.value, receipt.source_epoch, fingerprint),
                occurrence_key=occurrence,
                evidence_id=loaded.evidence[0].id.value,
                observed_at=now.value,
                sequence=0,
                completed_layer=layer,
            )
        except (ValueError, OSError):
            raise FinalizationRejected("calculated.calculation_unavailable") from None

        totals = {item.logical_material: item.mass_mg for item in proposal.materials}
        source_totals = {item.logical_material: item.mass_mg for item in facts.filaments}
        expected_policy = (
            "three-mf-full-mg-preview-v1" if layer is None else "haspel-range-cent-preview-v1"
        )
        if (
            proposal.file_sha256 != facts.file_sha256
            or proposal.evidence_id != loaded.evidence[0].id.value
            or proposal.occurrence_key != occurrence
            or proposal.policy_version != expected_policy
            or proposal.status != "needs_mapping"
            or proposal.allocations
            or proposal.partial != partial
            or proposal.confidence_bp != 0
            or totals.keys() != source_totals.keys()
            or any(value > source_totals[key] for key, value in totals.items())
            or (layer is None and totals != source_totals)
        ):
            raise FinalizationRejected("calculated.proposal_unverified")
        return CalculatedUsagePreview(
            job_id=job.id,
            file_sha256=facts.file_sha256,
            plate=plate,
            quantity_label=LABEL,
            partial=partial,
            completed_layer=layer,
            policy_version=proposal.policy_version,
            automatic_policy_enabled=self.policy.enabled,
            materials=tuple(
                CalculatedMaterialPreview(logical_material=index, estimated_mass_mg=mass)
                for index, mass in sorted(totals.items())
            ),
        )

    async def finalize(
        self,
        *,
        job_id: EntityId,
        evidence_ids: tuple[EntityId, ...],
        receipt_id: EntityId,
        actor_device_id: EntityId,
        command_key: str,
        plate: int,
        file_path: Path | None = None,
        at: UtcDateTime | None = None,
    ) -> FinalizationRecord:
        if (
            type(command_key) is not str
            or not command_key.strip()
            or len(command_key) > 500
            or not evidence_ids
            or len(evidence_ids) > 1024
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            raise FinalizationRejected("calculated.request_invalid")
        now = at or UtcDateTime.now()
        with self._unit_of_work() as work:
            initial = self._load(work, job_id, receipt_id, evidence_ids)
            fingerprint = self._fingerprint(initial, plate, actor_device_id)
            previous = self._prior(work, initial, command_key, fingerprint, actor_device_id)
            if previous is not None:
                return previous
            if not self.policy.enabled:
                raise FinalizationRejected("calculated.policy_disabled")
            _require_ufm_accounting_authority(work, initial.job.printer_id)
        if not self.policy.enabled:
            raise FinalizationRejected("calculated.policy_disabled")
        job = initial.job
        _terminal(job)
        if (
            file_path is None
            or job.file_hash is None
            or re.fullmatch(r"[0-9a-f]{64}", job.file_hash) is None
        ):
            raise FinalizationRejected("calculated.file_required")
        if type(plate) is not int or job.plate_name != str(plate):
            raise FinalizationRejected("calculated.plate_mismatch")
        partial = job.status is not PrintStatus.COMPLETED
        if partial and (not self.policy.allow_range_partial or job.current_layer is None):
            raise FinalizationRejected("calculated.partial_policy_required")
        layer = (
            max(-1, job.current_layer - 2) if partial and job.current_layer is not None else None
        )
        occurrence = initial.evidence[0].external_reference
        if not occurrence:
            raise FinalizationRejected("calculated.identity_unverified")
        try:
            facts = await asyncio.to_thread(
                self._file_reader, file_path, plate=plate, expected_sha256=job.file_hash
            )
            proposal = await self._calculator.calculate(
                facts,
                scope=WorkerScope(job.printer_id.value, initial.receipt.source_epoch, fingerprint),
                occurrence_key=occurrence,
                evidence_id=initial.evidence[0].id.value,
                observed_at=now.value,
                sequence=0,
                completed_layer=layer,
            )
        except (ValueError, OSError):
            raise FinalizationRejected("calculated.calculation_unavailable") from None
        with self._unit_of_work() as work:
            loaded = self._load(work, job_id, receipt_id, evidence_ids)
            if self._fingerprint(loaded, plate, actor_device_id) != fingerprint:
                raise IdempotencyConflict()
            previous = self._prior(work, loaded, command_key, fingerprint, actor_device_id)
            if previous is not None:
                return previous
            segments, spools, claims = self._verify(work, loaded, facts, proposal, layer, now)
            return self._commit(
                work,
                loaded,
                segments,
                spools,
                claims,
                fingerprint,
                command_key,
                actor_device_id,
                now,
            )

    @staticmethod
    def _load(
        work: UnitOfWork, job: EntityId, receipt: EntityId, evidence_ids: tuple[EntityId, ...]
    ) -> _Loaded:
        return _Loaded(
            work.jobs.get(job),
            work.receipts.get(receipt),
            tuple(work.evidence.get_consumption(key) for key in sorted(evidence_ids, key=str)),
        )

    def _fingerprint(self, loaded: _Loaded, plate: int, actor: EntityId) -> str:
        job, receipt = loaded.job, loaded.receipt
        return _hash(
            {
                "policy": POLICY_VERSION,
                "options": {
                    key: value for key, value in asdict(self.policy).items() if key != "enabled"
                },
                "actor": str(actor),
                "plate": plate,
                "job": {
                    "id": str(job.id),
                    "printer": str(job.printer_id),
                    "source": job.source_type,
                    "status": job.status,
                    "file_hash": job.file_hash,
                    "plate": job.plate_name,
                    "started": str(job.started_at),
                    "completed": str(job.completed_at),
                    "failed": str(job.failed_at),
                    "cancelled": str(job.cancelled_at),
                    "layer": job.current_layer,
                },
                "receipt": {
                    "id": str(receipt.id),
                    "provider": str(receipt.provider_instance_id),
                    "printer": str(receipt.printer_id),
                    "epoch": receipt.source_epoch,
                    "event": receipt.event_key,
                    "type": receipt.event_type,
                    "hash": receipt.payload_hash,
                    "received": str(receipt.received_at),
                },
                "evidence": [asdict(item) for item in loaded.evidence],
            }
        )

    def _prior(
        self, work: UnitOfWork, loaded: _Loaded, key: str, fingerprint: str, actor: EntityId
    ) -> FinalizationRecord | None:
        prior, keyed = work.finalizations.by_job(loaded.job.id), work.finalizations.by_key(key)
        events = work.audit.for_command(key)
        if prior is not None:
            if (
                keyed != prior
                or prior.request_hash != fingerprint
                or len(events) != 1
                or events[0].event_code != EVENT
                or events[0].entity_id != loaded.job.id
                or events[0].actor_device_id != actor
                or loaded.receipt.state is not ReceiptState.PROCESSED
                or loaded.receipt.processed_at != prior.completed_at
                or loaded.receipt.reason_code != "CALCULATED_PRINT_FINALIZED"
                or loaded.job.finalization_state is not FinalizationState.FINALIZED
                or prior.result_hash != self._result_hash(work, prior, loaded)
            ):
                raise IdempotencyConflict()
            return prior
        if keyed is not None or events or work.ledger.for_command(key):
            raise IdempotencyConflict()
        return None

    def _verify(
        self,
        work: UnitOfWork,
        loaded: _Loaded,
        facts: VerifiedSliceFacts,
        proposal: ProposalMessage,
        layer: int | None,
        at: UtcDateTime,
    ) -> tuple[tuple[MaterialUsageSegment, ...], dict[EntityId, Spool], tuple[Reservation, ...]]:
        job, receipt = loaded.job, loaded.receipt
        end, event = _terminal(job)
        assert job.started_at is not None
        if (
            job.deleted_at is not None
            or job.finalization_state
            not in {FinalizationState.NOT_STARTED, FinalizationState.NEEDS_RECONCILIATION}
            or not self.policy.enabled
            or work.ledger.for_job(job.id)
        ):
            raise FinalizationRejected("calculated.job_not_ready")
        if (
            receipt.deleted_at is not None
            or receipt.state is not ReceiptState.PENDING
            or receipt.printer_id != job.printer_id
            or receipt.event_type != event
            or receipt.received_at < end
            or re.fullmatch(r"[0-9a-f]{64}", receipt.payload_hash) is None
        ):
            raise FinalizationRejected("calculated.receipt_invalid")
        if work.reconciliations.open_task_by_dedupe(receipt_conflict_key(receipt.id)) is not None:
            raise FinalizationRejected("calculated.receipt_conflict")
        if work.reconciliations.open_task_by_dedupe(lifecycle_conflict_key(job.id)) is not None:
            raise FinalizationRejected("calculated.lifecycle_conflict")
        if (
            work.reconciliations.open_task_by_dedupe(projection_rejection_key(receipt.id))
            is not None
        ):
            raise FinalizationRejected("calculated.projection_quarantined")
        materials = work.jobs.materials_for_job(job.id)
        totals = {item.logical_material: item.mass_mg for item in proposal.materials}
        source_totals = {item.logical_material: item.mass_mg for item in facts.filaments}
        expected_calculation = (
            "three-mf-full-mg-preview-v1" if layer is None else "haspel-range-cent-preview-v1"
        )
        if (
            proposal.file_sha256 != facts.file_sha256
            or proposal.policy_version != expected_calculation
            or proposal.status != "needs_mapping"
            or proposal.allocations
            or proposal.partial != (layer is not None)
            or proposal.confidence_bp != 0
            or totals.keys() != source_totals.keys()
            or any(value > source_totals[key] for key, value in totals.items())
            or (layer is None and totals != source_totals)
        ):
            raise FinalizationRejected("calculated.proposal_unverified")
        materials_by_logical = _materials_by_logical_index(materials, set(totals))
        if any(item.deleted_at is not None for item in materials):
            raise FinalizationRejected("calculated.material_scope_invalid")
        segments = tuple(sorted(work.segments.for_job(job.id), key=lambda item: str(item.id)))
        by_segment = {item.segment_id: item for item in loaded.evidence}
        if len(by_segment) != len(loaded.evidence) or set(by_segment) != {
            item.id for item in segments
        }:
            raise FinalizationRejected("calculated.complete_evidence_required")
        confidence = 8000 if job.status is PrintStatus.COMPLETED else 6000
        spools: dict[EntityId, Spool] = {}
        allocations: dict[EntityId, int] = defaultdict(int)
        claims: list[Reservation] = []
        aliases = work.jobs.aliases_for_job(job.id)
        printer = work.printers.get(job.printer_id)
        _require_ufm_accounting_authority(work, job.printer_id)
        times = [job.updated_at, end, receipt.updated_at, receipt.received_at]
        for logical_material, material in sorted(materials_by_logical.items()):
            group = sorted(
                (item for item in segments if item.print_job_material_id == material.id),
                key=lambda item: (item.started_at, item.ended_at or item.started_at, str(item.id)),
            )
            if not group or group[0].started_at != job.started_at or group[-1].ended_at != end:
                raise FinalizationRejected("calculated.coverage_incomplete")
            prior_end = job.started_at
            total = 0
            for segment in group:
                evidence = by_segment[segment.id]
                if (
                    segment.deleted_at is not None
                    or segment.assignment_state is not SlotAssignment.ASSIGNED
                    or segment.spool_id is None
                    or segment.spool_mount_id is None
                    or segment.feed_slot_id is None
                    or segment.confidence_bp != 10000
                    or segment.tool_index != material.tool_index
                    or segment.started_at != prior_end
                    or segment.ended_at is None
                    or segment.ended_at > end
                ):
                    raise FinalizationRejected("calculated.segment_unresolved")
                prior_end = segment.ended_at
                if (
                    evidence.source is not EvidenceSource.THREE_MF
                    or evidence.mode is not EvidenceMode.ESTIMATE
                    or evidence.quantity_kind is not QuantityKind.CONSUMED_MASS
                    or evidence.mass is None
                    or evidence.confidence_bp != confidence
                    or evidence.print_job_material_id != material.id
                    or evidence.source_receipt_id != receipt.id
                    or evidence.scope_key != f"segment:{segment.id}"
                    or evidence.interval_start != segment.started_at
                    or evidence.interval_end != segment.ended_at
                    or evidence.captured_at < end
                    or evidence.received_at < evidence.captured_at
                    or evidence.includes_purge is not facts.includes_purge
                ):
                    raise FinalizationRejected("calculated.evidence_unverified")
                if evidence.includes_purge is not True and not self.policy.allow_unknown_purge:
                    raise FinalizationRejected("calculated.purge_policy_required")
                expected = estimate_provenance(
                    facts,
                    proposal,
                    logical_material=logical_material,
                    allocation_mg=evidence.mass.milligrams,
                    completed_layer=layer,
                )
                try:
                    meta = EstimateProvenance.model_validate_json(evidence.metadata_json)
                except ValidationError:
                    raise FinalizationRejected("calculated.provenance_invalid") from None
                if meta.model_dump_json() != expected:
                    raise FinalizationRejected("calculated.provenance_mismatch")
                matching_aliases = [
                    alias
                    for alias in aliases
                    if alias.provider_instance_id == receipt.provider_instance_id
                    and alias.printer_id == job.printer_id
                    and alias.source_epoch == receipt.source_epoch
                    and alias.source_type == job.source_type
                    and alias.occurrence_key == evidence.external_reference
                    and (alias.started_at is None or alias.started_at == job.started_at)
                    and (alias.file_hash is None or alias.file_hash == facts.file_sha256)
                ]
                if not matching_aliases:
                    raise FinalizationRejected("calculated.identity_unverified")
                if any(
                    work.reconciliations.open_task_by_dedupe(run_quarantine_key(alias)) is not None
                    for alias in matching_aliases
                ):
                    raise FinalizationRejected("calculated.projection_run_quarantined")
                if len(group) > 1:
                    self._verify_split(work, segment, evidence, facts, at)
                mount, slot = (
                    work.mounts.get(segment.spool_mount_id),
                    work.slots.get(segment.feed_slot_id),
                )
                system = work.feed_systems.get(slot.feed_system_id)
                if (
                    printer.deleted_at is not None
                    or not printer.enabled
                    or mount.deleted_at is not None
                    or slot.deleted_at is not None
                    or system.deleted_at is not None
                    or mount.spool_id != segment.spool_id
                    or mount.feed_slot_id != slot.id
                    or system.printer_id != job.printer_id
                    or mount.confidence_bp != 10000
                    or mount.mounted_at > segment.started_at
                    or (mount.unmounted_at is not None and mount.unmounted_at < segment.ended_at)
                    or slot.tool_index not in (None, segment.tool_index)
                ):
                    raise FinalizationRejected("calculated.mount_scope_invalid")
                spools.setdefault(segment.spool_id, work.spools.get(segment.spool_id))
                total += evidence.mass.milligrams
                allocations[segment.spool_id] += evidence.mass.milligrams
                times.extend((segment.updated_at, evidence.received_at, material.updated_at))
            if total != totals[logical_material]:
                raise FinalizationRejected("calculated.material_total_mismatch")
            reservations = work.reservations.for_material(material.id)
            if any(
                item.state is ReservationState.PENDING
                or item.settled_finalization_id is not None
                or item.deleted_at is not None
                for item in reservations
            ):
                raise FinalizationRejected("calculated.reservation_unresolved")
            claims.extend(item for item in reservations if item.state is ReservationState.ACTIVE)
        if len({(item.print_job_material_id, item.spool_id) for item in claims}) != len(claims):
            raise FinalizationRejected("calculated.reservation_scope_invalid")
        own = {item.id for item in claims}
        for spool in spools.values():
            if (
                spool.deleted_at is not None
                or spool.lifecycle is SpoolLifecycle.ARCHIVED
                or spool.inventory_health is not InventoryHealth.CONSISTENT
                or spool.effective_remaining is None
                or spool.ledger_sequence == 0
            ):
                raise FinalizationRejected("calculated.stock_unavailable")
            history = work.ledger.for_spool(spool.id)
            if not history or history[0].created_at > job.started_at:
                raise FinalizationRejected("calculated.opening_after_print_start")
            if any(
                item.created_at >= job.started_at
                and (
                    item.transaction_type is TransactionType.MEASUREMENT_CORRECTION
                    or item.inventory_reconciliation_id is not None
                )
                for item in history
            ):
                raise FinalizationRejected("calculated.measurement_overlap")
            others = sum(
                item.reserved.milligrams
                for item in work.reservations.active_for_spool(spool.id)
                if item.id not in own
            )
            if allocations[spool.id] > spool.effective_remaining.milligrams - others:
                raise FinalizationRejected("calculated.insufficient_available_stock")
            times.append(spool.updated_at)
        times.extend(item.updated_at for item in claims)
        if any(value > at for value in times):
            raise FinalizationRejected("calculated.time_invalid")
        return segments, spools, tuple(claims)

    def _verify_split(
        self,
        work: UnitOfWork,
        segment: MaterialUsageSegment,
        evidence: ConsumptionEvidence,
        facts: VerifiedSliceFacts,
        at: UtcDateTime,
    ) -> None:
        events = work.audit.for_command(f"segment:{segment.id}:allocation")
        if (
            not self.policy.allow_manual_splits
            or segment.source != "MANUAL_CONFIRMED_SPLIT"
            or segment.estimated_usage != evidence.mass
            or len(events) != 1
            or events[0].event_code != "print.allocation.confirmed"
            or events[0].entity_id != segment.id
            or events[0].entity_type != "material_usage_segment"
            or segment.ended_at is None
            or not segment.ended_at <= events[0].created_at <= at
        ):
            raise FinalizationRejected("calculated.split_unverified")
        parameters = json_object(events[0].parameters_json)
        if type(parameters.get("allocation_mg")) is not int or parameters != {
            "allocation_mg": evidence.mass.milligrams if evidence.mass else None,
            "file_sha256": facts.file_sha256,
        }:
            raise FinalizationRejected("calculated.split_unverified")

    def _commit(
        self,
        work: UnitOfWork,
        loaded: _Loaded,
        segments: tuple[MaterialUsageSegment, ...],
        spools: dict[EntityId, Spool],
        claims: tuple[Reservation, ...],
        fingerprint: str,
        key: str,
        actor: EntityId,
        at: UtcDateTime,
    ) -> FinalizationRecord:
        job, receipt = loaded.job, loaded.receipt
        record = FinalizationRecord(
            id=EntityId.new(),
            device_id=actor,
            created_at=at,
            print_job_id=job.id,
            idempotency_key=key,
            request_hash=fingerprint,
            started_at=at,
            completed_at=at,
            result_hash="pending",
        )
        running = replace(
            job,
            finalization_state=FinalizationState.IN_PROGRESS,
            revision=job.revision + 1,
            updated_at=at,
        )
        work.jobs.save(running, job.revision)
        evidence = {item.segment_id: item for item in loaded.evidence}
        pair_mass: dict[tuple[EntityId, EntityId], int] = defaultdict(int)
        own = {(item.print_job_material_id, item.spool_id): item for item in claims}
        # Prepare the complete immutable result before inserting its record.
        decisions, links, entries = [], [], []
        for index, segment in enumerate(segments):
            item = evidence[segment.id]
            assert item.mass is not None and segment.spool_id is not None
            spool = spools[segment.spool_id]
            assert spool.effective_remaining is not None
            decision = ConsumptionDecision(
                id=EntityId.new(),
                device_id=actor,
                created_at=at,
                finalization_record_id=record.id,
                material_usage_segment_id=segment.id,
                selected_mass=item.mass,
                confidence_bp=item.confidence_bp,
                strategy="verified_3mf_estimate",
                policy_version=POLICY_VERSION,
                reason_code="calculated.verified_file_estimate",
                finalized_at=at,
            )
            decisions.append(decision)
            links.append(
                DecisionEvidence(
                    id=EntityId.new(),
                    device_id=actor,
                    created_at=at,
                    decision_id=decision.id,
                    evidence_id=item.id,
                    role="SELECTED_ESTIMATE",
                )
            )
            pair = (segment.print_job_material_id, segment.spool_id)
            pair_mass[pair] += item.mass.milligrams
            if item.mass.milligrams:
                claim = own.get(pair)
                unit_cost, currency, metadata_json = (None, None, item.metadata_json)
                if job.status is PrintStatus.COMPLETED:
                    unit_cost, currency, metadata_json = with_cost_snapshot(
                        spool, item.mass, item.metadata_json,
                    )
                entry = FilamentTransaction(
                    id=EntityId.new(),
                    device_id=actor,
                    created_at=at,
                    spool_id=spool.id,
                    sequence=spool.ledger_sequence + 1,
                    transaction_type=TransactionType.PRINT_CONSUMPTION
                    if job.status is PrintStatus.COMPLETED
                    else TransactionType.FAILED_PRINT,
                    delta=Mass(-item.mass.milligrams),
                    previous_effective=spool.effective_remaining,
                    new_effective=spool.effective_remaining - item.mass,
                    previous_estimated=spool.estimated_remaining,
                    new_estimated=None
                    if spool.estimated_remaining is None
                    else spool.estimated_remaining - item.mass,
                    command_key=key,
                    command_item=index,
                    source_type="THREE_MF",
                    confidence_bp=item.confidence_bp,
                    estimate_policy_version=POLICY_VERSION,
                    print_job_id=job.id,
                    decision_id=decision.id,
                    source_receipt_id=receipt.id,
                    reservation_id=None if claim is None else claim.id,
                    description=LABEL,
                    metadata_json=metadata_json,
                    unit_cost=unit_cost,
                    currency=currency,
                )
                entries.append(entry)
                spools[spool.id] = replace(
                    spool,
                    effective_remaining=entry.new_effective,
                    estimated_remaining=entry.new_estimated,
                    ledger_sequence=entry.sequence,
                    updated_at=at,
                    revision=spool.revision + 1,
                )
        audit = AuditEvent(
            id=EntityId.new(),
            device_id=actor,
            created_at=at,
            event_code=EVENT,
            actor_device_id=actor,
            correlation_id=key,
            entity_type="print_job",
            entity_id=job.id,
            parameters_json=json.dumps(
                {
                    "request_hash_v1": fingerprint,
                    "finalization_id": str(record.id),
                    "policy_version": POLICY_VERSION,
                    "quantity": "estimate",
                    "label": LABEL,
                    "selected_mass_mg": sum(item.selected_mass.milligrams for item in decisions),
                },
                sort_keys=True,
            ),
        )
        # Reservations reference finalization_record, so compute their terminal
        # shapes in memory and insert the record before applying settlements.
        settled = []
        for claim in claims:
            mass = Mass(pair_mass[(claim.print_job_material_id, claim.spool_id)])
            allocated, released = reservation_settlement(claim.reserved, mass)
            zero = allocated.milligrams == 0
            settled.append(
                replace(
                    claim,
                    state=ReservationState.RELEASED if zero else ReservationState.CONSUMED,
                    allocated_consumption=allocated,
                    released=released,
                    settled_finalization_id=record.id,
                    consumed_at=None if zero else at,
                    released_at=at if zero else None,
                    reason="zero_consumption" if zero else None,
                    updated_at=at,
                    revision=claim.revision + 1,
                )
            )
        record = replace(
            record,
            result_hash=self._outcome_hash(
                record, loaded, decisions, links, entries, settled, [audit]
            ),
        )
        work.finalizations.add(record)
        for decision, link in zip(decisions, links, strict=True):
            work.decisions.add(decision)
            work.decisions.add_evidence_link(link)
        # Preserve intermediate projections when multiple segments use one spool.
        original = {key: work.spools.get(key) for key in spools}
        for entry in entries:
            spool = original[entry.spool_id]
            work.ledger.append(entry)
            updated = replace(
                spool,
                effective_remaining=entry.new_effective,
                estimated_remaining=entry.new_estimated,
                ledger_sequence=entry.sequence,
                revision=spool.revision + 1,
                updated_at=at,
            )
            work.spools.save(updated, spool.revision)
            original[spool.id] = updated
        for spool in original.values():
            FinalizationCommands._low_stock_alert(work, spool, actor, at)
        for previous, final in zip(claims, settled, strict=True):
            work.reservations.save(final, previous.revision)
        work.jobs.save(
            replace(
                running,
                finalization_state=FinalizationState.FINALIZED,
                revision=running.revision + 1,
            ),
            running.revision,
        )
        work.receipts.save(
            replace(
                receipt,
                state=ReceiptState.PROCESSED,
                processed_at=at,
                reason_code="CALCULATED_PRINT_FINALIZED",
                updated_at=at,
                revision=receipt.revision + 1,
            ),
            receipt.revision,
        )
        work.audit.append(audit)
        work.commit()
        return record

    @staticmethod
    def _outcome_hash(
        record: FinalizationRecord,
        loaded: _Loaded,
        decisions: Sequence[ConsumptionDecision],
        links: Sequence[DecisionEvidence],
        entries: Sequence[FilamentTransaction],
        claims: Sequence[Reservation],
        audit: Sequence[AuditEvent],
    ) -> str:
        header = asdict(record)
        header.pop("result_hash")

        def records(items: Sequence[Any], key: str = "id") -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = [asdict(item) for item in items]
            return sorted(rows, key=lambda item: str(item[key]))

        return _hash(
            {
                "record": header,
                "job": str(loaded.job.id),
                "receipt": str(loaded.receipt.id),
                "decisions": records(decisions),
                "links": records(links),
                "entries": records(entries, "command_item"),
                "claims": records(claims),
                "audit": records(audit),
            }
        )

    def _result_hash(self, work: UnitOfWork, record: FinalizationRecord, loaded: _Loaded) -> str:
        return self._outcome_hash(
            record,
            loaded,
            work.decisions.for_finalization(record.id),
            work.decisions.evidence_links_for_finalization(record.id),
            work.ledger.for_command(record.idempotency_key),
            work.reservations.for_finalization(record.id),
            work.audit.for_command(record.idempotency_key),
        )
