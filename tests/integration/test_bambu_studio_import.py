"""Safe parsing of Bambu Studio's local LAN profile."""

import json
import tempfile
import unittest
from pathlib import Path

from ufm.integrations.printers.bambu_studio import (
    BambuStudioImportError,
    _load_settings,
    _private_host,
    _profile_from_settings,
)


class BambuStudioImportTests(unittest.TestCase):
    def test_extracts_only_profile_matching_the_certificate_and_ip(self) -> None:
        settings = {
            "access_code": {"00P00CABCDEF1234": "not-logged"},
            "ip_address": {"00P00CABCDEF1234": "192.168.1.20"},
            "models": [{"model": "Bambu Lab P1S"}],
        }

        imported = _profile_from_settings(
            settings,
            host="192.168.1.20",
            serial_number="00P00CABCDEF1234",
        )

        self.assertIsNotNone(imported)
        assert imported is not None
        model, code, ip_confirmed = imported
        self.assertEqual(model, "Bambu Lab P1S")
        self.assertEqual(code, "not-logged")
        self.assertTrue(ip_confirmed)

    def test_rejects_studio_profile_when_saved_ip_disagrees(self) -> None:
        settings = {
            "access_code": {"00P00CABCDEF1234": "secret"},
            "ip_address": {"00P00CABCDEF1234": "192.168.1.21"},
        }

        self.assertIsNone(_profile_from_settings(
            settings,
            host="192.168.1.20",
            serial_number="00P00CABCDEF1234",
        ))

    def test_handles_multiple_enabled_models_without_guessing(self) -> None:
        settings = {
            "access_code": {"00P00CABCDEF1234": "secret"},
            "models": [
                {"model": "Bambu Lab P1S"},
                {"model": "Bambu Lab X1 Carbon"},
            ],
        }

        imported = _profile_from_settings(
            settings,
            host="192.168.1.20",
            serial_number="00P00CABCDEF1234",
        )

        self.assertIsNotNone(imported)
        assert imported is not None
        self.assertIsNone(imported[0])

    def test_loads_bambu_settings_with_checksum_trailer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-studio-") as directory:
            path = Path(directory) / "BambuStudio.conf"
            path.write_text(
                json.dumps({"access_code": {}}) + "\n# MD5 checksum ignored\n",
                encoding="utf-8",
            )

            self.assertEqual(_load_settings(path), {"access_code": {}})

    def test_rejects_malformed_settings_explicitly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-studio-") as directory:
            path = Path(directory) / "BambuStudio.conf"
            path.write_text("{", encoding="utf-8")

            with self.assertRaises(BambuStudioImportError):
                _load_settings(path)

    def test_rejects_non_private_host(self) -> None:
        with self.assertRaises(BambuStudioImportError):
            _private_host("8.8.8.8")
