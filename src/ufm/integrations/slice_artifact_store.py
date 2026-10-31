"""Immutable local verified 3MF artifacts; cache contents are always revalidated."""

from __future__ import annotations

import importlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ufm.application.dto.slice_facts import VerifiedSliceFacts
from ufm.integrations.sliced_files import MAX_ARCHIVE_BYTES, inspect_3mf_bytes

MAX_MANIFEST_BYTES = 128 * 1024


class SliceArtifactRejected(ValueError):
    def __init__(self, code: str = "slice_artifact.invalid") -> None:
        super().__init__(code)


@dataclass(frozen=True)
class StoredSliceArtifact:
    facts: VerifiedSliceFacts
    archive_path: Path


def _identity(expected_sha256: str, plate: int) -> None:
    if type(expected_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise SliceArtifactRejected("slice_artifact.hash_invalid")
    if type(plate) is not int or not 1 <= plate <= 1_000_000:
        raise SliceArtifactRejected("slice_artifact.plate_invalid")


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or os.fstat(stream.fileno()).st_size > limit:
            raise SliceArtifactRejected("slice_artifact.size_invalid")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise SliceArtifactRejected("slice_artifact.size_invalid")
        return data


def _manifest(facts: VerifiedSliceFacts) -> bytes:
    value = {
        "format": 1, "parser_version": facts.parser_version, "file_sha256": facts.file_sha256,
        "metadata_sha256": facts.metadata_sha256, "gcode_sha256": facts.gcode_sha256,
        "plate": facts.plate, "includes_purge": facts.includes_purge, "quantity": facts.quantity,
        "filaments": [{"filament_id": item.filament_id, "logical_material": item.logical_material,
                       "mass_mg": item.mass_mg} for item in facts.filaments],
    }
    data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > MAX_MANIFEST_BYTES:
        raise SliceArtifactRejected("slice_artifact.manifest_limit")
    return data


def _sync_directory(path: Path) -> None:
    # Windows does not expose directory fsync through the Python file API.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class SliceArtifactStore:
    """A trusted local root, with managed descendants checked before each access."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def _checked(self, path: Path) -> Path:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            raise SliceArtifactRejected("slice_artifact.path_invalid") from None
        current = self.root
        for part in relative.parts:
            current = current / part
            try:
                details = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(details.st_mode) or getattr(details, "st_file_attributes", 0) & 0x400:
                raise SliceArtifactRejected("slice_artifact.path_invalid")
        if not path.resolve().is_relative_to(self.root):
            raise SliceArtifactRejected("slice_artifact.path_invalid")
        return path

    @contextmanager
    def _publication_lock(self, parent: Path) -> Iterator[None]:
        lock_path = self._checked(parent / ".publish.lock")
        with lock_path.open("a+b") as lock:
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                module = importlib.import_module("msvcrt")
                module.locking(lock.fileno(), module.LK_LOCK, 1)
            else:
                module = importlib.import_module("fcntl")
                module.flock(lock.fileno(), module.LOCK_EX)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    module.locking(lock.fileno(), module.LK_UNLCK, 1)
                else:
                    module.flock(lock.fileno(), module.LOCK_UN)

    def _load(self, *, expected_sha256: str, plate: int) -> StoredSliceArtifact:
        destination = self._checked(self.root / expected_sha256 / str(plate))
        manifest = _read(self._checked(destination / "manifest.json"), MAX_MANIFEST_BYTES)
        archive = self._checked(destination / "archive.3mf")
        data = _read(archive, MAX_ARCHIVE_BYTES)
        facts = inspect_3mf_bytes(data, plate=plate, expected_sha256=expected_sha256)
        if manifest != _manifest(facts):
            raise SliceArtifactRejected("slice_artifact.manifest_mismatch")
        return StoredSliceArtifact(facts, archive)

    def load(self, *, expected_sha256: str, plate: int) -> StoredSliceArtifact:
        _identity(expected_sha256, plate)
        try:
            return self._load(expected_sha256=expected_sha256, plate=plate)
        except OSError:
            raise SliceArtifactRejected("slice_artifact.unavailable") from None

    def store_file(self, path: Path, *, expected_sha256: str, plate: int) -> StoredSliceArtifact:
        _identity(expected_sha256, plate)
        try:
            data = _read(path, MAX_ARCHIVE_BYTES)
        except OSError:
            raise SliceArtifactRejected("slice_artifact.unavailable") from None
        return self.store_bytes(data, expected_sha256=expected_sha256, plate=plate)

    def _cleanup(self, staging: Path) -> None:
        # Only this invocation's generated directory and its two fixed files are eligible.
        try:
            self._checked(staging)
            if not re.fullmatch(r"\.staging-[0-9a-f]{32}", staging.name):
                return
            for name in ("archive.3mf", "manifest.json"):
                self._checked(staging / name).unlink(missing_ok=True)
            staging.rmdir()
        except (OSError, SliceArtifactRejected):
            pass

    def store_bytes(self, data: bytes, *, expected_sha256: str, plate: int) -> StoredSliceArtifact:
        _identity(expected_sha256, plate)
        facts = inspect_3mf_bytes(data, plate=plate, expected_sha256=expected_sha256)
        manifest = _manifest(facts)
        staging: Path | None = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            parent = self._checked(self.root / expected_sha256)
            parent.mkdir(exist_ok=True)
            with self._publication_lock(parent):
                destination = self._checked(parent / str(plate))
                if destination.exists():
                    return self._load(expected_sha256=expected_sha256, plate=plate)
                staging = self._checked(parent / f".staging-{uuid4().hex}")
                staging.mkdir()
                for name, content in (("archive.3mf", data), ("manifest.json", manifest)):
                    with self._checked(staging / name).open("xb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                _sync_directory(staging)
                self._checked(destination)
                os.rename(self._checked(staging), destination)
                staging = None
                _sync_directory(parent)
                return StoredSliceArtifact(facts, destination / "archive.3mf")
        except OSError:
            raise SliceArtifactRejected("slice_artifact.unavailable") from None
        finally:
            if staging is not None:
                self._cleanup(staging)
