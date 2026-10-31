"""Backup-first import of the public Spoolman SQLite inventory into UFM."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import insert, inspect, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from ufm.application.inventory import InventoryCommands
from ufm.application.storage import StorageCommands
from ufm.domain.enums import MaterialType, SpoolLifecycle, StorageType
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.backup.sqlite_snapshot import create_snapshot
from ufm.infrastructure.persistence.models.schema import (
    brand,
    device_identity,
    filament_profile,
    spoolman_import_source,
)
from ufm.infrastructure.persistence.models.schema import (
    spool as ufm_spool,
)
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine, immediate_transaction
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.platform.common.paths import AppPaths

MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_CUTOVER_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SPOOLS = 10_000
_REQUIRED_COLUMNS = {
    "vendor": {"id", "name", "empty_spool_weight"},
    "filament": {"id", "name", "vendor_id", "material", "density", "diameter",
                 "weight", "spool_weight", "color_hex"},
    "spool": {"id", "filament_id", "used_weight", "archived", "initial_weight",
              "spool_weight", "location", "lot_nr"},
}
_MATERIAL_TYPES = {item.value for item in MaterialType if item is not MaterialType.CUSTOM}


class SpoolmanImportRejected(ValueError):
    """A sanitized source or import failure."""

    def __init__(self) -> None:
        super().__init__("spoolman.import_rejected")


@dataclass(frozen=True, slots=True)
class SpoolmanImportPreview:
    spool_count: int
    filament_count: int
    vendor_count: int
    known_stock_count: int
    unknown_stock_count: int
    archived_count: int
    purchase_price_count: int = 0
    purchase_price_not_imported_count: int = 0
    lot_number_count: int = 0
    color_count: int = 0
    location_count: int = 0
    unsupported_metadata_count: int = 0
    source_fingerprint: str = ""
    suggested_source_instance_key: str = ""
    source_instances: tuple[SpoolmanImportSourceInfo, ...] = ()
    spools: tuple[SpoolmanSpoolPreview, ...] = ()


@dataclass(frozen=True, slots=True)
class SpoolmanSpoolPreview:
    """Bounded, row-level summary of the values an import can carry over."""

    spool_id: int
    filament_id: int
    name: str
    material: str
    vendor: str | None
    nominal_mg: int | None
    empty_spool_mg: int | None
    remaining_mg: int | None
    archived: bool
    purchase_price: str | None
    purchase_basis_mg: int | None
    currency: str | None
    lot_number: str | None
    color_hex: str | None
    location: str | None
    omitted_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpoolmanImportSourceInfo:
    source_instance_key: str
    device_id: str
    display_name: str
    created_at: str
    last_seen_at: str
    snapshot_sha256: str | None
    recovery_counts: tuple[int, int, int, int, int] | None = None


def spoolman_import_source_label(
    source: SpoolmanImportSourceInfo, *, unverified_label: str,
    recovery_label: str | None = None,
) -> str:
    """Mark sources with no completed import snapshot so an operator can resume carefully."""
    label = f"{source.display_name} · {source.source_instance_key}"
    if source.snapshot_sha256 is None:
        label = f"{label} — {unverified_label}"
        if source.recovery_counts is not None and recovery_label is not None:
            total, matched, mismatch, missing, extra = source.recovery_counts
            return f"{label} · {recovery_label.format(total=total, matched=matched, mismatch=mismatch, missing=missing, extra=extra)}"
    return label


def default_spoolman_import_source_key(
    sources: tuple[SpoolmanImportSourceInfo, ...], suggested_key: str,
) -> str | None:
    """Prefer the exact path match, then a sole registered source after a move."""
    if any(item.source_instance_key == suggested_key for item in sources):
        return suggested_key
    if len(sources) == 1:
        return sources[0].source_instance_key
    return None


@dataclass(frozen=True, slots=True)
class SpoolmanImportResult:
    preview: SpoolmanImportPreview
    source_backup: Path
    target_backup: Path | None
    mapping_report: Path
    processed_count: int
    source_instance_key: str


@dataclass(frozen=True, slots=True)
class SpoolmanCutoverPreview:
    source_instance_key: str
    source_fingerprint: str
    source_unchanged_since_import: bool
    last_imported_at_ms: int
    spool_count: int
    matched_count: int
    mismatch_count: int
    missing_count: int
    unexpected_count: int

    @property
    def ready(self) -> bool:
        return (
            self.source_unchanged_since_import
            and self.matched_count == self.spool_count
            and self.mismatch_count == 0
            and self.missing_count == 0
            and self.unexpected_count == 0
        )


@dataclass(frozen=True, slots=True)
class _SpoolRow:
    spool_id: int
    filament_id: int
    name: str
    material: str
    vendor_id: int | None
    vendor: str | None
    diameter_mm: Decimal
    density_g_cm3: Decimal | None
    nominal_filament_g: Decimal | None
    empty_spool_g: Decimal | None
    remaining_g: Decimal | None
    archived: bool
    purchase_price: ExactDecimal | None
    purchase_basis_g: Decimal | None
    currency: str | None
    lot_number: str | None
    color_hex: str | None
    location: str | None
    unsupported_fields: tuple[str, ...]
    price_not_imported: bool


def _entity_id(source_key: str) -> EntityId:
    return EntityId.parse(str(uuid5(NAMESPACE_URL, source_key)))


def _number(value: object, *, positive: bool = False) -> Decimal | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise SpoolmanImportRejected()
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise SpoolmanImportRejected() from None
    if not number.is_finite() or (positive and number <= 0):
        raise SpoolmanImportRejected()
    return number


def _text(value: object, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if type(value) is not str or len(value) > 1024 or any(ord(c) < 32 for c in value):
        raise SpoolmanImportRejected()
    result = value.strip()
    if required and not result:
        raise SpoolmanImportRejected()
    return result or None


def _label(value: object) -> str:
    result = _text(value, required=True)
    if result is None or len(result) > 200:
        raise SpoolmanImportRejected()
    return result


def _color(value: object) -> str | None:
    color = _text(value)
    if color is None:
        return None
    return color if len(color) in (7, 9) and color.startswith("#") and all(
        character in "0123456789abcdefABCDEF" for character in color[1:]
    ) else None


def _mass(value_g: Decimal | None) -> Mass | None:
    if value_g is None:
        return None
    milligrams = (value_g * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if not milligrams.is_finite() or abs(milligrams) > Decimal("9000000000000000"):
        raise SpoolmanImportRejected()
    return Mass(int(milligrams))


def _milligrams(value_g: Decimal | None) -> int | None:
    mass = _mass(value_g)
    return None if mass is None else mass.milligrams


def _price(value: object) -> ExactDecimal | None:
    number = _number(value)
    if number is None:
        return None
    if number < 0:
        raise SpoolmanImportRejected()
    canonical = format(number, "f").rstrip("0").rstrip(".") if number else "0"
    whole, _, fraction = canonical.partition(".")
    if len(whole) > 9 or len(fraction) > 2 or len(canonical) > 30:
        raise SpoolmanImportRejected()
    return ExactDecimal(number)


def _currency(connection: sqlite3.Connection, tables: dict[str, set[str]]) -> str | None:
    if "setting" not in tables or not {"key", "value"} <= tables["setting"]:
        return None
    try:
        row = connection.execute(
            "SELECT value FROM setting WHERE key='currency' LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
    except (sqlite3.Error, TypeError, ValueError):
        return None
    if (type(value) is not str or len(value) != 3 or not value.isascii()
        or not value.isalpha() or value != value.upper()):
        return None
    return value


def _source_tables(connection: sqlite3.Connection) -> dict[str, set[str]]:
    return {
        row["name"]: {column["name"] for column in connection.execute(
            f'PRAGMA table_info("{row["name"]}")'
        )}
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('vendor','filament','spool','setting')"
        )
    }


def _open_source(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.stat().st_size > MAX_SOURCE_BYTES:
        raise SpoolmanImportRejected()
    if str(resolved).startswith("\\\\"):
        raise SpoolmanImportRejected()
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        if [tuple(row) for row in connection.execute("PRAGMA integrity_check")] != [("ok",)]:
            raise SpoolmanImportRejected()
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise SpoolmanImportRejected()
        tables = _source_tables(connection)
        if any(table not in tables or not columns <= tables[table]
               for table, columns in _REQUIRED_COLUMNS.items()):
            raise SpoolmanImportRejected()
        return connection
    except SpoolmanImportRejected:
        if connection is not None:
            connection.close()
        raise
    except (OSError, sqlite3.Error):
        if connection is not None:
            connection.close()
        raise SpoolmanImportRejected() from None


def _load_rows(path: Path) -> tuple[list[_SpoolRow], SpoolmanImportPreview]:
    connection = _open_source(path)
    try:
        tables = _source_tables(connection)
        spool_count = connection.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
        if type(spool_count) is not int or spool_count > MAX_SPOOLS:
            raise SpoolmanImportRejected()
        vendor_rows = {
            row["id"]: row for row in connection.execute(
                "SELECT id,name,empty_spool_weight FROM vendor"
            )
        }
        filament_rows = {
            row["id"]: row for row in connection.execute(
                "SELECT * FROM filament"
            )
        }
        source_currency = _currency(connection, tables)
        rows: list[_SpoolRow] = []
        known_stock = archived_count = 0
        purchase_price_count = purchase_price_not_imported_count = 0
        lot_number_count = color_count = location_count = unsupported_metadata_count = 0
        for spool in connection.execute(
            "SELECT * FROM spool ORDER BY id"
        ):
            if type(spool["id"]) is not int or spool["id"] < 1:
                raise SpoolmanImportRejected()
            filament = filament_rows.get(spool["filament_id"])
            if filament is None or type(filament["id"]) is not int or filament["id"] < 1:
                raise SpoolmanImportRejected()
            vendor_id = filament["vendor_id"]
            vendor = vendor_rows.get(vendor_id) if vendor_id is not None else None
            material = _label(filament["material"])
            diameter = _number(filament["diameter"], positive=True)
            if diameter is None:
                raise SpoolmanImportRejected()
            nominal = _number(filament["weight"])
            used = _number(spool["used_weight"])
            initial = _number(spool["initial_weight"])
            if initial is None:
                initial = nominal
            remaining = None
            if initial is not None and used is not None:
                remaining = initial - used
                if remaining < 0:
                    raise SpoolmanImportRejected()
                known_stock += 1
            archived = spool["archived"]
            if type(archived) not in (int, bool) or archived not in (0, 1):
                raise SpoolmanImportRejected()
            if archived:
                archived_count += 1
            empty_weight = _number(spool["spool_weight"])
            if empty_weight is None and vendor is not None:
                empty_weight = _number(vendor["empty_spool_weight"])
            spool_price = _price(spool["price"]) if "price" in spool.keys() else None
            filament_price = (
                _price(filament["price"]) if "price" in filament.keys() else None
            )
            selected_price = spool_price if spool_price is not None else filament_price
            purchase_basis_g = initial if initial is not None and initial > 0 else None
            imported_price = None
            imported_currency = None
            if selected_price is not None:
                if source_currency is not None and purchase_basis_g is not None:
                    imported_price = selected_price
                    imported_currency = source_currency
                    purchase_price_count += 1
                else:
                    purchase_price_not_imported_count += 1
            raw_lot = _text(spool["lot_nr"])
            raw_color = _text(filament["color_hex"])
            raw_location = _text(spool["location"])
            lot_number = raw_lot if raw_lot is not None and len(raw_lot) <= 200 else None
            color_hex = _color(raw_color)
            location = raw_location if raw_location is not None and len(raw_location) <= 200 else None
            unsupported_fields = tuple(name for name, present in (
                ("lot_nr", raw_lot is not None and lot_number is None),
                ("color_hex", raw_color is not None and color_hex is None),
                ("location", raw_location is not None and location is None),
            ) if present)
            lot_number_count += lot_number is not None
            color_count += color_hex is not None
            location_count += location is not None
            unsupported_metadata_count += sum((
                raw_lot is not None and lot_number is None,
                raw_color is not None and color_hex is None,
                raw_location is not None and location is None,
            ))
            rows.append(_SpoolRow(
                spool_id=spool["id"],
                filament_id=filament["id"],
                name=_label(filament["name"]),
                material=material or "",
                vendor_id=vendor_id,
                vendor=None if vendor is None else _label(vendor["name"]),
                diameter_mm=diameter,
                density_g_cm3=_number(filament["density"], positive=True),
                nominal_filament_g=nominal,
                empty_spool_g=empty_weight,
                remaining_g=remaining,
                archived=bool(archived),
                purchase_price=imported_price,
                purchase_basis_g=purchase_basis_g if imported_price is not None else None,
                currency=imported_currency,
                lot_number=lot_number, color_hex=color_hex, location=location,
                unsupported_fields=unsupported_fields,
                price_not_imported=(selected_price is not None and imported_price is None),
            ))
        preview_rows: list[SpoolmanSpoolPreview] = []
        for row in rows:
            omitted = row.unsupported_fields + (
                ("price",) if row.price_not_imported else ()
            )
            preview_rows.append(SpoolmanSpoolPreview(
                spool_id=row.spool_id, filament_id=row.filament_id,
                name=row.name, material=row.material, vendor=row.vendor,
                nominal_mg=_milligrams(row.nominal_filament_g),
                empty_spool_mg=_milligrams(row.empty_spool_g),
                remaining_mg=_milligrams(row.remaining_g),
                archived=row.archived,
                purchase_price=None if row.purchase_price is None else
                    row.purchase_price.canonical(),
                purchase_basis_mg=_milligrams(row.purchase_basis_g),
                currency=row.currency, lot_number=row.lot_number,
                color_hex=row.color_hex, location=row.location,
                omitted_fields=omitted,
            ))
        return rows, SpoolmanImportPreview(
            spool_count=len(rows), filament_count=len(filament_rows),
            vendor_count=len(vendor_rows), known_stock_count=known_stock,
            unknown_stock_count=len(rows) - known_stock, archived_count=archived_count,
            purchase_price_count=purchase_price_count,
            purchase_price_not_imported_count=purchase_price_not_imported_count,
            lot_number_count=lot_number_count, color_count=color_count,
            location_count=location_count,
            unsupported_metadata_count=unsupported_metadata_count,
            source_fingerprint=_rows_fingerprint(rows),
            spools=tuple(preview_rows),
        )
    except (sqlite3.Error, TypeError, ValueError, OverflowError):
        raise SpoolmanImportRejected() from None
    finally:
        connection.close()


def preview_spoolman_database(
    path: Path, *, engine: Engine | None = None,
) -> SpoolmanImportPreview:
    """Validate legacy data and return counts without writing or creating directories."""
    rows, preview = _load_rows(path)
    sources = () if engine is None else list_spoolman_import_sources(engine)
    if engine is not None:
        sources = tuple(
            replace(source, recovery_counts=_recovery_counts(
                rows, source_instance_key=source.source_instance_key,
                device_id=EntityId.parse(source.device_id), engine=engine,
            )) if source.snapshot_sha256 is None else source
            for source in sources
        )
    return replace(
        preview, source_instances=sources,
        suggested_source_instance_key=_source_instance(path),
    )


def _source_instance(path: Path) -> str:
    resolved = str(path.expanduser().resolve()).casefold()
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:24]


def _validated_source_instance_key(value: str | None, path: Path) -> str:
    if value is None:
        return _source_instance(path)
    if type(value) is not str or re.fullmatch(r"(?:[0-9a-f]{24}|[0-9a-f]{32})", value) is None:
        raise SpoolmanImportRejected()
    return value


def new_spoolman_source_key() -> str:
    """Create an opaque UFM-owned token for a newly chosen Spoolman instance."""
    return uuid4().hex


def list_spoolman_import_sources(engine: Engine) -> tuple[SpoolmanImportSourceInfo, ...]:
    if not inspect(engine).has_table("spoolman_import_source"):
        if not inspect(engine).has_table("audit_event"):
            return ()
        with engine.connect() as connection:
            rows = connection.exec_driver_sql("""
                WITH parsed AS (
                    SELECT actor_device_id AS device_id,
                           substr(correlation_id, 10,
                               instr(substr(correlation_id, 10), ':spool:') - 1)
                               AS source_instance_key,
                           created_at
                      FROM audit_event
                     WHERE event_code = 'spool.created'
                       AND correlation_id LIKE 'spoolman:%:spool:%:create'
                )
                SELECT source_instance_key, device_id,
                       MIN(created_at) AS created_at, MAX(created_at) AS last_seen_at
                  FROM parsed
                 WHERE length(source_instance_key) = 24
                   AND source_instance_key NOT GLOB '*[^0-9a-f]*'
                 GROUP BY device_id, source_instance_key
                 ORDER BY source_instance_key
            """).mappings().all()
        return tuple(SpoolmanImportSourceInfo(
            source_instance_key=row["source_instance_key"],
            device_id=row["device_id"],
            display_name=f"Legacy Spoolman import ({row['source_instance_key'][:8]})",
            created_at=row["created_at"], last_seen_at=row["last_seen_at"],
            snapshot_sha256=None,
        ) for row in rows)
    with engine.connect() as connection:
        rows = connection.execute(
            select(spoolman_import_source).order_by(
                spoolman_import_source.c.display_name,
                spoolman_import_source.c.source_instance_key,
            )
        ).mappings().all()
    return tuple(SpoolmanImportSourceInfo(
        source_instance_key=row["source_instance_key"],
        device_id=str(row["device_id"]), display_name=row["display_name"],
        created_at=row["created_at"].isoformat(), last_seen_at=row["last_seen_at"].isoformat(),
        snapshot_sha256=row["snapshot_sha256"],
    ) for row in rows)


def preview_spoolman_cutover(
    path: Path, *, engine: Engine, source_instance_key: str,
) -> SpoolmanCutoverPreview:
    """Read-only compare a bounded Spoolman snapshot with its imported UFM spools."""
    return _preview_spoolman_reconciliation(
        path, engine=engine, source_instance_key=source_instance_key,
        require_verified_snapshot=True,
    )


def preview_spoolman_import_recovery(
    path: Path, *, engine: Engine, source_instance_key: str,
) -> SpoolmanCutoverPreview:
    """Reconcile an incomplete import read-only before an operator retries it.

    This is intentionally not cutover evidence: the source record must still have
    no completed snapshot fingerprint, and the returned preview can never be ready.
    """
    key = _validated_source_instance_key(source_instance_key, path)
    source = next((item for item in list_spoolman_import_sources(engine)
                   if item.source_instance_key == key), None)
    if source is None or source.snapshot_sha256 is not None:
        raise SpoolmanImportRejected()
    preview = _preview_spoolman_reconciliation(
        path, engine=engine, source_instance_key=key,
        require_verified_snapshot=False,
    )
    if preview.source_unchanged_since_import:
        raise SpoolmanImportRejected()
    return preview


def _preview_spoolman_reconciliation(
    path: Path, *, engine: Engine, source_instance_key: str,
    require_verified_snapshot: bool,
) -> SpoolmanCutoverPreview:
    try:
        resolved = path.expanduser().resolve()
        if not resolved.is_file() or resolved.stat().st_size > MAX_CUTOVER_SOURCE_BYTES:
            raise SpoolmanImportRejected()
        key = _validated_source_instance_key(source_instance_key, resolved)
        source = next((item for item in list_spoolman_import_sources(engine)
                       if item.source_instance_key == key), None)
        if source is None or (require_verified_snapshot and source.snapshot_sha256 is None):
            raise SpoolmanImportRejected()
        last_imported_at = UtcDateTime.parse(source.last_seen_at)
        last_imported_at_ms = int(last_imported_at.value.timestamp() * 1000)
        rows, preview = _load_rows(resolved)
        total, matched, mismatch, missing, unexpected = _recovery_counts(
            rows, source_instance_key=key, device_id=EntityId.parse(source.device_id),
            engine=engine,
        )
        return SpoolmanCutoverPreview(
            source_instance_key=key,
            source_fingerprint=preview.source_fingerprint,
            source_unchanged_since_import=(
                source.snapshot_sha256 is not None
                and source.snapshot_sha256 == preview.source_fingerprint
            ),
            last_imported_at_ms=last_imported_at_ms,
            spool_count=total, matched_count=matched,
            mismatch_count=mismatch, missing_count=missing,
            unexpected_count=unexpected,
        )
    except SpoolmanImportRejected:
        raise
    except (OSError, ValueError, sqlite3.Error, SQLAlchemyError):
        raise SpoolmanImportRejected() from None


def _recovery_counts(
    rows: list[_SpoolRow], *, source_instance_key: str, device_id: EntityId,
    engine: Engine,
) -> tuple[int, int, int, int, int]:
    expected: dict[EntityId, tuple[Mass | None, bool]] = {
        _entity_id(f"ufm:spoolman:{source_instance_key}:spool:{row.spool_id}"):
        (_mass(row.remaining_g), row.archived) for row in rows
    }
    with engine.connect() as connection:
        target_rows = connection.execute(select(
            ufm_spool.c.id, ufm_spool.c.effective_remaining_mg,
            ufm_spool.c.lifecycle,
        ).where(
            ufm_spool.c.device_id == device_id,
            ufm_spool.c.deleted_at.is_(None),
        )).all()
    targets = {row[0]: (row[1], row[2]) for row in target_rows}
    matched = sum(
        1 for identity, (remaining, archived) in expected.items()
        if identity in targets
        and targets[identity][0] == remaining
        and (targets[identity][1] == SpoolLifecycle.ARCHIVED.value) == archived
    )
    missing = sum(identity not in targets for identity in expected)
    mismatch = len(expected) - matched - missing
    return len(rows), matched, mismatch, missing, len(targets.keys() - expected.keys())


def _rows_fingerprint(rows: list[_SpoolRow]) -> str:
    # Keep the persisted normalized-data fingerprint contract stable when adding
    # preview-only fields to _SpoolRow.
    payload_rows = []
    for row in rows:
        item = asdict(row)
        item.pop("unsupported_fields")
        item.pop("price_not_imported")
        payload_rows.append(item)
    payload = json.dumps(
        payload_rows, sort_keys=True, separators=(",", ":"), default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _backup_name(prefix: str) -> str:
    return f"spoolman-{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def _write_mapping_report(
    backup_root: Path, rows: list[_SpoolRow], *, source_instance: str,
    source_fingerprint: str, created_at: UtcDateTime,
) -> Path:
    mappings: set[tuple[str, str, str]] = set()
    for row in rows:
        mappings.add((
            "filament", str(row.filament_id),
            str(_entity_id(f"ufm:spoolman:{source_instance}:filament:{row.filament_id}")),
        ))
        if row.vendor_id is not None and row.vendor:
            mappings.add((
                "vendor", str(row.vendor_id),
                str(_entity_id(f"ufm:spoolman:{source_instance}:vendor:{row.vendor_id}")),
            ))
        mappings.add((
            "spool", str(row.spool_id),
            str(_entity_id(f"ufm:spoolman:{source_instance}:spool:{row.spool_id}")),
        ))
    records = [
        {"entity_type": kind, "external_id": external_id, "ufm_id": ufm_id}
        for kind, external_id, ufm_id in sorted(mappings)
    ]
    payload = {
        "format": "ufm-spoolman-id-map-v1",
        "source_instance_key": source_instance,
        "source_fingerprint": source_fingerprint,
        "created_at": created_at.isoformat(),
        "mappings": records,
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    payload["mapping_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    directory = backup_root / _backup_name("mapping")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    target = directory / "mapping.json"
    temporary = directory / ".mapping.json.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(payload, output, ensure_ascii=True, sort_keys=True, indent=2)
            output.write("\n")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _ensure_catalog(
    engine: Engine, *, device_id: EntityId, now: UtcDateTime,
    source_instance: str, row: _SpoolRow,
) -> EntityId:
    profile_id = _entity_id(f"ufm:spoolman:{source_instance}:filament:{row.filament_id}")
    brand_id = None
    if row.vendor_id is not None and row.vendor:
        brand_id = _entity_id(f"ufm:spoolman:{source_instance}:vendor:{row.vendor_id}")
    material = row.material.upper()
    material_type = material if material in _MATERIAL_TYPES else MaterialType.CUSTOM.value
    custom_name = None if material_type != MaterialType.CUSTOM.value else row.material
    with immediate_transaction(engine) as connection:
        if brand_id is not None:
            existing_brand = connection.execute(
                select(brand.c.name).where(brand.c.id == brand_id)
            ).scalar_one_or_none()
            if existing_brand is None:
                connection.execute(insert(brand).values(
                    id=brand_id, device_id=device_id, created_at=now, updated_at=now,
                    revision=1, name=row.vendor,
                ))
            elif existing_brand != row.vendor:
                raise SpoolmanImportRejected()
        existing_profile = connection.execute(
            select(filament_profile.c.name, filament_profile.c.material_type,
                   filament_profile.c.diameter_mm, filament_profile.c.brand_id)
            .where(filament_profile.c.id == profile_id)
        ).one_or_none()
        if existing_profile is None:
            connection.execute(insert(filament_profile).values(
                id=profile_id, device_id=device_id, created_at=now, updated_at=now,
                revision=1, brand_id=brand_id, name=row.name, material_type=material_type,
                custom_material_name=custom_name,
                diameter_mm=ExactDecimal(row.diameter_mm),
                density_g_cm3=(None if row.density_g_cm3 is None
                               else ExactDecimal(row.density_g_cm3)),
                notes=f"Imported from Spoolman ({source_instance}).",
            ))
        elif (
            existing_profile.name != row.name
            or existing_profile.material_type != material_type
            or existing_profile.diameter_mm != ExactDecimal(row.diameter_mm)
            or existing_profile.brand_id != brand_id
        ):
            raise SpoolmanImportRejected()
    return profile_id


def import_spoolman_database(
    source: Path, paths: AppPaths, *, engine: Engine | None = None,
    source_instance_key: str | None = None,
    expected_source_fingerprint: str | None = None,
) -> SpoolmanImportResult:
    """Back up source and existing UFM DB before importing a resumable snapshot."""
    rows, preview = _load_rows(source)
    if expected_source_fingerprint is not None and (
        re.fullmatch(r"[0-9a-f]{64}", expected_source_fingerprint) is None
        or preview.source_fingerprint != expected_source_fingerprint
    ):
        raise SpoolmanImportRejected()
    source_instance = _validated_source_instance_key(source_instance_key, source)
    paths.create()
    backup_root = paths.data / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    source_bundle = backup_root / _backup_name("source")
    create_snapshot(source.expanduser().resolve(), source_bundle)
    database_path = paths.data / "ufm.sqlite3"
    target_bundle: Path | None = None
    if database_path.is_file():
        target_bundle = backup_root / _backup_name("ufm")
        create_snapshot(database_path, target_bundle)

    owned_engine = engine is None
    active_engine = engine or create_sqlite_engine(database_path)
    try:
        migrate_database(active_engine)
        device_id = _entity_id(f"ufm:spoolman:{source_instance}:device")
        now = UtcDateTime.now()
        with immediate_transaction(active_engine) as connection:
            registered_device = connection.execute(
                select(spoolman_import_source.c.device_id).where(
                    spoolman_import_source.c.source_instance_key == source_instance
                )
            ).scalar_one_or_none()
            if registered_device is not None and registered_device != device_id:
                raise SpoolmanImportRejected()
            row = connection.execute(
                select(device_identity.c.id).where(device_identity.c.id == device_id)
            ).scalar_one_or_none()
            if row is None:
                connection.execute(insert(device_identity).values(
                    id=device_id, name="Spoolman import", public_id=str(device_id),
                    created_at=now,
                ))
            if registered_device is None:
                connection.execute(insert(spoolman_import_source).values(
                    source_instance_key=source_instance, device_id=device_id,
                    display_name=source.name[:200] or "Spoolman import",
                    created_at=now, last_seen_at=now, snapshot_sha256=None,
                ))

        commands = InventoryCommands(lambda: SQLiteUnitOfWork(active_engine))
        storage = StorageCommands(lambda: SQLiteUnitOfWork(active_engine))
        for row in rows:
            profile_id = _ensure_catalog(
                active_engine, device_id=device_id, now=now,
                source_instance=source_instance, row=row,
            )
            spool_id = _entity_id(f"ufm:spoolman:{source_instance}:spool:{row.spool_id}")
            actor = device_id
            spool = commands.create_spool(
                spool_id=spool_id, filament_profile_id=profile_id,
                display_name=(f"{row.vendor} {row.name}" if row.vendor else row.name)[:200],
                actor_device_id=actor,
                command_key=f"spoolman:{source_instance}:spool:{row.spool_id}:create",
                nominal_filament=_mass(row.nominal_filament_g),
                empty_spool=_mass(row.empty_spool_g),
                purchase_price=row.purchase_price,
                purchase_basis=_mass(row.purchase_basis_g),
                currency=row.currency,
                at=now,
            )
            if row.remaining_g is not None:
                amount = _mass(row.remaining_g)
                if amount is None:
                    raise SpoolmanImportRejected()
                history = commands.history(spool_id)
                if history:
                    if history[0].delta != amount:
                        raise SpoolmanImportRejected()
                elif spool.lifecycle is not SpoolLifecycle.ARCHIVED:
                    commands.establish_opening_stock(
                        spool_id=spool_id, amount=amount,
                        command_key=f"spoolman:{source_instance}:spool:{row.spool_id}:opening",
                        actor_device_id=actor, at=now,
                    )
                else:
                    raise SpoolmanImportRejected()
                with SQLiteUnitOfWork(active_engine) as work:
                    spool = work.spools.get(spool_id)
            # Import only enriches empty fields. Re-imports preserve later manual
            # edits, and this isolated metadata event never alters mass or ledger.
            lot_number = spool.lot_number or row.lot_number
            color_hex = spool.color_hex or row.color_hex
            if (spool.lifecycle is not SpoolLifecycle.ARCHIVED
                    and (lot_number != spool.lot_number or color_hex != spool.color_hex)):
                metadata_digest = hashlib.sha256(
                    f"{lot_number or ''}\0{color_hex or ''}".encode()
                ).hexdigest()[:24]
                spool = commands.edit_spool(
                    spool_id=spool_id, expected_revision=spool.revision,
                    display_name=spool.display_name, low_threshold=spool.low_threshold,
                    brand_id=spool.brand_id, nominal_filament=spool.nominal_filament,
                    empty_spool=spool.empty_spool, purchase_price=spool.purchase_price,
                    purchase_basis=spool.purchase_basis, currency=spool.currency,
                    purchase_date=spool.purchase_date, product_line=spool.product_line,
                    batch_number=spool.batch_number, lot_number=lot_number,
                    color_name=spool.color_name, color_hex=color_hex,
                    secondary_color_hex=spool.secondary_color_hex, image_uri=spool.image_uri,
                    notes=spool.notes, opened_at=spool.opened_at,
                    manufactured_at=spool.manufactured_at, expires_at=spool.expires_at,
                    actor_device_id=actor,
                    command_key=(f"spoolman:{source_instance}:spool:{row.spool_id}"
                                 f":metadata-v1:{metadata_digest}"),
                    at=now,
                )
            if (row.location is not None and spool.storage_location_id is None
                    and spool.lifecycle is not SpoolLifecycle.ARCHIVED):
                location_id = _entity_id(
                    f"ufm:spoolman:{source_instance}:location:{row.location}"
                )
                storage.create_location(
                    location_id=location_id, name=row.location, storage_type=StorageType.OTHER,
                    parent_id=None, actor_device_id=actor,
                    command_key=f"spoolman:{source_instance}:location:{hashlib.sha256(row.location.encode()).hexdigest()}",
                    at=now,
                )
                spool = storage.assign_spool(
                    spool_id=spool_id, expected_revision=spool.revision,
                    location_id=location_id, actor_device_id=actor,
                    command_key=f"spoolman:{source_instance}:spool:{row.spool_id}:location-v1",
                    at=now,
                )
            if row.archived and spool.lifecycle is not SpoolLifecycle.ARCHIVED:
                commands.archive_spool(
                    spool_id=spool_id, expected_revision=spool.revision,
                    actor_device_id=actor,
                    command_key=f"spoolman:{source_instance}:spool:{row.spool_id}:archive",
                    at=now,
                )
        mapping_report = _write_mapping_report(
            backup_root, rows, source_instance=source_instance,
            source_fingerprint=preview.source_fingerprint, created_at=now,
        )
        with immediate_transaction(active_engine) as connection:
            connection.execute(update(spoolman_import_source).where(
                spoolman_import_source.c.source_instance_key == source_instance
            ).values(last_seen_at=now, snapshot_sha256=preview.source_fingerprint))
    finally:
        if owned_engine:
            active_engine.dispose()
    return SpoolmanImportResult(
        preview=preview, source_backup=source_bundle,
        target_backup=target_bundle, mapping_report=mapping_report,
        processed_count=len(rows),
        source_instance_key=source_instance,
    )
