"""Read-only file/calculation dependencies, independent from Node or ZIP adapters."""

from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from ufm.application.dto.slice_facts import VerifiedSliceFacts
from ufm.application.dto.worker_protocol import ProposalMessage, WorkerScope


class SliceFileReader(Protocol):
    def __call__(self, path: Path, *, plate: int, expected_sha256: str) -> VerifiedSliceFacts: ...


class SliceCalculator(Protocol):
    async def calculate(
        self, facts: VerifiedSliceFacts, *, scope: WorkerScope, occurrence_key: str,
        evidence_id: UUID, observed_at: datetime, sequence: int, completed_layer: int | None = None,
    ) -> ProposalMessage: ...
