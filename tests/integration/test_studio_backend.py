"""Studio actions preserve the exact ledger and its duplicate-command guard."""

import tempfile
import unittest
from pathlib import Path

from ufm.infrastructure.backup.sqlite_snapshot import verify_snapshot
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.studio_backend import StudioBackend
from ufm.platform.common.paths import AppPaths


class StudioBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.paths = AppPaths.resolve(Path(self.directory.name))
        self.paths.create()
        self.engine = create_sqlite_engine(self.paths.data / "ufm.sqlite3")
        migrate_database(self.engine)
        self.backend = StudioBackend(self.engine, self.paths)
        self.profile = self.backend.add_material("PLA Basic", "PLA")
        self.spool = self.backend.add_spool("My spool", self.profile)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.directory.cleanup()

    def test_new_spool_is_unknown_and_cannot_be_deducted(self) -> None:
        self.assertIsNone(self.backend.spools()[0].remaining_mg)
        with self.assertRaises(ValueError):
            self.backend.change_stock(self.spool, "deduct", "1", "unknown-use")
        self.assertEqual(self.backend.history(self.spool), ())

    def test_exact_deduction_replay_and_rejected_overspend(self) -> None:
        self.backend.change_stock(self.spool, "opening", "1000", "initial")
        self.backend.change_stock(self.spool, "deduct", "12,345", "same-command")
        self.backend.change_stock(self.spool, "deduct", "12.345", "same-command")
        self.assertEqual(self.backend.spools()[0].remaining_mg, 987655)
        with self.assertRaises(ValueError):
            self.backend.change_stock(self.spool, "deduct", "999", "too-much")
        with self.assertRaises(ValueError):
            self.backend.change_stock(self.spool, "add", "-5", "negative-add")
        self.assertEqual(len(self.backend.history(self.spool)), 2)
        self.assertEqual(self.backend.spools()[0].remaining_mg, 987655)

    def test_invalid_catalog_does_not_create_partial_profile(self) -> None:
        with self.assertRaises(ValueError):
            self.backend.add_material("Invalid", "PLA", "0")
        with self.assertRaises(ValueError):
            self.backend.add_material("Bad temperature", "PLA", nozzle_min_c="230",
                                      nozzle_max_c="210")
        with self.assertRaises(ValueError):
            self.backend.add_material("Bad drying duration", "PLA", drying_duration_min="-1")
        self.assertEqual(len(self.backend.materials()), 1)
        custom = self.backend.add_material("Experimental mix", "CUSTOM")
        self.assertIn(custom, [row.id for row in self.backend.materials()])

    def test_backup_contains_a_verified_database(self) -> None:
        self.backend.change_stock(self.spool, "opening", "42.001", "initial")
        bundle = self.backend.backup()
        self.assertTrue(verify_snapshot(bundle).is_file())
        self.assertEqual(self.backend.spools()[0].remaining_mg, 42001)

    def test_spool_dates_reject_expiry_before_manufacture(self) -> None:
        with self.assertRaises(ValueError):
            self.backend.add_spool(
                "Invalid dates", self.profile,
                manufactured_date="2026-03-01", expires_date="2026-02-28",
            )
        self.assertEqual(len(self.backend.spools()), 1)


if __name__ == "__main__":
    unittest.main()
