"""Hardened file-backed SQLite engine configuration."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Connection, Engine

MIN_BUSY_TIMEOUT_MS = 100
MAX_BUSY_TIMEOUT_MS = 60_000


def _database_path(path: Path) -> Path:
    raw = str(path)
    if raw.startswith(("\\\\", "//")):
        raise ValueError("sqlite.network_path_unsupported")
    resolved = path.expanduser().resolve()
    if not resolved.name:
        raise ValueError("sqlite.path_invalid")
    return resolved


def create_sqlite_engine(path: Path, *, busy_timeout_ms: int = 5_000) -> Engine:
    """Create a configured engine without creating or migrating schema."""
    if type(busy_timeout_ms) is not int or not MIN_BUSY_TIMEOUT_MS <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS:
        raise ValueError("sqlite.busy_timeout_invalid")
    database = _database_path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(database)),
        connect_args={"timeout": busy_timeout_ms / 1_000},
    )

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA recursive_triggers = ON")
            cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = FULL")
        finally:
            cursor.close()

    return engine


@contextmanager
def immediate_transaction(engine: Engine) -> Iterator[Connection]:
    """Acquire SQLite's writer reservation before application-side guards run."""
    connection = engine.connect()
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
