"""Normalized notification and backup boundary models."""

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ufm.domain.enums import Severity
from ufm.domain.value_objects import EntityId, UtcDateTime


def _text(value: str, code: str, *, limit: int = 2_000) -> None:
    if type(value) is not str or not value or len(value) > limit:
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class Notification:
    kind: str
    title: str
    body: str
    severity: Severity
    subject_id: EntityId | None = None

    def __post_init__(self) -> None:
        _text(self.kind, "notification.kind_invalid", limit=200)
        _text(self.title, "notification.title_invalid", limit=500)
        _text(self.body, "notification.body_invalid", limit=10_000)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    accepted: bool
    reason_code: str
    provider_message_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool:
            raise TypeError("delivery_result.accepted_invalid")
        _text(self.reason_code, "delivery_result.reason_invalid", limit=500)
        if self.provider_message_id is not None:
            _text(self.provider_message_id, "delivery_result.message_id_invalid", limit=500)


@dataclass(frozen=True, slots=True)
class BackupDestination:
    location_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.location_ref, "backup_destination.reference_invalid", limit=2_000)


@dataclass(frozen=True, slots=True)
class BackupSource:
    location_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.location_ref, "backup_source.reference_invalid", limit=2_000)


@dataclass(frozen=True, slots=True)
class RestoreTarget:
    location_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.location_ref, "restore_target.reference_invalid", limit=2_000)


@dataclass(frozen=True, slots=True)
class BackupFile:
    relative_path: str
    sha256: str
    length: int

    def __post_init__(self) -> None:
        _text(self.relative_path, "backup_file.path_invalid", limit=1_000)
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts or "\\" in self.relative_path:
            raise ValueError("backup_file.path_invalid")
        if len(self.sha256) != 64 or any(character not in "0123456789abcdef" for character in self.sha256):
            raise ValueError("backup_file.checksum_invalid")
        if type(self.length) is not int or self.length < 0:
            raise ValueError("backup_file.length_invalid")


@dataclass(frozen=True, slots=True)
class BackupManifest:
    format_version: int
    schema_version: int
    app_version: str
    device_id: EntityId
    snapshot_at: UtcDateTime
    files: tuple[BackupFile, ...]

    def __post_init__(self) -> None:
        if type(self.format_version) is not int or self.format_version < 1:
            raise ValueError("backup_manifest.format_version_invalid")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("backup_manifest.schema_version_invalid")
        _text(self.app_version, "backup_manifest.app_version_invalid", limit=200)
        if type(self.files) is not tuple or len(self.files) > 100_000:
            raise ValueError("backup_manifest.files_invalid")
        paths = [file.relative_path for file in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("backup_manifest.duplicate_path")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    valid: bool
    reason_code: str
    manifest: BackupManifest | None = None

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise TypeError("backup_verification.valid_invalid")
        _text(self.reason_code, "backup_verification.reason_invalid", limit=500)
        if self.valid and self.manifest is None:
            raise ValueError("backup_verification.manifest_required")


@dataclass(frozen=True, slots=True)
class RestoreResult:
    restored: bool
    reason_code: str
    schema_version: int | None = None

    def __post_init__(self) -> None:
        if type(self.restored) is not bool:
            raise TypeError("restore_result.restored_invalid")
        _text(self.reason_code, "restore_result.reason_invalid", limit=500)
        if self.schema_version is not None and (
            type(self.schema_version) is not int or self.schema_version < 1
        ):
            raise ValueError("restore_result.schema_version_invalid")
