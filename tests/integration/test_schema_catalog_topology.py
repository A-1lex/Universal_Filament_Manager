import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from ufm.domain.value_objects import EntityId, ExactDecimal, UtcDateTime
from ufm.infrastructure.persistence.models.schema import (
    connection_profile,
    device_identity,
    filament_profile,
    material_feed_system,
    metadata,
    printer,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 11, tzinfo=UTC))


def mutable(device_id: EntityId, entity_id: EntityId | None = None) -> dict[str, object]:
    return {
        "id": entity_id or EntityId.new(),
        "device_id": device_id,
        "created_at": now(),
        "updated_at": now(),
        "revision": 1,
    }


class CatalogTopologySchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ufm-schema-")
        self.engine = create_sqlite_engine(Path(self.directory.name) / "ufm.sqlite3")
        metadata.create_all(self.engine)
        self.device_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(device_identity).values(
                    id=self.device_id,
                    name="workstation",
                    public_id="device-public-id",
                    created_at=now(),
                )
            )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.directory.cleanup()

    def test_expected_first_slice_tables_exist(self) -> None:
        self.assertGreaterEqual(
            set(metadata.tables),
            {
                "brand",
                "calibration_record",
                "connection_profile",
                "device_identity",
                "external_event_receipt",
                "feed_slot",
                "filament_profile",
                "inventory_evidence",
                "material_feed_system",
                "material_usage_segment",
                "printer",
                "print_job",
                "print_job_material",
                "job_identity_alias",
                "project",
                "sensor_device",
                "spool",
                "spool_identifier",
                "spool_mount",
                "storage_location",
            },
        )

    def test_origin_foreign_key_and_revision_are_database_enforced(self) -> None:
        invalid = mutable(EntityId.new())
        invalid["revision"] = 0
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(printer).values(**invalid, name="P1S", enabled=True)
            )

    def test_custom_material_shape_is_database_enforced(self) -> None:
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(filament_profile).values(
                    **mutable(self.device_id),
                    name="Custom",
                    material_type="CUSTOM",
                    diameter_mm=ExactDecimal.parse("1.75"),
                )
            )

    def test_one_connection_per_printer_and_safe_credential_reference(self) -> None:
        printer_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(printer).values(
                    **mutable(self.device_id, printer_id), name="P1S", enabled=True
                )
            )
            connection.execute(
                insert(connection_profile).values(
                    **mutable(self.device_id),
                    printer_id=printer_id,
                    provider_type="bambu",
                    connection_mode="LOCAL",
                    tls_enabled=True,
                    credential_ref="ufm:credential:00000000-0000-0000-0000-000000000001",
                )
            )
        duplicate = dict(
            **mutable(self.device_id),
            printer_id=printer_id,
            provider_type="other",
            connection_mode="LOCAL",
            tls_enabled=True,
        )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(connection_profile).values(**duplicate))
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            second_printer_id = EntityId.new()
            connection.execute(
                insert(printer).values(
                    **mutable(self.device_id, second_printer_id), name="P1S 2", enabled=True
                )
            )
            connection.execute(
                insert(connection_profile).values(
                    **mutable(self.device_id),
                    printer_id=second_printer_id,
                    provider_type="bambu",
                    connection_mode="LOCAL",
                    tls_enabled=True,
                    credential_ref="plaintext",
                )
            )

    def test_provider_feed_key_is_unique_only_when_known(self) -> None:
        printer_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(printer).values(
                    **mutable(self.device_id, printer_id), name="P1S", enabled=True
                )
            )
            base = dict(
                device_id=self.device_id,
                created_at=now(),
                updated_at=now(),
                revision=1,
                printer_id=printer_id,
                kind="EXTERNAL",
                name="External",
            )
            connection.execute(
                insert(material_feed_system),
                [
                    dict(base, id=EntityId.new(), provider_system_key=None),
                    dict(base, id=EntityId.new(), provider_system_key=None),
                    dict(base, id=EntityId.new(), provider_system_key="external"),
                ],
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(material_feed_system).values(
                    **mutable(self.device_id),
                    printer_id=printer_id,
                    provider_system_key="external",
                    kind="EXTERNAL",
                    name="Duplicate",
                )
            )
