"""Transactional inventory commands built exclusively on application ports."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal

from ufm.application.dto import WeightReading
from ufm.application.ports.persistence import (
    IdempotencyConflict,
    NotFound,
    RevisionConflict,
    UnitOfWork,
)
from ufm.domain.entities import (
    AlertEvent,
    AuditEvent,
    FilamentTransaction,
    InventoryEvidence,
    InventoryReconciliation,
    ReconciliationTask,
    Spool,
)
from ufm.domain.enums import (
    Availability,
    EvidenceSource,
    InventoryHealth,
    ReconciliationState,
    SensorType,
    Severity,
    SpoolLifecycle,
    StockLevel,
    TransactionType,
)
from ufm.domain.policies.ledger import validate_ledger_history
from ufm.domain.policies.transitions import validate_transition
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True, slots=True)
class InventoryAvailability:
    spool_id: EntityId
    effective: Mass | None
    reserved: Mass
    available: Mass | None
    level: StockLevel
    health: InventoryHealth


@dataclass(frozen=True, slots=True)
class InventoryMeasurementRecord:
    evidence: InventoryEvidence
    reconciliation: InventoryReconciliation | None


@dataclass(frozen=True, slots=True)
class InventoryCostSummary:
    spool_id: EntityId
    confirmed_prints: int
    unknown_cost_prints: int
    unknown_cost_consumed: Mass
    totals_by_currency: tuple[tuple[str, ExactDecimal], ...]


@dataclass(frozen=True, slots=True)
class InventoryCostReportEntry:
    transaction: FilamentTransaction
    print_started_at: UtcDateTime
    printer_name: str
    job_name: str
    spool_name: str


@dataclass(frozen=True, slots=True)
class InventoryCostReport:
    started_at: UtcDateTime
    until: UtcDateTime
    entries: tuple[InventoryCostReportEntry, ...]
    print_count: int
    consumed: Mass
    unknown_cost_prints: int
    unknown_cost_consumed: Mass
    totals_by_currency: tuple[tuple[str, ExactDecimal], ...]


MAX_COST_REPORT_ENTRIES = 10_000


def _sum_exact(values: list[ExactDecimal]) -> ExactDecimal:
    """Add finite decimal values without rounding through the Decimal context."""
    if not values:
        return ExactDecimal.parse(0)
    parts: list[tuple[int, tuple[int, ...], int]] = []
    for value in values:
        sign, digits, item_exponent = value.value.as_tuple()
        if not isinstance(item_exponent, int):
            raise ValueError("decimal.invalid")
        parts.append((sign, digits, item_exponent))
    exponent = min(part[2] for part in parts)
    total = 0
    for sign, digits, item_exponent in parts:
        coefficient = int("".join(str(digit) for digit in digits) or "0")
        total += (-1 if sign else 1) * coefficient * (10 ** (item_exponent - exponent))
    negative = total < 0
    digits = tuple(int(char) for char in str(abs(total))) if total else (0,)
    return ExactDecimal(Decimal((int(negative), digits, exponent)))


class InventoryCommands:
    """Write-side inventory use cases; ledger and projection always commit together."""

    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def availability(self, spool_id: EntityId) -> InventoryAvailability:
        with self._unit_of_work() as work:
            spool = work.spools.get(spool_id)
            reserved = Mass(sum(
                claim.reserved.milligrams
                for claim in work.reservations.active_for_spool(spool_id)
            ))
            available = spool.available(reserved)
            if available is None:
                level = StockLevel.UNKNOWN
            elif available.milligrams == 0:
                level = StockLevel.EMPTY
            elif available.milligrams < 0:
                level = StockLevel.LOW
            elif (
                spool.low_threshold is not None
                and available.milligrams <= spool.low_threshold.milligrams
            ):
                level = StockLevel.LOW
            else:
                level = StockLevel.NORMAL
            return InventoryAvailability(
                spool_id=spool_id, effective=spool.effective_remaining,
                reserved=reserved, available=available, level=level,
                health=spool.inventory_health,
            )

    def history(
        self, spool_id: EntityId, *, after_sequence: int = 0
    ) -> tuple[FilamentTransaction, ...]:
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("inventory.history_sequence_invalid")
        with self._unit_of_work() as work:
            work.spools.get(spool_id)
            return tuple(work.ledger.for_spool(spool_id, after_sequence))

    def cost_summary(self, spool_id: EntityId) -> InventoryCostSummary:
        """Summarize booked print costs without mixing currencies or estimates."""
        with self._unit_of_work() as work:
            work.spools.get(spool_id)
            entries = tuple(
                entry for entry in work.ledger.for_spool(spool_id)
                if entry.transaction_type is TransactionType.PRINT_CONSUMPTION
                and entry.delta.milligrams < 0
            )
            by_currency: dict[str, list[ExactDecimal]] = {}
            unknown_count = 0
            unknown_mg = 0
            for entry in entries:
                if entry.unit_cost is None or entry.currency is None:
                    unknown_count += 1
                    unknown_mg += -entry.delta.milligrams
                    continue
                by_currency.setdefault(entry.currency, []).append(entry.unit_cost)
            totals = tuple(
                (currency, _sum_exact(amounts))
                for currency, amounts in sorted(by_currency.items())
            )
            return InventoryCostSummary(
                spool_id=spool_id, confirmed_prints=len(entries),
                unknown_cost_prints=unknown_count,
                unknown_cost_consumed=Mass(unknown_mg), totals_by_currency=totals,
            )

    def cost_report(
        self, *, started_at: UtcDateTime, until: UtcDateTime,
        printer_id: EntityId | None = None,
    ) -> InventoryCostReport:
        """Read a bounded print-cost report using job start time and frozen costs."""
        if started_at >= until:
            raise ValueError("inventory.cost_report_interval_invalid")
        with self._unit_of_work() as work:
            records = tuple(work.ledger.cost_entries(
                started_at, until, printer_id, MAX_COST_REPORT_ENTRIES + 1,
            ))
            if len(records) > MAX_COST_REPORT_ENTRIES:
                raise ValueError("inventory.cost_report_limit")
            report_entries: list[InventoryCostReportEntry] = []
            jobs: set[EntityId] = set()
            by_currency: dict[str, list[ExactDecimal]] = {}
            unknown_count = 0
            unknown_mg = 0
            consumed_mg = 0
            for report_record in records:
                record = report_record.transaction
                if record.print_job_id is None:
                    raise ValueError("inventory.cost_report_job_missing")
                if record.delta.milligrams >= 0:
                    raise ValueError("inventory.cost_report_record_invalid")
                report_entries.append(InventoryCostReportEntry(
                    transaction=record, print_started_at=report_record.print_started_at,
                    printer_name=report_record.printer_name,
                    job_name=report_record.job_name,
                    spool_name=report_record.spool_name,
                ))
                jobs.add(record.print_job_id)
                consumed_mg += -record.delta.milligrams
                if record.unit_cost is None or record.currency is None:
                    unknown_count += 1
                    unknown_mg += -record.delta.milligrams
                else:
                    by_currency.setdefault(record.currency, []).append(record.unit_cost)
            totals = tuple(
                (currency, _sum_exact(amounts))
                for currency, amounts in sorted(by_currency.items())
            )
            return InventoryCostReport(
                started_at=started_at, until=until, entries=tuple(report_entries),
                print_count=len(jobs), consumed=Mass(consumed_mg),
                unknown_cost_prints=unknown_count,
                unknown_cost_consumed=Mass(unknown_mg), totals_by_currency=totals,
            )

    def measurement_history(
        self, spool_id: EntityId,
    ) -> tuple[InventoryMeasurementRecord, ...]:
        with self._unit_of_work() as work:
            work.spools.get(spool_id)
            evidence = work.evidence.inventory_for_spool(spool_id)
            return tuple(InventoryMeasurementRecord(
                evidence=item,
                reconciliation=work.reconciliations.inventory_for_evidence(item.id),
            ) for item in evidence)

    def record_inventory_measurement(
        self,
        *,
        spool_id: EntityId,
        net: Mass,
        actor_device_id: EntityId,
        command_key: str,
        source: EvidenceSource = EvidenceSource.MANUAL,
        gross: Mass | None = None,
        tare: Mass | None = None,
        sensor_id: EntityId | None = None,
        calibration_id: EntityId | None = None,
        stability_bp: int | None = None,
        stable_duration_ms: int | None = None,
        captured_at: UtcDateTime | None = None,
        at: UtcDateTime | None = None,
    ) -> InventoryEvidence:
        """Persist immutable physical evidence without changing inventory stock."""
        if source is not EvidenceSource.MANUAL:
            raise ValueError("inventory.measurement_provider_command_required")
        if type(command_key) is not str or not command_key.strip() or len(command_key) > 500:
            raise ValueError("inventory.measurement_command_key_invalid")
        received_at = at or UtcDateTime.now()
        measured_at = captured_at or received_at
        if measured_at > received_at:
            raise ValueError("inventory.measurement_capture_after_receive")
        fingerprint = self._fingerprint(
            operation="record_inventory_measurement", spool_id=str(spool_id),
            actor=str(actor_device_id), source=source.value,
            gross=None if gross is None else gross.milligrams,
            tare=None if tare is None else tare.milligrams,
            net=net.milligrams, sensor=None if sensor_id is None else str(sensor_id),
            calibration=None if calibration_id is None else str(calibration_id),
            stability_bp=stability_bp, stable_duration_ms=stable_duration_ms,
            captured_at=measured_at.value.isoformat(),
        )
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1 or event.event_code != "inventory.measurement_recorded"
                    or event.entity_type != "inventory_evidence"
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.evidence.get_inventory(event.entity_id)

            spool = work.spools.get(spool_id)
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            evidence = InventoryEvidence(
                id=EntityId.new(), device_id=actor_device_id, created_at=received_at,
                spool_id=spool_id, source=source, captured_at=measured_at,
                received_at=received_at, gross=gross, tare=tare, net=net,
                sensor_id=sensor_id, calibration_id=calibration_id,
                stability_bp=stability_bp, stable_duration_ms=stable_duration_ms,
                ledger_cutoff=spool.ledger_sequence,
            )
            work.evidence.add_inventory(evidence)
            work.audit.append(AuditEvent(
                id=EntityId.new(), device_id=actor_device_id, created_at=received_at,
                event_code="inventory.measurement_recorded", actor_device_id=actor_device_id,
                correlation_id=command_key, entity_type="inventory_evidence",
                entity_id=evidence.id,
                parameters_json=json.dumps({"request_hash_v1": fingerprint}, sort_keys=True),
            ))
            work.commit()
            return evidence

    def record_scale_reading(
        self,
        *,
        reading: WeightReading,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> InventoryEvidence:
        """Persist a normalized, stable and calibrated scale reading as evidence only."""
        if type(command_key) is not str or not command_key.strip() or len(command_key) > 500:
            raise ValueError("inventory.measurement_command_key_invalid")
        if reading.associated_spool_id is None:
            raise ValueError("inventory.scale_spool_required")
        observations = (reading.gross_mass, reading.tare_mass, reading.net_mass)
        if any(
            item.availability is not Availability.KNOWN or item.value is None
            for item in observations
        ):
            raise ValueError("inventory.scale_measurements_incomplete")
        if reading.stable.availability is not Availability.KNOWN or reading.stable.value is not True:
            raise ValueError("inventory.scale_reading_unstable")
        received_at = at or UtcDateTime.now()
        if reading.received_at > received_at:
            raise ValueError("inventory.scale_reading_received_in_future")
        if reading.interval_end > reading.received_at:
            raise ValueError("inventory.scale_interval_after_receive")
        if reading.observed_at > reading.received_at:
            raise ValueError("inventory.scale_observation_after_receive")
        if not reading.interval_start <= reading.observed_at <= reading.interval_end:
            raise ValueError("inventory.scale_observation_outside_interval")
        if any(
            item.observed_at > reading.observed_at
            or item.observed_at > item.received_at
            or item.received_at > reading.received_at
            for item in (*observations, reading.stable)
        ):
            raise ValueError("inventory.scale_observation_after_receive")
        if reading.calibration_id is None or reading.calibration_version is None:
            raise ValueError("inventory.measurement_calibration_required")

        gross, tare, net = (item.value for item in observations)
        assert gross is not None and tare is not None and net is not None
        fingerprint = self._fingerprint(
            operation="record_scale_reading", spool_id=str(reading.associated_spool_id),
            actor=str(actor_device_id), sensor=str(reading.sensor_id),
            calibration=str(reading.calibration_id), calibration_version=reading.calibration_version,
            gross=gross.milligrams, tare=tare.milligrams, net=net.milligrams,
            stable=reading.stable.value, interval_start=reading.interval_start.value.isoformat(),
            interval_end=reading.interval_end.value.isoformat(),
            observed_at=reading.observed_at.value.isoformat(),
            received_at=reading.received_at.value.isoformat(),
        )
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1 or event.event_code != "inventory.scale_measurement_recorded"
                    or event.entity_type != "inventory_evidence"
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.evidence.get_inventory(event.entity_id)
            spool = work.spools.get(reading.associated_spool_id)
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            self._validate_scale_calibration(
                work, sensor_id=reading.sensor_id, calibration_id=reading.calibration_id,
                calibration_version=reading.calibration_version,
                observed_at=reading.observed_at, valid_at=received_at,
            )
            stable_duration = reading.interval_end.value - reading.interval_start.value
            evidence = InventoryEvidence(
                id=EntityId.new(), device_id=actor_device_id, created_at=received_at,
                spool_id=spool.id, source=EvidenceSource.SCALE,
                captured_at=reading.observed_at, received_at=received_at,
                gross=gross, tare=tare, net=net, sensor_id=reading.sensor_id,
                calibration_id=reading.calibration_id,
                stable_duration_ms=(
                    stable_duration.days * 86_400_000 + stable_duration.seconds * 1_000
                    + stable_duration.microseconds // 1_000
                ),
                ledger_cutoff=spool.ledger_sequence,
            )
            work.evidence.add_inventory(evidence)
            work.audit.append(AuditEvent(
                id=EntityId.new(), device_id=actor_device_id, created_at=received_at,
                event_code="inventory.scale_measurement_recorded", actor_device_id=actor_device_id,
                correlation_id=command_key, entity_type="inventory_evidence", entity_id=evidence.id,
                parameters_json=json.dumps({"request_hash_v1": fingerprint}, sort_keys=True),
            ))
            work.commit()
            return evidence

    @staticmethod
    def _validate_scale_calibration(
        work: UnitOfWork,
        *,
        sensor_id: EntityId,
        calibration_id: EntityId,
        calibration_version: int,
        observed_at: UtcDateTime,
        valid_at: UtcDateTime,
    ) -> None:
        sensor = work.sensors.get(sensor_id)
        calibration = work.calibrations.get(calibration_id)
        if sensor.sensor_type is not SensorType.SCALE or not sensor.enabled or sensor.deleted_at is not None:
            raise ValueError("inventory.scale_sensor_unavailable")
        if (
            calibration.sensor_id != sensor_id or calibration.version != calibration_version
            or calibration.calibration_type.casefold() != "scale"
        ):
            raise ValueError("inventory.scale_calibration_mismatch")
        latest = work.calibrations.latest_for_sensor(sensor_id)
        if latest is None or latest.id != calibration.id:
            raise ValueError("inventory.scale_calibration_not_current")
        if calibration.performed_at > observed_at or (
            calibration.expires_at is not None
            and (observed_at > calibration.expires_at or valid_at > calibration.expires_at)
        ):
            raise ValueError("inventory.scale_calibration_expired")

    def accept_inventory_measurement(
        self,
        *,
        spool_id: EntityId,
        evidence_id: EntityId,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        reason: str,
        policy_version: str = "manual-measurement-v1",
        at: UtcDateTime | None = None,
    ) -> Spool:
        """Explicitly reconcile stock to a captured physical measurement."""
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("inventory.measurement_revision_invalid")
        if type(reason) is not str or not reason.strip() or len(reason) > 500:
            raise ValueError("inventory.measurement_reason_invalid")
        if type(policy_version) is not str or not policy_version.strip() or len(policy_version) > 500:
            raise ValueError("inventory.measurement_policy_invalid")
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="accept_inventory_measurement", spool_id=str(spool_id),
            evidence_id=str(evidence_id), expected_revision=expected_revision,
            actor=str(actor_device_id), reason=reason, policy_version=policy_version,
        )
        event_code = "inventory.measurement_reconciled"
        with self._unit_of_work() as work:
            replay = self._replay_spool(
                work, command_key, event_code, spool_id, fingerprint,
            )
            if replay is not None:
                return replay

            spool = work.spools.get(spool_id)
            if spool.revision != expected_revision:
                raise RevisionConflict()
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            evidence = work.evidence.get_inventory(evidence_id)
            if evidence.spool_id != spool_id or evidence.net is None:
                raise ValueError("inventory.measurement_evidence_scope_invalid")
            if evidence.source not in {EvidenceSource.MANUAL, EvidenceSource.SCALE}:
                raise ValueError("inventory.measurement_source_untrusted")
            if evidence.source is EvidenceSource.SCALE and (
                evidence.sensor_id is None or evidence.calibration_id is None
            ):
                raise ValueError("inventory.measurement_calibration_required")
            if evidence.source is EvidenceSource.SCALE:
                if evidence.calibration_id is None or evidence.sensor_id is None:
                    raise ValueError("inventory.measurement_calibration_required")
                calibration = work.calibrations.get(evidence.calibration_id)
                self._validate_scale_calibration(
                    work, sensor_id=evidence.sensor_id, calibration_id=evidence.calibration_id,
                    calibration_version=calibration.version, observed_at=evidence.captured_at,
                    valid_at=occurred_at,
                )
            if work.reconciliations.inventory_for_evidence(evidence_id) is not None:
                raise ValueError("inventory.measurement_already_accepted")
            if evidence.ledger_cutoff != spool.ledger_sequence:
                raise ValueError("inventory.measurement_ledger_stale")

            history = tuple(work.ledger.for_spool(spool_id))
            validate_ledger_history(history)
            if (
                len(history) != spool.ledger_sequence
                or (history and history[-1].new_effective != spool.effective_remaining)
                or (not history and spool.effective_remaining is not None)
            ):
                raise ValueError("inventory.measurement_projection_mismatch")
            if spool.revision != expected_revision:
                raise RevisionConflict()

            accepted = evidence.net
            reserved_mg = sum(
                reservation.reserved.milligrams
                for reservation in work.reservations.active_for_spool(spool_id)
            )
            if reserved_mg > accepted.milligrams:
                raise ValueError("inventory.measurement_below_reserved")
            previous_effective = spool.effective_remaining
            delta = accepted if previous_effective is None else Mass(
                accepted.milligrams - previous_effective.milligrams,
            )
            sequence = spool.ledger_sequence
            reconciliation = InventoryReconciliation(
                id=EntityId.new(), device_id=actor_device_id, created_at=occurred_at,
                spool_id=spool_id, evidence_id=evidence.id,
                accepted_ledger_cutoff=evidence.ledger_cutoff or 0,
                accepted_remaining=accepted, policy_version=policy_version,
                reason=reason.strip(), actor_device_id=actor_device_id,
                previous_effective=previous_effective,
                estimated_before=spool.estimated_remaining,
                estimated_after=accepted,
            )
            work.reconciliations.add_inventory(reconciliation)
            if previous_effective is None or delta.milligrams != 0:
                sequence += 1
                entry = FilamentTransaction(
                    id=EntityId.new(), device_id=actor_device_id, created_at=occurred_at,
                    spool_id=spool_id, sequence=sequence,
                    transaction_type=(
                        TransactionType.INITIAL_STOCK if previous_effective is None
                        else TransactionType.INVENTORY_ADJUSTMENT
                    ),
                    delta=delta, previous_effective=previous_effective,
                    new_effective=accepted, command_key=command_key, command_item=0,
                    source_type=evidence.source.value, confidence_bp=10_000,
                    previous_estimated=spool.estimated_remaining,
                    new_estimated=accepted,
                    estimate_policy_version=policy_version,
                    inventory_reconciliation_id=reconciliation.id,
                )
                work.ledger.append(entry)
            updated = replace(
                spool, updated_at=occurred_at, revision=spool.revision + 1,
                effective_remaining=accepted, estimated_remaining=accepted,
                measured_remaining=accepted, ledger_sequence=sequence,
                inventory_health=self._health_after_change(work, spool, accepted),
            )
            work.spools.save(updated, expected_revision)
            self._raise_inventory_alerts(work, updated, actor_device_id, occurred_at)
            self._audit(
                work, actor_device_id, occurred_at, event_code, command_key,
                spool_id, fingerprint=fingerprint,
            )
            work.commit()
            return updated

    def rebuild_projection(
        self,
        *,
        spool_id: EntityId,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Spool:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="rebuild_projection", spool_id=str(spool_id),
            expected_revision=expected_revision, actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay_spool(
                work, command_key, "inventory.projection_rebuilt", spool_id, fingerprint,
            )
            if replay is not None:
                return replay
            spool = work.spools.get(spool_id)
            if spool.revision != expected_revision:
                raise RevisionConflict()
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            history = tuple(work.ledger.for_spool(spool_id))
            validate_ledger_history(history)
            effective = None if not history else history[-1].new_effective
            estimated = None if not history else history[-1].new_estimated
            health = self._health_after_change(work, spool, effective)
            updated = replace(
                spool, revision=spool.revision + 1, updated_at=occurred_at,
                effective_remaining=effective, estimated_remaining=estimated,
                ledger_sequence=len(history), inventory_health=health,
            )
            work.spools.save(updated, expected_revision)
            self._raise_inventory_alerts(work, updated, actor_device_id, occurred_at)
            self._audit(
                work, actor_device_id, occurred_at, "inventory.projection_rebuilt",
                command_key, spool_id, fingerprint=fingerprint,
            )
            work.commit()
            return updated

    def resolve_quarantine(
        self,
        *,
        spool_id: EntityId,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        reason: str,
        at: UtcDateTime | None = None,
    ) -> Spool:
        if type(reason) is not str or not reason.strip() or len(reason) > 500:
            raise ValueError("inventory.quarantine_reason_invalid")
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="resolve_quarantine", spool_id=str(spool_id),
            expected_revision=expected_revision, actor=str(actor_device_id), reason=reason,
        )
        with self._unit_of_work() as work:
            replay = self._replay_spool(
                work, command_key, "inventory.quarantine_resolved", spool_id, fingerprint,
            )
            if replay is not None:
                return replay
            spool = work.spools.get(spool_id)
            if spool.revision != expected_revision:
                raise RevisionConflict()
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            if spool.inventory_health is not InventoryHealth.QUARANTINED:
                raise ValueError("inventory.quarantine_required")
            history = tuple(work.ledger.for_spool(spool_id))
            validate_ledger_history(history)
            if (
                not history or spool.ledger_sequence != history[-1].sequence
                or spool.effective_remaining != history[-1].new_effective
                or spool.estimated_remaining != history[-1].new_estimated
            ):
                raise ValueError("inventory.quarantine_projection_mismatch")
            if spool.effective_remaining is None or spool.effective_remaining.milligrams < 0:
                raise ValueError("inventory.quarantine_stock_invalid")
            reserved = sum(
                claim.reserved.milligrams for claim in work.reservations.active_for_spool(spool_id)
            )
            if reserved > spool.effective_remaining.milligrams:
                raise ValueError("inventory.quarantine_reservation_shortage")
            if work.segments.has_unresolved_for_spool(spool_id):
                raise ValueError("inventory.quarantine_unresolved_usage")
            tasks = work.reconciliations.open_tasks_for_spool(spool_id)
            allowed = {
                f"spool:{spool_id}:negative-stock": {
                    "inventory.negative_stock", "inventory.review_required",
                },
                f"spool:{spool_id}:reservation-shortage": {"RESERVATION_SHORTAGE"},
            }
            if not tasks or any(
                task.reason_code not in allowed.get(task.dedupe_key, set())
                or task.print_job_id is not None or task.feed_slot_id is not None
                for task in tasks
            ):
                raise ValueError("inventory.quarantine_tasks_require_review")
            for task in tasks:
                work.reconciliations.save_task(replace(
                    task, state=validate_transition(task.state, ReconciliationState.RESOLVED),
                    resolved_at=occurred_at, resolved_by=actor_device_id, resolution_notes=reason,
                    updated_at=occurred_at, revision=task.revision + 1,
                ), task.revision)
            updated = replace(
                spool, inventory_health=validate_transition(
                    spool.inventory_health, InventoryHealth.CONSISTENT,
                ), updated_at=occurred_at, revision=spool.revision + 1,
            )
            work.spools.save(updated, expected_revision)
            self._raise_inventory_alerts(work, updated, actor_device_id, occurred_at)
            self._audit(
                work, actor_device_id, occurred_at, "inventory.quarantine_resolved",
                command_key, spool_id, fingerprint=fingerprint,
            )
            work.commit()
            return updated

    def create_spool(
        self,
        *,
        spool_id: EntityId,
        filament_profile_id: EntityId,
        display_name: str,
        actor_device_id: EntityId,
        command_key: str,
        brand_id: EntityId | None = None,
        product_line: str | None = None,
        batch_number: str | None = None,
        lot_number: str | None = None,
        color_name: str | None = None,
        color_hex: str | None = None,
        secondary_color_hex: str | None = None,
        image_uri: str | None = None,
        notes: str | None = None,
        opened_at: UtcDateTime | None = None,
        manufactured_at: UtcDateTime | None = None,
        expires_at: UtcDateTime | None = None,
        nominal_filament: Mass | None = None,
        empty_spool: Mass | None = None,
        purchase_price: ExactDecimal | None = None,
        purchase_basis: Mass | None = None,
        currency: str | None = None,
        purchase_date: str | None = None,
        low_threshold: Mass | None = None,
        at: UtcDateTime | None = None,
    ) -> Spool:
        occurred_at = at or UtcDateTime.now()
        self._validate_purchase_profile(purchase_price, purchase_basis, currency)
        candidate = Spool(
            id=spool_id,
            device_id=actor_device_id,
            created_at=occurred_at,
            updated_at=occurred_at,
            revision=1,
            display_name=display_name,
            filament_profile_id=filament_profile_id,
            brand_id=brand_id,
            product_line=product_line,
            batch_number=batch_number,
            lot_number=lot_number,
            color_name=color_name,
            color_hex=color_hex,
            secondary_color_hex=secondary_color_hex,
            image_uri=image_uri,
            notes=notes,
            opened_at=opened_at,
            manufactured_at=manufactured_at,
            expires_at=expires_at,
            nominal_filament=nominal_filament,
            empty_spool=empty_spool,
            purchase_price=purchase_price,
            purchase_basis=purchase_basis,
            currency=currency,
            purchase_date=purchase_date,
            low_threshold=low_threshold,
        )
        fingerprint = self._fingerprint(
            operation="create_spool", spool_id=str(spool_id),
            filament_profile_id=str(filament_profile_id), display_name=display_name,
            actor=str(actor_device_id),
            brand_id=None if brand_id is None else str(brand_id),
            product_line=product_line, batch_number=batch_number, lot_number=lot_number,
            color_name=color_name, color_hex=color_hex,
            secondary_color_hex=secondary_color_hex, image_uri=image_uri, notes=notes,
            opened_at=None if opened_at is None else opened_at.isoformat(),
            manufactured_at=None if manufactured_at is None else manufactured_at.isoformat(),
            expires_at=None if expires_at is None else expires_at.isoformat(),
            nominal_filament=None if nominal_filament is None else nominal_filament.milligrams,
            empty_spool=None if empty_spool is None else empty_spool.milligrams,
            purchase_price=None if purchase_price is None else purchase_price.canonical(),
            purchase_basis=None if purchase_basis is None else purchase_basis.milligrams,
            currency=currency, purchase_date=purchase_date,
            low_threshold=None if low_threshold is None else low_threshold.milligrams,
        )
        with self._unit_of_work() as work:
            replay = self._replay_spool(work, command_key, "spool.created", spool_id, fingerprint)
            if replay is not None:
                return replay
            try:
                existing = work.spools.get(spool_id)
            except NotFound:
                existing = None
            if existing is not None:
                raise IdempotencyConflict()
            if brand_id is not None:
                brand = work.brands.get(brand_id)
                if brand.deleted_at is not None:
                    raise ValueError("spool.brand_unavailable")
            work.spools.add(candidate)
            self._audit(
                work, actor_device_id, occurred_at, "spool.created", command_key, spool_id,
                fingerprint=fingerprint,
            )
            work.commit()
            return candidate

    def edit_spool(
        self,
        *,
        spool_id: EntityId,
        expected_revision: int,
        display_name: str,
        low_threshold: Mass | None,
        brand_id: EntityId | None = None,
        nominal_filament: Mass | None = None,
        empty_spool: Mass | None = None,
        purchase_price: ExactDecimal | None = None,
        purchase_basis: Mass | None = None,
        currency: str | None = None,
        purchase_date: str | None = None,
        product_line: str | None = None,
        batch_number: str | None = None,
        lot_number: str | None = None,
        color_name: str | None = None,
        color_hex: str | None = None,
        secondary_color_hex: str | None = None,
        image_uri: str | None = None,
        notes: str | None = None,
        opened_at: UtcDateTime | None = None,
        manufactured_at: UtcDateTime | None = None,
        expires_at: UtcDateTime | None = None,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Spool:
        occurred_at = at or UtcDateTime.now()
        self._validate_purchase_profile(purchase_price, purchase_basis, currency)
        fingerprint = self._fingerprint(
            operation="edit_spool", spool_id=str(spool_id), expected_revision=expected_revision,
            display_name=display_name, actor=str(actor_device_id),
            low_threshold=None if low_threshold is None else low_threshold.milligrams,
            brand_id=None if brand_id is None else str(brand_id),
            nominal_filament=None if nominal_filament is None else nominal_filament.milligrams,
            empty_spool=None if empty_spool is None else empty_spool.milligrams,
            product_line=product_line, batch_number=batch_number, lot_number=lot_number,
            color_name=color_name, color_hex=color_hex,
            secondary_color_hex=secondary_color_hex, image_uri=image_uri, notes=notes,
            opened_at=None if opened_at is None else opened_at.isoformat(),
            manufactured_at=None if manufactured_at is None else manufactured_at.isoformat(),
            expires_at=None if expires_at is None else expires_at.isoformat(),
            purchase_price=None if purchase_price is None else purchase_price.canonical(),
            purchase_basis=None if purchase_basis is None else purchase_basis.milligrams,
            currency=currency, purchase_date=purchase_date,
        )
        with self._unit_of_work() as work:
            replay = self._replay_spool(work, command_key, "spool.edited", spool_id, fingerprint)
            if replay is not None:
                return replay
            current = work.spools.get(spool_id)
            if current.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            if current.revision != expected_revision:
                raise RevisionConflict()
            if brand_id is not None and brand_id != current.brand_id:
                brand = work.brands.get(brand_id)
                if brand.deleted_at is not None:
                    raise ValueError("spool.brand_unavailable")
            updated = replace(
                current,
                display_name=display_name,
                low_threshold=low_threshold,
                brand_id=brand_id,
                nominal_filament=nominal_filament,
                empty_spool=empty_spool,
                purchase_price=purchase_price,
                purchase_basis=purchase_basis,
                currency=currency,
                purchase_date=purchase_date,
                product_line=product_line,
                batch_number=batch_number,
                lot_number=lot_number,
                color_name=color_name,
                color_hex=color_hex,
                secondary_color_hex=secondary_color_hex,
                image_uri=image_uri,
                notes=notes,
                opened_at=opened_at,
                manufactured_at=manufactured_at,
                expires_at=expires_at,
                updated_at=occurred_at,
                revision=current.revision + 1,
            )
            work.spools.save(updated, expected_revision)
            self._audit(
                work, actor_device_id, occurred_at, "spool.edited", command_key, spool_id,
                fingerprint=fingerprint,
            )
            self._raise_inventory_alerts(work, updated, actor_device_id, occurred_at)
            work.commit()
            return updated

    def archive_spool(
        self,
        *,
        spool_id: EntityId,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Spool:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="archive_spool", spool_id=str(spool_id), expected_revision=expected_revision,
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay_spool(work, command_key, "spool.archived", spool_id, fingerprint)
            if replay is not None:
                return replay
            current = work.spools.get(spool_id)
            if current.lifecycle is SpoolLifecycle.ARCHIVED:
                raise IdempotencyConflict()
            if current.revision != expected_revision:
                raise RevisionConflict()
            if work.mounts.active_for_spool(spool_id) is not None:
                raise ValueError("spool.archive_active_mount")
            if work.reservations.active_for_spool(spool_id):
                raise ValueError("spool.archive_active_reservation")
            if work.segments.has_unresolved_for_spool(spool_id):
                raise ValueError("spool.archive_unresolved_usage")
            lifecycle = validate_transition(current.lifecycle, SpoolLifecycle.ARCHIVED)
            updated = replace(
                current,
                lifecycle=lifecycle,
                archived_at=occurred_at,
                updated_at=occurred_at,
                revision=current.revision + 1,
            )
            work.spools.save(updated, expected_revision)
            self._audit(
                work, actor_device_id, occurred_at, "spool.archived", command_key, spool_id,
                fingerprint=fingerprint,
            )
            work.commit()
            return updated

    def establish_opening_stock(
        self,
        *,
        spool_id: EntityId,
        amount: Mass,
        command_key: str,
        actor_device_id: EntityId,
        at: UtcDateTime | None = None,
    ) -> FilamentTransaction:
        if amount.milligrams < 0:
            raise ValueError("inventory.opening_negative")
        return self._post(
            spool_id=spool_id,
            delta=amount,
            transaction_type=TransactionType.INITIAL_STOCK,
            command_key=command_key,
            actor_device_id=actor_device_id,
            at=at,
        )

    def compensate(
        self,
        *,
        transaction_id: EntityId,
        command_key: str,
        actor_device_id: EntityId,
        at: UtcDateTime | None = None,
    ) -> FilamentTransaction:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="compensate", transaction_id=str(transaction_id), actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            prior = self._replay_ledger(
                work, command_key, "inventory.compensated", fingerprint,
            )
            if prior is not None:
                if prior.compensates_transaction_id != transaction_id:
                    raise IdempotencyConflict()
                return prior
            original = work.ledger.get(transaction_id)
            if original.delta.milligrams == 0:
                raise ValueError("inventory.zero_transaction_not_compensable")
            if work.ledger.compensation_for(transaction_id) is not None:
                raise ValueError("inventory.transaction_already_compensated")
            spool = work.spools.get(original.spool_id)
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            if spool.effective_remaining is None or spool.ledger_sequence == 0:
                raise ValueError("inventory.opening_required")
            delta = Mass(-original.delta.milligrams)
            new_effective = spool.effective_remaining + delta
            new_estimated = (
                None if spool.estimated_remaining is None else spool.estimated_remaining + delta
            )
            entry = FilamentTransaction(
                id=EntityId.new(), device_id=actor_device_id, created_at=occurred_at,
                spool_id=spool.id, sequence=spool.ledger_sequence + 1,
                transaction_type=TransactionType.INVENTORY_ADJUSTMENT, delta=delta,
                previous_effective=spool.effective_remaining, new_effective=new_effective,
                command_key=command_key, command_item=0, source_type="COMPENSATION",
                confidence_bp=10_000, previous_estimated=spool.estimated_remaining,
                new_estimated=new_estimated, estimate_policy_version="compensation-v1",
                compensates_transaction_id=transaction_id,
            )
            updated = replace(
                spool, revision=spool.revision + 1, updated_at=occurred_at,
                effective_remaining=new_effective, estimated_remaining=new_estimated,
                ledger_sequence=entry.sequence,
                inventory_health=self._health_after_change(work, spool, new_effective),
            )
            work.ledger.append(entry)
            work.spools.save(updated, spool.revision)
            self._raise_inventory_alerts(work, updated, actor_device_id, occurred_at)
            self._audit(
                work, actor_device_id, occurred_at, "inventory.compensated",
                command_key, spool.id, fingerprint=fingerprint,
            )
            work.commit()
            return entry

    def adjust(
        self,
        *,
        spool_id: EntityId,
        delta: Mass,
        command_key: str,
        actor_device_id: EntityId,
        at: UtcDateTime | None = None,
    ) -> FilamentTransaction:
        if delta.milligrams == 0:
            raise ValueError("inventory.adjustment_zero")
        return self._post(
            spool_id=spool_id,
            delta=delta,
            transaction_type=TransactionType.INVENTORY_ADJUSTMENT,
            command_key=command_key,
            actor_device_id=actor_device_id,
            at=at,
        )

    def deduct_manual(
        self,
        *,
        spool_id: EntityId,
        amount: Mass,
        command_key: str,
        actor_device_id: EntityId,
        at: UtcDateTime | None = None,
    ) -> FilamentTransaction:
        if amount.milligrams <= 0:
            raise ValueError("inventory.manual_deduction_invalid")
        return self._post(
            spool_id=spool_id,
            delta=Mass(-amount.milligrams),
            transaction_type=TransactionType.INVENTORY_ADJUSTMENT,
            command_key=command_key,
            actor_device_id=actor_device_id,
            at=at,
            enforce_available_stock=True,
        )

    def _post(
        self,
        *,
        spool_id: EntityId,
        delta: Mass,
        transaction_type: TransactionType,
        command_key: str,
        actor_device_id: EntityId,
        at: UtcDateTime | None,
        enforce_available_stock: bool = False,
    ) -> FilamentTransaction:
        occurred_at = at or UtcDateTime.now()
        opening = transaction_type is TransactionType.INITIAL_STOCK
        event_code = "inventory.opening_established" if opening else "inventory.adjusted"
        fingerprint = self._fingerprint(
            operation=event_code, spool_id=str(spool_id), delta=delta.milligrams,
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            prior = self._replay_ledger(work, command_key, event_code, fingerprint)
            if prior is not None:
                if (
                    prior.spool_id != spool_id
                    or prior.delta != delta
                    or prior.transaction_type is not transaction_type
                    or prior.source_type != "MANUAL"
                    or prior.compensates_transaction_id is not None
                ):
                    raise IdempotencyConflict()
                return prior

            spool = work.spools.get(spool_id)
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            if opening:
                if spool.ledger_sequence != 0 or spool.effective_remaining is not None:
                    raise ValueError("inventory.opening_already_established")
                previous_effective = None
                new_effective = delta
                previous_estimated = None
                new_estimated: Mass | None = delta
                sequence = 1
            else:
                if spool.effective_remaining is None or spool.ledger_sequence == 0:
                    raise ValueError("inventory.opening_required")
                if enforce_available_stock and delta.milligrams < 0:
                    reserved = sum(
                        claim.reserved.milligrams
                        for claim in work.reservations.active_for_spool(spool_id)
                    )
                    available = spool.effective_remaining.milligrams - reserved
                    if -delta.milligrams > available:
                        raise ValueError("inventory.manual_deduction_exceeds_available")
                previous_effective = spool.effective_remaining
                new_effective = previous_effective + delta
                previous_estimated = spool.estimated_remaining
                new_estimated = (
                    None if previous_estimated is None else previous_estimated + delta
                )
                sequence = spool.ledger_sequence + 1

            health = self._health_after_change(work, spool, new_effective)
            updated = replace(
                spool,
                updated_at=occurred_at,
                revision=spool.revision + 1,
                inventory_health=health,
                estimated_remaining=new_estimated,
                effective_remaining=new_effective,
                ledger_sequence=sequence,
            )
            entry = FilamentTransaction(
                id=EntityId.new(),
                device_id=actor_device_id,
                created_at=occurred_at,
                spool_id=spool_id,
                sequence=sequence,
                transaction_type=transaction_type,
                delta=delta,
                previous_effective=previous_effective,
                new_effective=new_effective,
                command_key=command_key,
                command_item=0,
                source_type="MANUAL",
                confidence_bp=10_000,
                previous_estimated=previous_estimated,
                new_estimated=new_estimated,
                estimate_policy_version="manual-v1",
            )
            work.ledger.append(entry)
            work.spools.save(updated, spool.revision)
            self._raise_inventory_alerts(work, updated, actor_device_id, occurred_at)
            self._audit(
                work,
                actor_device_id,
                occurred_at,
                event_code,
                command_key,
                spool_id,
                fingerprint=fingerprint,
            )
            work.commit()
            return entry

    @staticmethod
    def _replay_ledger(
        work: UnitOfWork, command_key: str, event_code: str, fingerprint: str,
    ) -> FilamentTransaction | None:
        prior = work.ledger.by_command(command_key)
        events = work.audit.for_command(command_key)
        if prior is None and not events:
            return None
        if prior is None or len(events) != 1:
            raise IdempotencyConflict()
        event = events[0]
        if (
            event.event_code != event_code or event.entity_type != "spool"
            or event.entity_id != prior.spool_id
            or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
        ):
            raise IdempotencyConflict()
        return prior

    @staticmethod
    def _fingerprint(**values: str | int | bool | None) -> str:
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_purchase_profile(
        price: ExactDecimal | None, basis: Mass | None, currency: str | None,
    ) -> None:
        if any(value is not None for value in (price, basis, currency)) and any(
            value is None for value in (price, basis, currency)
        ):
            raise ValueError("spool.purchase_profile_incomplete")
        if basis is not None and basis.milligrams <= 0:
            raise ValueError("spool.purchase_basis_invalid")

    @staticmethod
    def _replay_spool(
        work: UnitOfWork, command_key: str, event_code: str,
        spool_id: EntityId, fingerprint: str,
    ) -> Spool | None:
        events = work.audit.for_command(command_key)
        if not events:
            return None
        event = events[0]
        if (
            len(events) != 1 or event.event_code != event_code
            or event.entity_type != "spool" or event.entity_id != spool_id
            or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
        ):
            raise IdempotencyConflict()
        return work.spools.get(spool_id)

    @staticmethod
    def _audit(
        work: UnitOfWork,
        actor_device_id: EntityId,
        at: UtcDateTime,
        event_code: str,
        command_key: str,
        spool_id: EntityId,
        *,
        fingerprint: str | None = None,
    ) -> None:
        work.audit.append(AuditEvent(
            id=EntityId.new(),
            device_id=actor_device_id,
            created_at=at,
            event_code=event_code,
            actor_device_id=actor_device_id,
            correlation_id=command_key,
            entity_type="spool",
            entity_id=spool_id,
            parameters_json=("{}" if fingerprint is None else
                             json.dumps({"request_hash_v1": fingerprint}, sort_keys=True)),
        ))

    @staticmethod
    def _health_after_change(
        work: UnitOfWork, spool: Spool, effective: Mass | None,
    ) -> InventoryHealth:
        reserved = sum(
            claim.reserved.milligrams for claim in work.reservations.active_for_spool(spool.id)
        )
        if (
            spool.inventory_health is InventoryHealth.QUARANTINED
            or (effective is not None and effective.milligrams < 0)
            or (reserved > 0 and (effective is None or reserved > effective.milligrams))
        ):
            return InventoryHealth.QUARANTINED
        return InventoryHealth.CONSISTENT

    @staticmethod
    def _raise_inventory_alerts(
        work: UnitOfWork,
        spool: Spool,
        actor_device_id: EntityId,
        at: UtcDateTime,
    ) -> None:
        if spool.effective_remaining is None:
            return
        task_key = f"spool:{spool.id}:negative-stock"
        quarantine_key = f"spool:{spool.id}:quarantined"
        low_key = f"spool:{spool.id}:low-stock"
        shortage_key = f"spool:{spool.id}:reservation-shortage"
        reserved = sum(
            claim.reserved.milligrams for claim in work.reservations.active_for_spool(spool.id)
        )
        shortage_task = work.reconciliations.open_task_by_dedupe(shortage_key)
        if reserved > 0 and reserved > spool.effective_remaining.milligrams:
            if shortage_task is None:
                shortage_task = ReconciliationTask(
                    id=EntityId.new(), device_id=actor_device_id, created_at=at,
                    updated_at=at, revision=1, reason_code="RESERVATION_SHORTAGE",
                    severity=Severity.ERROR, state=ReconciliationState.OPEN,
                    dedupe_key=shortage_key, spool_id=spool.id,
                    suggested_action="reconcile_reserved_stock",
                )
                work.reconciliations.add_task(shortage_task)
        if spool.inventory_health is InventoryHealth.QUARANTINED:
            task = work.reconciliations.open_task_by_dedupe(task_key)
            if spool.effective_remaining.milligrams >= 0 and shortage_task is not None:
                task = shortage_task
            if task is None:
                negative = spool.effective_remaining.milligrams < 0
                task = ReconciliationTask(
                    id=EntityId.new(), device_id=actor_device_id, created_at=at,
                    updated_at=at, revision=1,
                    reason_code="inventory.negative_stock" if negative else "inventory.review_required",
                    severity=Severity.ERROR, state=ReconciliationState.OPEN,
                    dedupe_key=task_key, spool_id=spool.id,
                    suggested_action="verify_physical_stock",
                )
                work.reconciliations.add_task(task)
            if work.alerts.open_by_dedupe(quarantine_key) is None:
                work.alerts.add(AlertEvent(
                    id=EntityId.new(), device_id=actor_device_id, created_at=at,
                    updated_at=at, revision=1, severity=Severity.ERROR,
                    message_key="inventory.spool_quarantined", dedupe_key=quarantine_key,
                    raised_at=at, reconciliation_task_id=task.id, spool_id=spool.id,
                ))
            InventoryCommands._resolve_alert(work, low_key, at)
        elif (
            spool.low_threshold is not None
            and spool.effective_remaining.milligrams <= spool.low_threshold.milligrams
        ):
            InventoryCommands._resolve_reconciliation(
                work, task_key, actor_device_id, at, "balance_recovered"
            )
            InventoryCommands._resolve_alert(work, quarantine_key, at)
            if work.alerts.open_by_dedupe(low_key) is None:
                work.alerts.add(AlertEvent(
                    id=EntityId.new(), device_id=actor_device_id, created_at=at,
                    updated_at=at, revision=1, severity=Severity.WARNING,
                    message_key="inventory.low_stock", dedupe_key=low_key,
                    raised_at=at, spool_id=spool.id,
                ))
        else:
            InventoryCommands._resolve_reconciliation(
                work, task_key, actor_device_id, at, "balance_recovered"
            )
            InventoryCommands._resolve_alert(work, quarantine_key, at)
            InventoryCommands._resolve_alert(work, low_key, at)

    @staticmethod
    def _resolve_alert(work: UnitOfWork, dedupe_key: str, at: UtcDateTime) -> None:
        alert = work.alerts.open_by_dedupe(dedupe_key)
        if alert is not None:
            work.alerts.save(
                replace(
                    alert, resolved_at=at, updated_at=at, revision=alert.revision + 1,
                ),
                alert.revision,
            )

    @staticmethod
    def _resolve_reconciliation(
        work: UnitOfWork,
        dedupe_key: str,
        actor_device_id: EntityId,
        at: UtcDateTime,
        notes: str,
    ) -> None:
        task = work.reconciliations.open_task_by_dedupe(dedupe_key)
        if task is not None:
            work.reconciliations.save_task(
                replace(
                    task, state=ReconciliationState.RESOLVED, resolved_at=at,
                    resolved_by=actor_device_id, resolution_notes=notes,
                    updated_at=at, revision=task.revision + 1,
                ),
                task.revision,
            )
