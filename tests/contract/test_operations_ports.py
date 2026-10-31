import inspect
import unittest
from datetime import UTC, datetime

from ufm.application.dto import (
    BackupDestination,
    BackupFile,
    BackupManifest,
    BackupSource,
    Notification,
    RestoreTarget,
)
from ufm.application.ports import BackupInvalid, BackupProvider, NotificationProvider
from ufm.domain.enums import Severity
from ufm.domain.value_objects import EntityId, UtcDateTime


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 11, tzinfo=UTC))


class OperationsPortTests(unittest.TestCase):
    def test_notification_is_async_and_idempotency_key_is_explicit(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(NotificationProvider.send))
        self.assertIn("delivery_key", inspect.signature(NotificationProvider.send).parameters)
        notice = Notification("inventory.low", "Low stock", "Spool is low", Severity.WARNING)
        self.assertEqual(notice.kind, "inventory.low")

    def test_backup_locations_are_not_exposed_by_repr(self) -> None:
        for location in (
            BackupDestination("private-destination"),
            BackupSource("private-source"),
            RestoreTarget("private-target"),
        ):
            self.assertNotIn("private", repr(location))

    def test_manifest_paths_and_checksums_are_portable_and_bounded(self) -> None:
        file = BackupFile("database/ufm.sqlite3", "a" * 64, 42)
        manifest = BackupManifest(1, 1, "0.1", EntityId.new(), now(), (file,))
        self.assertEqual(manifest.files[0].length, 42)
        for path in ("../secret", "/absolute", "windows\\path"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "path_invalid"):
                BackupFile(path, "a" * 64, 1)

    def test_backup_port_separates_verify_from_restore(self) -> None:
        self.assertFalse(inspect.iscoroutinefunction(BackupProvider.verify))
        self.assertTrue(hasattr(BackupProvider, "restore"))
        self.assertEqual(str(BackupInvalid()), "backup.invalid")
