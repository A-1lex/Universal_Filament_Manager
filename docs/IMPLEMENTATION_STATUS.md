# Implementation checkpoint — 2026-10-05

## Atomic single-spool finalization — 2026-10-26

Implemented `FinalizationCommands.finalize_single` on the existing v1 schema and
shared UnitOfWork. It accepts one completed job with one fully closed assigned
segment and persisted, alias-scoped PRINTER/ABSOLUTE mass evidence. Decision,
evidence link, exact ledger/projection, own reservation settlement, finalization,
job/receipt transitions and audit commit together. Zero usage releases the claim
without a zero debit. Replay validates request/result hashes; changed keys or
actors conflict. Other jobs' active reservations remain protected.

Shortages, unknown/quarantined stock, ambiguous mapping, estimates, incomplete
purge coverage, a late opening balance and overlapping weighing are rejected
without writes; persisted evidence remains for later reconciliation. The service
does not poll hardware and is not wired to the live GUI/worker. Failed/cancelled
prints, multiple segments/AMS, evidence selection policies and reconciliation
incidents are still open Phase 6 work; the full automatic-accounting gate is not closed.

Added 14 integration tests and 20 subtests: exact success/proof links, zero usage,
replay after reopen and later manual use, conflicting commands, rollback after
ledger/settlement/receipt writes, two concurrent writers, reservation overrun,
unknown/insufficient stock, identity/mapping/evidence guards, late weighing, and
real subprocess termination before/after commit. Full suite: **327 passed,
231 subtests passed**, process exit 0. Ruff passed; strict mypy passed for 97
source files. No new dependencies, schema migration or production data changes.

## Native UFM Studio preview — 2026-10-26

Added a PySide6/Qt Widgets workspace without a browser or Docker: inventory
metrics/search, material-profile and spool creation, exact opening/manual stock
commands, ledger history, previewed Spoolman import and verified snapshots,
background local discovery/status probes, local printer enrollment, Bambu Studio
profile enrollment with explicit certificate trust, Ukrainian/English resources,
and light/dark themes. Physical printer commands and automatic print debits are
still not implemented; this slice does not close the accounting finalization gate.

The native onedir EXE was built with PyInstaller and smoke-tested with an explicit
test data root and screenshot capture (exit 0). Python and Qt are in the bundle.
This is a local Windows test, not a clean-machine distribution acceptance test.
The bundle lives at `D:/UFM Studio`; personal data stays outside it in
`D:/UFM Studio Data`. A source-preserving import copied 5 spools/5 profiles/2 vendors
from the current Spoolman database, total **3,999,672 mg**; the October 24 total
below is historical. No historical print transactions or printer credentials were
imported, and no legacy runtime was stopped or modified.

Six new tests cover Studio stock commands, idempotency, overspend rejection,
unknown stock, catalog validation, backup and Qt inventory interaction. Full suite
at the initial native checkpoint: 312 passed, 211 subtests passed. Ruff and strict
mypy passed (96 source files). See `DEVELOPMENT_HANDOFF.md` for subsequent checks.

## Standalone product direction confirmed — 2026-10-25

The user selected one extensible native desktop application combining Spoolman
and HaspelSync capabilities within UFM, without a browser or Docker requirement.
Added STANDALONE_DESKTOP_PLAN_UK.md, recorded option A in the integration
comparison, and aligned README, architecture and implementation-plan wording.
The native target is PySide6, UFM owns stock through its ledger, and future
integrations use versioned adapter contracts. This update changes documentation
only. It does not add Qt dependencies, complete finalization, install an app,
change inventory or switch the running legacy stack. Existing implementation
and acceptance limitations below remain applicable.

## Local desktop shell and Spoolman import — 2026-10-24

Added a small Tkinter desktop shell with a local inventory view and a preview/
confirmation workflow for importing the existing Spoolman SQLite database.
The importer validates its schema and balances, creates verified source and
existing-target snapshots under the UFM data directory, and records known
remaining balances as initial ledger entries. Re-import is idempotent. The live
legacy inventory was imported: 5 spools, 5 opening transactions, 2 brands; total
remaining stock is 4,180,552 mg (rounded to the ledger's 1 mg precision). The
source backup was verified; the imported SQLite database passed integrity and
foreign-key checks. No historical print transactions were available to import.
This is an early Tkinter shell, not the planned complete PySide6 UI or a full
HaspelSync replacement. The HaspelSync reference checkout is present under
`linked-stack/haspelsync` and is GPL-3.0-only; no HaspelSync source has been copied
into UFM. The separate runtime setup under `D:\Filament_Manager` still uses
Docker. No Bambu/AMS provider or automatic finalization has been implemented.
Keep ledger writes gated until replay/crash tests and a physical printer
end-to-end check pass. Full Windows/Python 3.12 suite: 272 tests / 206 subtests
passed; Ruff passed for `src` and `tests`, and mypy passed for all 87 source files.
CLI preview/import and desktop `--help` were smoke-tested. GUI interaction has
not been manually exercised.

## Read-only OctoPrint and Moonraker providers — 2026-10-24

Added independent local HTTP adapters for OctoPrint-compatible devices and
Klipper/Moonraker printers. They expose normalized health, job/progress and
temperature snapshots, with bounded response sizes, disabled proxy/redirect
following, private-IP-only endpoints, and API credentials supplied as secret
values. Moonraker filament length is exposed only as a provisional estimate;
neither adapter mutates inventory or claims a unique print-run ID. Seven local
fixture-server tests cover snapshots, event repeat suppression, auth failures,
offline health, endpoint validation, and verified profile persistence. Desktop
enrollment was added in the following checkpoint; no physical printer was used.

## Desktop setup for local printer providers

The desktop shell now offers OctoPrint and Moonraker selection, endpoint test,
and printer/profile persistence. Credentials are saved to the native OS secret
store; SQLite receives only the credential reference. The endpoint must pass the
existing literal-local-address checks and respond successfully before the
connection is saved. Configured printer names, providers, and local endpoints are
listed in the desktop window. This remains read-only monitoring: no durable
polling worker, live-status view, AMS setup, or physical device verification has
been added.

The inventory screen now has Ukrainian/English tabs, search, stock summary cards,
spool creation from existing material profiles, opening-stock entry, guarded
manual additions/deductions, and per-spool ledger history. Deductions are checked
against available stock in the same ledger transaction, including active
reservations. They are manual adjustments, not printer-confirmed print
consumption. Adding material profiles, durable printer polling, AMS-to-spool
assignment, a durable print lifecycle/finalization kernel, installer packaging,
and physical-device acceptance remain outstanding.

## Bambu Lab LAN monitoring integration

Added a Bambu LAN Mode MQTT/TLS read-only provider and desktop setup fields for
local IP, serial number, access code, and an optional trusted TLS certificate
file. Setup verifies the MQTT connection and receives a printer report before
saving; the access code is stored in the OS credential store and the TLS profile
in SQLite. The printer tab can request a one-time status snapshot including print
progress, temperatures, and AMS tray identifiers. AMS tray occupancy/identity
is observation only: no spool assignment, remaining mass inference, control
commands, or ledger writes are performed. TLS verification is never disabled.
Fixture/provider tests do not replace acceptance against the user's physical
printer; firmware/protocol compatibility remains to be verified on hardware.

## Applied upstream resources and usable CLI — 2026-10-05

Bundled all 34 generic material records from pinned SpoolmanDB commit
8f1a99f9cda7a58ca3118d6bd28c707647caa3db with its MIT notice. Integrated Segno
1.6.6 as a declared runtime dependency, preserving its BSD-3-Clause notice.
Three read-only CLI modes expose catalog JSON, canonical UUID QR SVG and explicit
local-file Spoolman preview. Commands bypass application-directory creation and
stock mutation. uk/en help/errors, process tests and installed-wheel resource/label
checks were added. These isolated utilities do not complete GUI, scan/mount,
committed import, Phase 6 finalization or P1S hardware gates.
See GITHUB_REUSE_REVIEW.md and THIRD_PARTY_NOTICES.md for provenance and scope.
Fresh Windows/Python 3.12: 267 tests / 206 subtests passed; Ruff and mypy (85
source files) passed; sdist/wheel built successfully. The fresh isolated wheel
installation passed packaged catalog/licenses, QR identity/rendering, migration
replay and uk/en startup checks (exit 0). Hardware scanning and Linux/macOS remain
unverified. No schema changes, commits, deployments or scheduler changes occurred.

## GitHub reuse and offline Spoolman preview — 2026-10-05

Inspected six related repositories and Spoolman's concrete v1 response schema.
[Reuse review](GITHUB_REUSE_REVIEW.md) records candidates, source/licensing limits
and the assembly order. No upstream code/dataset/service was installed or vendored.
An independent preview normalizer reuses UFM's exact Mass type and preserves unknown
estimated stock and source-scoped IDs. Bounded JSON, duplicates, invalid units and
unsafe values reject without writes. It is an isolated interoperability slice,
not a committed import, UI, live integration or completed Phase 19.
Fresh Windows/Python 3.12: 260 tests / 197 subtests, Ruff, mypy (83 source files),
sdist/wheel build passed. Phase 6 and the production/hardware gates remain open.
The paused scheduler was not resumed by this one-off request.

## Validated inventory quarantine resolution — 2026-10-05

`InventoryCommands.resolve_quarantine` now explicitly confirms an already corrected
inventory incident. It validates ordered immutable ledger history and both stored
projections, a known nonnegative balance, active reservation capacity and absence
of unaccounted usage (including closed segments of unfinished jobs). It only resolves
the inventory negative-stock/review and reservation-shortage tasks owned by this
spool; other live incidents block resolution. Actor, reason and expected revision
are recorded with a durable request fingerprint in the atomic success audit.
The command changes no mass or ledger history. Health, task resolution and alert
state commit together; matching replay is read-only, and changed requests conflict.
An explicit correction is still needed before confirming a negative balance.

Real-file regressions cover repaired negative stock, retained reservations after
shortage repair, stale revisions, invalid reasons, unrelated tasks, open/closed
unaccounted usage, replay and audit-boundary rollback/retry.
Fresh Windows/Python 3.12: 251 tests, 178 subtests; Ruff, mypy (80 files) and
sdist/wheel build passed. Phase 6 atomic finalization remains the next major gate.
The dated entries below retain earlier slice evidence and historical next steps.

## Topology and reservation process recovery — 2026-09-27

Real child processes now exit abruptly before and after commit for a material-aware
spool swap and active reservation acquisition. Reopening verifies all-or-nothing
mount/segment/receipt state and reservation capacity. Successful swap replay retains
exactly two adjacent segments; reservation replay retains one claim and one receipt,
with 280 mg available from 700 mg after a 420 mg claim. Exit codes verify that each
worker reached its intended fault boundary rather than failing during setup.
Swap recovery additionally checks SQLite integrity and foreign keys.

Fresh Windows/Python 3.12: 244 tests, 175 subtests; Ruff, mypy (80 files) and
sdist/wheel build passed. Only tests/docs changed since the last isolated wheel
check. These cover process exit at commit boundaries, not every internal write,
power loss, all reservation transitions or three-platform execution. Cross-family
command keys, validated quarantine resolution and Phase 6 finalization remain open.

## Inventory process-exit recovery — 2026-09-27

Inspected the current commands, implementation checkpoint and phase plan before
continuing; the existing migration process-exit test did not cover inventory commands.
A real-file integration regression now runs adjustment in a separate Python process
and calls os._exit(37) at two commit boundaries. Before commit, ledger, projection
and receipt all remain unchanged after reopening. After commit, all three are
present and a fresh command instance replays the original transaction without a
second debit. SQLite integrity_check and foreign_key_check pass afterward.
This demonstrates abrupt process-exit recovery at those boundaries, not power-loss
durability or every internal write boundary. Topology/reservation process recovery,
cross-family command-key uniqueness and quarantine resolution remain open.

Fresh Windows/Python 3.12 evidence: 242 tests and 171 subtests passed, Ruff and mypy
passed (80 source files), and sdist/wheel build passed. Production code was unchanged;
the prior isolated wheel/migration/startup verification remains the latest such run.

## Swap and unknown-assignment replay — 2026-09-27

Both commands now atomically store complete versioned request fingerprints in
their success audit. Swap retries return the historical replacement mount after
closure; unknown-assignment retries return the current slot without reapplying
unknown state after a later mount. Expected original mount/revision, actor and
optional material/segment identities participate in request matching. Execution
time remains excluded, consistently with other command families.
Fresh commands still validate current revisions. A matching physical state alone
does not establish a prior command receipt. Tests distinguish a verified replay
from a new stale request and reject altered identities without touching placement.

Fresh Windows/Python 3.12 verification: 241 tests, 169 subtests; Ruff and mypy
(80 files), sdist/wheel build and isolated wheel migration/startup checks all
passed. Further work includes cross-family command-key enforcement, process-kill
recovery evidence and validated quarantine resolution before Phase 6 completion.
These results do not establish hardware or three-platform acceptance.

## Mount replay continuation — 2026-09-27

Mount commands now persist the complete request fingerprint with their success audit.
Replay checks actor, slot/spool/mount, assignment source/confidence and optional
material/segment identities before inspecting mutable placement. An exact replay
returns the historical mount, including after closure and replacement, without
altering the new assignment. Occupancy alone no longer proves command execution.
Windows/Python 3.12 verification: 239 tests and 161 subtests passed; Ruff and mypy
passed (80 source files); sdist/wheel build passed. The isolated wheel check
passed after an escalated retry for sandbox-blocked dependency downloads, including
packaged migration replay and startup in both locales (exit 0).
Swap and unknown-assignment request fingerprints remain the next implementation
steps. Phase 6 atomic finalization and the other documented gates remain open.

Resume inspection found completed foundation/domain work and an incomplete Phase 2,
despite the old README describing only the first mass value object.

## Implemented in this continuation

- Expanded SQLite metadata to 33 application tables covering inventory, physical
  segments, evidence, reservations, finalization, ledger, reconciliation and audit.
- Enforced immutable history, ledger sequence/balance continuity, physical interval
  scope, active reservation identity and settlement constraints with SQL guards.
- Froze Alembic revision `0001_initial` as packaged SQL, independent of live model
  imports. Unknown/unversioned/newer schemas are rejected without resetting data.
- Added explicit `BEGIN IMMEDIATE` UnitOfWork and concrete persistence ports with
  compare-and-swap revisions, transaction poisoning after database failures and
  commit-time ledger/projection agreement. New active claims require known capacity.
- Added online SQLite snapshots with hashes/integrity/FK verification and exclusive
  restore into a new path; unverified WAL sidecars are not restored.
- Extended isolated wheel checks to execute the packaged migration twice.

## Evidence and boundaries

Real-file tests exercise rollback after normal errors and process termination before
migration commit, duplicate finalization, immutable history, inconsistent snapshots,
stale revisions, backup restore and schema-object parity. Run `python -m pytest`,
`python -m ruff check .`, `python -m mypy`, then build/check_wheel.py for fresh counts.
Current verification uses Windows/Python 3.12 in `.venv312`, not a three-platform
release approval. The older `.venv` references an unavailable interpreter.

The snapshot helper covers the database only. Full asset/config bundles, disk-budget
checks, recovery UI and upgrades from future released versions remain to implement.
Only empty-to-v1 and validated v1 no-op migration paths are enabled. No live data
upgrade, automatic replacement or downgrade is enabled.

## Phase 3–5 implementation (partial, not acceptance approval)

Phase 3 is now started: create/edit/archive spool, explicit opening-stock,
manual-adjustment and exact single-use compensation commands are transactional and
audited. Ledger commands are idempotent, preserve unknown versus known-zero stock,
update projections atomically and quarantine negative balances. Archiving rejects
active mounts/reservations and unresolved usage (including closed segments awaiting
job finalization). Archived spools reject new opening/adjustment/compensation/rebuild
writes while allowing read-only command replay. Ledger replay/rebuild,
reservation-aware availability/history queries, low-stock alerts, and deduplicated
negative-stock reconciliation alerts are implemented. Corrections that create
reservation shortage preserve claims and the debit, quarantine the spool and create
a deduplicated RESERVATION_SHORTAGE task. Positive adjustments/rebuilds do not clear
quarantine: an explicit reconciliation workflow is still required.
Phase 4 now covers external feed-slot setup, transactional mount/unmount,
unknown assignment and atomic spool swap, including active-resource conflict checks,
slot-state updates and material-segment rotation. Continue with broader topology query
access and remaining Phase 4 edge cases. Phase 5 reservation commands now cover
pending/active acquisition, serialized capacity checks, release, persisted-deadline
expiry with running/unresolved job protection, atomic release-and-resize, and
settlement of allocated consumption plus released remainder. A two-writer test
accepts one claim and requires a typed ReservationCapacityExceeded rejection for
the other: unrelated lock/database failures can no longer count as success.
Broader cross-process scheduling tests remain pending. Phase 6 is not implemented.
Its synthetic evidence/finalization kernel must precede GUI or printer integration.

The persistence ports cover the current domain records; extended catalog fields,
evidence-link access and full workflows must be extended with their consumers.
No real P1S, automatic debit or GUI verification has occurred.

## Reconciliation findings and corrected behavior

Architecture and state-machine documents describe normative requirements, not a
completed implementation. README and ARCHITECTURE no longer claim the repository
contains only design or that inventory commands are absent. The original
architecture review is explicitly marked historical.

Expiry previously freed claims for COMPLETED/FAILED/CANCELLED jobs even when
accounting was NOT_STARTED. It now requires DETECTED/PREPARING, no started_at,
and NOT_STARTED accounting. Terminal jobs require accounting/reconciliation,
not deadline-based release. Focused regressions: 8 tests and 10 subtests pass,
including protected states, unchanged claims on rejection and queued replay.
Provider freshness is not integrated: an old queued status is not sufficient
evidence for safe expiry after a disconnect. No automatic scheduler is implemented.

Open requirements, in dependency order:

1. Phase 3: broaden recovery evidence and complete measurement/transfer consumers.
   Explicit validated quarantine resolution now exists. Archive/archived mutation and correction shortage guards
   now have application-command regressions.
2. Phase 4: broaden durable command replay and cross-family concurrency evidence.
   Unknown assignment now creates an unresolved segment and deduplicated task;
   omitted/wrong material cannot leave open usage behind on a slot change.
3. Phase 5: reservation request fingerprinting and original resize identity are
   implemented (details below). Provider freshness and broader process/recovery
   tests remain open; the local tests do not close all R-035 requirements.
4. Phase 6: settle currently commits independently with caller-supplied actual
   mass. It is a primitive, not an atomic finalization workflow. Evidence,
   decisions, ledger, settlement, job, projections and receipts must commit together.
   Do not wire this primitive directly to automatic completion.
5. Cross-cutting: complete domain field/invariant coverage and user-facing diagnostics,
   real OS credential stores and hosted Windows/Linux/macOS results remain gates.

CLI startup tests cover foundation composition, not a complete inventory/printer
workflow. Phases 0–2 have implemented building blocks and local tests, not blanket
release approval. Phases 3–5 are partial; Phase 6 and later consumers remain pending.
No Git metadata is present in this directory, so a versioned baseline diff cannot
be established. Fresh `build --no-isolation` and `scripts/check_wheel.py` passed:
wheel installed outside the checkout, packaged migration ran twice, and startup
checks passed in both locales. These are Windows-only packaging checks.

Fresh verification for this checkpoint: `pytest -q -p no:cacheprovider` —
251 passed, 178 subtests passed after the validated quarantine resolution continuation;
`ruff check .` — passed; `mypy` — no issues
in 80 source files. These results do not establish the open acceptance gates above.

Manual-release follow-up: ACTIVE claims now require an unused queued job, with
the same persisted start/accounting protection as expiry. PENDING proposals may
still be cancelled because they hold no capacity. Regression tests cover ten
protected job/accounting cases, unchanged claims, and pending cancellation/replay.
Resize now applies the same unused-job protection to ACTIVE claims and rejects
reuse of the original reservation ID. Durable resize replay identity was
subsequently implemented below; provider freshness remains open.

Further corrections: ledger replay validates estimated as well as effective
continuity; manual adjustment cannot replay a compensation command with matching
mass; editing the low-stock threshold refreshes alerts without adding ledger rows.
Both inventory alert messages now have Ukrainian and English translations.

External-slot creation now validates replayed slot/system identity and rejects
reuse of another printer's feed system instead of silently linking the wrong
printer. This does not replace a durable command request-fingerprint mechanism.

## Automated continuation — topology safety

- Explicit unknown assignment closes the previous segment and starts a new
  ACTIVE_SPOOL_UNKNOWN segment with no spool/mount and zero confidence. It creates
  an ACTIVE_SPOOL_UNKNOWN task scoped to slot/job; an unchanged repeat reuses the
  existing outcome. Unknown-from-start is supported for a known material channel.
- Wrong slot, printer or tool context is rejected; a slot with open usage requires
  the matching material. Unmount/swap cannot silently leave that usage open.
- Regression tests cover nonzero temporal intervals, deduplicated task/audit,
  rollback after audit failure, and preservation of original state on rejection.
- Slot audit events use entity_type=feed_slot rather than spool_mount.
- Mount/swap replay rejects changed mount identity, provenance or confidence.
  Durable request fingerprints and complete segment replay comparison remain open.
- API changes: unmount_slot and swap_spool require expected_mount_id;
  mark_assignment_unknown requires expected_slot_revision. Repeating an old unmount
  after a new spool was installed returns the closed historical mount and never
  removes the new spool. All repository callers were updated.
  Stale swap/unknown commands are rejected rather than changing a newer assignment.

These commands are explicit local operations, not telemetry handlers. Stale or
missing provider observations must not invoke unknown-assignment automatically.

Topology checkpoint: full tests/lint/types and isolated wheel verification passed
for that slice. Two real-connection mount races verify
both exclusivity directions. The same-spool race now uses two printers, and
competing mount/swap rejections persist an audit event after transaction rollback.
Failure to persist rejection audit propagates a storage/validation error rather
than being presented as an ordinarily audited occupancy conflict.

Next safe continuation: durable request identity/replay for inventory and topology,
then remaining reservation recovery gates. Do not begin GUI or connect automatic
accounting until Phase 6 atomic finalization and replay/crash gates are implemented.
Automatic continuation checks the remaining allowance between completed slices.

## Automated continuation — reservation request replay

All six reservation commands (reserve, activate, resize, release, expire, settle)
store a versioned SHA-256 request fingerprint in the existing immutable
audit_event.parameters_json field, atomically with the reservation change.
Operation, entity identities, actor, expected revisions and command-specific input
(including deadline, release reason, actual consumption and original resize claim)
are compared before replay. The execution clock `at` is intentionally excluded.
No schema migration or raw request payload storage was introduced.

An exact replay returns the current reservation record, not a frozen original
response, and makes no additional mutation. Changed requests, legacy records with
no fingerprint and ambiguous audit keys are rejected rather than guessed valid.
Serialized SQLite writers protect concurrent application calls; the audit
correlation column is not a database-enforced unique command registry. Topology
does not yet implement the same gate, so this is not a global
cross-command-family idempotency guarantee.

Real-file regressions cover restart through a new command instance, changed
payloads, unrelated resize replacements, simultaneous identical requests producing
one reservation/audit event, and rollback of both claim and receipt on audit failure.
The fresh full suite, Ruff and mypy exited successfully on Windows/Python 3.12.
Fresh `build --no-isolation` and `scripts/check_wheel.py` also exited 0 after the
reservation changes: isolated wheel installation, packaged migration twice and
startup in both locales passed. Only documentation was edited afterward.
Process-termination reservation replay and Phase 6 atomic accounting remain unproven.

## Automated continuation — spool creation replay

`create_spool` previously compared the current mutable spool with its initial
candidate, rejecting a valid retry after editing and ignoring command-key identity.
It now stores a versioned request hash in the creation audit, in the same transaction
as the spool. An exact retry returns the current spool without reverting edits;
changed keys/inputs and existing records without a verified receipt fail closed.
The execution clock is excluded, matching reservation replay semantics. No schema
change was needed. Tests reproduce the original failure and cover a new command
instance, six changed-input/key cases, and rollback/retry after failed audit.

The full suite (225 tests, 128 subtests), Ruff, mypy, build and isolated wheel
verification passed (exit 0, Windows/Python 3.12). This is only the
creation command: edit/archive/rebuild and ledger-command request identity still
need review, as do topology commands and cross-family key enforcement.

Concurrency follow-up: two synchronized real-file SQLite writers now test both
identical creation (both callers receive one committed spool, one audit record)
and conflicting payloads under one key (one success, one IdempotencyConflict,
winner preserved). Generic database errors cannot satisfy the rejection test.
Focused tests: 2 passed. Full suite: 227 passed, 128 subtests; Ruff and mypy passed
(exit 0). Only tests/documentation changed since the successful wheel check above.
Next slice remains edit/archive/rebuild request replay; no Phase 6 gate is closed.

## Automated continuation — spool mutation replay

Edit, archive and projection rebuild now persist versioned request fingerprints
with their atomic audit record. Exact retries return the current spool, including
later edits/accounting changes or archival, without repeating changes or alerts.
Changed actor, target, expected revision or edit fields fail with IdempotencyConflict;
an archived state alone no longer proves that an archive command was executed.
Create/edit/archive/rebuild share the same local hash/replay implementation, with
the original creation hash format preserved. The execution clock is excluded.

Regressions first reproduced stale-revision rejection of legitimate edit/rebuild
retries and unchecked archive repeats. They now cover later changes, restart via
a new command instance, cross-operation key reuse and rollback on audit failure.
Fresh full suite: 232 tests, 145 subtests passed; Ruff and mypy passed (80 files).
Build and isolated wheel verification also exited 0 after these production changes,
including packaged migration replay and startup in both locales.
These are Windows/Python 3.12 results, not process-kill or three-platform evidence.
Next: complete opening/adjustment/compensation request identity and topology replay.
Legacy receipts without hashes remain unverifiable; no migration guesses old inputs.

## Automated continuation — ledger request identity

Opening stock, manual adjustment and compensation now store request hashes in the
same commit as ledger/projection/audit. Replay requires both the original ledger
entry and one matching audited request. Changed actors or metadata-operation key
reuse are rejected; exact repeats return the original immutable transaction, not
a new debit. Existing spool/type/delta/compensation checks remain in place.
Legacy ledger entries without a matching hashed audit cannot be verified and fail
closed. No stored history or migration was rewritten.

Regressions reproduced acceptance of changed actors and reuse of a metadata key.
New tests cover all three commands through a new command instance, an injected
failure at the audit boundary after real ledger/projection writes with successful
rollback/retry, and two synchronized identical adjustments producing one debit.
Full Windows/Python 3.12 suite: 236 tests, 148 subtests; Ruff and mypy passed.
Build and isolated wheel checks also passed (exit 0), including packaged migrations
and both startup locales, after the final production/test changes.
The fault injection is an exception test, not a process-termination recovery test.
Next safe slice: topology request identity, then broader restart/crash evidence and
explicit quarantine resolution. Phase 6 is still not an atomic accounting workflow.

## Automated continuation — external-slot request replay

External slot creation now persists the complete request fingerprint in its atomic
audit record, including system/slot/printer identity, name, key, tool and actor.
Changed input or command-key reuse is rejected; a matching retry returns the
current slot even after a mount has changed its assignment. A legacy slot without
a matching receipt is not inferred to be a completed command. No schema changed.
Tests cover eight changed-field/key cases, replay through a new command instance
after mounting, and failed audit rollback of both a newly created feed system and
slot followed by successful retry. The rollback fixture uses a new printer because
the external provider-system key is unique within a printer.

Fresh Windows/Python 3.12 verification: 237 tests, 152 subtests; Ruff and mypy passed.
Build and isolated wheel/migration/startup checks passed with exit 0 after the changes.
Mount/unmount/swap/unknown-assignment request identity remains the next slice;
physical occupancy rejection audits are not successful command receipts.

## Automated continuation — unmount request replay

Unmount now fingerprints slot, expected mount, actor and optional material in the
atomic success audit. A prior closed mount is not by itself proof of a completed
command. Exact replay returns that historical closed mount, including through a
new command instance after another spool is mounted. Changed inputs or a different
key are rejected; reusing the original key with the newer mount cannot remove it.
Regression tests demonstrated that unsafe key reuse before the change and now
verify five conflicting-request cases with the new mount preserved.

Fresh full suite: 237 tests, 157 subtests; Ruff and mypy passed on Windows/Python 3.12.
Build and isolated wheel/migration/startup checks passed with exit 0 afterward.
Next: mount/swap/unknown-assignment request identity. Unmount process-kill recovery
and complete cross-command-family key enforcement are not yet verified.

Unmount rollback follow-up: a real-file test fails audit validation after mount
closure and slot update, verifies both records and absence of a receipt, then
successfully retries and replays. Full suite: 238 tests, 157 subtests; Ruff and mypy
passed (exit 0). Only tests/docs changed since the last successful build/wheel check.
Next implementation slice remains mount/swap/unknown request identity. This checkpoint
is safe to resume after quota recovery; Phase 6 and production acceptance remain open.
