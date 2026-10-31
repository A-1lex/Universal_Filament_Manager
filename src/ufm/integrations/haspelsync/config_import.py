"""Offline preview of non-secret HaspelSync printer and slot assignments."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ufm.domain.value_objects import EntityId

MAX_PRINTERS_FILE_BYTES = 1 * 1024 * 1024
MAX_MAPPINGS_FILE_BYTES = 8 * 1024 * 1024
MAX_ID_MAP_FILE_BYTES = 8 * 1024 * 1024
MAX_PRINTERS = 64
MAX_SLOT_MAPPINGS = 20_000
MAX_ID_MAP_RECORDS = 30_000


class HaspelSyncImportRejected(ValueError):
    """A malformed or unsupported HaspelSync export, without source details."""

    def __init__(self) -> None:
        super().__init__("haspelsync.import_rejected")


@dataclass(frozen=True, slots=True)
class HaspelPrinterPreview:
    serial_number: str
    display_name: str
    has_private_lan_address: bool
    credential_required: bool = True


@dataclass(frozen=True, slots=True)
class HaspelMappingPreview:
    printer_serial: str
    source_slot_label: str
    external_spool_id: int
    ufm_spool_id: str | None
    provider_system_key: str | None
    provider_slot_key: str | None
    fingerprint_present: bool
    was_automatic: bool
    conflict: bool


@dataclass(frozen=True, slots=True)
class HaspelSyncImportPreview:
    printers: tuple[HaspelPrinterPreview, ...]
    mappings: tuple[HaspelMappingPreview, ...]
    unresolved_spool_count: int
    unsupported_slot_count: int
    orphan_printer_count: int
    duplicate_target_spool_count: int
    credentials_imported: bool = False
    network_access_performed: bool = False
    inventory_writes_performed: bool = False


def _read_json(path: Path, *, maximum: int) -> object:
    try:
        with path.open("rb") as source:
            payload = source.read(maximum + 1)
        if len(payload) > maximum:
            raise HaspelSyncImportRejected()
        return json.loads(payload.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise HaspelSyncImportRejected() from None


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise HaspelSyncImportRejected()
    return value


def _has_private_address(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        return False
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified:
        return False
    return True


def _serial(value: object) -> str:
    if not isinstance(value, str):
        raise HaspelSyncImportRejected()
    result = value.strip().upper()
    if not 1 <= len(result) <= 64 or any(ord(char) < 33 for char in result):
        raise HaspelSyncImportRejected()
    return result


def _display_name(value: object) -> str:
    if not isinstance(value, str):
        raise HaspelSyncImportRejected()
    result = value.strip()
    if not 1 <= len(result) <= 200 or any(ord(char) < 32 for char in result):
        raise HaspelSyncImportRejected()
    return result


def _load_spool_id_map(path: Path) -> dict[int, EntityId]:
    raw = _object(_read_json(path, maximum=MAX_ID_MAP_FILE_BYTES))
    if raw.get("format") != "ufm-spoolman-id-map-v1":
        raise HaspelSyncImportRejected()
    digest = raw.get("mapping_sha256")
    records = raw.get("mappings")
    if (
        not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or not isinstance(records, list) or len(records) > MAX_ID_MAP_RECORDS
    ):
        raise HaspelSyncImportRejected()
    payload = {key: value for key, value in raw.items() if key != "mapping_sha256"}
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(digest, expected):
        raise HaspelSyncImportRejected()
    result: dict[int, EntityId] = {}
    for raw_record in records:
        record = _object(raw_record)
        if record.get("entity_type") != "spool":
            continue
        external_id = record.get("external_id")
        ufm_id = record.get("ufm_id")
        if (
            not isinstance(external_id, str) or not external_id.isascii()
            or not external_id.isdecimal() or len(external_id) > 13
            or not isinstance(ufm_id, str)
        ):
            raise HaspelSyncImportRejected()
        spool_id = int(external_id)
        if spool_id <= 0:
            raise HaspelSyncImportRejected()
        try:
            entity_id = EntityId.parse(ufm_id)
        except ValueError:
            raise HaspelSyncImportRejected() from None
        prior = result.get(spool_id)
        if prior is not None and prior != entity_id:
            raise HaspelSyncImportRejected()
        result[spool_id] = entity_id
    return result


def _slot_crosswalk(label: str, schema_version: int) -> tuple[str, str] | None:
    value = label.strip()
    if schema_version < 1:
        legacy = re.fullmatch(r"([A-D])([0-3])", value)
        if legacy:
            value = f"{legacy.group(1)}{int(legacy.group(2)) + 1}"
    regular = re.fullmatch(r"([A-D])([1-4])", value)
    if regular:
        unit = ord(regular.group(1)) - ord("A")
        slot = int(regular.group(2)) - 1
        return f"ams:{unit}", f"{unit}:{slot}"
    ht = re.fullmatch(r"HT-([A-H])", value, flags=re.IGNORECASE)
    if ht:
        unit = 128 + ord(ht.group(1).upper()) - ord("A")
        return f"ams:{unit}", f"{unit}:0"
    if value.casefold() == "external":
        return "external", "external"
    return None


def preview_haspelsync_files(
    printers_path: Path, mappings_path: Path, id_map_path: Path,
) -> HaspelSyncImportPreview:
    """Preview printer fields and slot mappings, deliberately excluding secrets and writes."""
    raw_printers = _read_json(printers_path, maximum=MAX_PRINTERS_FILE_BYTES)
    raw_mappings = _object(_read_json(mappings_path, maximum=MAX_MAPPINGS_FILE_BYTES))
    spool_id_map = _load_spool_id_map(id_map_path)
    if not isinstance(raw_printers, list) or len(raw_printers) > MAX_PRINTERS:
        raise HaspelSyncImportRejected()
    printers: list[HaspelPrinterPreview] = []
    printer_serials: set[str] = set()
    for raw_printer in raw_printers:
        entry = _object(raw_printer)
        serial = _serial(entry.get("id"))
        if serial in printer_serials:
            raise HaspelSyncImportRejected()
        printer_serials.add(serial)
        printers.append(HaspelPrinterPreview(
            serial_number=serial,
            display_name=_display_name(entry.get("name")),
            has_private_lan_address=_has_private_address(entry.get("ip")),
        ))

    wrapped = isinstance(raw_mappings.get("printers"), dict)
    schema_version = raw_mappings.get("schemaVersion", 1 if wrapped else 0)
    assignments = raw_mappings["printers"] if wrapped else raw_mappings
    if (
        type(schema_version) is not int or schema_version not in (0, 1)
        or not isinstance(assignments, dict) or len(assignments) > MAX_PRINTERS
    ):
        raise HaspelSyncImportRejected()
    mappings: list[HaspelMappingPreview] = []
    target_spool_counts: dict[str, int] = {}
    seen_assignment_serials: set[str] = set()
    unresolved = unsupported = orphan = 0
    for raw_serial, raw_slots in assignments.items():
        if not isinstance(raw_serial, str) or not isinstance(raw_slots, dict):
            raise HaspelSyncImportRejected()
        serial = _serial(raw_serial)
        if serial in seen_assignment_serials:
            raise HaspelSyncImportRejected()
        seen_assignment_serials.add(serial)
        if serial not in printer_serials:
            orphan += len(raw_slots)
            continue
        if len(raw_slots) > MAX_SLOT_MAPPINGS - len(mappings):
            raise HaspelSyncImportRejected()
        for raw_label, raw_mapping in raw_slots.items():
            if not isinstance(raw_label, str) or len(raw_label) > 32:
                raise HaspelSyncImportRejected()
            item = _object(raw_mapping)
            external_spool_id = item.get("spoolId")
            if type(external_spool_id) is not int or not 1 <= external_spool_id <= 10**12:
                raise HaspelSyncImportRejected()
            fingerprint = item.get("fingerprint")
            automatic = item.get("automatic", False)
            if (
                (fingerprint is not None and (not isinstance(fingerprint, str) or len(fingerprint) > 512))
                or type(automatic) is not bool
            ):
                raise HaspelSyncImportRejected()
            crosswalk = _slot_crosswalk(raw_label, schema_version)
            target_id = spool_id_map.get(external_spool_id)
            if crosswalk is None:
                unsupported += 1
            if target_id is None:
                unresolved += 1
            conflict = target_id is not None and str(target_id) in target_spool_counts
            if target_id is not None:
                target_spool_counts[str(target_id)] = target_spool_counts.get(str(target_id), 0) + 1
            mappings.append(HaspelMappingPreview(
                printer_serial=serial,
                source_slot_label=raw_label,
                external_spool_id=external_spool_id,
                ufm_spool_id=None if target_id is None else str(target_id),
                provider_system_key=None if crosswalk is None else crosswalk[0],
                provider_slot_key=None if crosswalk is None else crosswalk[1],
                fingerprint_present=isinstance(fingerprint, str) and bool(fingerprint),
                was_automatic=automatic,
                conflict=conflict,
            ))
    return HaspelSyncImportPreview(
        printers=tuple(printers), mappings=tuple(mappings),
        unresolved_spool_count=unresolved, unsupported_slot_count=unsupported,
        orphan_printer_count=orphan,
        duplicate_target_spool_count=sum(count > 1 for count in target_spool_counts.values()),
    )
