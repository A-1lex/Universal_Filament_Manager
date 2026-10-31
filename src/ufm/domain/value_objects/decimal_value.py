"""Finite canonical decimal values without a binary-float path."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True, order=True)
class ExactDecimal:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("decimal.invalid")
        if self.value == 0:
            object.__setattr__(self, "value", Decimal(0))

    @classmethod
    def parse(cls, value: Decimal | int | str) -> ExactDecimal:
        if isinstance(value, (float, bool)):
            raise TypeError("decimal.float_forbidden")
        try:
            return cls(Decimal(value))
        except (InvalidOperation, ValueError):
            raise ValueError("decimal.invalid") from None

    def canonical(self) -> str:
        rendered = format(self.value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered or "0"
