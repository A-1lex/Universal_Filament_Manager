"""Bounded sync envelopes; defining them does not enable synchronization."""

from dataclasses import dataclass, field

from ufm.domain.value_objects import EntityId


def _text(value: str, code: str, *, limit: int = 500) -> None:
    if type(value) is not str or not value or len(value) > limit:
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class SyncChange:
    change_id: EntityId
    entity_type: str
    entity_id: EntityId
    base_revision: int
    new_revision: int
    payload_hash: str
    payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.entity_type, "sync_change.entity_type_invalid", limit=200)
        _text(self.payload_hash, "sync_change.payload_hash_invalid")
        if type(self.base_revision) is not int or self.base_revision < 0:
            raise ValueError("sync_change.base_revision_invalid")
        if type(self.new_revision) is not int or self.new_revision <= self.base_revision:
            raise ValueError("sync_change.new_revision_invalid")
        if type(self.payload) is not bytes or len(self.payload) > 16_777_216:
            raise ValueError("sync_change.payload_invalid")


@dataclass(frozen=True, slots=True)
class SyncBatch:
    request_id: EntityId
    device_id: EntityId
    cursor: str | None
    changes: tuple[SyncChange, ...]

    def __post_init__(self) -> None:
        if self.cursor is not None:
            _text(self.cursor, "sync_batch.cursor_invalid", limit=2_000)
        if type(self.changes) is not tuple or len(self.changes) > 1_000:
            raise ValueError("sync_batch.changes_invalid")
        ids = [change.change_id for change in self.changes]
        if len(ids) != len(set(ids)):
            raise ValueError("sync_batch.duplicate_change")


@dataclass(frozen=True, slots=True)
class SyncConflict:
    change_id: EntityId
    reason_code: str

    def __post_init__(self) -> None:
        _text(self.reason_code, "sync_conflict.reason_invalid")


@dataclass(frozen=True, slots=True)
class SyncResult:
    next_cursor: str
    accepted_change_ids: tuple[EntityId, ...]
    conflicts: tuple[SyncConflict, ...]

    def __post_init__(self) -> None:
        _text(self.next_cursor, "sync_result.cursor_invalid", limit=2_000)
        if type(self.accepted_change_ids) is not tuple or len(self.accepted_change_ids) > 1_000:
            raise ValueError("sync_result.accepted_invalid")
        if type(self.conflicts) is not tuple or len(self.conflicts) > 1_000:
            raise ValueError("sync_result.conflicts_invalid")
        accepted = set(self.accepted_change_ids)
        conflicted = {conflict.change_id for conflict in self.conflicts}
        if accepted & conflicted:
            raise ValueError("sync_result.outcome_conflict")
