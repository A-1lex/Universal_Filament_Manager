"""Atomic acceptance tests for explicitly enabled verified-3MF estimates."""

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError

from tests.integration.test_print_finalization import (
    AT,
    END,
    START,
    create_scope,
    snapshot_database,
)
from ufm.application.accounting_authority import PrinterAccountingAuthorityCommands
from ufm.application.calculated_finalization import (
    LABEL,
    POLICY_VERSION,
    CalculatedFinalizationCommands,
    EstimatedUsagePolicy,
    estimate_provenance,
)
from ufm.application.dto.worker_protocol import MaterialEstimate, ProposalMessage
from ufm.application.finalization import FinalizationRejected
from ufm.application.inventory import InventoryCommands
from ufm.application.ports.persistence import IdempotencyConflict
from ufm.domain.enums import FinalizationState, PrinterAccountingMode, ReceiptState
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass
from ufm.infrastructure.persistence.models import accounting as a
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.repositories.entities import Audit
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.calculation_worker import CalculationWorkerTransport
from ufm.integrations.haspel_calculation import FULL_POLICY, HaspelCalculator
from ufm.integrations.sliced_files import inspect_3mf_file


class CalculatedFinalizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ufm-calculated-finalization-")
        self.addCleanup(self.temp.cleanup)
        self.engine = create_sqlite_engine(Path(self.temp.name) / "fixture.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine, with_evidence=False)
        self.path = Path(self.temp.name) / "fixture.3mf"
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("Metadata/slice_info.config", '<config><plate><metadata key="index" value="1"/><filament id="1" used_g="12.345"/></plate></config>')
            archive.writestr("Metadata/plate_1.gcode", "M83\nT0\nG1 E1\n")
        self.facts = inspect_3mf_file(self.path, plate=1,
            expected_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.proposal = ProposalMessage(
            v=1, kind="proposal", request_id="fixture", printer_id=self.ids["printer"].value,
            source_epoch="epoch-1", sequence=0, observed_at=AT.value,
            occurrence_key="run-1", file_sha256=self.facts.file_sha256,
            evidence_id=self.ids["evidence"].value, policy_version=FULL_POLICY,
            quantity="estimate", label=LABEL, confidence_bp=0, status="needs_mapping",
            partial=False, materials=(MaterialEstimate(logical_material=0, mass_mg=12345),), allocations=(),
        )
        with self.engine.begin() as connection:
            connection.execute(update(s.print_job).where(s.print_job.c.id == self.ids["job"]).values(
                file_hash=self.facts.file_sha256, plate_name="1"))
            connection.execute(insert(a.consumption_evidence).values(
                id=self.ids["evidence"], device_id=self.ids["device"], created_at=END,
                print_job_material_id=self.ids["material"], segment_id=self.ids["segment"],
                source_type="THREE_MF", quantity_kind="CONSUMED_MASS", mode="ESTIMATE", weight_mg=Mass(12345),
                confidence_bp=8000, includes_purge=self.facts.includes_purge,
                captured_at=END, received_at=END, interval_start=START, interval_end=END,
                scope_key=f"segment:{self.ids['segment']}", source_receipt_id=self.ids["receipt"],
                external_reference="run-1", metadata_json=estimate_provenance(
                    self.facts, self.proposal, logical_material=0, allocation_mg=12345, completed_layer=None)))
        node = shutil.which("node")
        self.calculator = HaspelCalculator(CalculationWorkerTransport(
            Path(node).resolve() if node else Path("missing-node"),
            Path(__file__).resolve().parents[2] / "src/ufm/integrations/haspel_worker.mjs",
            Path(self.temp.name).resolve(), 5))

    def commands(self, *, enabled=True):
        return CalculatedFinalizationCommands(lambda: SQLiteUnitOfWork(self.engine), self.calculator,
            file_reader=inspect_3mf_file,
            policy=EstimatedUsagePolicy(enabled=enabled, allow_unknown_purge=True))

    def parameters(self, **overrides):
        return {"job_id": self.ids["job"], "evidence_ids": (self.ids["evidence"],),
                "receipt_id": self.ids["receipt"], "actor_device_id": self.ids["device"],
                "command_key": "calculated-run-1", "plate": 1, "file_path": self.path, "at": AT} | overrides

    async def finalize(self, *, commands=None, **overrides):
        with patch.object(HaspelCalculator, "calculate", AsyncMock(return_value=self.proposal)):
            return await (commands or self.commands()).finalize(**self.parameters(**overrides))

    def snapshot(self):
        return snapshot_database(self.engine)

    async def test_success_stores_estimate_provenance_and_proof_links(self):
        record = await self.finalize()
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.ids["spool"]).effective_remaining, Mass(987655))
            self.assertEqual(work.jobs.get(self.ids["job"]).finalization_state, FinalizationState.FINALIZED)
            self.assertEqual(work.receipts.get(self.ids["receipt"]).state, ReceiptState.PROCESSED)
            entries = work.ledger.for_command(record.idempotency_key)
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual((entry.description, entry.source_type, entry.estimate_policy_version),
                             (LABEL, "THREE_MF", POLICY_VERSION))
            self.assertEqual(json.loads(entry.metadata_json)["quantity"], "estimate")
            self.assertEqual(work.decisions.for_finalization(record.id)[0].strategy, "verified_3mf_estimate")
            self.assertEqual(work.decisions.evidence_links_for_finalization(record.id)[0].role, "SELECTED_ESTIMATE")

    async def test_verified_3mf_estimate_cost_is_snapshotted_without_losing_provenance(self):
        with self.engine.begin() as connection:
            connection.execute(update(s.spool).where(s.spool.c.id == self.ids["spool"]).values(
                purchase_price=ExactDecimal.parse("18.25"), purchase_basis_mg=Mass(1_000_000),
                currency="EUR", purchase_date="2026-10-01",
            ))
        record = await self.finalize()
        with SQLiteUnitOfWork(self.engine) as work:
            entry = work.ledger.for_command(record.idempotency_key)[0]
            metadata = json.loads(entry.metadata_json)
            self.assertEqual((entry.unit_cost, entry.currency), (ExactDecimal.parse("0.23"), "EUR"))
            self.assertEqual(metadata["quantity"], "estimate")
            self.assertEqual(metadata["cost_snapshot_v1"]["consumed_mg"], 12345)

    async def test_replay_after_manual_use_missing_file_and_disabled_policy(self):
        record = await self.finalize()
        InventoryCommands(lambda: SQLiteUnitOfWork(self.engine)).deduct_manual(
            spool_id=self.ids["spool"], amount=Mass(1000), command_key="later-use",
            actor_device_id=self.ids["device"], at=AT)
        self.path.unlink()
        before = self.snapshot()
        self.assertEqual(await self.finalize(commands=self.commands(enabled=False), file_path=None), record)
        self.assertEqual(self.snapshot(), before)

    async def test_changed_actor_key_or_provenance_conflicts_without_writes(self):
        await self.finalize()
        for override in ({"actor_device_id": EntityId.new()}, {"command_key": "other"}):
            with self.subTest(override=override):
                before = self.snapshot()
                with self.assertRaises(IdempotencyConflict):
                    await self.finalize(**override)
                self.assertEqual(self.snapshot(), before)
        before = self.snapshot()
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(update(a.consumption_evidence).where(
                a.consumption_evidence.c.id == self.ids["evidence"]).values(metadata_json='{}'))
        self.assertEqual(self.snapshot(), before)
        replacement_id = EntityId.new()
        with SQLiteUnitOfWork(self.engine) as work:
            original = work.evidence.get_consumption(self.ids["evidence"])
            work.evidence.add_consumption(replace(original, id=replacement_id, metadata_json='{}'))
            work.commit()
        before = self.snapshot()
        with self.assertRaises(IdempotencyConflict):
            await self.finalize(evidence_ids=(replacement_id,))
        self.assertEqual(self.snapshot(), before)

    async def test_audit_failure_rolls_back_entire_batch(self):
        before = self.snapshot()
        with patch.object(Audit, "append", side_effect=RuntimeError("injected audit failure")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                await self.finalize()
        self.assertEqual(self.snapshot(), before)
        await self.finalize()

    async def test_default_policy_rejects_without_writes(self):
        commands = CalculatedFinalizationCommands(lambda: SQLiteUnitOfWork(self.engine), self.calculator,
            file_reader=inspect_3mf_file)
        before = self.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "policy_disabled"):
            await self.finalize(commands=commands)
        self.assertEqual(self.snapshot(), before)

    async def test_review_only_accounting_authority_rejects_estimate_without_writes(self):
        authority = PrinterAccountingAuthorityCommands(
            lambda: SQLiteUnitOfWork(self.engine),
        )
        authority.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.REVIEW_ONLY,
            actor_device_id=self.ids["device"],
            command_key="authority-review-only-before-estimate",
            expected_revision=3,
            at=AT,
        )
        before = self.snapshot()

        with self.assertRaisesRegex(
            FinalizationRejected,
            "accounting_authority_required",
        ):
            await self.finalize()

        self.assertEqual(self.snapshot(), before)

    async def test_authority_change_during_estimation_blocks_commit(self):
        authority = PrinterAccountingAuthorityCommands(
            lambda: SQLiteUnitOfWork(self.engine),
        )
        after_review_only = []

        async def switch_to_review_only(*_args, **_kwargs):
            authority.transition(
                printer_id=self.ids["printer"],
                mode=PrinterAccountingMode.REVIEW_ONLY,
                actor_device_id=self.ids["device"],
                command_key="authority-review-only-during-estimate",
                expected_revision=3,
                at=AT,
            )
            after_review_only.append(self.snapshot())
            return self.proposal

        with patch.object(
            HaspelCalculator,
            "calculate",
            AsyncMock(side_effect=switch_to_review_only),
        ):
            with self.assertRaisesRegex(
                FinalizationRejected,
                "accounting_authority_required",
            ):
                await self.commands().finalize(**self.parameters())

        self.assertEqual(len(after_review_only), 1)
        self.assertEqual(self.snapshot(), after_review_only[0])

    async def test_review_preview_is_available_when_auto_policy_is_disabled_and_writes_nothing(self):
        commands = self.commands(enabled=False)
        before = self.snapshot()
        with patch.object(HaspelCalculator, "calculate", AsyncMock(return_value=self.proposal)):
            preview = await commands.preview(
                job_id=self.ids["job"],
                evidence_ids=(self.ids["evidence"],),
                receipt_id=self.ids["receipt"],
                actor_device_id=self.ids["device"],
                plate=1,
                file_path=self.path,
                at=AT,
            )
        self.assertEqual(preview.quantity_label, LABEL)
        self.assertEqual(preview.file_sha256, self.facts.file_sha256)
        self.assertFalse(preview.partial)
        self.assertFalse(preview.automatic_policy_enabled)
        self.assertEqual(
            [(item.logical_material, item.estimated_mass_mg) for item in preview.materials],
            [(0, 12_345)],
        )
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(shutil.which("node"), "Node developer runtime unavailable")
    async def test_real_node_verified_file_finalizes(self):
        record = await self.commands().finalize(**self.parameters())
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.ledger.for_command(record.idempotency_key)[0].delta, Mass(-12345))


if __name__ == "__main__":
    unittest.main()
