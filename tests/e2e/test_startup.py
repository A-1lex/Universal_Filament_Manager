import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class StartupProcessTests(unittest.TestCase):
    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "ufm", *arguments],
            env={**os.environ, "PYTHONUTF8": "1"}, capture_output=True,
            text=True, encoding="utf-8", timeout=15, check=False,
        )

    def test_catalog_and_qr_are_usable_without_creating_app_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "unused"
            result = self.run_tool("--catalog", "--data-dir", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)), 34)
            result = self.run_tool("--qr-label", "01234567-89ab-4cde-8123-0123456789ab",
                                   "--data-dir", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("<svg", result.stdout)
            self.assertFalse(root.exists())

    def test_spoolman_file_preview_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "unused"
            source = Path(directory) / "input.json"
            payload = '[{"id":1,"filament":{"id":2},"archived":false,"remaining_weight":null}]'
            source.write_text(payload, encoding="utf-8")
            result = self.run_tool("--spoolman-preview", str(source), "--source-instance", "local",
                                   "--data-dir", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertIsNone(data["spools"][0]["estimated_remaining_mg"])
            self.assertEqual(source.read_text("utf-8"), payload)
            self.assertFalse(root.exists())

    def test_invalid_tool_input_is_localized_and_not_echoed(self) -> None:
        for locale in ("uk-UA", "en-US"):
            result = self.run_tool("--qr-label", "secret-invalid", "--locale", locale)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("secret-invalid", result.stderr)
            self.assertEqual(result.stdout, "")
        result = self.run_tool("--catalog", "--check")
        self.assertEqual(result.returncode, 2)

    def test_module_entry_point_in_both_languages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "дані UFM"
            for locale, expected in (
                ("uk-UA", "Перевірки запуску пройшли успішно."),
                ("en-US", "Startup checks passed."),
            ):
                with self.subTest(locale=locale):
                    result = subprocess.run(
                        [sys.executable, "-m", "ufm", "--check", "--locale", locale,
                         "--data-dir", str(root)],
                        env={**os.environ, "PYTHONUTF8": "1"},
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=15,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)
                    self.assertFalse(root.exists())

