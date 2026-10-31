"""Physical printer and filament-feed topology entities."""

from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord
from ufm.domain.enums import AssignmentSource, FeedSystemKind, MountState, SlotAssignment
from ufm.domain.value_objects import EntityId, UtcDateTime


def _require_name(value: str, code: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 200:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class Printer(EntityRecord):
    name: str
    enabled: bool = True
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None

    def __post_init__(self) -> None:
        super(Printer, self).__post_init__()
        _require_name(self.name, "printer.name_invalid")
        if type(self.enabled) is not bool:
            raise TypeError("printer.enabled_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterialFeedSystem(EntityRecord):
    printer_id: EntityId
    kind: FeedSystemKind
    name: str
    provider_system_key: str | None = None

    def __post_init__(self) -> None:
        super(MaterialFeedSystem, self).__post_init__()
        _require_name(self.name, "feed_system.name_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class FeedSlot(EntityRecord):
    feed_system_id: EntityId
    slot_key: str
    assignment_state: SlotAssignment
    tool_index: int | None = None
    observed_at: UtcDateTime | None = None
    received_at: UtcDateTime | None = None
    source_epoch: str | None = None
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        super(FeedSlot, self).__post_init__()
        _require_name(self.slot_key, "feed_slot.key_invalid")
        if self.tool_index is not None and (type(self.tool_index) is not int or self.tool_index < 0):
            raise ValueError("feed_slot.tool_index_invalid")
        if self.source_sequence is not None and (
            type(self.source_sequence) is not int or self.source_sequence < 0
        ):
            raise ValueError("feed_slot.source_sequence_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpoolMount(EntityRecord):
    feed_slot_id: EntityId
    spool_id: EntityId
    state: MountState
    mounted_at: UtcDateTime
    assignment_source: AssignmentSource
    confidence_bp: int
    unmounted_at: UtcDateTime | None = None
    source_receipt_id: EntityId | None = None

    def __post_init__(self) -> None:
        super(SpoolMount, self).__post_init__()
        if type(self.confidence_bp) is not int or not 0 <= self.confidence_bp <= 10_000:
            raise ValueError("spool_mount.confidence_invalid")
        if self.state is MountState.ACTIVE and self.unmounted_at is not None:
            raise ValueError("spool_mount.active_has_end")
        if self.state is MountState.CLOSED and self.unmounted_at is None:
            raise ValueError("spool_mount.closed_missing_end")
        if self.unmounted_at is not None and self.unmounted_at < self.mounted_at:
            raise ValueError("spool_mount.interval_invalid")
