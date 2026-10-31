# Enum, transition and policy contract

Normative design, 2026-09-10. Implementation is partial; current execution evidence
and remaining gaps are tracked in [implementation status](IMPLEMENTATION_STATUS.md).
All persisted enums reject unknown values at the adapter boundary. A provider's
unknown vendor value maps to an explicit unavailable observation and a diagnostic,
never to a fabricated successful state.

## Orthogonal state dimensions

| Type | Values | Meaning |
|---|---|---|
| SpoolLifecycle | NEW, OPEN, ARCHIVED | Ownership/use lifecycle |
| InventoryHealth | CONSISTENT, QUARANTINED | Whether stock is safe for new reservations |
| StockLevel (derived) | UNKNOWN, NORMAL, LOW, EMPTY | Threshold comparison; negative implies quarantine, not EMPTY |
| FeedSystemKind | EXTERNAL, AMS, AMS_LITE, MMU, IDEX, TOOL_CHANGER, GENERIC | Topology description |
| SlotAssignment | EMPTY, ASSIGNED, ACTIVE_SPOOL_UNKNOWN, NEEDS_RECONCILIATION | Physical assignment knowledge |
| MountState | ACTIVE, CLOSED | Historical installation interval |
| Availability | KNOWN, UNKNOWN, UNAVAILABLE, UNSUPPORTED, STALE | Per-field data quality/availability |
| ConnectionState | DISCONNECTED, CONNECTING, ONLINE, OFFLINE, DEGRADED | Independent of print state |
| ProviderHealthState | HEALTHY, DEGRADED, UNAVAILABLE, UNSUPPORTED | Provider service health |
| PrintStatus | DETECTED, PREPARING, RUNNING, PAUSED, COMPLETING, COMPLETED, FAILED, CANCELLED | Observed job lifecycle |
| FinalizationState | NOT_STARTED, IN_PROGRESS, NEEDS_RECONCILIATION, FINALIZED | Accounting lifecycle |
| ReservationState | PENDING, ACTIVE, CONSUMED, RELEASED, EXPIRED | Availability claim |
| ReceiptState | PENDING, PROCESSED, REJECTED | Durable event processing |
| ReconciliationState | OPEN, IN_REVIEW, RESOLVED, DISMISSED | Resolution workflow |
| EvidenceSource | SCALE, PRINTER, AMS, SLICER, THREE_MF, GCODE, PROGRESS_ESTIMATE, MANUAL | Origin, not automatic trust |
| QuantityKind | CONSUMED_MASS, REMAINING_MASS, LENGTH | Never mix absolute remaining with consumed mass |
| EvidenceMode | DELTA, CUMULATIVE, ABSOLUTE, ESTIMATE | Interpretation within its scope |
| AssignmentSource | MANUAL, QR, NFC, PROVIDER, SCALE_ASSOCIATION | Provenance; weight alone cannot identify a spool |
| Severity | INFO, WARNING, ERROR, CRITICAL | Alerts and reconciliation |
| TransactionType | INITIAL_STOCK, PRINT_CONSUMPTION, PURGE, LOAD, UNLOAD, WASTE, FAILED_PRINT, MANUAL_USE, MEASUREMENT_CORRECTION, TRANSFER_IN, TRANSFER_OUT, RETURN, INVENTORY_ADJUSTMENT | Append-only signed ledger |
| MaterialType | PLA, PETG, ABS, ASA, TPU, PA, PC, PVA, HIPS, PP, PEEK, PEI, CUSTOM | Extensible profile catalog; custom names are data |
| StorageType | ROOM, CABINET, SHELF, DRY_BOX, BIN, OTHER | Hierarchical locations |
| SensorType | SCALE, TEMPERATURE, HUMIDITY, RFID_READER, NFC_READER, CAMERA, OTHER | Future physical adapters |
| ConnectionMode | LOCAL, CLOUD, MANUAL | Explicit transport/configuration intent |

Optional features introduce enums with their migrations rather than storing
unvalidated strings. Quantity indicators are query results, not mutually exclusive
spool lifecycle states. User-visible statuses resolve to uk-UA/en-US keys.

## Print transitions

| From | Allowed next |
|---|---|
| DETECTED | PREPARING, RUNNING, PAUSED, COMPLETING, COMPLETED, FAILED, CANCELLED |
| PREPARING | RUNNING, PAUSED, COMPLETING, COMPLETED, FAILED, CANCELLED |
| RUNNING | PAUSED, COMPLETING, COMPLETED, FAILED, CANCELLED |
| PAUSED | RUNNING, COMPLETING, COMPLETED, FAILED, CANCELLED |
| COMPLETING | COMPLETED, FAILED, CANCELLED |
| COMPLETED / FAILED / CANCELLED | no different print state |

Skipped intermediate states are accepted only from a validated observation of the
same occurrence; late detection may begin after the physical print finished.
Repeated same-state observations are no-op status updates. Conflicting terminal
observations are retained and reconciled, not overwritten. Out-of-order progress
never reopens a terminal job. Progress alone never proves completion or mass use.
Disconnect changes connection state only. Unknown current-job telemetry is distinct
from a known absence of a running job. Neither proves an earlier job failed.

## Finalization transitions

- NOT_STARTED -> IN_PROGRESS only after terminal job identity and required evidence
  are resolved; otherwise -> NEEDS_RECONCILIATION.
- NEEDS_RECONCILIATION -> IN_PROGRESS only after a persisted, auditable resolution.
- IN_PROGRESS -> FINALIZED in the same accounting transaction; rollback restores
  the previously committed state. No durable half-finalized ledger is permitted.
- FINALIZED is terminal. Corrections are separate append-only commands.

The initial FinalizationRecord is unique for the entire job lifetime. Its command
hash covers stable decision inputs and policy version. A duplicate event may have
a different event key, but cannot create another initial debit. Retrying pending
receipts after a crash must still reach this business-level guard.

## Reservations

PENDING -> ACTIVE / RELEASED / EXPIRED. ACTIVE -> CONSUMED / RELEASED / EXPIRED.
Terminal states cannot reactivate. A new reservation gets a new ID.
PENDING has no capacity effect. ACTIVE acquisition checks known healthy available
stock and expected revision under the same writer transaction. No overbooking
override is enabled in v1.

Expiry applies to unused queued reservations after durable UTC expiry. A running,
paused, disconnected unfinished or unresolved job retains its claim; a scheduler
must not release it merely because a clock/deadline passed. Startup recomputes
expiry against persisted time, never a process-local monotonic timestamp.

Standalone manual release of an ACTIVE claim is limited to an unused queued job
(DETECTED/PREPARING, no started_at, NOT_STARTED accounting). Started or terminal
jobs release claims through accounting/reconciliation, not a generic release.
PENDING proposals have no capacity effect and can be cancelled independently.
Resizing an ACTIVE claim uses the same unused-job guard; it cannot free capacity
during unresolved usage. Every resize requires a distinct replacement ID.

Settlement records consumed allocation and released remainder under one
FinalizationRecord. A zero-debit outcome releases the claim. An actual debit may
exceed the reservation: persist actual evidence, reconcile shortage and quarantine
negative stock. Do not increase a debit to match reserved amount. Evidence receipt
alone never consumes a reservation.

One ACTIVE reservation is allowed per spool/material pair. A settlement assigns
each actual segment debit once to that pair; sums of reserved consumption allocations
cannot exceed its actual usage. Active identity/material/amount fields are immutable;
resize/reassignment is an explicit atomic release-and-re-reserve command with a new
capacity check. Terminal settlement fields are immutable. Historical reservations
do not acquire the same debit again.

An eligible zero-consumption decision creates no FilamentTransaction and releases
the reservation; the immutable decision and finalization still record why no mass
was debited. Absence of evidence is never eligible evidence of zero consumption.

## Physical mounting and storage

NEW -> OPEN -> ARCHIVED; NEW -> ARCHIVED is permitted if unused. Archive is blocked
by active mount, reservation or unresolved in-progress usage. Restore from archive
is an explicit audited command after checking identities and stock health.

Mount ACTIVE -> CLOSED only, with unmounted_at >= mounted_at. One active mount per
slot and spool. Closed intervals must not overlap for the same spool or slot.
Slot changes close mount and applicable material segment and create new records
atomically. Material channels on separate tools may overlap in time; segments on
the same logical channel may not. Unknown assignment starts an unresolved segment.

Explicit local slot-change commands require the relevant active material context
when open usage exists. Unknown assignment preserves its unresolved interval and
creates a slot/job reconciliation task. Local unmount/swap commands target an
expected mount identity; unknown assignment checks an expected slot revision.
These preconditions prevent delayed requests from overwriting a newer assignment.

Telemetry freshness is scoped to provider instance/epoch and sequence when
available. Arrival time cannot make an old observation authoritative. Stale,
missing or ambiguous feeder data never unmounts a known spool automatically.
Trusted newer topology is reconciled with local history; conflicting identities
produce NEEDS_RECONCILIATION and preserve both observations.

Once a segment has a ConsumptionDecision, its spool/mount/material/channel and
interval are immutable. Correcting attribution requires an audited command that
compensates the old spool and debits the correct spool atomically, references the
original decision/transactions, and reconciles any shortage. It does not edit the
finalized segment or run a second initial job finalization.

## Evidence eligibility and measurement cutoff

Default policy version `safe-v1` is conservative:

1. Reject for automatic accounting any missing identity, unit, scope, interval,
   stability/calibration requirement or unresolved overlap. Preserve evidence.
2. Compare only evidence covering the same spool/material interval and purge
   scope. Evidence with different scope is not added or compared as a total.
3. Prefer eligible scale delta, then printer actual. Completed-job estimates
   require an explicit enabled estimate policy; default automatic deduction is
   disabled until production gates pass. A completed status is not mass evidence.
4. Failed/cancelled jobs never automatically use the complete slicer estimate.
   Progress approximation is a proposal requiring audited resolution.
5. Proposed discrepancy threshold is `max(5 g, 5% of the larger comparable mass)`;
   zero versus nonzero still uses the absolute tolerance. Store chosen thresholds,
   confidence floor (proposed 0.95), policy version and reason with each decision.
   These are product defaults to validate, not claims of sensor accuracy.
6. Greater discrepancy blocks automatic finalization and creates a task. Manual
   resolution identifies the user/device, evidence, chosen quantity and reason.
7. Never allocate a job total to spools by progress alone. Segment allocations
   must sum exactly to the authorized consumed total. Preserve rounding residual
   explicitly; reject conversions that silently lose milligrams.

Absolute measurements use InventoryEvidence/InventoryReconciliation with a ledger
cutoff. Acceptance requires known tare and stable calibrated reading, no unresolved
physical usage through that cutoff, and a matching spool revision. If a post-print
measurement already covers an unfinalized print, reconcile/finalize its usage
first or explicitly record that its allocation is covered by the correction;
block independent automatic finalization until this is resolved. This prevents
the later job debit being applied a second time. v1 takes the first conservative
path: reject measurement acceptance while covered usage remains unfinalized.

The correction delta is measured net minus effective at the accepted cutoff.
Later consumption advances effective remaining; measured value/time stays intact.
Delayed measurement cannot overwrite newer ledger state. Negative gross/tare or
net, expired calibration, mismatched spool or implausible results create tasks
without accepting the reading. Existing negative computed stock is preserved,
quarantined and repaired only by an explicit reconciliation transaction.

## Other workflow transitions

- Receipt PENDING -> PROCESSED with successful business commit, or -> REJECTED
  for permanent validation failure. Temporary errors leave it PENDING for bounded
  backoff/retry. Same key plus different payload hash creates a conflict.
- Reconciliation OPEN -> IN_REVIEW -> RESOLVED / DISMISSED; OPEN may resolve
  directly through a valid command. Resolution/dismissal requires reason and actor.
  Dismissal alone does not clear quarantine or authorize a debit.
- Health CONSISTENT -> QUARANTINED with an anomaly; -> CONSISTENT only after
  reconciliation validates ledger, reservations and unresolved physical usage.
- Provider connect/disconnect is idempotent. Reconnect uses capped exponential
  backoff with jitter, cancellation and a monotonic retry timer, independent of
  print lifecycle. Credential or permanent validation errors do not retry forever.
