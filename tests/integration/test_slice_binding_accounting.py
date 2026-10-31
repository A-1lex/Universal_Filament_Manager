"""Persistent verified source → canonical Node → atomic ledger, after restart."""

import shutil
import unittest
from pathlib import Path

from tests.integration import test_calculated_finalization as fixture
from ufm.application.slice_binding import VerifiedSliceBindings
from ufm.domain.value_objects import Mass
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.slice_artifact_store import SliceArtifactStore


class PersistentSliceAccountingTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(shutil.which("node"), "Node developer runtime unavailable")
    async def test_cached_bound_file_finalizes_after_selected_source_is_deleted(self):
        f = fixture.CalculatedFinalizationTests()
        f.setUp()
        self.addCleanup(f.temp.cleanup)
        self.addCleanup(f.engine.dispose)
        cache = Path(f.temp.name) / "verified-artifacts"
        bindings = VerifiedSliceBindings(lambda: SQLiteUnitOfWork(f.engine), SliceArtifactStore(cache))
        bound = bindings.bind_local(job_id=f.ids["job"], source_path=f.path,
            expected_sha256=f.facts.file_sha256, plate=1, actor_device_id=f.ids["device"], at=fixture.AT)
        f.path.unlink()
        reopened = VerifiedSliceBindings(lambda: SQLiteUnitOfWork(f.engine), SliceArtifactStore(cache))
        resolved = reopened.resolve(job_id=f.ids["job"])
        self.assertEqual(resolved, bound)
        parameters = f.parameters(file_path=resolved.archive_path)
        record = await f.commands().finalize(**parameters)
        before = f.snapshot()
        self.assertEqual(await f.commands().finalize(**parameters), record)
        self.assertEqual(f.snapshot(), before)
        with SQLiteUnitOfWork(f.engine) as work:
            entry, = work.ledger.for_command(record.idempotency_key)
            self.assertEqual((entry.delta, entry.description), (Mass(-12345), fixture.LABEL))
            self.assertEqual(work.spools.get(f.ids["spool"]).effective_remaining, Mass(987655))
