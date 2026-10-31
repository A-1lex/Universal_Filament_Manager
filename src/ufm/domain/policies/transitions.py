"""Fail-closed transition validation for persisted lifecycle states."""

from enum import StrEnum

from ufm.domain.enums import (
    FinalizationState,
    InventoryHealth,
    MountState,
    PrintStatus,
    ReceiptState,
    ReconciliationState,
    ReservationState,
    SpoolLifecycle,
)


class InvalidTransition(ValueError):
    def __init__(self) -> None:
        super().__init__("domain.invalid_transition")


_ALLOWED: dict[tuple[type[StrEnum], StrEnum], frozenset[StrEnum]] = {
    (PrintStatus, PrintStatus.DETECTED): frozenset(PrintStatus) - {PrintStatus.DETECTED},
    (PrintStatus, PrintStatus.PREPARING): frozenset(PrintStatus) - {PrintStatus.DETECTED, PrintStatus.PREPARING},
    (PrintStatus, PrintStatus.RUNNING): frozenset({PrintStatus.PAUSED, PrintStatus.COMPLETING, PrintStatus.COMPLETED, PrintStatus.FAILED, PrintStatus.CANCELLED}),
    (PrintStatus, PrintStatus.PAUSED): frozenset({PrintStatus.RUNNING, PrintStatus.COMPLETING, PrintStatus.COMPLETED, PrintStatus.FAILED, PrintStatus.CANCELLED}),
    (PrintStatus, PrintStatus.COMPLETING): frozenset({PrintStatus.COMPLETED, PrintStatus.FAILED, PrintStatus.CANCELLED}),
    (ReservationState, ReservationState.PENDING): frozenset({ReservationState.ACTIVE, ReservationState.RELEASED, ReservationState.EXPIRED}),
    (ReservationState, ReservationState.ACTIVE): frozenset({ReservationState.CONSUMED, ReservationState.RELEASED, ReservationState.EXPIRED}),
    (MountState, MountState.ACTIVE): frozenset({MountState.CLOSED}),
    (SpoolLifecycle, SpoolLifecycle.NEW): frozenset({SpoolLifecycle.OPEN, SpoolLifecycle.ARCHIVED}),
    (SpoolLifecycle, SpoolLifecycle.OPEN): frozenset({SpoolLifecycle.ARCHIVED}),
    (FinalizationState, FinalizationState.NOT_STARTED): frozenset({
        FinalizationState.IN_PROGRESS,
        FinalizationState.NEEDS_RECONCILIATION,
    }),
    (FinalizationState, FinalizationState.NEEDS_RECONCILIATION): frozenset({FinalizationState.IN_PROGRESS}),
    (FinalizationState, FinalizationState.IN_PROGRESS): frozenset({FinalizationState.FINALIZED}),
    (ReceiptState, ReceiptState.PENDING): frozenset({ReceiptState.PROCESSED, ReceiptState.REJECTED}),
    (ReconciliationState, ReconciliationState.OPEN): frozenset({
        ReconciliationState.IN_REVIEW,
        ReconciliationState.RESOLVED,
    }),
    (ReconciliationState, ReconciliationState.IN_REVIEW): frozenset({
        ReconciliationState.RESOLVED,
        ReconciliationState.DISMISSED,
    }),
    (InventoryHealth, InventoryHealth.CONSISTENT): frozenset({InventoryHealth.QUARANTINED}),
    (InventoryHealth, InventoryHealth.QUARANTINED): frozenset({InventoryHealth.CONSISTENT}),
}


def validate_transition[StateT: StrEnum](current: StateT, target: StateT) -> StateT:
    if type(current) is not type(target):
        raise TypeError("domain.state_type_mismatch")
    if current == target:
        return current
    if target not in _ALLOWED.get((type(current), current), frozenset()):
        raise InvalidTransition()
    return target
