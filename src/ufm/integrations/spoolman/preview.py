"""Independent implementation of the public Spoolman v1 spool-list format.

No upstream code is vendored. External IDs are scoped to an opaque source instance,
never UFM UUIDs. This adapter has no network, filesystem or persistence authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal

from ufm.domain.value_objects import MAX_ABS_MILLIGRAMS, Mass


class PreviewRejected(ValueError):
    """Sanitized failure: never echoes input or decoder exceptions."""

    def __init__(self) -> None:
        super().__init__("spoolman.preview_rejected")


@dataclass(frozen=True, slots=True)
class SpoolPreview:
    source_key: tuple[str, int]
    filament_id: int
    name: str | None
    material: str | None
    vendor: str | None
    location: str | None
    estimated_remaining: Mass | None
    archived: bool


@dataclass(frozen=True, slots=True)
class ImportPreview:
    source_fingerprint: str
    spools: tuple[SpoolPreview, ...]
    warnings: tuple[str, ...] = ("spoolman.preview_only",)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PreviewRejected()
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise PreviewRejected()


def _bounded_text(payload: bytes) -> str:
    text = payload.decode("utf-8")
    depth = 0
    quoted = escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > 32:
                raise PreviewRejected()
        elif character in "]}":
            depth -= 1
    return text


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PreviewRejected()
    return value


def _identifier(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise PreviewRejected()
    return value


def _text(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 500 or any(ord(c) < 32 for c in value):
        raise PreviewRejected()
    return value


def _mass(value: object) -> Mass | None:
    if value is None:
        return None
    if type(value) not in (int, Decimal):
        raise PreviewRejected()
    assert isinstance(value, (int, Decimal))
    quantity = Decimal(value)
    if not quantity.is_finite() or not 0 <= quantity <= Decimal(MAX_ABS_MILLIGRAMS) / 1000:
        raise PreviewRejected()
    if quantity != quantity.quantize(Decimal("0.001")):
        raise PreviewRejected()
    return Mass.from_grams(quantity)


def preview_spools(
    payload: bytes,
    *,
    source_instance: str,
    max_input_bytes: int = 4 * 1024 * 1024,
    max_spools: int = 10_000,
) -> ImportPreview:
    """Review GET /api/v1/spool JSON; not a CSV/backup or a committed import.

    Unknown stays unknown. No inferred tare subtraction or history import occurs.
    Invalid rows reject the whole input. An explicit future command must authorize
    UUID mapping, opening basis, audit and idempotent persistence separately.
    """
    if (type(source_instance) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", source_instance) is None
        or type(max_input_bytes) is not int or not 1 <= max_input_bytes <= 32 * 1024 * 1024
        or type(max_spools) is not int or not 1 <= max_spools <= 10_000
        or type(payload) is not bytes or len(payload) > max_input_bytes):
        raise PreviewRejected()
    try:
        data = json.loads(_bounded_text(payload), parse_float=Decimal,
                          parse_constant=_constant, object_pairs_hook=_object)
        if type(data) is not list or len(data) > max_spools:
            raise PreviewRejected()
        rows: list[SpoolPreview] = []
        seen: set[int] = set()
        for value in data:
            row = _mapping(value)
            spool_id = _identifier(row.get("id"))
            if spool_id in seen:
                raise PreviewRejected()
            seen.add(spool_id)
            filament = _mapping(row.get("filament"))
            vendor = filament.get("vendor")
            archived = row.get("archived")
            if type(archived) is not bool:
                raise PreviewRejected()
            rows.append(SpoolPreview(
                source_key=(source_instance, spool_id),
                filament_id=_identifier(filament.get("id")),
                name=_text(filament.get("name")), material=_text(filament.get("material")),
                vendor=None if vendor is None else _text(_mapping(vendor).get("name")),
                location=_text(row.get("location")),
                estimated_remaining=_mass(row.get("remaining_weight")), archived=archived,
            ))
        return ImportPreview(hashlib.sha256(payload).hexdigest(), tuple(rows))
    except (ValueError, TypeError, ArithmeticError, RecursionError):
        raise PreviewRejected() from None
