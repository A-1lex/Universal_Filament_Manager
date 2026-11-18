"""Behavior checks use unittest classes, also collected by the required pytest CI."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from ufm.bootstrap.cli import main
from ufm.bootstrap.settings import (
    MAX_SETTINGS_BYTES,
    AppSettings,
    SettingsError,
    load_settings,
    save_settings,
)
from ufm.platform.common.paths import AppPaths
from ufm.ui.i18n import (
    TranslationError,
    Translator,
    load_catalog,
    placeholders,
    validate_catalogs,
)
from ufm.ui.studio import resolve_settings


class SettingsTests(unittest.TestCase):
    def test_safe_defaults(self) -> None:
        settings = AppSettings()
        self.assertEqual(settings.locale, "uk-UA")
        self.assertEqual(settings.sqlite_busy_timeout_ms, 5000)

    def test_unknown_credentials_and_invalid_types_rejected(self) -> None:
        for invalid in (
            {"password": "private-test"},
            {"sqlite_busy_timeout_ms": True},
            {"sqlite_busy_timeout_ms": "5000"},
            {"sqlite_busy_timeout_ms": 0},
            {"locale": "de-DE"},
            {"inventory_columns": ["name", "unknown_column"]},
            {"schema_version": 2},
        ):
            with self.subTest(invalid=tuple(invalid)):
                with self.assertRaises(ValidationError):
                    AppSettings.model_validate(invalid)

    def test_settings_are_immutable(self) -> None:
        settings = AppSettings()
        with self.assertRaises(ValidationError):
            settings.locale = "en-US"

    def test_missing_file_is_default_but_bad_file_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load_settings(path), AppSettings())
            for content in (b'{"token":"private"}', b"invalid-private-json", b"\xff", b"[]"):
                path.write_bytes(content)
                with self.assertRaises(SettingsError) as raised:
                    load_settings(path)
                self.assertEqual(str(raised.exception), "settings.invalid")
                self.assertNotIn("private", str(raised.exception))

    def test_settings_size_limit_and_valid_locale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_bytes(b" " * (MAX_SETTINGS_BYTES + 1))
            with self.assertRaises(SettingsError):
                load_settings(path)
            path.write_text('{"locale":"en-US"}', encoding="utf-8")
            self.assertEqual(load_settings(path).locale, "en-US")
            path.write_text('{"inventory_columns":["name","remaining"]}', encoding="utf-8")
            self.assertEqual(load_settings(path).inventory_columns, ("name", "remaining"))

    def test_studio_uses_saved_locale_unless_explicitly_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            (config / "settings.json").write_text('{"locale":"en-US"}', encoding="utf-8")

            paths, saved = resolve_settings(root, None)
            self.assertEqual(paths.config, config.resolve())
            self.assertEqual(saved.locale, "en-US")

            _, overridden = resolve_settings(root, "uk-UA")
            self.assertEqual(overridden.locale, "uk-UA")

    def test_settings_save_atomically_round_trips_and_rejects_extra_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "settings.json"
            settings = AppSettings(locale="en-US", theme="dark", log_level="DEBUG",
                                   inventory_columns=("name", "remaining"))
            save_settings(settings, path)
            self.assertEqual(load_settings(path), settings)
            self.assertEqual(list(path.parent.iterdir()), [path])
            with self.assertRaises(ValidationError):
                AppSettings.model_validate({**settings.model_dump(), "access_code": "secret"})


class LocalizationTests(unittest.TestCase):
    def test_inventory_alerts_have_both_translations(self) -> None:
        for locale in ("uk-UA", "en-US"):
            for key in ("inventory.low_stock", "inventory.spool_quarantined"):
                with self.subTest(locale=locale, key=key):
                    self.assertTrue(Translator(locale).text(key).strip())

    def test_complete_catalog_parity(self) -> None:
        validate_catalogs()
        self.assertEqual(load_catalog("uk-UA").keys(), load_catalog("en-US").keys())

    def test_unknown_locale_falls_back_to_english(self) -> None:
        self.assertEqual(
            Translator("unsupported").text("app.check_ok"), "Startup checks passed."
        )

    def test_unknown_key_and_incorrect_parameters_raise(self) -> None:
        translator = Translator("uk-UA")
        with self.assertRaises(TranslationError):
            translator.text("missing.key")
        with self.assertRaises(TranslationError):
            translator.text("app.check_ok", unused="value")

    def test_placeholders_do_not_allow_object_traversal(self) -> None:
        self.assertEqual(placeholders("{count} spools"), frozenset({"count"}))
        for invalid in (
            "{secret.value}", "{secret[0]}", "{}", "{count!r}", "{count:.2f}", "{broken", "broken}"
        ):
            with self.subTest(template=invalid):
                with self.assertRaises(TranslationError):
                    placeholders(invalid)

    def test_missing_key_and_placeholder_mismatch_detected(self) -> None:
        catalogs = {"en-US": {"count": "{count} spools"}, "uk-UA": {"count": "{value}"}}
        with patch("ufm.ui.i18n.load_catalog", side_effect=catalogs.__getitem__):
            with self.assertRaises(TranslationError):
                validate_catalogs()

    def test_missing_localized_key_uses_english_fallback(self) -> None:
        english = load_catalog("en-US")
        ukrainian = load_catalog("uk-UA")
        del ukrainian["app.check_ok"]
        catalogs = {"en-US": english, "uk-UA": ukrainian}
        with patch("ufm.ui.i18n.load_catalog", side_effect=catalogs.__getitem__):
            self.assertEqual(Translator("uk-UA").text("app.check_ok"), "Startup checks passed.")

    def test_broken_template_returns_safe_startup_error(self) -> None:
        english = load_catalog("en-US")
        ukrainian = load_catalog("uk-UA")
        ukrainian["app.check_ok"] = "{broken"
        catalogs = {"en-US": english, "uk-UA": ukrainian}
        with patch("ufm.ui.i18n.load_catalog", side_effect=catalogs.__getitem__):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main(["--check"]), 1)
        self.assertEqual(json.loads(stderr.getvalue())["event"], "localization_unavailable")
        catalogs["uk-UA"] = {}
        with patch("ufm.ui.i18n.load_catalog", side_effect=catalogs.__getitem__):
            with self.assertRaises(TranslationError):
                validate_catalogs()


class PathsAndStartupTests(unittest.TestCase):
    def test_explicit_paths_are_resolved_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "дані програми"
            paths = AppPaths.resolve(root)
            self.assertEqual(paths.data, root.resolve() / "data")
            self.assertFalse(root.exists())
            paths.create()
            paths.create()
            self.assertTrue(all(path.is_dir() for path in (
                paths.data, paths.config, paths.logs, paths.cache
            )))

    def test_check_both_locales_writes_no_application_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            for locale in ("uk-UA", "en-US"):
                with self.subTest(locale=locale):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = main(["--check", "--locale", locale, "--data-dir", str(root)])
                    self.assertEqual(code, 0)
                    self.assertIn(Translator(locale).text("app.check_ok"), stdout.getvalue())
                    self.assertEqual(json.loads(stderr.getvalue())["event"], "startup_validated")
                    self.assertFalse(root.exists())

    def test_normal_start_creates_expected_paths_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--data-dir", str(root)])
            self.assertEqual(code, 0)
            self.assertTrue((root / "logs" / "ufm.log").is_file())
            self.assertFalse(any(root.rglob("*.db")))

    def test_help_version_and_invalid_arguments(self) -> None:
        for args in (["--help", "--locale", "en-US"], ["--version"]):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(args), 0)
            self.assertTrue(stdout.getvalue().strip())
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(main(["--password", "private-secret"]), 2)
        self.assertNotIn("private-secret", stderr.getvalue())

    def test_help_uses_neutral_flag_names_without_legacy_brands(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(["--help", "--locale", "en-US"]), 0)
        help_text = stdout.getvalue().lower()
        self.assertIn("--spool-db-import", help_text)
        self.assertIn("--spool-source-id", help_text)
        self.assertIn("--slot-mapping-preview", help_text)
        self.assertNotIn("spoolman", help_text)
        self.assertNotIn("haspelsync", help_text)

    def test_corrupt_config_is_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "settings.json").write_text('{"token":"private"}')
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main(["--check", "--data-dir", str(root)]), 2)
            self.assertNotIn("private", stderr.getvalue())
            self.assertFalse((root / "logs").exists())
