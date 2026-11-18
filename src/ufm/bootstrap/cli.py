"""Localized foundation CLI. No printer connections or inventory writes."""

import argparse
import json
import sys
from pathlib import Path
from typing import Never

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ufm import __version__
from ufm.application.ports.persistence import PersistenceError
from ufm.bootstrap.app_container import create_container
from ufm.bootstrap.settings import AppSettings, SettingsError, load_settings
from ufm.domain.value_objects import EntityId
from ufm.infrastructure.backup.sqlite_snapshot import BackupInvalid
from ufm.infrastructure.logging import configure_logging
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import MigrationRequired
from ufm.integrations.catalog import load_material_catalog
from ufm.integrations.haspelsync import preview_haspelsync_files
from ufm.integrations.qr import spool_label_svg
from ufm.integrations.spoolman.importer import (
    import_spoolman_database,
    new_spoolman_source_key,
    preview_spoolman_database,
)
from ufm.integrations.spoolman.preview import preview_spools
from ufm.platform.common.paths import AppPaths
from ufm.ui.i18n import TranslationError, Translator


class _InvalidArguments(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse can otherwise echo arbitrary input, including pasted secrets.
        raise _InvalidArguments()


def _localization_failure() -> int:
    logger = configure_logging()
    logger.error("localization_unavailable")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="ufm", add_help=False, allow_abbrev=False)
    parser.add_argument("--help", action="store_true")
    parser.add_argument("--version", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--catalog", action="store_true")
    modes.add_argument("--qr-label")
    modes.add_argument("--spool-api-preview", "--spoolman-preview",
                       dest="spoolman_preview", type=Path)
    modes.add_argument("--spool-db-preview", "--spoolman-db-preview",
                       dest="spoolman_db_preview", type=Path)
    modes.add_argument("--spool-db-import", "--spoolman-db-import",
                       dest="spoolman_db_import", type=Path)
    modes.add_argument(
        "--slot-mapping-preview", "--haspelsync-preview", dest="haspelsync_preview",
        nargs=3, metavar=("PRINTERS_JSON", "MAPPINGS_JSON", "ID_MAP_JSON"),
    )
    parser.add_argument("--spool-source-id", "--spoolman-source-id",
                        dest="spoolman_source_id")
    parser.add_argument("--source-instance")
    parser.add_argument("--locale", choices=("uk-UA", "en-US"))
    parser.add_argument("--data-dir", type=Path)
    try:
        translator = Translator("uk-UA")
    except TranslationError:
        return _localization_failure()
    try:
        args = parser.parse_args(argv)
    except _InvalidArguments:
        print(translator.text("error.arguments"), file=sys.stderr)
        return 2
    if args.locale:
        try:
            translator = Translator(args.locale)
        except TranslationError:
            return _localization_failure()
    if args.help:
        print(translator.text("cli.help"))
        return 0
    if args.version:
        print(__version__)
        return 0
    if args.source_instance is not None and args.spoolman_preview is None:
        print(translator.text("error.arguments"), file=sys.stderr)
        return 2
    if args.spoolman_source_id is not None and args.spoolman_db_import is None:
        print(translator.text("error.arguments"), file=sys.stderr)
        return 2
    try:
        if args.catalog:
            print(json.dumps([{
                "name": item.name, "density_g_cm3": str(item.density_g_cm3),
                "extruder_temp_c": item.extruder_temp_c, "bed_temp_c": item.bed_temp_c,
                "source_url": item.source_url,
            } for item in load_material_catalog()], ensure_ascii=True))
            return 0
        if args.qr_label is not None:
            print(spool_label_svg(EntityId.parse(args.qr_label)).decode("utf-8"))
            return 0
        if args.spoolman_preview is not None:
            if args.source_instance is None:
                raise ValueError("source_instance.required")
            # Bound the actual read, not only a potentially stale stat() size.
            with args.spoolman_preview.open("rb") as source:
                payload = source.read(4 * 1024 * 1024 + 1)
            preview = preview_spools(payload, source_instance=args.source_instance)
            print(json.dumps({
                "source_fingerprint": preview.source_fingerprint,
                "warnings": preview.warnings,
                "spools": [{
                    "source_key": item.source_key, "filament_id": item.filament_id,
                    "name": item.name, "material": item.material, "vendor": item.vendor,
                    "location": item.location, "archived": item.archived,
                    "estimated_remaining_mg": (None if item.estimated_remaining is None
                                               else item.estimated_remaining.milligrams),
                } for item in preview.spools],
            }, ensure_ascii=True))
            return 0
        if args.haspelsync_preview is not None:
            printers_path, mappings_path, id_map_path = map(Path, args.haspelsync_preview)
            haspel_preview = preview_haspelsync_files(
                printers_path, mappings_path, id_map_path,
            )
            print(json.dumps({
                "printers": [{
                    "serial_number": item.serial_number,
                    "display_name": item.display_name,
                    "has_private_lan_address": item.has_private_lan_address,
                    "credential_required": item.credential_required,
                } for item in haspel_preview.printers],
                "mappings": [{
                    "printer_serial": item.printer_serial,
                    "source_slot_label": item.source_slot_label,
                    "external_spool_id": item.external_spool_id,
                    "ufm_spool_id": item.ufm_spool_id,
                    "provider_system_key": item.provider_system_key,
                    "provider_slot_key": item.provider_slot_key,
                    "fingerprint_present": item.fingerprint_present,
                    "was_automatic": item.was_automatic,
                    "conflict": item.conflict,
                } for item in haspel_preview.mappings],
                "unresolved_spools": haspel_preview.unresolved_spool_count,
                "unsupported_slots": haspel_preview.unsupported_slot_count,
                "orphan_printers": haspel_preview.orphan_printer_count,
                "duplicate_target_spools": haspel_preview.duplicate_target_spool_count,
                "credentials_imported": haspel_preview.credentials_imported,
                "network_access_performed": haspel_preview.network_access_performed,
                "inventory_writes_performed": haspel_preview.inventory_writes_performed,
            }, ensure_ascii=True))
            return 0
        if args.spoolman_db_preview is not None:
            paths = AppPaths.resolve(args.data_dir)
            database_path = paths.data / "ufm.sqlite3"
            preview_engine = create_sqlite_engine(database_path) if database_path.is_file() else None
            try:
                database_preview = preview_spoolman_database(
                    args.spoolman_db_preview, engine=preview_engine,
                )
            finally:
                if preview_engine is not None:
                    preview_engine.dispose()
            print(json.dumps({
                "suggested_source_instance_key": database_preview.suggested_source_instance_key,
                "source_fingerprint": database_preview.source_fingerprint,
                "registered_sources": [{
                    "source_instance_key": item.source_instance_key,
                    "display_name": item.display_name,
                    "last_seen_at": item.last_seen_at,
                    "snapshot_sha256": item.snapshot_sha256,
                } for item in database_preview.source_instances],
                "spools": database_preview.spool_count,
                "filaments": database_preview.filament_count,
                "vendors": database_preview.vendor_count,
                "known_stock": database_preview.known_stock_count,
                "unknown_stock": database_preview.unknown_stock_count,
                "archived": database_preview.archived_count,
                "lot_numbers": database_preview.lot_number_count,
                "colors": database_preview.color_count,
                "locations": database_preview.location_count,
                "unsupported_metadata": database_preview.unsupported_metadata_count,
                "writes_performed": False,
            }, ensure_ascii=True))
            return 0
        if args.spoolman_db_import is not None:
            paths = AppPaths.resolve(args.data_dir)
            source_key = (
                new_spoolman_source_key()
                if args.spoolman_source_id == "new" else args.spoolman_source_id
            )
            try:
                result = import_spoolman_database(
                    args.spoolman_db_import, paths,
                    source_instance_key=source_key,
                )
            except (
                BackupInvalid, MigrationRequired, PersistenceError, SQLAlchemyError,
                OSError, ValueError,
            ):
                print(translator.text("error.spoolman_import"), file=sys.stderr)
                return 1
            print(json.dumps({
                "source_instance_key": result.source_instance_key,
                "spools_processed": result.processed_count,
                "known_stock": result.preview.known_stock_count,
                "unknown_stock": result.preview.unknown_stock_count,
                "archived": result.preview.archived_count,
                "source_backup": str(result.source_backup),
                "mapping_report": str(result.mapping_report),
                "target_backup": None if result.target_backup is None
                                  else str(result.target_backup),
                "historical_print_transactions_imported": 0,
            }, ensure_ascii=True))
            return 0
    except (OSError, ValueError):
        print(translator.text("error.interoperability"), file=sys.stderr)
        return 2
    except (BackupInvalid, MigrationRequired, PersistenceError, SQLAlchemyError):
        print(translator.text("error.spoolman_import"), file=sys.stderr)
        return 1
    try:
        paths = AppPaths.resolve(args.data_dir)
        settings = load_settings(paths.config / "settings.json")
        if args.locale:
            settings = AppSettings.model_validate({**settings.model_dump(), "locale": args.locale})
        translator = Translator(settings.locale)
        container = create_container(settings, paths, check_only=args.check)
    except (SettingsError, ValidationError):
        print(translator.text("error.settings"), file=sys.stderr)
        return 2
    except OSError:
        print(translator.text("error.startup"), file=sys.stderr)
        return 1
    except TranslationError:
        print(translator.text("error.localization"), file=sys.stderr)
        return 1
    try:
        container.logger.info("startup_validated" if args.check else "foundation_started")
        print(translator.text("app.check_ok" if args.check else "app.foundation_ready"))
        return 0
    finally:
        container.close()
