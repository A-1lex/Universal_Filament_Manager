"""Printer monitoring and optional control ports."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from ufm.application.dto import (
    CurrentJobObservation,
    PrinterCapabilities,
    PrinterEvent,
    PrinterStatusSnapshot,
    ProviderHealth,
)
from ufm.domain.value_objects import EntityId


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ProviderUnavailable(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider.unavailable", retryable=True)


class AuthenticationFailed(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider.authentication_failed", retryable=False)


class TLSVerificationFailed(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider.tls_verification_failed", retryable=False)


class UnsupportedCapability(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider.unsupported_capability", retryable=False)


class InvalidObservation(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider.invalid_observation", retryable=False)


@dataclass(frozen=True, slots=True)
class CommandResult:
    accepted: bool
    reason_code: str


class PrinterProvider(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health(self) -> ProviderHealth: ...
    async def get_capabilities(self) -> PrinterCapabilities: ...
    async def get_status(self) -> PrinterStatusSnapshot: ...
    async def get_current_job(self) -> CurrentJobObservation: ...
    def subscribe_events(self) -> AsyncIterator[PrinterEvent]: ...


class PrinterControl(Protocol):
    async def pause(self, job_id: EntityId) -> CommandResult: ...
    async def resume(self, job_id: EntityId) -> CommandResult: ...
    async def cancel(self, job_id: EntityId) -> CommandResult: ...
