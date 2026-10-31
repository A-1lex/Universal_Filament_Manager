"""Backup-first Spoolman SQLite import tests using synthetic source data."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlalchemy import select

from ufm.application.inventory import InventoryCommands
from ufm.domain.entities import Spool
from ufm.domain.enums import TransactionType
from ufm.domain.value_objects import EntityId
from ufm.infrastructure.persistence.models.ledger import filament_transaction
from ufm.infrastructure.persistence.models.schema import filament_profile, spool, spool_mount
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.spoolman.importer import (
    SpoolmanImportRejected,
    SpoolmanImportSourceInfo,
    default_spoolman_import_source_key,
    import_spoolman_database,
    list_spoolman_import_sources,
    preview_spoolman_cutover,
    preview_spoolman_database,
    preview_spoolman_import_recovery,
    spoolman_import_source_label,
)
from ufm.platform.common.paths import AppPaths


def create_spoolman_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE vendor (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                empty_spool_weight REAL
            );
            CREATE TABLE filament (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                vendor_id INTEGER REFERENCES vendor(id), material TEXT NOT NULL,
                density REAL, diameter REAL NOT NULL, weight REAL,
                spool_weight REAL, color_hex TEXT, price REAL
            );
            CREATE TABLE spool (
                id INTEGER PRIMARY KEY,
                filament_id INTEGER NOT NULL REFERENCES filament(id),
                used_weight REAL, archived INTEGER NOT NULL,
                initial_weight REAL, spool_weight REAL, location TEXT, lot_nr TEXT
                , price REAL
            );
            CREATE TABLE setting (key TEXT PRIMARY KEY, value TEXT NOT NULL, last_updated TEXT);
            INSERT INTO vendor VALUES (1, 'Example', 200.0);
            INSERT INTO setting VALUES ('currency', '"UAH"', NULL);
            INSERT INTO filament (id,name,vendor_id,material,density,diameter,weight,spool_weight,color_hex,price)
                VALUES (1, 'PLA Black', 1, 'PLA', 1.24, 1.75, 1000.0, 200.0, '#000000', 15.25);
            INSERT INTO filament (id,name,vendor_id,material,density,diameter,weight,spool_weight,color_hex,price)
                VALUES (2, 'Custom Mix', 1, 'PLA-CF', 1.3, 1.75, 750.0, 190.0, NULL, 12.25);
            INSERT INTO spool (id,filament_id,used_weight,archived,initial_weight,spool_weight,location,lot_nr,price)
                VALUES (1, 1, 200.552, 0, 1000.0, 201.0, 'Shelf 1', 'A-1', 20.50);
            INSERT INTO spool (id,filament_id,used_weight,archived,initial_weight,spool_weight,location,lot_nr,price)
                VALUES (2, 2, 400.0, 1, 750.0, NULL, NULL, NULL, NULL);
            INSERT INTO spool (id,filament_id,used_weight,archived,initial_weight,spool_weight,location,lot_nr,price)
                VALUES (3, 2, NULL, 0, NULL, NULL, NULL, NULL, NULL);
        """)
    finally:
        connection.close()


def create_legacy_spoolman_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE vendor (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                empty_spool_weight REAL
            );
            CREATE TABLE filament (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                vendor_id INTEGER REFERENCES vendor(id), material TEXT NOT NULL,
                density REAL, diameter REAL NOT NULL, weight REAL,
                spool_weight REAL, color_hex TEXT
            );
            CREATE TABLE spool (
                id INTEGER PRIMARY KEY,
                filament_id INTEGER NOT NULL REFERENCES filament(id),
                used_weight REAL, archived INTEGER NOT NULL,
                initial_weight REAL, spool_weight REAL, location TEXT, lot_nr TEXT
            );
            INSERT INTO filament VALUES (1, 'PLA', NULL, 'PLA', 1.24, 1.75,
                                         1000.0, NULL, '#000000');
            INSERT INTO spool VALUES (1, 1, 100.0, 0, 1000.0, NULL, NULL, NULL);
        """)
    finally:
        connection.close()


class SpoolmanImporterTests(unittest.TestCase):
    def test_source_label_flags_only_unverified_import_snapshots(self) -> None:
        pending = SpoolmanImportSourceInfo(
            source_instance_key="a" * 24, device_id="device", display_name="test",
            created_at="2026-01-01T00:00:00.000000Z",
            last_seen_at="2026-01-01T00:00:00.000000Z", snapshot_sha256=None,
        )
        verified = SpoolmanImportSourceInfo(
            source_instance_key="a" * 24, device_id="device", display_name="test",
            created_at="2026-01-01T00:00:00.000000Z",
            last_seen_at="2026-01-01T00:00:00.000000Z", snapshot_sha256="b" * 64,
        )
        self.assertIn("unverified", spoolman_import_source_label(
            pending, unverified_label="unverified",
        ))
        self.assertNotIn("unverified", spoolman_import_source_label(
            verified, unverified_label="unverified",
        ))
        pending = replace(pending, recovery_counts=(3, 1, 0, 2, 0))
        label = spoolman_import_source_label(
            pending, unverified_label="unverified",
            recovery_label="matched {matched}/{total}; mismatch {mismatch}; "
            "missing {missing}; extra {extra}",
        )
        self.assertIn("matched 1/3; mismatch 0; missing 2; extra 0", label)

    def test_moved_source_defaults_only_when_identity_is_unambiguous(self) -> None:
        first = SpoolmanImportSourceInfo(
            source_instance_key="a" * 24, device_id="one", display_name="one",
            created_at="2026-01-01T00:00:00.000000Z",
            last_seen_at="2026-01-01T00:00:00.000000Z", snapshot_sha256=None,
        )
        second = SpoolmanImportSourceInfo(
            source_instance_key="b" * 24, device_id="two", display_name="two",
            created_at="2026-01-01T00:00:00.000000Z",
            last_seen_at="2026-01-01T00:00:00.000000Z", snapshot_sha256="c" * 64,
        )
        self.assertEqual(
            default_spoolman_import_source_key((first,), "d" * 24), first.source_instance_key,
        )
        self.assertEqual(
            default_spoolman_import_source_key((first, second), second.source_instance_key),
            second.source_instance_key,
        )
        self.assertIsNone(default_spoolman_import_source_key((first, second), "d" * 24))
        self.assertIsNone(default_spoolman_import_source_key((), "d" * 24))

    def test_cutover_preview_detects_changed_source_and_target_balance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            paths = AppPaths.resolve(root / "ufm")
            imported = import_spoolman_database(
                source, paths, source_instance_key="c" * 24,
            )
            engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
            try:
                initial = preview_spoolman_cutover(
                    source, engine=engine,
                    source_instance_key=imported.source_instance_key,
                )
                self.assertTrue(initial.ready)
                self.assertEqual(
                    (initial.spool_count, initial.matched_count,
                     initial.mismatch_count, initial.missing_count,
                     initial.unexpected_count),
                    (3, 3, 0, 0, 0),
                )
                with self.assertRaises(SpoolmanImportRejected):
                    preview_spoolman_import_recovery(
                        source, engine=engine,
                        source_instance_key=imported.source_instance_key,
                    )
                connection = sqlite3.connect(source)
                try:
                    connection.execute(
                        "UPDATE spool SET used_weight=201.552 WHERE id=1",
                    )
                    connection.commit()
                finally:
                    connection.close()

                changed = preview_spoolman_cutover(
                    source, engine=engine,
                    source_instance_key=imported.source_instance_key,
                )
                self.assertFalse(changed.ready)
                self.assertFalse(changed.source_unchanged_since_import)
                self.assertEqual(
                    (changed.matched_count, changed.mismatch_count, changed.missing_count,
                     changed.unexpected_count),
                    (2, 1, 0, 0),
                )
                source_info = next(
                    item for item in list_spoolman_import_sources(engine)
                    if item.source_instance_key == imported.source_instance_key
                )
                with engine.connect() as profile_connection:
                    profile_id = profile_connection.execute(
                        select(filament_profile.c.id).limit(1),
                    ).scalar_one()
                InventoryCommands(lambda: SQLiteUnitOfWork(engine)).create_spool(
                    spool_id=EntityId.new(), filament_profile_id=profile_id,
                    display_name="Unexpected test spool",
                    actor_device_id=EntityId.parse(source_info.device_id),
                    command_key="cutover-unexpected-test-spool",
                )
                with_extra = preview_spoolman_cutover(
                    source, engine=engine,
                    source_instance_key=imported.source_instance_key,
                )
                self.assertFalse(with_extra.ready)
                self.assertEqual(with_extra.unexpected_count, 1)
            finally:
                engine.dispose()

    def test_preview_is_read_only_and_distinguishes_unknown_stock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            preview = preview_spoolman_database(source)
            self.assertEqual(preview.spool_count, 3)
            self.assertEqual(preview.filament_count, 2)
            self.assertEqual(preview.vendor_count, 1)
            self.assertEqual(preview.known_stock_count, 2)
            self.assertEqual(preview.unknown_stock_count, 1)
            self.assertEqual(preview.archived_count, 1)
            self.assertEqual(preview.purchase_price_count, 3)
            self.assertEqual(preview.purchase_price_not_imported_count, 0)
            connection = sqlite3.connect(source)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM spool").fetchone()[0], 3)
            finally:
                connection.close()

    def test_preview_exposes_each_row_and_uses_the_import_milligram_rounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            preview = preview_spoolman_database(source)

            self.assertEqual([item.spool_id for item in preview.spools], [1, 2, 3])
            self.assertEqual(preview.spools[0].remaining_mg, 799_448)
            self.assertEqual(preview.spools[0].purchase_price, "20.5")
            self.assertEqual(preview.spools[0].currency, "UAH")
            self.assertEqual(preview.spools[0].purchase_basis_mg, 1_000_000)
            self.assertTrue(preview.spools[1].archived)
            self.assertEqual(preview.spools[1].remaining_mg, 350_000)
            self.assertIsNone(preview.spools[2].remaining_mg)
            self.assertEqual(preview.spools[2].name, "Custom Mix")
            self.assertEqual(
                preview.source_fingerprint,
                "f5cd5145b39f39678e7b8c6bb7921b39ff58c598330805fa2bcd5d975832564d",
            )

    def test_import_backs_up_source_and_imports_opening_balance_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            paths = AppPaths.resolve(root / "ufm")
            result = import_spoolman_database(source, paths)

            self.assertTrue((result.source_backup / "database.sqlite3").is_file())
            self.assertEqual(result.source_backup.parent, paths.data / "backups")
            self.assertIsNone(result.target_backup)
            self.assertEqual(result.processed_count, 3)
            self.assertEqual(result.preview.known_stock_count, 2)

            engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
            try:
                with engine.connect() as connection:
                    self.assertEqual(len(connection.execute(select(spool.c.id)).all()), 3)
                    self.assertEqual(len(connection.execute(select(filament_profile.c.id)).all()), 2)
                    ledger = connection.execute(select(
                        filament_transaction.c.delta_mg,
                        filament_transaction.c.transaction_type,
                    )).all()
                    self.assertEqual(len(ledger), 2)
                    self.assertEqual(
                        sorted(row.delta_mg.milligrams for row in ledger),
                        [350000, 799448],
                    )
                    self.assertTrue(all(
                        row.transaction_type == TransactionType.INITIAL_STOCK.value
                        for row in ledger
                    ))
                    self.assertEqual(connection.execute(select(spool_mount.c.id)).all(), [])
                    priced = connection.execute(select(
                        spool.c.display_name, spool.c.purchase_price,
                        spool.c.purchase_basis_mg, spool.c.currency,
                    ).where(spool.c.purchase_price.is_not(None)).order_by(
                        spool.c.display_name,
                    )).all()
                    self.assertEqual(len(priced), 3)
                    self.assertEqual(
                        {(row.purchase_price.canonical(), row.purchase_basis_mg.milligrams,
                          row.currency) for row in priced},
                        {("20.5", 1_000_000, "UAH"), ("12.25", 750_000, "UAH")},
                    )
            finally:
                engine.dispose()

    def test_import_rejects_source_changed_after_preview_before_any_target_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            preview = preview_spoolman_database(source)
            connection = sqlite3.connect(source)
            try:
                connection.execute("UPDATE spool SET used_weight=210.0 WHERE id=1")
                connection.commit()
            finally:
                connection.close()

            paths = AppPaths.resolve(root / "ufm")
            with self.assertRaises(SpoolmanImportRejected):
                import_spoolman_database(
                    source, paths,
                    source_instance_key=preview.suggested_source_instance_key,
                    expected_source_fingerprint=preview.source_fingerprint,
                )
            self.assertFalse(paths.data.exists())

    def test_reimport_is_idempotent_and_backs_up_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            paths = AppPaths.resolve(root / "ufm")
            import_spoolman_database(source, paths)
            result = import_spoolman_database(source, paths)

            self.assertIsNotNone(result.target_backup)
            assert result.target_backup is not None
            self.assertTrue((result.target_backup / "database.sqlite3").is_file())
            engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
            try:
                with engine.connect() as connection:
                    self.assertEqual(len(connection.execute(select(spool.c.id)).all()), 3)
                    self.assertEqual(
                        len(connection.execute(select(filament_transaction.c.id)).all()), 2,
                    )
            finally:
                engine.dispose()

    def test_interrupted_import_resumes_without_duplicate_stock_or_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            paths = AppPaths.resolve(root / "ufm")
            source_key = "a" * 24
            original = InventoryCommands.create_spool
            calls = 0

            def fail_on_second_spool(
                self: InventoryCommands, **kwargs: Any,
            ) -> Spool:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("synthetic interruption")
                return original(self, **kwargs)

            with patch.object(InventoryCommands, "create_spool", fail_on_second_spool):
                with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                    import_spoolman_database(
                        source, paths, source_instance_key=source_key,
                    )

            engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
            try:
                import_preview = preview_spoolman_database(source, engine=engine)
                incomplete_source = next(
                    item for item in import_preview.source_instances
                    if item.source_instance_key == source_key
                )
                self.assertEqual(incomplete_source.recovery_counts, (3, 1, 0, 2, 0))
                recovery = preview_spoolman_import_recovery(
                    source, engine=engine, source_instance_key=source_key,
                )
                self.assertFalse(recovery.ready)
                self.assertFalse(recovery.source_unchanged_since_import)
                self.assertEqual(
                    (recovery.spool_count, recovery.matched_count,
                     recovery.mismatch_count, recovery.missing_count,
                     recovery.unexpected_count),
                    (3, 1, 0, 2, 0),
                )
            finally:
                engine.dispose()

            moved_source = root / "moved" / "renamed.sqlite3"
            moved_source.parent.mkdir()
            source.replace(moved_source)
            resumed = import_spoolman_database(
                moved_source, paths, source_instance_key=source_key,
            )
            self.assertEqual(resumed.processed_count, 3)
            self.assertTrue(resumed.mapping_report.is_file())
            mapping_text = resumed.mapping_report.read_text(encoding="utf-8")
            mapping = json.loads(mapping_text)
            self.assertEqual(mapping["source_fingerprint"], resumed.preview.source_fingerprint)
            mapping_digest = mapping.pop("mapping_sha256")
            canonical = json.dumps(mapping, ensure_ascii=True, sort_keys=True,
                                   separators=(",", ":"))
            self.assertEqual(mapping_digest, hashlib.sha256(canonical.encode("utf-8")).hexdigest())
            tampered = {**mapping, "mappings": [*mapping["mappings"]]}
            tampered["mappings"][0] = {**tampered["mappings"][0], "ufm_id": "changed"}
            tampered_canonical = json.dumps(
                tampered, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
            )
            self.assertNotEqual(
                mapping_digest, hashlib.sha256(tampered_canonical.encode("utf-8")).hexdigest(),
            )
            self.assertNotIn(str(moved_source), mapping_text)
            self.assertEqual(
                {entry["external_id"] for entry in mapping["mappings"]
                 if entry["entity_type"] == "spool"},
                {"1", "2", "3"},
            )
            self.assertEqual(
                {entry["external_id"] for entry in mapping["mappings"]
                 if entry["entity_type"] == "filament"},
                {"1", "2"},
            )

            engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
            try:
                with engine.connect() as connection:
                    self.assertEqual(len(connection.execute(select(spool.c.id)).all()), 3)
                    self.assertEqual(
                        len(connection.execute(select(filament_transaction.c.id)).all()), 2,
                    )
                    self.assertEqual(
                        sorted(row.delta_mg.milligrams for row in connection.execute(
                            select(filament_transaction.c.delta_mg)
                        ).all()),
                        [350000, 799448],
                    )
            finally:
                engine.dispose()

    def test_invalid_negative_remaining_rejects_before_any_import_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            connection = sqlite3.connect(source)
            try:
                connection.execute("UPDATE spool SET used_weight=2000 WHERE id=1")
                connection.commit()
            finally:
                connection.close()
            paths = AppPaths.resolve(root / "ufm")
            with self.assertRaises(SpoolmanImportRejected):
                import_spoolman_database(source, paths)
            self.assertFalse(paths.data.exists())

    def test_unknown_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unknown.sqlite3"
            connection = sqlite3.connect(source)
            try:
                connection.execute("CREATE TABLE unexpected (id INTEGER)")
            finally:
                connection.close()
            with self.assertRaises(SpoolmanImportRejected):
                preview_spoolman_database(source)

    def test_prices_are_not_imported_when_system_currency_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spoolman.sqlite3"
            create_spoolman_fixture(source)
            connection = sqlite3.connect(source)
            try:
                connection.execute("UPDATE setting SET value='null' WHERE key='currency'")
                connection.commit()
            finally:
                connection.close()
            preview = preview_spoolman_database(source)
            self.assertEqual(preview.purchase_price_count, 0)
            self.assertEqual(preview.purchase_price_not_imported_count, 3)
            self.assertTrue(all("price" in row.omitted_fields for row in preview.spools))

    def test_legacy_schema_without_price_columns_remains_importable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy-spoolman.sqlite3"
            create_legacy_spoolman_fixture(source)
            preview = preview_spoolman_database(source)
            self.assertEqual(preview.spool_count, 1)
            self.assertEqual(preview.purchase_price_count, 0)
            self.assertEqual(preview.purchase_price_not_imported_count, 0)
