"""Reservation, evidence, receipt, and finalization records."""

from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord, ImmutableRecord
from ufm.domain.enums import (
    EvidenceMode,
    EvidenceSource,
    QuantityKind,
    ReceiptState,
    ReservationState,
)
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime
from ufm.domain.value_objects.json_object import json_object


def _confidence(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 10_000:
        raise ValueError("evidence.confidence_invalid")


def _text(value: str, code: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 500:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class Reservation(EntityRecord):
    spool_id: EntityId
    print_job_material_id: EntityId
    reserved: Mass
    state: ReservationState
    activated_at: UtcDateTime | None = None
    consumed_at: UtcDateTime | None = None
    released_at: UtcDateTime | None = None
    expires_at: UtcDateTime | None = None
    settled_finalization_id: EntityId | None = None
    allocated_consumption: Mass | None = None
    released: Mass | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        super(Reservation, self).__post_init__()
        if self.reserved.milligrams <= 0:
            raise ValueError("reservation.mass_invalid")
        if self.state is ReservationState.ACTIVE and self.activated_at is None:
            raise ValueError("reservation.activation_missing")
        if self.state is ReservationState.CONSUMED and (
            self.consumed_at is None or self.settled_finalization_id is None
        ):
            raise ValueError("reservation.settlement_missing")
        if self.state is ReservationState.RELEASED and self.released_at is None:
            raise ValueError("reservation.release_missing")
        for value in (self.allocated_consumption, self.released):
            if value is not None and value.milligrams < 0:
                raise ValueError("reservation.settlement_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalEventReceipt(EntityRecord):
    provider_instance_id: EntityId
    printer_id: EntityId
    source_epoch: str
    event_key: str
    event_type: str
    payload_hash: str
    received_at: UtcDateTime
    state: ReceiptState
    processed_at: UtcDateTime | None = None
    reason_code: str | None = None
    sanitized_metadata: str | None = None

    def __post_init__(self) -> None:
        super(ExternalEventReceipt, self).__post_init__()
        for value in (self.source_epoch, self.event_key, self.event_type, self.payload_hash):
            _text(value, "receipt.field_invalid")
        if (self.state is ReceiptState.PROCESSED) != (self.processed_at is not None):
            raise ValueError("receipt.processed_at_invalid")
        if self.sanitized_metadata is not None:
            json_object(self.sanitized_metadata)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumptionEvidence(ImmutableRecord):
    print_job_material_id: EntityId
    source: EvidenceSource
    quantity_kind: QuantityKind
    mode: EvidenceMode
    confidence_bp: int
    captured_at: UtcDateTime
    received_at: UtcDateTime
    scope_key: str
    segment_id: EntityId | None = None
    mass: Mass | None = None
    length_mm: int | None = None
    interval_start: UtcDateTime | None = None
    interval_end: UtcDateTime | None = None
    includes_purge: bool | None = None
    calibration_id: EntityId | None = None
    source_receipt_id: EntityId | None = None
    external_reference: str | None = None
    metadata_json: str = "{}"

    def __post_init__(self) -> None:
        _confidence(self.confidence_bp)
        json_object(self.metadata_json)
        _text(self.scope_key, "evidence.scope_invalid")
        if self.quantity_kind is QuantityKind.REMAINING_MASS:
            raise ValueError("evidence.remaining_belongs_to_inventory")
        if self.quantity_kind is QuantityKind.CONSUMED_MASS:
            if self.mass is None or self.length_mm is not None or self.mass.milligrams < 0:
                raise ValueError("evidence.mass_shape_invalid")
        elif self.quantity_kind is QuantityKind.LENGTH:
            if self.length_mm is None or type(self.length_mm) is not int or self.length_mm < 0 or self.mass is not None:
                raise ValueError("evidence.length_shape_invalid")
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("evidence.interval_incomplete")
        if self.interval_end is not None and self.interval_start is not None and self.interval_end < self.interval_start:
            raise ValueError("evidence.interval_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryEvidence(ImmutableRecord):
    spool_id: EntityId
    source: EvidenceSource
    captured_at: UtcDateTime
    received_at: UtcDateTime
    gross: Mass | None = None
    tare: Mass | None = None
    net: Mass | None = None
    sensor_id: EntityId | None = None
    calibration_id: EntityId | None = None
    stability_bp: int | None = None
    stable_duration_ms: int | None = None
    ledger_cutoff: int | None = None

    def __post_init__(self) -> None:
        if self.gross is None and self.tare is None and self.net is None:
            raise ValueError("inventory_evidence.quantity_missing")
        for value in (self.gross, self.tare, self.net):
            if value is not None and value.milligrams < 0:
                raise ValueError("inventory_evidence.negative_mass")
        if self.gross is not None and self.tare is not None and self.net is not None:
            if self.net != self.gross - self.tare:
                raise ValueError("inventory_evidence.net_mismatch")
        if self.stability_bp is not None:
            _confidence(self.stability_bp)
        for number in (self.stable_duration_ms, self.ledger_cutoff):
            if number is not None and (type(number) is not int or number < 0):
                raise ValueError("inventory_evidence.number_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizationRecord(ImmutableRecord):
    print_job_id: EntityId
    idempotency_key: str
    request_hash: str
    started_at: UtcDateTime
    completed_at: UtcDateTime
    result_hash: str

    def __post_init__(self) -> None:
        for value in (self.idempotency_key, self.request_hash, self.result_hash):
            _text(value, "finalization.field_invalid")
        if self.completed_at < self.started_at:
            raise ValueError("finalization.interval_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumptionDecision(ImmutableRecord):
    finalization_record_id: EntityId
    material_usage_segment_id: EntityId
    selected_mass: Mass
    confidence_bp: int
    strategy: str
    policy_version: str
    reason_code: str
    finalized_at: UtcDateTime
    resolved_by_device_id: EntityId | None = None

    def __post_init__(self) -> None:
        if self.selected_mass.milligrams < 0:
            raise ValueError("decision.mass_invalid")
        _confidence(self.confidence_bp)
        for value in (self.strategy, self.policy_version, self.reason_code):
            _text(value, "decision.field_invalid")
