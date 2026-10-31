import inspect
import unittest

from ufm.application.dto import SyncBatch, SyncChange, SyncConflict, SyncResult
from ufm.application.ports import (
    AuthenticationFailed,
    InvalidObservation,
    ProviderUnavailable,
    SyncProvider,
    UnsupportedCapability,
)
from ufm.domain.value_objects import EntityId


class SyncAndProviderErrorContractTests(unittest.TestCase):
    def test_sync_port_exists_but_has_only_exchange_authority(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(SyncProvider.exchange))
        self.assertFalse(hasattr(SyncProvider, "enable"))
        self.assertFalse(hasattr(SyncProvider, "resolve_conflict"))

    def test_sync_payload_is_hidden_and_bounded(self) -> None:
        change = SyncChange(
            EntityId.new(), "spool", EntityId.new(), 1, 2, "sha256:abc", b"private-change",
        )
        self.assertNotIn("private-change", repr(change))
        batch = SyncBatch(EntityId.new(), EntityId.new(), None, (change,))
        self.assertEqual(batch.changes, (change,))
        with self.assertRaisesRegex(ValueError, "new_revision_invalid"):
            SyncChange(EntityId.new(), "spool", EntityId.new(), 2, 2, "sha256:abc", b"x")

    def test_one_change_cannot_be_both_accepted_and_conflicted(self) -> None:
        change_id = EntityId.new()
        with self.assertRaisesRegex(ValueError, "outcome_conflict"):
            SyncResult("next", (change_id,), (SyncConflict(change_id, "revision_conflict"),))

    def test_provider_errors_have_fixed_codes_and_retryability(self) -> None:
        expectations = (
            (ProviderUnavailable(), "provider.unavailable", True),
            (AuthenticationFailed(), "provider.authentication_failed", False),
            (UnsupportedCapability(), "provider.unsupported_capability", False),
            (InvalidObservation(), "provider.invalid_observation", False),
        )
        for error, code, retryable in expectations:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(str(error), code)
                self.assertIs(error.retryable, retryable)
