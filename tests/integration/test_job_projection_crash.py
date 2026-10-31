"""Process-boundary recovery and a non-starving observation projection queue."""

import subprocess
import sys
import unittest
from dataclasses import replace

from tests.integration import test_job_projection as fixture
from tests.integration.test_receipt_ingestion import create_receipt_conflict
from ufm.application.ports.persistence import PersistenceError
from ufm.application.receipt_ingestion import receipt_conflict_key
from ufm.domain.enums import ReconciliationState
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class JobProjectionCrashTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.JobProjectionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_process_death_before_after_projection_commit_recovers_one_application(self):
        f = self.f
        receipt = f.receive()
        script = '''
import os,sys
from pathlib import Path
from ufm.application.job_projection import JobProjectionCommands
from ufm.domain.value_objects import EntityId,UtcDateTime
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
engine=create_sqlite_engine(Path(sys.argv[1]))
original=SQLiteUnitOfWork.commit
def crash(work):
    if sys.argv[2]=="after": original(work)
    os._exit(39)
SQLiteUnitOfWork.commit=crash
JobProjectionCommands(lambda:SQLiteUnitOfWork(engine)).apply(
    receipt_id=EntityId.parse(sys.argv[3]),actor_device_id=EntityId.parse(sys.argv[4]),
    at=UtcDateTime.parse("2026-10-26T12:31:00.000000Z"))
'''
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                before = f.rows(tuple(s.metadata.tables))
                result = subprocess.run([sys.executable, "-c", script, str(f.path), boundary,
                                         str(receipt.id), str(f.ids["device"])],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 39, result.stderr)
                if boundary == "before":
                    self.assertEqual(f.rows(tuple(s.metadata.tables)), before)
                else:
                    committed = f.rows(tuple(s.metadata.tables))
                    marker = f.apply(receipt)
                    self.assertEqual(f.rows(tuple(s.metadata.tables)), committed)
                    with SQLiteUnitOfWork(f.engine) as work:
                        self.assertEqual(work.projections.by_receipt(receipt.id), marker)

    def test_queue_skips_blocked_receipt_until_explicit_resolution(self):
        f = self.f
        blocked = f.receive()
        create_receipt_conflict(f.engine, f.ids | {"receipt": blocked.id})
        following = f.receive(occurrence="next-unblocked")
        self.assertEqual([item.id for item in f.commands.pending(1)], [following.id])
        with SQLiteUnitOfWork(f.engine) as work:
            task = work.reconciliations.open_task_by_dedupe(receipt_conflict_key(blocked.id))
            work.reconciliations.save_task(replace(task, state=ReconciliationState.RESOLVED,
                resolved_at=fixture.AT, resolved_by=f.ids["device"], resolution_notes="Explicit fixture review",
                revision=task.revision + 1, updated_at=fixture.AT), task.revision)
            work.commit()
        self.assertIn(blocked.id, {item.id for item in f.commands.pending()})
        for limit in (0, 501, True):
            with self.subTest(limit=limit), self.assertRaises(PersistenceError):
                f.commands.pending(limit)

    def test_terminal_cursor_cannot_be_rewritten_through_repository(self):
        f = self.f
        marker = f.apply(f.receive())
        f.apply(f.receive("completed", observed_at=fixture.END, sequence=2, layers=10))
        with SQLiteUnitOfWork(f.engine) as work:
            state = work.projections.for_job(marker.print_job_id)
        with self.assertRaises(PersistenceError), SQLiteUnitOfWork(f.engine) as work:
            work.projections.save_state(replace(state, completed_layers=9, revision=state.revision + 1), state.revision)
            work.commit()
        with SQLiteUnitOfWork(f.engine) as work:
            self.assertEqual(work.projections.for_job(marker.print_job_id), state)
