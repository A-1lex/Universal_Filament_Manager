# Provider, repository and UnitOfWork contracts

Normative design for the first implementation. The following signatures describe
ports, not working integrations. Domain uses standard-library types only;
Pydantic validation belongs at application/adapter boundaries.

## Common DTO rules

All identifiers are UUID internally. All timestamps are aware UTC. Mass is integer
mg, money finite Decimal, confidence Decimal in [0,1]. DTOs are immutable.
External strings, metadata, collection size and nesting are bounded. Raw vendor
payloads never enter domain entities. A field uses `Observed[T]` with `value`,
`availability`, `observed_at`, `received_at` and optional `reason_code`.
KNOWN requires a value; UNKNOWN/UNAVAILABLE/UNSUPPORTED require no value; STALE
may retain the last value and timestamp but cannot authorize a physical mutation.

| DTO | Required data |
|---|---|
| ProviderHealth | state, checked_at, stable reason_code, retryable |
| PrinterCapabilities | Observed[bool] per capability, schema version |
| PrinterStatusSnapshot | printer_id, connection state, observed/received times, sequence/epoch when available, Observed progress/layers/temperatures, normalized feed snapshot |
| PrintJobSnapshot | source, provider run key if guaranteed, external ID, epoch, exact start observation, project UUID/hash if known, status, progress, timestamps |
| CurrentJobObservation | availability plus optional job; KNOWN + None means confirmed idle, unavailable never means idle |
| FeedSystemSnapshot | stable provider system key, kind, observed slots, sequence/epoch, completeness flag |
| FeedSlotSnapshot | slot key, occupancy knowledge, independent tray_uuid/tag_uid observations, assignment evidence, remaining-mass evidence and optional independent remaining-percent evidence |
| PrinterEvent | provider instance, printer, epoch, event key, kind, normalized job/slot observation, observed/received times, sanitized payload hash |
| WeightReading | sensor, spool association if known, gross/tare/net mg, calibration ID/version, stability, interval, observed/received times |
| SlicerProject | source fingerprint, project reference, plate list, tool/material estimates, units, purge inclusion, warnings and parser version |
| BackupManifest | format/schema/app versions, device, snapshot time, file checksums, lengths; no secret material |

Capabilities include job_detection, progress, layers, temperature, camera, pause,
resume, cancel, filament_usage, multi_material, file_metadata, local_connection,
cloud_connection, push_events, polling. Unsupported and unavailable differ from
known false. Capability changes do not silently change historical assignments.

## Port signatures

```python
class PrinterProvider(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health(self) -> ProviderHealth: ...
    async def get_capabilities(self) -> PrinterCapabilities: ...
    async def get_status(self) -> PrinterStatusSnapshot: ...
    async def get_current_job(self) -> CurrentJobObservation: ...
    def subscribe_events(self) -> AsyncIterator[PrinterEvent]: ...

class PrinterControl(Protocol):
    async def pause(self, job_id: UUID) -> CommandResult: ...
    async def resume(self, job_id: UUID) -> CommandResult: ...
    async def cancel(self, job_id: UUID) -> CommandResult: ...

class SlicerProvider(Protocol):
    def can_parse(self, source: ProjectInput) -> bool: ...
    def parse_project(self, source: ProjectInput, limits: ParseLimits) -> SlicerProject: ...

class ScaleProvider(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health(self) -> ProviderHealth: ...
    async def read(self) -> WeightReading: ...
    async def tare(self) -> TareResult: ...

class SecretStore(Protocol):
    def get(self, credential_ref: str) -> SecretValue: ...
    def put(self, secret: SecretValue) -> str: ...
    def delete(self, credential_ref: str) -> None: ...

class NotificationProvider(Protocol):
    async def send(self, notice: Notification, delivery_key: UUID) -> DeliveryResult: ...

class BackupProvider(Protocol):
    def create(self, destination: BackupDestination) -> BackupManifest: ...
    def verify(self, backup: BackupSource) -> VerificationResult: ...
    def restore(self, backup: BackupSource, target: RestoreTarget) -> RestoreResult: ...

class SyncProvider(Protocol):
    async def exchange(self, request: SyncBatch) -> SyncResult: ...
```

Types are deliberately vendor-neutral; concrete type definitions are Phase 1/2
work. PrinterControl is a separate optional port so monitoring does not acquire
command authority. Slicer ProjectInput is a bounded input abstraction; infrastructure
opens paths. `can_parse` is a format probe, not proof that content is safe.
Weight `tare` changes sensor state only and cannot mutate inventory. SecretValue
must not reveal its content through repr/str/logging. Sync remains disabled until
global conflict authority is designed; this signature alone does not permit sync.

The current-job envelope clarifies the earlier illustrative `Snapshot | None`:
it preserves the required distinction between unknown telemetry and confirmed
idle. The subscription method is a normal def returning an async iterator, whose
implementation may be an async generator. It is consumed directly by `async for`.

Errors: ProviderUnavailable, AuthenticationFailed, UnsupportedCapability,
InvalidObservation, ParseRejected, SecretStoreUnavailable, BackupInvalid. Each has
a stable code, retryability and sanitized contextual identifiers. Cancellation
propagates; adapters use bounded timeouts/backoff and never catch-and-ignore errors.
Reconnect never produces a new run ID from filename alone. Event iteration ends
or raises a typed error; it cannot silently discard an accounting event.

In receipt/alias persistence, `provider` is an immutable provider-instance identity,
not merely a vendor label. Adapter kind/version are separate metadata. Reconfiguring
to a different identity/authentication scope creates a new instance identity;
reconnect to the same instance preserves it. `source_epoch` represents the provider's
validated identity epoch and is never fabricated from local receipt time.

## Application ports and transaction ownership

```python
class SpoolRepository(Protocol):
    def get(self, spool_id: UUID) -> Spool: ...
    def add(self, spool: Spool) -> None: ...
    def save(self, spool: Spool, expected_revision: int) -> None: ...

class LedgerRepository(Protocol):
    def append(self, entry: FilamentTransaction) -> None: ...
    def for_spool(self, spool_id: UUID, after_sequence: int) -> Sequence[FilamentTransaction]: ...

class MountRepository(Protocol):
    def active_for_spool(self, spool_id: UUID) -> SpoolMount | None: ...
    def active_for_slot(self, slot_id: UUID) -> SpoolMount | None: ...
    def add(self, mount: SpoolMount) -> None: ...
    def close(self, mount_id: UUID, at: datetime, expected_revision: int) -> None: ...

class ReservationRepository(Protocol):
    def active_for_spool(self, spool_id: UUID) -> Sequence[Reservation]: ...
    def add(self, reservation: Reservation) -> None: ...
    def save(self, reservation: Reservation, expected_revision: int) -> None: ...

class UnitOfWork(Protocol):
    spools: SpoolRepository
    ledger: LedgerRepository
    mounts: MountRepository
    reservations: ReservationRepository
    jobs: JobRepository
    evidence: EvidenceRepository
    decisions: DecisionRepository
    receipts: ReceiptRepository
    finalizations: FinalizationRepository
    reconciliations: ReconciliationRepository
    audit: AuditRepository
    def __enter__(self) -> Self: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __exit__(self, *exc: object) -> None: ...
```

All repositories in one UoW share the same DB transaction. Context exit without
successful explicit commit rolls back, including exceptions. No nested independent
commit in a repository. Jobs support get/add/CAS-save and validated alias lookup;
evidence/decisions are add/read-only; receipts support get-by-scoped-key,
insert-pending and mark-processed; finalizations support get-by-job and insert
unique initial record. Reconciliations support create and audited resolve;
audit supports append only. Query ports expose immutable read models to UI.

Expected errors: NotFound, RevisionConflict, IdempotencyConflict, AlreadyMounted,
InsufficientAvailableStock, ReconciliationRequired, InvalidTransition,
PersistenceUnavailable. Map DB uniqueness failures to domain errors after rollback.
Retries reopen a UoW and re-read state; they do not reuse a stale balance.
Bounds: at most three contention retries with jitter before surfacing a typed
busy error; never retry uncertain external printer control commands blindly.

A finalization must either persist every required accounting row or none. A
notification failure occurs after commit and cannot change that result. Backup,
network, UI and logging work cannot run under the accounting write lock.
