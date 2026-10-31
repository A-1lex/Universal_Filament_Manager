# Database schema v1 — logical implementation contract

Status: reviewed design, not an applied migration. Desktop SQLite, SQLAlchemy 2.x,
Alembic. The first migration implements this core; later feature-specific schema
changes use new revisions. This document is not a claim of an existing database.

## Types and common columns

`ID` = canonical UUID TEXT primary key, validated by the application; `REF` = same
type with a declared FK. `I` = signed 64-bit INTEGER with typeof check for exact
mass/count fields (reject bool at the DTO boundary). `D` = canonical finite decimal
TEXT, validated by Decimal at the application boundary; no SQL REAL arithmetic.
`T` = fixed-width ISO 8601 UTC TEXT with Z; `S` = bounded TEXT; `B` = INTEGER 0/1;
`J` = bounded, schema-validated JSON TEXT. `?` marks nullable. Everything else is
NOT NULL. Money aggregation uses Decimal, not SUM(CAST(text AS REAL)).

Every mutable entity includes `id ID`, `device_id REF(device_identity)`,
`created_at T`, `updated_at T`, `revision I >= 1`, `deleted_at T?` (tombstone).
History-bearing rows cannot be tombstoned through normal operations. Every
immutable row includes `id ID`, `device_id REF`, `created_at T`. DeviceIdentity
itself has id, name S, public_id S UNIQUE, created_at T and last_seen_at T?.
The table definitions below add their specific columns to these common columns.
Enums use named CHECK lists from [STATE_MACHINES](../STATE_MACHINES.md).
All FKs default to ON DELETE RESTRICT / ON UPDATE RESTRICT. No cascade deletes.

Numeric bounds: masses/deltas are integer mg within ±9,000,000,000,000,000 mg,
keeping sums within signed 64-bit bounds with explicit overflow rejection.
Unsigned physical input fields require >=0 (diameter/density >0). Confidence is
an integer 0..10000 basis-point score in persistence. Percent uses 0..10000 basis
points. Currency is a three-letter uppercase code validated against the configured
currency catalog; display locale never changes stored units/currency.

## Catalog, devices and physical topology

| Table | Specific columns |
|---|---|
| brand | name S |
| filament_profile | brand_id REF(brand)?, name S, product_line S?, material_type enum, custom_material_name S?, subtype S?, diameter_mm D, density_g_cm3 D?, nozzle_min_c D?, nozzle_max_c D?, bed_min_c D?, bed_max_c D?, chamber_min_c D?, chamber_max_c D?, max_volumetric_speed_mm3_s D?, drying_temp_c D?, drying_duration_min I?, abrasive B?, flexible B?, hygroscopic B?, soluble B?, filled_material B?, default_color_name S?, notes S? |
| storage_location | parent_id REF(storage_location)?, name S, type enum, description S?, temperature_sensor_id REF(sensor_device)?, humidity_sensor_id REF(sensor_device)? |
| spool | display_name S, brand_id REF(brand)?, filament_profile_id REF(filament_profile), product_line S?, batch_number S?, lot_number S?, color_name S?, color_hex S?, secondary_color_hex S?, diameter_mm D, density_g_cm3 D?, nominal_filament_mg I?, empty_spool_mg I?, estimated_remaining_mg I?, measured_remaining_mg I?, effective_remaining_mg I?, measured_at T?, measured_evidence_id REF(inventory_evidence)?, ledger_sequence I DEFAULT 0, purchase_price D?, currency S?, purchase_date S?, opened_at T?, manufactured_at T?, expires_at T?, storage_location_id REF(storage_location)?, lifecycle enum, inventory_health enum, low_threshold_mg I?, low_threshold_bp I?, image_uri S?, notes S?, archived_at T? |
| spool_identifier | spool_id REF(spool), namespace S, kind S, value S, verified_at T?, retired_at T? |
| printer | name S, manufacturer S?, model S?, serial_number S?, enabled B, default_slicer_key S?, nozzle_diameter_mm D?, build_x_mm D?, build_y_mm D?, build_z_mm D?, has_enclosure B?, has_camera B?, has_filament_sensor B?, has_multi_material_system B?, firmware_version S?, last_seen_at T? |
| connection_profile | printer_id REF(printer), provider_type S, connection_mode enum, host S?, port I?, tls_enabled B, credential_ref S?, cloud_account_ref S?, extra_config_json J |
| material_feed_system | printer_id REF(printer), provider_system_key S?, kind enum, name S |
| feed_slot | feed_system_id REF(material_feed_system), slot_key S, tool_index I?, assignment_state enum, observed_at T?, received_at T?, source_epoch S?, source_sequence I? |
| spool_mount | feed_slot_id REF(feed_slot), spool_id REF(spool), state enum, mounted_at T, unmounted_at T?, assignment_source enum, confidence_bp I, source_receipt_id REF(external_event_receipt)? |
| sensor_device | name S, device_type enum, provider_type S, connection_config_ref S?, enabled B, last_seen_at T?, metadata_json J |
| calibration_record (immutable) | sensor_id REF(sensor_device), version I, calibration_type S, reference_value D, reference_unit S, offset D, scale_factor D, temperature_c D?, performed_at T, expires_at T?, notes S? |

Spool QR/NFC are query projections of spool_identifier rows (`kind=QR/NFC`), not
additional competing identity columns. Bambu `tray_uuid`/`tag_uid` use separate
kinds and provider namespaces. Empty/all-zero/unverified tag values remain
observations rather than identifier bindings. Profile-derived physical values are
copied with provenance into the spool when needed; profile edits do not rewrite
historical calculations. reserved_mg and available_mg are query projections from
ACTIVE reservations and effective_remaining_mg, never editable spool columns.

Printer has no active_spool_id. ConnectionProfile is the single direction of the
one-to-one FK (UNIQUE printer_id), eliminating a reciprocal printer/profile FK.
Current printer state/capabilities are normalized observations, not authoritative
inventory fields. If retained, they are bounded cache rows with explicit freshness.

## Printing, evidence and accounting

| Table | Specific columns |
|---|---|
| project | name S, description S? |
| print_job | printer_id REF(printer), project_id REF(project)?, external_job_id S?, name S?, file_name S?, file_hash S?, plate_name S?, source_type S, slicer_type S?, status enum, finalization_state enum, detected_at T, started_at T?, paused_at T?, completed_at T?, failed_at T?, cancelled_at T?, estimated_duration_sec I?, actual_duration_sec I?, progress_bp I?, current_layer I?, total_layers I?, thumbnail_uri S?, failure_code S?, failure_reason S? |
| job_identity_alias (immutable) | print_job_id REF(print_job), provider S, printer_id REF(printer), source_type S, source_epoch S, occurrence_key S, external_job_id S?, started_at T?, file_hash S?, project_reference S? |
| print_job_material | print_job_id REF(print_job), channel_key S, tool_index I, extruder_index I?, filament_profile_id REF(filament_profile)?, estimated_mg I?, estimated_length_mm I? |
| material_usage_segment | print_job_material_id REF(print_job_material), feed_slot_id REF(feed_slot)?, spool_mount_id REF(spool_mount)?, spool_id REF(spool)?, tool_index I, assignment_state enum, started_at T, ended_at T?, estimated_usage_mg I?, source S, confidence_bp I |
| reservation | spool_id REF(spool), print_job_material_id REF(print_job_material), reserved_mg I, status enum, activated_at T?, consumed_at T?, released_at T?, expires_at T?, settled_finalization_id REF(finalization_record)?, allocated_consumption_mg I?, released_mg I?, reason S? |
| external_event_receipt | provider S, printer_id REF(printer), source_epoch S, event_key S, event_type S, payload_hash S, received_at T, processed_at T?, processing_result enum, reason_code S?, sanitized_metadata J |
| consumption_evidence (immutable) | print_job_material_id REF(print_job_material), segment_id REF(material_usage_segment)?, source_type enum, quantity_kind enum, mode enum, weight_mg I?, length_mm I?, confidence_bp I, captured_at T, received_at T, interval_start T?, interval_end T?, scope_key S, includes_purge B?, calibration_id REF(calibration_record)?, source_receipt_id REF(external_event_receipt)?, external_reference S?, metadata_json J |
| inventory_evidence (immutable) | spool_id REF(spool), sensor_id REF(sensor_device)?, calibration_id REF(calibration_record)?, gross_mg I?, tare_mg I?, net_mg I?, captured_at T, received_at T, stability_bp I?, stable_duration_ms I?, ledger_cutoff I?, source_type enum, external_reference S?, metadata_json J |
| finalization_record (immutable on commit) | print_job_id REF(print_job), idempotency_key S, request_hash S, started_at T, completed_at T, result_hash S |
| consumption_decision (immutable) | finalization_record_id REF(finalization_record), material_usage_segment_id REF(material_usage_segment), selected_weight_mg I, confidence_bp I, strategy S, policy_version S, policy_parameters J, reason_code S, reason_notes S?, resolved_by_device_id REF(device_identity)?, finalized_at T |
| decision_evidence (immutable link) | decision_id REF(consumption_decision), evidence_id REF(consumption_evidence), role S |
| inventory_reconciliation (immutable) | spool_id REF(spool), evidence_id REF(inventory_evidence), accepted_ledger_cutoff I, previous_effective_mg I?, accepted_remaining_mg I, estimated_before_mg I?, estimated_after_mg I?, policy_version S, reason S, actor_device_id REF(device_identity) |
| filament_transaction (immutable) | spool_id REF(spool), sequence I, transaction_type enum, delta_mg I, previous_effective_mg I?, new_effective_mg I, command_key S, command_item I, print_job_id REF(print_job)?, decision_id REF(consumption_decision)?, reservation_id REF(reservation)?, inventory_reconciliation_id REF(inventory_reconciliation)?, compensates_transaction_id REF(filament_transaction)?, transfer_id REF(material_transfer)?, source_type S, source_receipt_id REF(external_event_receipt)?, confidence_bp I, unit_cost D?, currency S?, description S?, metadata_json J |
| material_transfer (immutable) | from_spool_id REF(spool), to_spool_id REF(spool), weight_mg I, command_key S, reason S |
| reconciliation_task | spool_id REF(spool)?, print_job_id REF(print_job)?, feed_slot_id REF(feed_slot)?, reason_code S, severity enum, status enum, dedupe_key S, suggested_action S?, resolved_at T?, resolved_by REF(device_identity)?, resolution_notes S? |
| alert_event | reconciliation_task_id REF(reconciliation_task)?, spool_id REF(spool)?, print_job_id REF(print_job)?, severity enum, message_key S, message_params_json J, dedupe_key S, raised_at T, acknowledged_at T?, resolved_at T? |
| audit_event (immutable) | event_code S, actor_device_id REF(device_identity), correlation_id S, entity_type S, entity_id S, parameters_json J |
| pending_effect | event_key S, effect_type S, payload_json J, state S, attempts I, next_attempt_at T?, delivered_at T? |

Material rows represent logical channels, not a fixed spool. Actual weight/cost are
decision/ledger query results per segment. An unresolved segment cannot have a
ConsumptionDecision. `decision_evidence` supports multiple observations (such as
paired measurements); no single selected_evidence_id is treated as the full audit.
Consumed mass derived from a scale pair retains references to both inventory
readings in a dedicated immutable `consumption_inventory_evidence` link
(`id`, origin/time, consumption_evidence_id FK, inventory_evidence_id FK, role),
UNIQUE(consumption_evidence_id, inventory_evidence_id, role).

ConsumptionEvidence quantity_kind is restricted to CONSUMED_MASS or LENGTH;
absolute REMAINING_MASS readings belong to InventoryEvidence. A derived scale
consumption delta references its input readings with the immutable link above.

FilamentTransaction is the signed effective balance ledger, not the raw evidence
store. Its first INITIAL_STOCK establishes a balance; previous may be NULL only
there, new=delta>=0 and sequence=1. A known zero opening is still an explicit
INITIAL_STOCK row. Subsequent transactions require known previous, sequence>1,
new=previous+delta. An initially unknown spool cannot debit until an audited
opening basis is resolved. A physical measurement can establish that basis using
INITIAL_STOCK linked to an InventoryReconciliation, not an unexplained zero.

Source observations and decisions are immutable. Finalization rows are inserted
only inside the successful accounting transaction; IN_PROGRESS is the job's
transient transaction state, not a durable partially committed record.

## UNIQUE and primary keys

| Constraint | Purpose |
|---|---|
| Every table id PK; device_identity.public_id UNIQUE | Internal identity and origin |
| connection_profile(printer_id) UNIQUE | One active configuration owner in v1 |
| material_feed_system(printer_id, provider_system_key) UNIQUE WHERE provider_system_key IS NOT NULL | Scoped provider topology |
| feed_slot(feed_system_id, slot_key) UNIQUE | Stable slot identity |
| spool_mount(spool_id) UNIQUE WHERE state='ACTIVE' | Physical spool exclusivity |
| spool_mount(feed_slot_id) UNIQUE WHERE state='ACTIVE' | One spool in a slot |
| spool_identifier(namespace, kind, value) UNIQUE WHERE retired_at IS NULL AND verified_at IS NOT NULL | Trusted current identity cannot map to two spools |
| job_identity_alias(provider, printer_id, source_type, source_epoch, occurrence_key) UNIQUE | Validated run identity; no filename uniqueness |
| print_job_material(print_job_id, channel_key) UNIQUE | Logical material channel |
| material_usage_segment(print_job_material_id) UNIQUE WHERE ended_at IS NULL | At most one open segment per channel |
| external_event_receipt(provider, printer_id, source_epoch, event_key) UNIQUE | Event deduplication scope |
| finalization_record(print_job_id) UNIQUE | Exactly one initial accounting result per run |
| finalization_record(idempotency_key) UNIQUE | Reused command key must have matching request hash |
| consumption_decision(finalization_record_id, material_usage_segment_id) UNIQUE | One selected allocation per segment |
| decision_evidence(decision_id, evidence_id, role) UNIQUE | No duplicate evidence link |
| filament_transaction(spool_id, sequence) UNIQUE | Total per-spool ledger ordering |
| filament_transaction(command_key, command_item) UNIQUE | Idempotent multi-row inventory command |
| filament_transaction(decision_id) UNIQUE WHERE decision_id IS NOT NULL AND compensates_transaction_id IS NULL | One original debit per decision |
| filament_transaction(inventory_reconciliation_id) UNIQUE WHERE inventory_reconciliation_id IS NOT NULL | One application per accepted correction |
| inventory_reconciliation(evidence_id) UNIQUE | One acceptance per physical reading |
| calibration_record(sensor_id, version) UNIQUE | Reproducible calibration |
| material_transfer(command_key) UNIQUE | Idempotent paired transfer |
| reconciliation_task(dedupe_key) UNIQUE WHERE status IN ('OPEN','IN_REVIEW') | One live task per incident |
| alert_event(dedupe_key) UNIQUE WHERE resolved_at IS NULL | Alert dedupe |
| pending_effect(event_key, effect_type) UNIQUE | Retryable post-commit intent |

No UNIQUE external_job_id alone or external_job_id/printer/source tuple. No
UNIQUE(job_id, idempotency_key) substituted for job-only finalization uniqueness.
Do not rely on nullable unique columns to establish an unknown occurrence identity.

Additional reservation uniqueness: `(spool_id, print_job_material_id)` WHERE
status='ACTIVE'. Each actual segment debit is assigned once in settlement;
historical claims do not receive the same allocation repeatedly.
The `provider` field in receipts/aliases denotes an immutable provider-instance
identity, not a vendor string; instance and epoch semantics match PROVIDER_CONTRACTS.

## CHECK constraints and application guards

| Invariant | Enforcement |
|---|---|
| Mass storage is integer and bounded; finite exact decimals; confidence/percent ranges | SQL typeof/range CHECK for integers; Decimal parsing and canonical serialization for D; no numeric casts to float |
| Enum membership, B IN (0,1), revision>=1, sequence>=1 | SQL CHECK |
| Positive diameter/density, nonnegative purchase price; paired price/currency; CUSTOM requires a name | Application validation; SQL paired-null and enum checks |
| Effective negative implies QUARANTINED | spool CHECK(effective_remaining_mg IS NULL OR effective_remaining_mg>=0 OR inventory_health='QUARANTINED') |
| No negative nominal/tare/measured input/reservation; reserved_mg>0 | SQL CHECK; raw rejected readings retained as sanitized invalid observations/audit, not accepted inventory evidence |
| new = previous + delta, NULL previous only for INITIAL_STOCK sequence1 | SQL CHECK plus ledger append sequencing guard |
| INITIAL_STOCK positive/zero; use/purge/load/unload/waste/failed/manual/transfer-out deltas negative; transfer-in/return positive; correction/adjustment signed | SQL transaction-type/delta CHECK; zero permitted only opening or an explicit zero correction |
| ACTIVE mount has NULL end, CLOSED has end>=start | SQL CHECK; closed rows immutable thereafter |
| Segment end>=start; missing spool/mount requires unresolved assignment | SQL CHECK; resolved segment requires matching slot, mount and spool |
| Receipt processed_at set iff PROCESSED; finalized row has completed_at>=started_at | SQL CHECK |
| Consumption evidence contains mass or length with consistent quantity kind; interval end>=start | SQL CHECK plus unit/scope validation |
| Inventory net=gross-tare when all known; calibration matches sensor; fresh and stable | SQL arithmetic CHECK plus application eligibility |
| Layer counters nonnegative, current<=total when both known; durations nonnegative | SQL CHECK |
| Port 1..65535 when given; string/time bounds and UTC normalization | SQL CHECK for port/length; application datetime validation |
| Reservation consumed state has finalization and consumed_at; released/expired claims cannot reactivate | SQL CHECK for shape; explicit transition guard and CAS |
| Settlement uses min(reserved,actual allocated) and released=reserved-consumed allocation; excess actual is separately charged | Application UoW; never equate reserved to actual debit |
| Cross-entity spool/slot/printer/job/material references must agree | Composite FK where keys are available, otherwise validated insert/update trigger and application guard; simple independent FKs alone are insufficient |
| No overlapping mount intervals per spool/slot or segment intervals per material | UoW guard plus DB interval insert/update trigger; a partial unique index only covers open intervals |
| Storage parent is not self and cannot reach self | SQL self CHECK, recursive application/trigger cycle guard under write transaction |
| Snapshot matches latest ledger; reservation activation cannot overbook | UoW writer lock, revision CAS, append sequence guard, recomputation on startup/integrity checks |
| Decisions, transactions, evidence, reconciliation acceptances, audit cannot UPDATE/DELETE | SQLite BEFORE UPDATE/DELETE abort triggers; migrations explicitly manage these triggers |
| Transfer distinct spools, exactly two equal/opposite entries | SQL distinct-spool/positive-weight CHECK plus atomic application guard; immutable linked transactions |

Cross-table accounting invariants are not falsely advertised as SQLite CHECK
constraints: they require transactions/guard triggers and integration tests.
Opening, corrections, finalization and transfer commands update ledger/snapshot,
reservation state, alerts/reconciliation and audit in the same UoW.
Compensations must target the same spool and reference a prior committed entry;
over-compensation requires explicit adjustment authorization and reason rather
than silently reversing more mass than originally charged.

Additional immutability guards: once a segment is referenced by a decision, reject
changes to spool/mount/material/channel/interval. ACTIVE reservation identity,
material and amount cannot change in place; release-and-re-reserve rechecks capacity
atomically. Terminal reservation settlement cannot be edited.

Add `previous_estimated_mg I?`, `new_estimated_mg I?`, and `estimate_policy_version S`
to FilamentTransaction. Opening records the estimate basis; ordinary accepted
physical deltas advance a known estimate by delta, while an unknown estimate stays
NULL. Measurement corrections preserve the estimate unless their explicit linked
InventoryReconciliation records adoption of a new basis. Persist before/after
estimate values for deterministic replay, independent of later policy changes.
The estimate projection is not an independently editable balance.

For a selected_weight_mg=0 decision, insert no PRINT_CONSUMPTION transaction;
finalize the decision and release claims. One original debit per decision means
at most one debit, not a requirement to manufacture a zero inventory mutation.

## Read/query indexes

Add nonunique indexes on each referencing FK not already covered by a unique
prefix; SQLite does not create them automatically. Additional workload indexes:

- spool(lifecycle, inventory_health), spool(storage_location_id)
- print_job(printer_id, status, detected_at), print_job(finalization_state)
- filament_transaction(spool_id, created_at, sequence)
- reservation(spool_id, status), reservation(status, expires_at)
- spool_mount(feed_slot_id, mounted_at), spool_mount(spool_id, mounted_at)
- material_usage_segment(print_job_material_id, started_at)
- consumption_evidence(print_job_material_id, captured_at)
- inventory_evidence(spool_id, captured_at)
- external_event_receipt(processing_result, received_at)
- reconciliation_task(status, severity, created_at)
- pending_effect(state, next_attempt_at)
- storage_location(parent_id)

## Deliberately later migrations

DryingSession (spool, sensor/device, temperatures, aware UTC start/end, humidity,
notes), CostProfile, PrintCostBreakdown (currency and immutable cost assumptions),
AlertRule, FeatureFlag persistence, supplier/purchasing, inventory counts, parts,
sync journal and server users are specified in DOMAIN_MODEL and added by their
feature phases. In v1 optional features are disabled configuration values, not
empty provider packages claiming support. Core IDs/revisions/origins support a
future migration but do not imply an implemented sync conflict model.

Required acceptance evidence is [TEST_MATRIX](../TEST_MATRIX.md). Final SQL DDL
must be generated/reviewed with the Phase 2 migration and verified against this
constraint catalog before calling persistence implemented.
