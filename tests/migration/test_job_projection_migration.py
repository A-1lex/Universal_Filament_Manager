"""Real SQLite checks for additive, backup-first schema revisions."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

from ufm.infrastructure.backup.sqlite_snapshot import BackupInvalid, verify_snapshot
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import (
    INITIAL_REVISION,
    LATEST_REVISION,
    PROJECTION_REVISION,
    MigrationRequired,
    _verify_objects,
    migrate_database,
)


class JobProjectionMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ufm-projection-migration-")
        self.root = Path(self.directory.name)
        self.database = self.root / "ufm.sqlite3"
        self.engine = create_sqlite_engine(self.database)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.engine.dispose)

    def seed_v1(self) -> None:
        versions = Path(__file__).resolve().parents[2] / "src/ufm/infrastructure/persistence/migrations/versions"
        with self.engine.begin() as connection:
            for statement in json.loads((versions / "0001_initial.json").read_text(encoding="utf-8")):
                connection.exec_driver_sql(statement)
            connection.exec_driver_sql("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (INITIAL_REVISION,))
            connection.exec_driver_sql(
                "INSERT INTO device_identity(id,name,public_id,created_at) VALUES(?,?,?,?)",
                ("00000000-0000-4000-8000-000000000001", "Збережено", "migration-device", "2026-09-11T00:00:00.000000Z"),
            )

    def assert_v1_preserved(self) -> None:
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one(), INITIAL_REVISION)
            self.assertEqual(connection.exec_driver_sql("SELECT name FROM device_identity").scalar_one(), "Збережено")
            self.assertNotIn("job_projection_state", inspect(connection).get_table_names())

    def test_populated_upgrade_creates_verified_v1_snapshot_and_preserves_rows(self) -> None:
        self.seed_v1()
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)
        bundles = list((self.root / "backups/migrations").iterdir())
        self.assertEqual(len(bundles), 1)
        with closing(sqlite3.connect(verify_snapshot(bundles[0]))) as backup:
            self.assertEqual(backup.execute("SELECT version_num FROM alembic_version").fetchone(), (INITIAL_REVISION,))
            self.assertEqual(backup.execute("SELECT name FROM device_identity").fetchone(), ("Збережено",))
            self.assertEqual(backup.execute("SELECT name FROM sqlite_master WHERE name='job_projection_state'").fetchall(), [])
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT name FROM device_identity").scalar_one(), "Збережено")
            self.assertEqual(connection.exec_driver_sql("SELECT COUNT(*) FROM job_projection_state").scalar_one(), 0)
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)
        self.assertEqual(len(list((self.root / "backups/migrations").iterdir())), 1)

    def test_existing_v2_gets_backup_before_logical_material_column(self) -> None:
        self.seed_v1()
        versions = Path(__file__).resolve().parents[2] / "src/ufm/infrastructure/persistence/migrations/versions"
        with self.engine.begin() as connection:
            for statement in json.loads((versions / f"{PROJECTION_REVISION}.json").read_text(encoding="utf-8")):
                connection.exec_driver_sql(statement)
            connection.exec_driver_sql(
                "UPDATE alembic_version SET version_num = ?", (PROJECTION_REVISION,),
            )
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)
        bundles = list((self.root / "backups/migrations").iterdir())
        self.assertEqual(len(bundles), 1)
        with closing(sqlite3.connect(verify_snapshot(bundles[0]))) as backup:
            self.assertEqual(
                backup.execute("SELECT version_num FROM alembic_version").fetchone(),
                (PROJECTION_REVISION,),
            )
            self.assertEqual(backup.execute("SELECT name FROM device_identity").fetchone(), ("Збережено",))
            self.assertNotIn(
                "logical_material_index",
                [row[1] for row in backup.execute("PRAGMA table_info(print_job_material)")],
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql("SELECT name FROM device_identity").scalar_one(),
                "Збережено",
            )
            self.assertIn(
                "logical_material_index",
                [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(print_job_material)")],
            )

    def test_backup_failure_prevents_any_ddl(self) -> None:
        self.seed_v1()
        with patch("ufm.infrastructure.persistence.sqlite.migrate.create_snapshot", side_effect=BackupInvalid()):
            with self.assertRaises(BackupInvalid):
                migrate_database(self.engine)
        self.assert_v1_preserved()

    def test_custom_backup_root_and_interruption_roll_back_to_v1(self) -> None:
        self.seed_v1()
        from ufm.infrastructure.persistence.sqlite import migrate

        original = migrate.command.upgrade

        def interrupt(*args: object, **kwargs: object) -> None:
            original(*args, **kwargs)
            raise RuntimeError("interrupted after DDL")

        with patch.object(migrate.command, "upgrade", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                migrate_database(self.engine, backup_root=self.root / "custom")
        self.assert_v1_preserved()
        self.assertEqual(len(list((self.root / "custom").iterdir())), 1)

    def test_invalid_v1_is_rejected_before_backup(self) -> None:
        self.seed_v1()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER guard_audit_event_update")
        with patch("ufm.infrastructure.persistence.sqlite.migrate.create_snapshot") as backup:
            with self.assertRaisesRegex(MigrationRequired, "schema_objects_invalid"):
                migrate_database(self.engine)
            backup.assert_not_called()
        self.assert_v1_preserved()

    def test_fresh_latest_and_current_metadata_have_matching_objects(self) -> None:
        from ufm.infrastructure.persistence.models import metadata

        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)
        self.assertFalse((self.root / "backups").exists())
        other = create_sqlite_engine(self.root / "metadata.sqlite3")
        self.addCleanup(other.dispose)
        metadata.create_all(other)
        with other.connect() as connection:
            objects = {(kind, name): sql for kind, name, sql in connection.exec_driver_sql(
                "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL"
            )}
        _verify_objects(objects, LATEST_REVISION)

    def test_missing_new_guard_is_rejected(self) -> None:
        migrate_database(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER guard_job_receipt_application_delete")
        with self.assertRaisesRegex(MigrationRequired, "schema_objects_invalid"):
            migrate_database(self.engine)

    def test_unknown_revision_is_unchanged_and_has_no_backup(self) -> None:
        self.seed_v1()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='future-schema'")
        with self.assertRaises(MigrationRequired):
            migrate_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one(), "future-schema")
            self.assertNotIn("job_projection_state", inspect(connection).get_table_names())
        self.assertFalse((self.root / "backups").exists())

    def test_process_death_after_upgrade_rolls_back_existing_v1(self) -> None:
        self.seed_v1()
        worker = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine, migrate
original = migrate.command.upgrade
def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(37)
with patch.object(migrate.command, 'upgrade', side_effect=crash):
    migrate.migrate_database(create_sqlite_engine(Path(sys.argv[1])))
"""
        result = subprocess.run([sys.executable, "-c", worker, str(self.database)],
                                env=os.environ.copy(), capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assert_v1_preserved()
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)

    def projection_rows(self):
        from tests.integration.test_print_finalization import END, create_scope
        from ufm.domain.value_objects import EntityId

        migrate_database(self.engine)
        ids = create_scope(self.engine, opening=False, with_evidence=False)
        common = dict(id=EntityId.new(), device_id=ids["device"], created_at=END)
        marker = dict(**common, receipt_id=ids["receipt"], print_job_id=ids["job"],
                      contract_version="job-receipt-projection-v1", outcome="APPLIED",
                      reason_code="job_projection.applied", request_hash="a" * 64)
        state = dict(**(common | {"id": EntityId.new()}), updated_at=END, revision=1,
                     print_job_id=ids["job"], last_receipt_id=ids["receipt"], observed_state="running",
                     observed_at=END, source_sequence=0, completed_layers=None)
        return ids, marker, state

    def test_marker_unique_immutable_and_request_hash_constraints(self) -> None:
        from ufm.domain.value_objects import EntityId
        from ufm.infrastructure.persistence.models.projection import (
            job_receipt_application as table,
        )

        _ids, marker, _state = self.projection_rows()
        for change in ({"request_hash": "A" * 64}, {"request_hash": "g" * 64},
                       {"outcome": "OTHER"}, {"reason_code": ""}, {"contract_version": "v2"}):
            with self.subTest(change=change), self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(insert(table).values(**(marker | change)))
        with self.engine.begin() as connection:
            connection.execute(insert(table).values(**marker))
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(table).values(**(marker | {"id": EntityId.new()})))
        for statement in (update(table).values(reason_code="changed"), delete(table)):
            with self.assertRaisesRegex(IntegrityError, "history.immutable"), self.engine.begin() as connection:
                connection.execute(statement)

    def test_completed_cursor_bounds_and_terminal_shape(self) -> None:
        from tests.integration.test_print_finalization import END, START
        from ufm.infrastructure.persistence.models.projection import job_projection_state as table

        ids, _marker, state = self.projection_rows()
        for change in ({"completed_layers": -1}, {"completed_layers": 1000000000001},
                       {"completed_layers": 1.5}, {"source_sequence": -1}, {"source_sequence": 1.5},
                       {"first_terminal_receipt_id": ids["receipt"]},
                       {"observed_state": "completed"},
                       {"observed_state": "failed"}, {"observed_state": "cancelled"},
                       {"observed_state": "completed", "first_terminal_receipt_id": ids["receipt"],
                        "first_terminal_state": "completed", "terminal_seen_at": START},
                       {"first_terminal_receipt_id": ids["receipt"], "first_terminal_state": "completed",
                        "terminal_seen_at": END}):
            with self.subTest(change=change), self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(insert(table).values(**(state | change)))
        for count in (None, 0, 1, 1000000000000):
            with self.engine.begin() as connection:
                connection.execute(insert(table).values(**(state | {"completed_layers": count})))
                connection.execute(delete(table))
        with self.engine.begin() as connection:
            connection.execute(insert(table).values(**(state | {
                "observed_state": "completed", "first_terminal_receipt_id": ids["receipt"],
                "first_terminal_state": "completed", "terminal_seen_at": END,
            })))

    def test_terminal_observation_facts_are_frozen_but_metadata_can_change(self) -> None:
        from tests.integration.test_print_finalization import END, START
        from ufm.domain.value_objects import EntityId
        from ufm.infrastructure.persistence.models import schema as s
        from ufm.infrastructure.persistence.models.projection import job_projection_state as table

        ids, _marker, state = self.projection_rows()
        other_receipt = EntityId.new()
        with self.engine.begin() as connection:
            receipt = dict(connection.execute(select(s.external_event_receipt)).mappings().one())
            connection.execute(insert(s.external_event_receipt).values(**(receipt | {
                "id": other_receipt, "event_key": "another-valid-receipt",
            })))
            connection.execute(insert(table).values(**(state | {
                "observed_state": "completed", "first_terminal_receipt_id": ids["receipt"],
                "first_terminal_state": "completed", "terminal_seen_at": END,
            })))
            connection.execute(update(table).values(revision=2, deleted_at=END))
        for change in ({"last_receipt_id": other_receipt}, {"observed_state": "failed"},
                       {"observed_at": START}, {"source_sequence": 1}, {"completed_layers": 1},
                       {"first_terminal_receipt_id": None}, {"first_terminal_state": None},
                       {"terminal_seen_at": START}):
            with self.subTest(change=change), self.assertRaisesRegex(
                IntegrityError, "job_projection.terminal_facts_immutable"
            ), self.engine.begin() as connection:
                connection.execute(update(table).values(**change))

    def test_marker_and_state_reject_receipts_from_another_printer(self) -> None:
        from tests.integration.test_print_finalization import create_scope
        from ufm.infrastructure.persistence.models.projection import (
            job_projection_state,
            job_receipt_application,
        )

        _ids, marker, state = self.projection_rows()
        other = create_scope(self.engine, opening=False, with_evidence=False)
        for table, values in (
            (job_receipt_application, marker | {"receipt_id": other["receipt"]}),
            (job_projection_state, state | {"last_receipt_id": other["receipt"]}),
            (job_projection_state, state | {"first_terminal_receipt_id": other["receipt"]}),
        ):
            with self.subTest(table=table.name), self.assertRaisesRegex(
                IntegrityError, "job_projection.receipt_scope_conflict"
            ), self.engine.begin() as connection:
                connection.execute(insert(table).values(**values))
