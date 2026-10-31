import inspect
import unittest

from ufm.application.ports import (
    FinalizationRepository,
    IdempotencyConflict,
    LedgerRepository,
    MountRepository,
    PersistenceUnavailable,
    ReceiptRepository,
    SpoolRepository,
    UnitOfWork,
)


class PersistencePortTests(unittest.TestCase):
    def test_critical_repositories_expose_no_delete_operation(self) -> None:
        for repository in (
            LedgerRepository,
            FinalizationRepository,
            ReceiptRepository,
            MountRepository,
        ):
            with self.subTest(repository=repository.__name__):
                self.assertFalse(hasattr(repository, "delete"))

    def test_ledger_is_append_only_and_spool_save_requires_revision(self) -> None:
        self.assertTrue(hasattr(LedgerRepository, "append"))
        self.assertFalse(hasattr(LedgerRepository, "save"))
        parameters = inspect.signature(SpoolRepository.save).parameters
        self.assertIn("expected_revision", parameters)

    def test_uow_owns_all_accounting_repositories_and_explicit_commit(self) -> None:
        annotations = inspect.get_annotations(UnitOfWork)
        for name in (
            "spools", "ledger", "mounts", "reservations", "jobs", "evidence",
            "decisions", "receipts", "finalizations", "reconciliations", "audit",
        ):
            self.assertIn(name, annotations)
        self.assertTrue(hasattr(UnitOfWork, "commit"))
        self.assertTrue(hasattr(UnitOfWork, "rollback"))

    def test_persistence_errors_have_stable_sanitized_codes(self) -> None:
        self.assertEqual(str(IdempotencyConflict()), "persistence.idempotency_conflict")
        self.assertEqual(str(PersistenceUnavailable()), "persistence.unavailable")
