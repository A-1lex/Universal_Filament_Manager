"""Optional future sync port; no adapter is composed by default."""

from typing import Protocol

from ufm.application.dto import SyncBatch, SyncResult


class SyncProvider(Protocol):
    async def exchange(self, request: SyncBatch) -> SyncResult: ...
