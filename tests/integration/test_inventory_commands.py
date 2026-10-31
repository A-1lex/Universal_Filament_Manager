"""Phase 3 inventory commands through the real SQLite unit of work."""

import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import insert, select, update

from ufm.application.dto import Observed, WeightReading
from ufm.application.inventory import InventoryCommands
from ufm.application.ports.persistence import IdempotencyConflict, NotFound, RevisionConflict
from ufm.domain.entities import Spool, SpoolIdentifier
from ufm.domain.enums import (
    Availability,
    EvidenceSource,
    InventoryHealth,
    StockLevel,
    TransactionType,
)
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models.accounting import reservation
from ufm.infrastructure.persistence.models.ledger import alert_event, reconciliation_task
from ufm.infrastructure.persistence.models.schema import (
    calibration_record,
    device_identity,
    feed_slot,
    filament_profile,
    material_feed_system,
    print_job,
    print_job_material,
    printer,
    sensor_device,
    spool_mount,
)
from ufm.infrastructure.persistence.models.schema import spool as spool_table
from ufm.infrastructure.persistence.models.schema import (
    spool_identifier as spool_identifier_table,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class InventoryCommandTests(unittest.TestCase):
    def _scale_setup(
        self, *, enabled: bool = True, expires_at: UtcDateTime | None = None,
        second_version: bool = False,
    ) -> tuple[EntityId, EntityId, int]:
        sensor_id, calibration_id = EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device, created_at=self.now, updated_at=self.now, revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(insert(sensor_device).values(
                **common, id=sensor_id, name="Bench scale", device_type="SCALE",
                provider_type="test", enabled=enabled,
            ))
            connection.execute(insert(calibration_record).values(
                id=calibration_id, device_id=self.device, created_at=self.now,
                sensor_id=sensor_id, version=1, calibration_type="scale",
                reference_value=ExactDecimal.parse("100"), reference_unit="g",
                offset=ExactDecimal.parse("0"), scale_factor=ExactDecimal.parse("1"),
                performed_at=self.now, expires_at=expires_at,
            ))
            if second_version:
                connection.execute(insert(calibration_record).values(
                    id=EntityId.new(), device_id=self.device, created_at=self.now,
                    sensor_id=sensor_id, version=2, calibration_type="scale",
                    reference_value=ExactDecimal.parse("100"), reference_unit="g",
                    offset=ExactDecimal.parse("0"), scale_factor=ExactDecimal.parse("1"),
                    performed_at=self.now,
                ))
        return sensor_id, calibration_id, 1

    def _scale_reading(
        self, sensor_id: EntityId, calibration_id: EntityId, version: int = 1,
        *, stable: bool = True,
    ) -> WeightReading:
        def known(value):
            return Observed(Availability.KNOWN, self.now, self.now, value)

        return WeightReading(
            sensor_id=sensor_id, associated_spool_id=self.spool_id,
            gross_mass=known(Mass(1250)), tare_mass=known(Mass(400)),
            net_mass=known(Mass(850)), stable=known(stable),
            interval_start=self.now, interval_end=self.now, observed_at=self.now,
            received_at=self.now, calibration_id=calibration_id,
            calibration_version=version,
        )

    def test_calibrated_scale_reading_is_immutable_idempotent_and_stock_neutral(self) -> None:
        sensor_id, calibration_id, version = self._scale_setup()
        reading = self._scale_reading(sensor_id, calibration_id, version)
        evidence = self.commands.record_scale_reading(
            reading=reading, actor_device_id=self.device, command_key="scale-read-1", at=self.now,
        )
        replay = self.commands.record_scale_reading(
            reading=reading, actor_device_id=self.device, command_key="scale-read-1", at=self.now,
        )
        self.assertEqual(replay, evidence)
        self.assertEqual(evidence.source, EvidenceSource.SCALE)
        self.assertEqual(evidence.net, Mass(850))
        self.assertEqual(evidence.sensor_id, sensor_id)
        self.assertEqual(evidence.calibration_id, calibration_id)
        self.assertEqual(evidence.ledger_cutoff, 0)
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.spool_id)
            self.assertIsNone(spool.effective_remaining)
            self.assertEqual(work.ledger.for_spool(self.spool_id), [])
        with self.assertRaisesRegex(ValueError, "provider_command_required"):
            self.commands.record_inventory_measurement(
                spool_id=self.spool_id, net=Mass(850), source=EvidenceSource.SCALE,
                sensor_id=sensor_id, calibration_id=calibration_id,
                actor_device_id=self.device, command_key="scale-bypass", at=self.now,
            )

    def test_scale_capture_rejects_unstable_unknown_and_noncurrent_calibration(self) -> None:
        sensor_id, calibration_id, version = self._scale_setup(second_version=True)
        with self.assertRaisesRegex(ValueError, "scale_reading_unstable"):
            self.commands.record_scale_reading(
                reading=self._scale_reading(sensor_id, calibration_id, version, stable=False),
                actor_device_id=self.device, command_key="scale-unstable", at=self.now,
            )
        reading = self._scale_reading(sensor_id, calibration_id, version)
        unknown = Observed[Mass](Availability.UNKNOWN, self.now, self.now)
        with self.assertRaisesRegex(ValueError, "scale_measurements_incomplete"):
            self.commands.record_scale_reading(
                reading=WeightReading(
                    sensor_id=reading.sensor_id, associated_spool_id=reading.associated_spool_id,
                    gross_mass=unknown, tare_mass=reading.tare_mass, net_mass=reading.net_mass,
                    stable=reading.stable, interval_start=reading.interval_start,
                    interval_end=reading.interval_end, observed_at=reading.observed_at,
                    received_at=reading.received_at, calibration_id=reading.calibration_id,
                    calibration_version=reading.calibration_version,
                ), actor_device_id=self.device, command_key="scale-unknown", at=self.now,
            )
        with self.assertRaisesRegex(ValueError, "calibration_not_current"):
            self.commands.record_scale_reading(
                reading=reading, actor_device_id=self.device, command_key="scale-old-cal", at=self.now,
            )

    def test_scale_capture_rejects_disabled_sensor_and_expired_calibration(self) -> None:
        disabled_id, disabled_cal, version = self._scale_setup(enabled=False)
        with self.assertRaisesRegex(ValueError, "scale_sensor_unavailable"):
            self.commands.record_scale_reading(
                reading=self._scale_reading(disabled_id, disabled_cal, version),
                actor_device_id=self.device, command_key="scale-disabled", at=self.now,
            )

        # Persist an expiry preceding performed_at is forbidden by the schema; use a
        # future capture against a calibration that expires before that capture.
        sensor_id, calibration_id, version = self._scale_setup(
            expires_at=UtcDateTime(self.now.value + timedelta(seconds=1)),
        )
        future = UtcDateTime(self.now.value + timedelta(seconds=2))
        def known(value):
            return Observed(Availability.KNOWN, future, future, value)
        reading = WeightReading(
            sensor_id=sensor_id, associated_spool_id=self.spool_id,
            gross_mass=known(Mass(1250)), tare_mass=known(Mass(400)),
            net_mass=known(Mass(850)), stable=known(True),
            interval_start=future, interval_end=future, observed_at=future, received_at=future,
            calibration_id=calibration_id, calibration_version=version,
        )
        with self.assertRaisesRegex(ValueError, "scale_calibration_expired"):
            self.commands.record_scale_reading(
                reading=reading, actor_device_id=self.device, command_key="scale-expired", at=future,
            )

    def test_scale_acceptance_rechecks_sensor_and_calibration_at_confirmation(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="scale-accept-opening",
            actor_device_id=self.device, at=self.now,
        )
        expiry = UtcDateTime(self.now.value + timedelta(seconds=1))
        sensor_id, calibration_id, version = self._scale_setup(expires_at=expiry)
        evidence = self.commands.record_scale_reading(
            reading=self._scale_reading(sensor_id, calibration_id, version),
            actor_device_id=self.device, command_key="scale-accept-evidence", at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.spool_id)
        with self.assertRaisesRegex(ValueError, "scale_calibration_expired"):
            self.commands.accept_inventory_measurement(
                spool_id=self.spool_id, evidence_id=evidence.id,
                expected_revision=spool.revision, actor_device_id=self.device,
                command_key="scale-accept-after-expiry", reason="Confirm scale measurement",
                at=UtcDateTime(self.now.value + timedelta(seconds=2)),
            )
        self.assertEqual(self.commands.availability(self.spool_id).effective, Mass(1000))
        self.assertEqual(len(self.commands.history(self.spool_id)), 1)

    def test_record_inventory_measurement_is_immutable_idempotent_and_stock_neutral(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="measurement-opening",
            actor_device_id=self.device, at=self.now,
        )
        arguments = {
            "spool_id": self.spool_id,
            "source": EvidenceSource.MANUAL,
            "gross": Mass(1250),
            "tare": Mass(400),
            "net": Mass(850),
            "actor_device_id": self.device,
            "command_key": "measurement-evidence-1",
            "captured_at": self.now,
            "at": self.now,
        }

        evidence = self.commands.record_inventory_measurement(**arguments)
        replay = self.commands.record_inventory_measurement(**arguments)

        self.assertEqual(replay, evidence)
        self.assertEqual(evidence.ledger_cutoff, 1)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.evidence.get_inventory(evidence.id), evidence)
            spool = work.spools.get(self.spool_id)
            self.assertEqual(spool.effective_remaining, Mass(1000))
            self.assertEqual(spool.measured_remaining, None)
            self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 1)
        with self.assertRaises(IdempotencyConflict):
            self.commands.record_inventory_measurement(**(arguments | {"net": Mass(851)}))

    def test_record_inventory_measurement_rejects_future_capture_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "measurement_capture_after_receive"):
            self.commands.record_inventory_measurement(
                spool_id=self.spool_id, net=Mass(100), actor_device_id=self.device,
                command_key="future-measurement",
                captured_at=UtcDateTime(self.now.value + timedelta(seconds=1)),
                at=self.now,
            )

    def test_accept_measurement_atomically_reconciles_ledger_and_is_idempotent(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="reconcile-opening",
            actor_device_id=self.device, at=self.now,
        )
        evidence = self.commands.record_inventory_measurement(
            spool_id=self.spool_id, source=EvidenceSource.MANUAL,
            gross=Mass(1250), tare=Mass(400), net=Mass(850),
            actor_device_id=self.device, command_key="reconcile-evidence",
            captured_at=self.now, at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            revision = work.spools.get(self.spool_id).revision
        arguments = {
            "spool_id": self.spool_id, "evidence_id": evidence.id,
            "expected_revision": revision, "actor_device_id": self.device,
            "command_key": "reconcile-accepted", "reason": "Physical inventory count",
            "at": self.now,
        }

        updated = self.commands.accept_inventory_measurement(**arguments)
        replay = self.commands.accept_inventory_measurement(**arguments)

        self.assertEqual(replay, updated)
        self.assertEqual(updated.effective_remaining, Mass(850))
        self.assertEqual(updated.estimated_remaining, Mass(850))
        self.assertEqual(updated.measured_remaining, Mass(850))
        history = self.commands.history(self.spool_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1].delta, Mass(-150))
        self.assertIsNotNone(history[-1].inventory_reconciliation_id)
        with SQLiteUnitOfWork(self.engine) as work:
            reconciliation = work.reconciliations.inventory_for_evidence(evidence.id)
            self.assertIsNotNone(reconciliation)
            assert reconciliation is not None
            self.assertEqual(reconciliation.accepted_ledger_cutoff, 1)
        with self.assertRaises(IdempotencyConflict):
            self.commands.accept_inventory_measurement(
                **(arguments | {"reason": "Changed request"}),
            )
        with self.assertRaisesRegex(ValueError, "measurement_already_accepted"):
            self.commands.accept_inventory_measurement(
                **(arguments | {
                    "expected_revision": updated.revision,
                    "command_key": "reconcile-second-key",
                }),
            )

    def test_measurement_reconciliation_requires_current_ledger_cutoff(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="stale-opening",
            actor_device_id=self.device, at=self.now,
        )
        evidence = self.commands.record_inventory_measurement(
            spool_id=self.spool_id, net=Mass(900), actor_device_id=self.device,
            command_key="stale-evidence", at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(50), command_key="after-measurement",
            actor_device_id=self.device, at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            revision = work.spools.get(self.spool_id).revision
        with self.assertRaisesRegex(ValueError, "measurement_ledger_stale"):
            self.commands.accept_inventory_measurement(
                spool_id=self.spool_id, evidence_id=evidence.id,
                expected_revision=revision, actor_device_id=self.device,
                command_key="stale-accept", reason="Test stale cutoff", at=self.now,
            )
        self.assertEqual(self.commands.history(self.spool_id)[-1].new_effective, Mass(1050))

    def test_measurement_below_active_reservation_is_not_accepted(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="reserved-opening",
            actor_device_id=self.device, at=self.now,
        )
        printer_id, job_id, material_id = EntityId.new(), EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device, created_at=self.now, updated_at=self.now, revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(insert(printer).values(
                **common, id=printer_id, name="P1S", enabled=True,
            ))
            connection.execute(insert(print_job).values(
                **common, id=job_id, printer_id=printer_id, source_type="manual",
                status="RUNNING", finalization_state="NOT_STARTED", detected_at=self.now,
            ))
            connection.execute(insert(print_job_material).values(
                **common, id=material_id, print_job_id=job_id,
                channel_key="tool-0", tool_index=0,
            ))
            connection.execute(insert(reservation).values(
                **common, id=EntityId.new(), spool_id=self.spool_id,
                print_job_material_id=material_id, reserved_mg=Mass(800),
                status="ACTIVE", activated_at=self.now,
            ))
        evidence = self.commands.record_inventory_measurement(
            spool_id=self.spool_id, net=Mass(700), actor_device_id=self.device,
            command_key="reserved-measurement", at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            revision = work.spools.get(self.spool_id).revision
        with self.assertRaisesRegex(ValueError, "measurement_below_reserved"):
            self.commands.accept_inventory_measurement(
                spool_id=self.spool_id, evidence_id=evidence.id,
                expected_revision=revision, actor_device_id=self.device,
                command_key="reserved-measurement-accept",
                reason="Measured mass under reserved amount", at=self.now,
            )
        self.assertEqual(self.commands.availability(self.spool_id).effective, Mass(1000))
        self.assertEqual(len(self.commands.history(self.spool_id)), 1)

    def test_measurement_zero_delta_and_measured_opening_are_valid(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(850), command_key="zero-opening",
            actor_device_id=self.device, at=self.now,
        )
        evidence = self.commands.record_inventory_measurement(
            spool_id=self.spool_id, net=Mass(850), actor_device_id=self.device,
            command_key="zero-delta-evidence", at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.spool_id)
        unchanged = self.commands.accept_inventory_measurement(
            spool_id=self.spool_id, evidence_id=evidence.id,
            expected_revision=spool.revision, actor_device_id=self.device,
            command_key="zero-delta-accept", reason="Verify scale reading", at=self.now,
        )
        self.assertEqual(unchanged.measured_remaining, Mass(850))
        self.assertEqual(unchanged.ledger_sequence, 1)
        self.assertEqual(len(self.commands.history(self.spool_id)), 1)

        unknown_id = EntityId.new()
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(Spool(
                id=unknown_id, device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, display_name="Measured empty spool",
                filament_profile_id=self.profile_id,
            ))
            work.commit()
        unknown_evidence = self.commands.record_inventory_measurement(
            spool_id=unknown_id, net=Mass(0), actor_device_id=self.device,
            command_key="measured-opening-evidence", at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            unknown_spool = work.spools.get(unknown_id)
        opened = self.commands.accept_inventory_measurement(
            spool_id=unknown_id, evidence_id=unknown_evidence.id,
            expected_revision=unknown_spool.revision, actor_device_id=self.device,
            command_key="measured-opening-accept", reason="Verified empty spool", at=self.now,
        )
        self.assertEqual(opened.effective_remaining, Mass(0))
        self.assertEqual(opened.ledger_sequence, 1)
        self.assertEqual(self.commands.history(unknown_id)[0].transaction_type,
                         TransactionType.INITIAL_STOCK)

    def test_spool_identifier_lookup_returns_only_exact_trusted_current_match(self) -> None:
        identifiers = (
            SpoolIdentifier(
                id=EntityId.new(), device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, deleted_at=None, spool_id=self.spool_id,
                namespace="bambu", kind="tray_uuid", value="tray-a",
            ),
            SpoolIdentifier(
                id=EntityId.new(), device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, deleted_at=None, spool_id=self.spool_id,
                namespace="bambu", kind="tray_uuid", value="tray-a",
                verified_at=self.now, retired_at=self.now,
            ),
            SpoolIdentifier(
                id=EntityId.new(), device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, deleted_at=None, spool_id=self.spool_id,
                namespace="bambu", kind="tray_uuid", value="tray-a",
                verified_at=self.now,
            ),
        )
        with self.engine.begin() as connection:
            connection.execute(insert(spool_identifier_table), [
                {
                    "id": item.id, "device_id": item.device_id,
                    "created_at": item.created_at, "updated_at": item.updated_at,
                    "revision": item.revision, "deleted_at": item.deleted_at,
                    "spool_id": item.spool_id, "namespace": item.namespace,
                    "kind": item.kind, "value": item.value,
                    "verified_at": item.verified_at, "retired_at": item.retired_at,
                }
                for item in identifiers
            ])

        with SQLiteUnitOfWork(self.engine) as work:
            found = work.spool_identifiers.by_trusted_identity("bambu", "tray_uuid", "tray-a")
            self.assertEqual(found, identifiers[2])
            self.assertIsNone(work.spool_identifiers.by_trusted_identity("bambu", "tray_uuid", "TRAY-A"))
            self.assertIsNone(work.spool_identifiers.by_trusted_identity("bambu", "tag_uid", "tray-a"))

    def test_process_exit_before_and_after_commit_preserves_exactly_once_adjustment(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="crash-opening",
            actor_device_id=self.device, at=self.now,
        )
        worker = '''
import os
import sys
from pathlib import Path
from ufm.application.inventory import InventoryCommands
from ufm.domain.value_objects import EntityId, Mass
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork

engine = create_sqlite_engine(Path(sys.argv[1]))
original_commit = SQLiteUnitOfWork.commit
def crash_commit(self):
    if sys.argv[4] == "after":
        original_commit(self)
    os._exit(37)
SQLiteUnitOfWork.commit = crash_commit
InventoryCommands(lambda: SQLiteUnitOfWork(engine)).adjust(
    spool_id=EntityId.parse(sys.argv[2]), actor_device_id=EntityId.parse(sys.argv[3]),
    delta=Mass(-250), command_key="crash-adjust",
)
'''
        database = str(self.engine.url.database)
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                result = subprocess.run(
                    [sys.executable, "-c", worker, database, str(self.spool_id),
                     str(self.device), boundary],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 37, result.stderr)
                reopened = create_sqlite_engine(Path(database))
                try:
                    with SQLiteUnitOfWork(reopened) as work:
                        current = work.spools.get(self.spool_id)
                        self.assertEqual(current.effective_remaining, Mass(
                            1000 if boundary == "before" else 750,
                        ))
                        self.assertEqual(len(work.ledger.for_spool(self.spool_id)),
                                         1 if boundary == "before" else 2)
                        self.assertEqual(len(work.audit.for_command("crash-adjust")),
                                         0 if boundary == "before" else 1)
                    if boundary == "after":
                        restarted = InventoryCommands(
                            lambda engine=reopened: SQLiteUnitOfWork(engine),
                        )
                        first = restarted.adjust(
                            spool_id=self.spool_id, actor_device_id=self.device,
                            delta=Mass(-250), command_key="crash-adjust",
                        )
                        self.assertEqual(first.new_effective, Mass(750))
                        self.assertEqual(len(restarted.history(self.spool_id)), 2)
                        with reopened.connect() as connection:
                            self.assertEqual(connection.exec_driver_sql(
                                "PRAGMA integrity_check",
                            ).scalar_one(), "ok")
                            self.assertEqual(connection.exec_driver_sql(
                                "PRAGMA foreign_key_check",
                            ).all(), [])
                finally:
                    reopened.dispose()

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="ufm-inventory-commands-")
        self.addCleanup(directory.cleanup)
        self.engine = create_sqlite_engine(Path(directory.name) / "test.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.device, self.profile_id, self.spool_id = (
            EntityId.new(), EntityId.new(), EntityId.new()
        )
        self.now = UtcDateTime.now()
        with self.engine.begin() as connection:
            connection.execute(insert(device_identity).values(
                id=self.device, name="test", public_id=str(self.device), created_at=self.now,
            ))
            connection.execute(insert(filament_profile).values(
                id=self.profile_id, device_id=self.device, created_at=self.now, updated_at=self.now,
                revision=1, name="PLA", material_type="PLA",
                diameter_mm=ExactDecimal.parse("1.75"),
            ))
        spool = Spool(
            id=self.spool_id, device_id=self.device, created_at=self.now,
            updated_at=self.now, revision=1, display_name="PLA",
            filament_profile_id=self.profile_id,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(spool)
            work.commit()
        self.commands = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))

    def test_opening_zero_is_known_and_idempotent(self) -> None:
        first = self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(0), command_key="opening-1",
            actor_device_id=self.device, at=self.now,
        )
        replay = self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(0), command_key="opening-1",
            actor_device_id=self.device, at=self.now,
        )
        self.assertEqual(replay, first)
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.spool_id)
            self.assertEqual(spool.effective_remaining, Mass(0))
            self.assertEqual(spool.ledger_sequence, 1)
            self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 1)

    def test_adjustment_updates_projection_and_quarantines_negative_stock(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        entry = self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-1500), command_key="adjust",
            actor_device_id=self.device, at=self.now,
        )
        self.assertEqual(entry.transaction_type, TransactionType.INVENTORY_ADJUSTMENT)
        self.assertEqual(entry.new_effective, Mass(-500))
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.spool_id)
            self.assertEqual(spool.inventory_health, InventoryHealth.QUARANTINED)
            self.assertEqual(spool.ledger_sequence, 2)

    def test_manual_deduction_is_atomic_and_cannot_exceed_stock(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening-manual-use",
            actor_device_id=self.device, at=self.now,
        )
        entry = self.commands.deduct_manual(
            spool_id=self.spool_id, amount=Mass(300), command_key="manual-use",
            actor_device_id=self.device, at=self.now,
        )
        self.assertEqual(entry.delta, Mass(-300))
        self.assertEqual(entry.new_effective, Mass(700))
        with self.assertRaisesRegex(
            ValueError, "inventory.manual_deduction_exceeds_available",
        ):
            self.commands.deduct_manual(
                spool_id=self.spool_id, amount=Mass(701), command_key="overdraw",
                actor_device_id=self.device, at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id).effective_remaining, Mass(700))
            self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 2)

    def test_unknown_stock_cannot_be_adjusted(self) -> None:
        self.assertEqual(
            self.commands.availability(self.spool_id).level,
            StockLevel.UNKNOWN,
        )
        with self.assertRaisesRegex(ValueError, "inventory.opening_required"):
            self.commands.adjust(
                spool_id=self.spool_id, delta=Mass(1), command_key="adjust",
                actor_device_id=self.device, at=self.now,
            )

    def test_ledger_replays_reject_changed_actor_and_preserve_balance(self) -> None:
        opening_args = dict(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening-identity",
            actor_device_id=self.device, at=self.now,
        )
        opening = self.commands.establish_opening_stock(**opening_args)
        adjust_args = dict(
            spool_id=self.spool_id, delta=Mass(-200), command_key="adjust-identity",
            actor_device_id=self.device, at=self.now,
        )
        adjustment = self.commands.adjust(**adjust_args)
        compensation_args = dict(
            transaction_id=adjustment.id, command_key="compensate-identity",
            actor_device_id=self.device, at=self.now,
        )
        compensation = self.commands.compensate(**compensation_args)
        restarted = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        for command, arguments, expected in (
            (restarted.establish_opening_stock, opening_args, opening),
            (restarted.adjust, adjust_args, adjustment),
            (restarted.compensate, compensation_args, compensation),
        ):
            with self.subTest(command=command.__name__):
                self.assertEqual(command(**arguments), expected)
                with self.assertRaises(IdempotencyConflict):
                    command(**(arguments | {"actor_device_id": EntityId.new()}))
        self.assertEqual(restarted.availability(self.spool_id).effective, Mass(1000))
        self.assertEqual(len(restarted.history(self.spool_id)), 3)

    def test_ledger_commands_cannot_reuse_metadata_command_key(self) -> None:
        self.commands.edit_spool(
            spool_id=self.spool_id, expected_revision=1, display_name="PLA",
            low_threshold=None, actor_device_id=self.device, command_key="metadata-key", at=self.now,
        )
        with self.assertRaises(IdempotencyConflict):
            self.commands.establish_opening_stock(
                spool_id=self.spool_id, amount=Mass(1000), command_key="metadata-key",
                actor_device_id=self.device, at=self.now,
            )
        self.assertEqual(self.commands.history(self.spool_id), ())

    def test_ledger_audit_failure_rolls_back_all_writes_and_allows_retry(self) -> None:
        common = dict(actor_device_id=self.device, at=self.now)

        def execute_with_failure_then_retry(command, arguments):
            with SQLiteUnitOfWork(self.engine) as work:
                before = work.spools.get(self.spool_id)
                history = tuple(work.ledger.for_spool(self.spool_id))
            with patch.object(InventoryCommands, "_audit", side_effect=RuntimeError("audit failpoint")):
                with self.assertRaisesRegex(RuntimeError, "audit failpoint"):
                    command(**arguments, **common)
            with SQLiteUnitOfWork(self.engine) as work:
                self.assertEqual(work.spools.get(self.spool_id), before)
                self.assertEqual(tuple(work.ledger.for_spool(self.spool_id)), history)
                self.assertEqual(work.audit.for_command(arguments["command_key"]), [])
            return command(**arguments, **common)

        execute_with_failure_then_retry(self.commands.establish_opening_stock, dict(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening-failpoint",
        ))
        adjustment = execute_with_failure_then_retry(self.commands.adjust, dict(
            spool_id=self.spool_id, delta=Mass(-200), command_key="adjust-failpoint",
        ))
        execute_with_failure_then_retry(self.commands.compensate, dict(
            transaction_id=adjustment.id, command_key="compensate-failpoint",
        ))
        self.assertEqual(self.commands.availability(self.spool_id).effective, Mass(1000))
        self.assertEqual(len(self.commands.history(self.spool_id)), 3)

    def test_concurrent_identical_adjustment_debits_once(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        barrier = Barrier(2)

        def adjust():
            commands = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
            barrier.wait(timeout=10)
            return commands.adjust(
                spool_id=self.spool_id, delta=Mass(-200), command_key="concurrent-debit",
                actor_device_id=self.device, at=self.now,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(adjust) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.commands.availability(self.spool_id).effective, Mass(800))
        self.assertEqual(len(self.commands.history(self.spool_id)), 2)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.audit.for_command("concurrent-debit")), 1)

    def test_reused_command_key_with_different_payload_is_rejected(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="same",
            actor_device_id=self.device, at=self.now,
        )
        with self.assertRaises(IdempotencyConflict):
            self.commands.establish_opening_stock(
                spool_id=self.spool_id, amount=Mass(999), command_key="same",
                actor_device_id=self.device, at=self.now,
            )

    def test_create_replay_after_edit_preserves_current_record(self) -> None:
        spool_id = EntityId.new()
        arguments = dict(
            spool_id=spool_id, filament_profile_id=self.profile_id, display_name="Original",
            actor_device_id=self.device, command_key="create-replay", low_threshold=Mass(100),
            at=self.now,
        )
        self.commands.create_spool(**arguments)
        edited = self.commands.edit_spool(
            spool_id=spool_id, expected_revision=1, display_name="Edited",
            low_threshold=Mass(200), actor_device_id=self.device, command_key="edit-replay",
            at=self.now,
        )
        restarted = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.create_spool(**arguments), edited)
        for changes in (
            {"display_name": "Edited"}, {"low_threshold": Mass(200)},
            {"command_key": "different-key"}, {"spool_id": EntityId.new()},
            {"actor_device_id": EntityId.new()}, {"nominal_filament": Mass(1000)},
        ):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                restarted.create_spool(**(arguments | changes))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(spool_id), edited)
            self.assertEqual(len(work.audit.for_command("create-replay")), 1)

    def test_create_audit_failure_rolls_back_and_allows_retry(self) -> None:
        spool_id = EntityId.new()
        arguments = dict(
            spool_id=spool_id, filament_profile_id=self.profile_id, display_name="Retry",
            actor_device_id=self.device, at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "audit.field_invalid"):
            self.commands.create_spool(**arguments, command_key="")
        with SQLiteUnitOfWork(self.engine) as work:
            with self.assertRaises(NotFound):
                work.spools.get(spool_id)
            self.assertEqual(work.audit.for_command(""), [])
        created = self.commands.create_spool(**arguments, command_key="retry-create")
        self.assertEqual(
            self.commands.create_spool(**arguments, command_key="retry-create"), created,
        )

    def test_concurrent_create_replays_one_spool_and_receipt(self) -> None:
        spool_id = EntityId.new()
        barrier = Barrier(2)

        def create() -> Spool:
            commands = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
            barrier.wait(timeout=10)
            return commands.create_spool(
                spool_id=spool_id, filament_profile_id=self.profile_id, display_name="Concurrent",
                actor_device_id=self.device, command_key="concurrent-create", at=self.now,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results[0], results[1])
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(spool_id).revision, 1)
            self.assertEqual(len(work.audit.for_command("concurrent-create")), 1)

    def test_concurrent_changed_create_rejects_conflicting_request(self) -> None:
        spool_id = EntityId.new()
        barrier = Barrier(2)

        def create(name: str) -> str:
            commands = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
            barrier.wait(timeout=10)
            try:
                commands.create_spool(
                    spool_id=spool_id, filament_profile_id=self.profile_id, display_name=name,
                    actor_device_id=self.device, command_key="conflicting-create", at=self.now,
                )
            except IdempotencyConflict:
                return "conflict"
            return name

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create, name) for name in ("First", "Second")]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results.count("conflict"), 1)
        winner = next(result for result in results if result != "conflict")
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(spool_id).display_name, winner)
            self.assertEqual(len(work.audit.for_command("conflicting-create")), 1)

    def test_edit_replay_preserves_later_changes_and_checks_request(self) -> None:
        arguments = dict(
            spool_id=self.spool_id, expected_revision=1, display_name="First edit",
            low_threshold=Mass(100), actor_device_id=self.device, command_key="edit-once",
            at=self.now,
        )
        first = self.commands.edit_spool(**arguments)
        self.assertEqual(self.commands.edit_spool(**arguments), first)
        later = self.commands.edit_spool(**(arguments | {
            "expected_revision": 2, "display_name": "Later edit", "command_key": "edit-later",
        }))
        restarted = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.edit_spool(**arguments), later)
        for changes in (
            {"expected_revision": 3}, {"display_name": "Changed"},
            {"low_threshold": None}, {"actor_device_id": EntityId.new()},
            {"spool_id": EntityId.new()},
        ):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                restarted.edit_spool(**(arguments | changes))
        archived = restarted.archive_spool(
            spool_id=self.spool_id, expected_revision=3, actor_device_id=self.device,
            command_key="archive-after-edit", at=self.now,
        )
        self.assertEqual(restarted.edit_spool(**arguments), archived)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.audit.for_command("edit-once")), 1)
            self.assertEqual(work.spools.get(self.spool_id), archived)

    def test_archive_replay_requires_matching_receipt(self) -> None:
        arguments = dict(
            spool_id=self.spool_id, expected_revision=1, actor_device_id=self.device,
            command_key="archive-once", at=self.now,
        )
        archived = self.commands.archive_spool(**arguments)
        restarted = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.archive_spool(**arguments), archived)
        for changes in (
            {"expected_revision": 2}, {"actor_device_id": EntityId.new()},
            {"command_key": "new-archive"}, {"spool_id": EntityId.new()},
        ):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                restarted.archive_spool(**(arguments | changes))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id), archived)
            self.assertEqual(len(work.audit.for_command("archive-once")), 1)

    def test_spool_mutation_audit_failure_rolls_back_state_and_receipt(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            original = work.spools.get(self.spool_id)
        for command, extra in (
            (self.commands.edit_spool, {"display_name": "Unsaved", "low_threshold": Mass(10)}),
            (self.commands.archive_spool, {}),
            (self.commands.rebuild_projection, {}),
        ):
            with self.subTest(command=command.__name__):
                with self.assertRaisesRegex(ValueError, "audit.field_invalid"):
                    command(
                        spool_id=self.spool_id, expected_revision=1,
                        actor_device_id=self.device, command_key="", at=self.now, **extra,
                    )
                with SQLiteUnitOfWork(self.engine) as work:
                    self.assertEqual(work.spools.get(self.spool_id), original)
                    self.assertEqual(work.audit.for_command(""), [])

    def test_spool_mutations_cannot_reuse_another_operations_key(self) -> None:
        edited = self.commands.edit_spool(
            spool_id=self.spool_id, expected_revision=1, display_name="Saved",
            low_threshold=None, actor_device_id=self.device, command_key="shared-key", at=self.now,
        )
        for command in (self.commands.archive_spool, self.commands.rebuild_projection):
            with self.subTest(command=command.__name__), self.assertRaises(IdempotencyConflict):
                command(
                    spool_id=self.spool_id, expected_revision=2,
                    actor_device_id=self.device, command_key="shared-key", at=self.now,
                )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id), edited)
            self.assertEqual(len(work.audit.for_command("shared-key")), 1)

    def test_create_edit_and_archive_spool(self) -> None:
        spool_id = EntityId.new()
        created = self.commands.create_spool(
            spool_id=spool_id, filament_profile_id=self.profile_id, display_name="PETG",
            actor_device_id=self.device, command_key="create", low_threshold=Mass(100),
            purchase_price=ExactDecimal.parse("18.25"), currency="UAH",
            purchase_basis=Mass(1_000_000),
            purchase_date="2026-10-15",
            at=self.now,
        )
        self.assertEqual(created.purchase_price, ExactDecimal.parse("18.25"))
        self.assertEqual(created.purchase_basis, Mass(1_000_000))
        self.assertEqual(created.currency, "UAH")
        self.assertEqual(created.purchase_date, "2026-10-15")
        edited = self.commands.edit_spool(
            spool_id=spool_id, expected_revision=created.revision, display_name="PETG Red",
            low_threshold=Mass(200), actor_device_id=self.device, command_key="edit",
            purchase_price=ExactDecimal.parse("20"), currency="EUR",
            purchase_basis=Mass(900_000),
            purchase_date="2026-10-16",
            at=self.now,
        )
        self.assertEqual(edited.purchase_price, ExactDecimal.parse("20"))
        self.assertEqual(edited.purchase_basis, Mass(900_000))
        self.assertEqual(edited.currency, "EUR")
        self.assertEqual(edited.purchase_date, "2026-10-16")
        archived = self.commands.archive_spool(
            spool_id=spool_id, expected_revision=edited.revision,
            actor_device_id=self.device, command_key="archive", at=self.now,
        )
        self.assertEqual(archived.display_name, "PETG Red")
        self.assertEqual(archived.lifecycle.value, "ARCHIVED")
        self.assertEqual(archived.revision, 3)
        with self.assertRaisesRegex(ValueError, "spool.archived_read_only"):
            self.commands.edit_spool(
                spool_id=spool_id, expected_revision=3, display_name="changed",
                low_threshold=None, actor_device_id=self.device, command_key="late-edit",
                at=self.now,
            )

    def test_spool_purchase_metadata_requires_exact_money_currency_and_date(self) -> None:
        common = dict(
            spool_id=EntityId.new(), filament_profile_id=self.profile_id,
            display_name="Purchase validation", actor_device_id=self.device,
        )
        for values, code in (
            ({"purchase_price": ExactDecimal.parse("4.50")}, "purchase_profile_incomplete"),
            ({"purchase_price": ExactDecimal.parse("-1"), "purchase_basis": Mass(500), "currency": "UAH"}, "purchase_price_invalid"),
            ({"purchase_price": ExactDecimal.parse("4.501"), "purchase_basis": Mass(500), "currency": "UAH"}, "purchase_price_invalid"),
            ({"purchase_price": ExactDecimal.parse("1234567890"), "purchase_basis": Mass(500), "currency": "UAH"}, "purchase_price_invalid"),
            ({"purchase_price": ExactDecimal.parse("4.50"), "purchase_basis": Mass(500), "currency": "uAh"}, "currency_invalid"),
            ({"purchase_price": ExactDecimal.parse("4.50"), "currency": "UAH"}, "purchase_profile_incomplete"),
            ({"purchase_price": ExactDecimal.parse("4.50"), "purchase_basis": Mass(0), "currency": "UAH"}, "purchase_basis_invalid"),
            ({"purchase_date": "2026-02-30"}, "purchase_date_invalid"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                self.commands.create_spool(
                    **common, command_key=f"invalid-purchase-{code}", **values, at=self.now,
                )

    def test_archived_unknown_spool_cannot_establish_opening_stock(self) -> None:
        self.commands.archive_spool(
            spool_id=self.spool_id, expected_revision=1, actor_device_id=self.device,
            command_key="archive", at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "spool.archived_read_only"):
            self.commands.establish_opening_stock(
                spool_id=self.spool_id, amount=Mass(100), command_key="late-opening",
                actor_device_id=self.device, at=self.now,
            )
        self.assertEqual(self.commands.history(self.spool_id), ())

    def test_archived_spool_rejects_new_stock_mutations_but_allows_replay(self) -> None:
        opening = self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        archived = self.commands.archive_spool(
            spool_id=self.spool_id, expected_revision=2, actor_device_id=self.device,
            command_key="archive", at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "spool.archived_read_only"):
            self.commands.adjust(
                spool_id=self.spool_id, delta=Mass(-100), command_key="late-adjust",
                actor_device_id=self.device, at=self.now,
            )
        with self.assertRaisesRegex(ValueError, "spool.archived_read_only"):
            self.commands.compensate(
                transaction_id=opening.id, command_key="late-compensate",
                actor_device_id=self.device, at=self.now,
            )
        with self.assertRaisesRegex(ValueError, "spool.archived_read_only"):
            self.commands.rebuild_projection(
                spool_id=self.spool_id, expected_revision=archived.revision,
                actor_device_id=self.device, command_key="late-rebuild", at=self.now,
            )
        self.assertEqual(self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        ), opening)
        self.assertEqual(self.commands.history(self.spool_id), (opening,))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id), archived)

    def test_archive_rejects_active_mount(self) -> None:
        printer_id, system_id, slot_id = EntityId.new(), EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device, created_at=self.now, updated_at=self.now, revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(insert(printer).values(
                **common, id=printer_id, name="P1S", enabled=True,
            ))
            connection.execute(insert(material_feed_system).values(
                **common, id=system_id, printer_id=printer_id,
                provider_system_key="external", kind="EXTERNAL", name="External",
            ))
            connection.execute(insert(feed_slot).values(
                **common, id=slot_id, feed_system_id=system_id, slot_key="slot-0",
                tool_index=0, assignment_state="ASSIGNED",
            ))
            connection.execute(insert(spool_mount).values(
                **common, id=EntityId.new(), feed_slot_id=slot_id, spool_id=self.spool_id,
                state="ACTIVE", mounted_at=self.now, assignment_source="MANUAL",
                confidence_bp=10_000,
            ))
        with self.assertRaisesRegex(ValueError, "spool.archive_active_mount"):
            self.commands.archive_spool(
                spool_id=self.spool_id, expected_revision=1,
                actor_device_id=self.device, command_key="archive", at=self.now,
            )

    def test_compensation_reverses_once_and_replays_idempotently(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        original = self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-250), command_key="use",
            actor_device_id=self.device, at=self.now,
        )
        compensation = self.commands.compensate(
            transaction_id=original.id, command_key="undo-use",
            actor_device_id=self.device, at=self.now,
        )
        replay = self.commands.compensate(
            transaction_id=original.id, command_key="undo-use",
            actor_device_id=self.device, at=self.now,
        )
        self.assertEqual(replay, compensation)
        self.assertEqual(compensation.delta, Mass(250))
        self.assertEqual(compensation.compensates_transaction_id, original.id)
        with self.assertRaises(IdempotencyConflict):
            self.commands.adjust(
                spool_id=self.spool_id, delta=Mass(250), command_key="undo-use",
                actor_device_id=self.device, at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id).effective_remaining, Mass(1000))
        with self.assertRaisesRegex(ValueError, "inventory.transaction_already_compensated"):
            self.commands.compensate(
                transaction_id=original.id, command_key="second-undo",
                actor_device_id=self.device, at=self.now,
            )

    def test_quarantine_resolution_validates_repaired_balance_and_replays(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(100), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-200), command_key="negative",
            actor_device_id=self.device, at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(300), command_key="repair",
            actor_device_id=self.device, at=self.now,
        )
        history = self.commands.history(self.spool_id)
        args = dict(
            spool_id=self.spool_id, expected_revision=4, actor_device_id=self.device,
            command_key="resolve-quarantine", reason="Verified corrected stock", at=self.now,
        )
        resolved = self.commands.resolve_quarantine(**args)
        self.assertEqual(resolved.inventory_health, InventoryHealth.CONSISTENT)
        self.assertEqual(resolved.effective_remaining, Mass(200))
        self.assertEqual(resolved.revision, 5)
        restarted = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.resolve_quarantine(**args), resolved)
        with self.assertRaises(IdempotencyConflict):
            restarted.resolve_quarantine(**(args | {"reason": "Different confirmation"}))
        self.assertEqual(restarted.history(self.spool_id), history)
        with self.engine.connect() as connection:
            task = connection.execute(select(reconciliation_task)).mappings().one()
            self.assertEqual(task["status"], "RESOLVED")
            self.assertEqual(task["resolved_by"], self.device)
            self.assertEqual(task["resolution_notes"], args["reason"])
            self.assertEqual(connection.execute(select(alert_event.c.id).where(
                alert_event.c.resolved_at.is_(None),
            )).all(), [])

    def test_quarantine_resolution_rejects_negative_stock_without_changes(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(100), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-200), command_key="negative",
            actor_device_id=self.device, at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "inventory.quarantine_stock_invalid"):
            self.commands.resolve_quarantine(
                spool_id=self.spool_id, expected_revision=3, actor_device_id=self.device,
                command_key="invalid-resolve", reason="Attempted confirmation", at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id).revision, 3)
            self.assertEqual(work.audit.for_command("invalid-resolve"), [])
            self.assertIsNotNone(work.reconciliations.open_task_by_dedupe(
                f"spool:{self.spool_id}:negative-stock",
            ))

    def _repaired_quarantine(self) -> dict:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(100), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        for key, delta in (("negative", -200), ("repair", 300)):
            self.commands.adjust(
                spool_id=self.spool_id, delta=Mass(delta), command_key=key,
                actor_device_id=self.device, at=self.now,
            )
        return dict(
            spool_id=self.spool_id, expected_revision=4, actor_device_id=self.device,
            command_key="resolve", reason="Verified correction", at=self.now,
        )

    def test_quarantine_resolution_audit_failure_rolls_back_tasks_and_alert(self) -> None:
        args = self._repaired_quarantine()
        with patch.object(InventoryCommands, "_audit", side_effect=RuntimeError("audit failpoint")):
            with self.assertRaisesRegex(RuntimeError, "audit failpoint"):
                self.commands.resolve_quarantine(**args)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id).inventory_health, InventoryHealth.QUARANTINED)
            self.assertEqual(work.spools.get(self.spool_id).revision, 4)
            self.assertEqual(len(work.reconciliations.open_tasks_for_spool(self.spool_id)), 1)
            self.assertIsNotNone(work.alerts.open_by_dedupe(f"spool:{self.spool_id}:quarantined"))
            self.assertEqual(work.audit.for_command("resolve"), [])
        self.assertEqual(self.commands.resolve_quarantine(**args).inventory_health,
                         InventoryHealth.CONSISTENT)

    def test_quarantine_resolution_rejects_stale_revision_and_invalid_reason(self) -> None:
        args = self._repaired_quarantine()
        with self.assertRaises(RevisionConflict):
            self.commands.resolve_quarantine(**(args | {"expected_revision": 3}))
        for reason in ("", " ", "x" * 501):
            with self.subTest(reason=reason), self.assertRaisesRegex(
                ValueError, "inventory.quarantine_reason_invalid",
            ):
                self.commands.resolve_quarantine(**(args | {"reason": reason}))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.spool_id).revision, 4)
            self.assertEqual(work.audit.for_command("resolve"), [])

    def test_quarantine_resolution_does_not_close_unrelated_incident(self) -> None:
        args = self._repaired_quarantine()
        with self.engine.begin() as connection:
            connection.execute(insert(reconciliation_task).values(
                id=EntityId.new(), device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, spool_id=self.spool_id,
                reason_code="CONFLICTING_EVIDENCE", severity="ERROR", status="OPEN",
                dedupe_key="unrelated-evidence",
            ))
        with self.assertRaisesRegex(ValueError, "inventory.quarantine_tasks_require_review"):
            self.commands.resolve_quarantine(**args)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.reconciliations.open_tasks_for_spool(self.spool_id)), 2)
            self.assertEqual(work.spools.get(self.spool_id).revision, 4)

    def test_low_and_negative_stock_raise_deduplicated_alerts(self) -> None:
        self.commands.edit_spool(
            spool_id=self.spool_id, expected_revision=1, display_name="PLA",
            low_threshold=Mass(100), actor_device_id=self.device,
            command_key="threshold", at=self.now,
        )
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-950), command_key="low",
            actor_device_id=self.device, at=self.now,
        )
        self.assertEqual(self.commands.availability(self.spool_id).level, StockLevel.LOW)
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-100), command_key="negative",
            actor_device_id=self.device, at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-1), command_key="still-negative",
            actor_device_id=self.device, at=self.now,
        )
        with self.engine.connect() as connection:
            alerts = connection.execute(select(alert_event.c.message_key).where(
                alert_event.c.resolved_at.is_(None),
            )).scalars().all()
            tasks = connection.execute(select(reconciliation_task.c.reason_code)).scalars().all()
        self.assertEqual(alerts, ["inventory.spool_quarantined"])
        self.assertEqual(tasks, ["inventory.negative_stock"])
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(200), command_key="recover",
            actor_device_id=self.device, at=self.now,
        )
        with self.engine.connect() as connection:
            open_alerts = connection.execute(select(alert_event.c.id).where(
                alert_event.c.resolved_at.is_(None),
            )).all()
            task_state = connection.execute(
                select(reconciliation_task.c.status)
            ).scalar_one()
        self.assertEqual(len(open_alerts), 1)
        self.assertEqual(task_state, "OPEN")
        self.assertEqual(
            self.commands.availability(self.spool_id).health, InventoryHealth.QUARANTINED,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            revision = work.spools.get(self.spool_id).revision
        rebuilt = self.commands.rebuild_projection(
            spool_id=self.spool_id, expected_revision=revision,
            actor_device_id=self.device, command_key="rebuild-quarantined", at=self.now,
        )
        self.assertEqual(rebuilt.inventory_health, InventoryHealth.QUARANTINED)

    def test_threshold_edit_refreshes_low_stock_alert_without_ledger_mutation(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(100), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        for revision, threshold, expected_alert in ((2, Mass(200), True), (3, Mass(50), False)):
            self.commands.edit_spool(
                spool_id=self.spool_id, expected_revision=revision, display_name="PLA",
                low_threshold=threshold, actor_device_id=self.device,
                command_key=f"threshold-{revision}", at=self.now,
            )
            with SQLiteUnitOfWork(self.engine) as work:
                self.assertEqual(
                    work.alerts.open_by_dedupe(f"spool:{self.spool_id}:low-stock") is not None,
                    expected_alert,
                )
                self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 1)

    def test_rebuild_replay_does_not_repeat_after_new_stock_change(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        arguments = dict(
            spool_id=self.spool_id, expected_revision=2, actor_device_id=self.device,
            command_key="rebuild-once", at=self.now,
        )
        rebuilt = self.commands.rebuild_projection(**arguments)
        self.assertEqual(self.commands.rebuild_projection(**arguments), rebuilt)
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-200), command_key="later-use",
            actor_device_id=self.device, at=self.now,
        )
        restarted = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        replay = restarted.rebuild_projection(**arguments)
        self.assertEqual(replay.effective_remaining, Mass(800))
        self.assertEqual(replay.revision, 4)
        for changes in (
            {"expected_revision": 4}, {"actor_device_id": EntityId.new()},
            {"spool_id": EntityId.new()},
        ):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                restarted.rebuild_projection(**(arguments | changes))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.audit.for_command("rebuild-once")), 1)
            self.assertEqual(len(work.ledger.for_spool(self.spool_id)), 2)

    def test_rebuild_projection_replays_ledger_truth(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(-250), command_key="adjust",
            actor_device_id=self.device, at=self.now,
        )
        with self.engine.begin() as connection:
            connection.execute(update(spool_table).where(
                spool_table.c.id == self.spool_id,
            ).values(effective_remaining_mg=Mass(123), estimated_remaining_mg=Mass(456)))
        rebuilt = self.commands.rebuild_projection(
            spool_id=self.spool_id, expected_revision=3,
            actor_device_id=self.device, command_key="rebuild", at=self.now,
        )
        self.assertEqual(rebuilt.effective_remaining, Mass(750))
        self.assertEqual(rebuilt.estimated_remaining, Mass(750))
        self.assertEqual(rebuilt.ledger_sequence, 2)
        self.assertEqual(
            [entry.sequence for entry in self.commands.history(self.spool_id)],
            [1, 2],
        )

    def test_availability_subtracts_active_reservations(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        printer_id, job_id, material_id = EntityId.new(), EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device, created_at=self.now, updated_at=self.now, revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(insert(printer).values(
                **common, id=printer_id, name="P1S", enabled=True,
            ))
            connection.execute(insert(print_job).values(
                **common, id=job_id, printer_id=printer_id, source_type="manual",
                status="DETECTED", finalization_state="NOT_STARTED", detected_at=self.now,
            ))
            connection.execute(insert(print_job_material).values(
                **common, id=material_id, print_job_id=job_id,
                channel_key="tool-0", tool_index=0,
            ))
            connection.execute(insert(reservation).values(
                **common, id=EntityId.new(), spool_id=self.spool_id,
                print_job_material_id=material_id, reserved_mg=Mass(400),
                status="ACTIVE", activated_at=self.now,
            ))
        availability = self.commands.availability(self.spool_id)
        self.assertEqual(availability.effective, Mass(1000))
        self.assertEqual(availability.reserved, Mass(400))
        self.assertEqual(availability.available, Mass(600))

    def test_correction_preserves_claims_and_records_shortage(self) -> None:
        self.commands.establish_opening_stock(
            spool_id=self.spool_id, amount=Mass(1000), command_key="opening",
            actor_device_id=self.device, at=self.now,
        )
        printer_id, job_id, material_id = EntityId.new(), EntityId.new(), EntityId.new()
        claim_id = EntityId.new()
        common = dict(
            device_id=self.device, created_at=self.now, updated_at=self.now, revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(insert(printer).values(
                **common, id=printer_id, name="P1S", enabled=True,
            ))
            connection.execute(insert(print_job).values(
                **common, id=job_id, printer_id=printer_id, source_type="manual",
                status="RUNNING", finalization_state="NOT_STARTED", detected_at=self.now,
            ))
            connection.execute(insert(print_job_material).values(
                **common, id=material_id, print_job_id=job_id, channel_key="tool-0", tool_index=0,
            ))
            connection.execute(insert(reservation).values(
                **common, id=claim_id, spool_id=self.spool_id,
                print_job_material_id=material_id, reserved_mg=Mass(800),
                status="ACTIVE", activated_at=self.now,
            ))
        for key, delta, expected in (("correction", -500, 500), ("second", -100, 400)):
            entry = self.commands.adjust(
                spool_id=self.spool_id, delta=Mass(delta), command_key=key,
                actor_device_id=self.device, at=self.now,
            )
            self.assertEqual(entry.new_effective, Mass(expected))
        availability = self.commands.availability(self.spool_id)
        self.assertEqual(availability.reserved, Mass(800))
        self.assertEqual(availability.available, Mass(-400))
        self.assertEqual(availability.health, InventoryHealth.QUARANTINED)
        with self.engine.connect() as connection:
            reasons = connection.execute(select(reconciliation_task.c.reason_code)).scalars().all()
            alerts = connection.execute(select(alert_event.c.message_key).where(
                alert_event.c.resolved_at.is_(None),
            )).scalars().all()
            persisted = connection.execute(select(reservation).where(
                reservation.c.id == claim_id,
            )).mappings().one()
        self.assertEqual(reasons, ["RESERVATION_SHORTAGE"])
        self.assertEqual(alerts, ["inventory.spool_quarantined"])
        self.assertEqual(persisted["status"], "ACTIVE")
        self.assertEqual(persisted["revision"], 1)
        with self.assertRaisesRegex(ValueError, "inventory.quarantine_reservation_shortage"):
            self.commands.resolve_quarantine(
                spool_id=self.spool_id, expected_revision=4, actor_device_id=self.device,
                command_key="shortage-resolution", reason="Attempted confirmation", at=self.now,
            )
        self.commands.adjust(
            spool_id=self.spool_id, delta=Mass(500), command_key="repair-shortage",
            actor_device_id=self.device, at=self.now,
        )
        resolved = self.commands.resolve_quarantine(
            spool_id=self.spool_id, expected_revision=5, actor_device_id=self.device,
            command_key="shortage-resolved", reason="Verified capacity correction", at=self.now,
        )
        self.assertEqual(resolved.inventory_health, InventoryHealth.CONSISTENT)
        self.assertEqual(self.commands.availability(self.spool_id).reserved, Mass(800))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.reconciliations.open_tasks_for_spool(self.spool_id), [])
