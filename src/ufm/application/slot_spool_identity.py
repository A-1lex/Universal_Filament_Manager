"""Resolve observed feed-slot identifiers without creating a spool mount."""

from dataclasses import dataclass
from enum import StrEnum

from ufm.application.dto.providers import FeedSlotSnapshot
from ufm.application.ports.persistence import SpoolIdentifierRepository
from ufm.domain.enums import Availability
from ufm.domain.value_objects import EntityId


class SlotSpoolMatchState(StrEnum):
    MATCHED = "MATCHED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class SlotSpoolResolution:
    slot_key: str
    state: SlotSpoolMatchState
    spool_id: EntityId | None = None
    matched_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.slot_key or len(self.slot_key) > 500:
            raise ValueError("slot_identity.slot_key_invalid")
        if type(self.matched_kinds) is not tuple or len(set(self.matched_kinds)) != len(self.matched_kinds):
            raise ValueError("slot_identity.matched_kinds_invalid")
        if self.state is SlotSpoolMatchState.MATCHED:
            if self.spool_id is None or not self.matched_kinds:
                raise ValueError("slot_identity.match_shape_invalid")
        elif self.spool_id is not None:
            raise ValueError("slot_identity.nonmatch_has_spool")
        if self.state is SlotSpoolMatchState.CONFLICT and len(self.matched_kinds) < 2:
            raise ValueError("slot_identity.conflict_shape_invalid")


def resolve_feed_slot_spool(
    snapshot: FeedSlotSnapshot,
    *,
    namespace: str,
    identifiers: SpoolIdentifierRepository,
) -> SlotSpoolResolution:
    """Match only exact, verified UUID/tag bindings; colour/type are non-identifiers."""
    if type(namespace) is not str or not namespace.strip() or len(namespace) > 200:
        raise ValueError("slot_identity.namespace_invalid")

    matches: dict[EntityId, list[str]] = {}
    for kind, observation in (("tray_uuid", snapshot.tray_uuid), ("tag_uid", snapshot.tag_uid)):
        value = observation.value
        if observation.availability is not Availability.KNOWN or type(value) is not str:
            continue
        identifier = identifiers.by_trusted_identity(namespace, kind, value)
        if identifier is None:
            continue
        if (
            not identifier.is_trusted_current
            or identifier.deleted_at is not None
            or (identifier.namespace, identifier.kind, identifier.value) != (namespace, kind, value)
        ):
            raise ValueError("slot_identity.repository_result_invalid")
        matches.setdefault(identifier.spool_id, []).append(kind)

    kinds = tuple(sorted(kind for found in matches.values() for kind in found))
    if len(matches) > 1:
        return SlotSpoolResolution(snapshot.slot_key, SlotSpoolMatchState.CONFLICT, matched_kinds=kinds)
    if not matches:
        return SlotSpoolResolution(snapshot.slot_key, SlotSpoolMatchState.UNKNOWN)
    spool_id, found_kinds = next(iter(matches.items()))
    return SlotSpoolResolution(
        snapshot.slot_key, SlotSpoolMatchState.MATCHED, spool_id,
        tuple(sorted(found_kinds)),
    )
