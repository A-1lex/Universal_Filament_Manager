"""Receipt projection persists observations without manufacturing accounting facts."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import select

from tests.integration.test_print_finalization import AT, END, START, create_scope
from ufm.application.job_projection import JobProjectionCommands, ProjectionRejected
from ufm.application.receipt_ingestion import ReceiptIngestion
from ufm.domain.enums import FinalizationState, PrintStatus, ReceiptState
from ufm.domain.value_objects import UtcDateTime
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class JobProjectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ufm-job-projection-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "projection.sqlite3"
        self.engine = create_sqlite_engine(self.path)
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine, with_evidence=False)
        self.ingestion = ReceiptIngestion(lambda: SQLiteUnitOfWork(self.engine))
        self.commands = JobProjectionCommands(lambda: SQLiteUnitOfWork(self.engine))
        self.event_number = 0

    def receive(self, state="started", *, occurrence="projection-run", epoch="projection-epoch",
                sequence=1, observed_at=START, layers=None, current_layer=None, progress_bp=None,
                digest="b" * 64, mappings=None):
        self.event_number += 1
        message = {"v": 1, "kind": "job", "request_id": "projection-request",
                   "printer_id": str(self.ids["printer"]), "source_epoch": epoch,
                   "sequence": sequence, "observed_at": observed_at.value.isoformat(),
                   "occurrence_key": occurrence, "state": state,
                   "file_sha256": digest, "completed_layers": layers,
                   "current_layer": current_layer, "progress_bp": progress_bp}
        if mappings is not None:
            message["material_slot_mappings"] = mappings
        payload = json.dumps(message).encode()
        return self.ingestion.ingest(
            provider_instance_id=self.ids["provider"], printer_id=self.ids["printer"],
            actor_device_id=self.ids["device"], event_key=f"projection:{self.event_number}",
            raw_payload=payload, normalized_payload=payload, received_at=END)

    def apply(self, receipt):
        return self.commands.apply(receipt_id=receipt.id, actor_device_id=self.ids["device"], at=AT)

    def job(self, marker):
        with SQLiteUnitOfWork(self.engine) as work:
            return work.jobs.get(marker.print_job_id)

    def assert_no_source_times(self, job):
        for field in ("started_at", "completed_at", "failed_at", "cancelled_at"):
            self.assertIsNone(getattr(job, field), field)

    def assert_conflict(self, job_id):
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.reconciliations.open_task_by_dedupe(
                f"job:{job_id}:lifecycle_conflict"))

    def rows(self, names):
        with self.engine.connect() as connection:
            snapshots = {}
            for name in names:
                table = s.metadata.tables[name]
                statement = select(table)
                primary_key = tuple(table.primary_key.columns)
                if primary_key:
                    statement = statement.order_by(*primary_key)
                snapshots[name] = tuple(connection.execute(statement).all())
            return snapshots

    def test_restart_replay_preserves_one_job_alias_and_application(self):
        receipt = self.receive()
        marker = self.apply(receipt)
        reopened = create_sqlite_engine(self.path)
        try:
            command = JobProjectionCommands(lambda: SQLiteUnitOfWork(reopened))
            self.assertEqual(command.apply(receipt_id=receipt.id,
                actor_device_id=self.ids["device"], at=AT), marker)
            with SQLiteUnitOfWork(reopened) as work:
                self.assertEqual(work.projections.by_receipt(receipt.id), marker)
                aliases = work.jobs.aliases_for_job(marker.print_job_id)
                self.assertEqual(len(aliases), 1)
                self.assertEqual(aliases[0].occurrence_scope, (
                    self.ids["provider"], self.ids["printer"], "PRINTER",
                    "projection-epoch", "projection-run"))
        finally:
            reopened.dispose()
        job = self.job(marker)
        self.assertEqual(marker.outcome, "APPLIED")
        self.assertEqual(job.status, PrintStatus.PREPARING)
        self.assertEqual(job.finalization_state, FinalizationState.NOT_STARTED)
        self.assertEqual(job.file_hash, "b" * 64)
        self.assert_no_source_times(job)

    def test_same_file_two_sequential_occurrences_remain_distinct(self):
        first = self.apply(self.receive())
        self.apply(self.receive("completed", sequence=2, observed_at=END))
        second = self.apply(self.receive(occurrence="projection-run-2", observed_at=END))
        self.assertNotEqual(first.print_job_id, second.print_job_id)
        self.assertEqual(self.job(first).file_hash, self.job(second).file_hash)

    def test_terminal_stays_accounting_pending_and_projection_queue_advances(self):
        first = self.receive()
        self.apply(first)
        terminal = self.receive("completed", sequence=2, observed_at=END)
        self.apply(terminal)
        next_run = self.receive(occurrence="projection-next", observed_at=END)
        queue_ids = {item.id for item in self.commands.pending()}
        self.assertNotIn(first.id, queue_ids)
        self.assertNotIn(terminal.id, queue_ids)
        self.assertIn(next_run.id, queue_ids)
        with SQLiteUnitOfWork(self.engine) as work:
            stored = work.receipts.get(terminal.id)
            self.assertEqual(stored.state, ReceiptState.PENDING)
            self.assertIsNone(stored.processed_at)

    def test_missing_start_is_durable_ambiguity_without_invented_interval(self):
        for state in ("running", "paused", "completed"):
            with self.subTest(state=state):
                marker = self.apply(self.receive(state, occurrence=f"missing-{state}"))
                job = self.job(marker)
                self.assertEqual(job.finalization_state, FinalizationState.NEEDS_RECONCILIATION)
                self.assert_no_source_times(job)
                self.assert_conflict(job.id)

    def test_zero_and_terminal_layer_counts_never_populate_current_layer(self):
        marker = self.apply(self.receive(layers=0, sequence=0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.projections.for_job(marker.print_job_id).completed_layers, 0)
        self.apply(self.receive("running", sequence=1, observed_at=END, layers=10))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.projections.for_job(marker.print_job_id).source_sequence, 1)
        self.apply(self.receive("completed", sequence=2, observed_at=AT, layers=10))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.projections.for_job(marker.print_job_id).completed_layers, 10)
        self.assertIsNone(self.job(marker).current_layer)
        self.assertIsNone(self.job(marker).total_layers)

    def test_verified_current_layer_and_progress_survive_projection_restart(self):
        first = self.apply(self.receive(
            layers=8, current_layer=9, progress_bp=3210, sequence=1,
        ))
        second = self.apply(self.receive(
            "running", layers=10, current_layer=11, progress_bp=4321,
            sequence=2, observed_at=END,
        ))
        self.assertEqual(first.print_job_id, second.print_job_id)
        self.assertEqual(self.job(second).current_layer, 11)
        self.assertEqual(self.job(second).progress_bp, 4321)

        self.engine.dispose()
        self.engine = create_sqlite_engine(self.path)
        self.addCleanup(self.engine.dispose)
        self.commands = JobProjectionCommands(lambda: SQLiteUnitOfWork(self.engine))
        with SQLiteUnitOfWork(self.engine) as work:
            restored = work.jobs.get(second.print_job_id)
        history = self.commands.mapping_history(print_job_id=second.print_job_id)

        self.assertEqual(restored.current_layer, 11)
        self.assertEqual(restored.progress_bp, 4321)
        self.assertEqual([item.completed_layers for item in history], [8, 10])
        self.assertEqual([item.current_layer for item in history], [9, 11])
        self.assertEqual([item.progress_bp for item in history], [3210, 4321])

    def test_mapping_history_reconstructs_each_applied_snapshot_after_restart(self):
        mapping_a = [{"logical_material": 0, "disposition": "reported_slot",
                      "provider_system_key": "ams-0", "provider_slot_key": "ams-0:slot-0"}]
        mapping_b = [{"logical_material": 0, "disposition": "reported_slot",
                      "provider_system_key": "ams-0", "provider_slot_key": "ams-0:slot-1"}]
        started = self.apply(self.receive(mappings=mapping_a, layers=0))
        self.apply(self.receive("running", sequence=2, observed_at=END, layers=24, mappings=mapping_b))
        self.apply(self.receive("running", sequence=3, observed_at=AT, layers=25, mappings=mapping_b))

        reopened = create_sqlite_engine(self.path)
        try:
            history = JobProjectionCommands(lambda: SQLiteUnitOfWork(reopened)).mapping_history(
                print_job_id=started.print_job_id)
        finally:
            reopened.dispose()

        self.assertEqual([item.source_sequence for item in history], [1, 2, 3])
        self.assertEqual([item.completed_layers for item in history], [0, 24, 25])
        self.assertEqual([item.material_slot_mappings[0].provider_slot_key for item in history],
                         ["ams-0:slot-0", "ams-0:slot-1", "ams-0:slot-1"])
        self.assertEqual([item.state for item in history], ["started", "running", "running"])

    def test_mapping_history_excludes_stale_receipt_and_rejects_sequence_time_reversal(self):
        started = self.apply(self.receive(mappings=[{
            "logical_material": 0, "disposition": "reported_slot",
            "provider_system_key": "ams-0", "provider_slot_key": "ams-0:slot-0",
        }]))
        self.apply(self.receive("running", sequence=2, observed_at=END, layers=10))
        stale = self.apply(self.receive("running", sequence=1, observed_at=START, layers=5,
                                        mappings=[{"logical_material": 0, "disposition": "reported_slot",
                                                   "provider_system_key": "ams-0",
                                                   "provider_slot_key": "ams-0:slot-1"}]))
        self.assertEqual(stale.outcome, "IGNORED_STALE")
        history = self.commands.mapping_history(print_job_id=started.print_job_id)
        self.assertEqual([item.source_sequence for item in history], [1, 2])
        self.assertEqual(history[-1].material_slot_mappings, ())

        conflict = self.apply(self.receive("running", sequence=3, observed_at=START, layers=11,
                                           mappings=[{"logical_material": 0, "disposition": "reported_slot",
                                                      "provider_system_key": "ams-0",
                                                      "provider_slot_key": "ams-0:slot-1"}]))
        self.assertEqual(conflict.outcome, "CONFLICT")

    def test_source_sequence_regression_or_reuse_cannot_rewrite_mapping_order(self):
        mapping_a = [{"logical_material": 0, "disposition": "reported_slot",
                      "provider_system_key": "ams-0", "provider_slot_key": "ams-0:slot-0"}]
        mapping_b = [{"logical_material": 0, "disposition": "reported_slot",
                      "provider_system_key": "ams-0", "provider_slot_key": "ams-0:slot-1"}]
        marker = self.apply(self.receive(mappings=mapping_a))
        self.apply(self.receive("running", sequence=2, observed_at=END, layers=4, mappings=mapping_a))

        regressed = self.apply(self.receive("running", sequence=1, observed_at=AT, layers=5,
                                            mappings=mapping_b))
        reused = self.apply(self.receive("running", sequence=2, observed_at=END, layers=4,
                                          mappings=mapping_b))

        self.assertEqual(regressed.outcome, "CONFLICT")
        self.assertEqual(reused.outcome, "CONFLICT")
        self.assertEqual([item.material_slot_mappings[0].provider_slot_key
                          for item in self.commands.mapping_history(print_job_id=marker.print_job_id)],
                         ["ams-0:slot-0", "ams-0:slot-0"])

    def test_terminal_duplicate_and_different_terminal_keep_first_status(self):
        self.apply(self.receive())
        terminal = self.apply(self.receive("cancelled", observed_at=END, sequence=2))
        duplicate = self.apply(self.receive("cancelled", observed_at=END, sequence=3))
        self.assertEqual(duplicate.outcome, "IGNORED_STALE")
        for state in ("failed", "completed"):
            with self.subTest(state=state):
                conflict = self.apply(self.receive(state, observed_at=END, sequence=4))
                self.assertEqual(conflict.outcome, "CONFLICT")
                self.assertEqual(conflict.print_job_id, terminal.print_job_id)
                self.assertEqual(self.job(terminal).status, PrintStatus.CANCELLED)
        self.assert_conflict(terminal.print_job_id)

    def test_older_running_after_terminal_is_stale_newer_or_equal_conflicts(self):
        self.apply(self.receive())
        terminal = self.apply(self.receive("completed", sequence=2, observed_at=END))
        stale = self.apply(self.receive("running", sequence=100, observed_at=START))
        self.assertEqual(stale.outcome, "IGNORED_STALE")
        for observed in (END, AT):
            conflict = self.apply(self.receive("running", sequence=0, observed_at=observed))
            self.assertEqual(conflict.outcome, "CONFLICT")
        self.assertEqual(self.job(terminal).status, PrintStatus.COMPLETED)

    def test_layer_reset_and_hash_change_are_conflicts_without_rewriting_facts(self):
        marker = self.apply(self.receive(layers=5))
        decrease = self.apply(self.receive("running", observed_at=END, sequence=2, layers=4))
        self.assertEqual(decrease.outcome, "CONFLICT")
        changed = self.apply(self.receive("running", observed_at=START, sequence=0, digest="c" * 64))
        self.assertEqual(changed.outcome, "CONFLICT")
        self.assertEqual(self.job(marker).file_hash, "b" * 64)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.projections.for_job(marker.print_job_id).completed_layers, 5)
        self.assert_conflict(marker.print_job_id)

    def test_current_layer_and_progress_regressions_are_conflicts(self):
        marker = self.apply(self.receive(current_layer=6, progress_bp=5500))
        layer_reset = self.apply(self.receive(
            "running", sequence=2, observed_at=END, current_layer=5, progress_bp=6000,
        ))
        self.assertEqual(layer_reset.outcome, "CONFLICT")
        progress_reset = self.apply(self.receive(
            "running", sequence=3, observed_at=AT, current_layer=7, progress_bp=5000,
        ))
        self.assertEqual(progress_reset.outcome, "CONFLICT")
        self.assertEqual(self.job(marker).current_layer, 6)
        self.assertEqual(self.job(marker).progress_bp, 5500)
        self.assert_conflict(marker.print_job_id)

    def test_projection_does_not_change_material_mapping_or_financial_tables(self):
        names = ("print_job_material", "material_usage_segment", "reservation",
                 "consumption_evidence", "filament_transaction", "spool",
                 "consumption_decision", "finalization_record")
        before = self.rows(names)
        marker = self.apply(self.receive())
        self.apply(self.receive("running", sequence=2, observed_at=END, layers=4))
        self.apply(self.receive("failed", sequence=3, observed_at=END, layers=4))
        self.assertEqual(self.rows(names), before)
        self.assertIsNone(self.job(marker).plate_name)
        self.assert_no_source_times(self.job(marker))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(list(work.jobs.materials_for_job(marker.print_job_id)), [])

    def test_commit_failure_rolls_back_job_alias_and_marker_then_retries(self):
        receipt = self.receive()
        before = self.rows(("print_job", "job_identity_alias"))
        with patch.object(SQLiteUnitOfWork, "commit", side_effect=RuntimeError("projection commit failure")):
            with self.assertRaisesRegex(RuntimeError, "projection commit failure"):
                self.apply(receipt)
        self.assertEqual(self.rows(("print_job", "job_identity_alias")), before)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNone(work.projections.by_receipt(receipt.id))
        self.assertEqual(self.apply(receipt).outcome, "APPLIED")

    def test_two_writers_apply_one_receipt_once(self):
        receipt = self.receive()
        barrier = Barrier(2)

        def apply():
            barrier.wait(timeout=5)
            return self.apply(receipt)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(apply) for _ in range(2)]
            markers = [future.result(timeout=10) for future in futures]
        self.assertEqual(markers[0], markers[1])
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(len(work.jobs.aliases_for_job(markers[0].print_job_id)), 1)

    def test_legacy_alias_without_projection_preserves_confirmed_job(self):
        before = self.rows(("print_job", "job_identity_alias"))
        marker = self.apply(self.receive("running", epoch="epoch-1", occurrence="run-1"))
        self.assertEqual(marker.outcome, "CONFLICT")
        self.assertEqual(marker.print_job_id, self.ids["job"])
        self.assertEqual(self.rows(("print_job", "job_identity_alias")), before)
        self.assert_conflict(self.ids["job"])

    def test_concurrent_occurrence_or_epoch_reconciles_both_runs_without_merging(self):
        first = self.apply(self.receive())
        second = self.apply(self.receive(occurrence="overlapping", observed_at=END))
        third = self.apply(self.receive(epoch="reconnected-epoch", observed_at=END))
        self.assertEqual(len({first.print_job_id, second.print_job_id, third.print_job_id}), 3)
        for marker in (first, second, third):
            self.assert_conflict(marker.print_job_id)

    def test_deleted_cursor_is_not_reused_or_given_an_application_marker(self):
        marker = self.apply(self.receive())
        with SQLiteUnitOfWork(self.engine) as work:
            state = work.projections.for_job(marker.print_job_id)
            work.projections.save_state(replace(state, deleted_at=AT,
                revision=state.revision + 1), state.revision)
            work.commit()
        incoming = self.receive("running", observed_at=END, sequence=2)
        before = self.rows(("print_job", "job_projection_state", "job_receipt_application"))
        with self.assertRaises(ProjectionRejected):
            self.apply(incoming)
        self.assertEqual(self.rows(tuple(before)), before)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNone(work.projections.by_receipt(incoming.id))

    def test_future_updated_cursor_cannot_be_rewound_by_projection(self):
        marker = self.apply(self.receive())
        with SQLiteUnitOfWork(self.engine) as work:
            state = work.projections.for_job(marker.print_job_id)
            work.projections.save_state(replace(state,
                updated_at=UtcDateTime.parse("2026-10-27T12:00:00.000000Z"),
                revision=state.revision + 1), state.revision)
            work.commit()
        incoming = self.receive("running", observed_at=END, sequence=2)
        before = self.rows(("print_job", "job_projection_state", "job_receipt_application"))
        with self.assertRaises(ProjectionRejected):
            self.apply(incoming)
        self.assertEqual(self.rows(tuple(before)), before)

