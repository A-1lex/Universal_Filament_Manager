"""Copy the minimal linked Haspel calculation source into UFM package resources."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "linked-stack" / "haspelsync"
RESOURCE_ROOT = ROOT / "src" / "ufm" / "integrations" / "haspel_engine"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    calculation = (SOURCE_ROOT / "src" / "calculation.js").read_bytes()
    shared = (SOURCE_ROOT / "public" / "shared.js").read_bytes()
    license_text = (SOURCE_ROOT / "LICENSE").read_bytes()
    source_import = b'from "../public/shared.js";'
    packaged_import = b'from "./shared.js";'
    if calculation.count(source_import) != 1:
        raise SystemExit("Unexpected Haspel calculation import shape")

    RESOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    packaged_calculation = calculation.replace(source_import, packaged_import, 1)
    files = {
        "calculation.js": packaged_calculation,
        "shared.js": shared,
        "LICENSE": license_text,
    }
    for name, content in files.items():
        (RESOURCE_ROOT / name).write_bytes(content)

    provenance = (
        "# Vendored HaspelSync calculation resources\n\n"
        "Source: the locally preserved `linked-stack/haspelsync` tree, package "
        "version `1.3.4-local.1`.\n\n"
        "This package contains only `src/calculation.js`, `public/shared.js`, and "
        "the upstream `LICENSE`. The relative import in calculation.js is adjusted "
        "from `../public/shared.js` to `./shared.js` to make this package resource "
        "closure relocatable. No service, settings, logs, credentials, npm packages, "
        "or databases are copied. Re-run `python scripts/sync_haspel_calculation_resources.py` "
        "before packaging after changing the linked source.\n\n"
        f"Source calculation SHA-256: `{_digest(calculation)}`\n\n"
        f"Packaged calculation SHA-256: `{_digest(packaged_calculation)}`\n\n"
        f"Shared source/package SHA-256: `{_digest(shared)}`\n"
    )
    (RESOURCE_ROOT / "PROVENANCE.md").write_text(provenance, encoding="utf-8")
    print("Synchronized Haspel calculation resources:")
    for name, content in files.items():
        print(f"  {name}: sha256={_digest(content)} bytes={len(content)}")


if __name__ == "__main__":
    main()
