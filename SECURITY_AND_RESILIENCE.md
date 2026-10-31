# Universal Filament Manager — SECURITY_AND_RESILIENCE

## 1. Threat model summary

Assets to protect:
- printer access codes
- API tokens
- cloud credentials
- local inventory data
- print history
- customer/project data
- plugin/update trust
- backups

Potential attackers/failure sources:
- malicious LAN device
- compromised printer/cloud account
- malformed 3MF/G-code
- malicious plugin
- poisoned update
- local malware
- accidental user action
- database corruption
- duplicate external events
- race conditions
- clock drift
- network partitions

---

## 2. Highest-risk vulnerabilities in the proposed system

### 2.1 Duplicate consumption
Risk:
Printer sends completion twice, reconnect replay occurs, or multiple workers finalize same job.

Impact:
Filament deducted twice.

Mitigation:
- external event dedupe key
- unique constraint on finalization
- idempotency token
- transactional finalization
- job row locking or optimistic concurrency
- one initial FinalizationRecord per job plus independent unique command key

This is one of the most important logical protections.

---

### 2.2 Race condition on spool balance
Risk:
Two jobs reserve or consume the same spool concurrently.

Impact:
available amount becomes invalid.

Mitigation:
- transaction boundary
- optimistic revision number
- compare-and-swap update
- active reservation query inside same transaction
- retry on conflict

---

### 2.3 Silent source conflict
Risk:
3MF says 120 g, printer says 145 g, scale says 131 g.

Impact:
incorrect remaining filament.

Mitigation:
- retain all evidence
- define trust policy
- detect discrepancy threshold
- flag reconciliation
- never silently discard conflicting measurements

---

### 2.4 Partial print accounting
Risk:
Cancelled at 68% but system deducts entire slicer estimate.

Mitigation:
- terminal state aware policy
- actual printer usage if available
- scale delta
- progress estimate as fallback
- user confirmation above configurable uncertainty

---

### 2.5 Spool swap during print
Risk:
User changes spool manually.

Impact:
all usage charged to wrong spool.

Mitigation:
- usage segments
- spool-change event if available
- manual split UI
- post-print reconciliation

---

### 2.6 Plaintext secrets
Risk:
access code/token in SQLite/logs/config.

Mitigation:
- OS credential stores
- Windows Credential Manager / DPAPI
- macOS Keychain
- Linux Secret Service/libsecret
- no plaintext keyring fallback; if a verified OS backend is unavailable, disable
  credential-dependent integration while keeping manual inventory usable
- a custom encrypted vault is deferred until separately designed and reviewed
- redacted logs

---

### 2.7 Insecure localhost API exposure
Risk:
server accidentally binds to 0.0.0.0 without auth.

Mitigation:
- localhost-only default
- explicit remote enable
- generated auth token
- TLS/reverse proxy guidance
- firewall warning
- CORS restrictions
- rate limiting

---

### 2.8 Malicious 3MF/ZIP
3MF is ZIP-based.

Risks:
- zip bomb
- path traversal
- huge XML
- malformed metadata

Mitigation:
- max archive size
- max extracted size
- max file count
- reject `..` paths
- parse in memory/temporary sandbox
- XML parser with external entity expansion disabled
- timeout / size limits

---

### 2.9 Malicious G-code
Risk:
parser assumes arbitrary lines are safe or executes content.

Mitigation:
- never execute G-code during parsing
- strict text-only parser
- size limits
- streaming parser
- treat comments as untrusted text
- no shell interpolation

---

### 2.10 Plugin supply-chain attack
Risk:
third-party plugin gains unrestricted Python access.

Mitigation:
- no auto-install from arbitrary URLs
- signed/verified plugin registry if introduced
- permission manifest
- compatibility validation
- subprocess crash isolation alone is not a security sandbox; untrusted plugin
  execution remains disabled until OS-enforced filesystem/network/process
  restrictions and permission enforcement are implemented and tested
- disable by default after crash loops
- plugin audit logs

---

### 2.11 Update supply-chain attack
Mitigation:
- signed manifests/releases
- hash verification
- HTTPS
- rollback
- staged update
- never run downloaded executable before verification

---

### 2.12 Backup leakage
Backups can contain sensitive configuration.

Mitigation:
- exclude plaintext secrets
- optional backup encryption
- explicit export warning
- checksums
- retention controls

---

## 3. Resilience design

### Printer offline
Expected behavior:
- UI shows stale timestamp
- inventory remains usable
- connection state OFFLINE/DEGRADED and stale timestamp; preserve PrintJob status
- reconnect with backoff
- reconcile current job after reconnect

### Application crash during print
On restart:
1. restore unfinished jobs
2. reconnect providers
3. compare printer current job
4. reconcile states
5. do not finalize until certainty is sufficient

### Crash during finalization
Use one DB transaction so either:
- all consumption/finalization commits
or
- none commits

### Database corruption
- daily backup
- integrity_check
- startup recovery path
- never overwrite last known good backup

### Disk full
- detect write failure
- stop destructive inventory mutation
- show critical alert
- keep printer monitor read-only if possible

### System clock changes
Use UTC timestamps and monotonic clocks for durations where practical.

### Network flap
Use exponential backoff with jitter.
Do not create a new job just because connection re-established.

---

## 4. Authentication and authorization

Desktop single-user v1:
- local OS trust
- no mandatory app password

Server/multi-user future:
roles:
- Admin
- Operator
- Viewer

Permissions:
- manage printers
- manage credentials
- edit inventory
- finalize/correct consumption
- manage users
- view costs
- configure integrations

---

## 5. Auditability

High-risk actions require audit records:
- manual stock correction
- transaction reversal
- printer credential change
- backup restore
- data import
- plugin install/update
- remote API enablement

---

## 6. Validation rules

All external input must be schema-validated.

Examples:
- weight cannot be NaN/Infinity
- negative purchase price invalid
- diameter must be within reasonable bounds
- temperatures bounded to sane configured ranges
- IP/host fields sanitized
- file paths normalized
- color hex validated
- enum values explicit

---

## 7. Privacy

Default:
- local-only storage
- no telemetry unless opt-in
- no cloud dependency for core inventory
- diagnostics export must be redacted

If telemetry is introduced:
- explicit consent
- documented fields
- easy disable
- no print filenames or personal project names by default

---

## 8. Logging policy

Levels:
DEBUG / INFO / WARNING / ERROR / CRITICAL

Redaction filters:
- tokens
- passwords
- access codes
- Authorization headers
- cloud session data

User-facing logs should be localized only in UI.
Internal technical event codes should remain stable English identifiers for diagnostics.

---

## 9. Failure-mode table

| Failure | Expected response |
|---|---|
| Printer disconnects | mark stale, reconnect, preserve job |
| Duplicate completion event | ignore duplicate |
| DB locked | retry bounded, surface error |
| DB corrupt | switch to recovery workflow |
| Negative computed stock | quarantine spool |
| Scale unstable | reject/flag reading |
| Slicer parse failure | keep job, mark estimate unavailable |
| Cloud unavailable | local mode continues |
| Secret store unavailable | disable affected integration |
| Plugin crashes | isolate/disable plugin |
| Update fails | rollback |
| Migration fails | stop writers, preserve failed DB and verify recovery copy before an explicit restore |
| Disk full | stop writes, alert |
| Conflicting spool assignment | request reconciliation |

---

## 10. Testing requirements

### Unit tests
- calculations
- state transitions
- reconciliation policies
- reservation logic
- cost logic
- validation

### Integration tests
- SQLite repositories
- migrations
- printer adapters with recorded fixtures
- 3MF/G-code parsers
- secret stores

### Contract tests
Every PrinterProvider implementation must pass the same contract suite.

### Property-based tests
Highly recommended for:
- transaction balances
- reservation invariants
- random state transitions
- unit conversions

### Migration tests
Test upgrading from every released schema version to latest.

### Crash consistency tests
Simulate interruption at:
- after reservation
- before consumption commit
- during migration
- during backup restore

### Security tests
- zip slip
- zip bomb limits
- malformed XML
- path traversal
- API auth bypass attempts
- secret redaction

---

## 11. Security gates before public release

Must-have:
- secrets not plaintext
- API localhost-only by default
- signed update process when automatic updates are included; otherwise updater disabled
- dependency vulnerability scanning
- reproducible or documented builds
- SBOM generation
- backup/restore tested
- no arbitrary plugin execution
- parser fuzzing or malformed corpus tests
- diagnostics redaction


---

## 12. Risk register governance

`RISK_REGISTER.md` is normative for release decisions.

Rules:
- Every Critical/High risk must have an owner/module.
- New integrations require risk assessment before production enablement.
- A risk is not considered mitigated only because code exists; automated tests and acceptance criteria are required.
- Critical unresolved release blockers prevent a Stable release.
- Experimental builds may expose unfinished controls only behind explicit feature flags and clear UI labeling.

## 13. Boundary controls clarified by the consistency review

- Unknown evidence never authorizes a debit, even under an experimental flag.
  Core inventory integrity controls cannot be bypassed by feature flags.
- Receipts and immutable decisions store sanitized, allowlisted metadata. Do not
  persist raw credential-bearing payloads in DB, logs, fixtures or diagnostics.
  Redact nested structures, exception text, traceback formatting and URLs before
  any output sink. Prefer stable error codes over raw provider exception bodies.
- Keyring backend selection must verify secure OS storage and fail closed. Linux
  headless/no-session operation must not silently select a plaintext backend.
- TLS validation is enabled. A printer requiring a private certificate needs an
  explicit trust/pinning setup; do not disable verification silently.
- 3MF validation checks both slash forms, drive/UNC/absolute paths, dot segments,
  symlinks, duplicate normalized names, actual decompressed bytes, entry count,
  compression ratio and bounded XML. Reject DTD/entity declarations; reject
  archive/XML budget exhaustion. Prefer bounded reads without extraction.
- G-code readers bound both file and line sizes and honor cancellation/time
  limits. Invalid encoding or malformed quantities fail as typed parse errors.
- Safe defaults proposed for parser implementation: 256 MiB input, 512 MiB total
  decompressed bytes, 4096 entries, 16 MiB per XML, 100:1 expansion limit,
  1 MiB line length, 30 s work deadline. Make limits explicit configuration;
  exceeding a limit rejects parsing without inventory mutation.
- Backups use a consistent SQLite snapshot, versioned manifest and checksums for
  every asset. Restore validates into a new private directory/database, checks
  integrity and FKs, then switches with writers stopped. Keep the original and
  last known-good backup. Never automatically overwrite newer user data after
  an ambiguous migration failure.
- Same-host hostile code running as the user is outside the credential-store
  protection boundary. This does not justify exposing secrets in normal output.
- Security/parser/API tests are release gates for those implemented features;
  listing a control in this document is not evidence that it has been implemented.
