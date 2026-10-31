"""Explicit, atomic migration entry point; no implicit reset of existing databases."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import cast
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from ufm.infrastructure.backup.sqlite_snapshot import create_snapshot
from ufm.infrastructure.persistence.sqlite.engine import immediate_transaction

INITIAL_REVISION = "0001_initial"
PROJECTION_REVISION = "0002_job_projection"
LOGICAL_MATERIAL_REVISION = "0003_logical_material_index"
LATEST_REVISION = "0007_haspel_authority_connection"
REVISIONS = (
    INITIAL_REVISION, PROJECTION_REVISION, LOGICAL_MATERIAL_REVISION,
    "0004_purchase_basis", "0005_spoolman_source_registry",
    "0006_printer_accounting_authority", LATEST_REVISION,
)


class MigrationRequired(RuntimeError):
    def __init__(self, code: str = "migration.unsupported_schema") -> None:
        super().__init__(code)


def _verify_v1_objects(engine_objects: dict[tuple[str, str], str]) -> None:
    _verify_objects(engine_objects, INITIAL_REVISION)


def _verify_objects(engine_objects: dict[tuple[str, str], str], revision: str) -> None:
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    if revision not in REVISIONS:
        raise MigrationRequired()
    revisions = REVISIONS[: REVISIONS.index(revision) + 1]
    with closing(sqlite3.connect(":memory:")) as reference:
        for item in revisions:
            statements = json.loads((versions / f"{item}.json").read_text(encoding="utf-8"))
            for statement in statements:
                reference.execute(statement)
        expected = reference.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    for kind, name, sql in expected:
        actual = engine_objects.get((kind, name), "")
        if re.sub(r"\s+", " ", actual).strip() != re.sub(r"\s+", " ", sql).strip():
            raise MigrationRequired("migration.schema_objects_invalid")


def migrate_database(engine: Engine, *, backup_root: Path | None = None) -> str:
    """Upgrade atomically, snapshotting validated existing v1 before any DDL."""
    with immediate_transaction(engine) as connection:
        names = set(inspect(connection).get_table_names())
        upgrade = not names
        if names:
            if "alembic_version" not in names:
                raise MigrationRequired("migration.unversioned_database")
            revisions = cast(
                list[str],
                connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version",
                ).scalars().all(),
            )
            revision = revisions[0] if len(revisions) == 1 else revisions[-1]
            if revision not in REVISIONS:
                raise MigrationRequired()
            objects = cast(
                dict[tuple[str, str], str],
                {(kind, name): sql for kind, name, sql in connection.exec_driver_sql(
                    "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL"
                )},
            )
            _verify_objects(objects, revision)
            if revision != LATEST_REVISION:
                database_name = engine.url.database
                if not database_name or database_name == ":memory:":
                    raise MigrationRequired("migration.backup_required")
                database = Path(database_name).resolve()
                destination = backup_root if backup_root is not None else database.parent / "backups" / "migrations"
                create_snapshot(database, destination / str(uuid4()))
                upgrade = True
        if upgrade:
            configuration = Config()
            scripts = Path(__file__).resolve().parents[1] / "migrations"
            configuration.set_main_option("script_location", str(scripts).replace("%", "%%"))
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, LATEST_REVISION)
        objects = cast(
            dict[tuple[str, str], str],
            {
                (kind, name): sql for kind, name, sql in connection.exec_driver_sql(
                    "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL"
                )
            },
        )
        _verify_objects(objects, LATEST_REVISION)
        if connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() != ["ok"]:
            raise MigrationRequired("migration.integrity_failed")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
            raise MigrationRequired("migration.foreign_key_failed")
    return LATEST_REVISION
