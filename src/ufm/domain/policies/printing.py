"""Cross-entity print identity and material-segment invariants."""

from collections.abc import Iterable

from ufm.domain.entities import JobIdentityAlias, MaterialUsageSegment
from ufm.domain.value_objects import EntityId


class JobIdentityConflict(ValueError):
    def __init__(self) -> None:
        super().__init__("print_job.identity_conflict")


class SegmentConflict(ValueError):
    def __init__(self) -> None:
        super().__init__("usage_segment.interval_conflict")


def resolve_job_identity(
    aliases: Iterable[JobIdentityAlias], incoming: JobIdentityAlias
) -> EntityId | None:
    matches = {
        alias.print_job_id
        for alias in aliases
        if alias.occurrence_scope == incoming.occurrence_scope
    }
    if len(matches) > 1 or (matches and incoming.print_job_id not in matches):
        raise JobIdentityConflict()
    return next(iter(matches), None)


def validate_segment_history(segments: Iterable[MaterialUsageSegment]) -> None:
    history = tuple(segments)
    for index, left in enumerate(history):
        for right in history[index + 1:]:
            if left.print_job_material_id != right.print_job_material_id:
                continue
            left_before_right = left.ended_at is not None and left.ended_at <= right.started_at
            right_before_left = right.ended_at is not None and right.ended_at <= left.started_at
            if not left_before_right and not right_before_left:
                raise SegmentConflict()
