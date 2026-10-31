"""Cross-receipt run keys isolate physical scopes without leaking source text."""

import unittest
from dataclasses import replace

from ufm.application.job_conflicts import run_quarantine_key
from ufm.domain.entities import JobIdentityAlias
from ufm.domain.value_objects import EntityId, UtcDateTime


class RunQuarantineKeyTests(unittest.TestCase):
    def setUp(self):
        self.alias = JobIdentityAlias(id=EntityId.new(), device_id=EntityId.new(),
            created_at=UtcDateTime.parse("2026-10-28T00:00:00.000000Z"),
            print_job_id=EntityId.new(), provider_instance_id=EntityId.new(), printer_id=EntityId.new(),
            source_type="PRINTER", source_epoch="private-source-epoch", occurrence_key="private-run-key")

    def test_key_ignores_storage_and_file_details_and_hides_occurrence(self):
        key = run_quarantine_key(self.alias)
        self.assertRegex(key, r"^run:[0-9a-f]{64}:projection_rejected$")
        self.assertNotIn("private", key)
        self.assertEqual(key, run_quarantine_key(replace(self.alias,
            id=EntityId.new(), print_job_id=EntityId.new(), file_hash="a" * 64)))

    def test_each_source_scope_dimension_is_independent(self):
        for patch in ({"provider_instance_id": EntityId.new()}, {"printer_id": EntityId.new()},
                      {"source_type": "OTHER"}, {"source_epoch": "other"}, {"occurrence_key": "other"}):
            with self.subTest(patch=patch):
                self.assertNotEqual(run_quarantine_key(self.alias), run_quarantine_key(replace(self.alias, **patch)))
