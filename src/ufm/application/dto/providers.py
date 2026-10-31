"""Vendor-neutral printer observations."""

from dataclasses import dataclass, fields
from typing import Literal

from ufm.domain.enums import (
    Availability,
    ConnectionState,
    FeedSystemKind,
    PrintStatus,
    ProviderHealthState,
)
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime


def _bounded_text(value: str, code: str) -> None:
    if type(value) is not str or not value or len(value) > 500:
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class Observed[ValueT]:
    availability: Availability
    observed_at: UtcDateTime
    received_at: UtcDateTime
    value: ValueT | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.availability is Availability.KNOWN and self.value is None:
            raise ValueError("observation.known_value_required")
        if self.availability in {
            Availability.UNKNOWN,
            Availability.UNAVAILABLE,
            Availability.UNSUPPORTED,
        } and self.value is not None:
            raise ValueError("observation.unavailable_value_forbidden")
        if self.reason_code is not None:
            _bounded_text(self.reason_code, "observation.reason_invalid")


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    state: ProviderHealthState
    checked_at: UtcDateTime
    reason_code: str
    retryable: bool

    def __post_init__(self) -> None:
        if type(self.retryable) is not bool:
            raise TypeError("provider_health.retryable_invalid")
        if type(self.reason_code) is not str or not self.reason_code:
            raise ValueError("provider_health.reason_invalid")


@dataclass(frozen=True, slots=True)
class PrinterCapabilities:
    schema_version: int
    job_detection: Observed[bool]
    progress: Observed[bool]
    layers: Observed[bool]
    temperature: Observed[bool]
    camera: Observed[bool]
    pause: Observed[bool]
    resume: Observed[bool]
    cancel: Observed[bool]
    filament_usage: Observed[bool]
    multi_material: Observed[bool]
    file_metadata: Observed[bool]
    local_connection: Observed[bool]
    cloud_connection: Observed[bool]
    push_events: Observed[bool]
    polling: Observed[bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("capabilities.schema_version_invalid")
        for field in fields(self):
            if field.name == "schema_version":
                continue
            observation = getattr(self, field.name)
            if observation.value is not None and type(observation.value) is not bool:
                raise TypeError("capabilities.value_invalid")


@dataclass(frozen=True, slots=True)
class ProviderMaterialSlotMapping:
    """Explicit printer-reported logical filament index to provider slot."""

    logical_material: int
    disposition: Literal["reported_slot", "unused", "unsupported"]
    provider_system_key: str | None = None
    provider_slot_key: str | None = None

    def __post_init__(self) -> None:
        if type(self.logical_material) is not int or not 0 <= self.logical_material <= 255:
            raise ValueError("material_slot_mapping.logical_material_invalid")
        if self.disposition not in {"reported_slot", "unused", "unsupported"}:
            raise ValueError("material_slot_mapping.disposition_invalid")
        has_reference = self.provider_system_key is not None and self.provider_slot_key is not None
        if (self.disposition == "reported_slot") != has_reference:
            raise ValueError("material_slot_mapping.reference_invalid")
        if has_reference:
            _bounded_text(self.provider_system_key or "", "material_slot_mapping.system_invalid")
            _bounded_text(self.provider_slot_key or "", "material_slot_mapping.slot_invalid")


@dataclass(frozen=True, slots=True)
class PrintJobSnapshot:
    source: str
    source_epoch: str
    status: PrintStatus
    observed_at: UtcDateTime
    received_at: UtcDateTime
    provider_run_key: str | None = None
    external_job_id: str | None = None
    provider_task_id: str | None = None
    provider_subtask_id: str | None = None
    provider_job_id: str | None = None
    provider_ams_mapping: tuple[int, ...] | None = None
    provider_ams_mapping2: tuple[tuple[int, int], ...] | None = None
    exact_started_at: UtcDateTime | None = None
    exact_started_at_source: Literal["printer_reported", "provider_reported"] | None = None
    project_uuid: str | None = None
    file_hash: str | None = None
    progress_bp: int | None = None
    current_layer: int | None = None
    completed_layers: int | None = None
    material_slot_mappings: tuple[ProviderMaterialSlotMapping, ...] = ()

    def __post_init__(self) -> None:
        _bounded_text(self.source, "job_snapshot.identity_scope_invalid")
        _bounded_text(self.source_epoch, "job_snapshot.identity_scope_invalid")
        if (
            (self.exact_started_at is None) != (self.exact_started_at_source is None)
            or self.exact_started_at_source not in {None, "printer_reported", "provider_reported"}
        ):
            raise ValueError("job_snapshot.start_time_provenance_required")
        for value in (
            self.provider_run_key,
            self.external_job_id,
            self.provider_task_id,
            self.provider_subtask_id,
            self.provider_job_id,
            self.project_uuid,
            self.file_hash,
        ):
            if value is not None:
                _bounded_text(value, "job_snapshot.field_invalid")
        if self.progress_bp is not None and (
            type(self.progress_bp) is not int or not 0 <= self.progress_bp <= 10_000
        ):
            raise ValueError("job_snapshot.progress_invalid")
        if self.current_layer is not None and (type(self.current_layer) is not int or self.current_layer < 0):
            raise ValueError("job_snapshot.layer_invalid")
        if self.completed_layers is not None and (
            type(self.completed_layers) is not int or self.completed_layers < 0
        ):
            raise ValueError("job_snapshot.completed_layers_invalid")
        if self.provider_ams_mapping is not None and (
            type(self.provider_ams_mapping) is not tuple
            or len(self.provider_ams_mapping) > 256
            or any(type(value) is not int or not -1 <= value <= 65_535
                   for value in self.provider_ams_mapping)
        ):
            raise ValueError("job_snapshot.provider_ams_mapping_invalid")
        if self.provider_ams_mapping2 is not None and (
            type(self.provider_ams_mapping2) is not tuple
            or len(self.provider_ams_mapping2) > 256
            or any(
                type(pair) is not tuple or len(pair) != 2
                or any(type(value) is not int or not 0 <= value <= 255 for value in pair)
                for pair in self.provider_ams_mapping2
            )
        ):
            raise ValueError("job_snapshot.provider_ams_mapping2_invalid")
        if (type(self.material_slot_mappings) is not tuple
                or len(self.material_slot_mappings) > 256
                or any(not isinstance(item, ProviderMaterialSlotMapping)
                       for item in self.material_slot_mappings)
                or len({item.logical_material for item in self.material_slot_mappings})
                != len(self.material_slot_mappings)):
            raise ValueError("job_snapshot.material_mapping_invalid")


@dataclass(frozen=True, slots=True)
class CurrentJobObservation:
    availability: Availability
    observed_at: UtcDateTime
    received_at: UtcDateTime
    job: PrintJobSnapshot | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.availability in {
            Availability.UNKNOWN,
            Availability.UNAVAILABLE,
            Availability.UNSUPPORTED,
        } and self.job is not None:
            raise ValueError("current_job.unavailable_value_forbidden")


@dataclass(frozen=True, slots=True)
class FeedSlotSnapshot:
    slot_key: str
    occupancy: Observed[bool]
    tray_uuid: Observed[str]
    tag_uid: Observed[str]
    assigned_spool_id: Observed[EntityId]
    remaining_mass: Observed[Mass]
    remaining_percent: Observed[int] | None = None

    def __post_init__(self) -> None:
        _bounded_text(self.slot_key, "feed_slot_snapshot.slot_key_invalid")
        if self.occupancy.value is not None and type(self.occupancy.value) is not bool:
            raise TypeError("feed_slot_snapshot.occupancy_invalid")
        for identifier in (self.tray_uuid.value, self.tag_uid.value):
            if identifier is not None:
                _bounded_text(identifier, "feed_slot_snapshot.identifier_invalid")
        if self.assigned_spool_id.value is not None and not isinstance(
            self.assigned_spool_id.value, EntityId
        ):
            raise TypeError("feed_slot_snapshot.assignment_invalid")
        if self.remaining_mass.value is not None and not isinstance(
            self.remaining_mass.value, Mass
        ):
            raise TypeError("feed_slot_snapshot.remaining_mass_invalid")
        if self.remaining_percent is not None and self.remaining_percent.value is not None:
            if (
                type(self.remaining_percent.value) is not int
                or not 0 <= self.remaining_percent.value <= 100
            ):
                raise ValueError("feed_slot_snapshot.remaining_percent_invalid")


@dataclass(frozen=True, slots=True)
class FeedSystemSnapshot:
    provider_system_key: str
    kind: FeedSystemKind
    slots: tuple[FeedSlotSnapshot, ...]
    observed_at: UtcDateTime
    received_at: UtcDateTime
    complete: bool
    source_epoch: str | None = None
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        _bounded_text(self.provider_system_key, "feed_system_snapshot.key_invalid")
        if type(self.slots) is not tuple or len(self.slots) > 256:
            raise ValueError("feed_system_snapshot.slots_invalid")
        if type(self.complete) is not bool:
            raise TypeError("feed_system_snapshot.complete_invalid")
        if self.source_epoch is not None:
            _bounded_text(self.source_epoch, "feed_system_snapshot.epoch_invalid")
        if self.source_sequence is not None and (
            type(self.source_sequence) is not int or self.source_sequence < 0
        ):
            raise ValueError("feed_system_snapshot.sequence_invalid")
        keys = [slot.slot_key for slot in self.slots]
        if len(keys) != len(set(keys)):
            raise ValueError("feed_system_snapshot.duplicate_slot")


@dataclass(frozen=True, slots=True)
class PrinterStatusSnapshot:
    printer_id: EntityId
    connection_state: ConnectionState
    observed_at: UtcDateTime
    received_at: UtcDateTime
    progress: Observed[int]
    current_layer: Observed[int]
    nozzle_temperature_c: Observed[ExactDecimal]
    bed_temperature_c: Observed[ExactDecimal]
    feed_systems: tuple[FeedSystemSnapshot, ...]
    source_epoch: str | None = None
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        if self.progress.value is not None and type(self.progress.value) is not int:
            raise TypeError("printer_status.integer_observation_invalid")
        if self.current_layer.value is not None and type(self.current_layer.value) is not int:
            raise TypeError("printer_status.integer_observation_invalid")
        if self.nozzle_temperature_c.value is not None and not isinstance(
            self.nozzle_temperature_c.value, ExactDecimal
        ):
            raise TypeError("printer_status.temperature_invalid")
        if self.bed_temperature_c.value is not None and not isinstance(
            self.bed_temperature_c.value, ExactDecimal
        ):
            raise TypeError("printer_status.temperature_invalid")
        if type(self.feed_systems) is not tuple or len(self.feed_systems) > 64:
            raise ValueError("printer_status.feed_systems_invalid")
        if self.source_epoch is not None:
            _bounded_text(self.source_epoch, "printer_status.epoch_invalid")
        if self.source_sequence is not None and (
            type(self.source_sequence) is not int or self.source_sequence < 0
        ):
            raise ValueError("printer_status.sequence_invalid")


@dataclass(frozen=True, slots=True)
class PrinterEvent:
    provider_instance_id: EntityId
    printer_id: EntityId
    source_epoch: str
    event_key: str
    kind: str
    observed_at: UtcDateTime
    received_at: UtcDateTime
    payload_hash: str
    job: PrintJobSnapshot | None = None
    feed_system: FeedSystemSnapshot | None = None

    def __post_init__(self) -> None:
        for value in (self.source_epoch, self.event_key, self.kind, self.payload_hash):
            _bounded_text(value, "printer_event.field_invalid")
