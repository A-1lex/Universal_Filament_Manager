"""One writer reservation, one transaction, explicit commit and rollback on exit."""

from collections.abc import Sequence
from types import TracebackType
from typing import Self

from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from ufm.application.ports import persistence as ports
from ufm.infrastructure.persistence.models import accounting as a
from ufm.infrastructure.persistence.models import ledger as l
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.repositories import entities as repositories
from ufm.infrastructure.persistence.repositories.core import Transaction
from ufm.infrastructure.persistence.sqlite.migrate import LATEST_REVISION


class SQLiteUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._transaction = Transaction()
        self._connection: Connection | None = None
        self.spools: ports.SpoolRepository = repositories.Spools(self._transaction)
        self.storage_locations: ports.StorageLocationRepository = repositories.StorageLocations(self._transaction)
        self.brands: ports.BrandRepository = repositories.Brands(self._transaction)
        self.filament_profiles: ports.FilamentProfileRepository = repositories.FilamentProfiles(self._transaction)
        self.sensors: ports.SensorRepository = repositories.Sensors(self._transaction)
        self.calibrations: ports.CalibrationRepository = repositories.Calibrations(self._transaction)
        self.spool_identifiers: ports.SpoolIdentifierRepository = repositories.SpoolIdentifiers(self._transaction)
        self.ledger: ports.LedgerRepository = repositories.Ledger(self._transaction)
        self.mounts: ports.MountRepository = repositories.Mounts(self._transaction)
        self.slots: ports.FeedSlotRepository = repositories.FeedSlots(self._transaction)
        self.printers: ports.PrinterRepository = repositories.Printers(self._transaction)
        self.printer_accounting_authorities: ports.PrinterAccountingAuthorityRepository = (
            repositories.PrinterAccountingAuthorities(self._transaction)
        )
        self.feed_systems: ports.FeedSystemRepository = repositories.FeedSystems(self._transaction)
        self.segments: ports.SegmentRepository = repositories.Segments(self._transaction)
        self.reservations: ports.ReservationRepository = repositories.Reservations(self._transaction)
        self.jobs: ports.JobRepository = repositories.Jobs(self._transaction)
        self.projections: ports.JobProjectionRepository = repositories.JobProjections(self._transaction)
        self.evidence: ports.EvidenceRepository = repositories.Evidence(self._transaction)
        self.decisions: ports.DecisionRepository = repositories.Decisions(self._transaction)
        self.receipts: ports.ReceiptRepository = repositories.Receipts(self._transaction)
        self.finalizations: ports.FinalizationRepository = repositories.Finalizations(self._transaction)
        self.reconciliations: ports.ReconciliationRepository = repositories.Reconciliations(self._transaction)
        self.alerts: ports.AlertRepository = repositories.Alerts(self._transaction)
        self.audit: ports.AuditRepository = repositories.Audit(self._transaction)

    def __enter__(self) -> Self:
        if self._connection is not None:
            raise ports.PersistenceUnavailable()
        try:
            self._connection = self.engine.connect()
            self._connection.exec_driver_sql("BEGIN IMMEDIATE")
            revision: Sequence[str] = self._connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalars().all()
            if revision != [LATEST_REVISION]:
                raise ports.PersistenceUnavailable()
        except (SQLAlchemyError, ports.PersistenceUnavailable):
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            raise ports.PersistenceUnavailable() from None
        self._transaction.connection = self._connection
        self._transaction.failed = False
        self._transaction.inventory_ids.clear()
        return self

    def _validate_inventory(self) -> None:
        for spool_id in self._transaction.inventory_ids:
            spool = self._transaction.execute(select(s.spool).where(s.spool.c.id == spool_id)).mappings().one()
            last = self._transaction.execute(select(l.filament_transaction).where(
                l.filament_transaction.c.spool_id == spool_id,
            ).order_by(l.filament_transaction.c.sequence.desc()).limit(1)).mappings().one_or_none()
            if last is None:
                valid = (spool["effective_remaining_mg"] is None
                         and spool["estimated_remaining_mg"] is None and spool["ledger_sequence"] == 0)
            else:
                valid = (spool["effective_remaining_mg"] == last["new_effective_mg"]
                         and spool["estimated_remaining_mg"] == last["new_estimated_mg"]
                         and spool["ledger_sequence"] == last["sequence"])
            if not valid:
                self._transaction.fail(ports.PersistenceError())
            claims = self._transaction.execute(select(a.reservation.c.reserved_mg).where(
                a.reservation.c.spool_id == spool_id, a.reservation.c.status == "ACTIVE",
            )).scalars().all()
            remaining = spool["effective_remaining_mg"]
            if claims and (remaining is None or sum(claim.milligrams for claim in claims) > remaining.milligrams):
                # Later consumption/correction workflows may retain shortages only
                # after creating a durable explicit reconciliation incident.
                task = self._transaction.execute(select(l.reconciliation_task.c.id).where(
                    l.reconciliation_task.c.spool_id == spool_id,
                    l.reconciliation_task.c.reason_code == "RESERVATION_SHORTAGE",
                    l.reconciliation_task.c.status.in_(("OPEN", "IN_REVIEW")),
                )).first()
                if task is None:
                    self._transaction.fail(ports.PersistenceError())

    def commit(self) -> None:
        if self._connection is None or self._transaction.connection is None:
            raise ports.PersistenceUnavailable()
        try:
            if self._transaction.failed:
                raise ports.PersistenceUnavailable()
            self._validate_inventory()
            self._connection.commit()
        except SQLAlchemyError:
            self.rollback()
            raise ports.PersistenceUnavailable() from None
        except ports.PersistenceError:
            self.rollback()
            raise
        finally:
            self._transaction.connection = None

    def rollback(self) -> None:
        if self._connection is not None:
            self._connection.rollback()
        self._transaction.connection = None

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        try:
            self.rollback()
        finally:
            if self._connection is not None:
                self._connection.close()
            self._connection = None


def unit_of_work(engine: Engine) -> ports.UnitOfWork:
    """The return annotation verifies the complete port implementation with mypy."""
    return SQLiteUnitOfWork(engine)
