"""Autofill never invents credentials or trusts conflicting device identity."""

import unittest
from unittest.mock import patch

from ufm.integrations.printers import bambu_discovery as discovery
from ufm.integrations.printers.bambu_studio import BambuStudioImportError


def advertisement(**overrides):
    headers = {"Location": "192.168.0.189", "NT": "urn:bambulab-com:device:3dprinter:1",
               "USN": "01P00TEST1234567", "DevModel.bambu.com": "C12",
               "DevName.bambu.com": "Workshop"} | overrides
    return ("NOTIFY * HTTP/1.1\r\n" + "\r\n".join(
        f"{name}: {value}" for name, value in headers.items()
    ) + "\r\n\r\n").encode()


class BambuNetworkAutofillTests(unittest.TestCase):
    def test_decodes_headers_without_access_code(self):
        result = discovery.parse_bambu_advertisement(advertisement(), "192.168.0.189")
        self.assertEqual(result.model_code, "C12")
        self.assertEqual(result.serial_number, "01P00TEST1234567")
        self.assertFalse(hasattr(result, "access_code"))

    def test_rejects_redirected_oversized_and_conflicting_headers(self):
        packets = (advertisement(Location="http://192.168.0.189/private"),
                   advertisement(Location="192.168.0.190"), advertisement(NT="upnp:rootdevice"),
                   advertisement(USN="invalid"), advertisement(**{"DevName.bambu.com": "x" * 201}),
                   advertisement() + b"\r\nUSN: ANOTHERSERIAL\r\n", b"x" * 8193)
        for data in packets:
            with self.subTest(data=data[:30]):
                self.assertIsNone(discovery.parse_bambu_advertisement(data, "192.168.0.189"))
        self.assertIsNone(discovery.parse_bambu_advertisement(advertisement(), "8.8.8.8"))

    def test_fills_model_and_certificate_identity(self):
        device = discovery.parse_bambu_advertisement(advertisement(), "192.168.0.189")
        with patch.object(discovery, "discover_bambu_printers", return_value=(device,)), \
             patch.object(discovery, "_certificate_chain",
                          return_value=(device.serial_number, "a" * 64, "issuer")):
            result = discovery.identify_bambu_printer(device.host)
        self.assertEqual(result.model, "Bambu Lab P1S")
        self.assertEqual(result.name, device.name)
        self.assertFalse(hasattr(result, "access_code"))

    def test_direct_ip_fallback_while_studio_owns_discovery_port(self):
        with patch.object(discovery, "discover_bambu_printers", side_effect=OSError), \
             patch.object(discovery, "_certificate_chain",
                          return_value=("01P00TEST1234567", "a" * 64, "issuer")):
            result = discovery.identify_bambu_printer("192.168.0.189")
        self.assertEqual(result.model, "Bambu Lab P1S")

    def test_rejects_advertisement_certificate_mismatch(self):
        device = discovery.parse_bambu_advertisement(advertisement(), "192.168.0.189")
        with patch.object(discovery, "discover_bambu_printers", return_value=(device,)), \
             patch.object(discovery, "_certificate_chain",
                          return_value=("ANOTHERSERIAL", "a" * 64, "issuer")):
            with self.assertRaisesRegex(BambuStudioImportError, "identity_mismatch"):
                discovery.identify_bambu_printer(device.host)

    def test_empty_ip_selects_one_device_and_rejects_ambiguity(self):
        device = discovery.parse_bambu_advertisement(advertisement(), "192.168.0.189")
        with patch.object(discovery, "discover_bambu_printers", return_value=(device,)), \
             patch.object(discovery, "_certificate_chain",
                          return_value=(device.serial_number, "a" * 64, "issuer")):
            self.assertEqual(discovery.identify_bambu_printer().host, device.host)
        second = discovery.BambuAdvertisement("192.168.0.190", "Other", "ANOTHERSERIAL", "C12")
        for candidates in ((), (device, second)):
            with self.subTest(candidates=candidates), \
                 patch.object(discovery, "discover_bambu_printers", return_value=candidates), \
                 patch.object(discovery, "_certificate_chain") as certificate:
                with self.assertRaises(BambuStudioImportError):
                    discovery.identify_bambu_printer()
                certificate.assert_not_called()

    def test_unknown_model_is_not_guessed_from_a_port(self):
        with patch.object(discovery, "discover_bambu_printers", return_value=()), \
             patch.object(discovery, "_certificate_chain",
                          return_value=("TESTUNKNOWN123", "a" * 64, "issuer")):
            result = discovery.identify_bambu_printer("192.168.0.189")
        self.assertIsNone(result.model)

    def test_tls_context_file_error_is_sanitized_as_certificate_unavailable(self):
        from ufm.integrations.printers import bambu_studio

        with patch.object(bambu_studio.ssl, "SSLContext", side_effect=FileNotFoundError):
            with self.assertRaises(BambuStudioImportError) as raised:
                bambu_studio._certificate_chain("192.168.0.189")
        self.assertEqual(raised.exception.code, "printer.studio_certificate_unavailable")
