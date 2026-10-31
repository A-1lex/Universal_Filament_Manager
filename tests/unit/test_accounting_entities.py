import unittest
from datetime import UTC, datetime, timedelta

from ufm.domain.entities import (
    ConsumptionDecision,
    ConsumptionEvidence,
    ExternalEventReceipt,
    FinalizationRecord,
    InventoryEvidence,
    MaterialUsageSegment,
    Reservation,
)
from ufm.domain.enums import (
    EvidenceMode,
    EvidenceSource,
    QuantityKind,
    ReceiptState,
    ReservationState,
    SlotAssignment,
)
from ufm.domain.policies import reservation_settlement, validate_decision_scope
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def at(minutes: int = 0) -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC) + timedelta(minutes=minutes))


def mutable() -> dict[str, object]:
    return {
        "id": EntityId.new(), "device_id": EntityId.new(), "created_at": at(),
        "updated_at": at(), "revision": 1,
    }


def immutable() -> dict[str, object]:
    return {"id": EntityId.new(), "device_id": EntityId.new(), "created_at": at()}


class ReservationTests(unittest.TestCase):
    def test_reservation_claim_does_not_equal_actual_debit(self) -> None:
        allocated, released = reservation_settlement(Mass.from_grams(420), Mass.from_grams(300))
        self.assertEqual(allocated, Mass.from_grams(300))
        self.assertEqual(released, Mass.from_grams(120))

    def test_actual_overrun_is_not_inflated_or_lost_in_allocation(self) -> None:
        actual = Mass.from_grams(500)
        allocated, released = reservation_settlement(Mass.from_grams(420), actual)
        self.assertEqual(allocated, Mass.from_grams(420))
        self.assertEqual(released, Mass(0))
        self.assertEqual(actual - allocated, Mass.from_grams(80))

    def test_consumed_reservation_requires_finalization(self) -> None:
        with self.assertRaises(ValueError):
            Reservation(**mutable(), spool_id=EntityId.new(), print_job_material_id=EntityId.new(), reserved=Mass(1), state=ReservationState.CONSUMED)


class EvidenceTests(unittest.TestCase):
    def test_consumption_and_absolute_remaining_are_separate(self) -> None:
        common = dict(**immutable(), print_job_material_id=EntityId.new(), source=EvidenceSource.SCALE, mode=EvidenceMode.DELTA, confidence_bp=9900, captured_at=at(), received_at=at(), scope_key="job-material")
        evidence = ConsumptionEvidence(**common, quantity_kind=QuantityKind.CONSUMED_MASS, mass=Mass.from_grams(10))
        self.assertEqual(evidence.mass, Mass.from_grams(10))
        with self.assertRaises(ValueError):
            ConsumptionEvidence(**common, quantity_kind=QuantityKind.REMAINING_MASS, mass=Mass.from_grams(10))

    def test_inventory_net_must_match_gross_minus_tare(self) -> None:
        with self.assertRaises(ValueError):
            InventoryEvidence(**immutable(), spool_id=EntityId.new(), source=EvidenceSource.SCALE, captured_at=at(), received_at=at(), gross=Mass(100), tare=Mass(40), net=Mass(70))


class ReceiptAndDecisionTests(unittest.TestCase):
    def test_processed_receipt_requires_processed_time(self) -> None:
        values = dict(**mutable(), provider_instance_id=EntityId.new(), printer_id=EntityId.new(), source_epoch="boot", event_key="event", event_type="completed", payload_hash="sha256", received_at=at())
        with self.assertRaises(ValueError):
            ExternalEventReceipt(**values, state=ReceiptState.PROCESSED)
        receipt = ExternalEventReceipt(**values, state=ReceiptState.PENDING)
        self.assertIsNone(receipt.processed_at)

    def test_finalization_interval_and_decision_scope_are_guarded(self) -> None:
        with self.assertRaises(ValueError):
            FinalizationRecord(**immutable(), print_job_id=EntityId.new(), idempotency_key="command", request_hash="request", started_at=at(2), completed_at=at(1), result_hash="result")

        material_id = EntityId.new()
        segment = MaterialUsageSegment(**mutable(), print_job_material_id=material_id, tool_index=0, assignment_state=SlotAssignment.ACTIVE_SPOOL_UNKNOWN, started_at=at(), ended_at=at(1), source="manual", confidence_bp=0)
        decision = ConsumptionDecision(**immutable(), finalization_record_id=EntityId.new(), material_usage_segment_id=segment.id, selected_mass=Mass(0), confidence_bp=10_000, strategy="manual", policy_version="safe-v1", reason_code="confirmed_zero", finalized_at=at(1))
        with self.assertRaises(ValueError):
            validate_decision_scope(segment, decision)
