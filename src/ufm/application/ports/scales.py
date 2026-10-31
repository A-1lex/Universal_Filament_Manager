"""Scale provider port without inventory mutation authority."""

from typing import Protocol

from ufm.application.dto import ProviderHealth, TareResult, WeightReading


class ScaleProvider(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def health(self) -> ProviderHealth: ...

    async def read(self) -> WeightReading: ...

    async def tare(self) -> TareResult: ...
