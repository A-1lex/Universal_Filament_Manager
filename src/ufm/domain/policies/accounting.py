"""Pure guards and calculations at the accounting boundary."""

from ufm.domain.entities import ConsumptionDecision, MaterialUsageSegment
from ufm.domain.enums import SlotAssignment
from ufm.domain.value_objects import Mass


def reservation_settlement(reserved: Mass, actual: Mass) -> tuple[Mass, Mass]:
    if reserved.milligrams <= 0 or actual.milligrams < 0:
        raise ValueError("reservation.settlement_input_invalid")
    allocated = Mass(min(reserved.milligrams, actual.milligrams))
    released = reserved - allocated
    return allocated, released


def validate_decision_scope(
    segment: MaterialUsageSegment, decision: ConsumptionDecision
) -> None:
    if segment.id != decision.material_usage_segment_id:
        raise ValueError("decision.segment_mismatch")
    if segment.assignment_state is not SlotAssignment.ASSIGNED or segment.spool_id is None:
        raise ValueError("decision.assignment_unresolved")
    if segment.ended_at is None:
        raise ValueError("decision.segment_open")
