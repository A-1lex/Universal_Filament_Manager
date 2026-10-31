"""Verified local files bind durably without creating consumption or physical facts."""

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from tests.contract.test_sliced_files import FILAMENT, archive, plate_xml
from tests.integration.test_print_finalization import AT, create_scope
from ufm.application.ports.persistence import IdempotencyConflict
from ufm.application.slice_binding import SliceBindingRejected, VerifiedSliceBindings
from ufm.domain.enums import FinalizationState
from ufm.domain.value_objects import EntityId
from ufm.infrastructure.persistence.models import schema as s
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.slice_artifact_store import SliceArtifactStore


class SliceBindingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ufm-slice-binding-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "binding.sqlite3"
        self.engine = create_sqlite_engine(self.path)
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine, with_evidence=False)
        self.store = SliceArtifactStore(self.root / "cache")
        self.commands = VerifiedSliceBindings(lambda: SQLiteUnitOfWork(self.engine), self.store)
        self.source = self.root / "private-project.3mf"
        data = archive("<config>" + plate_xml() + plate_xml(2,
            FILAMENT.replace("0.0005", "2.5")) + "</config>",
            (("Metadata/plate_2.gcode", b"G90\nM83\nG1 E2\n"),))
        self.source.write_bytes(data)
        self.digest = hashlib.sha256(data).hexdigest()

    def parameters(self, **changes):
        return {"job_id": self.ids["job"], "source_path": self.source,
                "expected_sha256": self.digest, "plate": 1,
                "actor_device_id": self.ids["device"], "manual_confirmation": True,
                "at": AT, **changes}

    def snapshot(self, names):
        with self.engine.connect() as connection:
            return {name: tuple(connection.execute(select(s.metadata.tables[name]).order_by(
                s.metadata.tables[name].c.id)).all()) for name in names}

    def job(self):
        with SQLiteUnitOfWork(self.engine) as work:
            return work.jobs.get(self.ids["job"])

    def change_job(self, **changes):
        with SQLiteUnitOfWork(self.engine) as work:
            original = work.jobs.get(self.ids["job"])
            work.jobs.save(replace(original, revision=original.revision + 1,
                updated_at=AT, **changes), original.revision)
            work.commit()

    def audit(self):
        with SQLiteUnitOfWork(self.engine) as work:
            return work.audit.for_command(f"job:{self.ids['job']}:slice_binding")

    def test_unknown_identity_requires_explicit_confirmation_and_writes_nothing(self):
        before = self.snapshot(("print_job", "audit_event"))
        with self.assertRaises(SliceBindingRejected):
            self.commands.bind_local(**self.parameters(manual_confirmation=False))
        self.assertEqual(self.snapshot(tuple(before)), before)
        with self.assertRaises(SliceBindingRejected):
            self.commands.resolve(job_id=self.ids["job"])

    def test_manual_binding_has_one_proof_and_changes_no_financial_or_physical_facts(self):
        financial = ("spool", "filament_transaction", "reservation", "print_job_material",
                     "material_usage_segment", "consumption_evidence", "consumption_decision",
                     "finalization_record", "external_event_receipt")
        before = self.snapshot(financial)
        original = self.job()
        bound = self.commands.bind_local(**self.parameters())
        self.assertEqual(bound.job_id, self.ids["job"])
        self.assertEqual(bound.facts.file_sha256, self.digest)
        self.assertEqual(bound.facts.plate, 1)
        self.assertEqual(bound.facts.filaments[0].mass_mg, 1)
        self.assertTrue(bound.archive_path.is_file())
        self.assertNotEqual(bound.archive_path, self.source)
        job = self.job()
        self.assertEqual(job.file_hash, self.digest)
        self.assertEqual(job.plate_name, "1")
        for field in ("started_at", "completed_at", "failed_at", "cancelled_at", "current_layer",
                      "total_layers", "status", "finalization_state"):
            self.assertEqual(getattr(job, field), getattr(original, field), field)
        proofs = self.audit()
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0].id, bound.binding_id)
        self.assertEqual(proofs[0].event_code, "print.slice_bound")
        for digest in (bound.facts.file_sha256, bound.facts.metadata_sha256,
                       bound.facts.gcode_sha256, bound.facts.parser_version):
            self.assertIn(digest, proofs[0].parameters_json)
        self.assertEqual(self.snapshot(financial), before)

    def test_known_matching_identity_binds_without_manual_confirmation(self):
        self.change_job(file_hash=self.digest, plate_name="2")
        bound = self.commands.bind_local(**self.parameters(plate=2, manual_confirmation=False))
        self.assertEqual(bound.facts.plate, 2)
        self.assertEqual(bound.facts.filaments[0].mass_mg, 2500)

    def test_known_hash_or_plate_mismatch_cannot_be_overridden_manually(self):
        for changes in ({"file_hash": "c" * 64, "plate_name": "1"},
                        {"file_hash": self.digest, "plate_name": "2"}):
            with self.subTest(changes=changes):
                self.change_job(**changes)
                before = self.snapshot(("print_job", "audit_event"))
                with self.assertRaises(SliceBindingRejected):
                    self.commands.bind_local(**self.parameters())
                self.assertEqual(self.snapshot(tuple(before)), before)

    def test_reopen_replay_and_resolve_work_after_original_source_disappears(self):
        bound = self.commands.bind_local(**self.parameters())
        self.source.unlink()
        reopened = create_sqlite_engine(self.path)
        try:
            commands = VerifiedSliceBindings(lambda: SQLiteUnitOfWork(reopened),
                SliceArtifactStore(self.root / "cache"))
            self.assertEqual(commands.bind_local(**self.parameters()), bound)
            self.assertEqual(commands.resolve(job_id=self.ids["job"]), bound)
        finally:
            reopened.dispose()
        self.assertEqual(len(self.audit()), 1)

    def test_changed_binding_actor_hash_plate_or_confirmation_is_idempotency_conflict(self):
        self.commands.bind_local(**self.parameters())
        before = self.snapshot(("print_job", "audit_event"))
        for changes in ({"actor_device_id": EntityId.new()}, {"expected_sha256": "c" * 64},
                        {"plate": 2}, {"manual_confirmation": False}):
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                self.commands.bind_local(**self.parameters(**changes))
        self.assertEqual(self.snapshot(tuple(before)), before)

    def test_finalized_job_cannot_get_new_binding(self):
        self.change_job(finalization_state=FinalizationState.FINALIZED)
        before = self.snapshot(("print_job", "audit_event"))
        with self.assertRaises(SliceBindingRejected):
            self.commands.bind_local(**self.parameters())
        self.assertEqual(self.snapshot(tuple(before)), before)

    def test_resolve_rejects_job_identity_changes_and_corrupt_cached_archive(self):
        bound = self.commands.bind_local(**self.parameters())
        self.change_job(file_hash="c" * 64)
        with self.assertRaises(SliceBindingRejected):
            self.commands.resolve(job_id=self.ids["job"])
        self.change_job(file_hash=self.digest)
        bound.archive_path.write_bytes(b"corrupted archive")
        with self.assertRaises(SliceBindingRejected):
            self.commands.resolve(job_id=self.ids["job"])
        self.assertEqual(len(self.audit()), 1)

    def test_job_revision_race_during_store_is_detected_without_binding_writes(self):
        original_store = self.store.store_file

        def store_with_concurrent_writer(*args, **kwargs):
            stored = original_store(*args, **kwargs)
            self.change_job(name="Updated while artifact was parsed")
            return stored

        with patch.object(self.store, "store_file", side_effect=store_with_concurrent_writer):
            with self.assertRaises(IdempotencyConflict):
                self.commands.bind_local(**self.parameters())
        job = self.job()
        self.assertEqual(job.name, "Updated while artifact was parsed")
        self.assertIsNone(job.file_hash)
        self.assertIsNone(job.plate_name)
        self.assertEqual(self.audit(), [])

    def test_failed_commit_rolls_back_job_and_proof_but_cache_can_be_reused(self):
        before = self.snapshot(("print_job", "audit_event"))
        with patch.object(SQLiteUnitOfWork, "commit", side_effect=RuntimeError("binding commit failure")):
            with self.assertRaisesRegex(RuntimeError, "binding commit failure"):
                self.commands.bind_local(**self.parameters())
        self.assertEqual(self.snapshot(tuple(before)), before)
        bound = self.commands.bind_local(**self.parameters())
        self.assertEqual(bound.facts.file_sha256, self.digest)
        self.assertEqual(len(self.audit()), 1)
