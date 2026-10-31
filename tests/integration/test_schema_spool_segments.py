import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models.schema import (
    device_identity,
    feed_slot,
    filament_profile,
    inventory_evidence,
    material_feed_system,
    material_usage_segment,
    metadata,
    print_job,
    print_job_material,
    printer,
    spool,
    spool_identifier,
    spool_mount,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 11, tzinfo=UTC))


class SpoolSegmentSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ufm-spool-schema-")
        self.engine = create_sqlite_engine(Path(self.directory.name) / "ufm.sqlite3")
        metadata.create_all(self.engine)
        self.device_id = EntityId.new()
        self.profile_id = EntityId.new()
        self.printer_id = EntityId.new()
        self.system_id = EntityId.new()
        self.slot_ids = (EntityId.new(), EntityId.new())
        with self.engine.begin() as connection:
            connection.execute(
                insert(device_identity).values(
                    id=self.device_id,
                    name="workstation",
                    public_id="spool-segment-device",
                    created_at=now(),
                )
            )
            connection.execute(
                insert(filament_profile).values(
                    **self.mutable(self.profile_id),
                    name="PLA",
                    material_type="PLA",
                    diameter_mm=ExactDecimal.parse("1.75"),
                )
            )
            connection.execute(
                insert(printer).values(
                    **self.mutable(self.printer_id), name="P1S", enabled=True
                )
            )
            connection.execute(
                insert(material_feed_system).values(
                    **self.mutable(self.system_id),
                    printer_id=self.printer_id,
                    provider_system_key="external",
                    kind="EXTERNAL",
                    name="External",
                )
            )
            for index, slot_id in enumerate(self.slot_ids):
                connection.execute(
                    insert(feed_slot).values(
                        **self.mutable(slot_id),
                        feed_system_id=self.system_id,
                        slot_key=f"slot-{index}",
                        tool_index=index,
                        assignment_state="EMPTY",
                    )
                )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.directory.cleanup()

    def mutable(self, entity_id: EntityId | None = None) -> dict[str, object]:
        return {
            "id": entity_id or EntityId.new(),
            "device_id": self.device_id,
            "created_at": now(),
            "updated_at": now(),
            "revision": 1,
        }

    def spool_values(self, spool_id: EntityId, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            **self.mutable(spool_id),
            "display_name": "PLA spool",
            "filament_profile_id": self.profile_id,
            "diameter_mm": ExactDecimal.parse("1.75"),
            "ledger_sequence": 0,
            "lifecycle": "OPEN",
            "inventory_health": "CONSISTENT",
        }
        values.update(overrides)
        return values

    def test_negative_effective_stock_requires_quarantine(self) -> None:
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(spool).values(
                    **self.spool_values(EntityId.new(), effective_remaining_mg=Mass(-1))
                )
            )
        with self.engine.begin() as connection:
            connection.execute(
                insert(spool).values(
                    **self.spool_values(
                        EntityId.new(),
                        effective_remaining_mg=Mass(-1),
                        inventory_health="QUARANTINED",
                    )
                )
            )

    def test_trusted_current_identifier_cannot_map_to_two_spools(self) -> None:
        spool_ids = (EntityId.new(), EntityId.new())
        with self.engine.begin() as connection:
            for spool_id in spool_ids:
                connection.execute(insert(spool).values(**self.spool_values(spool_id)))
            common = {
                "device_id": self.device_id,
                "created_at": now(),
                "updated_at": now(),
                "revision": 1,
                "namespace": "bambu",
                "kind": "tray_uuid",
                "value": "same-id",
            }
            for spool_id in spool_ids:
                connection.execute(
                    insert(spool_identifier).values(
                        **common,
                        id=EntityId.new(),
                        spool_id=spool_id,
                    )
                )
        with self.engine.begin() as connection:
            connection.execute(
                insert(spool_identifier).values(
                    **self.mutable(),
                    spool_id=spool_ids[0],
                    namespace="bambu",
                    kind="tray_uuid",
                    value="trusted-id",
                    verified_at=now(),
                )
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(spool_identifier).values(
                    **self.mutable(),
                    spool_id=spool_ids[1],
                    namespace="bambu",
                    kind="tray_uuid",
                    value="trusted-id",
                    verified_at=now(),
                )
            )

    def test_active_mount_is_unique_for_both_spool_and_slot(self) -> None:
        spool_ids = (EntityId.new(), EntityId.new())
        with self.engine.begin() as connection:
            for spool_id in spool_ids:
                connection.execute(insert(spool).values(**self.spool_values(spool_id)))
            connection.execute(
                insert(spool_mount).values(
                    **self.mutable(),
                    feed_slot_id=self.slot_ids[0],
                    spool_id=spool_ids[0],
                    state="ACTIVE",
                    mounted_at=now(),
                    assignment_source="MANUAL",
                    confidence_bp=10_000,
                )
            )
        conflicts = (
            (self.slot_ids[1], spool_ids[0]),
            (self.slot_ids[0], spool_ids[1]),
        )
        for slot_id, spool_id in conflicts:
            with self.subTest(slot_id=slot_id), self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(
                    insert(spool_mount).values(
                        **self.mutable(),
                        feed_slot_id=slot_id,
                        spool_id=spool_id,
                        state="ACTIVE",
                        mounted_at=now(),
                        assignment_source="MANUAL",
                        confidence_bp=10_000,
                    )
                )

    def test_inventory_evidence_enforces_exact_mass_relation(self) -> None:
        spool_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(insert(spool).values(**self.spool_values(spool_id)))
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(inventory_evidence).values(
                    id=EntityId.new(),
                    device_id=self.device_id,
                    created_at=now(),
                    spool_id=spool_id,
                    gross_mg=Mass(1_000),
                    tare_mg=Mass(200),
                    net_mg=Mass(799),
                    captured_at=now(),
                    received_at=now(),
                    source_type="SCALE",
                )
            )

    def test_open_segment_is_unique_and_assigned_shape_is_complete(self) -> None:
        job_id, material_id = EntityId.new(), EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(print_job).values(
                    **self.mutable(job_id),
                    printer_id=self.printer_id,
                    source_type="printer",
                    status="RUNNING",
                    finalization_state="NOT_STARTED",
                    detected_at=now(),
                )
            )
            connection.execute(
                insert(print_job_material).values(
                    **self.mutable(material_id),
                    print_job_id=job_id,
                    channel_key="tool-0",
                    tool_index=0,
                )
            )
            connection.execute(
                insert(material_usage_segment).values(
                    **self.mutable(),
                    print_job_material_id=material_id,
                    tool_index=0,
                    assignment_state="ACTIVE_SPOOL_UNKNOWN",
                    started_at=now(),
                    source="provider",
                    confidence_bp=5_000,
                )
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(material_usage_segment).values(
                    **self.mutable(),
                    print_job_material_id=material_id,
                    tool_index=0,
                    assignment_state="ACTIVE_SPOOL_UNKNOWN",
                    started_at=now(),
                    source="provider",
                    confidence_bp=5_000,
                )
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(material_usage_segment).values(
                    **self.mutable(),
                    print_job_material_id=material_id,
                    tool_index=0,
                    assignment_state="ASSIGNED",
                    started_at=now(),
                    ended_at=now(),
                    source="provider",
                    confidence_bp=10_000,
                )
            )
