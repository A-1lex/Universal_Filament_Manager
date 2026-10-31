"""Print runs, logical material channels, and physical usage segments."""

from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord
from ufm.domain.enums import FinalizationState, PrintStatus, SlotAssignment
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def _bounded_text(value: str, code: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 500:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class PrintJob(EntityRecord):
    printer_id: EntityId
    source_type: str
    status: PrintStatus
    finalization_state: FinalizationState
    detected_at: UtcDateTime
    external_job_id: str | None = None
    project_id: EntityId | None = None
    name: str | None = None
    file_name: str | None = None
    file_hash: str | None = None
    plate_name: str | None = None
    slicer_type: str | None = None
    started_at: UtcDateTime | None = None
    completed_at: UtcDateTime | None = None
    failed_at: UtcDateTime | None = None
    cancelled_at: UtcDateTime | None = None
    progress_bp: int | None = None
    current_layer: int | None = None
    total_layers: int | None = None

    def __post_init__(self) -> None:
        super(PrintJob, self).__post_init__()
        _bounded_text(self.source_type, "print_job.source_invalid")
        if self.progress_bp is not None and (
            type(self.progress_bp) is not int or not 0 <= self.progress_bp <= 10_000
        ):
            raise ValueError("print_job.progress_invalid")
        for layer in (self.current_layer, self.total_layers):
            if layer is not None and (type(layer) is not int or layer < 0):
                raise ValueError("print_job.layer_invalid")
        if (
            self.current_layer is not None
            and self.total_layers is not None
            and self.current_layer > self.total_layers
        ):
            raise ValueError("print_job.layers_inconsistent")


@dataclass(frozen=True, slots=True, kw_only=True)
class JobIdentityAlias:
    id: EntityId
    device_id: EntityId
    created_at: UtcDateTime
    print_job_id: EntityId
    provider_instance_id: EntityId
    printer_id: EntityId
    source_type: str
    source_epoch: str
    occurrence_key: str
    external_job_id: str | None = None
    started_at: UtcDateTime | None = None
    file_hash: str | None = None
    project_reference: str | None = None

    def __post_init__(self) -> None:
        for value, code in (
            (self.source_type, "job_identity.source_invalid"),
            (self.source_epoch, "job_identity.epoch_invalid"),
            (self.occurrence_key, "job_identity.occurrence_invalid"),
        ):
            _bounded_text(value, code)

    @property
    def occurrence_scope(self) -> tuple[EntityId, EntityId, str, str, str]:
        return (
            self.provider_instance_id,
            self.printer_id,
            self.source_type,
            self.source_epoch,
            self.occurrence_key,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PrintJobMaterial(EntityRecord):
    print_job_id: EntityId
    channel_key: str
    tool_index: int
    extruder_index: int | None = None
    logical_material_index: int | None = None
    filament_profile_id: EntityId | None = None
    estimated_mass: Mass | None = None
    estimated_length_mm: int | None = None

    def __post_init__(self) -> None:
        super(PrintJobMaterial, self).__post_init__()
        _bounded_text(self.channel_key, "print_material.channel_invalid")
        for value in (self.tool_index, self.extruder_index, self.estimated_length_mm):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("print_material.number_invalid")
        if self.logical_material_index is not None and (
            type(self.logical_material_index) is not int
            or not 0 <= self.logical_material_index <= 255
        ):
            raise ValueError("print_material.logical_material_index_invalid")
        if self.estimated_mass is not None and self.estimated_mass.milligrams < 0:
            raise ValueError("print_material.mass_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterialUsageSegment(EntityRecord):
    print_job_material_id: EntityId
    tool_index: int
    assignment_state: SlotAssignment
    started_at: UtcDateTime
    source: str
    confidence_bp: int
    ended_at: UtcDateTime | None = None
    feed_slot_id: EntityId | None = None
    spool_mount_id: EntityId | None = None
    spool_id: EntityId | None = None
    estimated_usage: Mass | None = None

    def __post_init__(self) -> None:
        super(MaterialUsageSegment, self).__post_init__()
        _bounded_text(self.source, "usage_segment.source_invalid")
        if type(self.tool_index) is not int or self.tool_index < 0:
            raise ValueError("usage_segment.tool_invalid")
        if type(self.confidence_bp) is not int or not 0 <= self.confidence_bp <= 10_000:
            raise ValueError("usage_segment.confidence_invalid")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("usage_segment.interval_invalid")
        if self.estimated_usage is not None and self.estimated_usage.milligrams < 0:
            raise ValueError("usage_segment.mass_invalid")
        physical_ids = (self.feed_slot_id, self.spool_mount_id, self.spool_id)
        if self.assignment_state is SlotAssignment.ASSIGNED and any(
            value is None for value in physical_ids
        ):
            raise ValueError("usage_segment.assignment_incomplete")
        if self.assignment_state is SlotAssignment.EMPTY:
            raise ValueError("usage_segment.empty_assignment")
