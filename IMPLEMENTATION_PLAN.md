# Universal Filament Manager — IMPLEMENTATION_PLAN

Current Phase 6 slice: atomic single-spool completed-print finalization is
implemented and covered by replay/crash/concurrency tests. The live receipt/job
ingestion worker, multi-segment accounting, failed/cancelled consumption and
reconciliation remain open. See docs/AUTOMATIC_ACCOUNTING_UK.md.

## Confirmed standalone product target — 2026-10-25

Build one native PySide6 desktop application combining Spoolman inventory,
HaspelSync printer/accounting workflows and UFM's existing domain core. End-user
installation must include its dependencies and require no browser, Docker or
separate Spoolman/HaspelSync service. UFM owns accepted stock and its immutable
ledger. Use modular provider contracts for expansion. The selected path and
source-data transition are specified in
[STANDALONE_DESKTOP_PLAN_UK](docs/STANDALONE_DESKTOP_PLAN_UK.md). Preserve the phase
numbering and accounting gates below; the current Tkinter shell and read-only
providers do not establish completion of the target product.

## Architecture gate (before Phase 0)

Read all five source-of-truth documents and complete the consistency review.
Canonical artifacts: docs/ARCHITECTURE_REVIEW.md, docs/REPOSITORY_STRUCTURE.md,
docs/STATE_MACHINES.md, docs/PROVIDER_CONTRACTS.md,
docs/database/SCHEMA_V1.md, docs/database/MIGRATIONS.md, docs/TEST_MATRIX.md.
User specification section 56 controls phase numbering. The old plan placed UI
and automatic deduction too early; this sequence supersedes that plan.

## Phase 0 — Repository foundation

Python 3.12+, src layout, pyproject, Ruff, pytest, mypy, three-OS CI, uk/en
localization parity, platformdirs paths, Pydantic settings, structured redacted
logging, composition root, secure keyring port. Add heavy dependencies only when
used. Exit: install/import/startup smoke, locale parity and redaction checks.

## Phase 1 — Domain core

Entities, immutable value objects, enums, transitions, provider/application ports
and domain invariants from DOMAIN_MODEL and docs/STATE_MACHINES.md. Include feed
topology, segments, evidence, receipts and finalization entities before UI.
Exit: unit tests for identity, exact units, unknown values and invalid transitions.

## Phase 2 — SQLite and migrations

SQLAlchemy 2.x, Alembic schema v1, repositories, explicit UnitOfWork, WAL/FKs/busy
limits, CAS, append-only guards, all constraints, backup and recovery. Implement
persistence primitives for later accounting commands now. Exit: schema/constraint,
rollback, migration and backup/restore tests using a real file database.

## Phase 3 — Inventory and FilamentTransaction

Create/edit/archive spool, explicit opening basis, signed append-only transactions,
manual adjustment, history, availability queries, alerts and idempotent inventory
commands. Exit: unknown/zero distinction, compensation, negative stock quarantine,
ledger rebuild and no direct balance mutation.

## Phase 4 — FeedSystem / FeedSlot / SpoolMount

External slot setup, unique physical mounting, unmount/history, unknown assignment,
atomic spool swap with material segments. No live AMS adapter yet. Exit: competing
mount rejection, unknown spool, temporal history, two segments after spool swap.

## Phase 5 — Reservation engine

Atomic activation and capacity checks, release/expiry guards, settled remainder
semantics. Exit: deterministic concurrent writers cannot overbook; disconnect or
unresolved running job does not expire material silently.

## Phase 6 — ConsumptionEvidence and reconciliation

Evidence scope/units, comparison policy, decisions, reconciliation tasks,
measurement cutoff, all-or-nothing finalization kernel using synthetic normalized
input. Exit: replay x100, different completion keys, rollback/crash recovery,
failed/cancelled 40% safe behavior, unknown allocations and conflicting evidence.
This headless kernel gate is required before UI; connecting real automatic
completion events remains Phase 11.

## Phase 7 — Basic PySide6 UI

Dashboard, spools/details, printers/feed systems, jobs/history, settings/logs.
Light/dark/system themes, uk-UA/en-US. UI calls application ports, no SQL or vendor
protocol code. Exit: headless UI smoke and manual workflow E2E on all three OSes.

## Phase 8 — Local printer providers

Credential configuration, verified local connection, health/capabilities,
normalized status/current-job/events, and reconnect for Bambu P1S/AMS plus
independent OctoPrint and Moonraker providers. The latter currently provide
read-only monitoring only. Do not copy GPL-3.0-only HaspelSync source. Automatic
stock deduction remains disabled until Phase 11 passes its gates. Exit: fixture
contract tests, saved connection profiles, and actual device verification with
recorded firmware/provider versions; cloud failure leaves local core usable.

## Phase 9 — Bambu Studio / 3MF parser

Plate/tool-aware estimates, exact units, bounded ZIP/XML parsing and G-code fallback.
Exit: valid sanitized fixtures plus traversal/bomb/DTD/duplicate-path/time-limit
security corpus. Parsed estimates alone cannot mutate stock.

## Phase 10 — Print lifecycle

Durable run aliases, detection/reservation/monitoring, out-of-order observations,
terminal states and recovery. Exit: same-file reprint is a new job; reconnect keeps
same job; reused vendor IDs and ambiguous terminal evidence require reconciliation.

## Phase 11 — Safe automatic deduction

Wire terminal events into the already tested accounting kernel. Keep disabled until
all production gates pass. Exit: concurrent completion, replay, process termination
at every write boundary, receipt recovery, segmented allocation, shortage and
measurement-cutoff tests, followed by an observed P1S end-to-end cycle.

## Phase 12 — Manual weighing/reconciliation

Manual scale entry, tare, accepted calibration/stability, prior-ledger cutoff,
audited correction and user evidence resolution. Exit: no double debit for a
measurement covering unfinalized consumption; stale readings cannot reset stock.

## Phase 13 — Statistics/costing

Filament valuation first; Decimal money, explicit currency, snapshot cost basis,
purge/waste inclusion. Additional electricity, labor, machine, maintenance and
markup components are optional separately tested additions. No implicit FX sum.

## Phase 14 — QR

UFM:SPOOL:<uuid>, label/scan workflow, validated UUID and no credentials. Scan proposes
an explicit mount command; it does not silently steal an already mounted spool.

## Phase 15 — Scale providers

Manual baseline then serial/USB/BLE/Wi-Fi/HTTP/MQTT/ESP32 adapters as independently
gated additions. Calibration records, stable reading and cancellation contracts.

## Phase 16 — Additional AMS support

Extend Phase 8 beyond the P1S target to other AMS variants and provider-specific
topologies. Keep tray_uuid/tag_uid evidence distinct, with trusted spool mapping
and temporal reconciliation. Exit: slot swaps preserve mount/segment history;
stale/missing telemetry cannot fabricate an empty slot or duplicate mount.

## Phase 17 — Klipper/Moonraker

Only after the P1S production vertical passes. Contract tests and explicit firmware
compatibility evidence; independent feature flag.

## Phase 18 — OctoPrint

Same isolation and provider acceptance gates; no brand branching in the core.

## Phase 19+ — Other ecosystems and later product work

Other printer providers, Spoolman import/export, storage/drying UX, sensors, richer
costing, local API/web/mobile, PostgreSQL/multi-user/sync, plugins, packaging and
updates follow separate bounded plans. Core storage entities may precede their UX.
Packaging/startup validation for the first desktop release is a cross-cutting
release task and does not wait for additional vendors. Remote API, sync authority,
plugin sandbox and signed updater require their own security/design gates.
No broad provider expansion before the P1S vertical is stable.

---
## MVP definition

MVP is NOT "all planned features".

A robust MVP should include:
- Windows/Linux/macOS app starts correctly
- uk/en i18n
- SQLite+migrations
- spool inventory
- transaction history
- manual weighing
- reservations
- Bambu P1S integration
- print job detection
- safe automatic consumption
- dashboard
- backup/restore
- logs
- installer/package

This is enough to validate the core product without compromising architecture.

---

## Non-goals for MVP

Delay:
- cloud sync
- multi-user
- mobile app
- plugin marketplace
- advanced sales/ERP
- dozens of printer vendors
- arbitrary remote API exposure

The architecture supports them, but they should not block a stable first release.

---

## Definition of Done for any feature

A feature is not complete until:
1. domain rule exists
2. persistence behavior is defined
3. migrations exist if needed
4. unit tests exist
5. integration/contract tests exist where relevant
6. uk/en strings exist
7. logs/diagnostics are defined
8. error handling is defined
9. security review completed
10. docs updated


---

## Risk-control workstream

These tasks run alongside feature development, not after it.

### Foundation gates
- idempotency utility/service
- optimistic concurrency support
- structured reconciliation states
- OS secret-store abstraction
- feature flags
- normalized provider DTO validation

### Bambu/P1S gates
Before automatic stock deduction is enabled:
- replay duplicate terminal events
- disconnect/reconnect tests
- app crash during finalization test
- wrong/unknown active-spool handling
- failed/cancelled print policy
- spool swap workflow
- conflicting evidence workflow

### Parser gates
Before enabling automatic 3MF/G-code ingestion:
- zip-slip tests
- zip bomb limits
- malformed XML fixtures
- huge G-code streaming test
- no execution/subprocess assertions

### Cross-platform gates
Every release candidate:
- Windows smoke test
- Linux smoke test
- macOS smoke test
- i18n key parity test
- migration test
- backup/restore test
- diagnostics secret-redaction test

### Public release gates
- dependency vulnerability scan
- SBOM
- signed artifacts/update metadata where update feature is enabled
- risk register reviewed
- no unresolved Critical release blockers
