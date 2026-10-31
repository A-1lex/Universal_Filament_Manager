import unittest
from datetime import UTC, datetime

from ufm.application.dto import FeedSlotSnapshot, FeedSystemSnapshot, Observed
from ufm.domain.enums import Availability, FeedSystemKind
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC))


def observed[ValueT](value: ValueT) -> Observed[ValueT]:
    return Observed(Availability.KNOWN, now(), now(), value)


def unknown[ValueT]() -> Observed[ValueT]:
    return Observed(Availability.UNKNOWN, now(), now())


def slot(key: str = "A1") -> FeedSlotSnapshot:
    return FeedSlotSnapshot(
        slot_key=key,
        occupancy=observed(True),
        tray_uuid=observed("tray-1"),
        tag_uid=unknown(),
        assigned_spool_id=observed(EntityId.new()),
        remaining_mass=observed(Mass.from_grams("420")),
    )


class FeedSnapshotContractTests(unittest.TestCase):
    def test_tray_and_tag_observations_remain_independent(self) -> None:
        snapshot = slot()
        self.assertEqual(snapshot.tray_uuid.value, "tray-1")
        self.assertIs(snapshot.tag_uid.availability, Availability.UNKNOWN)

    def test_remaining_percent_is_bounded_integer(self) -> None:
        with self.assertRaisesRegex(ValueError, "remaining_percent_invalid"):
            FeedSlotSnapshot(
                slot_key="A1",
                occupancy=observed(True),
                tray_uuid=observed("tray-1"),
                tag_uid=unknown(),
                assigned_spool_id=observed(EntityId.new()),
                remaining_mass=observed(Mass.from_grams("420")),
                remaining_percent=observed(101),
            )

    def test_system_rejects_duplicate_slot_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate_slot"):
            FeedSystemSnapshot(
                provider_system_key="ams-1",
                kind=FeedSystemKind.AMS,
                slots=(slot(), slot()),
                observed_at=now(),
                received_at=now(),
                complete=True,
            )

    def test_completeness_is_explicit_and_strictly_boolean(self) -> None:
        snapshot = FeedSystemSnapshot(
            provider_system_key="external",
            kind=FeedSystemKind.EXTERNAL,
            slots=(slot("external-0"),),
            observed_at=now(),
            received_at=now(),
            complete=False,
        )
        self.assertFalse(snapshot.complete)
        with self.assertRaises(TypeError):
            FeedSystemSnapshot(
                provider_system_key="external",
                kind=FeedSystemKind.EXTERNAL,
                slots=(),
                observed_at=now(),
                received_at=now(),
                complete=1,  # type: ignore[arg-type]
            )
