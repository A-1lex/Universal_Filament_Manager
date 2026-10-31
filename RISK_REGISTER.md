# Universal Filament Manager — RISK_REGISTER

## Purpose

This register is part of the architecture contract. Risks listed here are not optional considerations: each high/critical risk must have a technical control, test strategy, and acceptance criteria before the relevant feature is considered production-ready.

Scoring:
- Probability: 1..5
- Impact: 1..5
- Score = Probability × Impact
- 16–25: Critical
- 10–15: High
- 5–9: Medium
- 1–4: Low

---

## R-001 — Vendor API/protocol instability

**Risk:** Printer vendors can change LAN protocols, cloud APIs, firmware payloads, authentication, or event behavior.

Probability: 4  
Impact: 5  
Score: 20 — Critical

### Controls
- Core must never depend directly on vendor payloads.
- Every vendor integration lives behind `PrinterProvider`.
- Vendor payloads are normalized into internal DTOs.
- Capability detection replaces brand-based assumptions.
- Integrations expose health/degraded states.
- Feature flags can disable broken integration paths.
- Fallback chain: printer provider → slicer/3MF → G-code → manual mode.
- Integration version compatibility matrix must be maintained.
- Recorded fixtures from real devices are stored for regression testing.

### Acceptance criteria
- Application remains usable for inventory/manual tracking if vendor API is unavailable.
- A broken Bambu adapter must not crash the core or database.
- Provider contract tests pass for every supported version.

---

## R-002 — Filament remaining amount is only an estimate

**Risk:** Without physical measurement, purge, manual extrusion, failed prints, trimming, and spool changes accumulate error.

Probability: 5  
Impact: 4  
Score: 20 — Critical

### Controls
- Separate:
  - `estimated_remaining_g`
  - `measured_remaining_g`
  - `effective_remaining_g`
  - `reserved_g`
  - `available_g`
- Store all consumption evidence.
- Support periodic weighing.
- Never silently overwrite estimated values with measured values.
- Reconciliation policy chooses effective value and records reasoning.
- Track confidence score.
- Alert when discrepancy exceeds configurable threshold.

### Acceptance criteria
- User can see whether a value is measured or estimated.
- Every correction is auditable.
- Large discrepancies create a reconciliation task instead of silent adjustment.

---

## R-003 — Duplicate print completion / duplicate consumption

**Risk:** MQTT replay, reconnect, polling overlap, or provider bugs can finalize the same print twice.

Probability: 4  
Impact: 5  
Score: 20 — Critical

### Controls
- External event dedupe key.
- Idempotency token per finalization.
- Unique DB constraint on finalized consumption.
- Reservation consumption must be unique.
- Finalization runs inside one database transaction.
- `PrintJob.finalization_state`:
  - NOT_STARTED
  - IN_PROGRESS
  - FINALIZED
  - NEEDS_RECONCILIATION
- Duplicate terminal events are recorded but ignored for stock mutation.

### Acceptance criteria
- Replaying the same completion event 100 times changes stock exactly once.
- Crash/restart during finalization cannot cause a second deduction.

---

## R-004 — Race condition between concurrent reservations/prints

**Risk:** Two printers or workers reserve the same remaining material concurrently.

Probability: 3  
Impact: 5  
Score: 15 — High

### Controls
- Optimistic concurrency using `revision`.
- Reservation creation and availability check occur in the same transaction.
- Compare-and-swap updates.
- Retry on conflict with bounded attempts.
- DB constraints for active reservation integrity.

### Acceptance criteria
- Two concurrent activations cannot reserve more than known available stock. No overbooking override is enabled in v1; later physical consumption evidence is accounted and reconciled separately.
- Conflict produces a user-visible resolution state, not corrupted balance.

---

## R-005 — Cancelled/failed print charged as full print

**Risk:** Slicer estimate is deducted even though job stopped early.

Probability: 4  
Impact: 4  
Score: 16 — Critical

### Controls
- Terminal-state-aware consumption policy.
- Priority for:
  1. stable scale delta
  2. printer actual usage
  3. usage segments
  4. progress estimate
  5. manual confirmation
- Failed/cancelled jobs may remain `NEEDS_RECONCILIATION`.
- Configurable uncertainty threshold.

### Acceptance criteria
- Failed/cancelled job is never automatically charged the full initial slicer estimate. Insufficient actual evidence requires an audited user resolution; progress is not a proven mass fraction.

---

## R-006 — Spool replacement during print

**Risk:** All material is charged to the wrong spool after a manual swap.

Probability: 3  
Impact: 4  
Score: 12 — High

### Controls
- `MaterialUsageSegment` entity.
- Spool activation/deactivation events.
- Manual mid-print spool swap action.
- Provider event integration when available.
- Post-print split reconciliation.

### Acceptance criteria
- One print can consume multiple physical spools on the same tool/material channel.
- History preserves each segment separately.

---

## R-007 — Wrong active spool selected

**Risk:** Without AMS/NFC/QR the system cannot physically prove which spool is mounted.

Probability: 4  
Impact: 4  
Score: 16 — Critical

### Controls
- Explicit FeedSystem/FeedSlot/SpoolMount topology with physical spool and slot exclusivity.
- Confirmation before first print after ambiguous spool change.
- QR/NFC scan support.
- Optional scale association.
- Warning when job material profile mismatches selected spool.
- Unknown-spool state is first-class, never guessed silently.

### Acceptance criteria
- If active spool cannot be determined with sufficient confidence, automatic deduction is blocked or marked unresolved according to policy.

---

## R-008 — Multi-PC SQLite corruption/conflicts

**Risk:** Users attempt to open/sync one SQLite file from multiple active computers or cloud-sync folders.

Probability: 3  
Impact: 5  
Score: 15 — High

### Controls
- Local-first single-writer desktop DB.
- Explicit warning against Dropbox/Google Drive/OneDrive live DB sync.
- Future sync uses change journal/API, not raw DB file copying.
- Server mode uses PostgreSQL.
- Device identity and revisions included from day one.

### Acceptance criteria
- Documentation and UI explicitly prevent unsupported shared-file mode.
- Multi-device mode cannot be enabled without proper sync/server backend.

---

## R-009 — Plaintext credentials

**Risk:** Printer access codes, tokens, cloud sessions, or SMTP secrets leak through DB/config/logs.

Probability: 3  
Impact: 5  
Score: 15 — High

### Controls
- `SecretStore` abstraction.
- Windows Credential Manager / DPAPI.
- macOS Keychain.
- Linux Secret Service/libsecret.
- Fail closed when a verified secure OS keyring is unavailable; custom encrypted vault deferred.
- DB stores `credential_ref` only.
- Global log redaction middleware.

### Acceptance criteria
- Secret scanning of DB, config, logs, and diagnostics bundle finds no plaintext credentials.

---

## R-010 — Malicious or malformed 3MF

**Risk:** ZIP bomb, zip-slip/path traversal, oversized XML, entity expansion, malformed archive.

Probability: 3  
Impact: 5  
Score: 15 — High

### Controls
- Archive size limit.
- Uncompressed size limit.
- Entry count limit.
- Reject absolute paths and `..`.
- XML external entities disabled.
- Parsing timeout.
- Temporary sandbox path.
- No extraction outside sandbox.
- Fuzz/malformed corpus tests.

### Acceptance criteria
- Zip-slip test cannot create files outside sandbox.
- Oversized archive is rejected before memory/disk exhaustion.

---

## R-011 — Malicious G-code input

**Risk:** Parser treats G-code or comments as executable commands or shell input.

Probability: 2  
Impact: 5  
Score: 10 — High

### Controls
- Parsing is read-only.
- Never execute G-code during analysis.
- No shell interpolation.
- Streaming parser.
- Maximum file size/configurable limits.
- Treat comments and metadata as untrusted strings.

### Acceptance criteria
- G-code parser has no subprocess/shell execution path.

---

## R-012 — Plugin compromise

**Risk:** Third-party Python plugin gets full process/user permissions.

Probability: 3  
Impact: 5  
Score: 15 — High

### Controls
- No arbitrary URL install.
- Plugin manifests declare permissions.
- Compatibility version validation.
- Future signed plugin registry.
- Subprocesses isolate crashes, not permissions; untrusted plugins stay disabled until OS-enforced access restrictions are tested.
- Crash-loop detection and auto-disable.
- Plugin network/filesystem capabilities explicitly declared.

### Acceptance criteria
- Public plugin ecosystem is not launched until isolation/permission model is implemented.

---

## R-013 — Update supply-chain compromise

**Risk:** Fake/malicious update installs code.

Probability: 2  
Impact: 5  
Score: 10 — High

### Controls
- Signed update metadata.
- SHA-256 or stronger artifact verification.
- TLS.
- Version and schema compatibility check.
- Backup before update.
- Rollback.
- No blind execution of downloaded installers.

### Acceptance criteria
- Tampered package fails validation and is never executed.

---

## R-014 — App crash during print/finalization

**Risk:** Print state or inventory becomes inconsistent.

Probability: 4  
Impact: 4  
Score: 16 — Critical

### Controls
- Durable job state.
- Atomic DB transactions.
- Startup recovery workflow.
- Unfinished job reconciliation.
- Provider reconnect with backoff.
- Finalization idempotency.
- Journaling of significant state transitions.

### Acceptance criteria
- Forced process termination at each finalization step does not cause stock drift after recovery.

---

## R-015 — Printer disconnect/network flap

**Risk:** Reconnect interpreted as a new print or causes false failure.

Probability: 5  
Impact: 3  
Score: 15 — High

### Controls
- Connection-loss state separate from print terminal states.
- Exponential backoff with jitter.
- Stable job identity.
- On reconnect compare current job before creating new job.
- Stale snapshot timestamp.

### Acceptance criteria
- Network disconnect/reconnect during a print keeps a single job record.

---

## R-016 — Conflicting consumption sources

**Risk:** Scale, printer, slicer, and G-code disagree materially.

Probability: 4  
Impact: 4  
Score: 16 — Critical

### Controls
- Preserve every `ConsumptionEvidence`.
- Confidence and source trust model.
- Reconciliation thresholds.
- Audit trail of selected evidence and reason.
- Large discrepancy triggers `NEEDS_RECONCILIATION`.

### Acceptance criteria
- The user can inspect why 131 g was selected instead of 145 g.

---

## R-017 — Negative/physically impossible inventory

**Risk:** Bad import, wrong tare, duplicate event, or manual error produces negative stock.

Probability: 3  
Impact: 4  
Score: 12 — High

### Controls
- Do not silently clamp to zero.
- Mark spool `QUARANTINED/INCONSISTENT`.
- Raise alert.
- Require reconciliation.
- Preserve offending transaction/evidence.

### Acceptance criteria
- Data anomaly remains auditable and cannot silently disappear.

---

## R-018 — Scale error/calibration drift

**Risk:** Bad measurement becomes authoritative.

Probability: 3  
Impact: 4  
Score: 12 — High

### Controls
- calibration records/version
- stability score
- tare profile
- sensor health
- outlier detection
- minimum stable duration
- sanity comparison against previous stock

### Acceptance criteria
- unstable or implausible measurement cannot auto-correct stock.

---

## R-019 — Overly broad first release

**Risk:** Too many integrations cause unstable core and poor test coverage.

Probability: 5  
Impact: 4  
Score: 20 — Critical

### Controls
- Architecture supports breadth, implementation proceeds vertically.
- First production path:
  P1S without AMS → spool assignment → reservation → print lifecycle → consumption → history → weighing correction.
- Additional integrations require provider contract tests.
- Feature flags for experimental modules.

### Acceptance criteria
- MVP release is not blocked by unfinished secondary vendors/features.

---

## R-020 — Server/API exposure

**Risk:** Local desktop API becomes remotely reachable without proper controls.

Probability: 2  
Impact: 5  
Score: 10 — High

### Controls
- localhost-only default
- remote mode explicit opt-in
- authentication
- TLS/reverse proxy requirements
- CORS allowlist
- rate limiting
- audit logging
- no secrets in URL query parameters

### Acceptance criteria
- Fresh install exposes no unauthenticated remote service.

---

## R-021 — Backup corruption or secret leakage

**Risk:** Backup cannot restore or leaks sensitive data.

Probability: 3  
Impact: 4  
Score: 12 — High

### Controls
- consistent SQLite online snapshot and asset manifest; no live main-file-only copying
- checksums
- retention generations
- restore verification tests
- secrets excluded or encrypted
- backup format versioned

### Acceptance criteria
- Automated restore test succeeds for release candidate.

---

## R-022 — Migration failure

**Risk:** App update destroys or leaves DB half-migrated.

Probability: 3  
Impact: 5  
Score: 15 — High

### Controls
- backup before migration
- migrations transactional where supported
- schema version checks
- migrate from every released version in CI
- rollback/recovery flow

### Acceptance criteria
- Upgrade path from every supported prior release is tested.

---

## R-023 — Excessive trust in filename/job name

**Risk:** Same filename gets mistaken for same print and deduped incorrectly, or duplicate print created.

Probability: 4  
Impact: 3  
Score: 12 — High

### Controls
- job identity uses external ID when available
- printer ID
- source
- timestamps
- file hash/project UUID where possible
- filename only as display metadata

### Acceptance criteria
- reprinting same `.3mf` creates a new job while reconnect replay does not.

---

## R-024 — Platform-specific divergence

**Risk:** Windows features work while macOS/Linux break due to hardcoded paths, tray APIs, secret stores, notifications.

Probability: 4  
Impact: 4  
Score: 16 — Critical

### Controls
- platform adapter layer
- `platformdirs`
- CI matrix Windows/Linux/macOS
- shared contract tests
- no OS paths in core
- graceful feature degradation

### Acceptance criteria
- Core test suite and startup smoke test pass on all supported OSes before release.

---

## R-025 — Localization regressions

**Risk:** hardcoded UI text or missing translations break Ukrainian/English support.

Probability: 4  
Impact: 2  
Score: 8 — Medium

### Controls
- no user-visible strings outside i18n resources
- missing-key CI check
- English fallback
- locale-aware plural/date/number formatting

### Acceptance criteria
- CI reports missing/mismatched keys before merge.

---

# Mandatory release blockers

The following risks are release blockers for a public stable build:

- R-001 Vendor isolation
- R-002 Estimated vs measured separation
- R-003 Idempotent finalization
- R-004 Reservation concurrency
- R-005 Partial-print handling
- R-007 Wrong-spool protection
- R-009 Secret storage
- R-010 3MF hardening
- R-012 Plugin safety before public plugins
- R-013 Signed update validation before auto-update
- R-014 Crash recovery
- R-016 Consumption reconciliation
- R-022 Migration safety
- R-024 Cross-platform validation

## Review additions and ownership

All existing risks remain OPEN / unverified until linked execution evidence exists.
Documentation corrections do not mean that runtime controls have been implemented.
Owners below name responsible modules, not invented staff assignments.

| Risks | Accountable module |
|---|---|
| R-001, R-015, R-019, R-023 | application/printing + integrations/printers |
| R-002, R-005, R-006, R-016, R-017, R-018 | application/consumption + domain/policies |
| R-003, R-004, R-007, R-014 | application/accounting + infrastructure/persistence |
| R-008, R-021, R-022 | infrastructure/persistence + infrastructure/backup |
| R-009 | infrastructure/secrets + infrastructure/logging |
| R-010, R-011 | integrations/slicers |
| R-012, R-013 | bootstrap + packaging |
| R-020 | api |
| R-024 | platform + CI |
| R-025 | ui/i18n + CI |

| ID / failure | P x I / level | Owner | Required control and acceptance evidence |
|---|---|---|---|
| R-026 — One physical spool mounted twice | 4 x 5 = 20 Critical | application/feeds + persistence | Two partial unique indexes plus interval guard; simultaneous mounts on two printers yield one success and retained rejection audit |
| R-027 — Measurement and finalization double-account same usage | 4 x 5 = 20 Critical | application/consumption | Absolute-vs-delta scope, ledger cutoff and unresolved-usage gate; post-print reading followed by late completion cannot debit twice |
| R-028 — Out-of-order feeder/event observation changes newer physical state | 4 x 4 = 16 Critical | application/reconciliation | Epoch/sequence/freshness handling; old slot snapshot cannot reopen/replace current mount |
| R-029 — Purge or cumulative evidence counted more than once | 4 x 4 = 16 Critical | domain/consumption | Explicit intervals/scope/purge flag and allocation totals; cumulative samples and inclusive purge produce one authorized total |
| R-030 — Commit succeeds but receipt/notification recovery causes repeat debit | 3 x 5 = 15 High | application/accounting | Unique job finalization, retryable pending receipts and post-commit intents; crash before/after commit recovers without stock drift |
| R-031 — History erased or desynchronized from projection | 3 x 5 = 15 High | persistence | Append-only triggers, ordered ledger, CAS, FK RESTRICT; attempted edits/deletes fail and snapshot rebuild matches |
| R-032 — Independent devices violate global mount/reservation constraints | 4 x 5 = 20 Critical | future sync/server | Multi-device writes disabled until authority/conflict design and partition tests; merging immutable rows alone is insufficient |
| R-033 — Unavailable keyring silently uses insecure fallback | 3 x 5 = 15 High | infrastructure/secrets | Secure-backend allowlist; headless/unavailable OS store disables only affected integration and never writes secret to disk |
| R-034 — Restore overwrites valid newer data after ambiguous failure | 3 x 5 = 15 High | infrastructure/backup | Restore to verified separate target, preserve original, stop writers; crash during switch leaves recoverable originals |
| R-035 — Expiry or correction frees capacity while print still consumes | 4 x 4 = 16 Critical | application/reservations | No automatic active-print expiry; correction shortage task preserves claims; restart/clock jump cannot make material falsely available |

R-026..R-031 and R-033..R-035 block a stable first production vertical where those
features are present. R-032 blocks multi-device writes; disabling that feature
keeps it outside the desktop release scope. R-006, R-008, R-011, R-017, R-018 and
R-021 are also explicit stable-release gates for the corresponding implemented
workflows, not optional merely because omitted from the earlier short list.
R-012/R-013/R-020 gates apply when plugins/updater/API are enabled. An experimental
flag cannot bypass physical identity, ledger integrity or idempotency.

Traceability and planned checks: [TEST_MATRIX](docs/TEST_MATRIX.md).
