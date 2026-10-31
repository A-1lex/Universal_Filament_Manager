import unittest
from dataclasses import replace
from datetime import UTC, datetime

from ufm.domain.entities import FilamentTransaction, MaterialTransfer
from ufm.domain.enums import TransactionType
from ufm.domain.policies import validate_ledger_history
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def immutable() -> dict[str, object]:
    return {
        "id": EntityId.new(), "device_id": EntityId.new(),
        "created_at": UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC)),
    }


def entry(
    *, spool: EntityId, sequence: int, kind: TransactionType, delta: int,
    previous: int | None, command: str = "command",
) -> FilamentTransaction:
    return FilamentTransaction(
        **immutable(), spool_id=spool, sequence=sequence, transaction_type=kind,
        delta=Mass(delta), previous_effective=None if previous is None else Mass(previous),
        new_effective=Mass(delta if previous is None else previous + delta),
        command_key=command, command_item=0, source_type="manual", confidence_bp=10_000,
    )


class LedgerTests(unittest.TestCase):
    def test_known_zero_requires_explicit_opening_entry(self) -> None:
        opening = entry(
            spool=EntityId.new(), sequence=1, kind=TransactionType.INITIAL_STOCK,
            delta=0, previous=None,
        )
        self.assertEqual(opening.new_effective, Mass(0))

    def test_unknown_balance_cannot_be_debited(self) -> None:
        with self.assertRaises(ValueError):
            entry(
                spool=EntityId.new(), sequence=2, kind=TransactionType.MANUAL_USE,
                delta=-1, previous=None,
            )

    def test_negative_stock_is_preserved_by_exact_balance_equation(self) -> None:
        spool = EntityId.new()
        opening = entry(
            spool=spool, sequence=1, kind=TransactionType.INITIAL_STOCK,
            delta=50, previous=None,
        )
        debit = entry(
            spool=spool, sequence=2, kind=TransactionType.PRINT_CONSUMPTION,
            delta=-70, previous=50, command="use",
        )
        validate_ledger_history([opening, debit])
        self.assertEqual(debit.new_effective, Mass(-20))

    def test_direction_and_balance_mismatch_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            entry(
                spool=EntityId.new(), sequence=2,
                kind=TransactionType.PRINT_CONSUMPTION, delta=1, previous=10,
            )
        with self.assertRaises(ValueError):
            FilamentTransaction(
                **immutable(), spool_id=EntityId.new(), sequence=2,
                transaction_type=TransactionType.RETURN, delta=Mass(1),
                previous_effective=Mass(10), new_effective=Mass(12), command_key="c",
                command_item=0, source_type="manual", confidence_bp=10_000,
            )

    def test_replay_rejects_duplicate_command_items(self) -> None:
        spool = EntityId.new()
        opening = entry(
            spool=spool, sequence=1, kind=TransactionType.INITIAL_STOCK,
            delta=10, previous=None,
        )
        duplicate = entry(
            spool=spool, sequence=2, kind=TransactionType.RETURN,
            delta=1, previous=10,
        )
        with self.assertRaises(ValueError):
            validate_ledger_history([opening, duplicate])

    def test_transfer_requires_distinct_spools(self) -> None:
        spool = EntityId.new()
        with self.assertRaises(ValueError):
            MaterialTransfer(
                **immutable(), from_spool_id=spool, to_spool_id=spool, mass=Mass(1),
                command_key="transfer", reason="split",
            )

    def test_replay_rejects_discontinuous_estimate_even_when_effective_matches(self) -> None:
        spool = EntityId.new()
        opening = replace(entry(
            spool=spool, sequence=1, kind=TransactionType.INITIAL_STOCK,
            delta=100, previous=None,
        ), new_estimated=Mass(100))
        debit = replace(entry(
            spool=spool, sequence=2, kind=TransactionType.MANUAL_USE,
            delta=-10, previous=100, command="debit",
        ), previous_estimated=Mass(200), new_estimated=Mass(190))
        with self.assertRaisesRegex(ValueError, "ledger.history_estimate_invalid"):
            validate_ledger_history([opening, debit])
        validate_ledger_history([
            opening, replace(debit, previous_estimated=Mass(100), new_estimated=Mass(90)),
        ])
