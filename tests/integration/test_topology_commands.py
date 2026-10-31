"""Phase 4 physical mount commands through a real SQLite transaction."""

import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

from sqlalchemy import insert, select, update

from ufm.application.dto.providers import (
    FeedSlotSnapshot,
    FeedSystemSnapshot,
    Observed,
)
from ufm.application.inventory import InventoryCommands
from ufm.application.job_material_mapping import (
    JobMaterialMappingState,
    JobMaterialSlotResolution,
)
from ufm.application.mounted_material_mapping import (
    MountedMaterialState,
    resolve_mounted_material,
)
from ufm.application.ports.persistence import (
    IdempotencyConflict,
    NotFound,
    PersistenceError,
    RevisionConflict,
)
from ufm.application.reservations import ReservationCommands
from ufm.application.spool_identifiers import SpoolIdentifierCommands
from ufm.application.topology import ProviderSlotSnapshotDisposition, TopologyCommands
from ufm.domain.enums import (
    AssignmentSource,
    Availability,
    FeedSystemKind,
    MountState,
    SlotAssignment,
)
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models.ledger import audit_event, reconciliation_task
from ufm.infrastructure.persistence.models.schema import (
    device_identity,
    feed_slot,
    filament_profile,
    material_feed_system,
    material_usage_segment,
    print_job,
    print_job_material,
    printer,
    spool_mount,
)
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class TopologyCommandTests(unittest.TestCase):
    def _mounted_material_fixture(self, *, mounted_spool: EntityId | None = None):
        observed_at = UtcDateTime(self.now.value + timedelta(seconds=1))
        received_at = UtcDateTime(self.now.value + timedelta(seconds=2))

        def known(value):
            return Observed(Availability.KNOWN, observed_at, received_at, value)

        def unknown():
            return Observed(Availability.UNKNOWN, observed_at, received_at)

        snapshot = FeedSlotSnapshot(
            "slot-0",
            known(True),
            known("private-tray-01"),
            unknown(),
            unknown(),
            unknown(),
        )
        feed_system = FeedSystemSnapshot(
            "external",
            FeedSystemKind.EXTERNAL,
            (snapshot,),
            observed_at,
            received_at,
            True,
            "epoch-current",
            3,
        )
        self.commands.observe_provider_slot(
            printer_id=self.printer,
            system_id=self.system,
            provider_system_key="external",
            system_kind=FeedSystemKind.EXTERNAL,
            slot_id=self.slots[0],
            snapshot=snapshot,
            observed_at=observed_at,
            received_at=received_at,
            source_epoch="epoch-current",
            source_sequence=3,
            actor_device_id=self.device,
        )
        spool_id = mounted_spool or self.spools[0]
        SpoolIdentifierCommands(lambda: SQLiteUnitOfWork(self.engine)).verify(
            spool_id=spool_id,
            namespace="test-printer",
            kind="tray_uuid",
            value="private-tray-01",
            actor_device_id=self.device,
            command_key="verify-mounted-tray",
            manual_confirmation=True,
            at=self.now,
        )
        self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-material-slot",
            at=self.now,
        )
        resolution = JobMaterialSlotResolution(
            0,
            JobMaterialMappingState.MATCHED,
            "external",
            "slot-0",
            snapshot,
        )
        return feed_system, snapshot, resolution, UtcDateTime(self.now.value + timedelta(seconds=3))

    def test_exact_job_slot_rfid_and_active_mount_join_is_read_only(self) -> None:
        system, _, resolution, now = self._mounted_material_fixture()
        with SQLiteUnitOfWork(self.engine) as work:
            result = resolve_mounted_material(
                work,
                resolution=resolution,
                feed_system=system,
                printer_id=self.printer,
                identifier_namespace="test-printer",
                now=now,
            )
            self.assertEqual(result.state, MountedMaterialState.MATCHED)
            self.assertEqual(result.feed_slot_id, self.slots[0])
            self.assertEqual(result.spool_id, self.spools[0])
            self.assertIsNotNone(result.mount_id)
            self.assertEqual(work.ledger.for_spool(self.spools[0]), [])

    def test_mounted_slot_join_fails_on_unpersisted_snapshot_or_wrong_rfid_spool(self) -> None:
        system, snapshot, resolution, now = self._mounted_material_fixture(
            mounted_spool=self.spools[0],
        )
        SpoolIdentifierCommands(lambda: SQLiteUnitOfWork(self.engine)).verify(
            spool_id=self.spools[1],
            namespace="test-printer",
            kind="tray_uuid",
            value="private-tray-other",
            actor_device_id=self.device,
            command_key="verify-other-tray",
            manual_confirmation=True,
            at=self.now,
        )
        unprojected_observed = UtcDateTime(system.observed_at.value + timedelta(seconds=1))
        unprojected_received = UtcDateTime(system.received_at.value + timedelta(seconds=1))
        unprojected_system = FeedSystemSnapshot(
            system.provider_system_key,
            system.kind,
            (snapshot,),
            unprojected_observed,
            unprojected_received,
            system.complete,
            system.source_epoch,
            system.source_sequence + 1,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            unprojected = resolve_mounted_material(
                work,
                resolution=resolution,
                feed_system=unprojected_system,
                printer_id=self.printer,
                identifier_namespace="test-printer",
                now=now,
            )
            self.assertEqual(unprojected.state, MountedMaterialState.UNKNOWN)
            self.assertEqual(unprojected.reason_code, "provider_snapshot_not_durable")

        tampered_snapshot = FeedSlotSnapshot(
            snapshot.slot_key,
            snapshot.occupancy,
            Observed(
                Availability.KNOWN,
                snapshot.tray_uuid.observed_at,
                snapshot.tray_uuid.received_at,
                "private-tray-forged",
            ),
            snapshot.tag_uid,
            snapshot.assigned_spool_id,
            snapshot.remaining_mass,
        )
        tampered_system = FeedSystemSnapshot(
            system.provider_system_key,
            system.kind,
            (tampered_snapshot,),
            system.observed_at,
            system.received_at,
            system.complete,
            system.source_epoch,
            system.source_sequence,
        )
        tampered_resolution = JobMaterialSlotResolution(
            resolution.logical_material,
            JobMaterialMappingState.MATCHED,
            resolution.provider_system_key,
            resolution.provider_slot_key,
            tampered_snapshot,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            tampered = resolve_mounted_material(
                work,
                resolution=tampered_resolution,
                feed_system=tampered_system,
                printer_id=self.printer,
                identifier_namespace="test-printer",
                now=now,
            )
            self.assertEqual(tampered.state, MountedMaterialState.UNKNOWN)
            self.assertEqual(tampered.reason_code, "provider_snapshot_audit_proof_missing")

        observed_at = UtcDateTime(system.observed_at.value + timedelta(seconds=1))
        received_at = UtcDateTime(system.received_at.value + timedelta(seconds=1))
        changed_snapshot = FeedSlotSnapshot(
            snapshot.slot_key,
            Observed(Availability.KNOWN, observed_at, received_at, True),
            Observed(Availability.KNOWN, observed_at, received_at, "private-tray-other"),
            Observed(Availability.UNKNOWN, observed_at, received_at),
            Observed(Availability.UNKNOWN, observed_at, received_at),
            Observed(Availability.UNKNOWN, observed_at, received_at),
        )
        changed_system = FeedSystemSnapshot(
            system.provider_system_key,
            system.kind,
            (changed_snapshot,),
            observed_at,
            received_at,
            system.complete,
            system.source_epoch,
            system.source_sequence + 1,
        )
        self.assertEqual(
            self.commands.observe_provider_slot(
                printer_id=self.printer,
                system_id=self.system,
                provider_system_key=changed_system.provider_system_key,
                system_kind=changed_system.kind,
                slot_id=self.slots[0],
                snapshot=changed_snapshot,
                observed_at=observed_at,
                received_at=received_at,
                source_epoch=changed_system.source_epoch,
                source_sequence=changed_system.source_sequence,
                actor_device_id=self.device,
            ).value,
            "APPLIED",
        )
        changed_resolution = JobMaterialSlotResolution(
            resolution.logical_material,
            JobMaterialMappingState.MATCHED,
            resolution.provider_system_key,
            resolution.provider_slot_key,
            changed_snapshot,
        )
        changed_now = UtcDateTime(received_at.value + timedelta(seconds=1))
        with SQLiteUnitOfWork(self.engine) as work:
            conflict = resolve_mounted_material(
                work,
                resolution=changed_resolution,
                feed_system=changed_system,
                printer_id=self.printer,
                identifier_namespace="test-printer",
                now=changed_now,
            )
            self.assertEqual(conflict.state, MountedMaterialState.CONFLICT)
            self.assertEqual(conflict.reason_code, "mounted_spool_identity_mismatch")

    def test_feed_slot_exact_provider_key_lookup_is_printer_scoped(self) -> None:
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(
                work.slots.by_provider_key(self.printer, "external", "slot-0").id,
                self.slots[0],
            )
            self.assertIsNone(
                work.slots.by_provider_key(
                    EntityId.new(),
                    "external",
                    "slot-0",
                )
            )
            self.assertIsNone(
                work.slots.by_provider_key(
                    self.printer,
                    "unknown-system",
                    "slot-0",
                )
            )
            self.assertIsNone(
                work.slots.by_provider_key(
                    self.printer,
                    "external",
                    "unknown-slot",
                )
            )

    def test_provider_slot_snapshot_is_audited_ordered_and_never_changes_assignment(self) -> None:
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="snapshot-initial-mount",
            at=self.now,
        )

        def snapshot(
            at: UtcDateTime, tray_id: str, remaining_percent: int | None = None,
        ) -> FeedSlotSnapshot:
            def known(value):
                return Observed(Availability.KNOWN, at, at, value)

            def unknown():
                return Observed(Availability.UNKNOWN, at, at)

            observed_percent = (
                Observed(Availability.KNOWN, at, at, remaining_percent)
                if remaining_percent is not None else None
            )
            return FeedSlotSnapshot(
                "slot-0",
                unknown(),
                known(tray_id),
                unknown(),
                unknown(),
                unknown(),
                observed_percent,
            )

        def observe(
            *,
            epoch: str | None,
            sequence: int | None,
            at: UtcDateTime,
            tray_id: str = "private-tray-001",
            remaining_percent: int | None = None,
        ):
            return self.commands.observe_provider_slot(
                printer_id=self.printer,
                system_id=self.system,
                provider_system_key="external",
                system_kind=FeedSystemKind.EXTERNAL,
                slot_id=self.slots[0],
                snapshot=snapshot(at, tray_id, remaining_percent),
                observed_at=at,
                received_at=at,
                source_epoch=epoch,
                source_sequence=sequence,
                actor_device_id=self.device,
            )

        first_at = UtcDateTime(self.now.value + timedelta(seconds=1))
        second_at = UtcDateTime(self.now.value + timedelta(seconds=2))
        third_at = UtcDateTime(self.now.value + timedelta(seconds=3))
        self.assertEqual(
            observe(epoch="boot-a", sequence=5, at=first_at),
            ProviderSlotSnapshotDisposition.APPLIED,
        )
        self.assertEqual(
            observe(epoch="boot-a", sequence=5, at=first_at),
            ProviderSlotSnapshotDisposition.DUPLICATE,
        )
        with self.assertRaises(IdempotencyConflict):
            observe(epoch="boot-a", sequence=5, at=first_at, tray_id="different-private-id")
        with self.assertRaises(IdempotencyConflict):
            observe(epoch="boot-a", sequence=5, at=first_at, remaining_percent=61)
        self.assertEqual(
            observe(epoch="boot-a", sequence=4, at=second_at), ProviderSlotSnapshotDisposition.STALE
        )
        self.assertEqual(
            observe(epoch="boot-b", sequence=1, at=third_at),
            ProviderSlotSnapshotDisposition.APPLIED,
        )

        with SQLiteUnitOfWork(self.engine) as work:
            slot = work.slots.get(self.slots[0])
            self.assertEqual(slot.assignment_state, SlotAssignment.ASSIGNED)
            self.assertEqual(slot.observed_at, third_at)
            self.assertEqual(slot.received_at, third_at)
            self.assertEqual(slot.source_epoch, "boot-b")
            self.assertEqual(slot.source_sequence, 1)
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(work.ledger.for_spool(self.spools[0]), [])
        with self.engine.connect() as connection:
            params = (
                connection.execute(
                    select(audit_event.c.parameters_json).where(
                        audit_event.c.event_code == "feed_slot.snapshot_observed",
                    )
                )
                .scalars()
                .all()
            )
        self.assertTrue(params)
        self.assertTrue(all("private-tray-001" not in value for value in params))

    def test_command_keys_conflict_across_inventory_topology_and_reservations(self) -> None:
        inventory = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        reservations = ReservationCommands(lambda: SQLiteUnitOfWork(self.engine))
        inventory.establish_opening_stock(
            spool_id=self.spools[0],
            amount=Mass(700),
            command_key="opening",
            actor_device_id=self.device,
            at=self.now,
        )
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="placement",
            at=self.now,
        )
        material = self._running_material()
        args = dict(
            reservation_id=EntityId.new(),
            spool_id=self.spools[0],
            material_id=material,
            amount=Mass(100),
            activate=False,
            actor_device_id=self.device,
            at=self.now,
        )
        with self.assertRaises(IdempotencyConflict):
            reservations.reserve(**args, command_key="placement")
        claim = reservations.reserve(**args, command_key="proposal")
        with self.assertRaises(IdempotencyConflict):
            inventory.adjust(
                spool_id=self.spools[0],
                delta=Mass(-100),
                command_key="proposal",
                actor_device_id=self.device,
                at=self.now,
            )
        with self.assertRaises(IdempotencyConflict):
            self.commands.mark_assignment_unknown(
                slot_id=self.slots[0],
                expected_slot_revision=2,
                actor_device_id=self.device,
                command_key="proposal",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), mounted)
            self.assertEqual(work.reservations.get(claim.id), claim)
            self.assertEqual(work.spools.get(self.spools[0]).effective_remaining, Mass(700))
            self.assertEqual(len(work.audit.for_command("proposal")), 1)

    def test_concurrent_cross_family_key_has_one_success(self) -> None:
        barrier = Barrier(2)

        def run(operation: str) -> str:
            barrier.wait(timeout=10)
            try:
                if operation == "opening":
                    InventoryCommands(
                        lambda: SQLiteUnitOfWork(self.engine)
                    ).establish_opening_stock(
                        spool_id=self.spools[0],
                        amount=Mass(100),
                        command_key="shared-race",
                        actor_device_id=self.device,
                        at=self.now,
                    )
                else:
                    self.commands.mount_spool(
                        mount_id=EntityId.new(),
                        slot_id=self.slots[0],
                        spool_id=self.spools[0],
                        actor_device_id=self.device,
                        command_key="shared-race",
                        at=self.now,
                    )
            except IdempotencyConflict:
                return "conflict"
            return operation

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, operation) for operation in ("opening", "mount")]
            outcomes = [future.result(timeout=20) for future in futures]
        self.assertEqual(outcomes.count("conflict"), 1)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.audit.for_command("shared-race")), 1)
            self.assertEqual(
                work.spools.get(self.spools[0]).effective_remaining,
                Mass(100) if "opening" in outcomes else None,
            )
            self.assertEqual(
                work.mounts.active_for_slot(self.slots[0]) is not None, "mount" in outcomes
            )

    def test_process_exit_swap_recovers_mount_segment_and_receipt_atomically(self) -> None:
        material = self._running_material()
        old_segment, new_segment, new_mount = EntityId.new(), EntityId.new(), EntityId.new()
        old_mount = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            material_id=material,
            segment_id=old_segment,
            actor_device_id=self.device,
            command_key="crash-initial-mount",
            at=self.now,
        )
        worker = """
import os
import sys
from pathlib import Path
from ufm.application.topology import TopologyCommands
from ufm.domain.value_objects import EntityId
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
engine = create_sqlite_engine(Path(sys.argv[1]))
original = SQLiteUnitOfWork.commit
def crash_commit(self):
    if sys.argv[2] == "after":
        original(self)
    os._exit(38)
SQLiteUnitOfWork.commit = crash_commit
ids = [EntityId.parse(value) for value in sys.argv[3:]]
TopologyCommands(lambda: SQLiteUnitOfWork(engine)).swap_spool(
    expected_mount_id=ids[0], new_mount_id=ids[1], slot_id=ids[2],
    new_spool_id=ids[3], actor_device_id=ids[4], material_id=ids[5],
    new_segment_id=ids[6], command_key="crash-swap",
)
"""
        database = str(self.engine.url.database)
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        worker,
                        database,
                        boundary,
                        *map(
                            str,
                            (
                                old_mount.id,
                                new_mount,
                                self.slots[0],
                                self.spools[1],
                                self.device,
                                material,
                                new_segment,
                            ),
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 38, result.stderr)
                reopened = create_sqlite_engine(Path(database))
                try:
                    with SQLiteUnitOfWork(reopened) as work:
                        mounted = work.mounts.active_for_slot(self.slots[0])
                        active_segment = work.segments.active_for_material(material)
                        self.assertEqual(
                            mounted.id, old_mount.id if boundary == "before" else new_mount
                        )
                        self.assertEqual(
                            active_segment.id, old_segment if boundary == "before" else new_segment
                        )
                        self.assertEqual(
                            work.mounts.get(old_mount.id).state,
                            MountState.ACTIVE if boundary == "before" else MountState.CLOSED,
                        )
                        self.assertEqual(
                            len(work.audit.for_command("crash-swap")),
                            0 if boundary == "before" else 1,
                        )
                    if boundary == "after":
                        replay = TopologyCommands(
                            lambda engine=reopened: SQLiteUnitOfWork(engine),
                        ).swap_spool(
                            expected_mount_id=old_mount.id,
                            new_mount_id=new_mount,
                            slot_id=self.slots[0],
                            new_spool_id=self.spools[1],
                            actor_device_id=self.device,
                            material_id=material,
                            new_segment_id=new_segment,
                            command_key="crash-swap",
                        )
                        self.assertEqual(replay.id, new_mount)
                        with reopened.connect() as connection:
                            segments = (
                                connection.execute(select(material_usage_segment)).mappings().all()
                            )
                            self.assertEqual(len(segments), 2)
                            old = next(row for row in segments if row["id"] == old_segment)
                            new = next(row for row in segments if row["id"] == new_segment)
                            self.assertEqual(old["ended_at"], new["started_at"])
                            self.assertEqual(
                                connection.exec_driver_sql("PRAGMA integrity_check").scalar_one(),
                                "ok",
                            )
                            self.assertEqual(
                                connection.exec_driver_sql("PRAGMA foreign_key_check").all(), []
                            )
                finally:
                    reopened.dispose()

    def _running_material(self) -> EntityId:
        job_id, material_id = EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device,
            created_at=self.now,
            updated_at=self.now,
            revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(
                insert(print_job).values(
                    **common,
                    id=job_id,
                    printer_id=self.printer,
                    source_type="manual",
                    status="RUNNING",
                    finalization_state="NOT_STARTED",
                    detected_at=self.now,
                )
            )
            connection.execute(
                insert(print_job_material).values(
                    **common,
                    id=material_id,
                    print_job_id=job_id,
                    channel_key="tool-0",
                    tool_index=0,
                )
            )
        return material_id

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="ufm-topology-commands-")
        self.addCleanup(directory.cleanup)
        self.engine = create_sqlite_engine(Path(directory.name) / "test.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.device, self.profile = EntityId.new(), EntityId.new()
        self.printer, self.system = EntityId.new(), EntityId.new()
        self.slots = (EntityId.new(), EntityId.new())
        self.spools = (EntityId.new(), EntityId.new(), EntityId.new())
        self.now = UtcDateTime.now()
        common = dict(
            device_id=self.device,
            created_at=self.now,
            updated_at=self.now,
            revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(
                insert(device_identity).values(
                    id=self.device,
                    name="test",
                    public_id=str(self.device),
                    created_at=self.now,
                )
            )
            connection.execute(
                insert(filament_profile).values(
                    **common,
                    id=self.profile,
                    name="PLA",
                    material_type="PLA",
                    diameter_mm=ExactDecimal.parse("1.75"),
                )
            )
            connection.execute(
                insert(printer).values(
                    **common,
                    id=self.printer,
                    name="P1S",
                    enabled=True,
                )
            )
            connection.execute(
                insert(material_feed_system).values(
                    **common,
                    id=self.system,
                    printer_id=self.printer,
                    provider_system_key="external",
                    kind="EXTERNAL",
                    name="External",
                )
            )
            for index, slot_id in enumerate(self.slots):
                connection.execute(
                    insert(feed_slot).values(
                        **common,
                        id=slot_id,
                        feed_system_id=self.system,
                        slot_key=f"slot-{index}",
                        tool_index=index,
                        assignment_state="EMPTY",
                    )
                )
        inventory = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        for index, spool_id in enumerate(self.spools):
            inventory.create_spool(
                spool_id=spool_id,
                filament_profile_id=self.profile,
                display_name=f"spool-{index}",
                actor_device_id=self.device,
                command_key=f"create-{index}",
                at=self.now,
            )
        inventory.archive_spool(
            spool_id=self.spools[2],
            expected_revision=1,
            actor_device_id=self.device,
            command_key="archive-third",
            at=self.now,
        )
        self.commands = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))

    def test_mount_request_replay_after_unmount_preserves_new_assignment(self) -> None:
        args = dict(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-request",
            at=self.now,
        )
        first = self.commands.mount_spool(**args)
        closed = self.commands.unmount_slot(
            slot_id=self.slots[0],
            expected_mount_id=first.id,
            actor_device_id=self.device,
            command_key="close-request",
            at=self.now,
        )
        second = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="second-request",
            at=self.now,
        )
        restarted = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.mount_spool(**args), closed)
        for changes in (
            {"actor_device_id": EntityId.new()},
            {"material_id": EntityId.new()},
            {"segment_id": EntityId.new()},
            {"spool_id": self.spools[1]},
        ):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                restarted.mount_spool(**(args | changes))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), second)
            self.assertEqual(len(work.audit.for_command("mount-request")), 1)

    def test_swap_request_replays_after_later_unmount(self) -> None:
        first = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="initial",
            at=self.now,
        )
        args = dict(
            expected_mount_id=first.id,
            new_mount_id=EntityId.new(),
            slot_id=self.slots[0],
            new_spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="swap-request",
            at=self.now,
        )
        swapped = self.commands.swap_spool(**args)
        closed = self.commands.unmount_slot(
            slot_id=self.slots[0],
            expected_mount_id=swapped.id,
            actor_device_id=self.device,
            command_key="close-swap",
            at=self.now,
        )
        restarted = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.swap_spool(**args), closed)
        for change in (
            {"expected_mount_id": EntityId.new()},
            {"actor_device_id": EntityId.new()},
            {"material_id": EntityId.new()},
            {"new_segment_id": EntityId.new()},
        ):
            with self.subTest(change=change), self.assertRaises(IdempotencyConflict):
                restarted.swap_spool(**(args | change))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNone(work.mounts.active_for_slot(self.slots[0]))
            self.assertEqual(len(work.audit.for_command("swap-request")), 1)

    def test_unknown_request_replay_preserves_restored_assignment(self) -> None:
        args = dict(
            slot_id=self.slots[0],
            expected_slot_revision=1,
            actor_device_id=self.device,
            command_key="unknown-request",
            at=self.now,
        )
        self.commands.mark_assignment_unknown(**args)
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="restore-known",
            at=self.now,
        )
        restarted = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(
            restarted.mark_assignment_unknown(**args).assignment_state,
            SlotAssignment.ASSIGNED,
        )
        for change in (
            {"expected_slot_revision": 3},
            {"actor_device_id": EntityId.new()},
            {"material_id": EntityId.new()},
            {"slot_id": self.slots[1]},
        ):
            with self.subTest(change=change), self.assertRaises(IdempotencyConflict):
                restarted.mark_assignment_unknown(**(args | change))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), mounted)
            self.assertEqual(len(work.audit.for_command("unknown-request")), 1)

    def test_mount_swap_and_unmount_preserve_history(self) -> None:
        first = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        second = self.commands.swap_spool(
            new_mount_id=EntityId.new(),
            slot_id=self.slots[0],
            expected_mount_id=first.id,
            new_spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="swap",
            at=self.now,
        )
        closed = self.commands.unmount_slot(
            slot_id=self.slots[0],
            expected_mount_id=second.id,
            actor_device_id=self.device,
            command_key="unmount",
            at=self.now,
        )
        self.assertEqual(first.state, MountState.ACTIVE)
        self.assertEqual(second.spool_id, self.spools[1])
        self.assertEqual(closed.state, MountState.CLOSED)
        with self.engine.connect() as connection:
            states = (
                connection.execute(
                    select(spool_mount.c.state).order_by(
                        spool_mount.c.created_at,
                        spool_mount.c.id,
                    )
                )
                .scalars()
                .all()
            )
            slot_state = connection.execute(
                select(feed_slot.c.assignment_state).where(
                    feed_slot.c.id == self.slots[0],
                )
            ).scalar_one()
        self.assertEqual(states, ["CLOSED", "CLOSED"])
        self.assertEqual(slot_state, SlotAssignment.EMPTY.value)

    def test_conflicts_and_archived_spool_leave_current_mount_unchanged(self) -> None:
        current = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "spool_mount.slot_occupied"):
            self.commands.mount_spool(
                mount_id=EntityId.new(),
                slot_id=self.slots[0],
                spool_id=self.spools[1],
                actor_device_id=self.device,
                command_key="conflict",
                at=self.now,
            )
        with self.assertRaisesRegex(ValueError, "spool_mount.archived_spool"):
            self.commands.swap_spool(
                new_mount_id=EntityId.new(),
                slot_id=self.slots[0],
                expected_mount_id=current.id,
                new_spool_id=self.spools[2],
                actor_device_id=self.device,
                command_key="bad-swap",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), current)

    def test_swap_rotates_material_usage_segment_atomically(self) -> None:
        job_id, material_id = EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device,
            created_at=self.now,
            updated_at=self.now,
            revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(
                insert(print_job).values(
                    **common,
                    id=job_id,
                    printer_id=self.printer,
                    source_type="manual",
                    status="RUNNING",
                    finalization_state="NOT_STARTED",
                    detected_at=self.now,
                )
            )
            connection.execute(
                insert(print_job_material).values(
                    **common,
                    id=material_id,
                    print_job_id=job_id,
                    channel_key="tool-0",
                    tool_index=0,
                )
            )
        first_segment, second_segment = EntityId.new(), EntityId.new()
        first_mount = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            material_id=material_id,
            segment_id=first_segment,
            at=self.now,
        )
        self.commands.swap_spool(
            new_mount_id=EntityId.new(),
            slot_id=self.slots[0],
            expected_mount_id=first_mount.id,
            new_spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="swap",
            material_id=material_id,
            new_segment_id=second_segment,
            at=self.now,
        )
        with self.engine.connect() as connection:
            segments = connection.execute(
                select(
                    material_usage_segment.c.id,
                    material_usage_segment.c.spool_id,
                    material_usage_segment.c.ended_at,
                )
                .where(
                    material_usage_segment.c.print_job_material_id == material_id,
                )
                .order_by(material_usage_segment.c.id)
            ).all()
        by_id = {row.id: row for row in segments}
        self.assertEqual(len(segments), 2)
        self.assertEqual(by_id[first_segment].spool_id, self.spools[0])
        self.assertIsNotNone(by_id[first_segment].ended_at)
        self.assertEqual(by_id[second_segment].spool_id, self.spools[1])
        self.assertIsNone(by_id[second_segment].ended_at)
        inventory = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        with self.assertRaisesRegex(ValueError, "spool.archive_unresolved_usage"):
            inventory.archive_spool(
                spool_id=self.spools[0],
                expected_revision=1,
                actor_device_id=self.device,
                command_key="archive-unaccounted",
                at=self.now,
            )

    def test_external_slot_setup_and_unknown_assignment(self) -> None:
        slot_id = EntityId.new()
        slot = self.commands.create_external_slot(
            system_id=self.system,
            slot_id=slot_id,
            printer_id=self.printer,
            system_name="External",
            slot_key="slot-extra",
            tool_index=2,
            actor_device_id=self.device,
            command_key="create-slot",
            at=self.now,
        )
        self.assertEqual(slot.assignment_state, SlotAssignment.EMPTY)
        self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=slot_id,
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-extra",
            at=self.now,
        )
        unknown = self.commands.mark_assignment_unknown(
            slot_id=slot_id,
            expected_slot_revision=2,
            actor_device_id=self.device,
            command_key="unknown",
            at=self.now,
        )
        self.assertEqual(unknown.assignment_state, SlotAssignment.ACTIVE_SPOOL_UNKNOWN)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNone(work.mounts.active_for_slot(slot_id))

    def test_external_slot_replay_validates_slot_and_system_identity(self) -> None:
        slot_id = EntityId.new()
        args = dict(
            system_id=self.system,
            slot_id=slot_id,
            printer_id=self.printer,
            system_name="External",
            slot_key="extra",
            tool_index=2,
            actor_device_id=self.device,
            command_key="create-extra",
            at=self.now,
        )
        created = self.commands.create_external_slot(**args)
        self.assertEqual(self.commands.create_external_slot(**args), created)
        for changed in (
            {"tool_index": 3},
            {"slot_key": "different"},
            {"system_id": EntityId.new()},
            {"system_name": "different"},
            {"actor_device_id": EntityId.new()},
            {"command_key": "different-command"},
            {"slot_id": EntityId.new()},
            {"printer_id": EntityId.new()},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(IdempotencyConflict):
                    self.commands.create_external_slot(**(args | changed))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.slots.get(slot_id), created)
            self.assertEqual(len(work.audit.for_command("create-extra")), 1)
        self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=slot_id,
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-created",
            at=self.now,
        )
        restarted = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))
        replay = restarted.create_external_slot(**args)
        self.assertEqual(replay.assignment_state, SlotAssignment.ASSIGNED)
        self.assertEqual(replay.revision, 2)

    def test_external_slot_audit_failure_rolls_back_system_and_slot(self) -> None:
        system_id, slot_id = EntityId.new(), EntityId.new()
        printer_id = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(printer).values(
                    id=printer_id,
                    device_id=self.device,
                    created_at=self.now,
                    updated_at=self.now,
                    revision=1,
                    name="New printer",
                    enabled=True,
                )
            )
        args = dict(
            system_id=system_id,
            slot_id=slot_id,
            printer_id=printer_id,
            system_name="Another external",
            slot_key="new",
            tool_index=2,
            actor_device_id=self.device,
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "audit.field_invalid"):
            self.commands.create_external_slot(**args, command_key="")
        with SQLiteUnitOfWork(self.engine) as work:
            with self.assertRaises(NotFound):
                work.feed_systems.get(system_id)
            with self.assertRaises(NotFound):
                work.slots.get(slot_id)
            self.assertEqual(work.audit.for_command(""), [])
        created = self.commands.create_external_slot(**args, command_key="retry-slot")
        self.assertEqual(
            self.commands.create_external_slot(**args, command_key="retry-slot"), created
        )

    def test_external_slot_cannot_reuse_another_printers_system(self) -> None:
        other_printer = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(
                insert(printer).values(
                    id=other_printer,
                    device_id=self.device,
                    created_at=self.now,
                    updated_at=self.now,
                    revision=1,
                    name="Second",
                    enabled=True,
                )
            )
        with self.assertRaises(IdempotencyConflict):
            self.commands.create_external_slot(
                system_id=self.system,
                slot_id=EntityId.new(),
                printer_id=other_printer,
                system_name="External",
                slot_key="wrong-printer",
                tool_index=2,
                actor_device_id=self.device,
                command_key="wrong-printer",
                at=self.now,
            )

    def test_unknown_assignment_preserves_unresolved_usage_and_deduplicates_task(self) -> None:
        material = self._running_material()
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        changed_at = UtcDateTime(self.now.value + timedelta(minutes=5))
        args = dict(
            slot_id=self.slots[0],
            material_id=material,
            actor_device_id=self.device,
            command_key="unknown",
            at=changed_at,
            expected_slot_revision=2,
        )
        unknown = self.commands.mark_assignment_unknown(**args)
        self.assertEqual(self.commands.mark_assignment_unknown(**args), unknown)
        with SQLiteUnitOfWork(self.engine) as work:
            current = work.segments.active_for_material(material)
            self.assertIsNotNone(current)
            self.assertEqual(current.assignment_state, SlotAssignment.ACTIVE_SPOOL_UNKNOWN)
            self.assertIsNone(current.spool_id)
            self.assertIsNone(current.spool_mount_id)
            self.assertEqual(current.feed_slot_id, self.slots[0])
            self.assertEqual(work.mounts.get(mounted.id).state, MountState.CLOSED)
        with self.engine.connect() as connection:
            segments = connection.execute(select(material_usage_segment)).mappings().all()
            tasks = connection.execute(select(reconciliation_task)).mappings().all()
            audit = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.correlation_id == "unknown",
                    )
                )
                .mappings()
                .all()
            )
        self.assertEqual(len(segments), 2)
        old = next(item for item in segments if item["spool_id"] == self.spools[0])
        new = next(item for item in segments if item["spool_id"] is None)
        self.assertEqual(old["ended_at"], changed_at)
        self.assertEqual(new["started_at"], changed_at)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["reason_code"], "ACTIVE_SPOOL_UNKNOWN")
        self.assertEqual(tasks[0]["feed_slot_id"], self.slots[0])
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["entity_type"], "feed_slot")
        self.assertEqual(audit[0]["entity_id"], str(self.slots[0]))
        restored_at = UtcDateTime(changed_at.value + timedelta(minutes=5))
        self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[1],
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="known-again",
            at=restored_at,
        )
        with self.engine.connect() as connection:
            unknown_history = (
                connection.execute(
                    select(material_usage_segment).where(
                        material_usage_segment.c.assignment_state == "ACTIVE_SPOOL_UNKNOWN",
                    )
                )
                .mappings()
                .one()
            )
            task = connection.execute(select(reconciliation_task)).mappings().one()
        self.assertEqual(unknown_history["ended_at"], restored_at)
        self.assertIsNone(unknown_history["spool_id"])
        self.assertEqual(task["status"], "OPEN")

    def test_unknown_assignment_requires_material_when_slot_has_open_usage(self) -> None:
        material = self._running_material()
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "usage_segment.material_required"):
            self.commands.mark_assignment_unknown(
                slot_id=self.slots[0],
                actor_device_id=self.device,
                command_key="unknown",
                at=self.now,
                expected_slot_revision=2,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(work.segments.active_for_material(material).spool_id, self.spools[0])

    def test_unknown_assignment_rolls_back_all_changes_on_audit_failure(self) -> None:
        material = self._running_material()
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "audit.field_invalid"):
            self.commands.mark_assignment_unknown(
                slot_id=self.slots[0],
                material_id=material,
                actor_device_id=self.device,
                command_key="",
                at=self.now,
                expected_slot_revision=2,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(
                work.slots.get(self.slots[0]).assignment_state, SlotAssignment.ASSIGNED
            )
            self.assertEqual(work.segments.active_for_material(material).spool_id, self.spools[0])
        with self.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(material_usage_segment)).all()), 1)
            self.assertEqual(connection.execute(select(reconciliation_task)).all(), [])

    def test_unknown_assignment_without_prior_mount_checks_material_tool(self) -> None:
        material = self._running_material()
        with self.assertRaisesRegex(ValueError, "usage_segment.tool_mismatch"):
            self.commands.mark_assignment_unknown(
                slot_id=self.slots[1],
                material_id=material,
                actor_device_id=self.device,
                command_key="wrong-tool",
                at=self.now,
                expected_slot_revision=1,
            )
        self.commands.mark_assignment_unknown(
            slot_id=self.slots[0],
            material_id=material,
            actor_device_id=self.device,
            command_key="unknown-from-start",
            at=self.now,
            expected_slot_revision=1,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            current = work.segments.active_for_material(material)
            self.assertIsNotNone(current)
            self.assertEqual(current.assignment_state, SlotAssignment.ACTIVE_SPOOL_UNKNOWN)
            self.assertEqual(current.tool_index, 0)

    def test_unknown_assignment_cannot_close_another_slots_segment(self) -> None:
        material = self._running_material()
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "usage_segment.slot_mismatch"):
            self.commands.mark_assignment_unknown(
                slot_id=self.slots[1],
                material_id=material,
                actor_device_id=self.device,
                command_key="wrong-slot",
                at=self.now,
                expected_slot_revision=1,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(
                work.segments.active_for_material(material).feed_slot_id, self.slots[0]
            )

    def _assert_material_required_for_mount_change(self, operation: str) -> None:
        material = self._running_material()
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        args = dict(
            slot_id=self.slots[0], actor_device_id=self.device, command_key="change", at=self.now
        )
        with self.assertRaisesRegex(ValueError, "usage_segment.material_required"):
            if operation == "swap":
                self.commands.swap_spool(
                    **args,
                    new_mount_id=EntityId.new(),
                    new_spool_id=self.spools[1],
                    expected_mount_id=mounted.id,
                )
            else:
                self.commands.unmount_slot(**args, expected_mount_id=mounted.id)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(work.segments.active_for_material(material).spool_id, self.spools[0])

    def test_unmount_cannot_leave_an_open_usage_segment(self) -> None:
        self._assert_material_required_for_mount_change("unmount")

    def test_swap_cannot_leave_an_open_usage_segment(self) -> None:
        self._assert_material_required_for_mount_change("swap")

    def test_mount_replay_does_not_accept_different_mount_identity_or_provenance(self) -> None:
        args = dict(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        mounted = self.commands.mount_spool(**args)
        self.assertEqual(self.commands.mount_spool(**args), mounted)
        for changed in (
            {"mount_id": EntityId.new()},
            {"assignment_source": AssignmentSource.QR},
            {"confidence_bp": 5000},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(IdempotencyConflict):
                    self.commands.mount_spool(**(args | changed))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), mounted)

    def test_swap_replay_does_not_accept_different_mount_identity_or_provenance(self) -> None:
        first = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        args = dict(
            new_mount_id=EntityId.new(),
            slot_id=self.slots[0],
            new_spool_id=self.spools[1],
            expected_mount_id=first.id,
            actor_device_id=self.device,
            command_key="swap",
            at=self.now,
        )
        swapped = self.commands.swap_spool(**args)
        self.assertEqual(self.commands.swap_spool(**args), swapped)
        for changed in (
            {"new_mount_id": EntityId.new()},
            {"assignment_source": AssignmentSource.QR},
            {"confidence_bp": 5000},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(IdempotencyConflict):
                    self.commands.swap_spool(**(args | changed))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), swapped)

    def test_inventory_quarantine_resolution_requires_accounted_usage(self) -> None:
        inventory = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        spool_id = self.spools[0]
        inventory.establish_opening_stock(
            spool_id=spool_id,
            amount=Mass(100),
            command_key="opening-reconcile",
            actor_device_id=self.device,
            at=self.now,
        )
        for key, delta in (("negative-reconcile", -200), ("repair-reconcile", 300)):
            inventory.adjust(
                spool_id=spool_id,
                delta=Mass(delta),
                command_key=key,
                actor_device_id=self.device,
                at=self.now,
            )
        material = self._running_material()
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=spool_id,
            material_id=material,
            segment_id=EntityId.new(),
            actor_device_id=self.device,
            command_key="mount-unaccounted",
            at=self.now,
        )
        args = dict(
            spool_id=spool_id,
            expected_revision=4,
            actor_device_id=self.device,
            command_key="resolve-unaccounted",
            reason="Verified correction",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "inventory.quarantine_unresolved_usage"):
            inventory.resolve_quarantine(**args)
        self.commands.unmount_slot(
            slot_id=self.slots[0],
            expected_mount_id=mounted.id,
            material_id=material,
            actor_device_id=self.device,
            command_key="close-unaccounted",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "inventory.quarantine_unresolved_usage"):
            inventory.resolve_quarantine(**args)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.audit.for_command("resolve-unaccounted"), [])

    def test_unmount_audit_failure_preserves_mount_and_slot_then_retries(self) -> None:
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-before-failure",
            at=self.now,
        )
        with SQLiteUnitOfWork(self.engine) as work:
            slot = work.slots.get(self.slots[0])
        arguments = dict(
            slot_id=self.slots[0],
            expected_mount_id=mounted.id,
            actor_device_id=self.device,
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "audit.field_invalid"):
            self.commands.unmount_slot(**arguments, command_key="")
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), mounted)
            self.assertEqual(work.slots.get(self.slots[0]), slot)
            self.assertEqual(work.audit.for_command(""), [])
        closed = self.commands.unmount_slot(**arguments, command_key="retry-unmount")
        self.assertEqual(closed.state, MountState.CLOSED)
        self.assertEqual(
            self.commands.unmount_slot(**arguments, command_key="retry-unmount"), closed
        )

    def test_delayed_unmount_replay_does_not_remove_a_new_spool(self) -> None:
        first = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-first",
            at=self.now,
        )
        args = dict(
            slot_id=self.slots[0],
            expected_mount_id=first.id,
            actor_device_id=self.device,
            command_key="unmount-first",
            at=self.now,
        )
        closed = self.commands.unmount_slot(**args)
        second = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="mount-second",
            at=self.now,
        )
        restarted = TopologyCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.assertEqual(restarted.unmount_slot(**args), closed)
        for changes in (
            {"actor_device_id": EntityId.new()},
            {"material_id": EntityId.new()},
            {"command_key": "new-unmount"},
            {"expected_mount_id": second.id},
            {"slot_id": self.slots[1]},
        ):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                restarted.unmount_slot(**(args | changes))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), second)
            self.assertEqual(len(work.audit.for_command("unmount-first")), 1)

    def test_stale_swap_cannot_replace_an_unexpected_mount(self) -> None:
        first = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount-first",
            at=self.now,
        )
        second = self.commands.swap_spool(
            expected_mount_id=first.id,
            new_mount_id=EntityId.new(),
            slot_id=self.slots[0],
            new_spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="swap-second",
            at=self.now,
        )
        with self.assertRaises(RevisionConflict):
            self.commands.swap_spool(
                expected_mount_id=first.id,
                new_mount_id=EntityId.new(),
                slot_id=self.slots[0],
                new_spool_id=self.spools[0],
                actor_device_id=self.device,
                command_key="stale-swap",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), second)

    def test_stale_unknown_command_preserves_a_new_assignment(self) -> None:
        unknown = self.commands.mark_assignment_unknown(
            slot_id=self.slots[0],
            expected_slot_revision=1,
            actor_device_id=self.device,
            command_key="unknown",
            at=self.now,
        )
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaises(RevisionConflict):
            self.commands.mark_assignment_unknown(
                slot_id=self.slots[0],
                expected_slot_revision=1,
                actor_device_id=self.device,
                command_key="new-stale-unknown",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.active_for_slot(self.slots[0]), mounted)
            self.assertEqual(work.slots.get(self.slots[0]).revision, unknown.revision + 1)

    def test_concurrent_mounts_cannot_assign_one_spool_to_two_slots(self) -> None:
        other_printer, other_system = EntityId.new(), EntityId.new()
        common = dict(
            device_id=self.device,
            created_at=self.now,
            updated_at=self.now,
            revision=1,
        )
        with self.engine.begin() as connection:
            connection.execute(
                insert(printer).values(
                    **common,
                    id=other_printer,
                    name="Second printer",
                    enabled=True,
                )
            )
            connection.execute(
                insert(material_feed_system).values(
                    **common,
                    id=other_system,
                    printer_id=other_printer,
                    provider_system_key="external",
                    kind="EXTERNAL",
                    name="External",
                )
            )
            connection.execute(
                update(feed_slot)
                .where(feed_slot.c.id == self.slots[1])
                .values(
                    feed_system_id=other_system,
                )
            )
        barrier = Barrier(2)

        def mount(index: int) -> str:
            barrier.wait(timeout=5)
            try:
                self.commands.mount_spool(
                    mount_id=EntityId.new(),
                    slot_id=self.slots[index],
                    spool_id=self.spools[0],
                    actor_device_id=self.device,
                    command_key=f"race-{index}",
                    at=self.now,
                )
            except ValueError as error:
                if str(error) != "spool_mount.spool_already_mounted":
                    raise
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(mount, range(2)))
        self.assertCountEqual(results, ["accepted", "rejected"])
        with self.engine.connect() as connection:
            mounts = (
                connection.execute(
                    select(spool_mount).where(
                        spool_mount.c.state == "ACTIVE",
                    )
                )
                .mappings()
                .all()
            )
            slots = connection.execute(select(feed_slot.c.assignment_state)).scalars().all()
            rejected = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.event_code == "spool.mount_rejected.spool_already_mounted",
                    )
                )
                .mappings()
                .all()
            )
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]["spool_id"], self.spools[0])
        self.assertCountEqual(slots, ["ASSIGNED", "EMPTY"])
        self.assertEqual(len(rejected), 1)
        self.assertIn(rejected[0]["correlation_id"], {"race-0", "race-1"})

    def test_concurrent_mounts_cannot_assign_two_spools_to_one_slot(self) -> None:
        barrier = Barrier(2)

        def mount(index: int) -> str:
            barrier.wait(timeout=5)
            try:
                self.commands.mount_spool(
                    mount_id=EntityId.new(),
                    slot_id=self.slots[0],
                    spool_id=self.spools[index],
                    actor_device_id=self.device,
                    command_key=f"slot-race-{index}",
                    at=self.now,
                )
            except ValueError as error:
                if str(error) != "spool_mount.slot_occupied":
                    raise
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(mount, range(2)))
        self.assertCountEqual(results, ["accepted", "rejected"])
        with self.engine.connect() as connection:
            mounts = (
                connection.execute(
                    select(spool_mount).where(
                        spool_mount.c.state == "ACTIVE",
                    )
                )
                .mappings()
                .all()
            )
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]["feed_slot_id"], self.slots[0])

    def test_unmount_rejects_identity_belonging_to_another_slot(self) -> None:
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaises(RevisionConflict):
            self.commands.unmount_slot(
                slot_id=self.slots[1],
                expected_mount_id=mounted.id,
                actor_device_id=self.device,
                command_key="wrong-slot-unmount",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)

    def test_rejected_mount_is_audited_without_changing_physical_state(self) -> None:
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        rejected_id = EntityId.new()
        with self.assertRaisesRegex(ValueError, "spool_mount.spool_already_mounted"):
            self.commands.mount_spool(
                mount_id=rejected_id,
                slot_id=self.slots[1],
                spool_id=self.spools[0],
                actor_device_id=self.device,
                command_key="rejected-mount",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(work.slots.get(self.slots[1]).assignment_state, SlotAssignment.EMPTY)
        with self.engine.connect() as connection:
            events = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.correlation_id == "rejected-mount",
                    )
                )
                .mappings()
                .all()
            )
            self.assertEqual(len(connection.execute(select(spool_mount)).all()), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_code"], "spool.mount_rejected.spool_already_mounted")
        self.assertEqual(events[0]["entity_id"], str(rejected_id))
        self.assertEqual(events[0]["actor_device_id"], self.device)

    def test_rejected_swap_is_audited_and_preserves_both_mounts(self) -> None:
        first = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="first",
            at=self.now,
        )
        second = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[1],
            spool_id=self.spools[1],
            actor_device_id=self.device,
            command_key="second",
            at=self.now,
        )
        with self.assertRaisesRegex(ValueError, "spool_mount.spool_already_mounted"):
            self.commands.swap_spool(
                expected_mount_id=first.id,
                new_mount_id=EntityId.new(),
                slot_id=self.slots[0],
                new_spool_id=self.spools[1],
                actor_device_id=self.device,
                command_key="rejected-swap",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(first.id), first)
            self.assertEqual(work.mounts.get(second.id), second)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    select(audit_event.c.event_code).where(
                        audit_event.c.correlation_id == "rejected-swap",
                    )
                ).scalar_one(),
                "spool.mount_rejected.spool_already_mounted",
            )

    def test_rejection_audit_failure_is_not_reported_as_an_audited_conflict(self) -> None:
        mounted = self.commands.mount_spool(
            mount_id=EntityId.new(),
            slot_id=self.slots[0],
            spool_id=self.spools[0],
            actor_device_id=self.device,
            command_key="mount",
            at=self.now,
        )
        with self.assertRaises(PersistenceError):
            self.commands.mount_spool(
                mount_id=EntityId.new(),
                slot_id=self.slots[1],
                spool_id=self.spools[0],
                actor_device_id=EntityId.new(),
                command_key="audit-fails",
                at=self.now,
            )
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.mounts.get(mounted.id), mounted)
            self.assertEqual(work.slots.get(self.slots[1]).assignment_state, SlotAssignment.EMPTY)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.correlation_id == "audit-fails",
                    )
                ).all(),
                [],
            )
