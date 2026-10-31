"""Read-only local HTTP adapters for OctoPrint and Moonraker."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from hashlib import sha256
from http.client import HTTPMessage
from typing import IO, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import uuid4

from ufm.application.dto import (
    CurrentJobObservation,
    Observed,
    PrinterCapabilities,
    PrinterEvent,
    PrinterStatusSnapshot,
    PrintJobSnapshot,
    ProviderHealth,
)
from ufm.application.ports.printers import (
    AuthenticationFailed,
    InvalidObservation,
    ProviderError,
    ProviderUnavailable,
)
from ufm.application.ports.secrets import SecretValue
from ufm.domain.enums import (
    Availability,
    ConnectionState,
    PrintStatus,
    ProviderHealthState,
)
from ufm.domain.value_objects import EntityId, ExactDecimal, UtcDateTime

_MAX_RESPONSE_BYTES = 1024 * 1024
_TIMEOUT_SECONDS = 5
_POLL_INTERVAL_SECONDS = 2


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
        new_url: str,
    ) -> None:
        return None


def _validate_local_url(value: str) -> str:
    if type(value) is not str or len(value) > 2_000:
        raise ValueError("printer.endpoint_invalid")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or parsed.hostname is None
        ):
            raise ValueError("printer.endpoint_invalid")
        host = parsed.hostname
        if not isinstance(host, str):
            raise ValueError("printer.endpoint_invalid")
        port = parsed.port
        if port is None:
            port = 80
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("printer.endpoint_invalid")
        address = (
            ipaddress.ip_address("127.0.0.1")
            if host.casefold() == "localhost"
            else ipaddress.ip_address(host)
        )
    except (OSError, ValueError):
        raise ValueError("printer.endpoint_invalid") from None
    private_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fc00::/7"),
    )
    if (
        address.is_multicast or address.is_reserved
        or not (
            address.is_loopback or address.is_link_local
            or any(address.version == network.version and address in network
                   for network in private_networks)
        )
    ):
        raise ValueError("printer.endpoint_must_be_local")
    host = address.compressed
    if address.version == 6:
        host = f"[{host}]"
    netloc = host if port == 80 else f"{host}:{port}"
    return urlunsplit(("http", netloc, "", "", ""))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InvalidObservation()
    return value


def _nested(value: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    current: object = value
    for key in keys:
        if not isinstance(current, dict):
            raise InvalidObservation()
        current = current.get(key)
    return _mapping(current)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _observed[T](value: T | None, now: UtcDateTime) -> Observed[T]:
    return Observed(
        availability=Availability.KNOWN if value is not None else Availability.UNKNOWN,
        observed_at=now,
        received_at=now,
        value=value,
        reason_code=None if value is not None else "provider.field_unavailable",
    )


def _job_status(value: object) -> PrintStatus:
    state = str(value).strip().lower()
    if state in {"printing", "running"}:
        return PrintStatus.RUNNING
    if state in {"paused", "pausing"}:
        return PrintStatus.PAUSED
    if state in {"complete", "completed"}:
        return PrintStatus.COMPLETED
    if state in {"cancelled", "canceled"}:
        return PrintStatus.CANCELLED
    if state in {"error", "failed"}:
        return PrintStatus.FAILED
    raise InvalidObservation()


class LocalPrinterHttpProvider(ABC):
    """Shared bounded transport; callers must keep credentials in the OS store."""

    provider_name = "local-http"

    def __init__(
        self,
        *,
        printer_id: EntityId,
        provider_instance_id: EntityId,
        endpoint: str,
        token: SecretValue | None = None,
    ) -> None:
        self.printer_id = printer_id
        self.provider_instance_id = provider_instance_id
        self.endpoint = _validate_local_url(endpoint)
        self._token = token
        self._source_epoch = str(uuid4())
        self._event_sequence = 0
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    async def connect(self) -> None:
        await self._get_json(self.health_path)

    async def disconnect(self) -> None:
        return None

    async def health(self) -> ProviderHealth:
        now = UtcDateTime.now()
        try:
            await self._get_json(self.health_path)
        except ProviderError as error:
            return ProviderHealth(
                state=(ProviderHealthState.DEGRADED if error.retryable
                       else ProviderHealthState.UNAVAILABLE),
                checked_at=now, reason_code=error.code, retryable=error.retryable,
            )
        return ProviderHealth(
            state=ProviderHealthState.HEALTHY, checked_at=now,
            reason_code="provider.connected", retryable=False,
        )

    async def get_capabilities(self) -> PrinterCapabilities:
        now = UtcDateTime.now()
        supported = {
            "job_detection": True, "progress": True, "layers": False,
            "temperature": True, "camera": False, "pause": False, "resume": False,
            "cancel": False, "filament_usage": False, "multi_material": False,
            "file_metadata": False, "local_connection": True, "cloud_connection": False,
            "push_events": False, "polling": True,
        }
        return PrinterCapabilities(
            schema_version=1,
            **{name: _observed(value, now) for name, value in supported.items()},
        )

    @abstractmethod
    async def get_status(self) -> PrinterStatusSnapshot: ...

    @abstractmethod
    async def get_current_job(self) -> CurrentJobObservation: ...

    async def subscribe_events(self) -> AsyncIterator[PrinterEvent]:
        previous: str | None = None
        while True:
            observation = await self.get_current_job()
            encoded = json.dumps(
                self._job_event_payload(observation), sort_keys=True, separators=(",", ":"),
            )
            payload_hash = sha256(encoded.encode("utf-8")).hexdigest()
            if payload_hash != previous:
                self._event_sequence += 1
                yield PrinterEvent(
                    provider_instance_id=self.provider_instance_id,
                    printer_id=self.printer_id,
                    source_epoch=self._source_epoch,
                    event_key=str(self._event_sequence),
                    kind="current_job",
                    observed_at=observation.observed_at,
                    received_at=observation.received_at,
                    payload_hash=payload_hash,
                    job=observation.job,
                )
                previous = payload_hash
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    @property
    @abstractmethod
    def health_path(self) -> str:
        ...

    async def _get_json(
        self, path: str, *, query: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        url = self.endpoint + path
        if query:
            url += "?" + urlencode(query)
        return await asyncio.to_thread(self._request_json, url)

    def _request_json(self, url: str) -> Mapping[str, Any]:
        headers = {"Accept": "application/json"}
        if self._token is not None:
            headers.update(self._authorization_headers(self._token.reveal()))
        request = Request(url, headers=headers, method="GET")
        try:
            with self._opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
                content = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(content) > _MAX_RESPONSE_BYTES:
                raise InvalidObservation()
            payload = json.loads(content)
        except HTTPError as error:
            if error.code in (401, 403):
                raise AuthenticationFailed() from None
            raise ProviderUnavailable() from None
        except (URLError, OSError, TimeoutError):
            raise ProviderUnavailable() from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise InvalidObservation() from None
        return _mapping(payload)

    @abstractmethod
    def _authorization_headers(self, token: str) -> dict[str, str]:
        ...

    def _job_event_payload(self, observation: CurrentJobObservation) -> dict[str, Any]:
        job = observation.job
        return {
            "availability": observation.availability.value,
            "job": None if job is None else {
                "source": job.source,
                "source_epoch": job.source_epoch,
                "status": job.status.value,
                "provider_run_key": job.provider_run_key,
                "external_job_id": job.external_job_id,
                "file_hash": job.file_hash,
                "progress_bp": job.progress_bp,
            },
        }


class OctoPrintProvider(LocalPrinterHttpProvider):
    """Read-only OctoPrint API monitoring; printer control is intentionally absent."""

    provider_name = "octoprint"

    @property
    def health_path(self) -> str:
        return "/api/version"

    def _authorization_headers(self, token: str) -> dict[str, str]:
        return {"X-Api-Key": token}

    async def get_status(self) -> PrinterStatusSnapshot:
        now = UtcDateTime.now()
        raw = await self._get_json("/api/printer", query={"exclude": "sd"})
        temperature = raw.get("temperature")
        temperature_map = temperature if isinstance(temperature, dict) else {}
        tool = temperature_map.get("tool0")
        bed = temperature_map.get("bed")
        tool_actual = _number(tool.get("actual")) if isinstance(tool, dict) else None
        bed_actual = _number(bed.get("actual")) if isinstance(bed, dict) else None
        return PrinterStatusSnapshot(
            printer_id=self.printer_id,
            connection_state=ConnectionState.ONLINE,
            observed_at=now,
            received_at=now,
            progress=_observed(None, now),
            current_layer=_observed(None, now),
            nozzle_temperature_c=_observed(
                None if tool_actual is None else ExactDecimal.parse(str(tool_actual)), now,
            ),
            bed_temperature_c=_observed(
                None if bed_actual is None else ExactDecimal.parse(str(bed_actual)), now,
            ),
            feed_systems=(),
            source_epoch=self._source_epoch,
        )

    async def get_current_job(self) -> CurrentJobObservation:
        now = UtcDateTime.now()
        raw = await self._get_json("/api/job")
        state = raw.get("state")
        if not isinstance(state, str):
            raise InvalidObservation()
        normalized = state.strip().lower()
        if normalized == "offline":
            return CurrentJobObservation(
                Availability.UNAVAILABLE, now, now,
                reason_code="provider.printer_offline",
            )
        if normalized == "operational":
            return CurrentJobObservation(
                Availability.KNOWN, now, now, reason_code="provider.no_active_job",
            )
        file_info = raw.get("job")
        file_info = file_info if isinstance(file_info, dict) else {}
        file_data = file_info.get("file")
        file_data = file_data if isinstance(file_data, dict) else {}
        progress = raw.get("progress")
        progress = progress if isinstance(progress, dict) else {}
        completion = _number(progress.get("completion"))
        progress_bp = None if completion is None else max(0, min(10_000, round(completion * 100)))
        filename = file_data.get("name")
        if filename is not None and (type(filename) is not str or len(filename) > 500):
            raise InvalidObservation()
        status = _job_status(state)
        job = PrintJobSnapshot(
            source="OCTOPRINT",
            source_epoch=self._source_epoch,
            status=status,
            observed_at=now,
            received_at=now,
            progress_bp=progress_bp,
        )
        return CurrentJobObservation(Availability.KNOWN, now, now, job=job)


class MoonrakerProvider(LocalPrinterHttpProvider):
    """Read-only Moonraker monitoring for Klipper-based printers."""

    provider_name = "moonraker"

    @property
    def health_path(self) -> str:
        return "/server/info"

    def _authorization_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def _printer_objects(self) -> Mapping[str, Any]:
        result = await self._get_json(
            "/printer/objects/query",
            query={"print_stats": "", "display_status": "", "extruder": "", "heater_bed": ""},
        )
        return _nested(result, "result", "status")

    async def get_status(self) -> PrinterStatusSnapshot:
        now = UtcDateTime.now()
        objects = await self._printer_objects()
        display = objects.get("display_status")
        display = display if isinstance(display, dict) else {}
        extruder = objects.get("extruder")
        extruder = extruder if isinstance(extruder, dict) else {}
        bed = objects.get("heater_bed")
        bed = bed if isinstance(bed, dict) else {}
        progress = _number(display.get("progress"))
        extruder_temp = _number(extruder.get("temperature"))
        bed_temp = _number(bed.get("temperature"))
        return PrinterStatusSnapshot(
            printer_id=self.printer_id,
            connection_state=ConnectionState.ONLINE,
            observed_at=now,
            received_at=now,
            progress=_observed(
                None if progress is None else max(0, min(10_000, round(progress * 10_000))),
                now,
            ),
            current_layer=_observed(None, now),
            nozzle_temperature_c=_observed(
                None if extruder_temp is None else ExactDecimal.parse(str(extruder_temp)), now,
            ),
            bed_temperature_c=_observed(
                None if bed_temp is None else ExactDecimal.parse(str(bed_temp)), now,
            ),
            feed_systems=(),
            source_epoch=self._source_epoch,
        )

    async def get_current_job(self) -> CurrentJobObservation:
        now = UtcDateTime.now()
        objects = await self._printer_objects()
        stats = objects.get("print_stats")
        stats = stats if isinstance(stats, dict) else {}
        state = stats.get("state")
        if not isinstance(state, str):
            raise InvalidObservation()
        normalized = state.strip().lower()
        if normalized in {"standby", "ready"}:
            return CurrentJobObservation(
                Availability.KNOWN, now, now, reason_code="provider.no_active_job",
            )
        filename = stats.get("filename")
        if filename is not None and (type(filename) is not str or len(filename) > 500):
            raise InvalidObservation()
        display = objects.get("display_status")
        display = display if isinstance(display, dict) else {}
        progress = _number(display.get("progress"))
        progress_bp = None if progress is None else max(0, min(10_000, round(progress * 10_000)))
        job = PrintJobSnapshot(
            source="MOONRAKER",
            source_epoch=self._source_epoch,
            status=_job_status(state),
            observed_at=now,
            received_at=now,
            progress_bp=progress_bp,
        )
        return CurrentJobObservation(Availability.KNOWN, now, now, job=job)

    async def estimated_filament_usage_mm(self) -> int | None:
        objects = await self._printer_objects()
        stats = objects.get("print_stats")
        stats = stats if isinstance(stats, dict) else {}
        value = _number(stats.get("filament_used"))
        return None if value is None else max(0, round(value))
