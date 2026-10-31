"""Cross-entity physical topology invariants."""

from collections.abc import Iterable

from ufm.domain.entities import SpoolMount


class MountConflict(ValueError):
    def __init__(self) -> None:
        super().__init__("spool_mount.interval_conflict")


def validate_mount_history(mounts: Iterable[SpoolMount]) -> None:
    history = tuple(mounts)
    for index, left in enumerate(history):
        left_end = left.unmounted_at
        for right in history[index + 1:]:
            same_physical_resource = (
                left.spool_id == right.spool_id or left.feed_slot_id == right.feed_slot_id
            )
            if not same_physical_resource:
                continue
            right_end = right.unmounted_at
            left_before_right = left_end is not None and left_end <= right.mounted_at
            right_before_left = right_end is not None and right_end <= left.mounted_at
            if not left_before_right and not right_before_left:
                raise MountConflict()
