"""Exact physical mass represented as integer milligrams."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_ABS_MILLIGRAMS = 9_000_000_000_000_000


class MassPrecisionError(ValueError):
    """The supplied quantity cannot be represented as whole milligrams."""


@dataclass(frozen=True, slots=True, order=True)
class Mass:
    """A known mass; use ``None`` when the quantity is unknown."""

    milligrams: int

    def __post_init__(self) -> None:
        if type(self.milligrams) is not int:
            raise TypeError("mass.milligrams_invalid")
        if abs(self.milligrams) > MAX_ABS_MILLIGRAMS:
            raise ValueError("mass.out_of_range")

    @classmethod
    def from_grams(cls, grams: Decimal | int | str) -> Mass:
        if isinstance(grams, float) or isinstance(grams, bool):
            raise TypeError("mass.grams_invalid")
        try:
            decimal_grams = Decimal(grams)
        except (InvalidOperation, ValueError):
            raise ValueError("mass.grams_invalid") from None
        if not decimal_grams.is_finite():
            raise ValueError("mass.grams_invalid")
        milligrams = decimal_grams * 1000
        if milligrams != milligrams.to_integral_value():
            raise MassPrecisionError("mass.fractional_milligram")
        return cls(int(milligrams))

    @property
    def grams(self) -> Decimal:
        return Decimal(self.milligrams) / 1000

    def __add__(self, other: Mass) -> Mass:
        if not isinstance(other, Mass):
            return NotImplemented
        return Mass(self.milligrams + other.milligrams)

    def __sub__(self, other: Mass) -> Mass:
        if not isinstance(other, Mass):
            return NotImplemented
        return Mass(self.milligrams - other.milligrams)
