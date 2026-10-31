"""Financial edge cases using real SQLite and the canonical calculator boundary."""

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from unittest.mock import AsyncMock, patch

from sqlalchemy import insert, select, update

from tests.integration import test_calculated_finalization as fixtures
from tests.integration.test_print_finalization import BASE, END, START, create_scope
from ufm.application.calculated_finalization import (
    CalculatedFinalizationCommands,
    EstimatedUsagePolicy,
    estimate_provenance,
)
from ufm.application.finalization import FinalizationRejected
from ufm.application.inventory import InventoryCommands
from ufm.domain.entities import AuditEvent, FilamentTransaction
from ufm.domain.enums import ReservationState, TransactionType
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime
from ufm.infrastructure.persistence.models import accounting as a
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.haspel_calculation import PARTIAL_POLICY, HaspelCalculator
from ufm.integrations.sliced_files import inspect_3mf_file

MID = UtcDateTime.parse("2026-10-26T12:15:00.000000Z")


class CalculatedBatchEdges(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f = fixtures.CalculatedFinalizationTests()
        self.f.setUp()
        self.addCleanup(self.f.temp.cleanup)
        self.addCleanup(self.f.engine.dispose)
        self.evidence_ids = (self.f.ids["evidence"],)

    def commands(self, **flags):
        f = self.f
        return CalculatedFinalizationCommands(
            lambda: SQLiteUnitOfWork(f.engine),
            f.calculator,
            EstimatedUsagePolicy(enabled=True, allow_unknown_purge=True, **flags),
            file_reader=inspect_3mf_file,
        )

    async def finalize(self, **flags):
        return await self.f.finalize(
            commands=self.commands(**flags), evidence_ids=self.evidence_ids
        )

    def reserve(self, amount, *, foreign=False):
        f = self.f
        material = (
            create_scope(f.engine, with_evidence=False)["material"]
            if foreign
            else f.ids["material"]
        )
        identity = EntityId.new()
        with f.engine.begin() as connection:
            connection.execute(
                insert(a.reservation).values(
                    id=identity,
                    device_id=f.ids["device"],
                    created_at=BASE,
                    updated_at=BASE,
                    revision=1,
                    spool_id=f.ids["spool"],
                    print_job_material_id=material,
                    reserved_mg=Mass(amount),
                    status="ACTIVE",
                    activated_at=START,
                )
            )
        return identity

    def append_evidence(
        self, *, segment, mass, start=START, end=END, layer=None, logical=0, material=None
    ):
        f = self.f
        identity = EntityId.new()
        with SQLiteUnitOfWork(f.engine) as work:
            original = work.evidence.get_consumption(f.ids["evidence"])
            work.evidence.add_consumption(
                replace(
                    original,
                    id=identity,
                    segment_id=segment,
                    mass=Mass(mass),
                    print_job_material_id=material or f.ids["material"],
                    interval_start=start,
                    interval_end=end,
                    scope_key=f"segment:{segment}",
                    confidence_bp=8000 if layer is None else 6000,
                    metadata_json=estimate_provenance(
                        f.facts,
                        f.proposal,
                        logical_material=logical,
                        allocation_mg=mass,
                        completed_layer=layer,
                    ),
                )
            )
            work.commit()
        return identity

    def split(self, *, second_spool=False, audit=True):
        f = self.f
        second = EntityId.new()
        spool, mount, slot = (f.ids[key] for key in ("spool", "mount", "slot"))
        if second_spool:
            spool, mount, slot = EntityId.new(), EntityId.new(), EntityId.new()
            inventory = InventoryCommands(lambda: SQLiteUnitOfWork(f.engine))
            inventory.create_spool(
                spool_id=spool,
                filament_profile_id=f.ids["profile"],
                display_name="Second spool",
                actor_device_id=f.ids["device"],
                command_key="second-spool",
                at=BASE,
            )
            inventory.establish_opening_stock(
                spool_id=spool,
                amount=Mass(100000),
                actor_device_id=f.ids["device"],
                command_key="second-opening",
                at=BASE,
            )
            common = dict(device_id=f.ids["device"], created_at=BASE, updated_at=BASE, revision=1)
            with f.engine.begin() as connection:
                connection.execute(
                    insert(s.feed_slot).values(
                        **common,
                        id=slot,
                        feed_system_id=f.ids["system"],
                        slot_key="second",
                        assignment_state="ASSIGNED",
                        tool_index=0,
                    )
                )
                connection.execute(
                    insert(s.spool_mount).values(
                        **common,
                        id=mount,
                        feed_slot_id=slot,
                        spool_id=spool,
                        state="ACTIVE",
                        mounted_at=BASE,
                        assignment_source="MANUAL",
                        confidence_bp=10000,
                    )
                )
        with f.engine.begin() as connection:
            original = dict(
                connection.execute(
                    select(s.material_usage_segment).where(
                        s.material_usage_segment.c.id == f.ids["segment"]
                    )
                )
                .mappings()
                .one()
            )
            connection.execute(
                update(s.material_usage_segment)
                .where(s.material_usage_segment.c.id == f.ids["segment"])
                .values(
                    ended_at=MID, source="MANUAL_CONFIRMED_SPLIT", estimated_usage_mg=Mass(4000)
                )
            )
            original.update(
                id=second,
                started_at=MID,
                spool_id=spool,
                spool_mount_id=mount,
                feed_slot_id=slot,
                source="MANUAL_CONFIRMED_SPLIT",
                estimated_usage_mg=Mass(8345),
            )
            connection.execute(insert(s.material_usage_segment).values(**original))
        self.evidence_ids = (
            self.append_evidence(segment=f.ids["segment"], mass=4000, end=MID),
            self.append_evidence(segment=second, mass=8345, start=MID),
        )
        if audit:
            with SQLiteUnitOfWork(f.engine) as work:
                for segment, mass in ((f.ids["segment"], 4000), (second, 8345)):
                    work.audit.append(
                        AuditEvent(
                            id=EntityId.new(),
                            device_id=f.ids["device"],
                            created_at=END,
                            event_code="print.allocation.confirmed",
                            actor_device_id=f.ids["device"],
                            correlation_id=f"segment:{segment}:allocation",
                            entity_type="material_usage_segment",
                            entity_id=segment,
                            parameters_json=json.dumps(
                                {"allocation_mg": mass, "file_sha256": f.facts.file_sha256}
                            ),
                        )
                    )
                work.commit()
        return spool

    async def test_same_spool_split_has_sequential_balances_and_one_settlement(self):
        f = self.f
        claim = self.reserve(20000)
        self.split()
        result = await self.finalize(allow_manual_splits=True)
        with SQLiteUnitOfWork(f.engine) as work:
            entries = sorted(
                work.ledger.for_command(result.idempotency_key), key=lambda row: row.sequence
            )
            self.assertEqual([row.sequence for row in entries], [2, 3])
            self.assertEqual(entries[0].new_effective, entries[1].previous_effective)
            self.assertEqual(work.spools.get(f.ids["spool"]).effective_remaining, Mass(987655))
            settled = work.reservations.get(claim)
            self.assertEqual(
                (settled.allocated_consumption, settled.released), (Mass(12345), Mass(7655))
            )
            self.assertEqual(len(work.reservations.for_finalization(result.id)), 1)

    async def test_two_spools_commit_together(self):
        f = self.f
        second = self.split(second_spool=True)
        result = await self.finalize(allow_manual_splits=True)
        with SQLiteUnitOfWork(f.engine) as work:
            self.assertEqual(work.spools.get(f.ids["spool"]).effective_remaining, Mass(996000))
            self.assertEqual(work.spools.get(second).effective_remaining, Mass(91655))
            self.assertEqual(len(work.decisions.for_finalization(result.id)), 2)

    async def test_second_spool_shortage_rejects_whole_batch(self):
        f = self.f
        second = self.split(second_spool=True)
        InventoryCommands(lambda: SQLiteUnitOfWork(f.engine)).deduct_manual(
            spool_id=second,
            amount=Mass(99000),
            command_key="prior-use",
            actor_device_id=f.ids["device"],
            at=BASE,
        )
        before = f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "insufficient_available_stock"):
            await self.finalize(allow_manual_splits=True)
        self.assertEqual(f.snapshot(), before)

    async def test_split_without_confirmation_cannot_write(self):
        self.split(audit=False)
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "split_unverified"):
            await self.finalize(allow_manual_splits=True)
        self.assertEqual(self.f.snapshot(), before)

    async def test_foreign_reserved_capacity_cannot_be_spent(self):
        self.reserve(995000, foreign=True)
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "insufficient_available_stock"):
            await self.finalize()
        self.assertEqual(self.f.snapshot(), before)

    async def test_receipt_conflict_blocks_new_calculated_debit(self):
        from tests.integration.test_receipt_ingestion import create_receipt_conflict

        create_receipt_conflict(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "receipt_conflict"):
            await self.finalize()
        self.assertEqual(self.f.snapshot(), before)

    async def test_different_receipt_lifecycle_conflict_blocks_calculated_debit(self):
        from tests.integration.test_receipt_ingestion import create_lifecycle_conflict

        create_lifecycle_conflict(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "lifecycle_conflict"):
            await self.finalize()
        self.assertEqual(self.f.snapshot(), before)

    async def test_quarantined_terminal_cannot_authorize_calculated_debit(self):
        from tests.integration.test_receipt_ingestion import quarantine_receipt

        quarantine_receipt(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "projection_quarantined"):
            await self.finalize()
        self.assertEqual(self.f.snapshot(), before)

    async def test_different_receipt_run_quarantine_blocks_calculated_debit(self):
        from tests.integration.test_receipt_ingestion import create_run_quarantine

        create_run_quarantine(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "projection_run_quarantined"):
            await self.finalize()
        self.assertEqual(self.f.snapshot(), before)

    async def test_run_quarantine_after_calculated_finalization_preserves_replay(self):
        from tests.integration.test_receipt_ingestion import create_run_quarantine

        result = await self.finalize()
        create_run_quarantine(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        self.assertEqual(await self.finalize(), result)
        self.assertEqual(self.f.snapshot(), before)

    async def test_lifecycle_conflict_after_commit_preserves_calculated_replay(self):
        from tests.integration.test_receipt_ingestion import create_lifecycle_conflict

        result = await self.finalize()
        create_lifecycle_conflict(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        self.assertEqual(await self.finalize(), result)
        self.assertEqual(self.f.snapshot(), before)

    async def test_conflict_after_commit_does_not_break_safe_replay(self):
        from tests.integration.test_receipt_ingestion import create_receipt_conflict

        result = await self.finalize()
        create_receipt_conflict(self.f.engine, self.f.ids)
        before = self.f.snapshot()
        self.assertEqual(await self.finalize(), result)
        self.assertEqual(self.f.snapshot(), before)

    async def test_weighing_after_start_requires_reconciliation(self):
        f = self.f
        with SQLiteUnitOfWork(f.engine) as work:
            spool = work.spools.get(f.ids["spool"])
            entry = FilamentTransaction(
                id=EntityId.new(),
                device_id=f.ids["device"],
                created_at=END,
                spool_id=spool.id,
                sequence=2,
                transaction_type=TransactionType.MEASUREMENT_CORRECTION,
                delta=Mass(-10000),
                previous_effective=spool.effective_remaining,
                new_effective=Mass(990000),
                previous_estimated=spool.estimated_remaining,
                new_estimated=Mass(990000),
                command_key="weighing",
                command_item=0,
                source_type="SCALE",
                confidence_bp=10000,
            )
            work.ledger.append(entry)
            work.spools.save(
                replace(
                    spool,
                    effective_remaining=entry.new_effective,
                    estimated_remaining=entry.new_estimated,
                    ledger_sequence=2,
                    revision=spool.revision + 1,
                    updated_at=END,
                ),
                spool.revision,
            )
            work.commit()
        before = f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "measurement_overlap"):
            await self.finalize()
        self.assertEqual(f.snapshot(), before)

    async def test_missing_segment_evidence_cannot_finalize_partial_batch(self):
        self.split(second_spool=True)
        self.evidence_ids = self.evidence_ids[:1]
        before = self.f.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "complete_evidence_required"):
            await self.finalize(allow_manual_splits=True)
        self.assertEqual(self.f.snapshot(), before)

    def partial(self, *, zero=False):
        f = self.f
        with zipfile.ZipFile(f.path, "w") as archive:
            archive.writestr(
                "Metadata/slice_info.config",
                '<config><plate><metadata key="index" value="1"/><filament id="1" used_g="12.345"/><layer_filament_lists><layer_filament_list><layer_range start="0" end="9"/><filament id="1" used_g="12.345"/></layer_filament_list></layer_filament_lists></plate></config>',
            )
            archive.writestr("Metadata/plate_1.gcode", "M83\nT0\nG1 E1\n")
        f.facts = inspect_3mf_file(
            f.path, plate=1, expected_sha256=hashlib.sha256(f.path.read_bytes()).hexdigest()
        )
        mass, layer = (0, -1) if zero else (6170, 4)
        f.proposal = f.proposal.model_copy(
            update={
                "file_sha256": f.facts.file_sha256,
                "partial": True,
                "policy_version": PARTIAL_POLICY,
                "materials": (fixtures.MaterialEstimate(logical_material=0, mass_mg=mass),),
            }
        )
        status, stamp = ("CANCELLED", "cancelled_at") if zero else ("FAILED", "failed_at")
        with f.engine.begin() as connection:
            connection.execute(
                update(s.print_job)
                .where(s.print_job.c.id == f.ids["job"])
                .values(
                    file_hash=f.facts.file_sha256,
                    status=status,
                    completed_at=None,
                    **{stamp: END},
                    current_layer=1 if zero else 6,
                    total_layers=10,
                )
            )
            connection.execute(
                update(s.external_event_receipt)
                .where(s.external_event_receipt.c.id == f.ids["receipt"])
                .values(event_type=f"PRINT_{status}")
            )
        self.evidence_ids = (
            self.append_evidence(segment=f.ids["segment"], mass=mass, layer=layer),
        )

    async def test_failed_partial_preserves_estimate_label_and_failed_print_type(self):
        self.partial()
        result = await self.finalize(allow_range_partial=True)
        with SQLiteUnitOfWork(self.f.engine) as work:
            (entry,) = work.ledger.for_command(result.idempotency_key)
            self.assertEqual(
                (entry.transaction_type, entry.delta, entry.description),
                (TransactionType.FAILED_PRINT, Mass(-6170), fixtures.LABEL),
            )

    async def test_zero_cancel_releases_reservation_without_zero_ledger(self):
        claim = self.reserve(20000)
        self.partial(zero=True)
        result = await self.finalize(allow_range_partial=True)
        with SQLiteUnitOfWork(self.f.engine) as work:
            self.assertEqual(work.ledger.for_command(result.idempotency_key), [])
            settled = work.reservations.get(claim)
            self.assertEqual(
                (settled.state, settled.released), (ReservationState.RELEASED, Mass(20000))
            )
            self.assertEqual(len(work.decisions.for_finalization(result.id)), 1)

    async def test_concurrent_terminal_deliveries_have_one_result(self):
        f = self.f

        async def calculation(*args, **kwargs):
            await asyncio.sleep(0)
            return f.proposal

        with patch.object(HaspelCalculator, "calculate", AsyncMock(side_effect=calculation)):
            first, second = await asyncio.gather(
                self.commands().finalize(**f.parameters()),
                self.commands().finalize(**f.parameters()),
            )
        self.assertEqual(first, second)
        with SQLiteUnitOfWork(f.engine) as work:
            self.assertEqual(len(work.ledger.for_job(f.ids["job"])), 1)

    async def test_two_threads_serialize_into_one_finalization(self):
        f = self.f
        barrier = Barrier(2)

        async def calculate(*args, **kwargs):
            await asyncio.to_thread(barrier.wait, 10)
            return f.proposal

        def execute(_):
            return asyncio.run(self.commands().finalize(**f.parameters()))

        with patch.object(HaspelCalculator, "calculate", AsyncMock(side_effect=calculate)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = await asyncio.to_thread(lambda: list(pool.map(execute, range(2))))
        self.assertEqual(results[0], results[1])
        with SQLiteUnitOfWork(f.engine) as work:
            self.assertEqual(len(work.ledger.for_job(f.ids["job"])), 1)

    @unittest.skipUnless(shutil.which("node"), "Node developer runtime unavailable")
    async def test_process_crash_before_and_after_commit_is_recoverable(self):
        f = self.f
        script = """
import asyncio,os,shutil,sys
from pathlib import Path
from ufm.application.calculated_finalization import CalculatedFinalizationCommands,EstimatedUsagePolicy
from ufm.domain.value_objects import EntityId,UtcDateTime
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.calculation_worker import CalculationWorkerTransport
from ufm.integrations.haspel_calculation import HaspelCalculator
from ufm.integrations.sliced_files import inspect_3mf_file
database,boundary,file,entry,*values=sys.argv[1:]
engine=create_sqlite_engine(Path(database))
original=SQLiteUnitOfWork.commit
def crash(work):
    if boundary=="after": original(work)
    os._exit(39)
SQLiteUnitOfWork.commit=crash
ids=[EntityId.parse(value) for value in values]
calculator=HaspelCalculator(CalculationWorkerTransport(Path(shutil.which("node")).resolve(),Path(entry),Path(file).parent,5))
commands=CalculatedFinalizationCommands(lambda:SQLiteUnitOfWork(engine),calculator,
    EstimatedUsagePolicy(enabled=True,allow_unknown_purge=True),file_reader=inspect_3mf_file)
asyncio.run(commands.finalize(job_id=ids[0],evidence_ids=(ids[1],),receipt_id=ids[2],
    actor_device_id=ids[3],command_key="calculated-run-1",plate=1,file_path=Path(file),
    at=UtcDateTime.parse("2026-10-26T12:31:00.000000Z")))
"""
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                before = f.snapshot()
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(Path(f.temp.name) / "fixture.sqlite3"),
                        boundary,
                        str(f.path),
                        str(
                            Path(__file__).resolve().parents[2]
                            / "src/ufm/integrations/haspel_worker.mjs"
                        ),
                        *(str(f.ids[key]) for key in ("job", "evidence", "receipt", "device")),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 39, result.stderr)
                if boundary == "before":
                    self.assertEqual(f.snapshot(), before)
                else:
                    committed = f.snapshot()
                    await self.finalize()
                    self.assertEqual(f.snapshot(), committed)

    async def test_two_logical_materials_keep_separate_decisions(self):
        f = self.f
        second_spool = self.split(second_spool=True, audit=False)
        with f.engine.connect() as connection:
            second_segment = (
                connection.execute(
                    select(s.material_usage_segment).where(
                        s.material_usage_segment.c.spool_id == second_spool
                    )
                )
                .mappings()
                .one()
            )
        material = EntityId.new()
        with zipfile.ZipFile(f.path, "w") as archive:
            archive.writestr(
                "Metadata/slice_info.config",
                '<config><plate><metadata key="index" value="1"/><filament id="1" used_g="12.345" color="#FFFFFF"/><filament id="2" used_g="20" color="#FFFFFF"/></plate></config>',
            )
            archive.writestr("Metadata/plate_1.gcode", "M83\nT0\nG1 E1\nT1\nG1 E2\n")
        f.facts = inspect_3mf_file(
            f.path, plate=1, expected_sha256=hashlib.sha256(f.path.read_bytes()).hexdigest()
        )
        f.proposal = f.proposal.model_copy(
            update={
                "file_sha256": f.facts.file_sha256,
                "materials": (
                    fixtures.MaterialEstimate(logical_material=0, mass_mg=12345),
                    fixtures.MaterialEstimate(logical_material=1, mass_mg=20000),
                ),
            }
        )
        with f.engine.begin() as connection:
            connection.execute(
                update(s.print_job)
                .where(s.print_job.c.id == f.ids["job"])
                .values(file_hash=f.facts.file_sha256)
            )
            connection.execute(
                update(s.print_job_material)
                .where(
                    s.print_job_material.c.id == f.ids["material"],
                )
                .values(logical_material_index=0)
            )
            connection.execute(
                insert(s.print_job_material).values(
                    id=material,
                    device_id=f.ids["device"],
                    created_at=BASE,
                    updated_at=BASE,
                    revision=1,
                    print_job_id=f.ids["job"],
                    channel_key="tool-1",
                    tool_index=1,
                    logical_material_index=1,
                )
            )
            connection.execute(
                update(s.material_usage_segment)
                .where(s.material_usage_segment.c.id == second_segment["id"])
                .values(print_job_material_id=material, tool_index=1)
            )
            connection.execute(
                update(s.material_usage_segment)
                .where(s.material_usage_segment.c.id.in_((f.ids["segment"], second_segment["id"])))
                .values(started_at=START, ended_at=END, source="PRINTER", estimated_usage_mg=None)
            )
            connection.execute(
                update(s.feed_slot)
                .where(s.feed_slot.c.id == second_segment["feed_slot_id"])
                .values(tool_index=1)
            )
        self.evidence_ids = (
            self.append_evidence(segment=f.ids["segment"], mass=12345),
            self.append_evidence(
                segment=second_segment["id"], mass=20000, logical=1, material=material
            ),
        )
        result = await self.finalize()
        with SQLiteUnitOfWork(f.engine) as work:
            self.assertEqual(len(work.decisions.for_finalization(result.id)), 2)
            self.assertEqual(work.spools.get(f.ids["spool"]).effective_remaining, Mass(987655))
            self.assertEqual(work.spools.get(second_spool).effective_remaining, Mass(80000))
