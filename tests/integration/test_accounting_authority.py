"""Isolated SQLite checks for the operator-controlled accounting cutover."""

import tempfile
import unittest
from pathlib import Path

from tests.integration.test_print_finalization import BASE, create_scope
from ufm.application.accounting_authority import (
    AccountingAuthorityRejected,
    PrinterAccountingAuthorityCommands,
)
from ufm.application.ports.persistence import IdempotencyConflict, RevisionConflict
from ufm.domain.enums import PrinterAccountingMode
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class AccountingAuthorityCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ufm-authority-cutover-")
        self.addCleanup(self.temp.cleanup)
        self.engine = create_sqlite_engine(Path(self.temp.name) / "fixture.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.ids = create_scope(self.engine)
        self.commands = PrinterAccountingAuthorityCommands(
            lambda: SQLiteUnitOfWork(self.engine)
        )
        self.snapshot = "a" * 64
        self.active_key = f"authority-active:{self.ids['printer']}"

    def authority(self):
        with SQLiteUnitOfWork(self.engine) as work:
            return work.printer_accounting_authorities.for_printer(self.ids["printer"])

    def events(self, command_key: str):
        with SQLiteUnitOfWork(self.engine) as work:
            return work.audit.for_command(command_key)

    def test_exact_retry_returns_original_revision_without_duplicate_audit(self) -> None:
        original = self.authority()
        replay = self.commands.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.UFM_ACTIVE,
            actor_device_id=self.ids["device"],
            command_key=self.active_key,
            expected_revision=2,
            snapshot_sha256=self.snapshot,
            legacy_writer_disabled_at=BASE,
            reconciled_at=BASE,
            at=BASE,
        )

        self.assertEqual(replay.id, original.id)
        self.assertEqual(replay.revision, original.revision)
        self.assertEqual(replay.mode, PrinterAccountingMode.UFM_ACTIVE)
        self.assertEqual(len(self.events(self.active_key)), 1)

    def test_reusing_command_key_for_changed_payload_conflicts_without_mutation(self) -> None:
        before = self.authority()
        with self.assertRaises(IdempotencyConflict):
            self.commands.transition(
                printer_id=self.ids["printer"],
                mode=PrinterAccountingMode.REVIEW_ONLY,
                actor_device_id=self.ids["device"],
                command_key=self.active_key,
                expected_revision=2,
                at=BASE,
            )

        after = self.authority()
        self.assertEqual((after.revision, after.mode), (before.revision, before.mode))
        self.assertEqual(len(self.events(self.active_key)), 1)

    def test_stale_revision_rejects_without_audit_write(self) -> None:
        key = "authority-stale-revision"
        with self.assertRaises(RevisionConflict):
            self.commands.transition(
                printer_id=self.ids["printer"],
                mode=PrinterAccountingMode.REVIEW_ONLY,
                actor_device_id=self.ids["device"],
                command_key=key,
                expected_revision=2,
                at=BASE,
            )

        self.assertEqual(self.authority().revision, 3)
        self.assertEqual(self.events(key), [])

    def test_cutover_requires_snapshot_and_both_attestations(self) -> None:
        self.commands.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.REVIEW_ONLY,
            actor_device_id=self.ids["device"],
            command_key="authority-return-to-review",
            expected_revision=3,
            at=BASE,
        )
        self.commands.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.LEGACY_ACTIVE,
            actor_device_id=self.ids["device"],
            command_key="authority-legacy-again",
            expected_revision=4,
            at=BASE,
        )
        with self.assertRaisesRegex(
            AccountingAuthorityRejected, "accounting_authority.cutover_evidence_required"
        ):
            self.commands.transition(
                printer_id=self.ids["printer"],
                mode=PrinterAccountingMode.CUTOVER_READY,
                actor_device_id=self.ids["device"],
                command_key="authority-cutover-missing-time",
                expected_revision=5,
                snapshot_sha256=self.snapshot,
                legacy_writer_disabled_at=BASE,
                at=BASE,
            )

        current = self.authority()
        self.assertEqual((current.revision, current.mode), (5, PrinterAccountingMode.LEGACY_ACTIVE))
        self.assertEqual(self.events("authority-cutover-missing-time"), [])

    def test_active_transition_requires_exact_cutover_evidence(self) -> None:
        self.commands.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.REVIEW_ONLY,
            actor_device_id=self.ids["device"],
            command_key="authority-return-to-review",
            expected_revision=3,
            at=BASE,
        )
        self.commands.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.LEGACY_ACTIVE,
            actor_device_id=self.ids["device"],
            command_key="authority-legacy-again",
            expected_revision=4,
            at=BASE,
        )
        self.commands.transition(
            printer_id=self.ids["printer"],
            mode=PrinterAccountingMode.CUTOVER_READY,
            actor_device_id=self.ids["device"],
            command_key="authority-cutover-again",
            expected_revision=5,
            snapshot_sha256=self.snapshot,
            legacy_writer_disabled_at=BASE,
            reconciled_at=BASE,
            at=BASE,
        )
        with self.assertRaisesRegex(
            AccountingAuthorityRejected, "accounting_authority.cutover_evidence_mismatch"
        ):
            self.commands.transition(
                printer_id=self.ids["printer"],
                mode=PrinterAccountingMode.UFM_ACTIVE,
                actor_device_id=self.ids["device"],
                command_key="authority-active-mismatched-snapshot",
                expected_revision=6,
                snapshot_sha256="b" * 64,
                legacy_writer_disabled_at=BASE,
                reconciled_at=BASE,
                at=BASE,
            )

        current = self.authority()
        self.assertEqual((current.revision, current.mode), (6, PrinterAccountingMode.CUTOVER_READY))
        self.assertEqual(self.events("authority-active-mismatched-snapshot"), [])


if __name__ == "__main__":
    unittest.main()
