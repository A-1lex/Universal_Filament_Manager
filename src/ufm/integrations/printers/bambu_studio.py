"""Securely import the active Bambu Studio LAN profile."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ufm.application.ports.secrets import SecretValue

_CERTIFICATE_TIMEOUT_SECONDS = 4
_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9]{8,64}$")
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_LOCAL_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


class BambuStudioImportError(RuntimeError):
    """A safe, unambiguous Bambu Studio profile could not be imported."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class BambuStudioProfile:
    host: str
    serial_number: str
    model: str | None
    access_code: SecretValue
    certificate_sha256: str
    root_certificate_pem: str


@dataclass(frozen=True, slots=True)
class BambuPrinterIdentity:
    host: str
    name: str
    serial_number: str
    model: str | None
    certificate_sha256: str
    root_certificate_pem: str


def _private_host(host: str) -> str:
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError:
        raise BambuStudioImportError("printer.studio_invalid_host") from None
    if not any(address in network for network in _ALLOWED_LOCAL_NETWORKS):
        raise BambuStudioImportError("printer.studio_invalid_host")
    return str(address)


def _certificate_chain(host: str) -> tuple[str, str, str]:
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection(
            (host, 8883), timeout=_CERTIFICATE_TIMEOUT_SECONDS,
        ) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=host) as connection:
                ssl_object = getattr(connection, "_sslobj", None)
                get_chain = getattr(ssl_object, "get_unverified_chain", None)
                if not callable(get_chain):
                    raise BambuStudioImportError("printer.studio_certificate_unavailable")
                chain = get_chain()
    except BambuStudioImportError:
        raise
    except (OSError, ssl.SSLError, TimeoutError, ValueError):
        raise BambuStudioImportError("printer.studio_certificate_unavailable") from None

    try:
        if len(chain) < 2:
            raise BambuStudioImportError("printer.studio_certificate_unavailable")
        certificates = [certificate.public_bytes() for certificate in chain]
        if isinstance(certificates[0], bytes):
            certificates = [certificate.decode("ascii") for certificate in certificates]
        leaf_pem, root_pem = certificates[0], certificates[-1]
        leaf_der = ssl.PEM_cert_to_DER_cert(leaf_pem)
        fingerprint = hashlib.sha256(leaf_der).hexdigest()
    except (
        AttributeError, IndexError, ssl.SSLError, TypeError, UnicodeError, ValueError,
    ):
        raise BambuStudioImportError("printer.studio_certificate_unavailable") from None
    if not _FINGERPRINT_PATTERN.fullmatch(fingerprint):
        raise BambuStudioImportError("printer.studio_certificate_unavailable")

    decoder = getattr(getattr(ssl, "_ssl", None), "_test_decode_cert", None)
    if not callable(decoder):
        raise BambuStudioImportError("printer.studio_certificate_unavailable")
    certificate_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            suffix=".pem",
            delete=False,
        ) as temporary:
            temporary.write(leaf_pem)
            certificate_path = Path(temporary.name)
        details: dict[str, Any] = decoder(str(certificate_path))
    except (OSError, ssl.SSLError, ValueError):
        raise BambuStudioImportError("printer.studio_certificate_unavailable") from None
    finally:
        if certificate_path is not None:
            try:
                certificate_path.unlink(missing_ok=True)
            except OSError:
                raise BambuStudioImportError(
                    "printer.studio_certificate_unavailable",
                ) from None

    common_names = [
        value
        for group in details.get("subject", ())
        for key, value in group
        if key == "commonName"
    ]
    serial = common_names[0] if len(common_names) == 1 else ""
    if not _SERIAL_PATTERN.fullmatch(serial):
        raise BambuStudioImportError("printer.studio_identity_unavailable")
    return serial, fingerprint, root_pem


def _load_settings(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        raise BambuStudioImportError("printer.studio_settings_invalid") from None
    body = text.split("\n# MD5 checksum ", maxsplit=1)[0]
    try:
        settings: Any = json.loads(body)
    except json.JSONDecodeError:
        raise BambuStudioImportError("printer.studio_settings_invalid") from None
    if not isinstance(settings, dict):
        raise BambuStudioImportError("printer.studio_settings_invalid")
    return settings


def _profile_from_settings(
    settings: dict[str, Any],
    *,
    host: str,
    serial_number: str,
) -> tuple[str | None, str, bool] | None:
    access_codes = settings.get("access_code")
    if not isinstance(access_codes, dict):
        return None
    access_code = access_codes.get(serial_number)
    if not isinstance(access_code, str) or not access_code.strip():
        return None

    ip_addresses = settings.get("ip_address")
    ip_confirmed = False
    if isinstance(ip_addresses, dict):
        configured_host = ip_addresses.get(serial_number)
        if configured_host is not None and configured_host != host:
            return None
        ip_confirmed = configured_host == host

    models = settings.get("models")
    model_names = {
        item["model"].strip()
        for item in models
        if isinstance(item, dict)
        and isinstance(item.get("model"), str)
        and item["model"].strip()
    } if isinstance(models, list) else set()
    model = next(iter(model_names)) if len(model_names) == 1 else None
    return model, access_code, ip_confirmed


def import_bambu_studio_profile(host: str) -> BambuStudioProfile:
    """Read matching Studio LAN details and inspect the device certificate.

    The initial TLS handshake sends no MQTT authentication data. Its
    certificate is not trusted until the UI obtains the user's explicit
    fingerprint confirmation.
    """
    clean_host = _private_host(host)
    serial_number, fingerprint, root_pem = _certificate_chain(clean_host)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise BambuStudioImportError("printer.studio_settings_unavailable")

    matching: list[tuple[str | None, str, bool]] = []
    invalid_settings = False
    for app in ("BambuStudio", "BambuStudioBeta"):
        path = Path(appdata) / app / "BambuStudio.conf"
        try:
            settings = _load_settings(path)
        except BambuStudioImportError:
            invalid_settings = True
            continue
        if settings is None:
            continue
        profile = _profile_from_settings(
            settings, host=clean_host, serial_number=serial_number,
        )
        if profile is not None:
            matching.append(profile)
    if not matching:
        if invalid_settings:
            raise BambuStudioImportError("printer.studio_settings_invalid")
        raise BambuStudioImportError("printer.studio_profile_not_found")

    confirmed_matches = [candidate for candidate in matching if candidate[2]]
    if confirmed_matches:
        matching = confirmed_matches
    codes = {code for _, code, _ in matching}
    if len(codes) != 1:
        raise BambuStudioImportError("printer.studio_profile_ambiguous")
    models = {model for model, _, _ in matching if model}
    model = next(iter(models)) if len(models) == 1 else None
    return BambuStudioProfile(
        host=clean_host,
        serial_number=serial_number,
        model=model,
        access_code=SecretValue(next(iter(codes))),
        certificate_sha256=fingerprint,
        root_certificate_pem=root_pem,
    )


def store_bambu_root_certificate(
    config_directory: Path,
    profile: BambuStudioProfile | BambuPrinterIdentity,
) -> Path:
    """Persist the public issuer certificate after the user trusts its leaf."""
    if not _FINGERPRINT_PATTERN.fullmatch(profile.certificate_sha256):
        raise ValueError("printer.certificate_pin_invalid")
    directory = config_directory / "trusted-printers"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"bambu-{profile.certificate_sha256}.pem"
    if path.is_file():
        if path.read_text(encoding="ascii") != profile.root_certificate_pem:
            raise OSError("Stored Bambu certificate does not match its fingerprint.")
        return path

    temporary_path = directory / f".{uuid4().hex}.tmp"
    try:
        temporary_path.write_text(profile.root_certificate_pem, encoding="ascii")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path
