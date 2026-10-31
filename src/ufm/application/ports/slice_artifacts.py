"""Persistent verified source artifacts; the store has no inventory authority."""

from pathlib import Path
from typing import Protocol

from ufm.application.dto.slice_facts import VerifiedSliceFacts


class StoredSliceArtifact(Protocol):
    @property
    def facts(self) -> VerifiedSliceFacts: ...

    @property
    def archive_path(self) -> Path: ...


class SliceArtifactStore(Protocol):
    def store_file(self, path: Path, *, expected_sha256: str, plate: int) -> StoredSliceArtifact: ...
    def load(self, *, expected_sha256: str, plate: int) -> StoredSliceArtifact: ...
