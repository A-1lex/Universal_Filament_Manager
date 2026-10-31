# Architecture consistency review

Historical design review, not a current implementation report. Statements below
describe the repository on 2026-09-10. See [implementation status](IMPLEMENTATION_STATUS.md)
for subsequent code, execution evidence and remaining gates.

Reviewed: 2026-09-10. Inputs: the five supplied source-of-truth documents and the
user specification, sections 1–62. There was no source code, database, migration,
test suite or Git metadata in the project directory at review start.

Outcome: the original documents contained release-critical design contradictions.
The corrections below align them with the user's chosen architecture; they do not
establish that a production implementation exists or that runtime risks are closed.

## Findings and resolutions

| ID / severity | Original evidence | Failure mode | Resolution / authoritative location | Planned verification |
|---|---|---|---|---|
| A-01 Critical | DOMAIN_MODEL §2.3 `active_spool_id`; absent feeder entities vs user §§4–7 | Same physical spool could be assigned to multiple printers; no mount history | Remove printer field; introduce system/slot/mount plus two partial unique indexes; DOMAIN_MODEL §23, SCHEMA_V1 | T-005,006,007,037 |
| A-02 Critical | DOMAIN_MODEL §20 UNIQUE(job,key); ARCHITECTURE §8 only one active record | Different keys debit same job twice | UNIQUE(job) for lifetime initial finalization and independent UNIQUE(key); compensation afterward | T-001,013 |
| A-03 Critical | DOMAIN_MODEL §6 atomicity “where possible”, notify inside sequence | Half-applied stock/reservation/job or repeated debit after delivery failure | One mandatory accounting UoW; durable pending receipt and post-commit side effects | T-002,036 |
| A-04 High | DOMAIN_MODEL §2.5 external ID tuple unique vs §12 start-time bucket | Reused IDs merge reprints, or reconnect creates duplicates | Internal run UUID, guaranteed scoped occurrence aliases; ambiguity blocks debit | T-003,014 |
| A-05 Critical | DOMAIN_MODEL §§2.1,5,11 leave scale absolute/delta undefined | Post-print weighing and delayed completion charge same use twice | InventoryEvidence separate; ledger cutoff and unresolved-usage acceptance gate; STATE_MACHINES | T-017,018 |
| A-06 Critical | DOMAIN_MODEL §§2.6,2.10,7,19 material has one spool and one decision | Mid-print swap allocates all usage to one spool | Logical material channels; physical segments; per-segment decisions and evidence links | T-008,038 |
| A-07 High | ARCHITECTURE §7 linear print/reservation diagrams; SECURITY §3 connection-lost job | Cannot record skipped states, cancellation or safe disconnected reservations | Orthogonal print/connection/finalization; explicit transitions and expiry guards | T-004,026,032 |
| A-08 High | ARCHITECTURE spool states mix NEW/ACTIVE/LOW/QUARANTINED | Mutually exclusive status hides simultaneous properties | Separate lifecycle, mounting, stock health, derived level, observation availability | T-007,009,025 |
| A-09 Critical | IMPLEMENTATION_PLAN UI Phase4, automatic deduction Phase5, engine Phase7 vs user §56 | Accounting safety arrives after consumers | Restore canonical Phase0–19+; headless kernel/replay/crash gate before UI | Plan heading/order check; T-001,002 before Phase7 |
| A-10 High | Ledger previous/new fields without sequencing/unknown-opening rules | Projection drift, float loss, unknown treated as zero | Integer mg, canonical Decimal money, ordered immutable ledger, explicit opening basis | T-022,025 |
| A-11 High | Reservation correspondence “exactly one action”; no remainder or overrun semantics | Reserved amount mistaken for actual debit; freed running capacity | Finalization settlement, atomic capacity/CAS, shortage and active-print expiry guards | T-015,032 |
| A-12 High | Scale priority without comparable interval/purge/cumulative semantics; AMS source absent | Incompatible evidence added; purge/cumulative use duplicated | Explicit quantity/mode/scope/policy, AMS origin, evidence preservation | T-016,019,020 |
| A-13 High | ARCHITECTURE §10 “newest trusted measurement wins”, “immutable transactions: merge” | Clock drift and independent devices break physical constraints | Remove automatic merge prescriptions; gate distributed writes on authority design | T-017,035 |
| A-14 High | Backup checkpoint/snapshot ambiguity; SECURITY auto-restore after failed migration | WAL data lost or newer user data overwritten | Online consistent backup, separate verified restore target, preserve originals | T-023,024 |
| A-15 High | Secret vault fallback unspecified; plugin subprocess treated as sandbox | Insecure keyring fallback or unrestricted untrusted code | Fail closed on insecure keyring; defer vault; OS-enforced plugin permissions required | T-028,035 |
| A-16 Medium | PrinterProvider illustrative async subscription and optional current-job result | Coroutine/iterator mismatch; unavailable mistaken for idle | Direct async-iterator return; explicit CurrentJobObservation envelope | Provider contracts and Phase1 type/contract checks |
| A-17 High | No temporal ordering/interval guard for feed snapshots | Stale AMS update steals/reopens mount or missing slot treated empty | Epoch/sequence/freshness and historical overlap guards | T-006,021,037 |
| A-18 High | No explicit deletion/transfer/currency/cross-reference invariants | History loss, mass creation on location move, wrong-job decision | RESTRICT FKs, append-only guards, cycle/transfer and scope validation | T-027,034,038 |
| A-19 Medium | Existing high/critical risks lack owner/status; updater gate unconditional | Controls appear complete merely because documented; disabled features block desktop | Module owners, OPEN status, scoped release gates and R-026..035 | Risk-to-test matrix review |

## Fundamental decisions and ADR outcome

No new ADR is required for these corrections. Clean/hexagonal architecture,
SQLite desktop/PostgreSQL future server, append-only inventory, provider capabilities,
physical feed topology, exact units and atomic idempotent accounting were already
explicit user decisions. Correcting contradictory documents implements that contract.

The previous list of ten “initial ADRs” described existing choices but pointed to
no actual decision records. It is replaced by the rule to create ADRs only for a
new fundamental choice or a material change. A multi-device authority model, plugin
sandbox architecture or encrypted vault would require future design/ADR work before
implementation. No provider-specific protocol behavior is claimed verified here.

## Required design outputs

| User §62 item | Artifact / result |
|---|---|
| 1. Contradictions | Findings A-01..A-19 above; five original documents corrected |
| 2. Missing invariants | DOMAIN_MODEL §§23–24; STATE_MACHINES; SCHEMA_V1 constraints |
| 3. Uncovered risks | RISK_REGISTER R-026..R-035 with owners and acceptance evidence |
| 4. ADR only if needed | No departure required; rationale above |
| 5. Repository structure | [REPOSITORY_STRUCTURE](REPOSITORY_STRUCTURE.md) |
| 6. Entity map | Entity ownership table and relationship diagrams in REPOSITORY_STRUCTURE and DOMAIN_MODEL |
| 7. Enum/state machines | [STATE_MACHINES](STATE_MACHINES.md) |
| 8. Provider interfaces | [PROVIDER_CONTRACTS](PROVIDER_CONTRACTS.md), including UoW and repository ports |
| 9. Schema v1 | [SCHEMA_V1](database/SCHEMA_V1.md), typed logical schema; executable Alembic DDL remains Phase2 |
| 10. Constraints/indexes | SCHEMA_V1 UNIQUE, FK, CHECK/guard and query-index catalogs |
| 11. Migration strategy | [MIGRATIONS](database/MIGRATIONS.md) |
| 12. Test matrix | [TEST_MATRIX](TEST_MATRIX.md), T-001..T-042 |
| 13. Code only after review | No application implementation included in this document correction |

## Remaining implementation and validation gates

- The logical schema needs executable SQLAlchemy mappings/Alembic revisions with
  actual SQLite constraint/concurrency/crash tests. Do not advertise a working DB.
- `safe-v1` thresholds and parser budgets are explicit proposed conservative
  product defaults, requiring fixture/hardware validation. They are not vendor or
  sensor accuracy guarantees.
- P1S connection, firmware fields, tray/tag semantics, job identity and TLS behavior
  need real recorded fixtures and hardware verification during adapter work.
- OS credential backends, GUI behavior and packaging require all three OS CI jobs.
- Real automatic deduction remains disabled until the full production gates pass.

## Review verification

Independent follow-up review also resolved seven contract ambiguities: legacy
material/profile/evidence fields, finalized-segment immutability, active-reservation
immutability, allocation across claims, reproducible estimate projection,
zero-consumption finalization and immutable provider-instance identity. Cases
T-039..T-042 extend the acceptance matrix for these guards.

All five source documents were read in UTF-8, reviewed against the supplied request,
and checked independently for core accounting contradictions. Local structural
checks cover relative documentation links, Markdown code fences, phase ordering,
test/risk identifiers and removed unsafe prescriptions. These checks validate the
documents only; implementation tests remain unexecuted.

Fresh structural verification: 14 Markdown documents, all local links resolved,
20 phase headings in exact order 0..19+, 42 unique planned test IDs, balanced code
fences and no remaining authoritative legacy active_spool_id/profile FK/single
evidence field or optional accounting-atomicity prescription. PowerShell validation
completed with exit code 0. Follow-up edits were rechecked before handoff.

Environment probe: `py -0p` reports `No installed Pythons found!`; `python` and
`git` are not available on PATH. This does not affect document review, but Python
3.12+ must be available before executing the planned implementation checks.
