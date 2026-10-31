"""Read-only audit of HaspelSync's local debit and weighing journals."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

MAX_JOURNAL_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 10_000
_DIGEST = re.compile(r"[a-f0-9]{64}")
_BOOKING_STATES = {"pending", "booked", "uncertain", "dismissed"}
_WEIGHING_STATES = {"pending", "recorded", "uncertain", "rejected"}


class HaspelCutoverPreviewRejected(ValueError):
    """Malformed journal or an unsupported schema; source data is not echoed."""

    def __init__(self) -> None:
        super().__init__("haspelsync.cutover_preview_rejected")


@dataclass(frozen=True, slots=True)
class HaspelCutoverPreview:
    printer_serial: str
    evidence_sha256: str
    printer_bookings: tuple[int, int, int, int]
    global_weighings: tuple[int, int, int, int]
    latest_activity_at_ms: int

    @property
    def unresolved_count(self) -> int:
        return self.printer_bookings[0] + self.printer_bookings[2] + (
            self.global_weighings[0] + self.global_weighings[2]
        )

    @property
    def ready(self) -> bool:
        return self.unresolved_count == 0


def _read(path: Path) -> tuple[bytes, object]:
    try:
        with path.open("rb") as source:
            payload = source.read(MAX_JOURNAL_BYTES + 1)
        if len(payload) > MAX_JOURNAL_BYTES:
            raise HaspelCutoverPreviewRejected()
        value = json.loads(payload.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise HaspelCutoverPreviewRejected() from None
    return payload, value


def _reject_constant(_: str) -> None:
    raise HaspelCutoverPreviewRejected()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise HaspelCutoverPreviewRejected()
    return value


def _positive_int(value: object) -> bool:
    return type(value) is int and 0 < value <= 2**53 - 1


def _valid_booking(key: object, value: object) -> dict[str, object]:
    record = _object(value)
    request_hash = record.get("requestHash")
    source = record.get("source")
    printer_id = record.get("printerId")
    item_key = record.get("itemKey")
    grams = record.get("grams")
    status = record.get("status")
    if (
        not isinstance(key, str) or _DIGEST.fullmatch(key) is None
        or record.get("id") != key
        or not isinstance(request_hash, str) or _DIGEST.fullmatch(request_hash) is None
        or not isinstance(source, str) or _DIGEST.fullmatch(source) is None
        or not isinstance(printer_id, str) or not 1 <= len(printer_id) <= 200
        or not isinstance(item_key, str) or not 1 <= len(item_key) <= 200
        or not _positive_int(record.get("startedAt"))
        or not _positive_int(record.get("createdAt"))
        or not _positive_int(record.get("updatedAt"))
        or not _positive_int(record.get("spoolId"))
        or not isinstance(grams, (int, float)) or isinstance(grams, bool)
        or not math.isfinite(grams)
        or grams <= 0
        or not isinstance(status, str) or status not in _BOOKING_STATES
    ):
        raise HaspelCutoverPreviewRejected()
    if status == "booked":
        result = _object(record.get("result"))
        if result.get("id") != record["spoolId"]:
            raise HaspelCutoverPreviewRejected()
    cost = record.get("cost")
    if cost is not None:
        cost_record = _object(cost)
        cost_minor = cost_record.get("costMinor")
        currency = cost_record.get("currency")
        if (
            not isinstance(cost_minor, int) or isinstance(cost_minor, bool) or cost_minor < 0
            or not isinstance(currency, str)
            or currency not in {"UAH", "EUR", "USD", "PLN"}
        ):
            raise HaspelCutoverPreviewRejected()
    return record


def _valid_weighing(value: object) -> dict[str, object]:
    record = _object(value)
    status = record.get("status")
    identity = record.get("id")
    request_hash = record.get("requestHash")
    source = record.get("source")
    net_milligrams = record.get("netMilligrams")
    if (
        not isinstance(status, str) or status not in _WEIGHING_STATES
        or not isinstance(identity, str) or len(identity) > 64
        or not isinstance(request_hash, str) or _DIGEST.fullmatch(request_hash) is None
        or not isinstance(source, str) or _DIGEST.fullmatch(source) is None
        or not _positive_int(record.get("spoolId"))
        or type(net_milligrams) is not int or net_milligrams < 0
        or not _positive_int(record.get("createdAt"))
    ):
        raise HaspelCutoverPreviewRejected()
    return record


def _valid_profile(value: object) -> None:
    record = _object(value)
    price_minor = record.get("priceMinor")
    basis_milligrams = record.get("basisMilligrams")
    currency = record.get("currency")
    source = record.get("source")
    if (
        not _positive_int(record.get("spoolId"))
        or type(price_minor) is not int or price_minor < 0
        or type(basis_milligrams) is not int or basis_milligrams <= 0
        or not isinstance(currency, str) or currency not in {"UAH", "EUR", "USD", "PLN"}
        or not _positive_int(record.get("revision"))
        or not isinstance(source, str) or _DIGEST.fullmatch(source) is None
    ):
        raise HaspelCutoverPreviewRejected()


def preview_haspelsync_cutover(
    bookings_path: Path, accounting_path: Path, printer_serial: str,
) -> HaspelCutoverPreview:
    """Count unresolved attempts for one serial and global weighings; never writes."""
    serial = printer_serial.strip().upper()
    if not 1 <= len(serial) <= 64 or any(ord(char) < 33 for char in serial):
        raise HaspelCutoverPreviewRejected()
    bookings_bytes, raw_bookings = _read(bookings_path)
    accounting_bytes, raw_accounting = _read(accounting_path)
    bookings = _object(raw_bookings)
    accounting = _object(raw_accounting)
    raw_records = bookings.get("records")
    raw_weighings = accounting.get("weighings")
    profiles = accounting.get("profiles")
    if (
        type(bookings.get("schemaVersion")) is not int
        or bookings["schemaVersion"] != 1
        or not isinstance(raw_records, dict) or len(raw_records) > MAX_RECORDS
        or type(accounting.get("schemaVersion")) is not int
        or accounting["schemaVersion"] != 1
        or not isinstance(profiles, dict) or len(profiles) > MAX_RECORDS
        or not isinstance(raw_weighings, list) or len(raw_weighings) > MAX_RECORDS
    ):
        raise HaspelCutoverPreviewRejected()

    for profile in profiles.values():
        _valid_profile(profile)

    booking_counts = {status: 0 for status in _BOOKING_STATES}
    latest_activity_at_ms = 0
    for key, value in raw_records.items():
        record = _valid_booking(key, value)
        printer_id = cast(str, record["printerId"])
        status = cast(str, record["status"])
        if printer_id.strip().upper() == serial:
            booking_counts[status] += 1
            latest_activity_at_ms = max(latest_activity_at_ms, cast(int, record["updatedAt"]))

    weighing_counts = {status: 0 for status in _WEIGHING_STATES}
    for value in raw_weighings:
        record = _valid_weighing(value)
        weighing_counts[cast(str, record["status"])] += 1
        latest_activity_at_ms = max(latest_activity_at_ms, cast(int, record["createdAt"]))

    booking_digest = hashlib.sha256(bookings_bytes).hexdigest()
    accounting_digest = hashlib.sha256(accounting_bytes).hexdigest()
    evidence = json.dumps({
        "schema": "ufm-haspelsync-cutover-preview-v1",
        "printer_serial": serial,
        "bookings_sha256": booking_digest,
        "accounting_sha256": accounting_digest,
        "printer_bookings": booking_counts,
        "global_weighings": weighing_counts,
        "latest_activity_at_ms": latest_activity_at_ms,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return HaspelCutoverPreview(
        printer_serial=serial,
        evidence_sha256=hashlib.sha256(evidence.encode("ascii")).hexdigest(),
        printer_bookings=(
            booking_counts["pending"], booking_counts["booked"],
            booking_counts["uncertain"], booking_counts["dismissed"],
        ),
        global_weighings=(
            weighing_counts["pending"], weighing_counts["recorded"],
            weighing_counts["uncertain"], weighing_counts["rejected"],
        ),
        latest_activity_at_ms=latest_activity_at_ms,
    )
