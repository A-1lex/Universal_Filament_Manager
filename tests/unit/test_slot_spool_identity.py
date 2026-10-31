import unittest
from datetime import UTC, datetime

from ufm.application.dto.providers import FeedSlotSnapshot, Observed
from ufm.application.ports.persistence import SpoolIdentifierRepository
from ufm.application.slot_spool_identity import (
    SlotSpoolMatchState,
    resolve_feed_slot_spool,
)
from ufm.domain.entities import SpoolIdentifier
from ufm.domain.enums import Availability
from ufm.domain.value_objects import EntityId, UtcDateTime


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 10, 28, tzinfo=UTC))


def observation[T](value: T | None) -> Observed[T]:
    return Observed(
        Availability.UNKNOWN if value is None else Availability.KNOWN,
        now(), now(), value,
    )


def identifier(
    spool_id: EntityId, kind: str, value: str, *, verified: bool = True,
) -> SpoolIdentifier:
    return SpoolIdentifier(
        id=EntityId.new(), device_id=EntityId.new(), created_at=now(), updated_at=now(),
        revision=1, deleted_at=None, spool_id=spool_id, namespace="bambu",
        kind=kind, value=value, verified_at=now() if verified else None,
    )


def snapshot(*, tray_uuid: str | None = None, tag_uid: str | None = None) -> FeedSlotSnapshot:
    return FeedSlotSnapshot(
        slot_key="0:1", occupancy=observation(True), tray_uuid=observation(tray_uuid),
        tag_uid=observation(tag_uid), assigned_spool_id=observation(None),
        remaining_mass=observation(None),
    )


class Identifiers(SpoolIdentifierRepository):
    def __init__(self, rows: list[SpoolIdentifier]) -> None:
        self.rows = {(row.namespace, row.kind, row.value): row for row in rows}

    def by_trusted_identity(self, namespace: str, kind: str, value: str) -> SpoolIdentifier | None:
        return self.rows.get((namespace, kind, value))


class SlotSpoolIdentityTests(unittest.TestCase):
    def test_exact_tray_uuid_and_tag_uid_can_resolve_same_spool(self) -> None:
        spool = EntityId.new()
        result = resolve_feed_slot_spool(
            snapshot(tray_uuid="tray-1", tag_uid="tag-1"), namespace="bambu",
            identifiers=Identifiers([
                identifier(spool, "tray_uuid", "tray-1"),
                identifier(spool, "tag_uid", "tag-1"),
            ]),
        )
        self.assertEqual(result.state, SlotSpoolMatchState.MATCHED)
        self.assertEqual(result.spool_id, spool)
        self.assertEqual(result.matched_kinds, ("tag_uid", "tray_uuid"))

    def test_two_trusted_identifiers_for_different_spools_are_a_conflict(self) -> None:
        result = resolve_feed_slot_spool(
            snapshot(tray_uuid="tray-1", tag_uid="tag-1"), namespace="bambu",
            identifiers=Identifiers([
                identifier(EntityId.new(), "tray_uuid", "tray-1"),
                identifier(EntityId.new(), "tag_uid", "tag-1"),
            ]),
        )
        self.assertEqual(result.state, SlotSpoolMatchState.CONFLICT)
        self.assertIsNone(result.spool_id)

    def test_unknown_identifiers_and_material_color_do_not_guess_a_spool(self) -> None:
        result = resolve_feed_slot_spool(
            snapshot(), namespace="bambu", identifiers=Identifiers([]),
        )
        self.assertEqual(result.state, SlotSpoolMatchState.UNKNOWN)
        self.assertIsNone(result.spool_id)

    def test_untrusted_repository_result_is_rejected(self) -> None:
        untrusted = identifier(EntityId.new(), "tray_uuid", "tray-1", verified=False)
        with self.assertRaisesRegex(ValueError, "slot_identity.repository_result_invalid"):
            resolve_feed_slot_spool(
                snapshot(tray_uuid="tray-1"), namespace="bambu",
                identifiers=Identifiers([untrusted]),
            )

