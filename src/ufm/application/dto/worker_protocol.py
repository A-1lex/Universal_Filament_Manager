"""Versioned, untrusted calculation-worker messages; never inventory commands.

Only the parent application may issue a finalization outcome. A ready proposal
is still subject to persisted receipt/evidence/job checks inside a UFM UoW.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Self, cast
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

Token = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonnegative = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000_000)]
Confidence = Annotated[int, Field(strict=True, ge=0, le=10_000)]
LogicalId = Annotated[int, Field(strict=True, ge=0, le=255)]


@dataclass(frozen=True, slots=True)
class WorkerScope:
    printer_id: UUID
    source_epoch: str
    request_id: str


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Envelope(WireModel):
    v: Annotated[int, Field(strict=True, ge=1, le=1)]
    request_id: Token
    printer_id: UUID
    source_epoch: Token
    sequence: Nonnegative
    observed_at: AwareDatetime


class StatusMessage(Envelope):
    kind: Literal["status"]
    connection: Literal["connected", "offline", "retrying", "disabled"]
    reason_code: Token | None = None


class MaterialSlotMappingFact(WireModel):
    logical_material: LogicalId
    disposition: Literal["reported_slot", "unused", "unsupported"]
    provider_system_key: Token | None = None
    provider_slot_key: Token | None = None

    @model_validator(mode="after")
    def reference_shape(self) -> Self:
        has_any_reference = (
            self.provider_system_key is not None or self.provider_slot_key is not None
        )
        has_complete_reference = (
            self.provider_system_key is not None and self.provider_slot_key is not None
        )
        if ((self.disposition == "reported_slot") != has_complete_reference
                or (self.disposition != "reported_slot" and has_any_reference)):
            raise ValueError("worker.material_mapping_reference_invalid")
        return self


class JobMessage(Envelope):
    kind: Literal["job"]
    occurrence_key: Token
    state: Literal["started", "running", "paused", "completed", "failed", "cancelled"]
    file_sha256: Digest | None = None
    completed_layers: Nonnegative | None = None
    current_layer: Nonnegative | None = None
    progress_bp: Annotated[int, Field(strict=True, ge=0, le=10_000)] | None = None
    exact_started_at: AwareDatetime | None = None
    exact_started_at_source: Literal["printer_reported", "provider_reported"] | None = None
    exact_ended_at: AwareDatetime | None = None
    exact_ended_at_source: Literal["printer_reported", "provider_reported"] | None = None
    material_slot_mappings: Annotated[tuple[MaterialSlotMappingFact, ...], Field(max_length=256)] = ()

    @model_validator(mode="after")
    def unique_material_mappings(self) -> Self:
        if len({item.logical_material for item in self.material_slot_mappings}) != len(
            self.material_slot_mappings
        ):
            raise ValueError("worker.duplicate_material_mapping")
        if (self.exact_started_at is None) != (self.exact_started_at_source is None):
            raise ValueError("worker.exact_start_provenance_required")
        if (self.exact_ended_at is None) != (self.exact_ended_at_source is None):
            raise ValueError("worker.exact_end_provenance_required")
        if self.exact_ended_at is not None and self.state not in {
            "completed", "failed", "cancelled",
        }:
            raise ValueError("worker.exact_end_requires_terminal_state")
        if (self.exact_started_at is not None and self.exact_ended_at is not None
                and self.exact_ended_at < self.exact_started_at):
            raise ValueError("worker.exact_lifecycle_interval_invalid")
        return self


class SlotFact(WireModel):
    slot_key: Token
    logical_material: LogicalId | None = None
    identifier: Token | None = None


class SlotsMessage(Envelope):
    kind: Literal["slots"]
    occurrence_key: Token | None = None
    slots: Annotated[tuple[SlotFact, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def unique_slots(self) -> Self:
        if len({item.slot_key for item in self.slots}) != len(self.slots):
            raise ValueError("worker.duplicate_slot")
        return self


class EvidenceMessage(Envelope):
    kind: Literal["evidence"]
    occurrence_key: Token
    file_sha256: Digest
    plate: Annotated[int, Field(strict=True, ge=1, le=256)]
    source: Literal["three_mf", "gcode", "slicer", "printer"]
    quantity: Literal["estimate", "measurement"]
    confidence_bp: Confidence
    includes_purge: bool | None
    interval_start: AwareDatetime
    interval_end: AwareDatetime

    @model_validator(mode="after")
    def consistent_evidence(self) -> Self:
        if self.interval_end < self.interval_start:
            raise ValueError("worker.interval_reversed")
        if self.source != "printer" and self.quantity != "estimate":
            raise ValueError("worker.file_is_not_measurement")
        return self


class MaterialEstimate(WireModel):
    logical_material: LogicalId
    mass_mg: Nonnegative


class SpoolAllocation(WireModel):
    allocation_id: UUID
    logical_material: LogicalId
    segment_id: UUID
    spool_id: UUID
    mass_mg: Nonnegative


class ProposalMessage(Envelope):
    kind: Literal["proposal"]
    occurrence_key: Token
    file_sha256: Digest
    evidence_id: UUID
    policy_version: Token
    quantity: Literal["estimate"]
    label: Literal["Розрахункова витрата"]
    confidence_bp: Confidence
    status: Literal["ready", "needs_mapping"]
    partial: bool
    materials: Annotated[tuple[MaterialEstimate, ...], Field(min_length=1, max_length=256)]
    allocations: Annotated[tuple[SpoolAllocation, ...], Field(max_length=1024)]

    @model_validator(mode="after")
    def consistent_allocations(self) -> Self:
        expected = {item.logical_material: item.mass_mg for item in self.materials}
        if len(expected) != len(self.materials):
            raise ValueError("worker.duplicate_material")
        seen: set[UUID] = set()
        segments: set[UUID] = set()
        assigned: dict[int, int] = defaultdict(int)
        for item in self.allocations:
            if item.allocation_id in seen or item.segment_id in segments:
                raise ValueError("worker.duplicate_allocation")
            seen.add(item.allocation_id)
            segments.add(item.segment_id)
            if item.logical_material not in expected:
                raise ValueError("worker.unexpected_material")
            assigned[item.logical_material] += item.mass_mg
            if assigned[item.logical_material] > expected[item.logical_material]:
                raise ValueError("worker.overallocated_material")
        if self.status == "ready" and (
            set(assigned) != set(expected) or dict(assigned) != expected
        ):
            raise ValueError("worker.incomplete_allocation")
        return self


class ErrorMessage(Envelope):
    kind: Literal["error"]
    code: Token
    retryable: bool


class FinalizationOutcome(Envelope):
    """Parent-to-worker acknowledgement; must never be accepted as a fact."""

    kind: Literal["finalization_outcome"]
    job_id: UUID
    receipt_id: UUID
    outcome: Literal["committed", "already_committed", "rejected"]
    finalization_id: UUID | None = None
    reason_code: Token | None = None

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.outcome != "rejected" and self.finalization_id is None:
            raise ValueError("worker.finalization_id_required")
        if self.outcome == "rejected" and (self.reason_code is None or self.finalization_id is not None):
            raise ValueError("worker.rejection_invalid")
        return self


WorkerMessage = Annotated[
    StatusMessage | JobMessage | SlotsMessage | EvidenceMessage | ProposalMessage | ErrorMessage,
    Field(discriminator="kind"),
]
_WORKER_ADAPTER: TypeAdapter[WorkerMessage] = TypeAdapter(cast(Any, WorkerMessage))
MAX_WIRE_BYTES = 512 * 1024


class WorkerProtocolRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("worker.frame_invalid")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkerProtocolRejected()
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise WorkerProtocolRejected()


def decode_worker_message(payload: bytes) -> WorkerMessage:
    if type(payload) is not bytes or len(payload) > MAX_WIRE_BYTES:
        raise WorkerProtocolRejected()
    try:
        json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        return _WORKER_ADAPTER.validate_json(payload)
    except (ValueError, UnicodeError, RecursionError):
        # ValidationError includes input values by default; never cross the
        # process/UI boundary with a raw exception containing untrusted facts.
        raise WorkerProtocolRejected() from None
