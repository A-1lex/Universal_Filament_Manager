# Universal Filament Manager — ARCHITECTURE

## 1. Purpose

Universal Filament Manager (UFM) is a cross-platform application for Windows, Linux, and macOS that manages filament inventory, printer integrations, print jobs, consumption, reservations, costs, storage, drying, sensors, alerts, and future multi-user/server workflows.

The first fully supported real-world scenario is Bambu Lab P1S without AMS, but the architecture MUST remain manufacturer-neutral.

The user confirmed a standalone native desktop product on 2026-10-25. Combine
Spoolman inventory and HaspelSync printer/accounting capabilities within UFM's
modules, with PySide6 and UFM-owned SQLite accounting. End-user operation must not
require a browser, Docker, a separately installed Node.js runtime or running
Spoolman/HaspelSync servers. Optional interoperability stays behind adapters.
Extensions use explicit versioned ports and capabilities; third-party plugin
loading remains a separately reviewed implementation phase. See
[standalone desktop plan](docs/STANDALONE_DESKTOP_PLAN_UK.md).

Integration decision ADR-001 (2026-10-27): Python orchestration and the
UFM-owned ledger remain authoritative; reuse HaspelSync pure calculations
through a narrow internally managed Node worker, bundled with the product.
The Python comparison reference is test-only, not a parallel production port.
The current worker is an experimental read-only prototype, not installed or
connected to stock accounting. See [decision and evidence](docs/INTEGRATION_DECISION_UK.md).

Primary principles:

1. Domain logic must not depend on a specific printer brand, slicer, operating system, UI toolkit, database engine, or transport protocol.
2. Integrations are adapters behind explicit interfaces.
3. All inventory mutations are auditable.
4. Estimated values and measured values must never be silently mixed.
5. A print must never consume filament twice.
6. External events must be idempotent.
7. Secrets must never be stored in plaintext.
8. Offline-first operation is mandatory.
9. The application must remain usable when printers, cloud services, sensors, or integrations are unavailable.
10. Every schema change must be migration-safe.

---

## 2. Architectural style

Use a layered modular architecture inspired by Clean Architecture / Hexagonal Architecture:

```text
┌──────────────────────────────────────────────────┐
│                    UI / API                      │
│  PySide6 | REST | WebSocket | CLI | future Web  │
└──────────────────────┬───────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│               Application Layer                  │
│ Commands | Queries | Services | Use Cases        │
└──────────────────────┬───────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│                   Domain Core                    │
│ Entities | Value Objects | Invariants | Events   │
└──────────────────────┬───────────────────────────┘
                       ↑
┌──────────────────────────────────────────────────┐
│          Infrastructure / Integrations           │
│ DB | Bambu | Klipper | OctoPrint | Slicers      │
│ Scale | QR | NFC | OS | Notifications | Backup   │
└──────────────────────────────────────────────────┘
```

Dependencies always point inward.

The Domain Core MUST NOT import:
- PySide6
- SQLAlchemy
- requests/httpx
- paho-mqtt
- OS-specific modules
- Bambu-specific or Klipper-specific SDKs

---

## 3. Repository layout

The canonical target tree and entity ownership map are in
[REPOSITORY_STRUCTURE](docs/REPOSITORY_STRUCTURE.md). Create directories as their
phases begin; planned providers do not imply installed or supported integrations.

Application ports live in application/ports. Domain entities/policies have no
infrastructure or framework imports. Bootstrap owns concrete adapter composition.
SQLite mappings and Alembic revisions live under infrastructure/persistence;
OS adapters under platform; PySide6 under ui. API, PostgreSQL and sync are later
implementation surfaces. The repository includes domain code, SQLite persistence
and partial inventory, topology and reservation workflows. This document specifies
the target architecture, not completed functionality; see
[implementation status](docs/IMPLEMENTATION_STATUS.md) for evidence and open gates.

---
## 4. Core subsystems

### 4.1 Inventory
Responsibilities:
- spool creation
- material catalog
- remaining amount
- storage location
- archival
- transfers
- reservations
- corrections
- stock valuation

### 4.2 Print lifecycle
Responsibilities:
- detect jobs
- identify printer
- identify material source
- reserve filament
- track status
- finalize consumption
- handle cancellation/failure
- prevent duplicate finalization

### 4.3 Consumption Engine
Accepts multiple evidence sources:
- slicer estimate
- 3MF metadata
- G-code estimate
- printer-reported usage
- progress-based estimate
- scale measurement
- manual correction

Outputs:
- selected consumption
- confidence score
- evidence list
- source priority
- reconciliation result

### 4.4 Integration layer
Every external system is behind a port/adapter.

Required ports:
- PrinterProvider
- SlicerProvider
- ScaleProvider
- SecretStore
- NotificationProvider
- BackupProvider
- SyncProvider

### 4.5 Event Bus
Internal domain/application events decouple modules.

Examples:
- PrinterConnected
- PrintDetected
- PrintStarted
- PrintProgressChanged
- PrintCompleted
- PrintFailed
- PrintCancelled
- SpoolActivated
- SpoolWeighed
- FilamentReserved
- FilamentConsumed
- FilamentAdjusted
- AlertRaised

The bus is process-local in desktop mode. Accounting never relies on successful
event delivery. Persist retryable side-effect intents with the accounting commit
when delivery matters; dispatch outside the transaction. A distributed outbox
transport is required before server/distributed mode.

---

## 5. Provider contracts

### PrinterProvider

```python
class PrinterProvider(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health(self) -> ProviderHealth: ...
    async def get_capabilities(self) -> PrinterCapabilities: ...
    async def get_status(self) -> PrinterStatusSnapshot: ...
    async def get_current_job(self) -> CurrentJobObservation: ...
    def subscribe_events(self) -> AsyncIterator[PrinterEvent]: ...
```

The core MUST use normalized snapshots, never vendor payloads directly.
The subscription method returns an async iterator directly (consumed with
`async for`), not a coroutine that returns an iterator. Full DTO, availability,
repository and UnitOfWork contracts: [PROVIDER_CONTRACTS](docs/PROVIDER_CONTRACTS.md).

### SlicerProvider

```python
class SlicerProvider(Protocol):
    def can_parse(self, source: ProjectInput) -> bool: ...
    def parse_project(self, source: ProjectInput, limits: ParseLimits) -> SlicerProject: ...
```

### ScaleProvider

```python
class ScaleProvider(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health(self) -> ProviderHealth: ...
    async def tare(self) -> TareResult: ...
    async def read(self) -> WeightReading: ...
```

---

## 6. Capability model

Avoid brand-based branching.

Example capabilities:

```text
supports_job_detection
supports_progress
supports_layers
supports_temperature
supports_camera
supports_pause
supports_resume
supports_cancel
supports_filament_usage
supports_multi_material
supports_file_metadata
supports_local_connection
supports_cloud_connection
supports_push_events
supports_polling
```

Feature availability is derived from capabilities, not manufacturer names.
Each capability has explicit observation availability. Vendor topology names such
as AMS/MMU describe FeedSystemKind, not a required vendor-specific business branch.

---

## 7. State machines

The canonical transition and enum map is [STATE_MACHINES](docs/STATE_MACHINES.md).
Print status, connection health and accounting finalization are independent.
Failures/cancellations do not require a fictitious successful completion stage.
Terminal observations cannot reopen a job. Reservation expiry must not silently
release material for a running or disconnected unfinished job.

Spool lifecycle is NEW/OPEN/ARCHIVED. Mount state is ACTIVE/CLOSED. Inventory
health is CONSISTENT/QUARANTINED. LOW/EMPTY are derived quantity indicators,
and unknown quantity is neither. These dimensions may coexist.

---

## 8. Data consistency rules

Critical invariants:

1. Known effective stock can be negative only with atomic quarantine, alert and reconciliation; unknown stock remains null.
2. reserved_g >= 0.
3. available_g = effective_remaining_g - active_reservations.
4. A completed reservation can never be consumed twice.
5. A print job has at most one initial FinalizationRecord for its entire lifetime, regardless of event/key count.
6. Every inventory-changing action creates a transaction.
7. Transaction history is append-only.
8. Manual corrections never erase old values.
9. External event identifiers are deduplicated.
10. Vendor timestamps are normalized to UTC internally.
11. User-facing timestamps are rendered in local timezone.
12. Currency amounts use Decimal, never float.
13. Weight calculations use Decimal or carefully controlled integer milligrams.
14. A spool's identity is UUID-based, not name-based.
15. QR/NFC identifies a UUID/reference, never stores secrets.
16. One ACTIVE SpoolMount per physical spool and per FeedSlot; preserve closed history.
17. A known stock projection is reproducible from its ordered append-only ledger.
18. No automatic debit for unresolved identity, scope or evidence eligibility.

---

## 9. Persistence

Desktop v1:
- SQLite
- WAL mode
- foreign keys ON
- busy timeout
- migrations
- scheduled integrity checks
- transactional repositories

Future:
- PostgreSQL for server mode

Recommended logical separation:
- repositories
- unit of work
- migrations
- query models

Schema v1 and its constraints are specified in [SCHEMA_V1](docs/database/SCHEMA_V1.md).
Migration and restore sequencing is in [MIGRATIONS](docs/database/MIGRATIONS.md).
Use SQLAlchemy 2.x and Alembic. SQLite writes use one application writer and
short explicit write transactions; every connection enables foreign_keys and
busy_timeout. Enable WAL for the local file. Cross-process stale edits are
rejected through revision checks. No network calls inside write transactions.
Initial connection settings: foreign_keys=ON, busy_timeout=5000 ms and
synchronous=FULL; verify WAL activation for the local file. Write UoWs acquire
their SQLite write reservation before reading balances (BEGIN IMMEDIATE or an
equivalent tested serialized-writer path). Read-only recovery does not force writes.

Do not let UI execute SQL.

---

## 10. Synchronization model

Local-first is mandatory.

Future multi-device sync needs:
- globally unique IDs
- monotonically tracked revisions
- created_at / updated_at
- tombstones for deletions
- device_id
- conflict detection
- change journal

Conflict policy examples:
- immutable transactions: deduplicate by identity and reconcile intent; never blindly merge stock-changing commands from independent authorities
- spool notes: last-writer-wins initially
- measured weight: retain both observations and reconcile against their ledger cutoff; wall-clock recency cannot choose a balance
- printer configuration: explicit conflict resolution
- secret material: never synced without encryption

Do NOT implement cloud sync by copying the SQLite file between active machines.
Global mount/reservation exclusivity requires a defined authoritative coordinator
before multi-device writes are enabled. Offline conflicting physical operations
cannot be resolved by last-writer-wins. This remains a future design gate.

---

## 11. Internationalization

Initial languages:
- uk-UA
- en-US

Rules:
- no user-visible hardcoded strings outside localization resources
- stable translation keys
- ICU-style pluralization where needed
- locale-aware dates
- locale-aware decimal formatting
- units configurable independently of language
- fallback to English if translation key missing
- CI test for missing keys

Example keys:

```text
app.title
nav.dashboard
nav.spools
printer.status.online
printer.status.offline
print.status.completed
alert.filament_low
spool.remaining
```

---

## 12. Cross-platform rules

Target platforms (release support requires execution evidence on each):
- Windows 10/11
- modern mainstream Linux distributions
- macOS

Platform-specific adapters handle:
- notifications
- autostart
- credential storage
- file locations
- tray integration
- installer/update behavior

Data directories:
- never hardcode `C:\...`
- use OS-standard application data directories
- use platformdirs through platform/common adapters

---

## 13. Security boundaries

Trust zones:

```text
User UI
  ↓
Application Core
  ↓
Local DB
  ↓
Integration adapters
  ↓
LAN / printer / cloud / third-party services
```

All external data is untrusted.

Vendor MQTT/HTTP payloads must be validated before entering the domain.

---

## 14. Plugin architecture

Plugins must not receive unrestricted process access by default.

Long-term plugin manifest should declare:
- plugin id
- version
- compatible core version
- capabilities
- permissions
- network access requirement
- filesystem access requirement

Future plugin isolation may use subprocesses.

Avoid arbitrary `exec()` or dynamic loading of unsigned Python code from the internet.

---

## 15. Observability

Structured logging:
- timestamp
- severity
- subsystem
- event
- printer_id
- spool_id
- job_id
- correlation_id

Never log:
- passwords
- access codes
- tokens
- API keys
- full credential-bearing URLs

Logs must rotate.

Add diagnostics bundle export that redacts secrets.

---

## 16. Backup and recovery

Backup contents:
- database
- settings
- localization overrides
- spool images
- custom profiles

Backup process:
1. coordinate the snapshot boundary and immutable asset manifest
2. use SQLite's online backup API (or fully quiesced DB); checkpoint plus copying
   only the main live WAL database file is not a valid backup algorithm
3. checksum
4. optionally compress
5. retain generations
6. verify restore in tests

Automatic backups:
- before migration
- before update
- daily configurable

---

## 17. API

Future REST API should be versioned:

```text
/api/v1/spools
/api/v1/printers
/api/v1/jobs
/api/v1/transactions
```

Desktop mode binds to localhost only by default.

Remote access requires:
- explicit opt-in
- authentication
- TLS or reverse proxy guidance
- rate limits
- CSRF protection if browser cookies are used

---

## 18. Update strategy

Never self-update blindly.

Required:
- signed release metadata
- version compatibility check
- backup before migration/update
- rollback strategy
- schema compatibility check

---

## 19. ADRs

Important architectural decisions must be documented in `docs/adr/`.

The user has already selected clean architecture, SQLite/PostgreSQL, append-only
inventory, capability providers, local-first, i18n, cross-platform adapters,
external secret storage and idempotent accounting. Correcting documents to these
requirements does not require ten invented ADRs. Record a new ADR only for a
material departure or a new fundamental decision; no such change is needed for
the current consistency corrections. See [review](docs/ARCHITECTURE_REVIEW.md).


---

## 20. Mandatory risk-control architecture

The following mechanisms are required from the first implementation where applicable:

### Idempotency
External printer/cloud/slicer events must be safe to replay.
Every stock-mutating workflow requires an idempotency boundary.

### Reconciliation
The system must model uncertainty explicitly.
Unknown or conflicting data must become a reconciliation state rather than a guessed final value.

### Usage segmentation
A print's material assignment is time-segmented so manual spool swaps and multi-material systems can be represented correctly.

### Degraded mode
If an integration fails, the application continues in a reduced mode:
- inventory still works
- manual spool assignment works
- manual weighing works
- local history remains available

### Feature isolation
Experimental providers/features are guarded by feature flags and may fail without crashing the core.

### Cross-platform abstraction
No OS-specific behavior is called directly from domain/application services.

### Security by default
- no remote API exposure by default
- no plaintext secrets
- no arbitrary plugin execution
- no unsigned blind self-update

### Durable workflow state
Print finalization and inventory mutations must survive process crashes without double-application.
