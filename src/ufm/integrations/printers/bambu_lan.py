"""Read-only Bambu Lab LAN MQTT monitoring with verified TLS."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import re
import ssl
import threading
import time
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from ufm.application.dto import (
    CurrentJobObservation,
    FeedSlotSnapshot,
    FeedSystemSnapshot,
    Observed,
    PrinterCapabilities,
    PrinterEvent,
    PrinterStatusSnapshot,
    PrintJobSnapshot,
    ProviderHealth,
    ProviderMaterialSlotMapping,
)
from ufm.application.ports.printers import (
    AuthenticationFailed,
    InvalidObservation,
    ProviderError,
    ProviderUnavailable,
    TLSVerificationFailed,
)
from ufm.application.ports.secrets import SecretValue
from ufm.domain.enums import (
    Availability,
    ConnectionState,
    FeedSystemKind,
    PrintStatus,
    ProviderHealthState,
)
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.integrations.printers.local_http import _validate_local_url

_MAX_PAYLOAD_BYTES = 1024 * 1024
_CONNECT_TIMEOUT_SECONDS = 10
_REPORT_TIMEOUT_SECONDS = 12
_POLL_INTERVAL_SECONDS = 2
_MAX_AMS_SYSTEMS = 32
_MAX_AMS_TRAYS = 16
_CERTIFICATE_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class _PinnedMqttClient(mqtt.Client):
    def __init__(self, *, certificate_sha256: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._certificate_sha256 = certificate_sha256

    def _ssl_wrap_socket(self, tcp_sock: Any) -> ssl.SSLSocket:
        ssl_sock = super()._ssl_wrap_socket(tcp_sock)
        certificate = ssl_sock.getpeercert(binary_form=True)
        if certificate is None:
            ssl_sock.close()
            raise ssl.SSLCertVerificationError(
                "The Bambu printer did not present a certificate.",
            )
        actual = hashlib.sha256(certificate).hexdigest()
        if not hmac.compare_digest(actual, self._certificate_sha256):
            ssl_sock.close()
            raise ssl.SSLCertVerificationError(
                "The Bambu printer certificate does not match the trusted fingerprint.",
            )
        return ssl_sock


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InvalidObservation()
    return value


def _optional_text(value: object, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > limit:
        raise InvalidObservation()
    return value


def _identifier(value: object) -> str | None:
    if type(value) is int and 0 <= value <= 65_535:
        return str(value)
    return _optional_text(value, limit=80)


def _provider_report_id(value: object) -> str | None:
    """Preserve Bambu-reported identity fields without treating them as run keys."""
    if value is None:
        return None
    if type(value) is int:
        if value < 0:
            raise InvalidObservation()
        return str(value)
    if type(value) is str:
        normalized = value.strip()
        if len(normalized) > 500:
            raise InvalidObservation()
        return normalized or None
    raise InvalidObservation()


def _provider_ams_mapping(value: object) -> tuple[int, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 256 or any(
        type(item) is not int or not -1 <= item <= 65_535 for item in value
    ):
        raise InvalidObservation()
    return tuple(value)


def _provider_ams_mapping2(value: object) -> tuple[tuple[int, int], ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 256:
        raise InvalidObservation()
    result: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, dict):
            raise InvalidObservation()
        ams_id, slot_id = item.get("ams_id"), item.get("slot_id")
        if any(type(part) is not int or not 0 <= part <= 255 for part in (ams_id, slot_id)):
            raise InvalidObservation()
        result.append((cast(int, ams_id), cast(int, slot_id)))
    return tuple(result)


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number == number and abs(number) != float("inf"):
            return number
    return None


def _temperature(value: object, now: UtcDateTime) -> Observed[ExactDecimal]:
    number = _optional_number(value)
    if number is None:
        return _observed(None, now)
    try:
        exact = ExactDecimal.parse(str(value))
    except ValueError:
        return _observed(None, now)
    return _observed(exact, now)


def _observed[T](value: T | None, now: UtcDateTime) -> Observed[T]:
    return Observed(
        availability=Availability.KNOWN if value is not None else Availability.UNKNOWN,
        observed_at=now,
        received_at=now,
        value=value,
        reason_code=None if value is not None else "provider.field_unavailable",
    )


def _print_report(payload: object) -> Mapping[str, Any]:
    root = _mapping(payload)
    report = root.get("print", root)
    return _mapping(report)


def _merge_report(previous: dict[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(previous)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_report(merged[key], value)
        else:
            merged[key] = value
    return merged


def _list(value: object, key: str | None = None) -> list[object]:
    if isinstance(value, list):
        return [item for item in value]
    if key is not None and isinstance(value, dict) and isinstance(value.get(key), list):
        return [item for item in value[key]]
    return []


def _slot_observation(slot: Mapping[str, Any], now: UtcDateTime, key: str) -> FeedSlotSnapshot:
    tray_uuid = _optional_text(slot.get("tray_uuid"))
    tag_uid = _optional_text(slot.get("tag_uid"))
    tray_type = _optional_text(slot.get("tray_type"), limit=200)
    occupancy = None if not (tray_uuid or tag_uid or tray_type) else True
    raw_remaining_percent = slot.get("remain")
    remaining_percent = (
        raw_remaining_percent
        if type(raw_remaining_percent) is int and 0 <= raw_remaining_percent <= 100
        else None
    )
    raw_remaining_grams = slot.get("remain_g")
    remaining_mass = (
        Mass.from_grams(raw_remaining_grams)
        if type(raw_remaining_grams) is int and 0 < raw_remaining_grams <= 100_000
        else None
    )
    return FeedSlotSnapshot(
        slot_key=key,
        occupancy=_observed(occupancy, now),
        tray_uuid=_observed(tray_uuid, now),
        tag_uid=_observed(tag_uid, now),
        assigned_spool_id=_observed(None, now),
        remaining_mass=_observed(remaining_mass, now),
        remaining_percent=_observed(remaining_percent, now),
    )


def feed_systems_from_report(
    report: Mapping[str, Any], now: UtcDateTime,
) -> tuple[FeedSystemSnapshot, ...]:
    raw_ams = report.get("ams")
    ams_units = _list(raw_ams, "ams")
    if len(ams_units) > _MAX_AMS_SYSTEMS:
        raise InvalidObservation()
    systems: list[FeedSystemSnapshot] = []
    for unit_index, raw_unit in enumerate(ams_units):
        unit = _mapping(raw_unit)
        unit_id = _identifier(unit.get("id")) or str(unit_index)
        raw_trays = unit.get("tray", [])
        trays = _list(raw_trays)
        if len(trays) > _MAX_AMS_TRAYS:
            raise InvalidObservation()
        slots = tuple(
            _slot_observation(
                _mapping(raw_tray),
                now,
                f"{unit_id}:{_identifier(_mapping(raw_tray).get('id')) or tray_index}",
            )
            for tray_index, raw_tray in enumerate(trays)
        )
        systems.append(FeedSystemSnapshot(
            provider_system_key=f"ams:{unit_id}",
            kind=FeedSystemKind.AMS,
            slots=slots,
            observed_at=now,
            received_at=now,
            complete=False,
        ))
    external = report.get("vt_tray")
    if isinstance(external, dict):
        systems.append(FeedSystemSnapshot(
            provider_system_key="external",
            kind=FeedSystemKind.EXTERNAL,
            slots=(_slot_observation(external, now, "external"),),
            observed_at=now,
            received_at=now,
            complete=False,
        ))
    return tuple(systems)


def material_slot_mappings_from_report(
    report: Mapping[str, Any],
) -> tuple[ProviderMaterialSlotMapping, ...]:
    """Decode only the current job's explicit ``mapping`` field.

    MQTT callbacks store the inner ``print`` object, while callers and fixtures
    may pass the full report envelope. Studio's ``ams_mapping*`` fields are
    preserved separately: they can come from the earlier ``project_file``
    command and are not correlated to this active job occurrence here.
    """
    nested = report.get("print")
    print_block = nested if isinstance(nested, Mapping) else report
    if "mapping" not in print_block:
        return ()
    raw_mapping = print_block.get("mapping")
    if not isinstance(raw_mapping, list) or len(raw_mapping) > 256:
        raise InvalidObservation()

    result: list[ProviderMaterialSlotMapping] = []
    for logical_material, raw_value in enumerate(raw_mapping):
        if type(raw_value) is not int or not 0 <= raw_value <= 0xFFFF:
            result.append(ProviderMaterialSlotMapping(logical_material, "unsupported"))
            continue
        if raw_value == 0xFFFF:
            result.append(ProviderMaterialSlotMapping(logical_material, "unused"))
            continue
        system_id, slot_id = raw_value >> 8, raw_value & 0xFF
        if (0 <= system_id <= 3 and 0 <= slot_id <= 3):
            system_key, slot_key = f"ams:{system_id}", f"{system_id}:{slot_id}"
        elif 128 <= system_id <= 135 and slot_id == 0:
            system_key, slot_key = f"ams:{system_id}", f"{system_id}:0"
        elif system_id == 255 and slot_id == 0:
            system_key, slot_key = "external", "external"
        else:
            result.append(ProviderMaterialSlotMapping(logical_material, "unsupported"))
            continue
        result.append(ProviderMaterialSlotMapping(
            logical_material, "reported_slot", system_key, slot_key,
        ))
    return tuple(result)


def _status(value: object) -> PrintStatus | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    states = {
        "RUNNING": PrintStatus.RUNNING,
        "PREPARE": PrintStatus.PREPARING,
        "PREPARING": PrintStatus.PREPARING,
        "SLICING": PrintStatus.PREPARING,
        "PAUSE": PrintStatus.PAUSED,
        "PAUSED": PrintStatus.PAUSED,
        "FINISH": PrintStatus.COMPLETED,
        "COMPLETED": PrintStatus.COMPLETED,
        "FAILED": PrintStatus.FAILED,
        "CANCELLED": PrintStatus.CANCELLED,
        "CANCELED": PrintStatus.CANCELLED,
    }
    return states.get(normalized)


class BambuLanProvider:
    """Read-only telemetry client for Bambu LAN mode; never sends control commands."""

    provider_name = "bambu-lan"

    def __init__(
        self,
        *,
        printer_id: EntityId,
        provider_instance_id: EntityId,
        host: str,
        serial_number: str,
        access_code: SecretValue,
        ca_certificate: Path | None = None,
        certificate_sha256: str | None = None,
        port: int = 8883,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("printer.port_invalid")
        host_literal = f"[{host}]" if ":" in host and not host.startswith("[") else host
        validated = _validate_local_url(f"http://{host_literal}:{port}")
        validated_host = validated.removeprefix("http://").rsplit(":", 1)[0]
        if validated_host.startswith("[") and validated_host.endswith("]"):
            validated_host = validated_host[1:-1]
        if not serial_number.isascii() or not serial_number.isalnum() or not 8 <= len(serial_number) <= 64:
            raise ValueError("printer.serial_invalid")
        if ca_certificate is not None and not ca_certificate.is_file():
            raise ValueError("printer.certificate_invalid")
        if certificate_sha256 is not None and (
            ca_certificate is None
            or not _CERTIFICATE_FINGERPRINT_PATTERN.fullmatch(certificate_sha256)
        ):
            raise ValueError("printer.certificate_pin_invalid")
        self.printer_id = printer_id
        self.provider_instance_id = provider_instance_id
        self.host = validated_host
        self.serial_number = serial_number
        self._access_code = access_code
        self._ca_certificate = ca_certificate
        self._certificate_sha256 = certificate_sha256
        self.port = port
        self._source_epoch = str(uuid4())
        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        self._changed = threading.Condition()
        self._report: dict[str, Any] = {}
        self._report_generation = 0
        self._request_sequence = 0
        self._report_error = False
        self._connection_error: ProviderError | None = None
        self._event_sequence = 0

    async def connect(self) -> None:
        if self._connected.is_set():
            return
        self._connection_error = None
        self._connected.clear()
        with self._changed:
            self._report.clear()
            self._report_generation = 0
            self._report_error = False
        client: mqtt.Client
        if self._certificate_sha256 is None:
            client = mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=f"ufm-{uuid4().hex[:20]}",
                protocol=mqtt.MQTTv311,
            )
        else:
            client = _PinnedMqttClient(
                certificate_sha256=self._certificate_sha256,
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=f"ufm-{uuid4().hex[:20]}",
                protocol=mqtt.MQTTv311,
            )
        client.username_pw_set("bblp", self._access_code.reveal())
        context = ssl.create_default_context(
            cafile=None if self._ca_certificate is None else str(self._ca_certificate),
        )
        if self._certificate_sha256 is not None:
            context.check_hostname = False
        client.tls_set_context(context)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self._client = client
        try:
            await asyncio.to_thread(self._connect_client, client)
            connected = await asyncio.to_thread(
                self._connected.wait, _CONNECT_TIMEOUT_SECONDS,
            )
            error = self._connection_error
            if error is not None:
                raise error
            if not connected:
                raise ProviderUnavailable()
        except ProviderError:
            await self.disconnect()
            raise
        except (OSError, ssl.SSLError, ValueError, RuntimeError):
            await self.disconnect()
            raise ProviderUnavailable() from None

    def _connect_client(self, client: mqtt.Client) -> None:
        try:
            client.connect(self.host, self.port, keepalive=30)
            client.loop_start()
        except ssl.SSLCertVerificationError:
            self._connection_error = TLSVerificationFailed()
            self._connected.set()
        except (OSError, ssl.SSLError, ValueError, RuntimeError):
            self._connection_error = ProviderUnavailable()
            self._connected.set()

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            get_name = getattr(reason_code, "getName", None)
            reason_name = get_name() if callable(get_name) else ""
            self._connection_error = (
                AuthenticationFailed()
                if reason_name in {"Bad user name or password", "Not authorized"}
                else ProviderUnavailable()
            )
            self._connected.set()
            return
        self._connected.set()
        client.subscribe(f"device/{self.serial_number}/report", qos=0)
        client.publish(
            f"device/{self.serial_number}/request",
            json.dumps(
                {"pushing": {"sequence_id": "-1", "command": "pushall"}},
                separators=(",", ":"),
            ),
            qos=0,
        )

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if (
            self._connected.is_set()
            and self._connection_error is None
            and getattr(reason_code, "is_failure", False)
        ):
            self._connection_error = ProviderUnavailable()
        self._connected.clear()
        with self._changed:
            self._changed.notify_all()

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        if len(message.payload) > _MAX_PAYLOAD_BYTES:
            self._report_error = True
            with self._changed:
                self._changed.notify_all()
            return
        try:
            payload = json.loads(message.payload)
            if not isinstance(payload, dict) or "print" not in payload:
                return
            report = _print_report(payload)
            with self._changed:
                self._report = _merge_report(self._report, report)
                self._report_error = False
                self._report_generation += 1
                self._changed.notify_all()
        except (UnicodeDecodeError, json.JSONDecodeError, InvalidObservation, RecursionError):
            self._report_error = True
            with self._changed:
                self._changed.notify_all()

    def _wait_report(self) -> Mapping[str, Any]:
        deadline = time.monotonic() + _REPORT_TIMEOUT_SECONDS
        with self._changed:
            while self._connected.is_set() and not self._report and not self._report_error:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderUnavailable()
                self._changed.wait(remaining)
            if not self._connected.is_set():
                raise ProviderUnavailable()
            if self._report_error:
                raise InvalidObservation()
            return dict(self._report)

    async def _get_report(self) -> Mapping[str, Any]:
        if not self._connected.is_set():
            raise ProviderUnavailable()
        return await asyncio.to_thread(self._wait_report)

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        self._connected.clear()
        with self._changed:
            self._changed.notify_all()
        if client is not None:
            await asyncio.to_thread(client.disconnect)
            await asyncio.to_thread(client.loop_stop)

    async def health(self) -> ProviderHealth:
        now = UtcDateTime.now()
        if self._connected.is_set():
            try:
                await asyncio.to_thread(self._request_fresh_report)
            except ProviderError as error:
                return ProviderHealth(
                    state=ProviderHealthState.DEGRADED,
                    checked_at=UtcDateTime.now(),
                    reason_code="provider.stale" if error.retryable else error.code,
                    retryable=error.retryable,
                )
            return ProviderHealth(
                state=ProviderHealthState.HEALTHY,
                checked_at=UtcDateTime.now(),
                reason_code="provider.connected",
                retryable=False,
            )
        connection_error = self._connection_error
        return ProviderHealth(
            state=ProviderHealthState.UNAVAILABLE,
            checked_at=now,
            reason_code=("provider.unavailable" if connection_error is None
                         else connection_error.code),
            retryable=True if connection_error is None else connection_error.retryable,
        )

    def _request_fresh_report(self) -> None:
        with self._changed:
            if not self._connected.is_set() or self._client is None:
                raise ProviderUnavailable()
            generation = self._report_generation
            self._request_sequence += 1
            sequence = str(self._request_sequence)
            client = self._client

        request_topic = f"device/{self.serial_number}/request"
        try:
            client.publish(
                request_topic,
                json.dumps(
                    {"info": {"sequence_id": sequence, "command": "get_version"}},
                    separators=(",", ":"),
                ),
                qos=1,
            )
            client.publish(
                request_topic,
                json.dumps(
                    {
                        "pushing": {
                            "sequence_id": sequence,
                            "command": "pushall",
                            "version": 1,
                            "push_target": 1,
                        },
                    },
                    separators=(",", ":"),
                ),
                qos=0,
            )
        except (OSError, RuntimeError, ValueError):
            raise ProviderUnavailable() from None
        deadline = time.monotonic() + _REPORT_TIMEOUT_SECONDS
        with self._changed:
            while self._connected.is_set() and self._report_generation <= generation:
                if self._report_error:
                    raise InvalidObservation()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderUnavailable()
                self._changed.wait(remaining)
            if not self._connected.is_set():
                raise ProviderUnavailable()
            if self._report_error:
                raise InvalidObservation()

    async def get_capabilities(self) -> PrinterCapabilities:
        now = UtcDateTime.now()
        support = {
            "job_detection": True,
            "progress": True,
            "layers": True,
            "temperature": True,
            "camera": False,
            "pause": False,
            "resume": False,
            "cancel": False,
            "filament_usage": False,
            "multi_material": True,
            "file_metadata": False,
            "local_connection": True,
            "cloud_connection": False,
            "push_events": True,
            "polling": False,
        }
        return PrinterCapabilities(
            schema_version=1,
            **{key: _observed(value, now) for key, value in support.items()},
        )

    async def get_status(self) -> PrinterStatusSnapshot:
        report = await self._get_report()
        now = UtcDateTime.now()
        percent = _optional_number(report.get("mc_percent"))
        layer_value = _optional_number(report.get("layer_num"))
        layer = None if layer_value is None else max(0, math.floor(layer_value))
        return PrinterStatusSnapshot(
            printer_id=self.printer_id,
            connection_state=ConnectionState.ONLINE,
            observed_at=now,
            received_at=now,
            progress=_observed(
                None if percent is None else max(0, min(10_000, round(percent * 100))),
                now,
            ),
            current_layer=_observed(layer, now),
            nozzle_temperature_c=_temperature(report.get("nozzle_temper"), now),
            bed_temperature_c=_temperature(report.get("bed_temper"), now),
            feed_systems=feed_systems_from_report(report, now),
            source_epoch=self._source_epoch,
        )

    async def get_current_job(self) -> CurrentJobObservation:
        report = await self._get_report()
        now = UtcDateTime.now()
        status = _status(report.get("gcode_state"))
        if status is None:
            state = report.get("gcode_state")
            if isinstance(state, str) and state.upper() in {"IDLE", "SCHEDULE"}:
                return CurrentJobObservation(
                    Availability.KNOWN, now, now, reason_code="provider.no_active_job",
                )
            raise InvalidObservation()
        percent = _optional_number(report.get("mc_percent"))
        progress = None if percent is None else max(0, min(10_000, round(percent * 100)))
        layer_value = _optional_number(report.get("layer_num"))
        current_layer = None if layer_value is None else max(0, math.floor(layer_value))
        # HaspelSync's traced Bambu rule: layer_num N means N-1 layers complete.
        completed_layers = None if current_layer is None else max(0, current_layer - 1)
        job = PrintJobSnapshot(
            source="BAMBU_LAN",
            source_epoch=self._source_epoch,
            status=status,
            observed_at=now,
            received_at=now,
            provider_task_id=_provider_report_id(report.get("task_id")),
            provider_subtask_id=_provider_report_id(report.get("subtask_id")),
            provider_job_id=_provider_report_id(report.get("job_id")),
            provider_ams_mapping=_provider_ams_mapping(report.get("ams_mapping")),
            provider_ams_mapping2=_provider_ams_mapping2(report.get("ams_mapping2")),
            progress_bp=progress,
            current_layer=current_layer,
            completed_layers=completed_layers,
            material_slot_mappings=material_slot_mappings_from_report(report),
        )
        return CurrentJobObservation(Availability.KNOWN, now, now, job=job)

    async def subscribe_events(self) -> AsyncIterator[PrinterEvent]:
        previous: str | None = None
        while True:
            observation = await self.get_current_job()
            payload = json.dumps(
                {
                    "availability": observation.availability.value,
                    "status": None if observation.job is None else observation.job.status.value,
                    "progress": None if observation.job is None else observation.job.progress_bp,
                    "current_layer": None if observation.job is None else observation.job.current_layer,
                    "completed_layers": None if observation.job is None else observation.job.completed_layers,
                    "provider_task_id": None if observation.job is None else observation.job.provider_task_id,
                    "provider_subtask_id": None if observation.job is None else observation.job.provider_subtask_id,
                    "provider_job_id": None if observation.job is None else observation.job.provider_job_id,
                    "provider_ams_mapping": (
                        None if observation.job is None else observation.job.provider_ams_mapping
                    ),
                    "provider_ams_mapping2": (
                        None if observation.job is None else observation.job.provider_ams_mapping2
                    ),
                    "material_slot_mappings": (
                        [] if observation.job is None else [
                            {
                                "logical_material": item.logical_material,
                                "disposition": item.disposition,
                                "provider_system_key": item.provider_system_key,
                                "provider_slot_key": item.provider_slot_key,
                            }
                            for item in observation.job.material_slot_mappings
                        ]
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if digest != previous:
                self._event_sequence += 1
                yield PrinterEvent(
                    provider_instance_id=self.provider_instance_id,
                    printer_id=self.printer_id,
                    source_epoch=self._source_epoch,
                    event_key=str(self._event_sequence),
                    kind="current_job",
                    observed_at=observation.observed_at,
                    received_at=observation.received_at,
                    payload_hash=digest,
                    job=observation.job,
                )
                previous = digest
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
