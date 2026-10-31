"""Bounded receipt passes isolate observation rejects from persistence failures."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from sqlalchemy import select

from tests.integration.test_print_finalization import AT, END, START, create_scope
from ufm.application.job_conflicts import run_quarantine_key, run_quarantine_key_for_scope
from ufm.application.job_projection import JobProjectionCommands, ProjectionRejected
from ufm.application.ports.persistence import PersistenceUnavailable
from ufm.application.projection_drain import (
    DrainResult,
    ProjectionDrain,
    ProjectionQuarantineResolution,
)
from ufm.application.receipt_ingestion import ReceiptIngestion
from ufm.domain.enums import ReceiptState, ReconciliationState, Severity
from ufm.domain.value_objects import UtcDateTime
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork

FUTURE = UtcDateTime.parse("2026-10-27T12:00:00.000000Z")


class ProjectionDrainTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ufm-projection-drain-")
        self.addCleanup(directory.cleanup)
        self.engine = create_sqlite_engine(Path(directory.name) / "drain.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine, with_evidence=False)
        self.ingestion = ReceiptIngestion(lambda: SQLiteUnitOfWork(self.engine))
        self.drain = ProjectionDrain(lambda: SQLiteUnitOfWork(self.engine))
        self.counter = 0

    def receive(self, *, state="started", observed=START, received=END, sequence=1,
                occurrence="drain-run", epoch="drain-epoch"):
        self.counter += 1
        payload = json.dumps({"v": 1, "kind": "job", "request_id": f"drain-{self.counter}",
            "printer_id": str(self.ids["printer"]), "source_epoch": epoch,
            "sequence": sequence, "observed_at": observed.value.isoformat(),
            "occurrence_key": occurrence, "state": state}).encode()
        return self.ingestion.ingest(provider_instance_id=self.ids["provider"],
            printer_id=self.ids["printer"], actor_device_id=self.ids["device"],
            event_key=f"drain:{self.counter}", raw_payload=payload,
            normalized_payload=payload, received_at=received)

    def run_pass(self, **changes):
        return self.drain.run_once(actor_device_id=self.ids["device"], at=AT, **changes)

    def task(self, receipt):
        with SQLiteUnitOfWork(self.engine) as work:
            return work.reconciliations.open_task_by_dedupe(f"receipt:{receipt.id}:projection_rejected")

    def rows(self, names):
        with self.engine.connect() as connection:
            return {name: tuple(connection.execute(select(s.metadata.tables[name]).order_by(
                s.metadata.tables[name].c.id)).all()) for name in names}

    def test_rejected_head_is_quarantined_and_later_valid_receipt_advances_next_pass(self):
        rejected = self.receive(observed=FUTURE)
        good = self.receive(received=AT)
        self.assertEqual(self.run_pass(limit=1), DrainResult(0, 0, 0, 1))
        task = self.task(rejected)
        self.assertEqual(task.reason_code, "PROJECTION_OBSERVATION_REJECTED")
        self.assertEqual(task.suggested_action, "review_projection_observation")
        self.assertEqual(task.state, ReconciliationState.OPEN)
        self.assertEqual(task.severity, Severity.ERROR)
        self.assertIsNone(task.print_job_id)
        self.assertEqual(self.run_pass(limit=1), DrainResult(1, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(good.id))
            self.assertIsNone(work.projections.by_receipt(rejected.id))
            self.assertEqual(work.receipts.get(rejected.id), rejected)

    def test_valid_start_and_terminal_remain_accounting_pending_without_financial_writes(self):
        names = ("spool", "filament_transaction", "reservation", "print_job_material",
                 "material_usage_segment", "consumption_evidence", "consumption_decision",
                 "finalization_record")
        before = self.rows(names)
        started = self.receive()
        terminal = self.receive(state="completed", observed=END, received=AT, sequence=2)
        self.assertEqual(self.run_pass(), DrainResult(2, 0, 0, 0))
        self.assertEqual(self.rows(names), before)
        with SQLiteUnitOfWork(self.engine) as work:
            for receipt in (started, terminal):
                self.assertEqual(work.receipts.get(receipt.id).state, ReceiptState.PENDING)
                self.assertIsNone(work.receipts.get(receipt.id).processed_at)

    def test_stale_and_terminal_conflict_are_counted_separately_from_quarantine(self):
        self.receive()
        self.assertEqual(self.run_pass(), DrainResult(1, 0, 0, 0))
        self.receive(state="completed", observed=END, sequence=2)
        self.assertEqual(self.run_pass(), DrainResult(1, 0, 0, 0))
        self.receive(state="running", observed=START, sequence=1)
        self.assertEqual(self.run_pass(), DrainResult(0, 1, 0, 0))
        self.receive(state="cancelled", observed=END, sequence=3)
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 1, 0))

    def test_repeated_rejection_snapshot_deduplicates_static_incident(self):
        rejected = self.receive(observed=FUTURE)
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 1))
        first = self.task(rejected)
        with patch.object(JobProjectionCommands, "pending", return_value=(rejected,)):
            self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 1))
        self.assertEqual(self.task(rejected), first)
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 0))

    def test_quarantine_commit_failure_propagates_without_false_marker_or_task(self):
        rejected = self.receive(observed=FUTURE)
        with patch.object(SQLiteUnitOfWork, "commit", side_effect=PersistenceUnavailable):
            with self.assertRaises(PersistenceUnavailable):
                self.run_pass()
        self.assertIsNone(self.task(rejected))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNone(work.projections.by_receipt(rejected.id))

    def test_persistence_failure_aborts_pass_preserving_prior_receipt_commit(self):
        first = self.receive()
        second = self.receive(state="running", observed=END, received=AT)
        original = JobProjectionCommands.apply

        def apply(commands, **kwargs):
            if kwargs["receipt_id"] == second.id:
                raise PersistenceUnavailable()
            return original(commands, **kwargs)

        with patch.object(JobProjectionCommands, "apply", new=apply):
            with self.assertRaises(PersistenceUnavailable):
                self.run_pass()
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(first.id))
            self.assertIsNone(work.projections.by_receipt(second.id))
        self.assertIsNone(self.task(second))

    def test_resolving_quarantine_makes_receipt_retryable(self):
        rejected = self.receive(observed=FUTURE)
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 1))
        with SQLiteUnitOfWork(self.engine) as work:
            task = work.reconciliations.open_task_by_dedupe(f"receipt:{rejected.id}:projection_rejected")
            work.reconciliations.save_task(replace(task, state=ReconciliationState.RESOLVED,
                updated_at=FUTURE, resolved_at=FUTURE, resolved_by=self.ids["device"],
                resolution_notes="Observation clock reviewed", revision=task.revision + 1), task.revision)
            work.commit()
        self.assertEqual(self.drain.run_once(actor_device_id=self.ids["device"], at=FUTURE),
                         DrainResult(1, 0, 0, 0))

    def run_key(self, occurrence, epoch="drain-epoch"):
        return run_quarantine_key_for_scope(self.ids["provider"], self.ids["printer"],
                                             "PRINTER", epoch, occurrence)

    def test_quarantine_before_first_alias_blocks_future_scope_and_normal_events_do_not_clear_it(self):
        rejected = self.receive(state="completed", observed=FUTURE,
                                occurrence="before-first-start")
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 1))
        key = self.run_key("before-first-start")
        with SQLiteUnitOfWork(self.engine) as work:
            blocker = work.reconciliations.open_task_by_dedupe(key)
            self.assertIsNotNone(blocker)
            self.assertIsNone(blocker.print_job_id)
        start = self.receive(observed=START, received=AT, occurrence="before-first-start")
        self.assertEqual(self.run_pass(), DrainResult(1, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(start.id))
            self.assertIsNotNone(work.jobs.by_occurrence_scope(
                self.ids["provider"], self.ids["printer"], "PRINTER", "drain-epoch",
                "before-first-start"))
            created = work.jobs.by_occurrence_scope(
                self.ids["provider"], self.ids["printer"], "PRINTER", "drain-epoch",
                "before-first-start")
            alias = work.jobs.aliases_for_job(created.id)[0]
            self.assertEqual(run_quarantine_key(alias), key)
            self.assertIsNotNone(work.reconciliations.open_task_by_dedupe(key))
            self.assertIsNone(work.projections.by_receipt(rejected.id))

    def test_distinct_occurrence_is_not_blocked_by_another_run_quarantine(self):
        self.receive(state="completed", observed=FUTURE, occurrence="quarantined-run")
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 1))
        other = self.receive(observed=START, received=AT, occurrence="independent-run")
        self.assertEqual(self.run_pass(), DrainResult(1, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(other.id))
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(self.run_key("independent-run")))

    def test_recheck_after_concurrent_apply_does_not_create_false_quarantine(self):
        receipt = self.receive()
        original = JobProjectionCommands.apply

        def applied_then_rejected(commands, **kwargs):
            original(commands, **kwargs)
            raise ProjectionRejected("projection.synthetic_race")

        with patch.object(JobProjectionCommands, "apply", new=applied_then_rejected):
            self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(receipt.id))
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(
                f"receipt:{receipt.id}:projection_rejected"))
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(self.run_key("drain-run")))

    def test_recheck_after_concurrent_accounting_processing_does_not_quarantine_receipt(self):
        receipt = self.receive()

        def processed_then_rejected(_commands, **_kwargs):
            with SQLiteUnitOfWork(self.engine) as work:
                current = work.receipts.get(receipt.id)
                work.receipts.save(replace(current, state=ReceiptState.PROCESSED,
                    processed_at=AT, reason_code="PRINTER_JOB_ACCOUNTED", updated_at=AT,
                    revision=current.revision + 1), current.revision)
                work.commit()
            raise ProjectionRejected("projection.synthetic_processed_race")

        with patch.object(JobProjectionCommands, "apply", new=processed_then_rejected):
            self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.receipts.get(receipt.id).state, ReceiptState.PROCESSED)
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(
                f"receipt:{receipt.id}:projection_rejected"))
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(self.run_key("drain-run")))

    def test_two_workers_apply_before_first_quarantine_recheck_without_false_incident(self):
        receipt = self.receive(state="completed", observed=FUTURE)
        quarantine_entered, release_quarantine = Event(), Event()
        original = ProjectionDrain._quarantine_rejected

        def pause_before_recheck(drain, receipt_id, actor_device_id, now):
            quarantine_entered.set()
            if not release_quarantine.wait(timeout=5):
                raise TimeoutError("second worker did not apply receipt")
            return original(drain, receipt_id, actor_device_id, now)

        with ThreadPoolExecutor(max_workers=1) as executor, patch.object(
                ProjectionDrain, "_quarantine_rejected", new=pause_before_recheck):
            rejected_worker = executor.submit(self.drain.run_once,
                actor_device_id=self.ids["device"], at=AT)
            self.assertTrue(quarantine_entered.wait(timeout=5))
            applied = self.drain.run_once(actor_device_id=self.ids["device"], at=FUTURE)
            release_quarantine.set()
            rejected = rejected_worker.result(timeout=5)

        self.assertEqual(applied, DrainResult(1, 0, 0, 0))
        self.assertEqual(rejected, DrainResult(0, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(receipt.id))
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(
                f"receipt:{receipt.id}:projection_rejected"))
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(
                self.run_key("drain-run")))

    def test_manual_resolution_is_scoped_audited_and_retry_requires_explicit_tasks(self):
        rejected = self.receive(state="completed", observed=FUTURE,
                                occurrence="reviewed-run")
        self.assertEqual(self.run_pass(), DrainResult(0, 0, 0, 1))
        run_key = self.run_key("reviewed-run")
        with SQLiteUnitOfWork(self.engine) as work:
            run_task = work.reconciliations.open_task_by_dedupe(run_key)
            receipt_task = work.reconciliations.open_task_by_dedupe(
                f"receipt:{rejected.id}:projection_rejected")
        resolution = ProjectionQuarantineResolution(lambda: SQLiteUnitOfWork(self.engine))
        with self.assertRaisesRegex(ValueError, "resolution_notes_invalid"):
            resolution.resolve_task(task_id=run_task.id, actor_device_id=self.ids["device"],
                                    resolution_notes=" ", at=FUTURE)
        resolved_run = resolution.resolve_task(task_id=run_task.id,
            actor_device_id=self.ids["device"], resolution_notes="Run occurrence reviewed", at=FUTURE)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.reconciliations.open_task_by_dedupe(run_key), None)
            self.assertIsNotNone(work.reconciliations.open_task_by_dedupe(
                f"receipt:{rejected.id}:projection_rejected"))
            self.assertTrue(any(event.event_code == "printer.projection_quarantine_resolved"
                                and event.entity_id == run_task.id
                                for event in work.audit.for_command(
                                    f"reconciliation:{run_task.id}:manual-resolution")))
        resolution.resolve_task(task_id=receipt_task.id, actor_device_id=self.ids["device"],
            resolution_notes="Observation clock reviewed", at=FUTURE)
        self.assertEqual(self.drain.run_once(actor_device_id=self.ids["device"], at=FUTURE),
                         DrainResult(1, 0, 0, 0))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNotNone(work.projections.by_receipt(rejected.id))
            self.assertEqual(work.reconciliations.open_task_by_dedupe(run_key), None)
            self.assertEqual(resolved_run.state, ReconciliationState.RESOLVED)
