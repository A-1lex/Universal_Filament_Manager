"""The fake proves port/error behavior; it does not certify native OS storage."""

import importlib.util
import unittest
from unittest.mock import patch
from uuid import uuid4

from ufm.application.ports.secrets import (
    InvalidCredentialReference,
    SecretNotFound,
    SecretStoreUnavailable,
    SecretValue,
)
from ufm.infrastructure.secrets import OSSecretStore
from ufm.infrastructure.secrets.os_store import _load_backend


class MemoryBackend:
    priority = 1.0

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class SecretStoreTests(unittest.TestCase):
    def test_secret_repr_does_not_reveal_value(self) -> None:
        secret = SecretValue("test-private-value")
        self.assertNotIn("test-private-value", repr(secret))
        self.assertNotIn("test-private-value", str(secret))
        self.assertEqual(secret.reveal(), "test-private-value")

    def test_roundtrip_scoped_reference_and_idempotent_delete(self) -> None:
        backend = MemoryBackend()
        with patch("ufm.infrastructure.secrets.os_store._load_backend", return_value=backend):
            store = OSSecretStore()
            reference = store.put(SecretValue("test-private-value"))
            self.assertTrue(reference.startswith("ufm:credential:"))
            self.assertNotIn("test-private-value", reference)
            self.assertEqual(store.get(reference).reveal(), "test-private-value")
            store.delete(reference)
            store.delete(reference)
            with self.assertRaises(SecretNotFound):
                store.get(reference)
        self.assertEqual(backend.values, {})

    def test_arbitrary_reference_cannot_read_or_delete_other_credentials(self) -> None:
        with patch("ufm.infrastructure.secrets.os_store._load_backend") as load:
            for reference in ("other:service", "ufm:credential:not-a-uuid", "private"):
                for operation in (OSSecretStore().get, OSSecretStore().delete):
                    with self.assertRaises(InvalidCredentialReference):
                        operation(reference)
            load.assert_not_called()

    def test_backend_failure_is_sanitized_without_fallback(self) -> None:
        with patch(
            "ufm.infrastructure.secrets.os_store._load_backend",
            side_effect=RuntimeError("password=private-error"),
        ):
            store = OSSecretStore()
            for operation in (
                lambda: store.put(SecretValue("private-value")),
                lambda: store.get("ufm:credential:" + str(uuid4())),
                lambda: store.delete("ufm:credential:" + str(uuid4())),
            ):
                with self.assertRaises(SecretStoreUnavailable) as raised:
                    operation()
                self.assertNotIn("private", str(raised.exception))

    def test_native_selection_is_explicit_and_does_not_probe_at_construction(self) -> None:
        with patch("ufm.infrastructure.secrets.os_store.import_module") as import_backend:
            OSSecretStore()
            import_backend.assert_not_called()
            import_backend.return_value.WinVaultKeyring.return_value = MemoryBackend()
            with patch("ufm.infrastructure.secrets.os_store.sys.platform", "win32"):
                _load_backend()
            import_backend.assert_called_once_with("keyring.backends.Windows")

    def test_unsupported_platform_fails_closed(self) -> None:
        with patch("ufm.infrastructure.secrets.os_store.sys.platform", "unsupported"):
            with self.assertRaises(SecretStoreUnavailable):
                _load_backend()

    @unittest.skipUnless(importlib.util.find_spec("keyring"), "keyring dependency unavailable")
    def test_installed_keyring_has_declared_windows_backend_name(self) -> None:
        # Import only the platform's own backend in CI; no real credential writes.
        import sys
        from importlib import import_module

        modules = {
            "win32": ("keyring.backends.Windows", "WinVaultKeyring"),
            "darwin": ("keyring.backends.macOS", "Keyring"),
            "linux": ("keyring.backends.SecretService", "Keyring"),
        }
        module_name, class_name = modules[sys.platform]
        self.assertTrue(hasattr(import_module(module_name), class_name))

