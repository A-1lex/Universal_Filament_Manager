"""Write a local integrity inventory for a completed Windows folder bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

_FORBIDDEN_SUFFIXES = {
    ".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite-shm", ".sqlite-wal",
    ".sqlite3", ".sqlite3-shm", ".sqlite3-wal", ".log", ".pem", ".p12", ".pfx",
    ".key",
}
_SOURCE_INPUT_FILES = (
    "pyproject.toml",
    "uv.lock",
    "THIRD_PARTY_NOTICES.md",
    "scripts/build_release_candidate.ps1",
    "scripts/build_studio.ps1",
    "scripts/build_installer.ps1",
    "scripts/collect_studio_notices.py",
    "scripts/create_studio_icon.py",
    "scripts/prepare_node_runtime.ps1",
    "scripts/sign_windows_artifact.ps1",
    "scripts/studio_entry.py",
    "scripts/sync_haspel_calculation_resources.py",
    "scripts/ufm_studio.iss",
    "scripts/ufm_studio.spec",
    "scripts/write_pyinstaller_version.py",
    "scripts/write_release_sbom.py",
    "scripts/write_studio_manifest.py",
    "linked-stack/haspelsync/src/calculation.js",
    "linked-stack/haspelsync/public/shared.js",
    "linked-stack/haspelsync/LICENSE",
)


def _is_forbidden_file(path: Path) -> bool:
    name = path.name.casefold()
    return (
        path.suffix.casefold() in _FORBIDDEN_SUFFIXES
        or name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_input_records(root: Path) -> list[dict[str, str | int]]:
    paths = [root / relative for relative in _SOURCE_INPUT_FILES]
    source_tree = root / "src" / "ufm"
    if not source_tree.is_dir():
        raise ValueError("source.package_tree_missing")
    paths.extend(sorted(source_tree.rglob("*")))
    records: list[dict[str, str | int]] = []
    for path in sorted(set(paths)):
        if path.is_dir() and not path.is_symlink():
            continue
        if path.is_symlink():
            raise ValueError("source.symlink_forbidden")
        if not path.is_file():
            raise ValueError("source.build_input_missing")
        if "__pycache__" in path.parts or path.suffix.casefold() in {".pyc", ".pyo"}:
            continue
        if _is_forbidden_file(path):
            raise ValueError("source.private_or_runtime_data_forbidden")
        records.append({
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    if not records:
        raise ValueError("source.build_inputs_empty")
    return records


def _source_provenance(root: Path) -> dict[str, object]:
    root = root.resolve(strict=True)
    records = _source_input_records(root)
    serial = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    revision: str | None = None
    worktree_clean: bool | None = None
    try:
        git_root = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if git_root.returncode == 0 and Path(git_root.stdout.strip()).resolve() == root.resolve():
            git_revision = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                capture_output=True, text=True, check=False, timeout=5,
            )
            git_status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            candidate_revision = git_revision.stdout.strip().lower()
            if (git_revision.returncode == 0
                    and re.fullmatch(r"[0-9a-f]{40,64}", candidate_revision)
                    and git_status.returncode == 0):
                revision = candidate_revision
                worktree_clean = not git_status.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "source_git_revision": revision,
        "source_git_worktree_clean": worktree_clean,
        "input_file_count": len(records),
        "input_tree_sha256": hashlib.sha256(serial.encode("utf-8")).hexdigest(),
        "inputs": records,
    }


def write_manifest(bundle: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    bundle = bundle.resolve(strict=True)
    if not bundle.is_dir():
        raise ValueError("bundle.directory_required")

    manifest_path = bundle / "build-manifest.json"
    files: list[dict[str, str | int]] = []
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink():
            raise ValueError("bundle.symlink_forbidden")
        if path == manifest_path or not path.is_file():
            continue
        if _is_forbidden_file(path):
            raise ValueError("bundle.private_or_runtime_data_forbidden")
        files.append({
            "path": path.relative_to(bundle).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })

    manifest = {
        "schema_version": 1,
        "artifact_type": "windows-folder",
        "project": project["name"],
        "version": project["version"],
        "built_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "machine": platform.machine(),
        "source_provenance": _source_provenance(root),
        "file_count": len(files),
        "files": files,
        "integrity_note": (
            "Hashes describe this folder tree at manifest generation time. The separate "
            "source_provenance field records selected source/build inputs and optional Git "
            "revision state; neither proves runtime behavior, full upstream package "
            "provenance, or license compliance."
        ),
    }
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest_path


def verify_manifest(bundle: Path) -> int:
    bundle = bundle.resolve(strict=True)
    if not bundle.is_dir():
        raise ValueError("bundle.directory_required")
    manifest_path = bundle / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("bundle.manifest_invalid")
    source = manifest.get("source_provenance")
    if source is not None:
        expected_source = _source_provenance(Path(__file__).resolve().parents[1])
        if source != expected_source:
            raise ValueError("bundle.source_provenance_mismatch")

    expected: dict[str, dict[str, str | int]] = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ValueError("bundle.manifest_record_invalid")
        relative = item.get("path")
        posix_path = PurePosixPath(relative) if isinstance(relative, str) else None
        windows_path = PureWindowsPath(relative) if isinstance(relative, str) else None
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or posix_path is None
            or windows_path is None
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or ".." in posix_path.parts
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
            or not isinstance(item.get("size_bytes"), int)
            or isinstance(item.get("size_bytes"), bool)
            or item["size_bytes"] < 0
        ):
            raise ValueError("bundle.manifest_path_invalid")
        if _is_forbidden_file(Path(relative)):
            raise ValueError("bundle.private_or_runtime_data_forbidden")
        if relative in expected:
            raise ValueError("bundle.manifest_duplicate_path")
        expected[relative] = item

    actual: set[str] = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("bundle.symlink_forbidden")
        if path.is_file() and path != manifest_path:
            relative = path.relative_to(bundle).as_posix()
            actual.add(relative)
            record = expected.get(relative)
            if record is None:
                raise ValueError("bundle.manifest_unlisted_file")
            if (path.stat().st_size != record.get("size_bytes")
                    or _sha256(path) != record.get("sha256")):
                raise ValueError("bundle.manifest_hash_mismatch")
    if actual != expected.keys() or manifest.get("file_count") != len(expected):
        raise ValueError("bundle.manifest_file_set_mismatch")
    return len(actual)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(f"Verified {verify_manifest(args.bundle)} bundle files")
    else:
        result = write_manifest(args.bundle)
        print(f"Wrote integrity manifest: {result}")
