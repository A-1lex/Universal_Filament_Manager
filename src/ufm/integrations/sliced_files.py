"""Bounded offline sliced-3MF facts; no extrusion interpretation or accounting."""
from __future__ import annotations

import hashlib
import io
import re
import stat
import struct
import unicodedata
import zipfile
import zlib
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from ufm.application.dto.slice_facts import FilamentFact as FilamentFact
from ufm.application.dto.slice_facts import LayerFilamentFact as LayerFilamentFact
from ufm.application.dto.slice_facts import VerifiedSliceFacts as VerifiedSliceFacts

PARSER_VERSION = "sliced-3mf-v1"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ENTRIES = 2048
MAX_DECLARED_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 512 * 1024
MAX_GCODE_BYTES = 64 * 1024 * 1024


class SlicedFileRejected(ValueError):
    """Stable rejection codes do not disclose source filenames or content."""

    def __init__(self, code: str = "slice.invalid") -> None:
        super().__init__(code)


def _integer(value: str | None, minimum: int, maximum: int) -> int:
    if value is None or len(value) > 10 or re.fullmatch(r"[0-9]+", value) is None:
        raise SlicedFileRejected("slice.metadata_invalid")
    number = int(value)
    if not minimum <= number <= maximum:
        raise SlicedFileRejected("slice.metadata_invalid")
    return number


def _decimal(value: str | None, maximum: int) -> Decimal:
    if (value is None or len(value) > 24
            or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is None):
        raise SlicedFileRejected("slice.metadata_invalid")
    number = Decimal(value)
    if not number.is_finite() or number > maximum:
        raise SlicedFileRejected("slice.metadata_invalid")
    return number


def _optional(element: ET.Element, key: str) -> str | None:
    value = element.get(key)
    if value is not None and (not value or len(value) > 256):
        raise SlicedFileRejected("slice.metadata_invalid")
    return value


def _xml(data: bytes) -> ET.Element:
    text = data.decode("utf-8-sig", errors="strict")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise SlicedFileRejected("slice.xml_invalid")
    declaration = re.match(r"\s*<\?xml\b[^?]*\?>", text)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)['\"]", declaration[0])
        if encoding and encoding[1].lower() not in {"utf-8", "utf8"}:
            raise SlicedFileRejected("slice.xml_invalid")
    parser = ET.XMLPullParser(events=("start", "end"))
    depth = nodes = attributes = 0
    root: ET.Element | None = None
    for offset in range(0, len(text), 4096):
        parser.feed(text[offset:offset + 4096])
        for event, element in cast(Iterator[tuple[str, ET.Element]], parser.read_events()):
            if event == "start":
                depth += 1
                nodes += 1
                attributes += len(element.attrib)
                if (depth > 16 or nodes > 8192 or len(element.attrib) > 32
                        or attributes > 32768 or len(element.tag) > 128
                        or any(len(k) > 128 or len(v) > 4096
                               for k, v in element.attrib.items())):
                    raise SlicedFileRejected("slice.xml_invalid")
                if root is None:
                    root = element
            else:
                depth -= 1
    parser.close()
    if root is None or root.tag != "config":
        raise SlicedFileRejected("slice.xml_invalid")
    return root


def _facts(root: ET.Element, plate: int) -> tuple[
    tuple[FilamentFact, ...], tuple[LayerFilamentFact, ...],
    tuple[tuple[str, str], ...], str,
]:
    selected: ET.Element | None = None
    plate_ids: set[int] = set()
    for candidate in root.findall("plate"):
        indexes = [m.get("value") for m in candidate.findall("metadata")
                   if m.get("key") == "index"]
        if len(indexes) != 1:
            raise SlicedFileRejected("slice.metadata_invalid")
        index = _integer(indexes[0], 1, 1_000_000)
        if index in plate_ids:
            raise SlicedFileRejected("slice.metadata_invalid")
        plate_ids.add(index)
        ids = [_integer(f.get("id"), 1, 256) for f in candidate.findall("filament")]
        if len(ids) != len(set(ids)):
            raise SlicedFileRejected("slice.metadata_invalid")
        if index == plate:
            selected = candidate
    if selected is None:
        raise SlicedFileRejected("slice.plate_missing")
    normalized = ET.Element("config")
    target = ET.SubElement(normalized, "plate")
    metadata: dict[str, str] = {}
    for item in selected.findall("metadata"):
        key, value = item.get("key"), item.get("value")
        if not key or value is None or key in metadata or len(key) > 128 or len(value) > 512:
            raise SlicedFileRejected("slice.metadata_invalid")
        metadata[key] = value
        ET.SubElement(target, "metadata", key=key, value=value)
    filaments: list[FilamentFact] = []
    for element in selected.findall("filament"):
        fid = _integer(element.get("id"), 1, 256)
        grams = _decimal(element.get("used_g"), 10_000)
        used_m = element.get("used_m")
        fact = FilamentFact(fid, fid - 1, element.attrib["used_g"],
                            int((grams * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
                            None if used_m is None else _decimal(used_m, 1_000_000),
                            _optional(element, "tray_info_idx"), _optional(element, "color"),
                            _optional(element, "type"))
        filaments.append(fact)
        attrs = {"id": str(fid), "used_g": format(grams, "f")}
        if fact.used_m is not None:
            attrs["used_m"] = format(fact.used_m, "f")
        for key in ("tray_info_idx", "color", "type"):
            value = getattr(fact, key)
            if value is not None:
                attrs[key] = value
        ET.SubElement(target, "filament", attrs)
    if not filaments:
        raise SlicedFileRejected("slice.metadata_invalid")
    known = {fact.logical_material for fact in filaments}
    layers: list[LayerFilamentFact] = []
    if len(selected.findall("layer_filament_lists")) > 1:
        raise SlicedFileRejected("slice.metadata_invalid")
    for element in selected.findall("layer_filament_lists/layer_filament_list"):
        materials = tuple(_integer(s, 0, 255)
                          for s in element.get("filament_list", "").split())
        # Bambu may leave an empty, unused tail entry after the actual layers.
        # HaspelSync ignores it; it must not inflate progress or block intake.
        if not materials:
            continue
        if len(materials) != len(set(materials)) or not set(materials) <= known:
            raise SlicedFileRejected("slice.metadata_invalid")
        ranges: list[tuple[int, int]] = []
        for pair in element.get("layer_ranges", "").split(","):
            tokens = pair.split()
            if len(tokens) != 2:
                raise SlicedFileRejected("slice.metadata_invalid")
            start, end = (_integer(t, 0, 1_000_000) for t in tokens)
            if start > end or (ranges and start <= ranges[-1][1]):
                raise SlicedFileRejected("slice.metadata_invalid")
            ranges.append((start, end))
        if len(ranges) > 1024 or len(layers) >= 2048:
            raise SlicedFileRejected("slice.metadata_invalid")
        layers.append(LayerFilamentFact(materials, tuple(ranges)))
    if layers:
        group = ET.SubElement(target, "layer_filament_lists")
        for layer in layers:
            ET.SubElement(group, "layer_filament_list",
                          filament_list=" ".join(map(str, layer.logical_materials)),
                          layer_ranges=",".join(f"{a} {b}" for a, b in layer.layer_ranges))
    return tuple(filaments), tuple(layers), tuple(metadata.items()), ET.tostring(
        normalized, encoding="unicode")


def _entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise SlicedFileRejected("slice.zip_limit")
    total = 0
    seen: set[str] = set()
    result: dict[str, zipfile.ZipInfo] = {}
    for entry in entries:
        name = entry.orig_filename
        normalized = unicodedata.normalize("NFC", name).casefold()
        components = name.rstrip("/").split("/")
        if (not name or name != entry.filename or name.startswith("/")
                or "\\" in name or ":" in name or "\x00" in name
                or any(part in {"", ".", ".."} for part in components)
                or normalized in seen or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.flag_bits & 1
                or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
            raise SlicedFileRejected("slice.zip_invalid")
        seen.add(normalized)
        total += entry.file_size
        if total > MAX_DECLARED_BYTES or entry.file_size > max(entry.compress_size, 1) * 200:
            raise SlicedFileRejected("slice.zip_limit")
        result[name] = entry
    return result


def _preflight_directory(data: bytes) -> None:
    # ZipFile eagerly creates central-directory objects. Bound that allocation
    # before invoking it, rather than checking only after millions of entries.
    offset = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if offset < 0 or offset + 22 > len(data):
        raise SlicedFileRejected("slice.zip_invalid")
    _, disk, directory_disk, local_count, count, size, start, comment = struct.unpack_from(
        "<4s4H2LH", data, offset)
    if (disk or directory_disk or local_count != count or count == 65535
            or size == 0xFFFFFFFF or start == 0xFFFFFFFF):
        raise SlicedFileRejected("slice.zip_unsupported")
    if (count > MAX_ENTRIES or size > 16 * 1024 * 1024 or size < 46 * count
            or start + size != offset or offset + 22 + comment != len(data)):
        raise SlicedFileRejected("slice.zip_limit")


def _read(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, limit: int) -> bytes:
    if entry.file_size > limit:
        raise SlicedFileRejected("slice.zip_limit")
    with archive.open(entry) as stream:
        data = stream.read(limit + 1)
        if len(data) > limit or len(data) != entry.file_size or stream.read(1):
            raise SlicedFileRejected("slice.zip_limit")
    return data


def inspect_3mf_bytes(data: bytes, *, plate: int, expected_sha256: str) -> VerifiedSliceFacts:
    """Verify exact archive bytes and selected metadata without extracting ZIP paths."""
    if type(plate) is not int or not 1 <= plate <= 1_000_000:
        raise SlicedFileRejected("slice.plate_invalid")
    if (not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
        raise SlicedFileRejected("slice.hash_invalid")
    if not isinstance(data, bytes) or len(data) > MAX_ARCHIVE_BYTES:
        raise SlicedFileRejected("slice.archive_limit")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise SlicedFileRejected("slice.hash_mismatch")
    _preflight_directory(data)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = _entries(archive)
            metadata_entry = entries.get("Metadata/slice_info.config")
            gcode_entry = entries.get(f"Metadata/plate_{plate}.gcode")
            if metadata_entry is None or gcode_entry is None:
                raise SlicedFileRejected("slice.entry_missing")
            metadata_bytes = _read(archive, metadata_entry, MAX_METADATA_BYTES)
            root = _xml(metadata_bytes)
            filaments, layers, metadata, normalized = _facts(root, plate)
            gcode = _read(archive, gcode_entry, MAX_GCODE_BYTES)
    except SlicedFileRejected:
        raise
    except (OSError, EOFError, RuntimeError, ValueError, UnicodeError,
            ET.ParseError, zipfile.BadZipFile, zlib.error):
        raise SlicedFileRejected() from None
    return VerifiedSliceFacts(PARSER_VERSION, digest, plate,
                              hashlib.sha256(metadata_bytes).hexdigest(),
                              hashlib.sha256(gcode).hexdigest(), filaments, layers,
                              metadata, normalized, gcode)


def inspect_3mf_file(path: str | Path, *, plate: int, expected_sha256: str) -> VerifiedSliceFacts:
    """Read at most the archive cap plus one byte; hash the same bytes later parsed."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_ARCHIVE_BYTES + 1)
    except OSError:
        raise SlicedFileRejected("slice.file_unreadable") from None
    return inspect_3mf_bytes(data, plate=plate, expected_sha256=expected_sha256)


def inspect_3mf_file_for_local_review(path: str | Path, *, plate: int) -> VerifiedSliceFacts:
    """Inspect an explicitly selected local file without trusting a prior digest.

    The digest is derived from the same bounded byte sequence that is parsed. This
    entry point is for a read-only UI review; it does not persist artifacts or bind
    the file to a job. Accounting paths must continue to supply their expected hash
    through :func:`inspect_3mf_file`.
    """
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_ARCHIVE_BYTES + 1)
    except OSError:
        raise SlicedFileRejected("slice.file_unreadable") from None
    digest = hashlib.sha256(data).hexdigest()
    return inspect_3mf_bytes(data, plate=plate, expected_sha256=digest)


def list_3mf_plates_for_local_review(path: str | Path) -> tuple[int, ...]:
    """Return bounded metadata plates that have a corresponding sliced G-code entry."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_ARCHIVE_BYTES + 1)
        if not isinstance(data, bytes) or len(data) > MAX_ARCHIVE_BYTES:
            raise SlicedFileRejected("slice.archive_limit")
        _preflight_directory(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = _entries(archive)
            metadata_entry = entries.get("Metadata/slice_info.config")
            if metadata_entry is None:
                raise SlicedFileRejected("slice.entry_missing")
            root = _xml(_read(archive, metadata_entry, MAX_METADATA_BYTES))
            plates: list[int] = []
            seen: set[int] = set()
            for candidate in root.findall("plate"):
                indexes = [item.get("value") for item in candidate.findall("metadata")
                           if item.get("key") == "index"]
                if len(indexes) != 1:
                    raise SlicedFileRejected("slice.metadata_invalid")
                plate = _integer(indexes[0], 1, 1_000_000)
                if plate in seen:
                    raise SlicedFileRejected("slice.metadata_invalid")
                seen.add(plate)
                if f"Metadata/plate_{plate}.gcode" not in entries:
                    continue
                _facts(root, plate)
                plates.append(plate)
    except SlicedFileRejected:
        raise
    except (OSError, EOFError, RuntimeError, ValueError, UnicodeError,
            ET.ParseError, zipfile.BadZipFile, zlib.error):
        raise SlicedFileRejected() from None
    if not plates:
        raise SlicedFileRejected("slice.plate_missing")
    return tuple(sorted(plates))
