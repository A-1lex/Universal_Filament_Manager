"""Concrete repositories implement the domain/application persistence ports."""

from typing import cast

from sqlalchemy import exists, func, insert, or_, select, update
from sqlalchemy.engine import RowMapping

from ufm.application.ports.persistence import (
    CostLedgerRecord,
    NotFound,
    PersistenceError,
    ReservationCapacityExceeded,
    RevisionConflict,
)
from ufm.domain.entities import (
    AlertEvent,
    AuditEvent,
    Brand,
    CalibrationRecord,
    ConsumptionDecision,
    ConsumptionEvidence,
    DecisionEvidence,
    ExternalEventReceipt,
    FeedSlot,
    FilamentProfile,
    FilamentTransaction,
    FinalizationRecord,
    InventoryEvidence,
    InventoryReconciliation,
    JobIdentityAlias,
    JobProjectionState,
    JobReceiptApplication,
    MaterialFeedSystem,
    MaterialUsageSegment,
    Printer,
    PrinterAccountingAuthority,
    PrintJob,
    PrintJobMaterial,
    ReconciliationTask,
    Reservation,
    SensorDevice,
    Spool,
    SpoolIdentifier,
    SpoolMount,
    StorageLocation,
)
from ufm.domain.enums import ReceiptState, ReservationState
from ufm.domain.value_objects import EntityId, UtcDateTime
from ufm.infrastructure.persistence.models import accounting as a
from ufm.infrastructure.persistence.models import ledger as l
from ufm.infrastructure.persistence.models import projection as p
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.repositories.core import MappedRepository, Transaction


class Spools(MappedRepository[Spool]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.spool, Spool, {
            "nominal_filament": "nominal_filament_mg", "empty_spool": "empty_spool_mg",
            "purchase_basis": "purchase_basis_mg",
            "estimated_remaining": "estimated_remaining_mg", "measured_remaining": "measured_remaining_mg",
            "effective_remaining": "effective_remaining_mg", "low_threshold": "low_threshold_mg",
            "storage_location_id": "storage_location_id",
        })

    def add(self, spool: Spool) -> None:
        profile = self.transaction.execute(select(s.filament_profile).where(s.filament_profile.c.id == spool.filament_profile_id)).mappings().one_or_none()
        if profile is None:
            raise NotFound()
        # Preserve the explicit catalog diameter rather than inventing one.
        self.transaction.execute(insert(s.spool).values(
            **self.values(spool), diameter_mm=profile["diameter_mm"], density_g_cm3=profile["density_g_cm3"],
        ))
        self.transaction.inventory_ids.add(spool.id)

    def save(self, spool: Spool, expected_revision: int) -> None:
        super().save(spool, expected_revision)
        self.transaction.inventory_ids.add(spool.id)


class SpoolIdentifiers(MappedRepository[SpoolIdentifier]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.spool_identifier, SpoolIdentifier)

    def by_trusted_identity(self, namespace: str, kind: str, value: str) -> SpoolIdentifier | None:
        row = self.transaction.execute(select(s.spool_identifier).where(
            s.spool_identifier.c.namespace == namespace,
            s.spool_identifier.c.kind == kind,
            s.spool_identifier.c.value == value,
            s.spool_identifier.c.verified_at.is_not(None),
            s.spool_identifier.c.retired_at.is_(None),
            s.spool_identifier.c.deleted_at.is_(None),
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class StorageLocations(MappedRepository[StorageLocation]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.storage_location, StorageLocation, {"storage_type": "type"})

    def all(self) -> list[StorageLocation]:
        rows = self.transaction.execute(select(s.storage_location).where(
            s.storage_location.c.deleted_at.is_(None),
        ).order_by(s.storage_location.c.name)).mappings()
        return [self.entity(row) for row in rows]


class Brands(MappedRepository[Brand]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.brand, Brand)

    def all(self) -> list[Brand]:
        rows = self.transaction.execute(select(s.brand).where(
            s.brand.c.deleted_at.is_(None),
        ).order_by(s.brand.c.name)).mappings()
        return [self.entity(row) for row in rows]


class FilamentProfiles(MappedRepository[FilamentProfile]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.filament_profile, FilamentProfile)

    def all(self) -> list[FilamentProfile]:
        rows = self.transaction.execute(select(s.filament_profile).where(
            s.filament_profile.c.deleted_at.is_(None),
        ).order_by(s.filament_profile.c.name)).mappings()
        return [self.entity(row) for row in rows]

    def entity(self, row: RowMapping) -> FilamentProfile:
        values = dict(row)
        for field in ("abrasive", "flexible", "hygroscopic", "soluble", "filled_material"):
            values[field] = bool(values[field])
        return super().entity(cast(RowMapping, values))


class Sensors(MappedRepository[SensorDevice]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.sensor_device, SensorDevice, {"sensor_type": "device_type"})


class Calibrations(MappedRepository[CalibrationRecord]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.calibration_record, CalibrationRecord)

    def latest_for_sensor(self, sensor_id: EntityId) -> CalibrationRecord | None:
        row = self.transaction.execute(select(s.calibration_record).where(
            s.calibration_record.c.sensor_id == sensor_id,
        ).order_by(s.calibration_record.c.version.desc()).limit(1)).mappings().one_or_none()
        return None if row is None else self.entity(row)


class Ledger(MappedRepository[FilamentTransaction]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, l.filament_transaction, FilamentTransaction, {
            "delta": "delta_mg", "previous_effective": "previous_effective_mg", "new_effective": "new_effective_mg",
            "previous_estimated": "previous_estimated_mg", "new_estimated": "new_estimated_mg",
        })

    def append(self, entry: FilamentTransaction) -> None:
        self.transaction.execute(insert(l.filament_transaction).values(
            **self.values(entry),
        ), unique=True)
        self.transaction.inventory_ids.add(entry.spool_id)

    def by_command(self, command_key: str, command_item: int = 0) -> FilamentTransaction | None:
        row = self.transaction.execute(select(l.filament_transaction).where(
            l.filament_transaction.c.command_key == command_key,
            l.filament_transaction.c.command_item == command_item,
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def compensation_for(self, transaction_id: EntityId) -> FilamentTransaction | None:
        row = self.transaction.execute(select(l.filament_transaction).where(
            l.filament_transaction.c.compensates_transaction_id == transaction_id,
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def for_command(self, command_key: str) -> list[FilamentTransaction]:
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.command_key == command_key,
        ).order_by(self.table.c.command_item)).mappings()
        return [self.entity(row) for row in rows]

    def for_job(self, job_id: EntityId) -> list[FilamentTransaction]:
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.print_job_id == job_id,
        ).order_by(self.table.c.id)).mappings()
        return [self.entity(row) for row in rows]

    def for_spool(self, spool_id: EntityId, after_sequence: int = 0) -> list[FilamentTransaction]:
        rows = self.transaction.execute(select(l.filament_transaction).where(
            l.filament_transaction.c.spool_id == spool_id, l.filament_transaction.c.sequence > after_sequence,
        ).order_by(l.filament_transaction.c.sequence)).mappings()
        return [self.entity(row) for row in rows]

    def cost_entries(
        self, started_at: UtcDateTime, until: UtcDateTime,
        printer_id: EntityId | None, limit: int,
    ) -> list[CostLedgerRecord]:
        job = s.print_job
        printer = s.printer
        spool = s.spool
        statement = select(*l.filament_transaction.c).select_from(
            l.filament_transaction.join(
                job, l.filament_transaction.c.print_job_id == job.c.id,
            ).join(printer, job.c.printer_id == printer.c.id).join(
                spool, l.filament_transaction.c.spool_id == spool.c.id,
            )
        ).where(
            l.filament_transaction.c.transaction_type == "PRINT_CONSUMPTION",
            job.c.started_at >= started_at,
            job.c.started_at < until,
        )
        if printer_id is not None:
            statement = statement.where(job.c.printer_id == printer_id)
        statement = statement.add_columns(
            job.c.started_at.label("report_started_at"),
            printer.c.name.label("report_printer_name"),
            job.c.name.label("report_job_name"),
            job.c.file_name.label("report_file_name"),
            job.c.id.label("report_job_id"),
            spool.c.display_name.label("report_spool_name"),
        )
        rows = self.transaction.execute(
            statement.order_by(job.c.started_at, l.filament_transaction.c.id).limit(limit),
        ).mappings()
        return [CostLedgerRecord(
            transaction=self.entity(row),
            print_started_at=row["report_started_at"],
            printer_name=row["report_printer_name"],
            job_name=row["report_job_name"] or row["report_file_name"] or str(row["report_job_id"]),
            spool_name=row["report_spool_name"],
        ) for row in rows]


class Mounts(MappedRepository[SpoolMount]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.spool_mount, SpoolMount)

    def active_for_spool(self, spool_id: EntityId) -> SpoolMount | None:
        row = self.transaction.execute(select(s.spool_mount).where(s.spool_mount.c.spool_id == spool_id, s.spool_mount.c.state == "ACTIVE")).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def active_for_slot(self, slot_id: EntityId) -> SpoolMount | None:
        row = self.transaction.execute(select(s.spool_mount).where(s.spool_mount.c.feed_slot_id == slot_id, s.spool_mount.c.state == "ACTIVE")).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def close(self, mount_id: EntityId, at: UtcDateTime, expected_revision: int) -> None:
        result = self.transaction.execute(update(s.spool_mount).where(
            s.spool_mount.c.id == mount_id, s.spool_mount.c.revision == expected_revision,
            s.spool_mount.c.state == "ACTIVE",
        ).values(state="CLOSED", unmounted_at=at, updated_at=at, revision=expected_revision + 1))
        if result.rowcount != 1:
            self.transaction.fail(RevisionConflict())


class FeedSlots(MappedRepository[FeedSlot]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.feed_slot, FeedSlot)

    def by_provider_key(
        self, printer_id: EntityId, provider_system_key: str, slot_key: str,
    ) -> FeedSlot | None:
        system, slot = s.material_feed_system, s.feed_slot
        row = self.transaction.execute(select(slot).join(
            system, system.c.id == slot.c.feed_system_id,
        ).where(
            system.c.printer_id == printer_id,
            system.c.provider_system_key == provider_system_key,
            system.c.deleted_at.is_(None),
            slot.c.slot_key == slot_key,
            slot.c.deleted_at.is_(None),
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class Printers(MappedRepository[Printer]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.printer, Printer)


class PrinterAccountingAuthorities(MappedRepository[PrinterAccountingAuthority]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.printer_accounting_authority, PrinterAccountingAuthority)

    def for_printer(self, printer_id: EntityId) -> PrinterAccountingAuthority | None:
        row = self.transaction.execute(select(s.printer_accounting_authority).where(
            s.printer_accounting_authority.c.printer_id == printer_id,
            s.printer_accounting_authority.c.deleted_at.is_(None),
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class FeedSystems(MappedRepository[MaterialFeedSystem]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.material_feed_system, MaterialFeedSystem)


class Segments(MappedRepository[MaterialUsageSegment]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.material_usage_segment, MaterialUsageSegment, {
            "estimated_usage": "estimated_usage_mg",
        })

    def active_for_slot(self, slot_id: EntityId) -> list[MaterialUsageSegment]:
        rows = self.transaction.execute(select(s.material_usage_segment).where(
            s.material_usage_segment.c.feed_slot_id == slot_id,
            s.material_usage_segment.c.ended_at.is_(None),
        )).mappings()
        return [self.entity(row) for row in rows]

    def for_job(self, job_id: EntityId) -> list[MaterialUsageSegment]:
        segment, material = s.material_usage_segment, s.print_job_material
        rows = self.transaction.execute(select(segment).join(
            material, material.c.id == segment.c.print_job_material_id,
        ).where(material.c.print_job_id == job_id).order_by(segment.c.id)).mappings()
        # Include closed/deleted history: silently dropping a segment would let
        # a caller finalize only part of a multi-spool job.
        return [self.entity(row) for row in rows]

    def has_unresolved_for_spool(self, spool_id: EntityId) -> bool:
        segment, material, job = s.material_usage_segment, s.print_job_material, s.print_job
        row = self.transaction.execute(select(segment.c.id).join(
            material, material.c.id == segment.c.print_job_material_id,
        ).join(job, job.c.id == material.c.print_job_id).where(
            segment.c.spool_id == spool_id,
            or_(segment.c.ended_at.is_(None), job.c.finalization_state != "FINALIZED"),
        ).limit(1)).first()
        return row is not None

    def active_for_material(self, material_id: EntityId) -> MaterialUsageSegment | None:
        row = self.transaction.execute(select(s.material_usage_segment).where(
            s.material_usage_segment.c.print_job_material_id == material_id,
            s.material_usage_segment.c.ended_at.is_(None),
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class Reservations(MappedRepository[Reservation]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, a.reservation, Reservation, {
            "reserved": "reserved_mg", "state": "status", "allocated_consumption": "allocated_consumption_mg", "released": "released_mg",
        })

    def active_for_spool(self, spool_id: EntityId) -> list[Reservation]:
        rows = self.transaction.execute(select(a.reservation).where(a.reservation.c.spool_id == spool_id, a.reservation.c.status == "ACTIVE")).mappings()
        return [self.entity(row) for row in rows]

    def for_material(self, material_id: EntityId) -> list[Reservation]:
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.print_job_material_id == material_id,
        ).order_by(self.table.c.id)).mappings()
        return [self.entity(row) for row in rows]

    def for_finalization(self, finalization_id: EntityId) -> list[Reservation]:
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.settled_finalization_id == finalization_id,
        ).order_by(self.table.c.id)).mappings()
        return [self.entity(row) for row in rows]

    def add(self, reservation: Reservation) -> None:
        if reservation.state is ReservationState.ACTIVE:
            self._check_capacity(reservation)
        super().add(reservation)
        self.transaction.inventory_ids.add(reservation.spool_id)

    def save(self, reservation: Reservation, expected_revision: int) -> None:
        current = self.get(reservation.id)
        if reservation.state is ReservationState.ACTIVE and current.state is not ReservationState.ACTIVE:
            self._check_capacity(reservation)
        super().save(reservation, expected_revision)
        self.transaction.inventory_ids.add(reservation.spool_id)

    def _check_capacity(self, reservation: Reservation) -> None:
        spool = self.transaction.execute(select(s.spool).where(
            s.spool.c.id == reservation.spool_id,
        )).mappings().one_or_none()
        if spool is None or spool["effective_remaining_mg"] is None:
            self.transaction.fail(PersistenceError())
        if spool["inventory_health"] != "CONSISTENT" or spool["lifecycle"] == "ARCHIVED":
            self.transaction.fail(PersistenceError())
        committed = sum(item.reserved.milligrams for item in self.active_for_spool(reservation.spool_id))
        if committed + reservation.reserved.milligrams > spool["effective_remaining_mg"].milligrams:
            self.transaction.fail(ReservationCapacityExceeded())


class Jobs(MappedRepository[PrintJob]):
    def active_for_printer(self, printer_id: EntityId) -> list[PrintJob]:
        rows = self.transaction.execute(select(s.print_job).where(
            s.print_job.c.printer_id == printer_id, s.print_job.c.deleted_at.is_(None),
            s.print_job.c.status.in_(("DETECTED", "PREPARING", "RUNNING", "PAUSED", "COMPLETING")),
        ).limit(1025)).mappings().all()
        if len(rows) > 1024:
            raise PersistenceError()
        return [self.entity(row) for row in rows]

    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.print_job, PrintJob)
        self.aliases = MappedRepository(transaction, s.job_identity_alias, JobIdentityAlias, {"provider_instance_id": "provider"})

    def get_material(self, material_id: EntityId) -> PrintJobMaterial:
        materials = MappedRepository(self.transaction, s.print_job_material, PrintJobMaterial, {
            "estimated_mass": "estimated_mg",
        })
        return materials.get(material_id)

    def materials_for_job(self, job_id: EntityId) -> list[PrintJobMaterial]:
        materials = MappedRepository(self.transaction, s.print_job_material, PrintJobMaterial, {
            "estimated_mass": "estimated_mg",
        })
        rows = self.transaction.execute(select(s.print_job_material).where(
            s.print_job_material.c.print_job_id == job_id,
        ).order_by(s.print_job_material.c.id)).mappings()
        return [materials.entity(row) for row in rows]

    def aliases_for_job(self, job_id: EntityId) -> list[JobIdentityAlias]:
        rows = self.transaction.execute(select(s.job_identity_alias).where(
            s.job_identity_alias.c.print_job_id == job_id,
        ).order_by(s.job_identity_alias.c.id)).mappings()
        return [self.aliases.entity(row) for row in rows]

    def add_alias(self, alias: JobIdentityAlias) -> None:
        self.transaction.execute(insert(s.job_identity_alias).values(**self.aliases.values(alias)), unique=True)

    def by_alias(self, alias: JobIdentityAlias) -> PrintJob | None:
        table = s.job_identity_alias
        row = self.transaction.execute(select(s.print_job).join(table, table.c.print_job_id == s.print_job.c.id).where(
            table.c.provider == alias.provider_instance_id, table.c.printer_id == alias.printer_id,
            table.c.source_type == alias.source_type, table.c.source_epoch == alias.source_epoch,
            table.c.occurrence_key == alias.occurrence_key,
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def by_occurrence_scope(
        self, provider_instance_id: EntityId, printer_id: EntityId,
        source_type: str, source_epoch: str, occurrence_key: str,
    ) -> PrintJob | None:
        table = s.job_identity_alias
        row = self.transaction.execute(select(s.print_job).join(
            table, table.c.print_job_id == s.print_job.c.id,
        ).where(
            table.c.provider == provider_instance_id, table.c.printer_id == printer_id,
            table.c.source_type == source_type, table.c.source_epoch == source_epoch,
            table.c.occurrence_key == occurrence_key,
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def for_material(self, material_id: EntityId) -> PrintJob:
        material = s.print_job_material
        row = self.transaction.execute(select(s.print_job).join(
            material, material.c.print_job_id == s.print_job.c.id,
        ).where(material.c.id == material_id)).mappings().one_or_none()
        if row is None:
            raise NotFound()
        return self.entity(row)


class JobProjections:
    def __init__(self, transaction: Transaction) -> None:
        self.states = MappedRepository(transaction, p.job_projection_state, JobProjectionState)
        self.applications = MappedRepository(transaction, p.job_receipt_application, JobReceiptApplication)
        self.receipts = MappedRepository(transaction, s.external_event_receipt, ExternalEventReceipt,
            {"provider_instance_id": "provider", "state": "processing_result"})

    def for_job(self, job_id: EntityId) -> JobProjectionState | None:
        row = self.states.transaction.execute(select(p.job_projection_state).where(
            p.job_projection_state.c.print_job_id == job_id)).mappings().one_or_none()
        return None if row is None else self.states.entity(row)

    def by_receipt(self, receipt_id: EntityId) -> JobReceiptApplication | None:
        row = self.applications.transaction.execute(select(p.job_receipt_application).where(
            p.job_receipt_application.c.receipt_id == receipt_id)).mappings().one_or_none()
        return None if row is None else self.applications.entity(row)

    def applications_for_job(self, job_id: EntityId, limit: int) -> list[JobReceiptApplication]:
        if type(limit) is not int or not 1 <= limit <= 10_001:
            raise PersistenceError()
        rows = self.applications.transaction.execute(select(p.job_receipt_application).where(
            p.job_receipt_application.c.print_job_id == job_id,
        ).order_by(p.job_receipt_application.c.created_at, p.job_receipt_application.c.id).limit(limit)
        ).mappings().all()
        return [self.applications.entity(row) for row in rows]

    def pending(self, limit: int) -> list[ExternalEventReceipt]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise PersistenceError()
        receipt = s.external_event_receipt
        blocked = exists(select(l.reconciliation_task.c.id).where(
            l.reconciliation_task.c.dedupe_key.in_((
                func.printf("receipt:%s:payload_conflict", receipt.c.id),
                func.printf("receipt:%s:projection_rejected", receipt.c.id))),
            l.reconciliation_task.c.status.in_(("OPEN", "IN_REVIEW")),
        ))
        applied = exists(select(p.job_receipt_application.c.id).where(
            p.job_receipt_application.c.receipt_id == receipt.c.id))
        rows = self.receipts.transaction.execute(select(receipt).join(
            s.printer, s.printer.c.id == receipt.c.printer_id).where(
            s.printer.c.deleted_at.is_(None), s.printer.c.enabled.is_(True),
            receipt.c.deleted_at.is_(None), receipt.c.sanitized_metadata.is_not(None),
            receipt.c.processing_result == "PENDING", ~applied, ~blocked,
            receipt.c.event_type.in_(("PRINT_STARTED", "PRINT_RUNNING", "PRINT_PAUSED",
                                    "PRINT_COMPLETED", "PRINT_FAILED", "PRINT_CANCELLED")),
        ).order_by(receipt.c.received_at, receipt.c.id).limit(limit)).mappings().all()
        return [self.receipts.entity(row) for row in rows]

    def add_state(self, state: JobProjectionState) -> None:
        self.states.add(state)

    def save_state(self, state: JobProjectionState, expected_revision: int) -> None:
        original = self.states.get(state.id)
        terminal_fields = ("last_receipt_id", "observed_state", "observed_at", "source_sequence",
                           "completed_layers", "first_terminal_receipt_id", "first_terminal_state", "terminal_seen_at")
        if (original.print_job_id != state.print_job_id
                or (original.first_terminal_receipt_id is not None and any(
                    getattr(original, key) != getattr(state, key) for key in terminal_fields))):
            self.states.transaction.fail(PersistenceError())
        self.states.save(state, expected_revision)

    def add_application(self, application: JobReceiptApplication) -> None:
        self.applications.add(application)


class Evidence:
    def __init__(self, transaction: Transaction) -> None:
        self.consumption = MappedRepository(transaction, a.consumption_evidence, ConsumptionEvidence, {"source": "source_type", "mass": "weight_mg"})
        self.inventory = MappedRepository(transaction, s.inventory_evidence, InventoryEvidence, {"source": "source_type", "gross": "gross_mg", "tare": "tare_mg", "net": "net_mg"})

    def add_consumption(self, evidence: ConsumptionEvidence) -> None:
        self.consumption.add(evidence)

    def get_consumption(self, evidence_id: EntityId) -> ConsumptionEvidence:
        return self.consumption.get(evidence_id)

    def get_inventory(self, evidence_id: EntityId) -> InventoryEvidence:
        return self.inventory.get(evidence_id)

    def inventory_for_spool(self, spool_id: EntityId) -> list[InventoryEvidence]:
        rows = self.inventory.transaction.execute(select(s.inventory_evidence).where(
            s.inventory_evidence.c.spool_id == spool_id,
        ).order_by(
            s.inventory_evidence.c.captured_at.desc(), s.inventory_evidence.c.id.desc(),
        ).limit(100)).mappings().all()
        return [self.inventory.entity(row) for row in rows]

    def add_inventory(self, evidence: InventoryEvidence) -> None:
        self.inventory.add(evidence)


class Decisions(MappedRepository[ConsumptionDecision]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, a.consumption_decision, ConsumptionDecision, {"selected_mass": "selected_weight_mg"})

    def for_finalization(self, finalization_id: EntityId) -> list[ConsumptionDecision]:
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.finalization_record_id == finalization_id,
        ).order_by(self.table.c.id)).mappings()
        return [self.entity(row) for row in rows]

    def add_evidence_link(self, link: DecisionEvidence) -> None:
        MappedRepository(self.transaction, a.decision_evidence, DecisionEvidence).add(link)

    def evidence_links_for_finalization(self, finalization_id: EntityId) -> list[DecisionEvidence]:
        repository = MappedRepository(self.transaction, a.decision_evidence, DecisionEvidence)
        rows = self.transaction.execute(select(a.decision_evidence).join(
            a.consumption_decision, a.decision_evidence.c.decision_id == a.consumption_decision.c.id,
        ).where(a.consumption_decision.c.finalization_record_id == finalization_id)
            .order_by(a.decision_evidence.c.id)).mappings()
        return [repository.entity(row) for row in rows]


class Receipts(MappedRepository[ExternalEventReceipt]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, s.external_event_receipt, ExternalEventReceipt, {"provider_instance_id": "provider", "state": "processing_result"})

    def add_pending(self, receipt: ExternalEventReceipt) -> None:
        if receipt.state is not ReceiptState.PENDING:
            self.transaction.fail(PersistenceError())
        self.transaction.execute(insert(s.external_event_receipt).values(**self.values(receipt)), unique=True)

    def pending(self, limit: int = 100) -> list[ExternalEventReceipt]:
        if type(limit) is not int or not 1 <= limit <= 500:
            self.transaction.fail(PersistenceError())
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.processing_result == "PENDING", self.table.c.deleted_at.is_(None),
        ).order_by(self.table.c.received_at, self.table.c.id).limit(limit)).mappings()
        return [self.entity(row) for row in rows]

    def save(self, receipt: ExternalEventReceipt, expected_revision: int) -> None:
        original = self.get(receipt.id)
        identity = ("provider_instance_id", "printer_id", "source_epoch", "event_key", "event_type",
                    "payload_hash", "received_at", "sanitized_metadata")
        if any(getattr(original, key) != getattr(receipt, key) for key in identity):
            self.transaction.fail(PersistenceError())
        super().save(receipt, expected_revision)

    def by_scoped_key(self, provider_instance_id: EntityId, printer_id: EntityId, source_epoch: str, event_key: str) -> ExternalEventReceipt | None:
        table = s.external_event_receipt
        row = self.transaction.execute(select(table).where(
            table.c.provider == provider_instance_id, table.c.printer_id == printer_id,
            table.c.source_epoch == source_epoch, table.c.event_key == event_key,
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class Finalizations(MappedRepository[FinalizationRecord]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, a.finalization_record, FinalizationRecord)

    def add(self, finalization: FinalizationRecord) -> None:
        self.transaction.execute(insert(self.table).values(**self.values(finalization)), unique=True)

    def by_job(self, job_id: EntityId) -> FinalizationRecord | None:
        row = self.transaction.execute(select(self.table).where(self.table.c.print_job_id == job_id)).mappings().one_or_none()
        return None if row is None else self.entity(row)

    def by_key(self, key: str) -> FinalizationRecord | None:
        row = self.transaction.execute(select(self.table).where(
            self.table.c.idempotency_key == key,
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class Reconciliations:
    def __init__(self, transaction: Transaction) -> None:
        self.tasks = MappedRepository(transaction, l.reconciliation_task, ReconciliationTask, {"state": "status"})
        self.inventory = MappedRepository(transaction, a.inventory_reconciliation, InventoryReconciliation, {
            "accepted_remaining": "accepted_remaining_mg", "previous_effective": "previous_effective_mg",
            "estimated_before": "estimated_before_mg", "estimated_after": "estimated_after_mg",
        })

    def open_tasks_for_spool(self, spool_id: EntityId) -> list[ReconciliationTask]:
        rows = self.tasks.transaction.execute(select(l.reconciliation_task).where(
            l.reconciliation_task.c.spool_id == spool_id,
            l.reconciliation_task.c.status.in_(("OPEN", "IN_REVIEW")),
        )).mappings().all()
        return [self.tasks.entity(row) for row in rows]

    def get(self, task_id: EntityId) -> ReconciliationTask:
        return self.tasks.get(task_id)

    def inventory_for_evidence(self, evidence_id: EntityId) -> InventoryReconciliation | None:
        row = self.inventory.transaction.execute(select(a.inventory_reconciliation).where(
            a.inventory_reconciliation.c.evidence_id == evidence_id,
        )).mappings().one_or_none()
        return None if row is None else self.inventory.entity(row)

    def open_task_by_dedupe(self, dedupe_key: str) -> ReconciliationTask | None:
        row = self.tasks.transaction.execute(select(l.reconciliation_task).where(
            l.reconciliation_task.c.dedupe_key == dedupe_key,
            l.reconciliation_task.c.status.in_(("OPEN", "IN_REVIEW")),
        )).mappings().one_or_none()
        return None if row is None else self.tasks.entity(row)

    def add_task(self, task: ReconciliationTask) -> None:
        self.tasks.add(task)

    def save_task(self, task: ReconciliationTask, expected_revision: int) -> None:
        self.tasks.save(task, expected_revision)

    def add_inventory(self, reconciliation: InventoryReconciliation) -> None:
        self.inventory.add(reconciliation)


class Alerts(MappedRepository[AlertEvent]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, l.alert_event, AlertEvent)

    def open_by_dedupe(self, dedupe_key: str) -> AlertEvent | None:
        row = self.transaction.execute(select(l.alert_event).where(
            l.alert_event.c.dedupe_key == dedupe_key,
            l.alert_event.c.resolved_at.is_(None),
        )).mappings().one_or_none()
        return None if row is None else self.entity(row)


class Audit(MappedRepository[AuditEvent]):
    def __init__(self, transaction: Transaction) -> None:
        super().__init__(transaction, l.audit_event, AuditEvent)

    def for_command(self, command_key: str) -> list[AuditEvent]:
        rows = self.transaction.execute(select(self.table).where(
            self.table.c.correlation_id == command_key,
        ).limit(2)).mappings()
        return [AuditEvent(
            id=row["id"], device_id=row["device_id"], created_at=row["created_at"],
            event_code=row["event_code"], actor_device_id=row["actor_device_id"],
            correlation_id=row["correlation_id"], entity_type=row["entity_type"],
            entity_id=EntityId.parse(row["entity_id"]), parameters_json=row["parameters_json"],
        ) for row in rows]

    def append(self, event: AuditEvent) -> None:
        values = self.values(event)
        values["entity_id"] = str(event.entity_id)
        self.transaction.execute(insert(self.table).values(**values))
