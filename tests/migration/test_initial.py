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

from sqlalchemy import inspect

from ufm.infrastructure.backup.sqlite_snapshot import (
    BackupInvalid,
    create_snapshot,
    restore_snapshot,
    verify_snapshot,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import (
    LATEST_REVISION,
    MigrationRequired,
    migrate_database,
)


class InitialMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ufm-migration-")
        self.root = Path(self.directory.name)
        self.database = self.root / "ufm.sqlite3"
        self.engine = create_sqlite_engine(self.database)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.engine.dispose)

    def test_fresh_upgrade_and_replay_preserve_data(self) -> None:
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO device_identity(id,name,public_id,created_at) VALUES(?,?,?,?)",
                ("00000000-0000-4000-8000-000000000001", "Українська майстерня", "device", "2026-09-11T00:00:00.000000Z"),
            )
        migrate_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT name FROM device_identity").scalar_one(), "Українська майстерня")
            tables = set(inspect(connection).get_table_names())
            self.assertEqual(len(tables), 39)
            self.assertIn("printer_accounting_authority", tables)
            self.assertIn("spoolman_import_source", tables)

    def test_frozen_revision_matches_initial_reference(self) -> None:
        from ufm.infrastructure.persistence.sqlite.migrate import _verify_v1_objects

        snapshot = Path(__file__).resolve().parents[2] / "src/ufm/infrastructure/persistence/migrations/versions/0001_initial.json"
        with self.engine.begin() as connection:
            for statement in json.loads(snapshot.read_text(encoding="utf-8")):
                connection.exec_driver_sql(statement)
        with self.engine.connect() as connection:
            objects = {(kind, name): sql for kind, name, sql in connection.exec_driver_sql(
                "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL"
            )}
        _verify_v1_objects(objects)

    def test_unversioned_database_is_not_replaced(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE legacy (value TEXT)")
            connection.exec_driver_sql("INSERT INTO legacy VALUES ('retained')")
        with self.assertRaises(MigrationRequired):
            migrate_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT value FROM legacy").scalar_one(), "retained")
            self.assertEqual(inspect(connection).get_table_names(), ["legacy"])

    def test_newer_revision_is_rejected_unchanged(self) -> None:
        migrate_database(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='future-version'")
        with self.assertRaises(MigrationRequired):
            migrate_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one(), "future-version")

    def test_missing_guard_cannot_pass_as_a_valid_v1(self) -> None:
        migrate_database(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER guard_filament_transaction_delete")
        with self.assertRaisesRegex(MigrationRequired, "schema_objects_invalid"):
            migrate_database(self.engine)

    def test_exception_after_ddl_rolls_back_version_and_all_tables(self) -> None:
        from ufm.infrastructure.persistence.sqlite import migrate

        original = migrate.command.upgrade

        def fail_after_ddl(*args: object, **kwargs: object) -> None:
            original(*args, **kwargs)
            raise RuntimeError("simulated interruption")

        with patch.object(migrate.command, "upgrade", side_effect=fail_after_ddl):
            with self.assertRaises(RuntimeError):
                migrate_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(inspect(connection).get_table_names(), [])
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)

    def test_process_termination_before_commit_is_recoverable(self) -> None:
        worker = """
import os, sys
from unittest.mock import patch
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine, migrate
original = migrate.command.upgrade
def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(37)
with patch.object(migrate.command, 'upgrade', side_effect=crash):
    migrate.migrate_database(create_sqlite_engine(__import__('pathlib').Path(sys.argv[1])))
"""
        result = subprocess.run([sys.executable, "-c", worker, str(self.database)],
                                env=os.environ.copy(), capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 37, result.stderr)
        with self.engine.connect() as connection:
            self.assertEqual(inspect(connection).get_table_names(), [])
        self.assertEqual(migrate_database(self.engine), LATEST_REVISION)

    def test_online_wal_snapshot_and_restore_preserve_committed_data(self) -> None:
        migrate_database(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE snapshot_sample(value TEXT)")
            connection.exec_driver_sql("INSERT INTO snapshot_sample VALUES ('committed')")
        # Keep a writer connection alive, so correctness cannot depend on copying
        # a closed/checkpointed main database file alone.
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA wal_autocheckpoint=0")
            connection.exec_driver_sql("INSERT INTO snapshot_sample VALUES ('also committed')")
            connection.commit()
            bundle = create_snapshot(self.database, self.root / "backup")
        restored = self.root / "restored.sqlite3"
        restore_snapshot(bundle, restored)
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM snapshot_sample").fetchall(), [("committed",), ("also committed",)])
        self.assertTrue(self.database.exists())
        with self.assertRaises(FileExistsError):
            restore_snapshot(bundle, restored)

    def test_tampered_or_incomplete_backup_is_rejected(self) -> None:
        migrate_database(self.engine)
        bundle = create_snapshot(self.database, self.root / "backup")
        manifest = json.loads((bundle / "manifest.json").read_text())
        manifest["sha256"] = "0" * 64
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(BackupInvalid):
            verify_snapshot(bundle)
        with self.assertRaises(BackupInvalid):
            restore_snapshot(bundle, self.root / "never_created.sqlite3")
        self.assertFalse((self.root / "never_created.sqlite3").exists())
