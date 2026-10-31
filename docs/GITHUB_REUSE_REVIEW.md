# GitHub reuse review — 2026-10-05

## Outcome and evidence boundary

No identical implementation was identified in the inspected repositories. This is
a targeted search, not proof that no identical project exists on GitHub. UFM's
offline desktop, exact immutable ledger and atomic segmented accounting contracts
are retained. Repository feature claims are not hardware acceptance evidence.
Default-branch pages were inspected. The subsequent material-data reuse below is
commit-pinned; no upstream application source has been vendored.
Pin a commit, inspect file-level notices and dependencies before any future copying.

## Candidate components

| Project / source | Useful content | Fit and decision |
| --- | --- | --- |
| [Spoolman](https://github.com/Donkie/Spoolman) | Inventory API, catalog relationships, labels, import/export interoperability | Best inventory interchange target. [MIT notice](https://github.com/Donkie/Spoolman/blob/master/LICENSE) inspected. Do not replace UFM's ledger with remote balance writes. |
| [SpoolmanDB](https://github.com/Donkie/SpoolmanDB) | Manufacturer/material catalog data | MIT notice inspected; 34 generic material records now bundled from a pinned commit. Brand/product catalogs remain future work. Nominal weight cannot initialize physical stock automatically. |
| [Filament Manager](https://github.com/cgradl/filament-manager) | Print-review UI, spool-at-start snapshots, cloud MQTT, projects/cost screens | README advertises MIT; LICENSE retrieval was unavailable, so copying is not cleared. Backend tree and [cloud client](https://github.com/cgradl/filament-manager/blob/master/filament_manager/backend/app/bambu_cloud_client.py) inspected. Cloud-first/HA-dependent workflow is not UFM's default. |
| [SpoolmanSync](https://github.com/gibz104/SpoolmanSync) | Slot assignment, QR/NFC workflows, multi-feeder dashboard | [MIT notice](https://github.com/gibz104/SpoolmanSync/blob/main/LICENSE.txt) inspected. UI reference for later phases, not a drop-in PySide6 component. HA integration and density assumptions need independent adapter validation. |
| [bambu-middleman](https://github.com/szymon3/bambu-middleman) | LAN P1S monitoring, G-code consumption by layer | README declares GPL-3.0; full license fetch unavailable. [Parser documentation](https://github.com/szymon3/bambu-middleman/blob/master/docs/gcode-parser.md) inspected. Single-filament Orca scope; no code copied. Layer-derived consumption remains modeled evidence, not measured usage. |
| [HaspelSync](https://github.com/Rdiger-36/HaspelSync) | LAN MQTT/FTPS, external spool and AMS matching, G-code tracking | Repository declares GPL-3.0; full license fetch unavailable. Useful integration reference; no code copied. Material/color matching must remain a proposal, not proof of physical identity. |

The independent preview uses Spoolman's documented wire fields, not its Python
classes. No upstream executable, service or Docker image was installed. The later
slice bundles material data and adds Segno as a normal dependency. UFM's license remains an owner decision; this
review does not select it. Direct MIT copying would retain copyright/license notices;
GPL incorporation needs an explicit distribution/licensing decision first.

## Compatibility findings

The inspected Filament Manager cloud client stores a token in a JSON credential
file and keeps its encryption key beside password ciphertext. That model is not
compatible with UFM's verified OS SecretStore requirement. Do not copy its credential
storage, exception logging or absolute container paths. This is a local compatibility
finding, not a complete security audit of that project.

Spoolman's [v1 response schema](https://github.com/Donkie/Spoolman/blob/master/spoolman/api/v1/models.py)
defines remaining_weight as estimated net grams. used_weight is consumed grams;
spool_weight is tare. These fields must not be interchanged. The schema has integer
external IDs, not UFM UUIDs. Unknown remaining_weight cannot be reconstructed from
nominal weight without an explicitly accepted opening basis.

No inspected upstream workflow has been verified against all UFM release gates:
duplicate completion, atomic all-segment accounting, crash recovery, unknown spool,
measurement cutoff and failed/cancelled-print policy. Reuse can shorten adapter/UI
work but does not close Phase 6 or hardware acceptance.

## Working component assembled in this slice

[preview.py](../src/ufm/integrations/spoolman/preview.py) combines an independent
Spoolman wire normalizer with UFM's existing exact Mass value object:

- Input: caller-provided UTF-8 bytes containing GET /api/v1/spool response array,
  plus an opaque stable source-instance name (not a URL or credentials).
- Output: immutable source-scoped IDs, filament identity/name/material/vendor,
  location, estimated remaining mass, archived flag and SHA-256 input fingerprint.
- Limits: 4 MiB default input, configurable up to 32 MiB; 10,000 maximum rows;
  JSON nesting capped at 32; retained text capped at 500 characters.
- Decimal JSON parsing avoids binary floats. Negative, nonfinite, out-of-range,
  fractional-milligram quantities, duplicate IDs/keys and malformed metadata reject
  the whole preview. Unknown remains None; confirmed zero remains Mass(0).
- Unknown fields are not retained. Error text is stable and does not echo payloads.
  Names/material/location remain untrusted descriptive text, not credential storage.
- No network, DB writes, UUID creation, stock adoption, mounting, tag reassignment,
  CSV/backup parsing or historical transaction import. Fingerprint alone is not an
  authenticated source or durable idempotency receipt.

Example, after installing the project:

```python
from ufm.integrations.spoolman.preview import preview_spools

response = b'[{"id":1,"filament":{"id":2,"name":"PLA"},"archived":false,"remaining_weight":500.125}]'
preview = preview_spools(response, source_instance="my-spoolman")
assert preview.spools[0].estimated_remaining.milligrams == 500125
```

Synthetic contract examples live in
[test_spoolman_preview.py](../tests/integration/test_spoolman_preview.py).
No live Spoolman server was exercised. There is no user-facing import UI yet.

## Assembly sequence and remaining work

1. Retain and complete UFM's Phase 6 finalization kernel before connecting any
   automatic debit source. Upstream consumers must submit normalized evidence,
   never directly overwrite stock or settle a reservation separately.
2. Add explicit reviewed import commands with persisted source-ID/UUID mapping,
   accepted opening basis, audit, replay/conflict handling and one atomic batch.
   Preview does not authorize those writes; mapping needs a migration-safe design.
3. Build desktop screens using the existing application commands and upstream
   interaction patterns, with uk/en resources. Web/HA frontends are not PySide6.
4. Implement P1S LAN adapter behind PrinterProvider with OS secrets, TLS trust,
   fixtures, reconnection/run identity and hardware evidence. Keep cloud optional.
5. Add bounded 3MF/G-code parser behind SlicerProvider. Preserve tool/plate,
   purge scope and unknowns. Do not treat layer count or progress as measured mass.
6. Add catalog import, QR and AMS workflows at their documented phase gates.
   Catalog/type/color/labels cannot silently select a physical spool.

This slice provides a tested reusable boundary, not a complete assembled product.
No scheduler was resumed, and no commit/push/deploy/live integration was performed.

## Fresh verification

Windows/Python 3.12: focused preview tests 7 passed / 19 subtests; full suite
260 passed / 197 subtests; Ruff passed; mypy passed for 83 source files; sdist and
wheel build passed. Initial focused collection failed because the adapter package
was absent; implementation then made it pass. Linux/macOS and live-server behavior
remain unverified.

## Expanded reuse applied — 2026-10-05

The explicit follow-up authorized broader reuse, without changing the ledger,
secret-store or production hardware gates. Applied components:

| Component | Actual application in UFM | Evidence / limitations |
| --- | --- | --- |
| SpoolmanDB `materials.json` | All 34 records from commit `8f1a99f9cda7a58ca3118d6bd28c707647caa3db`, packaged offline with full MIT notice | Exact Decimal density, preserved labels and unknown temperatures. Suggestions only; no automatic profile or stock creation. |
| [Segno](https://github.com/heuer/segno) | Public QR encoder/serializer API, dependency 1.6.6 tested, BSD-3-Clause notice packaged | Canonical internal UUID labels, standard QR SVG, four-module border. Tests inspect SVG structure/identity serialization; physical scan/printing remains unverified. |
| Spoolman preview | Exposed through an explicit local-file CLI operation | Bounded file read; no HTTP, DB or stock changes. |

Source access for the catalog was sandbox-blocked and then performed with approved
network access. Dataset values are unchanged; JSON whitespace was compacted.
Segno's installed license was inspected. See [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md).
This is substantive data/library reuse rather than copying another application's DB.

Further GitHub references inspected: [ha-bambulab](https://github.com/greghesp/ha-bambulab)
and [OpenBambuAPI](https://github.com/Doridian/OpenBambuAPI) for later printer-adapter
research; [BambuStudio 3MF source](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Format/bbs_3mf.cpp)
and SpoolmanDB's filament schema for format research. No code from these sources was
copied and their integration/security/license acceptance is not established here.

Usable offline commands (stdout contains JSON or SVG, not a persisted import):

```powershell
& ./.venv312/Scripts/python.exe -m ufm --catalog
& ./.venv312/Scripts/python.exe -m ufm --qr-label 01234567-89ab-4cde-8123-0123456789ab
& ./.venv312/Scripts/python.exe -m ufm --spoolman-preview inventory.json --source-instance my-spoolman
```

The preview input must be the Spoolman v1 spool-list JSON response, not a DB backup
or CSV. `--source-instance` must remain stable for that source. Modes are mutually
exclusive; locale/error handling is Ukrainian/English. All three skip startup DB,
settings and application-directory creation. SVG rendering creates bytes only;
it neither prints nor mounts a spool. Camera scanning/label UI are still planned.

Fresh combined verification after integration: 267 tests / 206 subtests passed,
Ruff passed, mypy passed for 85 source files, sdist/wheel build passed. A fresh
isolated wheel installation verified packaged data/licenses, QR generation,
migration replay and startup in both locales (exit 0). This confirms these local
components, not live printer, physical scanner or full-product readiness.
