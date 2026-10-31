import unittest

from ufm.domain.enums import (
    FinalizationState,
    InventoryHealth,
    MountState,
    PrintStatus,
    ReceiptState,
    ReconciliationState,
    ReservationState,
    SlotAssignment,
)
from ufm.domain.policies import InvalidTransition, validate_transition


class TransitionTests(unittest.TestCase):
    def test_same_state_observation_is_idempotent(self) -> None:
        self.assertIs(validate_transition(PrintStatus.RUNNING, PrintStatus.RUNNING), PrintStatus.RUNNING)

    def test_skipped_print_states_and_pause_resume_are_supported(self) -> None:
        self.assertIs(validate_transition(PrintStatus.DETECTED, PrintStatus.COMPLETED), PrintStatus.COMPLETED)
        self.assertIs(validate_transition(PrintStatus.PAUSED, PrintStatus.RUNNING), PrintStatus.RUNNING)

    def test_terminal_print_and_reservation_states_cannot_reactivate(self) -> None:
        for current, target in ((PrintStatus.COMPLETED, PrintStatus.RUNNING), (ReservationState.RELEASED, ReservationState.ACTIVE)):
            with self.subTest(current=current), self.assertRaises(InvalidTransition):
                validate_transition(current, target)

    def test_closed_mount_cannot_reopen(self) -> None:
        self.assertIs(validate_transition(MountState.ACTIVE, MountState.CLOSED), MountState.CLOSED)
        with self.assertRaises(InvalidTransition):
            validate_transition(MountState.CLOSED, MountState.ACTIVE)

    def test_equal_str_values_do_not_collide_between_enum_types(self) -> None:
        self.assertIs(
            validate_transition(ReservationState.PENDING, ReservationState.ACTIVE),
            ReservationState.ACTIVE,
        )
        self.assertIs(
            validate_transition(ReservationState.ACTIVE, ReservationState.EXPIRED),
            ReservationState.EXPIRED,
        )

    def test_unknown_enum_values_and_cross_enum_transitions_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            SlotAssignment("UNKNOWN")
        with self.assertRaises(TypeError):
            validate_transition(PrintStatus.RUNNING, ReservationState.ACTIVE)  # type: ignore[arg-type]

    def test_accounting_and_reconciliation_workflows_are_one_way(self) -> None:
        allowed = (
            (FinalizationState.NOT_STARTED, FinalizationState.NEEDS_RECONCILIATION),
            (FinalizationState.NEEDS_RECONCILIATION, FinalizationState.IN_PROGRESS),
            (FinalizationState.IN_PROGRESS, FinalizationState.FINALIZED),
            (ReceiptState.PENDING, ReceiptState.PROCESSED),
            (ReconciliationState.OPEN, ReconciliationState.RESOLVED),
            (InventoryHealth.CONSISTENT, InventoryHealth.QUARANTINED),
            (InventoryHealth.QUARANTINED, InventoryHealth.CONSISTENT),
        )
        for current, target in allowed:
            with self.subTest(current=current):
                self.assertIs(validate_transition(current, target), target)

        for current, target in (
            (FinalizationState.FINALIZED, FinalizationState.IN_PROGRESS),
            (ReceiptState.PROCESSED, ReceiptState.PENDING),
            (ReconciliationState.RESOLVED, ReconciliationState.OPEN),
        ):
            with self.subTest(current=current), self.assertRaises(InvalidTransition):
                validate_transition(current, target)
