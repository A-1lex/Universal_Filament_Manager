"""Phase 5 reservation lifecycle and writer-race acceptance tests."""

import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from sqlalchemy import insert, select, update

from ufm.application.inventory import InventoryCommands
from ufm.application.ports.persistence import (
    IdempotencyConflict,
    PersistenceError,
    ReservationCapacityExceeded,
)
from ufm.application.reservations import ReservationCommands
from ufm.application.topology import TopologyCommands
from ufm.domain.enums import ReservationState
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models.accounting import finalization_record, reservation
from ufm.infrastructure.persistence.models.ledger import audit_event
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


class ReservationCommandTests(unittest.TestCase):
    def test_three_command_families_cannot_commit_one_shared_key(self) -> None:
        topology = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))
        inventory = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        slot_id = EntityId.new()
        topology.create_external_slot(
            system_id=EntityId.new(), slot_id=slot_id, printer_id=self.printer_id,
            system_name="External", slot_key="external", actor_device_id=self.device,
            command_key="race-slot", at=self.now,
        )
        barrier = Barrier(3)

        def execute(index: int) -> str:
            barrier.wait(timeout=10)
            try:
                if index == 0:
                    inventory.adjust(
                        spool_id=self.spool_id, delta=Mass(-1), actor_device_id=self.device,
                        command_key="shared-family-key",
                    )
                elif index == 1:
                    self.commands.reserve(
                        reservation_id=EntityId.new(), spool_id=self.spool_id,
                        material_id=self.materials[0], amount=Mass(100), activate=False,
                        actor_device_id=self.device, command_key="shared-family-key",
                    )
                else:
                    topology.mount_spool(
                        mount_id=EntityId.new(), slot_id=slot_id, spool_id=self.spool_id,
                        actor_device_id=self.device, command_key="shared-family-key",
                    )
            except IdempotencyConflict:
                return "conflict"
            return str(index)

        with ThreadPoolExecutor(max_workers=3) as executor:
            outcomes = list(executor.map(execute, range(3)))
        self.assertEqual(outcomes.count("conflict"), 2)
        winner = next(value for value in outcomes if value != "conflict")
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.audit.for_command("shared-family-key")), 1)
            self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 2 if winner == "0" else 1)
            self.assertEqual(work.spools.get(self.spool_id).effective_remaining,
                             Mass(699 if winner == "0" else 700))
            self.assertEqual(work.mounts.active_for_slot(slot_id) is not None, winner == "2")
        with self.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(reservation)).all()),
                             1 if winner == "1" else 0)

    def test_process_exit_reservation_recovery_preserves_capacity_and_receipt(self) -> None:
        reservation_id = EntityId.new()
        worker = '''
import os
import sys
from pathlib import Path
from ufm.application.reservations import ReservationCommands
from ufm.domain.value_objects import EntityId, Mass
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
engine = create_sqlite_engine(Path(sys.argv[1]))
original = SQLiteUnitOfWork.commit
def crash_commit(self):
    if sys.argv[2] == "after":
        original(self)
    os._exit(39)
SQLiteUnitOfWork.commit = crash_commit
ids = [EntityId.parse(value) for value in sys.argv[3:]]
ReservationCommands(lambda: SQLiteUnitOfWork(engine)).reserve(
    reservation_id=ids[0], spool_id=ids[1], material_id=ids[2], actor_device_id=ids[3],
    amount=Mass(420), activate=True, expected_spool_revision=2, command_key="crash-reserve",
)
'''
        database = str(self.engine.url.database)
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                result = subprocess.run(
                    [sys.executable, "-c", worker, database, boundary,
                     *map(str, (reservation_id, self.spool_id, self.materials[0], self.device))],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 39, result.stderr)
                reopened = create_sqlite_engine(Path(database))
                try:
                    def factory(engine=reopened):
                        return SQLiteUnitOfWork(engine)
                    inventory = InventoryCommands(factory)
                    self.assertEqual(inventory.availability(self.spool_id).available,
                                     Mass(700 if boundary == "before" else 280))
                    with factory() as work:
                        self.assertEqual(len(work.audit.for_command("crash-reserve")),
                                         0 if boundary == "before" else 1)
                    if boundary == "after":
                        replay = ReservationCommands(factory).reserve(
                            reservation_id=reservation_id, spool_id=self.spool_id,
                            material_id=self.materials[0], actor_device_id=self.device,
                            amount=Mass(420), activate=True, expected_spool_revision=2,
                            command_key="crash-reserve",
                        )
                        self.assertEqual(replay.id, reservation_id)
                        self.assertEqual(inventory.availability(self.spool_id).available, Mass(280))
                        with factory() as work:
                            self.assertEqual(len(work.reservations.active_for_spool(self.spool_id)), 1)
                            self.assertEqual(len(work.audit.for_command("crash-reserve")), 1)
                finally:
                    reopened.dispose()

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="ufm-reservation-commands-")
        self.addCleanup(directory.cleanup)
        self.engine = create_sqlite_engine(Path(directory.name) / "test.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.device, profile_id, self.spool_id = EntityId.new(), EntityId.new(), EntityId.new()
        self.printer_id, self.job_id = EntityId.new(), EntityId.new()
        self.materials = (EntityId.new(), EntityId.new(), EntityId.new())
        self.now = UtcDateTime.now()
        common = dict(
            device_id=self.device, created_at=self.now, updated_at=self.now, revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(insert(device_identity).values(
                id=self.device, name="test", public_id=str(self.device), created_at=self.now,
            ))
            connection.execute(insert(filament_profile).values(
                **common, id=profile_id, name="PLA", material_type="PLA",
                diameter_mm=ExactDecimal.parse("1.75"),
            ))
            connection.execute(insert(printer).values(
                **common, id=self.printer_id, name="P1S", enabled=True,
            ))
            connection.execute(insert(print_job).values(
                **common, id=self.job_id, printer_id=self.printer_id,
                source_type="manual", status="DETECTED",
                finalization_state="NOT_STARTED", detected_at=self.now,
            ))
            for index, material_id in enumerate(self.materials):
                connection.execute(insert(print_job_material).values(
                    **common, id=material_id, print_job_id=self.job_id,
                    channel_key=f"tool-{index}", tool_index=index,
                ))
        inventory = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        inventory.create_spool(
            spool_id=self.spool_id, filament_profile_id=profile_id, display_name="PLA",
            actor_device_id=self.device, command_key="create", at=self.now,
        )
        inventory.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(700), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        self.commands = ReservationCommands(lambda: SQLiteUnitOfWork(self.engine))

    def test_pending_activation_release_and_terminal_guard(self) -> None:
        reservation_id = EntityId.new()
        pending = self.commands.reserve(
            reservation_id=reservation_id, spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(420), actor_device_id=self.device,
            command_key="pending", activate=False, at=self.now,
        )
        active = self.commands.activate(
            reservation_id=reservation_id, expected_revision=pending.revision,
            expected_spool_revision=2, actor_device_id=self.device,
            command_key="activate", at=self.now,
        )
        released = self.commands.release(
            reservation_id=reservation_id, expected_revision=active.revision,
            actor_device_id=self.device, command_key="release", reason="cancelled",
            at=self.now,
        )
        self.assertEqual(released.state, ReservationState.RELEASED)
        with self.assertRaises(IdempotencyConflict):
            self.commands.release(
                reservation_id=reservation_id, expected_revision=active.revision,
                actor_device_id=self.device, command_key="release", reason="different",
                at=self.now,
            )
        with self.assertRaisesRegex(ValueError, "domain.invalid_transition"):
            self.commands.activate(
                reservation_id=reservation_id, expected_revision=released.revision,
                expected_spool_revision=2, actor_device_id=self.device,
                command_key="reactivate", at=self.now,
            )

    def test_reserve_replay_checks_full_request_not_just_amount(self) -> None:
        args = dict(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
            command_key="create-claim", activate=False, at=self.now,
        )
        pending = self.commands.reserve(**args)
        for changed in (
            {"activate": True, "expected_spool_revision": 2},
            {"expires_at": self.now}, {"command_key": "other-key"},
            {"reservation_id": EntityId.new()}, {"actor_device_id": EntityId.new()},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(IdempotencyConflict):
                    self.commands.reserve(**(args | changed))
        active = self.commands.activate(
            reservation_id=pending.id, expected_revision=pending.revision,
            expected_spool_revision=2, actor_device_id=self.device,
            command_key="activate", at=self.now,
        )
        restarted = ReservationCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.reserve(**args), active)

    def test_resize_replay_cannot_claim_an_unrelated_replacement(self) -> None:
        original = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
            command_key="original", activate=False, at=self.now,
        )
        other = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[1], amount=Mass(200), actor_device_id=self.device,
            command_key="other", activate=False, at=self.now,
        )
        with self.assertRaises(IdempotencyConflict):
            self.commands.resize(
                reservation_id=original.id, new_reservation_id=other.id, amount=Mass(200),
                expected_revision=original.revision, expected_spool_revision=2,
                actor_device_id=self.device, command_key="resize", at=self.now,
            )
        args = dict(
            reservation_id=original.id, new_reservation_id=EntityId.new(), amount=Mass(200),
            expected_revision=original.revision, expected_spool_revision=2,
            actor_device_id=self.device, command_key="resize-valid", at=self.now,
        )
        replacement = self.commands.resize(**args)
        self.assertEqual(self.commands.resize(**args), replacement)
        with self.assertRaises(IdempotencyConflict):
            self.commands.resize(**(args | {"reservation_id": other.id}))

    def test_concurrent_identical_reserve_replays_one_committed_command(self) -> None:
        barrier = Barrier(2)
        reservation_id = EntityId.new()

        def reserve_again(_: int) -> EntityId:
            barrier.wait(timeout=5)
            return self.commands.reserve(
                reservation_id=reservation_id, spool_id=self.spool_id,
                material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
                command_key="same-request", activate=True, expected_spool_revision=2,
                at=self.now,
            ).id

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(list(executor.map(reserve_again, range(2))),
                             [reservation_id, reservation_id])
        with self.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(reservation)).all()), 1)
            events = connection.execute(select(audit_event.c.parameters_json).where(
                audit_event.c.correlation_id == "same-request",
            )).scalars().all()
        self.assertEqual(len(events), 1)
        self.assertIn("request_hash_v1", events[0])
        self.assertNotIn(str(reservation_id), events[0])

    def test_failed_audit_does_not_leave_claim_or_receipt(self) -> None:
        reservation_id = EntityId.new()
        args = dict(
            reservation_id=reservation_id, spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
            activate=True, expected_spool_revision=2, at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "audit.field_invalid"):
            self.commands.reserve(**args, command_key="")
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(reservation)).all(), [])
            self.assertEqual(connection.execute(select(audit_event).where(
                audit_event.c.entity_id == str(reservation_id),
            )).all(), [])
        created = self.commands.reserve(**args, command_key="valid-retry")
        self.assertEqual(created.id, reservation_id)

    def test_legacy_reservation_without_fingerprint_is_not_a_verified_replay(self) -> None:
        reservation_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(insert(reservation).values(
                id=reservation_id, device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, spool_id=self.spool_id,
                print_job_material_id=self.materials[0], reserved_mg=Mass(100), status="PENDING",
            ))
        with self.assertRaises(IdempotencyConflict):
            self.commands.reserve(
                reservation_id=reservation_id, spool_id=self.spool_id,
                material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
                command_key="legacy-retry", activate=False, at=self.now,
            )

    def test_manual_release_preserves_claim_for_unresolved_usage(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(420), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2, at=self.now,
        )
        for fields in (
            {"status": "RUNNING"}, {"status": "PAUSED"},
            {"status": "COMPLETING"}, {"status": "COMPLETED"},
            {"status": "FAILED"}, {"status": "CANCELLED"},
            {"started_at": self.now},
            {"finalization_state": "IN_PROGRESS"},
            {"finalization_state": "NEEDS_RECONCILIATION"},
            {"finalization_state": "FINALIZED"},
        ):
            with self.subTest(fields=fields):
                with self.engine.begin() as connection:
                    connection.execute(update(print_job).where(
                        print_job.c.id == self.job_id,
                    ).values(status="DETECTED", started_at=None, finalization_state="NOT_STARTED"))
                    connection.execute(update(print_job).where(
                        print_job.c.id == self.job_id,
                    ).values(**fields))
                with self.assertRaisesRegex(ValueError, "reservation.release_job_protected"):
                    self.commands.release(
                        reservation_id=claim.id, expected_revision=claim.revision,
                        actor_device_id=self.device, command_key="release",
                        reason="manual cancellation", at=self.now,
                    )
                with SQLiteUnitOfWork(self.engine) as work:
                    self.assertEqual(work.reservations.get(claim.id), claim)

    def test_pending_claim_can_be_released_without_freeing_capacity(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(420), actor_device_id=self.device,
            command_key="pending", activate=False, at=self.now,
        )
        with self.engine.begin() as connection:
            connection.execute(update(print_job).where(
                print_job.c.id == self.job_id,
            ).values(status="RUNNING"))
        released = self.commands.release(
            reservation_id=claim.id, expected_revision=claim.revision,
            actor_device_id=self.device, command_key="release", reason="unused proposal",
            at=self.now,
        )
        self.assertEqual(released.state, ReservationState.RELEASED)
        self.assertEqual(self.commands.release(
            reservation_id=claim.id, expected_revision=claim.revision,
            actor_device_id=self.device, command_key="release", reason="unused proposal",
            at=self.now,
        ), released)

    def test_resize_cannot_reduce_claim_during_a_print(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(420), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2, at=self.now,
        )
        with self.engine.begin() as connection:
            connection.execute(update(print_job).where(
                print_job.c.id == self.job_id,
            ).values(status="RUNNING", started_at=self.now))
        with self.assertRaisesRegex(ValueError, "reservation.resize_job_protected"):
            self.commands.resize(
                reservation_id=claim.id, new_reservation_id=EntityId.new(), amount=Mass(1),
                expected_revision=claim.revision, expected_spool_revision=2,
                actor_device_id=self.device, command_key="shrink", at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.reservations.get(claim.id), claim)
            self.assertEqual(len(work.reservations.active_for_spool(self.spool_id)), 1)

    def test_resize_requires_a_new_identity(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(420), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2, at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "reservation.resize_requires_new_id"):
            self.commands.resize(
                reservation_id=claim.id, new_reservation_id=claim.id, amount=claim.reserved,
                expected_revision=claim.revision, expected_spool_revision=2,
                actor_device_id=self.device, command_key="resize", at=self.now,
            )

    def test_queued_resize_replaces_claim_and_replays_without_duplicate_capacity(self) -> None:
        for index, activate in enumerate((False, True)):
            with self.subTest(activate=activate):
                original = self.commands.reserve(
                    reservation_id=EntityId.new(), spool_id=self.spool_id,
                    material_id=self.materials[index], amount=Mass(100),
                    actor_device_id=self.device, command_key=f"original-{index}",
                    activate=activate, expected_spool_revision=2, at=self.now,
                )
                args = dict(
                    reservation_id=original.id, new_reservation_id=EntityId.new(),
                    amount=Mass(250), expected_revision=original.revision,
                    expected_spool_revision=2, actor_device_id=self.device,
                    command_key=f"resize-{index}", at=self.now,
                )
                replacement = self.commands.resize(**args)
                self.assertEqual(self.commands.resize(**args), replacement)
                self.assertEqual(replacement.state, original.state)
                with SQLiteUnitOfWork(self.engine) as work:
                    released = work.reservations.get(original.id)
                    self.assertEqual(released.state, ReservationState.RELEASED)
                    self.assertEqual(released.reserved, Mass(100))
                    active = work.reservations.active_for_spool(self.spool_id)
                    self.assertEqual(sum(item.reserved.milligrams for item in active),
                                     250 if activate else 0)
                    self.assertEqual(work.spools.get(self.spool_id).effective_remaining, Mass(700))
                    self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 1)

    def test_concurrent_writers_cannot_overbook(self) -> None:
        barrier = Barrier(2)

        def attempt(index: int) -> str:
            barrier.wait()
            try:
                self.commands.reserve(
                    reservation_id=EntityId.new(), spool_id=self.spool_id,
                    material_id=self.materials[index], amount=Mass(420),
                    actor_device_id=self.device, command_key=f"race-{index}",
                    activate=True, expected_spool_revision=2, at=self.now,
                )
            except ReservationCapacityExceeded:
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, range(2)))
        self.assertCountEqual(results, ["accepted", "rejected"])
        with self.engine.connect() as connection:
            active = connection.execute(select(reservation.c.reserved_mg).where(
                reservation.c.status == "ACTIVE",
            )).scalars().all()
        self.assertEqual(active, [Mass(420)])

    def test_expiry_protects_started_and_terminal_jobs(self) -> None:
        reservation_id = EntityId.new()
        claim = self.commands.reserve(
            reservation_id=reservation_id, spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2,
            expires_at=self.now, at=self.now,
        )
        for status in ("RUNNING", "PAUSED", "COMPLETING", "COMPLETED", "FAILED", "CANCELLED"):
            with self.subTest(status=status):
                with self.engine.begin() as connection:
                    connection.execute(update(print_job).where(
                        print_job.c.id == self.job_id,
                    ).values(status=status))
                with self.assertRaisesRegex(ValueError, "reservation.expiry_job_protected"):
                    self.commands.expire(
                        reservation_id=reservation_id, expected_revision=claim.revision,
                        actor_device_id=self.device, command_key="expire", at=self.now,
                    )
                with SQLiteUnitOfWork(self.engine) as work:
                    self.assertEqual(work.reservations.get(reservation_id), claim)

    def test_expiry_of_unused_queued_claim_is_idempotent(self) -> None:
        reservation_id = EntityId.new()
        claim = self.commands.reserve(
            reservation_id=reservation_id, spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2,
            expires_at=self.now, at=self.now,
        )
        expired = self.commands.expire(
            reservation_id=reservation_id, expected_revision=claim.revision,
            actor_device_id=self.device, command_key="expire", at=self.now,
        )
        self.assertEqual(expired.state, ReservationState.EXPIRED)
        self.assertEqual(self.commands.expire(
            reservation_id=reservation_id, expected_revision=claim.revision,
            actor_device_id=self.device, command_key="expire", at=self.now,
        ), expired)

    def test_expiry_rejects_queued_job_with_usage_or_accounting_state(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(100), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2,
            expires_at=self.now, at=self.now,
        )
        for fields in (
            {"started_at": self.now},
            {"finalization_state": "IN_PROGRESS"},
            {"finalization_state": "NEEDS_RECONCILIATION"},
            {"finalization_state": "FINALIZED"},
        ):
            with self.subTest(fields=fields):
                with self.engine.begin() as connection:
                    connection.execute(update(print_job).where(
                        print_job.c.id == self.job_id,
                    ).values(started_at=None, finalization_state="NOT_STARTED"))
                    connection.execute(update(print_job).where(
                        print_job.c.id == self.job_id,
                    ).values(**fields))
                with self.assertRaisesRegex(ValueError, "reservation.expiry_job_protected"):
                    self.commands.expire(
                        reservation_id=claim.id, expected_revision=claim.revision,
                        actor_device_id=self.device, command_key="expire", at=self.now,
                    )
                with SQLiteUnitOfWork(self.engine) as work:
                    self.assertEqual(work.reservations.get(claim.id), claim)

    def test_zero_settlement_releases_full_remainder_idempotently(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(300), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2, at=self.now,
        )
        finalization_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(
                id=finalization_id, device_id=self.device, created_at=self.now,
                print_job_id=self.job_id, idempotency_key="finalize", request_hash="request",
                result_hash="result", started_at=self.now, completed_at=self.now,
            ))
        settled = self.commands.settle(
            reservation_id=claim.id, finalization_id=finalization_id, actual=Mass(0),
            expected_revision=claim.revision, actor_device_id=self.device,
            command_key="settle", at=self.now,
        )
        replay = self.commands.settle(
            reservation_id=claim.id, finalization_id=finalization_id, actual=Mass(0),
            expected_revision=claim.revision, actor_device_id=self.device,
            command_key="settle", at=self.now,
        )
        self.assertEqual(replay, settled)
        self.assertEqual(settled.state, ReservationState.RELEASED)
        self.assertEqual(settled.allocated_consumption, Mass(0))
        self.assertEqual(settled.released, Mass(300))

    def test_resize_rechecks_capacity_and_rolls_back_original_on_failure(self) -> None:
        original = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(500), actor_device_id=self.device,
            command_key="original", activate=True, expected_spool_revision=2, at=self.now,
        )
        self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[1], amount=Mass(100), actor_device_id=self.device,
            command_key="other", activate=True, expected_spool_revision=2, at=self.now,
        )
        with self.assertRaises(PersistenceError):
            self.commands.resize(
                reservation_id=original.id, new_reservation_id=EntityId.new(),
                amount=Mass(650), expected_revision=original.revision,
                expected_spool_revision=2, actor_device_id=self.device,
                command_key="resize-too-large", at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            persisted = work.reservations.get(original.id)
        self.assertEqual(persisted.state, ReservationState.ACTIVE)
        self.assertEqual(persisted.reserved, Mass(500))

    def test_settlement_allocates_only_reserved_share_not_actual_debit(self) -> None:
        claim = self.commands.reserve(
            reservation_id=EntityId.new(), spool_id=self.spool_id,
            material_id=self.materials[0], amount=Mass(300), actor_device_id=self.device,
            command_key="reserve", activate=True, expected_spool_revision=2, at=self.now,
        )
        finalization_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(
                id=finalization_id, device_id=self.device, created_at=self.now,
                print_job_id=self.job_id, idempotency_key="finalize-large",
                request_hash="request-large", result_hash="result-large",
                started_at=self.now, completed_at=self.now,
            ))
        settled = self.commands.settle(
            reservation_id=claim.id, finalization_id=finalization_id, actual=Mass(500),
            expected_revision=claim.revision, actor_device_id=self.device,
            command_key="settle-large", at=self.now,
        )
        self.assertEqual(settled.state, ReservationState.CONSUMED)
        self.assertEqual(settled.allocated_consumption, Mass(300))
        self.assertEqual(settled.released, Mass(0))
        with self.assertRaises(IdempotencyConflict):
            self.commands.settle(
                reservation_id=claim.id, finalization_id=finalization_id, actual=Mass(501),
                expected_revision=claim.revision, actor_device_id=self.device,
                command_key="settle-large", at=self.now,
            )
        with self.engine.connect() as connection:
            ledger_rows = connection.exec_driver_sql(
                "SELECT count(*) FROM filament_transaction WHERE reservation_id IS NOT NULL"
            ).scalar_one()
        self.assertEqual(ledger_rows, 0)
