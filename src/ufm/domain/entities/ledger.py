"""Append-only exact inventory ledger records."""

from dataclasses import dataclass

from ufm.domain.entities.base import ImmutableRecord
from ufm.domain.enums import TransactionType
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass
from ufm.domain.value_objects.json_object import json_object

_NEGATIVE_TYPES = frozenset({
    TransactionType.PRINT_CONSUMPTION, TransactionType.PURGE, TransactionType.LOAD,
    TransactionType.UNLOAD, TransactionType.WASTE, TransactionType.FAILED_PRINT,
    TransactionType.MANUAL_USE, TransactionType.TRANSFER_OUT,
})
_POSITIVE_TYPES = frozenset({TransactionType.TRANSFER_IN, TransactionType.RETURN})


@dataclass(frozen=True, slots=True, kw_only=True)
class FilamentTransaction(ImmutableRecord):
    spool_id: EntityId
    sequence: int
    transaction_type: TransactionType
    delta: Mass
    previous_effective: Mass | None
    new_effective: Mass
    command_key: str
    command_item: int
    source_type: str
    confidence_bp: int
    previous_estimated: Mass | None = None
    new_estimated: Mass | None = None
    estimate_policy_version: str = "safe-v1"
    print_job_id: EntityId | None = None
    decision_id: EntityId | None = None
    reservation_id: EntityId | None = None
    inventory_reconciliation_id: EntityId | None = None
    compensates_transaction_id: EntityId | None = None
    transfer_id: EntityId | None = None
    source_receipt_id: EntityId | None = None
    description: str | None = None
    metadata_json: str = "{}"
    unit_cost: ExactDecimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        json_object(self.metadata_json)
        if self.unit_cost is not None and (
            not isinstance(self.unit_cost, ExactDecimal) or self.unit_cost.value < 0
        ):
            raise ValueError("ledger.unit_cost_invalid")
        if (self.unit_cost is None) != (self.currency is None):
            raise ValueError("ledger.money_shape_invalid")
        if self.currency is not None and (
            type(self.currency) is not str or len(self.currency) != 3
            or not self.currency.isascii() or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValueError("ledger.currency_invalid")
        if self.description is not None and (type(self.description) is not str or len(self.description) > 500):
            raise ValueError("ledger.description_invalid")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("ledger.sequence_invalid")
        if type(self.command_item) is not int or self.command_item < 0:
            raise ValueError("ledger.command_item_invalid")
        if not self.command_key or not self.source_type or not self.estimate_policy_version:
            raise ValueError("ledger.text_invalid")
        if type(self.confidence_bp) is not int or not 0 <= self.confidence_bp <= 10_000:
            raise ValueError("ledger.confidence_invalid")
        if self.sequence == 1:
            if (
                self.transaction_type is not TransactionType.INITIAL_STOCK
                or self.previous_effective is not None
                or self.delta.milligrams < 0
                or self.new_effective != self.delta
            ):
                raise ValueError("ledger.opening_invalid")
        elif (self.transaction_type is TransactionType.INITIAL_STOCK
              or self.previous_effective is None
              or self.new_effective != self.previous_effective + self.delta):
            raise ValueError("ledger.balance_invalid")
        if self.transaction_type in _NEGATIVE_TYPES and self.delta.milligrams >= 0:
            raise ValueError("ledger.delta_direction_invalid")
        if self.transaction_type in _POSITIVE_TYPES and self.delta.milligrams <= 0:
            raise ValueError("ledger.delta_direction_invalid")
        if self.transaction_type is TransactionType.INVENTORY_ADJUSTMENT and self.delta.milligrams == 0:
            raise ValueError("ledger.zero_adjustment_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterialTransfer(ImmutableRecord):
    from_spool_id: EntityId
    to_spool_id: EntityId
    mass: Mass
    command_key: str
    reason: str

    def __post_init__(self) -> None:
        if self.from_spool_id == self.to_spool_id:
            raise ValueError("transfer.same_spool")
        if self.mass.milligrams <= 0:
            raise ValueError("transfer.mass_invalid")
        if not self.command_key or not self.reason:
            raise ValueError("transfer.text_invalid")
