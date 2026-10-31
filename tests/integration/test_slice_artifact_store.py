"""Filesystem acceptance checks for immutable verified slice artifacts."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tests.contract.test_sliced_files import FIXTURES, archive
from ufm.integrations.slice_artifact_store import (
    MAX_MANIFEST_BYTES,
    SliceArtifactRejected,
    SliceArtifactStore,
)
from ufm.integrations.sliced_files import MAX_ARCHIVE_BYTES, SlicedFileRejected


class SliceArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ufm-artifacts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.store = SliceArtifactStore(self.cache)
        self.data = archive()
        self.digest = hashlib.sha256(self.data).hexdigest()

    def save(self):
        return self.store.store_bytes(self.data, expected_sha256=self.digest, plate=1)

    def test_restart_load_revalidates_and_retry_preserves_exact_files(self) -> None:
        saved = self.save()
        manifest = saved.archive_path.with_name("manifest.json")
        before = (saved.archive_path.stat().st_mtime_ns, manifest.read_bytes())
        restarted = SliceArtifactStore(self.cache)
        self.assertEqual(restarted.load(expected_sha256=self.digest, plate=1), saved)
        self.assertEqual(self.save(), saved)
        self.assertEqual((saved.archive_path.stat().st_mtime_ns, manifest.read_bytes()), before)
        document = json.loads(manifest.read_bytes())
        self.assertEqual(document["filaments"], [{"filament_id": 1, "logical_material": 0, "mass_mg": 1}])
        self.assertEqual(document["quantity"], "estimate")
        self.assertIsNone(document["includes_purge"])
        self.assertNotIn(str(self.root), manifest.read_text())

    def test_real_fixture_store_file_and_load(self) -> None:
        source = FIXTURES / "p2s_two_colours.gcode.3mf"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        result = self.store.store_file(source, expected_sha256=digest, plate=1)
        self.assertEqual(len(result.facts.filaments), 2)
        self.assertEqual(self.store.load(expected_sha256=digest, plate=1), result)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)

    def test_identity_rejected_before_path_creation(self) -> None:
        for digest, plate in (("../escape", 1), ("A" * 64, 1), (self.digest, 0),
                              (self.digest, True), (self.digest, 1000001), (self.digest, "1")):
            with self.subTest(digest=digest, plate=plate), self.assertRaises(SliceArtifactRejected):
                self.store.store_bytes(self.data, expected_sha256=digest, plate=plate)
        self.assertFalse(self.cache.exists())
        with self.assertRaises(SlicedFileRejected):
            self.store.store_bytes(self.data, expected_sha256="b" * 64, plate=1)
        self.assertFalse(self.cache.exists())

    def test_selected_plate_is_bound_and_parser_security_is_preserved(self) -> None:
        data = archive(extras=(("../escape", b"bad"),))
        with self.assertRaises(SlicedFileRejected):
            self.store.store_bytes(data, expected_sha256=hashlib.sha256(data).hexdigest(), plate=1)
        self.assertFalse(self.cache.exists())
        self.save()
        with self.assertRaises(SliceArtifactRejected):
            self.store.load(expected_sha256=self.digest, plate=2)

    def test_manifest_tamper_is_rejected_and_never_overwritten(self) -> None:
        saved = self.save()
        manifest = saved.archive_path.with_name("manifest.json")
        original = json.loads(manifest.read_bytes())
        for key, value in (("plate", 2), ("parser_version", "untrusted"), ("file_sha256", "b" * 64),
                           ("metadata_sha256", "c" * 64), ("gcode_sha256", "d" * 64),
                           ("filaments", []), ("includes_purge", True), ("quantity", "measurement")):
            modified = json.dumps(original | {key: value}).encode()
            manifest.write_bytes(modified)
            with self.subTest(field=key):
                with self.assertRaises(SliceArtifactRejected):
                    self.store.load(expected_sha256=self.digest, plate=1)
                with self.assertRaises(SliceArtifactRejected):
                    self.save()
                self.assertEqual(manifest.read_bytes(), modified)

    def test_archive_tamper_is_rejected_and_preserved(self) -> None:
        saved = self.save()
        saved.archive_path.write_bytes(b"tampered")
        for action in (lambda: self.store.load(expected_sha256=self.digest, plate=1), self.save):
            with self.assertRaises(SlicedFileRejected):
                action()
        self.assertEqual(saved.archive_path.read_bytes(), b"tampered")

    def test_incomplete_destination_is_never_replaced(self) -> None:
        destination = self.cache / self.digest / "1"
        destination.mkdir(parents=True)
        sentinel = destination / "sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(SliceArtifactRejected):
            self.save()
        self.assertEqual(list(destination.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_exception_before_publish_has_no_usable_partial_artifact(self) -> None:
        with patch("ufm.integrations.slice_artifact_store.os.rename", side_effect=OSError("private-path")):
            with self.assertRaisesRegex(SliceArtifactRejected, "^slice_artifact.unavailable$"):
                self.save()
        self.assertFalse((self.cache / self.digest / "1").exists())
        self.assertFalse(list((self.cache / self.digest).glob(".staging-*")))
        self.save()

    def test_process_death_leaves_only_staging_and_restart_recovers(self) -> None:
        source = self.root / "source.3mf"
        source.write_bytes(self.data)
        worker = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from ufm.integrations.slice_artifact_store import SliceArtifactStore
with patch('ufm.integrations.slice_artifact_store.os.rename', side_effect=lambda *args: os._exit(37)):
    SliceArtifactStore(Path(sys.argv[1])).store_file(Path(sys.argv[2]), expected_sha256=sys.argv[3], plate=1)
"""
        result = subprocess.run([sys.executable, "-c", worker, str(self.cache), str(source), self.digest],
                                capture_output=True, env=os.environ.copy(), timeout=20)
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertFalse((self.cache / self.digest / "1").exists())
        with self.assertRaises(SliceArtifactRejected):
            self.store.load(expected_sha256=self.digest, plate=1)
        staging = list((self.cache / self.digest).glob(".staging-*"))
        self.assertEqual(len(staging), 1)
        self.save()
        self.assertTrue(staging[0].exists())

    def test_two_writers_get_the_same_complete_artifact(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.save) for _ in range(2)]
            first, second = [future.result(timeout=20) for future in futures]
        self.assertEqual(first, second)
        self.assertEqual(self.store.load(expected_sha256=self.digest, plate=1), first)
        self.assertFalse(list((self.cache / self.digest).glob(".staging-*")))

    def test_two_processes_publish_one_complete_artifact(self) -> None:
        source = self.root / "source.3mf"
        source.write_bytes(self.data)
        worker = """
import sys
from pathlib import Path
from ufm.integrations.slice_artifact_store import SliceArtifactStore
result = SliceArtifactStore(Path(sys.argv[1])).store_file(Path(sys.argv[2]), expected_sha256=sys.argv[3], plate=1)
assert result.facts.file_sha256 == sys.argv[3]
"""
        processes = [subprocess.Popen([sys.executable, "-c", worker, str(self.cache), str(source), self.digest],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
                     for _ in range(2)]
        for process in processes:
            _out, error = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, error)
        self.assertEqual(self.store.load(expected_sha256=self.digest, plate=1).facts.file_sha256, self.digest)
        self.assertFalse(list((self.cache / self.digest).glob(".staging-*")))

    def test_current_parser_version_is_rechecked_on_load(self) -> None:
        self.save()
        with patch("ufm.integrations.sliced_files.PARSER_VERSION", "future-trusted-parser"):
            with self.assertRaisesRegex(SliceArtifactRejected, "manifest_mismatch"):
                self.store.load(expected_sha256=self.digest, plate=1)

    def test_bounded_archive_and_manifest_files_are_rejected(self) -> None:
        source = self.root / "large.3mf"
        with source.open("wb") as stream:
            stream.truncate(MAX_ARCHIVE_BYTES + 1)
        with self.assertRaisesRegex(SliceArtifactRejected, "size_invalid"):
            self.store.store_file(source, expected_sha256=self.digest, plate=1)
        saved = self.save()
        manifest = saved.archive_path.with_name("manifest.json")
        with manifest.open("wb") as stream:
            stream.truncate(MAX_MANIFEST_BYTES + 1)
        with self.assertRaisesRegex(SliceArtifactRejected, "size_invalid"):
            self.store.load(expected_sha256=self.digest, plate=1)

    def test_managed_junction_is_rejected_without_touching_target(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows junction check")
        self.cache.mkdir()
        target = self.root / "outside"
        target.mkdir()
        sentinel = target / "sentinel"
        sentinel.write_bytes(b"keep")
        junction = self.cache / self.digest
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            with self.assertRaisesRegex(SliceArtifactRejected, "path_invalid"):
                self.save()
            with self.assertRaisesRegex(SliceArtifactRejected, "path_invalid"):
                self.store.load(expected_sha256=self.digest, plate=1)
            self.assertEqual(sentinel.read_bytes(), b"keep")
        finally:
            junction.rmdir()
