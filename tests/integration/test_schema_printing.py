import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from ufm.domain.value_objects import EntityId, UtcDateTime
from ufm.infrastructure.persistence.models.schema import (
    device_identity,
    job_identity_alias,
    metadata,
    print_job,
    print_job_material,
    printer,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 11, tzinfo=UTC))


class PrintingSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ufm-print-schema-")
        self.engine = create_sqlite_engine(Path(self.directory.name) / "ufm.sqlite3")
        metadata.create_all(self.engine)
        self.device_id = EntityId.new()
        self.printer_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(device_identity).values(
                    id=self.device_id,
                    name="workstation",
                    public_id="printing-test-device",
                    created_at=now(),
                )
            )
            connection.execute(
                insert(printer).values(
                    **self.mutable(self.printer_id), name="P1S", enabled=True
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

    def add_job(self, connection: Connection, job_id: EntityId) -> None:
        connection.execute(
            insert(print_job).values(
                **self.mutable(job_id),
                printer_id=self.printer_id,
                source_type="printer",
                status="DETECTED",
                finalization_state="NOT_STARTED",
                detected_at=now(),
                file_name="same.3mf",
                external_job_id="reused-id",
            )
        )

    def test_reprints_may_share_external_id_but_not_occurrence_scope(self) -> None:
        first_job, second_job = EntityId.new(), EntityId.new()
        provider = EntityId.new()
        with self.engine.begin() as connection:
            self.add_job(connection, first_job)
            self.add_job(connection, second_job)
            common = {
                "device_id": self.device_id,
                "created_at": now(),
                "provider": provider,
                "printer_id": self.printer_id,
                "source_type": "printer",
                "source_epoch": "epoch-1",
                "external_job_id": "reused-id",
                "file_hash": "same-hash",
            }
            connection.execute(
                insert(job_identity_alias),
                [
                    dict(common, id=EntityId.new(), print_job_id=first_job, occurrence_key="run-1"),
                    dict(common, id=EntityId.new(), print_job_id=second_job, occurrence_key="run-2"),
                ],
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(job_identity_alias).values(
                    id=EntityId.new(),
                    device_id=self.device_id,
                    created_at=now(),
                    print_job_id=second_job,
                    provider=provider,
                    printer_id=self.printer_id,
                    source_type="printer",
                    source_epoch="epoch-1",
                    occurrence_key="run-1",
                )
            )

    def test_material_channel_is_unique_only_within_job(self) -> None:
        first_job, second_job = EntityId.new(), EntityId.new()
        with self.engine.begin() as connection:
            self.add_job(connection, first_job)
            self.add_job(connection, second_job)
            for job_id in (first_job, second_job):
                connection.execute(
                    insert(print_job_material).values(
                        **self.mutable(),
                        print_job_id=job_id,
                        channel_key="tool-0",
                        tool_index=0,
                    )
                )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(print_job_material).values(
                    **self.mutable(),
                    print_job_id=first_job,
                    channel_key="tool-0",
                    tool_index=1,
                )
            )

    def test_progress_and_layer_bounds_are_database_enforced(self) -> None:
        for values in (
            {"progress_bp": 10_001},
            {"current_layer": 3, "total_layers": 2},
            {"actual_duration_sec": -1},
        ):
            with self.subTest(values=values), self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(
                    insert(print_job).values(
                        **self.mutable(),
                        printer_id=self.printer_id,
                        source_type="printer",
                        status="RUNNING",
                        finalization_state="NOT_STARTED",
                        detected_at=now(),
                        **values,
                    )
                )
