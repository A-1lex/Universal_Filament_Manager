"""SQLite connection and transaction primitives."""

from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine

__all__ = ["create_sqlite_engine"]
