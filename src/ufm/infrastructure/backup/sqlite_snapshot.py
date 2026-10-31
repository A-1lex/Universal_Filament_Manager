"""Consistent SQLite online snapshots and non-destructive restore to a new target."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path


class BackupInvalid(RuntimeError):
    def __init__(self) -> None:
        super().__init__("backup.invalid")


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _read_connection(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    return sqlite3.connect(path.resolve().as_uri() + suffix, uri=True)


def _check(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise BackupInvalid()
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise BackupInvalid()


def create_snapshot(database: Path, bundle: Path) -> Path:
    """Write a new bundle exclusively. A failed/incomplete bundle is never reused."""
    if not database.is_file():
        raise BackupInvalid()
    bundle.mkdir(parents=True, exist_ok=False, mode=0o700)
    target = bundle / "database.sqlite3"
    try:
        with closing(_read_connection(database)) as source:
            with closing(sqlite3.connect(target)) as destination:
                source.backup(destination, pages=256)
                destination.execute("PRAGMA journal_mode=DELETE")
                _check(destination)
        manifest = {"format": 1, "sha256": _digest(target), "size": target.stat().st_size}
        with (bundle / "manifest.json").open("x", encoding="utf-8") as output:
            json.dump(manifest, output, sort_keys=True)
        verify_snapshot(bundle)
        return bundle
    except (OSError, sqlite3.Error, ValueError):
        raise BackupInvalid() from None


def verify_snapshot(bundle: Path) -> Path:
    try:
        with (bundle / "manifest.json").open("rb") as source:
            content = source.read(4097)
        if len(content) > 4096:
            raise BackupInvalid()
        manifest = json.loads(content)
        target = bundle / "database.sqlite3"
        if not isinstance(manifest, dict) or manifest.get("format") != 1:
            raise BackupInvalid()
        if manifest.get("size") != target.stat().st_size or manifest.get("sha256") != _digest(target):
            raise BackupInvalid()
        with closing(_read_connection(target, immutable=True)) as connection:
            _check(connection)
        return target
    except (OSError, sqlite3.Error, ValueError):
        raise BackupInvalid() from None


def restore_snapshot(bundle: Path, target: Path) -> None:
    """Never overwrite an existing DB. Switching the live application is separate."""
    source = verify_snapshot(bundle)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected_digest = _digest(source)
    # Copy only the verified main database, never unverified WAL sidecars.
    with target.open("xb") as destination, source.open("rb") as original:
        digest = hashlib.sha256()
        while chunk := original.read(1024 * 1024):
            destination.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != expected_digest:
        raise BackupInvalid()
    try:
        verify_snapshot(bundle)
        with closing(_read_connection(target, immutable=True)) as restored:
            _check(restored)
    except (OSError, sqlite3.Error):
        raise BackupInvalid() from None
