"""Secret references cross application boundaries; secret text never becomes config."""

from dataclasses import dataclass, field
from typing import Protocol


class SecretStoreUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("secrets.unavailable")


class SecretNotFound(LookupError):
    def __init__(self) -> None:
        super().__init__("secrets.not_found")


class InvalidCredentialReference(ValueError):
    def __init__(self) -> None:
        super().__init__("secrets.invalid_reference")


@dataclass(frozen=True, slots=True)
class SecretValue:
    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._value, str) or not 1 <= len(self._value) <= 16_384:
            raise ValueError("secrets.invalid_value")

    def reveal(self) -> str:
        """Only a credential-consuming adapter should call this explicitly."""
        return self._value


class SecretStore(Protocol):
    def get(self, credential_ref: str) -> SecretValue: ...

    def put(self, secret: SecretValue) -> str: ...

    def delete(self, credential_ref: str) -> None: ...

