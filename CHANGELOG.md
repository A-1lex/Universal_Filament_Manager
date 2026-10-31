# Changelog

## Unreleased — 2026-10-05

- Bundled 34 MIT SpoolmanDB material reference records from a pinned commit and
  integrated Segno QR rendering with preserved third-party notices.
- Added localized offline catalog, UUID QR SVG and local Spoolman file-preview CLI
  modes, process tests and installed-wheel resource/label checks. No auto-import
  or live printer accounting was enabled.

- Reviewed GitHub component candidates and recorded license/architecture boundaries.
- Added a bounded, exact-mass, offline Spoolman v1 inventory preview adapter and
  synthetic tests. No stock mutation, live integration or vendored code is enabled.

## Unreleased — 2026-09-27

- Added abrupt-process-exit recovery tests for spool swap with material segments
  and active reservation acquisition, including durable replay after reopening.

- Verified inventory adjustment recovery using abrupt child-process exit before
  and after commit, database reopening, request replay and integrity/FK checks.

- Added durable request fingerprints for swap and unknown-assignment commands.
  Delayed retries preserve newer placement, while altered requests and fresh
  commands with stale revisions are rejected.

- Persist complete mount-command request fingerprints with the atomic success audit.
  Exact retries return historical mounts after unmount/remount; altered actor,
  material, segment or spool requests are rejected without changing placement.

## Unreleased — 2026-09-11

- Completed the current 33-table SQLite schema and accounting/history guards.
- Added frozen Alembic v1, crash rollback and schema-parity validation.
- Added concrete repositories and explicit atomic UnitOfWork with CAS, failure
  rollback, ledger/snapshot validation and reservation capacity checks.
- Added verified SQLite snapshot/restore and packaged migration smoke checks.
- Recorded the actual continuation point in docs/IMPLEMENTATION_STATUS.md.

## Unreleased — 2026-09-10

- Implemented the Phase 0 Python foundation: CLI/composition root, bounded strict
  settings, native paths, uk/en localization, redacted structured logging and an
  OS-secret-store port/adapter.
- Added Windows startup, packaging, localization, logging and secret-store checks;
  isolated wheel validation now installs and exercises declared runtime dependencies.
- Started Phase 1 with an immutable exact-mass value object using integer milligrams,
  explicit Decimal conversion, no float path and no silent sub-milligram rounding.
- Added the first persisted domain enums and fail-closed transition policy for print,
  reservation, mount and spool lifecycles, including terminal/idempotent behavior.
- Added canonical UUID and timezone-aware UTC value objects, completed the Phase 1
  enum catalog, and covered accounting/reconciliation state edges fail-closed.
- Added framework-neutral printer/feed/slot/mount entities with physical interval
  exclusivity checks, plus the initial Spool aggregate with distinct inventory
  projections, quarantine preservation and schema-safe exact mass bounds.
- Added print-run identity aliases, logical material channels and physical usage
  segments with reconnect/reprint distinction and non-overlapping segment history.
- Added immutable normalized printer observations and vendor-neutral monitoring/control
  ports that preserve unknown/unavailable/stale semantics and confirmed-idle distinction.
- Added reservation, consumption/inventory evidence, receipt, decision and lifetime
  finalization records without granting evidence an inventory mutation path.
- Added exact append-only ledger and material-transfer records with replay, balance,
  direction and command guards, plus revision-aware repository and shared UoW ports.
- Added reconciliation, audit, catalog, storage, calibration, local device identity,
  secret-reference connection, spool-identifier and feature-flag domain records.
- Completed normalized provider DTOs for feed topology, bounded slicer projects and
  scale observations, preserving unknown values, exact mass and calibration scope.
- Added vendor-neutral slicer, scale, notification, backup and dormant sync ports,
  bounded backup manifests, stable provider errors and contract tests for authority
  separation; no concrete vendor or sync adapter is enabled.
- Started Phase 2 with SQLAlchemy/Alembic dependencies, a hardened file-backed SQLite
  engine (FKs, WAL, FULL sync, busy timeout), exact persistence types and real-file
  rollback tests.
- Canonicalized persisted UTC timestamps to fixed-width microsecond `Z` text so
  SQLite lexical order remains chronological within a second.
- Added the first schema-v1 metadata block for device identity, catalog, sensors,
  storage and printer/feed configuration with database-level FK/CHECK/UNIQUE guards.
- Reviewed five supplied architecture documents against the user's specification;
  recorded 19 consistency findings and corrected their source-of-truth rules.
- Replaced printer active-spool shortcut with physical feeder/slot/mount history.
- Defined lifetime job finalization uniqueness, mandatory atomic accounting,
  receipt recovery, segment allocations and measurement-cutoff protection.
- Aligned Phase0–19+ with the requested order and added explicit pre-UI core gates.
- Added repository/entity maps, enum/transition and provider/UoW contracts, logical
  schema v1, constraint catalog, migration/restore strategy and 42 planned tests.
- Added ten uncovered risks with module ownership; risks remain unverified until
  implementation tests pass. No runtime functionality or production readiness claimed.
