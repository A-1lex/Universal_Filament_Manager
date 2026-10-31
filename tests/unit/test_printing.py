import unittest
from datetime import UTC, datetime, timedelta

from ufm.domain.entities import (
    JobIdentityAlias,
    MaterialUsageSegment,
    PrintJob,
    PrintJobMaterial,
)
from ufm.domain.enums import FinalizationState, PrintStatus, SlotAssignment
from ufm.domain.policies import (
    JobIdentityConflict,
    SegmentConflict,
    resolve_job_identity,
    validate_segment_history,
)
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def at(minutes: int = 0) -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC) + timedelta(minutes=minutes))


def metadata() -> dict[str, object]:
    return {"id": EntityId.new(), "device_id": EntityId.new(), "created_at": at(), "updated_at": at(), "revision": 1}


def alias(job_id: EntityId, occurrence: str, *, provider: EntityId, printer: EntityId) -> JobIdentityAlias:
    return JobIdentityAlias(id=EntityId.new(), device_id=EntityId.new(), created_at=at(), print_job_id=job_id, provider_instance_id=provider, printer_id=printer, source_type="printer", source_epoch="boot-1", occurrence_key=occurrence, external_job_id="reused", file_hash="same")


def segment(material_id: EntityId, start: int, end: int | None, spool: EntityId) -> MaterialUsageSegment:
    return MaterialUsageSegment(**metadata(), print_job_material_id=material_id, tool_index=0, assignment_state=SlotAssignment.ASSIGNED, started_at=at(start), ended_at=None if end is None else at(end), source="manual", confidence_bp=10_000, feed_slot_id=EntityId.new(), spool_mount_id=EntityId.new(), spool_id=spool)


class PrintingTests(unittest.TestCase):
    def test_job_identity_is_occurrence_scoped_not_filename_scoped(self) -> None:
        provider, printer = EntityId.new(), EntityId.new()
        first_job, second_job = EntityId.new(), EntityId.new()
        first = alias(first_job, "run-1", provider=provider, printer=printer)
        replay = alias(first_job, "run-1", provider=provider, printer=printer)
        reprint = alias(second_job, "run-2", provider=provider, printer=printer)
        self.assertEqual(resolve_job_identity([first], replay), first_job)
        self.assertIsNone(resolve_job_identity([first], reprint))

    def test_same_occurrence_cannot_be_attached_to_another_job(self) -> None:
        provider, printer = EntityId.new(), EntityId.new()
        existing = alias(EntityId.new(), "run", provider=provider, printer=printer)
        conflicting = alias(EntityId.new(), "run", provider=provider, printer=printer)
        with self.assertRaises(JobIdentityConflict):
            resolve_job_identity([existing], conflicting)

    def test_material_channel_has_no_physical_spool(self) -> None:
        material = PrintJobMaterial(**metadata(), print_job_id=EntityId.new(), channel_key="tool-0", tool_index=0, estimated_mass=Mass.from_grams(25))
        self.assertFalse(hasattr(material, "spool_id"))

    def test_logical_material_index_is_distinct_and_bounded(self) -> None:
        material = PrintJobMaterial(
            **metadata(), print_job_id=EntityId.new(), channel_key="channel-a",
            logical_material_index=5, tool_index=1, extruder_index=0,
        )
        self.assertEqual(material.logical_material_index, 5)
        self.assertEqual(material.tool_index, 1)
        self.assertEqual(material.extruder_index, 0)
        with self.assertRaisesRegex(ValueError, "logical_material_index_invalid"):
            PrintJobMaterial(
                **metadata(), print_job_id=EntityId.new(), channel_key="channel-b",
                logical_material_index=256, tool_index=1,
            )

    def test_spool_swap_creates_adjacent_non_overlapping_segments(self) -> None:
        material = EntityId.new()
        first = segment(material, 0, 62, EntityId.new())
        second = segment(material, 62, 100, EntityId.new())
        validate_segment_history([first, second])
        self.assertNotEqual(first.spool_id, second.spool_id)

    def test_overlapping_or_two_open_segments_for_channel_are_rejected(self) -> None:
        material = EntityId.new()
        with self.assertRaises(SegmentConflict):
            validate_segment_history([segment(material, 0, None, EntityId.new()), segment(material, 1, None, EntityId.new())])

    def test_print_progress_and_assignment_shape_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            PrintJob(**metadata(), printer_id=EntityId.new(), source_type="printer", status=PrintStatus.RUNNING, finalization_state=FinalizationState.NOT_STARTED, detected_at=at(), progress_bp=10_001)
        with self.assertRaises(ValueError):
            MaterialUsageSegment(**metadata(), print_job_material_id=EntityId.new(), tool_index=0, assignment_state=SlotAssignment.ASSIGNED, started_at=at(), source="manual", confidence_bp=10_000)
