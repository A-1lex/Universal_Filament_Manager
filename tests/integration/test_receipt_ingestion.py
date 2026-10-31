"""Durable event intake must deduplicate, preserve scope and leave stock alone."""

import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from unittest.mock import patch as mock_patch

from sqlalchemy import select

from tests.integration.test_print_finalization import AT, END, create_scope
from ufm.application.ports.persistence import IdempotencyConflict, PersistenceError
from ufm.application.receipt_ingestion import (
    ReceiptIngestion,
    ReceiptRejected,
    receipt_conflict_key,
)
from ufm.domain.enums import ReceiptState, ReconciliationState
from ufm.domain.value_objects import EntityId
from ufm.infrastructure.persistence.models import ledger as l
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


def create_receipt_conflict(engine, ids):
    """Persist an incident against an existing receipt through the public intake."""
    with SQLiteUnitOfWork(engine) as work:
        original = work.receipts.get(ids["receipt"])
    message = {"v": 1, "kind": "job", "request_id": "conflict-probe",
               "printer_id": str(ids["printer"]), "source_epoch": original.source_epoch,
               "sequence": 1, "observed_at": END.value.isoformat(),
               "occurrence_key": "run-1", "state": "completed",
               "file_sha256": "a" * 64, "completed_layers": 10}
    try:
        ReceiptIngestion(lambda: SQLiteUnitOfWork(engine)).ingest(
            provider_instance_id=original.provider_instance_id, printer_id=ids["printer"],
            actor_device_id=ids["device"], event_key=original.event_key,
            raw_payload=b"conflicting-event", normalized_payload=json.dumps(message).encode(),
            received_at=AT)
    except IdempotencyConflict:
        return
    raise AssertionError("conflicting receipt was unexpectedly accepted")


def create_lifecycle_conflict(engine, ids):
    """A different receipt on the same run must block the original terminal debit."""
    from ufm.application.job_projection import JobProjectionCommands
    with SQLiteUnitOfWork(engine) as work:
        original = work.receipts.get(ids["receipt"])
    message = {"v": 1, "kind": "job", "request_id": "separate-conflict",
               "printer_id": str(ids["printer"]), "source_epoch": original.source_epoch,
               "sequence": 2, "observed_at": END.value.isoformat(),
               "occurrence_key": "run-1", "state": "running"}
    payload = json.dumps(message).encode()
    receipt = ReceiptIngestion(lambda: SQLiteUnitOfWork(engine)).ingest(
        provider_instance_id=original.provider_instance_id, printer_id=ids["printer"],
        actor_device_id=ids["device"], event_key="separate-lifecycle-conflict",
        raw_payload=payload, normalized_payload=payload, received_at=AT)
    marker = JobProjectionCommands(lambda: SQLiteUnitOfWork(engine)).apply(
        receipt_id=receipt.id, actor_device_id=ids["device"], at=AT)
    assert marker.outcome == "CONFLICT"
    assert marker.print_job_id == ids["job"]


def quarantine_receipt(engine, ids):
    from ufm.application.job_conflicts import projection_rejection_key
    from ufm.domain.entities import ReconciliationTask
    from ufm.domain.enums import Severity
    with SQLiteUnitOfWork(engine) as work:
        work.reconciliations.add_task(ReconciliationTask(
            id=EntityId.new(), device_id=ids["device"], created_at=AT, updated_at=AT,
            revision=1, reason_code="PROJECTION_OBSERVATION_REJECTED", severity=Severity.ERROR,
            state=ReconciliationState.OPEN, dedupe_key=projection_rejection_key(ids["receipt"]),
            suggested_action="review_projection_observation"))
        work.commit()


def create_run_quarantine(engine, ids):
    """Reject one future observation on the exact run already attached to a job."""
    from ufm.application.job_conflicts import run_quarantine_key_for_scope
    from ufm.application.projection_drain import DrainResult, ProjectionDrain
    from ufm.domain.value_objects import UtcDateTime

    with SQLiteUnitOfWork(engine) as work:
        original = work.receipts.get(ids["receipt"])
    observed = UtcDateTime.parse("2026-10-27T12:30:00.000000Z")
    message = {"v": 1, "kind": "job", "request_id": "run-quarantine-probe",
        "printer_id": str(ids["printer"]), "source_epoch": original.source_epoch,
        "sequence": 20, "observed_at": observed.value.isoformat(),
        "occurrence_key": "run-1", "state": "completed"}
    payload = json.dumps(message).encode()
    receipt = ReceiptIngestion(lambda: SQLiteUnitOfWork(engine)).ingest(
        provider_instance_id=original.provider_instance_id, printer_id=ids["printer"],
        actor_device_id=ids["device"], event_key="run-quarantine-terminal",
        raw_payload=payload, normalized_payload=payload, received_at=AT)
    result = ProjectionDrain(lambda: SQLiteUnitOfWork(engine)).run_once(
        actor_device_id=ids["device"], at=AT)
    assert result == DrainResult(0, 0, 0, 1)
    key = run_quarantine_key_for_scope(original.provider_instance_id, ids["printer"],
        "PRINTER", original.source_epoch, "run-1")
    with SQLiteUnitOfWork(engine) as work:
        task = work.reconciliations.open_task_by_dedupe(key)
        assert task is not None and task.print_job_id == ids["job"]
    return receipt, key


class ReceiptIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ufm-receipts-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "events.sqlite3"
        self.engine = create_sqlite_engine(self.path)
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine, with_evidence=False)
        self.ingestion = ReceiptIngestion(lambda: SQLiteUnitOfWork(self.engine))
        self.raw = b'{"private_access_code":"never-store-this-secret"}'
        self.message = {"v": 1, "kind": "job", "request_id": "request-1",
                        "printer_id": str(self.ids["printer"]), "source_epoch": "epoch-1",
                        "sequence": 1, "observed_at": "2026-10-26T12:30:00Z",
                        "occurrence_key": "run-1", "state": "completed",
                        "file_sha256": "a" * 64, "completed_layers": 10}

    def parameters(self, *, patch=None, **changes):
        return {"provider_instance_id": self.ids["provider"], "printer_id": self.ids["printer"],
                "actor_device_id": self.ids["device"], "event_key": "queue-event",
                "raw_payload": self.raw, "normalized_payload": json.dumps({**self.message, **(patch or {})}).encode(),
                "received_at": END, **changes}

    def test_restart_redelivery_and_pending_preserve_first_facts_without_stock_mutation(self) -> None:
        receipt = self.ingestion.ingest(**self.parameters())
        reopened = ReceiptIngestion(lambda: SQLiteUnitOfWork(self.engine))
        replay = reopened.ingest(**self.parameters(patch={"request_id": "request-2", "sequence": 20,
            "observed_at": "2026-10-26T12:31:00Z"}, received_at=AT))
        self.assertEqual(replay, receipt)
        self.assertIn(receipt, reopened.pending())
        self.assertEqual(receipt.event_type, "PRINT_COMPLETED")
        self.assertEqual(receipt.payload_hash, hashlib.sha256(self.raw).hexdigest())
        self.assertNotIn("never-store-this-secret", receipt.sanitized_metadata)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.spools.get(self.ids["spool"]).effective_remaining.milligrams, 1000000)
            self.assertEqual(len(work.ledger.for_spool(self.ids["spool"])), 1)

    def test_printer_reported_material_mapping_is_durable_receipt_metadata(self) -> None:
        mappings = [
            {"logical_material": 5, "disposition": "reported_slot",
             "provider_system_key": "ams:0", "provider_slot_key": "0:3"},
            {"logical_material": 6, "disposition": "unused"},
        ]
        receipt = self.ingestion.ingest(**self.parameters(
            patch={"material_slot_mappings": mappings},
        ))
        with SQLiteUnitOfWork(self.engine) as work:
            reopened = work.receipts.get(receipt.id)
            spool = work.spools.get(self.ids["spool"])
            history = work.ledger.for_spool(self.ids["spool"])
        stored_mappings = json.loads(reopened.sanitized_metadata)["material_slot_mappings"]
        self.assertEqual(len(stored_mappings), 2)
        self.assertEqual(stored_mappings[0]["provider_slot_key"], "0:3")
        self.assertEqual(stored_mappings[1]["disposition"], "unused")
        self.assertIsNone(stored_mappings[1]["provider_slot_key"])
        self.assertEqual(spool.effective_remaining.milligrams, 1_000_000)
        self.assertEqual(len(history), 1)

    def test_same_identity_changed_raw_or_semantic_facts_is_conflict(self) -> None:
        original = self.ingestion.ingest(**self.parameters())
        for arguments in (self.parameters(raw_payload=b"changed"), self.parameters(patch={"state": "failed"}),
                          self.parameters(patch={"occurrence_key": "foreign-run"})):
            with self.subTest(arguments=arguments), self.assertRaises(IdempotencyConflict):
                self.ingestion.ingest(**arguments)
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertEqual(work.receipts.get(original.id), original)
            task = work.reconciliations.open_task_by_dedupe(receipt_conflict_key(original.id))
            self.assertEqual(task.reason_code, "RECEIPT_IDENTITY_PAYLOAD_CONFLICT")
            self.assertEqual(task.state, ReconciliationState.OPEN)
            self.assertIsNone(task.spool_id)
            self.assertEqual(work.spools.get(self.ids["spool"]).effective_remaining.milligrams, 1000000)
        with self.engine.connect() as connection:
            rows = connection.execute(select(l.reconciliation_task)).all()
            self.assertEqual(len(rows), 1)
            self.assertNotIn("never-store-this-secret", str(rows))

    def test_conflict_task_commit_failure_is_not_hidden(self) -> None:
        original = self.ingestion.ingest(**self.parameters())
        with mock_patch.object(SQLiteUnitOfWork, "commit", side_effect=RuntimeError("commit failure")):
            with self.assertRaisesRegex(RuntimeError, "commit failure"):
                self.ingestion.ingest(**self.parameters(raw_payload=b"changed"))
        with SQLiteUnitOfWork(self.engine) as work:
            self.assertIsNone(work.reconciliations.open_task_by_dedupe(receipt_conflict_key(original.id)))
            self.assertEqual(work.receipts.get(original.id), original)

    def test_parallel_conflicts_keep_one_open_incident_after_restart(self) -> None:
        receipt = self.ingestion.ingest(**self.parameters())
        barrier = Barrier(2)
        def conflict(_):
            barrier.wait(timeout=5)
            with self.assertRaises(IdempotencyConflict):
                self.ingestion.ingest(**self.parameters(raw_payload=b"changed"))
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(conflict, range(2)))
        reopened = create_sqlite_engine(self.path)
        try:
            with SQLiteUnitOfWork(reopened) as work:
                self.assertIsNotNone(work.reconciliations.open_task_by_dedupe(receipt_conflict_key(receipt.id)))
                self.assertEqual(work.receipts.get(receipt.id), receipt)
            with reopened.connect() as connection:
                self.assertEqual(len(connection.execute(select(l.reconciliation_task)).all()), 1)
        finally:
            reopened.dispose()

    def test_epoch_and_provider_are_distinct_scopes(self) -> None:
        first = self.ingestion.ingest(**self.parameters())
        second = self.ingestion.ingest(**self.parameters(patch={"source_epoch": "epoch-2"}))
        third = self.ingestion.ingest(**self.parameters(provider_instance_id=EntityId.new()))
        self.assertEqual(len({first.id, second.id, third.id}), 3)

    def test_wrong_scope_unknown_fields_and_forged_outcome_are_rejected(self) -> None:
        for patch in ({"printer_id": str(EntityId.new())}, {"access_code": "secret"},
                      {"kind": "finalization_outcome"}, {"v": True}):
            with self.subTest(patch=patch), self.assertRaises(ReceiptRejected):
                self.ingestion.ingest(**self.parameters(patch=patch))
        for raw in (b"", b"x" * (512 * 1024 + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(ReceiptRejected):
                self.ingestion.ingest(**self.parameters(raw_payload=raw))

    def test_processed_redelivery_does_not_reopen_receipt(self) -> None:
        receipt = self.ingestion.ingest(**self.parameters())
        with SQLiteUnitOfWork(self.engine) as work:
            processed = replace(receipt, state=ReceiptState.PROCESSED, processed_at=AT,
                                updated_at=AT, revision=2, reason_code="STATUS_HANDLED")
            work.receipts.save(processed, 1)
            work.commit()
        self.assertEqual(self.ingestion.ingest(**self.parameters()), processed)
        self.assertNotIn(processed.id, {item.id for item in self.ingestion.pending()})

    def test_saved_identity_cannot_be_rewritten_and_pending_limit_is_bounded(self) -> None:
        receipt = self.ingestion.ingest(**self.parameters())
        for patch in ({"payload_hash": "b" * 64}, {"event_key": "different"},
                      {"sanitized_metadata": "{}"}):
            with self.subTest(patch=patch), self.assertRaises(PersistenceError), SQLiteUnitOfWork(self.engine) as work:
                work.receipts.save(replace(receipt, **patch, revision=2), 1)
                work.commit()
        self.assertEqual(len(self.ingestion.pending(1)), 1)
        for limit in (0, 501, True):
            with self.subTest(limit=limit), self.assertRaises(PersistenceError):
                self.ingestion.pending(limit)

    def test_two_intake_writers_commit_only_one_receipt(self) -> None:
        barrier = Barrier(2)

        def ingest():
            barrier.wait(timeout=5)
            return self.ingestion.ingest(**self.parameters())

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(ingest) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(sum(item.event_key == "queue-event" for item in self.ingestion.pending()), 1)
