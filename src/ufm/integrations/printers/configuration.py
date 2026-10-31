"""Verified enrollment of a local HTTP printer and its OS-backed credential reference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from ufm.application.dto import CurrentJobObservation, PrinterStatusSnapshot
from ufm.application.ports.printers import PrinterProvider
from ufm.application.ports.secrets import (
    SecretNotFound,
    SecretStore,
    SecretStoreUnavailable,
    SecretValue,
)
from ufm.domain.enums import ConnectionMode
from ufm.domain.value_objects import EntityId, UtcDateTime
from ufm.infrastructure.persistence.models.schema import (
    connection_profile,
    device_identity,
    printer,
)
from ufm.infrastructure.persistence.sqlite.engine import immediate_transaction
from ufm.integrations.printers.bambu_lan import BambuLanProvider
from ufm.integrations.printers.local_http import (
    LocalPrinterHttpProvider,
    MoonrakerProvider,
    OctoPrintProvider,
    _validate_local_url,
)


class PrinterConfigurationError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("printer.configuration_failed")


@dataclass(frozen=True, slots=True)
class ConfiguredLocalPrinter:
    printer_id: EntityId
    name: str
    provider_type: str
    endpoint: str
    credential_ref: str | None


@dataclass(frozen=True, slots=True)
class ConfiguredPrinterObservation:
    status: PrinterStatusSnapshot
    current_job: CurrentJobObservation


def remove_configured_printer(
    *,
    engine: Engine,
    secret_store: SecretStore,
    printer_id: EntityId,
) -> str:
    """Remove a printer's connection while preserving its historical records."""
    with engine.connect() as connection:
        row = connection.execute(
            select(printer.c.name, connection_profile.c.credential_ref).join(
                connection_profile,
                connection_profile.c.printer_id == printer.c.id,
            ).where(printer.c.id == printer_id)
        ).first()
    if row is None:
        raise ValueError("printer.configuration_not_found")

    credential = (
        None if row.credential_ref is None
        else secret_store.get(row.credential_ref)
    )
    if row.credential_ref is not None:
        secret_store.delete(row.credential_ref)

    try:
        with immediate_transaction(engine) as connection:
            removed = connection.execute(
                delete(connection_profile).where(
                    connection_profile.c.printer_id == printer_id,
                ),
            )
            if removed.rowcount != 1:
                raise PrinterConfigurationError()
            disabled = connection.execute(
                update(printer).where(printer.c.id == printer_id).values(enabled=False),
            )
            if disabled.rowcount != 1:
                raise PrinterConfigurationError()
    except (OSError, SQLAlchemyError, PrinterConfigurationError):
        if credential is not None:
            new_ref = secret_store.put(credential)
            with immediate_transaction(engine) as connection:
                connection.execute(
                    update(connection_profile)
                    .where(connection_profile.c.printer_id == printer_id)
                    .values(credential_ref=new_ref),
                )
        raise

    return _required_text(row.name, "printer.name_invalid")


def update_printer_details(
    *, engine: Engine, printer_id: EntityId, name: str, model: str,
) -> str:
    """Edit display details without changing the tested endpoint or credential."""
    clean_name = _required_text(name, "printer.name_invalid")
    clean_model = _required_text(model, "printer.model_invalid")
    now = UtcDateTime.now()
    with immediate_transaction(engine) as connection:
        row = connection.execute(
            select(printer.c.revision).join(
                connection_profile,
                connection_profile.c.printer_id == printer.c.id,
            ).where(printer.c.id == printer_id, printer.c.enabled.is_(True))
        ).first()
        if row is None:
            raise ValueError("printer.configuration_not_found")
        updated = connection.execute(
            update(printer).where(
                printer.c.id == printer_id,
                printer.c.revision == row.revision,
                printer.c.enabled.is_(True),
            ).values(
                name=clean_name,
                model=clean_model,
                revision=row.revision + 1,
                updated_at=now,
            )
        )
        if updated.rowcount != 1:
            raise PrinterConfigurationError()
    return clean_name


async def update_bambu_printer_connection(
    *,
    engine: Engine,
    secret_store: SecretStore,
    printer_id: EntityId,
    host: str,
    serial_number: str,
    access_code: SecretValue,
) -> ConfiguredLocalPrinter:
    """Verify a replacement Bambu connection before changing its saved profile."""
    clean_serial = _required_text(serial_number, "printer.serial_invalid", limit=64)
    host_literal = f"[{host}]" if ":" in host and not host.startswith("[") else host
    endpoint = _validate_local_url(f"http://{host_literal}:8883")
    parsed = urlsplit(endpoint)
    if parsed.hostname is None:
        raise ValueError("printer.endpoint_invalid")

    with engine.connect() as connection:
        row = connection.execute(
            select(
                printer.c.name,
                printer.c.revision.label("printer_revision"),
                connection_profile.c.id.label("profile_id"),
                connection_profile.c.provider_type,
                connection_profile.c.revision.label("profile_revision"),
                connection_profile.c.host,
                connection_profile.c.port,
                connection_profile.c.credential_ref,
                connection_profile.c.extra_config_json,
            ).join(
                connection_profile,
                connection_profile.c.printer_id == printer.c.id,
            ).where(printer.c.id == printer_id, printer.c.enabled.is_(True))
        ).first()
    if row is None:
        raise ValueError("printer.configuration_not_found")
    if row.provider_type != "BAMBU_LAN" or row.credential_ref is None:
        raise ValueError("printer.provider_not_editable")
    try:
        old_config = json.loads(row.extra_config_json or "{}")
    except (TypeError, json.JSONDecodeError):
        raise PrinterConfigurationError() from None
    if not isinstance(old_config, dict):
        raise PrinterConfigurationError()
    old_serial = old_config.get("serial_number")
    certificate_path = old_config.get("ca_certificate_path")
    certificate_sha256 = old_config.get("certificate_sha256")
    if (
        not isinstance(old_serial, str)
        or certificate_path is not None and not isinstance(certificate_path, str)
        or certificate_sha256 is not None and not isinstance(certificate_sha256, str)
    ):
        raise PrinterConfigurationError()
    old_secret = secret_store.get(row.credential_ref)

    provider = BambuLanProvider(
        printer_id=printer_id,
        provider_instance_id=row.profile_id,
        host=parsed.hostname,
        port=8883,
        serial_number=clean_serial,
        access_code=access_code,
        ca_certificate=None if certificate_path is None else Path(certificate_path),
        certificate_sha256=certificate_sha256,
    )
    try:
        await provider.connect()
        await provider.get_status()
    finally:
        await provider.disconnect()

    new_credential_ref = secret_store.put(access_code)
    try:
        secret_store.delete(row.credential_ref)
    except Exception:
        try:
            secret_store.delete(new_credential_ref)
        except Exception:
            raise PrinterConfigurationError() from None
        raise

    new_config = {
        **old_config,
        "serial_number": clean_serial,
    }
    now = UtcDateTime.now()
    try:
        with immediate_transaction(engine) as connection:
            profile_update = connection.execute(
                update(connection_profile).where(
                    connection_profile.c.id == row.profile_id,
                    connection_profile.c.printer_id == printer_id,
                    connection_profile.c.revision == row.profile_revision,
                ).values(
                    host=parsed.hostname,
                    port=8883,
                    tls_enabled=True,
                    credential_ref=new_credential_ref,
                    extra_config_json=json.dumps(
                        new_config, separators=(",", ":"), sort_keys=True,
                    ),
                    revision=row.profile_revision + 1,
                    updated_at=now,
                ),
            )
            printer_update = connection.execute(
                update(printer).where(
                    printer.c.id == printer_id,
                    printer.c.revision == row.printer_revision,
                    printer.c.enabled.is_(True),
                ).values(
                    serial_number=clean_serial,
                    revision=row.printer_revision + 1,
                    updated_at=now,
                ),
            )
            if profile_update.rowcount != 1 or printer_update.rowcount != 1:
                raise PrinterConfigurationError()
    except Exception:
        try:
            restored_credential_ref = secret_store.put(old_secret)
            with immediate_transaction(engine) as connection:
                restored = connection.execute(
                    update(connection_profile).where(
                        connection_profile.c.id == row.profile_id,
                        connection_profile.c.printer_id == printer_id,
                        connection_profile.c.revision == row.profile_revision,
                    ).values(
                        credential_ref=restored_credential_ref,
                        revision=row.profile_revision + 1,
                        updated_at=UtcDateTime.now(),
                    ),
                )
                if restored.rowcount != 1:
                    raise PrinterConfigurationError()
            secret_store.delete(new_credential_ref)
        except Exception:
            raise PrinterConfigurationError() from None
        raise

    return ConfiguredLocalPrinter(
        printer_id=printer_id,
        name=row.name,
        provider_type="BAMBU_LAN",
        endpoint=(
            f"mqtts://[{parsed.hostname}]:8883"
            if ":" in parsed.hostname else f"mqtts://{parsed.hostname}:8883"
        ),
        credential_ref=new_credential_ref,
    )


def _required_text(value: str, code: str, *, limit: int = 200) -> str:
    if type(value) is not str or not value.strip() or len(value.strip()) > limit:
        raise ValueError(code)
    return value.strip()


def local_provider(
    provider_type: str,
    *,
    printer_id: EntityId,
    provider_instance_id: EntityId,
    endpoint: str,
    token: SecretValue | None,
) -> LocalPrinterHttpProvider:
    providers = {
        "OCTOPRINT": OctoPrintProvider,
        "MOONRAKER": MoonrakerProvider,
    }
    provider_class = providers.get(provider_type)
    if provider_class is None:
        raise ValueError("printer.provider_unsupported")
    return provider_class(
        printer_id=printer_id,
        provider_instance_id=provider_instance_id,
        endpoint=endpoint,
        token=token,
    )


async def configure_bambu_printer(
    *,
    engine: Engine,
    secret_store: SecretStore,
    name: str,
    model: str,
    host: str,
    serial_number: str,
    access_code: SecretValue,
    ca_certificate: Path | None = None,
    certificate_sha256: str | None = None,
) -> ConfiguredLocalPrinter:
    clean_name = _required_text(name, "printer.name_invalid")
    clean_model = _required_text(model, "printer.model_invalid")
    clean_serial = _required_text(serial_number, "printer.serial_invalid")
    if ca_certificate is not None and not ca_certificate.is_file():
        raise ValueError("printer.certificate_invalid")
    host_literal = f"[{host}]" if ":" in host and not host.startswith("[") else host
    endpoint = _validate_local_url(f"http://{host_literal}:8883")
    parsed = urlsplit(endpoint)
    if parsed.hostname is None:
        raise ValueError("printer.endpoint_invalid")
    printer_id = EntityId.new()
    provider = BambuLanProvider(
        printer_id=printer_id,
        provider_instance_id=EntityId.new(),
        host=parsed.hostname,
        serial_number=clean_serial,
        access_code=access_code,
        ca_certificate=ca_certificate,
        certificate_sha256=certificate_sha256,
    )
    try:
        await provider.connect()
        await provider.get_status()
    finally:
        await provider.disconnect()

    device_id = ensure_local_device(engine)
    credential_ref = secret_store.put(access_code)
    now = UtcDateTime(datetime.now(UTC))
    try:
        with immediate_transaction(engine) as connection:
            connection.execute(insert(printer).values(
                id=printer_id,
                device_id=device_id,
                created_at=now,
                updated_at=now,
                revision=1,
                name=clean_name,
                manufacturer="Bambu Lab",
                model=clean_model,
                serial_number=clean_serial,
                enabled=True,
                has_multi_material_system=True,
            ))
            connection.execute(insert(connection_profile).values(
                id=EntityId.new(),
                device_id=device_id,
                created_at=now,
                updated_at=now,
                revision=1,
                printer_id=printer_id,
                provider_type="BAMBU_LAN",
                connection_mode=ConnectionMode.LOCAL.value,
                host=parsed.hostname,
                port=8883,
                tls_enabled=True,
                credential_ref=credential_ref,
                extra_config_json=json.dumps({
                    "serial_number": clean_serial,
                    "ca_certificate_path": (
                        None if ca_certificate is None
                        else str(ca_certificate.expanduser().resolve())
                    ),
                    "certificate_sha256": certificate_sha256,
                }, separators=(",", ":"), sort_keys=True),
            ))
    except (SQLAlchemyError, OSError, ValueError):
        try:
            secret_store.delete(credential_ref)
        except SecretStoreUnavailable:
            raise PrinterConfigurationError() from None
        raise
    return ConfiguredLocalPrinter(
        printer_id=printer_id,
        name=clean_name,
        provider_type="BAMBU_LAN",
        endpoint=(
            f"mqtts://[{parsed.hostname}]:8883"
            if ":" in parsed.hostname else f"mqtts://{parsed.hostname}:8883"
        ),
        credential_ref=credential_ref,
    )


def configured_printer_provider(
    *,
    engine: Engine,
    secret_store: SecretStore,
    printer_id: EntityId,
) -> PrinterProvider:
    """Build a read-only provider from one saved profile without connecting."""
    with engine.connect() as connection:
        row = connection.execute(
            select(
                printer.c.id,
                connection_profile.c.id.label("profile_id"),
                connection_profile.c.provider_type,
                connection_profile.c.host,
                connection_profile.c.port,
                connection_profile.c.credential_ref,
                connection_profile.c.extra_config_json,
            ).join(
                connection_profile,
                connection_profile.c.printer_id == printer.c.id,
            ).where(printer.c.id == printer_id)
        ).first()
    if row is None or row.host is None:
        raise ValueError("printer.configuration_not_found")
    token = None
    if row.credential_ref is not None:
        token = secret_store.get(row.credential_ref)
    provider: PrinterProvider
    if row.provider_type == "BAMBU_LAN":
        if token is None:
            raise SecretNotFound()
        try:
            config = json.loads(row.extra_config_json or "{}")
        except (TypeError, json.JSONDecodeError):
            raise PrinterConfigurationError() from None
        if not isinstance(config, dict):
            raise PrinterConfigurationError()
        serial = config.get("serial_number")
        certificate_path = config.get("ca_certificate_path")
        certificate_sha256 = config.get("certificate_sha256")
        if not isinstance(serial, str):
            raise PrinterConfigurationError()
        if certificate_path is not None and not isinstance(certificate_path, str):
            raise PrinterConfigurationError()
        if certificate_sha256 is not None and not isinstance(certificate_sha256, str):
            raise PrinterConfigurationError()
        provider = BambuLanProvider(
            printer_id=row.id,
            provider_instance_id=row.profile_id,
            host=row.host,
            port=row.port or 8883,
            serial_number=serial,
            access_code=token,
            ca_certificate=None if certificate_path is None else Path(certificate_path),
            certificate_sha256=certificate_sha256,
        )
    else:
        provider_type = row.provider_type
        if provider_type not in {"OCTOPRINT", "MOONRAKER"}:
            raise ValueError("printer.provider_unsupported")
        host = f"[{row.host}]" if ":" in row.host else row.host
        port = row.port or 80
        endpoint = f"http://{host}" if port == 80 else f"http://{host}:{port}"
        provider = local_provider(
            provider_type,
            printer_id=row.id,
            provider_instance_id=row.profile_id,
            endpoint=endpoint,
            token=token,
        )

    return provider


async def probe_configured_printer(
    *,
    engine: Engine,
    secret_store: SecretStore,
    printer_id: EntityId,
) -> ConfiguredPrinterObservation:
    provider = configured_printer_provider(
        engine=engine, secret_store=secret_store, printer_id=printer_id,
    )
    try:
        await provider.connect()
        status = await provider.get_status()
        current_job = await provider.get_current_job()
    finally:
        await provider.disconnect()
    return ConfiguredPrinterObservation(status=status, current_job=current_job)


def ensure_local_device(engine: Engine) -> EntityId:
    database_path = engine.url.database
    if not database_path:
        raise PrinterConfigurationError()
    device_id = EntityId.parse(str(uuid5(
        NAMESPACE_URL,
        f"ufm:local-device:{database_path}",
    )))
    now = UtcDateTime(datetime.now(UTC))
    with immediate_transaction(engine) as connection:
        existing_device = connection.execute(
            select(device_identity.c.id).where(device_identity.c.id == device_id)
        ).first()
        if existing_device is None:
            connection.execute(insert(device_identity).values(
                id=device_id,
                name="Local UFM installation",
                public_id=str(device_id),
                created_at=now,
            ))
    return device_id


async def configure_local_printer(
    *,
    engine: Engine,
    secret_store: SecretStore,
    name: str,
    manufacturer: str,
    model: str,
    provider_type: str,
    endpoint: str,
    token: SecretValue | None,
) -> ConfiguredLocalPrinter:
    """Test the endpoint first, then persist the printer and only a secret reference."""
    clean_name = _required_text(name, "printer.name_invalid")
    clean_manufacturer = _required_text(manufacturer, "printer.manufacturer_invalid")
    clean_model = _required_text(model, "printer.model_invalid")
    canonical_endpoint = _validate_local_url(endpoint)
    parsed = urlsplit(canonical_endpoint)
    host = parsed.hostname
    if host is None:
        raise ValueError("printer.endpoint_invalid")
    port = parsed.port or 80
    printer_id = EntityId.new()
    provider_instance_id = EntityId.new()
    provider = local_provider(
        provider_type,
        printer_id=printer_id,
        provider_instance_id=provider_instance_id,
        endpoint=canonical_endpoint,
        token=token,
    )
    try:
        await provider.connect()
    finally:
        await provider.disconnect()

    device_id = ensure_local_device(engine)
    credential_ref = None if token is None else secret_store.put(token)
    now = UtcDateTime(datetime.now(UTC))
    try:
        with immediate_transaction(engine) as connection:
            connection.execute(insert(printer).values(
                id=printer_id,
                device_id=device_id,
                created_at=now,
                updated_at=now,
                revision=1,
                name=clean_name,
                manufacturer=clean_manufacturer,
                model=clean_model,
                enabled=True,
            ))
            connection.execute(insert(connection_profile).values(
                id=EntityId.new(),
                device_id=device_id,
                created_at=now,
                updated_at=now,
                revision=1,
                printer_id=printer_id,
                provider_type=provider_type,
                connection_mode=ConnectionMode.LOCAL.value,
                host=host,
                port=port,
                tls_enabled=False,
                credential_ref=credential_ref,
                extra_config_json="{}",
            ))
    except (SQLAlchemyError, OSError, ValueError):
        if credential_ref is not None:
            try:
                secret_store.delete(credential_ref)
            except SecretStoreUnavailable:
                raise PrinterConfigurationError() from None
        raise
    return ConfiguredLocalPrinter(
        printer_id=printer_id,
        name=clean_name,
        provider_type=provider_type,
        endpoint=canonical_endpoint,
        credential_ref=credential_ref,
    )
