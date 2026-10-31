"""Canonical internal UUID identity."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True, order=True)
class EntityId:
    value: UUID

    @classmethod
    def new(cls) -> EntityId:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str) -> EntityId:
        if type(value) is not str:
            raise TypeError("identity.invalid")
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("identity.invalid") from None
        if str(parsed) != value:
            raise ValueError("identity.not_canonical")
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)
