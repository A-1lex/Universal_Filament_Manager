"""Public persistence ports against a migrated, file-backed SQLite database."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from sqlalchemy import insert

from ufm.application.ports.persistence import (
    NotFound,
    PersistenceError,
    PersistenceUnavailable,
    RevisionConflict,
)
from ufm.domain.entities import FilamentTransaction, Reservation, Spool
from ufm.domain.enums import ReservationState, TransactionType
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models.schema import (
    device_identity,
    filament_profile,
    print_job,
    print_job_material,
    printer,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class UnitOfWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="ufm-uow-")
        self.addCleanup(directory.cleanup)
        self.engine = create_sqlite_engine(Path(directory.name) / "test.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.device, self.profile = EntityId.new(), EntityId.new()
        self.now = UtcDateTime.now()
        with self.engine.begin() as connection:
            connection.execute(insert(device_identity).values(id=self.device, name="test", public_id="test", created_at=self.now))
            connection.execute(insert(filament_profile).values(
                id=self.profile, device_id=self.device, created_at=self.now, updated_at=self.now,
                revision=1, name="PLA", material_type="PLA", diameter_mm=ExactDecimal.parse("1.75"),
            ))
        self.spool = Spool(id=EntityId.new(), device_id=self.device, created_at=self.now,
                           updated_at=self.now, revision=1, display_name="PLA", filament_profile_id=self.profile)

    def test_exit_without_commit_rolls_back(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(self.spool)
        with SQLiteUnitOfWork(self.engine) as work, self.assertRaises(NotFound):
            work.spools.get(self.spool.id)

    def test_commit_round_trips_unknown_stock(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(self.spool)
            work.commit()
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool.id), self.spool)

    def test_caught_database_error_prevents_partial_commit(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(self.spool)
            with self.assertRaises(PersistenceError):
                work.spools.add(self.spool)
            with self.assertRaises(PersistenceUnavailable):
                work.commit()
        with SQLiteUnitOfWork(self.engine) as work, self.assertRaises(NotFound):
            work.spools.get(self.spool.id)

    def test_stale_revision_rolls_back_earlier_update(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(self.spool)
            work.commit()
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.save(replace(self.spool, revision=2, display_name="first"), 1)
            with self.assertRaises(RevisionConflict):
                work.spools.save(replace(self.spool, revision=2, display_name="stale"), 1)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool.id), self.spool)

    def test_stock_without_ledger_is_rejected(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(replace(self.spool, effective_remaining=Mass(1000)))
            with self.assertRaises(PersistenceError):
                work.commit()
        with SQLiteUnitOfWork(self.engine) as work, self.assertRaises(NotFound):
            work.spools.get(self.spool.id)

    def test_ledger_and_projection_commit_together(self) -> None:
        spool = replace(self.spool, effective_remaining=Mass(1000000), estimated_remaining=Mass(1000000), ledger_sequence=1)
        entry = FilamentTransaction(id=EntityId.new(), device_id=self.device, created_at=self.now,
            spool_id=spool.id, sequence=1, transaction_type=TransactionType.INITIAL_STOCK,
            delta=Mass(1000000), previous_effective=None, new_effective=Mass(1000000),
            new_estimated=Mass(1000000), estimate_policy_version="opening-v1",
            command_key="opening", command_item=0, source_type="MANUAL", confidence_bp=10000)
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(spool)
            work.ledger.append(entry)
            work.commit()
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(spool.id), spool)
            self.assertEqual(work.ledger.for_spool(spool.id), [entry])

    def test_repository_requires_active_context(self) -> None:
        work = SQLiteUnitOfWork(self.engine)
        with self.assertRaises(PersistenceUnavailable):
            work.spools.get(self.spool.id)
        with work:
            work.commit()
            with self.assertRaises(PersistenceUnavailable):
                work.spools.get(self.spool.id)

    def reservation(self, amount: int) -> Reservation:
        printer_id, job_id, material_id = EntityId.new(), EntityId.new(), EntityId.new()
        common = dict(device_id=self.device, created_at=self.now, updated_at=self.now, revision=1)
        with self.engine.begin() as connection:
            connection.execute(insert(printer).values(**common, id=printer_id, name="printer", enabled=True))
            connection.execute(insert(print_job).values(**common, id=job_id, printer_id=printer_id,
                source_type="manual", status="DETECTED", finalization_state="NOT_STARTED", detected_at=self.now))
            connection.execute(insert(print_job_material).values(**common, id=material_id,
                print_job_id=job_id, channel_key="tool-0", tool_index=0))
        return Reservation(**common, id=EntityId.new(), spool_id=self.spool.id,
            print_job_material_id=material_id, reserved=Mass(amount), state=ReservationState.ACTIVE, activated_at=self.now)

    def test_unknown_balance_cannot_be_reserved(self) -> None:
        claim = self.reservation(1)
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(self.spool)
            work.commit()
        with SQLiteUnitOfWork(self.engine) as work, self.assertRaises(PersistenceError):
            work.reservations.add(claim)

    def test_capacity_accounts_for_existing_claims(self) -> None:
        self.test_ledger_and_projection_commit_together()
        first, second = self.reservation(600000), self.reservation(400001)
        with SQLiteUnitOfWork(self.engine) as work:
            work.reservations.add(first)
            work.commit()
        with SQLiteUnitOfWork(self.engine) as work, self.assertRaises(PersistenceError):
            work.reservations.add(second)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.reservations.active_for_spool(self.spool.id), [first])
