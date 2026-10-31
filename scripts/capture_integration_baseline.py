"""Capture private, non-destructive integration evidence; never overwrite a run.

Run from the source checkout using its Python environment. Archives stay under
.runtime (ignored by Git). Runtime credentials are deliberately not archived.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tomllib
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ufm.infrastructure.backup.sqlite_snapshot import create_snapshot, restore_snapshot

ROOT = Path(__file__).resolve().parents[1]
LEGACY = Path("D:/Filament_Manager")
INSTALLED = Path("D:/UFM Studio")
DATA = Path("D:/UFM Studio Data/data/ufm.sqlite3")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def summary(database: Path, kind: str) -> dict[str, object]:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        counts = {}
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = db.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
        if kind == "spoolman":
            rows = db.execute(
                "SELECT coalesce(s.initial_weight,f.weight),s.used_weight "
                "FROM spool s LEFT JOIN filament f ON f.id=s.filament_id"
            ).fetchall()
            known = [Decimal(str(initial)) - Decimal(str(used or 0))
                     for initial, used in rows if initial is not None]
            balance = str(sum(known, Decimal(0)))
            unit = "g"
            unknown = sum(initial is None for initial, _ in rows)
        else:
            rows = db.execute("SELECT effective_remaining_mg FROM spool").fetchall()
            balance = str(sum(row[0] for row in rows if row[0] is not None))
            unit = "mg"
            unknown = sum(row[0] is None for row in rows)
        return {"counts": counts, "remaining_total": balance, "unit": unit,
                "unknown_spools": unknown, "scope": "all spools, including archived"}


def archive_tree(source: Path, target: Path, *, source_only: bool = False) -> dict[str, object]:
    excluded = {".git", "node_modules", "__pycache__", ".runtime", "backups", "logs", "printers"}
    records = []
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as output:
        for directory, subdirs, filenames in os.walk(source, followlinks=False):
            subdirs[:] = sorted(name for name in subdirs
                               if not (Path(directory) / name).is_symlink()
                               and (not source_only or name not in excluded))
            for name in sorted(filenames):
                path = Path(directory) / name
                if path.is_symlink() or (source_only and name.startswith(".env")
                                        and name != ".env.example"):
                    continue
                relative = path.relative_to(source).as_posix()
                before = digest(path)
                output.write(path, relative)
                if digest(path) != before:
                    raise RuntimeError("Source changed during capture; retain failed run and retry")
                records.append({"path": relative, "sha256": before, "bytes": path.stat().st_size})
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive CRC verification failed")
        for record in records:
            with archive.open(str(record["path"])) as member:
                if hashlib.file_digest(member, "sha256").hexdigest() != record["sha256"]:
                    raise RuntimeError("Archived content hash mismatch")
    return {"archive": target.name, "sha256": digest(target), "files": records}


def main() -> None:
    run = ROOT / ".runtime/integration-baseline" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, exist_ok=False)
    report: dict[str, object] = {"format": 1, "created_utc": datetime.now(UTC).isoformat(),
                               "complete": False, "credentials_archived": False}
    # Snapshot first, then compare snapshot/restored statistics, never live-copy statistics.
    databases = {}
    for name, source in (("spoolman", LEGACY / "spoolman/spoolman.db"), ("ufm", DATA)):
        bundle = run / name
        create_snapshot(source, bundle)
        restored = run / "restore-check" / f"{name}.sqlite3"
        restore_snapshot(bundle, restored)
        original_summary = summary(bundle / "database.sqlite3", name)
        if summary(restored, name) != original_summary:
            raise RuntimeError("Restored record counts/balances differ")
        databases[name] = {"source": str(source), "sha256": digest(bundle / "database.sqlite3"),
                           "restored_sha256": digest(restored), "integrity": "ok",
                           "foreign_keys": "ok", "restore_matches": True, **original_summary}
    report["databases"] = databases
    with (ROOT / "pyproject.toml").open("rb") as stream:
        ufm_version = tomllib.load(stream)["project"]["version"]
    with (LEGACY / "localization/spoolman/pyproject.toml").open("rb") as stream:
        spoolman_version = tomllib.load(stream)["project"]["version"]
    report["versions"] = {
        "ufm_source": ufm_version,
        "spoolman_downloaded": spoolman_version,
        "haspelsync_downloaded": json.loads(
            (LEGACY / "localization/haspelsync/package.json").read_text("utf-8"))["version"],
        "haspelsync_own": json.loads(
            (ROOT / "linked-stack/haspelsync/package.json").read_text("utf-8"))["version"],
        "installed": {key: value for key, value in json.loads(
            (INSTALLED / "release-manifest.json").read_text("utf-8")).items()
                      if key in ("version", "stage", "created_utc")},
    }
    report["own_haspelsync_source"] = archive_tree(
        ROOT / "linked-stack/haspelsync", run / "haspelsync-own-source.zip", source_only=True)
    report["installed_program"] = archive_tree(INSTALLED, run / "installed-program.zip")
    report["limitations"] = [
        "Docker runtime unavailable at capture; compose images are declarations, not running-version proof.",
        "Private HaspelSync runtime configuration, history and credentials remain in place; "
        "a protected coherent backup of these still needs implementation.",
        "Source archive excludes .git, node_modules, caches, printers, backups, logs and .env files "
        "except .env.example. Git history is preserved in the original checkout, not in this archive.",
        "Database snapshots are independently consistent; they are not a synchronized cross-system cutover.",
        "Private snapshots contain personal inventory; never include them in a distributable package.",
    ]
    report["complete"] = True
    (run / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"run": str(run), "complete": True,
                      "databases": list(databases)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
