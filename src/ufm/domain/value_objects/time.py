"""UTC timestamp boundary value."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True, order=True)
class UtcDateTime:
    value: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.value, datetime) or self.value.tzinfo is None:
            raise ValueError("time.timezone_required")
        object.__setattr__(self, "value", self.value.astimezone(UTC))

    @classmethod
    def now(cls) -> UtcDateTime:
        return cls(datetime.now(UTC))

    @classmethod
    def parse(cls, value: str) -> UtcDateTime:
        if type(value) is not str or len(value) != 27 or not value.endswith("Z"):
            raise ValueError("time.utc_format_required")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            raise ValueError("time.invalid") from None
        result = cls(parsed)
        if result.isoformat() != value:
            raise ValueError("time.invalid")
        return result

    def isoformat(self) -> str:
        return self.value.isoformat(timespec="microseconds").replace("+00:00", "Z")
