import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.engine import immediate_transaction


class SqliteEngineTests(unittest.TestCase):
    def test_file_engine_enables_required_pragmas_without_creating_schema(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-sqlite-") as directory:
            path = Path(directory) / "data" / "ufm.sqlite3"
            engine = create_sqlite_engine(path, busy_timeout_ms=1_234)
            try:
                with engine.connect() as connection:
                    self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)
                    self.assertEqual(connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(), 1_234)
                    self.assertEqual(connection.exec_driver_sql("PRAGMA journal_mode").scalar_one(), "wal")
                    self.assertEqual(connection.exec_driver_sql("PRAGMA synchronous").scalar_one(), 2)
                self.assertEqual(inspect(engine).get_table_names(), [])
                self.assertTrue(path.is_file())
            finally:
                engine.dispose()

    def test_foreign_keys_are_enforced_on_real_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-sqlite-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            try:
                with engine.begin() as connection:
                    connection.exec_driver_sql("CREATE TABLE parent (id TEXT PRIMARY KEY)")
                    connection.exec_driver_sql(
                        "CREATE TABLE child (parent_id TEXT NOT NULL REFERENCES parent(id))"
                    )
                with self.assertRaises(IntegrityError), engine.begin() as connection:
                    connection.exec_driver_sql("INSERT INTO child(parent_id) VALUES ('missing')")
            finally:
                engine.dispose()

    def test_immediate_transaction_rolls_back_on_exception(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-sqlite-") as directory:
            path = Path(directory) / "ufm.sqlite3"
            engine = create_sqlite_engine(path)
            try:
                with engine.begin() as connection:
                    connection.exec_driver_sql("CREATE TABLE values_table (value INTEGER NOT NULL)")
                with self.assertRaisesRegex(RuntimeError, "stop"):
                    with immediate_transaction(engine) as connection:
                        connection.exec_driver_sql("INSERT INTO values_table VALUES (1)")
                        raise RuntimeError("stop")
                with engine.connect() as connection:
                    self.assertEqual(connection.exec_driver_sql("SELECT count(*) FROM values_table").scalar_one(), 0)
            finally:
                engine.dispose()

    def test_invalid_timeout_and_obvious_unc_path_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "busy_timeout_invalid"):
            create_sqlite_engine(Path("database.sqlite3"), busy_timeout_ms=0)
        if sqlite3.sqlite_version_info >= (3, 0):
            with self.assertRaisesRegex(ValueError, "network_path_unsupported"):
                create_sqlite_engine(Path(r"\\server\share\database.sqlite3"))
