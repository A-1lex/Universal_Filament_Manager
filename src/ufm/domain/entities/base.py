"""Common entity metadata and revision invariants."""

from dataclasses import dataclass

from ufm.domain.value_objects import EntityId, UtcDateTime


@dataclass(frozen=True, slots=True, kw_only=True)
class EntityRecord:
    id: EntityId
    device_id: EntityId
    created_at: UtcDateTime
    updated_at: UtcDateTime
    revision: int
    deleted_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("entity.revision_invalid")
        if self.updated_at < self.created_at:
            raise ValueError("entity.timestamps_invalid")
        if self.deleted_at is not None and self.deleted_at < self.created_at:
            raise ValueError("entity.deleted_at_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ImmutableRecord:
    id: EntityId
    device_id: EntityId
    created_at: UtcDateTime
