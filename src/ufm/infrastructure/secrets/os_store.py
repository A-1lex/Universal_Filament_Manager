"""Select only the native secure backend, lazily on the first secret operation."""

import sys
from importlib import import_module
from typing import Protocol, cast
from uuid import UUID, uuid4

from ufm.application.ports.secrets import (
    InvalidCredentialReference,
    SecretNotFound,
    SecretStoreUnavailable,
    SecretValue,
)

_SERVICE = "UniversalFilamentManager"
_PREFIX = "ufm:credential:"
_BACKENDS = {
    "win32": ("keyring.backends.Windows", "WinVaultKeyring"),
    "darwin": ("keyring.backends.macOS", "Keyring"),
    "linux": ("keyring.backends.SecretService", "Keyring"),
}


class _Backend(Protocol):
    @property
    def priority(self) -> float: ...

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def _load_backend() -> _Backend:
    selection = _BACKENDS.get(sys.platform)
    if selection is None:
        raise SecretStoreUnavailable()
    try:
        # Explicit trusted class: never keyring.get_keyring(), entry points,
        # keyringrc.cfg, environment selection, or plaintext fallback plugins.
        module = import_module(selection[0])
        backend = cast(_Backend, getattr(module, selection[1])())
        if backend.priority <= 0:
            raise SecretStoreUnavailable()
        return backend
    except Exception:
        # OS libraries have heterogeneous errors and may echo credentials.
        # Catch only at this external boundary; interruption still propagates.
        raise SecretStoreUnavailable() from None


def _username(reference: str) -> str:
    if not isinstance(reference, str) or not reference.startswith(_PREFIX):
        raise InvalidCredentialReference()
    identifier = reference[len(_PREFIX) :]
    try:
        parsed = UUID(identifier)
    except ValueError:
        raise InvalidCredentialReference() from None
    if str(parsed) != identifier:
        raise InvalidCredentialReference()
    return identifier


class OSSecretStore:
    """No backend probing at import/startup, and no credential-dependent fallback."""

    def __init__(self) -> None:
        self._backend: _Backend | None = None

    def _get_backend(self) -> _Backend:
        if self._backend is None:
            self._backend = _load_backend()
        return self._backend

    def get(self, credential_ref: str) -> SecretValue:
        username = _username(credential_ref)
        try:
            result = self._get_backend().get_password(_SERVICE, username)
        except Exception:
            raise SecretStoreUnavailable() from None
        if result is None:
            raise SecretNotFound()
        try:
            return SecretValue(result)
        except ValueError:
            raise SecretStoreUnavailable() from None

    def put(self, secret: SecretValue) -> str:
        if not isinstance(secret, SecretValue):
            raise TypeError("secrets.invalid_value")
        username = str(uuid4())
        try:
            self._get_backend().set_password(_SERVICE, username, secret.reveal())
        except Exception:
            raise SecretStoreUnavailable() from None
        return _PREFIX + username

    def delete(self, credential_ref: str) -> None:
        username = _username(credential_ref)
        try:
            backend = self._get_backend()
            if backend.get_password(_SERVICE, username) is None:
                return
            backend.delete_password(_SERVICE, username)
        except Exception:
            raise SecretStoreUnavailable() from None

