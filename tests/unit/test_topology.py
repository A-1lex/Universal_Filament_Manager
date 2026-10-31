import unittest
from datetime import UTC, datetime, timedelta

from ufm.domain.entities import FeedSlot, MaterialFeedSystem, Printer, SpoolMount
from ufm.domain.enums import AssignmentSource, FeedSystemKind, MountState, SlotAssignment
from ufm.domain.policies import MountConflict, validate_mount_history
from ufm.domain.value_objects import EntityId, UtcDateTime


def timestamp(minutes: int = 0) -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC) + timedelta(minutes=minutes))


def identity() -> EntityId:
    return EntityId.new()


def mount(
    *, slot: EntityId, spool: EntityId, start: int, end: int | None = None,
    confidence: int = 10_000,
) -> SpoolMount:
    state = MountState.ACTIVE if end is None else MountState.CLOSED
    return SpoolMount(
        id=identity(), device_id=identity(), created_at=timestamp(), updated_at=timestamp(), revision=1,
        feed_slot_id=slot, spool_id=spool, state=state, mounted_at=timestamp(start),
        unmounted_at=None if end is None else timestamp(end),
        assignment_source=AssignmentSource.MANUAL, confidence_bp=confidence,
    )


class TopologyEntityTests(unittest.TestCase):
    def test_external_feed_topology_does_not_put_spool_on_printer(self) -> None:
        printer = Printer(id=identity(), device_id=identity(), created_at=timestamp(), updated_at=timestamp(), revision=1, name="P1S")
        system = MaterialFeedSystem(id=identity(), device_id=identity(), created_at=timestamp(), updated_at=timestamp(), revision=1, printer_id=printer.id, kind=FeedSystemKind.EXTERNAL, name="External")
        slot = FeedSlot(id=identity(), device_id=identity(), created_at=timestamp(), updated_at=timestamp(), revision=1, feed_system_id=system.id, slot_key="external", assignment_state=SlotAssignment.ACTIVE_SPOOL_UNKNOWN)
        self.assertEqual(slot.feed_system_id, system.id)
        self.assertFalse(hasattr(printer, "active_spool_id"))

    def test_active_mount_shape_and_confidence_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            mount(slot=identity(), spool=identity(), start=2, end=1)
        with self.assertRaises(ValueError):
            mount(slot=identity(), spool=identity(), start=0, confidence=10_001)

    def test_same_spool_cannot_be_active_on_two_slots(self) -> None:
        spool = identity()
        with self.assertRaises(MountConflict):
            validate_mount_history([mount(slot=identity(), spool=spool, start=0), mount(slot=identity(), spool=spool, start=1)])

    def test_same_slot_cannot_hold_two_active_spools(self) -> None:
        slot = identity()
        with self.assertRaises(MountConflict):
            validate_mount_history([mount(slot=slot, spool=identity(), start=0), mount(slot=slot, spool=identity(), start=1)])

    def test_adjacent_closed_history_and_distinct_resources_are_allowed(self) -> None:
        slot, spool = identity(), identity()
        validate_mount_history([mount(slot=slot, spool=spool, start=0, end=5), mount(slot=slot, spool=spool, start=5, end=10), mount(slot=identity(), spool=identity(), start=0)])
