"""Backup creation, verification and restore port."""

from typing import Protocol

from ufm.application.dto import (
    BackupDestination,
    BackupManifest,
    BackupSource,
    RestoreResult,
    RestoreTarget,
    VerificationResult,
)


class BackupInvalid(ValueError):
    code = "backup.invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


class BackupProvider(Protocol):
    def create(self, destination: BackupDestination) -> BackupManifest: ...

    def verify(self, backup: BackupSource) -> VerificationResult: ...

    def restore(self, backup: BackupSource, target: RestoreTarget) -> RestoreResult: ...
