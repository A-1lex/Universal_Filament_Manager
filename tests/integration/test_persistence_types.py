import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Column, MetaData, Table, insert, select
from sqlalchemy.exc import StatementError

from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models import (
    EntityIdType,
    ExactDecimalType,
    MassType,
    UtcDateTimeType,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine


class PersistenceTypeTests(unittest.TestCase):
    def test_roundtrip_preserves_domain_values_and_raw_storage(self) -> None:
        metadata = MetaData()
        values = Table(
            "typed_values",
            metadata,
            Column("id", EntityIdType(), primary_key=True),
            Column("captured_at", UtcDateTimeType(), nullable=False),
            Column("decimal_value", ExactDecimalType(), nullable=False),
            Column("mass", MassType(), nullable=False),
        )
        entity_id = EntityId.new()
        captured_at = UtcDateTime(datetime(2026, 9, 11, 12, 30, tzinfo=UTC))
        with tempfile.TemporaryDirectory(prefix="ufm-types-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            try:
                metadata.create_all(engine)
                with engine.begin() as connection:
                    connection.execute(
                        insert(values).values(
                            id=entity_id,
                            captured_at=captured_at,
                            decimal_value=ExactDecimal.parse("1.7500"),
                            mass=Mass.from_grams("12.345"),
                        )
                    )
                with engine.connect() as connection:
                    row = connection.execute(select(values)).one()
                    self.assertEqual(row.id, entity_id)
                    self.assertEqual(row.captured_at, captured_at)
                    self.assertEqual(row.decimal_value.canonical(), "1.75")
                    self.assertEqual(row.mass, Mass(12_345))
                    raw = connection.exec_driver_sql(
                        "SELECT captured_at, decimal_value, mass, typeof(mass) FROM typed_values"
                    ).one()
                    self.assertEqual(
                        raw,
                        ("2026-09-11T12:30:00.000000Z", "1.75", 12_345, "integer"),
                    )
            finally:
                engine.dispose()

    def test_float_and_plain_primitive_bindings_are_rejected(self) -> None:
        metadata = MetaData()
        values = Table(
            "typed_values",
            metadata,
            Column("id", EntityIdType(), primary_key=True),
            Column("decimal_value", ExactDecimalType(), nullable=False),
            Column("mass", MassType(), nullable=False),
        )
        with tempfile.TemporaryDirectory(prefix="ufm-types-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            try:
                metadata.create_all(engine)
                invalid_rows = (
                    {"id": str(EntityId.new()), "decimal_value": ExactDecimal.parse("1"), "mass": Mass(1)},
                    {"id": EntityId.new(), "decimal_value": 1.5, "mass": Mass(1)},
                    {"id": EntityId.new(), "decimal_value": ExactDecimal.parse("1"), "mass": 1.5},
                )
                for row in invalid_rows:
                    with self.subTest(row=row), self.assertRaises(StatementError), engine.begin() as connection:
                        connection.execute(insert(values).values(**row))
            finally:
                engine.dispose()
