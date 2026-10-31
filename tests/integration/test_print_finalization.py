"""Real-file acceptance tests for atomic, restart-safe print debits."""

import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import insert, select, update

from ufm.application.accounting_authority import PrinterAccountingAuthorityCommands
from ufm.application.finalization import FinalizationCommands, FinalizationRejected
from ufm.application.inventory import InventoryCommands
from ufm.application.ports.persistence import IdempotencyConflict
from ufm.domain.entities import FilamentTransaction
from ufm.domain.enums import (
    FinalizationState,
    PrinterAccountingMode,
    ReceiptState,
    ReservationState,
    TransactionType,
)
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.persistence.models import accounting as a
from ufm.infrastructure.persistence.models import ledger as l
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.repositories.entities import Audit
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork

BASE = UtcDateTime.parse("2026-10-26T11:59:00.000000Z")
START = UtcDateTime.parse("2026-10-26T12:00:00.000000Z")
END = UtcDateTime.parse("2026-10-26T12:30:00.000000Z")
AT = UtcDateTime.parse("2026-10-26T12:31:00.000000Z")


def create_scope(engine, *, opening=True, mass=12345, with_evidence=True):
    ids = {key: EntityId.new() for key in (
        "device", "profile", "printer", "system", "slot", "spool", "job", "material",
        "mount", "segment", "alias", "provider", "receipt", "evidence",
    )}

    def mutable(key):
        return dict(id=ids[key], device_id=ids["device"], created_at=BASE,
                    updated_at=BASE, revision=1)

    with engine.begin() as connection:
        connection.execute(insert(s.device_identity).values(
            id=ids["device"], name="Test", public_id=str(ids["device"]), created_at=BASE,
        ))
        connection.execute(insert(s.filament_profile).values(
            **mutable("profile"), name="PLA", material_type="PLA",
            diameter_mm=ExactDecimal.parse("1.75"),
        ))
        connection.execute(insert(s.printer).values(
            **mutable("printer"), name="Fixture printer", enabled=True,
        ))
        connection.execute(insert(s.material_feed_system).values(
            **mutable("system"), printer_id=ids["printer"], kind="EXTERNAL", name="External",
        ))
        connection.execute(insert(s.feed_slot).values(
            **mutable("slot"), feed_system_id=ids["system"], slot_key="external",
            assignment_state="ASSIGNED", tool_index=0,
        ))
    authority = PrinterAccountingAuthorityCommands(lambda: SQLiteUnitOfWork(engine))
    authority.transition(
        printer_id=ids["printer"], mode=PrinterAccountingMode.LEGACY_ACTIVE,
        actor_device_id=ids["device"], command_key=f"authority-legacy:{ids['printer']}",
        expected_revision=0, at=BASE,
    )
    snapshot = "a" * 64
    authority.transition(
        printer_id=ids["printer"], mode=PrinterAccountingMode.CUTOVER_READY,
        actor_device_id=ids["device"], command_key=f"authority-cutover:{ids['printer']}",
        expected_revision=1, snapshot_sha256=snapshot,
        legacy_writer_disabled_at=BASE, reconciled_at=BASE, at=BASE,
    )
    authority.transition(
        printer_id=ids["printer"], mode=PrinterAccountingMode.UFM_ACTIVE,
        actor_device_id=ids["device"], command_key=f"authority-active:{ids['printer']}",
        expected_revision=2, snapshot_sha256=snapshot,
        legacy_writer_disabled_at=BASE, reconciled_at=BASE, at=BASE,
    )
    commands = InventoryCommands(lambda: SQLiteUnitOfWork(engine))
    commands.create_spool(
        spool_id=ids["spool"], filament_profile_id=ids["profile"], display_name="Fixture spool",
        actor_device_id=ids["device"], command_key=f"create:{ids['spool']}", at=BASE,
    )
    if opening:
        commands.establish_opening_stock(
            spool_id=ids["spool"], amount=Mass(1_000_000), actor_device_id=ids["device"],
            command_key=f"opening:{ids['spool']}", at=BASE,
        )
    with engine.begin() as connection:
        connection.execute(insert(s.print_job).values(
            **mutable("job"), printer_id=ids["printer"], source_type="PRINTER",
            status="COMPLETED", finalization_state="NOT_STARTED", detected_at=START,
            started_at=START, completed_at=END,
        ))
        connection.execute(insert(s.print_job_material).values(
            **mutable("material"), print_job_id=ids["job"], channel_key="tool-0", tool_index=0,
        ))
        connection.execute(insert(s.spool_mount).values(
            **mutable("mount"), feed_slot_id=ids["slot"], spool_id=ids["spool"], state="ACTIVE",
            mounted_at=BASE, assignment_source="MANUAL", confidence_bp=10000,
        ))
        connection.execute(insert(s.material_usage_segment).values(
            **mutable("segment"), print_job_material_id=ids["material"],
            feed_slot_id=ids["slot"], spool_mount_id=ids["mount"], spool_id=ids["spool"],
            tool_index=0, assignment_state="ASSIGNED", started_at=START, ended_at=END,
            source="PRINTER", confidence_bp=10000,
        ))
        connection.execute(insert(s.job_identity_alias).values(
            id=ids["alias"], device_id=ids["device"], created_at=END,
            print_job_id=ids["job"], provider=ids["provider"], printer_id=ids["printer"],
            source_type="PRINTER", source_epoch="epoch-1", occurrence_key="run-1",
            started_at=START,
        ))
        connection.execute(insert(s.external_event_receipt).values(
            **mutable("receipt"), provider=ids["provider"], printer_id=ids["printer"],
            source_epoch="epoch-1", event_key="run-1:completed", event_type="PRINT_COMPLETED",
            payload_hash="a" * 64, received_at=END, processing_result="PENDING",
        ))
        if with_evidence:
            connection.execute(insert(a.consumption_evidence).values(
                id=ids["evidence"], device_id=ids["device"], created_at=END,
                print_job_material_id=ids["material"], segment_id=ids["segment"],
                source_type="PRINTER", quantity_kind="CONSUMED_MASS", mode="ABSOLUTE",
                weight_mg=Mass(mass), confidence_bp=10000, includes_purge=True,
                captured_at=END, received_at=END, interval_start=START, interval_end=END,
                scope_key=f"segment:{ids['segment']}", source_receipt_id=ids["receipt"],
                external_reference="run-1",
            ))
    return ids


def snapshot_database(engine):
    with engine.connect() as connection:
        snapshots = []
        for table in sorted(s.metadata.tables.values(), key=lambda item: item.name):
            primary_key = tuple(table.primary_key.columns)
            order = " ORDER BY " + ", ".join(
                f'"{column.name}"' for column in primary_key
            ) if primary_key else ""
            rows = connection.exec_driver_sql(
                f'SELECT * FROM "{table.name}"{order}',
            ).all()
            snapshots.append((table.name, tuple(rows)))
        return tuple(snapshots)


class PrintFinalizationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ufm-finalization-")
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "ufm.sqlite3"
        self.engine = create_sqlite_engine(self.database)
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine)
        self.commands = FinalizationCommands(lambda: SQLiteUnitOfWork(self.engine))

    def parameters(self):
        return {"job_id": self.ids["job"], "segment_id": self.ids["segment"],
                "evidence_id": self.ids["evidence"], "receipt_id": self.ids["receipt"],
                "actor_device_id": self.ids["device"], "command_key": "finalize-run-1", "at": AT}

    def test_persisted_logical_material_is_independent_of_tool_index(self) -> None:
        from ufm.infrastructure.persistence.models.schema import print_job_material

        with self.engine.begin() as connection:
            connection.execute(
                update(print_job_material).where(
                    print_job_material.c.id == self.ids["material"],
                ).values(logical_material_index=5),
            )
        with SQLiteUnitOfWork(self.engine) as work:
            material = work.jobs.get_material(self.ids["material"])
        self.assertEqual(material.logical_material_index, 5)
        self.assertEqual(material.tool_index, 0)

    def snapshot(self):
        return snapshot_database(self.engine)

    def reserve(self, amount, *, other=False):
        material = self.ids["material"]
        if other:
            job, material = EntityId.new(), EntityId.new()
            common = dict(device_id=self.ids["device"], created_at=BASE, updated_at=BASE, revision=1)
            with self.engine.begin() as connection:
                connection.execute(insert(s.print_job).values(
                    **common, id=job, printer_id=self.ids["printer"], source_type="PRINTER",
                    detected_at=START, status="RUNNING", finalization_state="NOT_STARTED",
                ))
                connection.execute(insert(s.print_job_material).values(
                    **common, id=material, print_job_id=job, channel_key="other", tool_index=0,
                ))
        identity = EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(insert(a.reservation).values(
                id=identity, device_id=self.ids["device"], created_at=BASE, updated_at=BASE,
                revision=1, spool_id=self.ids["spool"], print_job_material_id=material,
                reserved_mg=Mass(amount), status="ACTIVE", activated_at=START,
            ))
        return identity

    def test_success_has_proof_links_exact_balance_and_terminal_states(self):
        claim = self.reserve(100000)
        record = self.commands.finalize_single(**self.parameters())
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.ids["spool"])
            self.assertEqual(spool.effective_remaining, Mass(987655))
            self.assertEqual(spool.estimated_remaining, Mass(987655))
            self.assertEqual(spool.ledger_sequence, 2)
            self.assertEqual(work.jobs.get(self.ids["job"]).finalization_state,
                             FinalizationState.FINALIZED)
            self.assertEqual(work.receipts.get(self.ids["receipt"]).state, ReceiptState.PROCESSED)
            settled = work.reservations.get(claim)
            self.assertEqual(settled.state, ReservationState.CONSUMED)
            self.assertEqual(settled.allocated_consumption, Mass(12345))
            self.assertEqual(settled.released, Mass(87655))
            self.assertEqual(settled.settled_finalization_id, record.id)
        with self.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(a.decision_evidence)).all()), 1)

    def test_confirmed_print_freezes_cost_from_purchase_basis(self):
        with self.engine.begin() as connection:
            connection.execute(update(s.spool).where(s.spool.c.id == self.ids["spool"]).values(
                purchase_price=ExactDecimal.parse("18.25"), purchase_basis_mg=Mass(1_000_000),
                currency="UAH", purchase_date="2026-10-01",
            ))
        self.commands.finalize_single(**self.parameters())
        with self.engine.begin() as connection:
            connection.execute(update(s.spool).where(s.spool.c.id == self.ids["spool"]).values(
                purchase_price=ExactDecimal.parse("99.99"),
            ))
        with SQLiteUnitOfWork(self.engine) as work:
            entry = work.ledger.by_command("finalize-run-1")
            self.assertEqual((entry.unit_cost, entry.currency), (ExactDecimal.parse("0.23"), "UAH"))
            self.assertEqual(entry.metadata_json, '{"cost_snapshot_v1":{"basis_mg":1000000,"consumed_mg":12345,"cost_minor":23,"price_minor":1825,"purchase_date":"2026-10-01","version":1}}')
        summary = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine)).cost_summary(self.ids["spool"])
        self.assertEqual((summary.confirmed_prints, summary.unknown_cost_prints,
                          summary.unknown_cost_consumed, summary.totals_by_currency),
                         (1, 0, Mass(0), (("UAH", ExactDecimal.parse("0.23")),)))
        InventoryCommands(lambda: SQLiteUnitOfWork(self.engine)).deduct_manual(
            spool_id=self.ids["spool"], amount=Mass(100), command_key="manual-cost-exclusion",
            actor_device_id=self.ids["device"], at=AT,
        )
        self.assertEqual(InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
                         .cost_summary(self.ids["spool"]), summary)

    def test_missing_or_unrecognized_cost_profile_does_not_block_print_finalization(self):
        with self.engine.begin() as connection:
            connection.execute(update(s.spool).where(s.spool.c.id == self.ids["spool"]).values(
                purchase_price=ExactDecimal.parse("18.25"), purchase_basis_mg=Mass(1_000_000),
                currency="JPY",
            ))
        self.commands.finalize_single(**self.parameters())
        with SQLiteUnitOfWork(self.engine) as work:
            entry = work.ledger.by_command("finalize-run-1")
            self.assertIsNone(entry.unit_cost)
            self.assertIsNone(entry.currency)
            self.assertEqual(entry.metadata_json, "{}")
        summary = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine)).cost_summary(
            self.ids["spool"],
        )
        self.assertEqual((summary.confirmed_prints, summary.unknown_cost_prints,
                          summary.unknown_cost_consumed, summary.totals_by_currency),
                         (1, 1, Mass(12345), ()))

    def test_period_cost_report_uses_print_start_time_and_keeps_currency_and_unknowns(self):
        with self.engine.begin() as connection:
            connection.execute(update(s.spool).where(s.spool.c.id == self.ids["spool"]).values(
                purchase_price=ExactDecimal.parse("18.25"), purchase_basis_mg=Mass(1_000_000),
                currency="PLN",
            ))
        self.commands.finalize_single(**self.parameters())
        commands = InventoryCommands(lambda: SQLiteUnitOfWork(self.engine))
        report = commands.cost_report(started_at=START, until=AT, printer_id=self.ids["printer"])
        self.assertEqual(report.print_count, 1)
        self.assertEqual(report.consumed, Mass(12345))
        self.assertEqual(report.totals_by_currency, (("PLN", ExactDecimal.parse("0.23")),))
        self.assertEqual(len(report.entries), 1)
        self.assertEqual(report.entries[0].spool_name, "Fixture spool")
        self.assertEqual(report.entries[0].printer_name, "Fixture printer")
        excluded = commands.cost_report(started_at=AT, until=UtcDateTime.parse(
            "2026-10-26T12:32:00.000000Z"))
        self.assertEqual(excluded.entries, ())
        with self.assertRaisesRegex(ValueError, "interval_invalid"):
            commands.cost_report(started_at=AT, until=START)

    def test_receipt_identity_conflict_blocks_new_printer_debit(self):
        from tests.integration.test_receipt_ingestion import create_receipt_conflict
        create_receipt_conflict(self.engine, self.ids)
        before = self.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "receipt_conflict"):
            self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)

    def test_other_receipt_lifecycle_conflict_blocks_new_printer_debit(self):
        from tests.integration.test_receipt_ingestion import create_lifecycle_conflict
        create_lifecycle_conflict(self.engine, self.ids)
        before = self.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "lifecycle_conflict"):
            self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)

    def test_quarantined_terminal_receipt_cannot_authorize_debit(self):
        from tests.integration.test_receipt_ingestion import quarantine_receipt
        quarantine_receipt(self.engine, self.ids)
        before = self.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "projection_quarantined"):
            self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)

    def test_different_receipt_run_quarantine_blocks_printer_debit(self):
        from tests.integration.test_receipt_ingestion import create_run_quarantine
        create_run_quarantine(self.engine, self.ids)
        before = self.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "projection_run_quarantined"):
            self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)

    def test_run_quarantine_after_finalization_preserves_safe_replay(self):
        from tests.integration.test_receipt_ingestion import create_run_quarantine
        result = self.commands.finalize_single(**self.parameters())
        create_run_quarantine(self.engine, self.ids)
        before = self.snapshot()
        self.assertEqual(self.commands.finalize_single(**self.parameters()), result)
        self.assertEqual(self.snapshot(), before)

    def test_lifecycle_conflict_after_commit_preserves_printer_replay(self):
        from tests.integration.test_receipt_ingestion import create_lifecycle_conflict
        result = self.commands.finalize_single(**self.parameters())
        create_lifecycle_conflict(self.engine, self.ids)
        before = self.snapshot()
        self.assertEqual(self.commands.finalize_single(**self.parameters()), result)
        self.assertEqual(self.snapshot(), before)

    def test_replay_after_reopen_and_later_manual_use_does_not_debit_again(self):
        record = self.commands.finalize_single(**self.parameters())
        InventoryCommands(lambda: SQLiteUnitOfWork(self.engine)).deduct_manual(
            spool_id=self.ids["spool"], amount=Mass(1000), command_key="later-manual-use",
            actor_device_id=self.ids["device"], at=AT,
        )
        before = self.snapshot()
        reopened = create_sqlite_engine(self.database)
        try:
            replay = FinalizationCommands(lambda: SQLiteUnitOfWork(reopened)).finalize_single(
                **self.parameters(),
            )
        finally:
            reopened.dispose()
        self.assertEqual(record, replay)
        self.assertEqual(self.snapshot(), before)

    def test_changed_key_or_actor_is_a_conflict_without_writes(self):
        self.commands.finalize_single(**self.parameters())
        for overrides in ({"command_key": "other-event"}, {"actor_device_id": EntityId.new()}):
            with self.subTest(overrides=overrides):
                before = self.snapshot()
                with self.assertRaises(IdempotencyConflict):
                    self.commands.finalize_single(**(self.parameters() | overrides))
                self.assertEqual(self.snapshot(), before)

    def test_failure_after_ledger_settlement_and_receipt_update_rolls_everything_back(self):
        self.reserve(100000)
        before = self.snapshot()
        with patch.object(Audit, "append", side_effect=RuntimeError("injected audit failure")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)
        self.commands.finalize_single(**self.parameters())

    def test_two_concurrent_writers_return_one_finalization(self):
        barrier = Barrier(2)

        def execute(_):
            barrier.wait(timeout=10)
            return FinalizationCommands(lambda: SQLiteUnitOfWork(self.engine)).finalize_single(
                **self.parameters(),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            records = list(executor.map(execute, range(2)))
        self.assertEqual(records[0], records[1])
        with self.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(a.finalization_record)).all()), 1)
            self.assertEqual(len(connection.execute(select(l.filament_transaction)).all()), 2)

    def test_zero_consumption_releases_reservation_without_zero_debit(self):
        self.ids = create_scope(self.engine, mass=0)
        claim = self.reserve(100000)
        record = self.commands.finalize_single(**self.parameters())
        before = self.snapshot()
        self.assertEqual(self.commands.finalize_single(**self.parameters()), record)
        self.assertEqual(self.snapshot(), before)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.reservations.get(claim).state, ReservationState.RELEASED)
            self.assertEqual(work.reservations.get(claim).released, Mass(100000))
            self.assertEqual(work.spools.get(self.ids["spool"]).ledger_sequence, 1)

    def test_actual_over_own_reservation_preserves_other_jobs_claim(self):
        self.ids = create_scope(self.engine, mass=250000)
        own = self.reserve(100000)
        other = self.reserve(300000, other=True)
        self.commands.finalize_single(**self.parameters())
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.ids["spool"]).effective_remaining, Mass(750000))
            self.assertEqual(work.reservations.get(own).allocated_consumption, Mass(100000))
            self.assertEqual(work.reservations.get(other).state, ReservationState.ACTIVE)

    def test_unknown_stock_and_foreign_reserved_capacity_are_not_deducted(self):
        for unknown in (True, False):
            with self.subTest(unknown=unknown):
                self.ids = create_scope(self.engine, opening=not unknown, mass=900000)
                if not unknown:
                    self.reserve(300000, other=True)
                before = self.snapshot()
                with self.assertRaises(FinalizationRejected):
                    self.commands.finalize_single(**self.parameters())
                self.assertEqual(self.snapshot(), before)

    def test_unresolved_or_partial_job_is_not_finalized(self):
        for change in ("extra-material", "open-segment", "wrong-epoch", "late-opening"):
            with self.subTest(change=change):
                self.ids = create_scope(self.engine, opening=change != "late-opening")
                with self.engine.begin() as connection:
                    if change == "extra-material":
                        connection.execute(insert(s.print_job_material).values(
                            id=EntityId.new(), device_id=self.ids["device"], created_at=BASE,
                            updated_at=BASE, revision=1, print_job_id=self.ids["job"],
                            channel_key="second", tool_index=1,
                        ))
                    elif change == "open-segment":
                        connection.execute(update(s.material_usage_segment).where(
                            s.material_usage_segment.c.id == self.ids["segment"],
                        ).values(ended_at=None))
                    elif change == "wrong-epoch":
                        connection.execute(update(s.external_event_receipt).where(
                            s.external_event_receipt.c.id == self.ids["receipt"],
                        ).values(source_epoch="unverified-epoch"))
                if change == "late-opening":
                    InventoryCommands(lambda: SQLiteUnitOfWork(self.engine)).establish_opening_stock(
                        spool_id=self.ids["spool"], amount=Mass(1000000),
                        actor_device_id=self.ids["device"], command_key=f"late:{self.ids['spool']}",
                        at=END,
                    )
                before = self.snapshot()
                with self.assertRaises(FinalizationRejected):
                    self.commands.finalize_single(**self.parameters())
                self.assertEqual(self.snapshot(), before)

    def test_unverified_evidence_is_never_promoted_to_actual_consumption(self):
        with self.engine.connect() as connection:
            original = dict(connection.execute(select(a.consumption_evidence).where(
                a.consumption_evidence.c.id == self.ids["evidence"],
            )).mappings().one())
        cases = (
            {"source_type": "SLICER"}, {"mode": "ESTIMATE"}, {"confidence_bp": 9999},
            {"includes_purge": None}, {"interval_start": BASE}, {"segment_id": None},
            {"external_reference": "a-different-print-run"},
            {"quantity_kind": "LENGTH", "weight_mg": None, "length_mm": 1000},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                identity = EntityId.new()
                with self.engine.begin() as connection:
                    connection.execute(insert(a.consumption_evidence).values(
                        **(original | overrides | {"id": identity}),
                    ))
                before = self.snapshot()
                with self.assertRaises(FinalizationRejected):
                    self.commands.finalize_single(**(self.parameters() | {"evidence_id": identity}))
                self.assertEqual(self.snapshot(), before)

    def test_late_print_after_weighing_requires_reconciliation(self):
        with SQLiteUnitOfWork(self.engine) as work:
            spool = work.spools.get(self.ids["spool"])
            entry = FilamentTransaction(
                id=EntityId.new(), device_id=self.ids["device"], created_at=END,
                spool_id=spool.id, sequence=2, transaction_type=TransactionType.MEASUREMENT_CORRECTION,
                delta=Mass(-10000), previous_effective=spool.effective_remaining,
                new_effective=Mass(990000), previous_estimated=spool.estimated_remaining,
                new_estimated=Mass(990000), command_key="weighing", command_item=0,
                source_type="SCALE", confidence_bp=10000,
            )
            work.ledger.append(entry)
            work.spools.save(replace(
                spool, effective_remaining=entry.new_effective, estimated_remaining=entry.new_estimated,
                ledger_sequence=2, revision=spool.revision + 1, updated_at=END,
            ), spool.revision)
            work.commit()
        before = self.snapshot()
        with self.assertRaisesRegex(FinalizationRejected, "measurement_overlap"):
            self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)

    def test_changed_payload_or_damaged_job_cannot_replay_as_success(self):
        self.commands.finalize_single(**self.parameters())
        for change in ("payload", "job-state"):
            with self.subTest(change=change):
                with self.engine.begin() as connection:
                    if change == "payload":
                        connection.execute(update(s.external_event_receipt).where(
                            s.external_event_receipt.c.id == self.ids["receipt"],
                        ).values(payload_hash="b" * 64))
                    else:
                        connection.execute(update(s.external_event_receipt).where(
                            s.external_event_receipt.c.id == self.ids["receipt"],
                        ).values(payload_hash="a" * 64))
                        connection.execute(update(s.print_job).where(
                            s.print_job.c.id == self.ids["job"],
                        ).values(finalization_state="NOT_STARTED"))
                before = self.snapshot()
                with self.assertRaises(IdempotencyConflict):
                    self.commands.finalize_single(**self.parameters())
                self.assertEqual(self.snapshot(), before)

    def test_command_key_cannot_be_reused_for_another_print(self):
        self.commands.finalize_single(**self.parameters())
        self.ids = create_scope(self.engine)
        before = self.snapshot()
        with self.assertRaises(IdempotencyConflict):
            self.commands.finalize_single(**self.parameters())
        self.assertEqual(self.snapshot(), before)

    def test_process_crash_before_and_after_commit_recovers_without_double_debit(self):
        script = '''
import os,sys
from pathlib import Path
from ufm.application.finalization import FinalizationCommands
from ufm.domain.value_objects import EntityId,UtcDateTime
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
engine=create_sqlite_engine(Path(sys.argv[1]))
original=SQLiteUnitOfWork.commit
def crash(work):
    if sys.argv[2]=="after": original(work)
    os._exit(39)
SQLiteUnitOfWork.commit=crash
ids=[EntityId.parse(value) for value in sys.argv[3:]]
FinalizationCommands(lambda:SQLiteUnitOfWork(engine)).finalize_single(
    job_id=ids[0],segment_id=ids[1],evidence_id=ids[2],receipt_id=ids[3],
    actor_device_id=ids[4],command_key="finalize-run-1",
    at=UtcDateTime.parse("2026-10-26T12:31:00.000000Z"))
'''
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                before = self.snapshot()
                result = subprocess.run([
                    sys.executable, "-c", script, str(self.database), boundary,
                    *[str(self.ids[key]) for key in ("job", "segment", "evidence", "receipt", "device")],
                ], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 39, result.stderr)
                if boundary == "before":
                    self.assertEqual(self.snapshot(), before)
                else:
                    committed = self.snapshot()
                    self.commands.finalize_single(**self.parameters())
                    self.assertEqual(self.snapshot(), committed)


if __name__ == "__main__":
    unittest.main()
