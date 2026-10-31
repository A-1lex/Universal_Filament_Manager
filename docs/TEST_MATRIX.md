# Acceptance and release test matrix

The table is the normative acceptance plan, originally written before application
code existed. Selected implementation checks now run; see the evidence notes below
and IMPLEMENTATION_STATUS.md. A passing subset does not close an entire release gate.

Offline Spoolman preview evidence (2026-10-05):
tests/integration/test_spoolman_preview.py validates exact JSON decimal mass,
unknown/zero separation, distinct net/used/tare quantities, source-scoped identity,
duplicate IDs/keys, byte/row/depth limits, malformed encoding/shape, sanitized errors
and omission of extra metadata. It tests a review-only adapter, not live HTTP,
committed import, backups or accounting; see GITHUB_REUSE_REVIEW.md.

Applied reuse evidence (2026-10-05): test_reused_components.py checks the 34-record
pinned offline catalog, exact reference densities, missing temperatures, canonical
UUID label parsing and safe deterministic SVG structure. test_startup.py exercises
catalog/QR/file-preview processes without application directory creation or input
file modification, plus localized non-echoing failures. check_wheel.py checks
packaged catalog/license resources and QR generation in an isolated installation.
No physical scanner, printer or auto-import/finalization acceptance is claimed.

| ID | Requirement / risks | Level and stimulus | Required observable result | Phase |
|---|---|---|---|---|
| T-001 | Duplicate completion; R-003 | Integration: same terminal event 100 times | One initial finalization; exact single stock debit; receipt audit retained | 6,11 |
| T-002 | Crash atomicity; R-014,R-030 | Subprocess kill at each write step and immediately before/after commit | Restart finds all accounting changes or none; pending receipt replays safely | 6,11 |
| T-003 | P1S reconnect; R-015,R-023 | Contract/E2E: disconnect during print, reconnect same occurrence | Same internal job UUID; connection loss does not set FAILED | 8,10 |
| T-004 | Cancel at 40%; R-005 | Unit/integration: 200 g slicer estimate, cancelled 40%, no actual data | No automatic 200 g or unapproved 80 g debit; NEEDS_RECONCILIATION | 6,11 |
| T-005 | Physical exclusivity; R-026 | Two real DB connections mount same spool on different printers concurrently | Exactly one active mount; other operation rejected; rejection audited | 4 |
| T-006 | AMS slot A2 swap; R-006,R-028 | Normalized snapshot then actual adapter fixture | Old mount closed; new mount and segment start; adjacent intervals, no history deletion | 4,16 |
| T-007 | Unknown external spool; R-007 | Known occupied slot with no trusted identity | ACTIVE_SPOOL_UNKNOWN; unresolved segment/task; no guessed debit | 4,6 |
| T-008 | Mid-print spool swap; R-006 | Public swap command on one material channel | Two segments bound to correct spools; later decisions/transactions preserve allocation | 4,6 |
| T-009 | Negative stock; R-017 | Known 50 g stock, eligible actual 70 g use | -20 g retained; QUARANTINED, alert/task and debit commit together | 3,6 |
| T-010 | 3MF traversal; R-010 | ZIP names ../, backslash traversal, absolute, drive/UNC, symlink, normalized duplicate | Safe rejection; no file outside private temp; inventory unchanged | 9 |
| T-011 | Secret in error payload; R-009 | Nested provider error, repr/traceback, headers/cookie/credential URL | Secret absent from every log/diagnostic sink and stored metadata | 0,8 |
| T-012 | Cross-platform; R-024 | CI install/import/startup on Windows/Linux/macOS, GUI smoke after Phase7 | Correct paths, clean startup/shutdown, explicit unavailable native features | 0,7,release |
| T-013 | Distinct keys same job; R-003 | Concurrent completion A and B and duplicate key/different request | One job finalization; conflicting key reuse reports IdempotencyConflict | 6,11 |
| T-014 | Reprinted same file; R-023 | Two runs sharing filename/hash/external ID but valid distinct occurrence | Two internal jobs; replay of each still one debit; ambiguous identity blocks mutation | 10 |
| T-015 | Reservation race; R-004 | Two connections reserve 420 g each against 700 g using synchronization barriers | One succeeds; 280 g available; losing command receives conflict/insufficient stock | 5 |
| T-016 | Evidence conflict; R-016 | Comparable 181/194/186 g plus an above-threshold case | All evidence preserved; policy version/reason visible; above threshold blocks auto debit | 6 |
| T-017 | Measurement cutoff; R-027 | Post-print absolute measurement arrives before late completion | Acceptance blocked until covered usage resolved; no double deduction afterward | 6,12 |
| T-018 | Measurement aging; R-002 | Accept trusted 700 g then post 100 g use; replay old reading | measured stays 700 g with original time; effective 600 g; stale reset rejected | 12 |
| T-019 | Evidence scopes; R-029 | Cumulative readings 10/20/30 g, inclusive purge, mismatched intervals | Authorized total 30 g once; no summing to 60 or adding purge twice | 6 |
| T-020 | Scale validity; R-018 | Unstable, expired calibration, wrong tare/spool, negative net, stale interval | Reading cannot auto-correct stock; typed rejection/task preserves provenance | 12,15 |
| T-021 | Mount ordering; R-028 | Old snapshot after current slot change; partial snapshot missing slot | No rollback of current mount; missing slot not treated EMPTY | 4,16 |
| T-022 | Ledger immutability; R-031 | SQL UPDATE/DELETE history, duplicate sequence, mismatched previous/new | DB rejects; compensation command appends; rebuild equals stored projection | 2,3 |
| T-023 | Backup/restore; R-021,R-034 | WAL writes during snapshot, Unicode assets, tampered/missing asset | Verified restore preserves data; tampered restore rejected; source remains intact | 2,release |
| T-024 | Migration; R-022 | Each released schema fixture -> latest; kill during upgrade | History/IDs/constraints preserved or explicit recoverable failure, never empty reset | 2,every schema change |
| T-025 | Unknown quantities and exact units | Unit/property cases: None vs 0, bool, float, NaN/Inf, overflow, fractional mg | Unknown propagates; invalid input rejected; exact valid conversions | 1 |
| T-026 | States | Table-driven valid/invalid transitions, late terminal detection, conflicting terminal | Only contract transitions; terminal cannot reopen; conflict task retained | 1,10 |
| T-027 | Archive/storage/transfer | Archive mounted/reserved spool, storage cycle, location move, paired transfer crash | Invalid archives/cycles blocked; move changes no mass; transfer conserves mass atomically | 3,4 |
| T-028 | Keyring unavailable; R-033 | Backend contract with secure/unavailable/insecure backend | No plaintext fallback; affected integration disabled, inventory works | 0,8 |
| T-029 | Parser budgets; R-010,R-011 | ZIP bomb, falsified sizes, oversized XML, DTD/entities, huge G-code line and cancellation | Bounded rejection/time/memory behavior; no shell/eval/exec path | 9 |
| T-030 | Localization; R-025 | Key and interpolation-placeholder parity; locale fallback; visible error codes | uk-UA/en-US complete and renderable; missing locale falls back to English | 0,7 |
| T-031 | Provider isolation; R-001,R-019 | Adapter raises malformed payload/auth/timeouts; cloud offline | Core/manual inventory stays available; stable health/reason, bounded retries | 8 |
| T-032 | Expiry/shortage; R-035 | Restart/clock jump with running job; correction below active claims | No silent release; shortage alert and no new unsafe capacity | 5,12 |
| T-033 | Full P1S vertical | Hardware E2E: connect->mount->detect->parse->reserve->monitor->finalize->history->cost->weigh | Correct physical spool and single audited debit with explainable correction | 11–13 |
| T-034 | Money | Decimal rounding, missing currency, multiple currencies, revised purchase price | Exact cost basis retained; no implicit currency sum or historical rewrite | 13 |
| T-035 | Future remote/plugin/update/sync gates | Feature-specific auth/permission/signature/partition tests | Features remain disabled until all required controls pass | 19+ |
| T-036 | Receipt interruption; R-030 | Commit PENDING receipt then kill before handler; same key different hash | Restart processes once; hash conflict cannot be silently treated as success | 6,11 |
| T-037 | One slot, competing spools | Concurrent different spools into same feed slot; overlapping historical intervals | One active mount; overlapping history rejected even when both mounts closed | 4 |
| T-038 | Cross-entity integrity | Segment references mount on another spool; decision references another job's material | FK/trigger/application boundary rejects mismatched accounting scope | 2,6 |
| T-039 | Finalized attribution | Attempt to change finalized segment spool/interval; explicit correction command | Direct edit rejected; old debit compensated and new debit committed atomically | 6,12 |
| T-040 | Reservation immutability | Change active amount/spool directly; competing resize; replay settlement | Direct edit blocked; atomic re-reservation rechecks capacity; no repeated allocation | 5,6 |
| T-041 | Confirmed zero usage | Eligible zero actual evidence versus missing evidence | Zero decision finalizes without debit and releases claim; unknown stays unresolved | 6 |
| T-042 | Estimate replay | Opening estimate, use, measurement correction, explicit estimate rebase, later policy change | Stored estimate before/after replays exactly; reading changes estimate only with recorded adoption | 3,12 |

Tests run at the lowest layer that proves each risk. Concurrency tests use separate
connections/processes against a real temporary SQLite file and deterministic
barriers, not sleeps or in-memory per-connection databases. Exception rollback
tests supplement rather than replace actual process-termination tests.

The verification report records command, commit/file baseline, OS/Python/dependency
versions, exit code, case IDs and limitations. Hardware fixtures include sanitized
provenance and firmware version. Fake-provider results do not establish real P1S
compatibility. All three OS jobs must actually pass before claiming cross-platform
startup support. A completed risk-control design is not a mitigated production risk.

## Selected local evidence — 2026-09-17

`tests/integration/test_topology_commands.py` uses real temporary file databases.
Its scenarios cover local unknown-assignment intervals/tasks and rollback (T-007),
slot/material identity checks (T-038), stale explicit swap/unknown/unmount commands,
and concurrent mounts for both exclusivity directions (T-005/T-037 subsets).
Concurrent tests require the specific occupancy rejection, not a generic DB error.
The T-005 test uses two printers and verifies retained rejection audit. Competing
mount/swap occupancy rejections are audited after rollback; a failed audit write
is surfaced separately. T-021 provider snapshot ordering
is not proven by local command preconditions. Real evidence allocation/finalization
parts of T-007/T-008/T-038 remain Phase 6 work.

`tests/integration/test_reservation_commands.py` covers reservation request hashes,
changed-input rejection, original resize identity, restart via a new command
instance, and concurrent identical requests retaining one claim and audit record.
Audit failure rolls back the claim and permits a later valid retry. These extend
the T-040 local replay evidence, not T-036 pending-receipt recovery or T-002 process
crash acceptance. Settlement still needs integration into Phase 6's single
accounting transaction. Full local suite: 223 tests and 122 subtests passed;
Ruff and mypy (80 source files) passed on Windows/Python 3.12.

Spool creation replay now has real-file regressions after metadata editing and
through a new command instance, with changed request/key rejection and atomic
rollback on audit failure. The latest full suite is 225 tests and 128 subtests;
Ruff and mypy passed. Other inventory command replay and cross-process crash
acceptance are not established by these tests.

Creation concurrency uses two synchronized writers against one real temporary
database: identical requests retain one spool/audit and differing payloads under
one key require one explicit IdempotencyConflict. Latest full verification:
227 tests, 128 subtests, Ruff and mypy passed. These are thread/connection tests,
not cross-process crash or multi-device authority evidence.

Edit/archive/rebuild request replay now preserves later spool changes, rejects
changed inputs and cross-operation keys, and rolls back on audit failure. Exact
replay after archival is read-only; new archived-spool writes remain prohibited.
Latest Windows/Python 3.12 run: 232 tests, 145 subtests, Ruff and mypy passed.
Ledger command and topology request identity remain separate open work.

Ledger request-identity follow-up: opening/adjustment/compensation now reject
changed actors and reused metadata keys. Real-file tests cover exact replay via
a new command instance, injected audit-boundary exception rollback/retry, and two
concurrent identical adjustments applying one debit. Full local suite: 236 tests,
148 subtests; Ruff and mypy passed. This improves T-022 replay evidence, not T-002
process-kill accounting acceptance. Topology request identity remains open.

External-slot creation now rejects changed request fields/keys and replays the
current assignment after mounting. Audit failure rolls back a new system and slot
together. Latest suite: 237 tests, 152 subtests; Ruff and mypy passed. Other topology
commands still need durable request identity; provider ordering remains unverified.

Delayed unmount replay now additionally rejects changed actor/material/slot/key or
new expected mount under the old key. The new mount remains active in all five
cases. Latest suite: 237 tests, 157 subtests; Ruff and mypy passed. This covers an
explicit-command replay risk, not stale provider snapshot ordering (T-021).

Unmount audit-failure regression confirms mount and slot rollback plus later
retry/replay on a real database. Latest full suite: 238 tests, 157 subtests; Ruff
and mypy passed. Exception rollback is not process-termination crash evidence.
