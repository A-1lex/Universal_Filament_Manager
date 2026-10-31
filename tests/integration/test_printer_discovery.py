"""Bounded local printer discovery tests; network I/O is mocked."""

import ipaddress
import json
import subprocess
import unittest
from unittest.mock import patch

from ufm.integrations.printers.discovery import (
    PrinterCandidate,
    PrinterDiscoveryError,
    _http_candidate,
    discover_printers,
    primary_local_network,
)


class PrinterDiscoveryTests(unittest.TestCase):
    def test_primary_network_uses_private_windows_route_and_caps_to_slash_24(
        self,
    ) -> None:
        result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({"IPAddress": "192.168.12.45", "PrefixLength": 20}),
            stderr="",
        )
        with patch(
            "ufm.integrations.printers.discovery.sys.platform", "win32",
        ), patch(
            "ufm.integrations.printers.discovery.subprocess.run", return_value=result,
        ) as mocked_run:
            network = primary_local_network()

        self.assertEqual(network, ipaddress.IPv4Network("192.168.12.0/24"))
        mocked_run.assert_called_once()
        self.assertEqual(
            mocked_run.call_args.kwargs["creationflags"],
            getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def test_primary_network_rejects_public_address(self) -> None:
        result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({"IPAddress": "8.8.8.8", "PrefixLength": 24}),
            stderr="",
        )
        with patch(
            "ufm.integrations.printers.discovery.sys.platform", "win32",
        ), patch(
            "ufm.integrations.printers.discovery.subprocess.run", return_value=result,
        ):
            with self.assertRaises(PrinterDiscoveryError):
                primary_local_network()

    def test_discovery_rejects_networks_larger_than_256_addresses(self) -> None:
        with self.assertRaises(PrinterDiscoveryError):
            discover_printers(ipaddress.IPv4Network("192.168.0.0/23"))

    def test_discovery_rejects_public_networks(self) -> None:
        with self.assertRaises(PrinterDiscoveryError):
            discover_printers(ipaddress.IPv4Network("8.8.8.0/24"))

    def test_discovery_probes_only_hosts_in_the_selected_network(self) -> None:
        with patch(
            "ufm.integrations.printers.discovery._probe_host",
            side_effect=lambda host: [],
        ) as probe_host:
            candidates = discover_printers(ipaddress.IPv4Network("192.168.1.0/30"))

        self.assertEqual(candidates, ())
        self.assertEqual(
            {call.args[0] for call in probe_host.call_args_list},
            {"192.168.1.1", "192.168.1.2"},
        )

    def test_octoprint_is_identified_by_api_response(self) -> None:
        candidate = _http_candidate(
            "192.168.1.20", 80, 200,
            b'{"api":"0.1","server":"1.10.0"}',
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.provider_type, "OCTOPRINT")
        self.assertEqual(candidate.confidence, "identified")

    def test_authorized_api_response_is_only_a_possible_candidate(self) -> None:
        candidate = _http_candidate("192.168.1.20", 7125, 401, b"")

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.provider_type, "MOONRAKER")
        self.assertEqual(candidate.confidence, "unverified")

    def test_unrelated_http_service_is_not_offered(self) -> None:
        self.assertIsNone(
            _http_candidate("192.168.1.20", 80, 200, b'{"status":"ok"}'),
        )

    def test_candidates_prefill_protocol_endpoint_without_credentials(self) -> None:
        octoprint = PrinterCandidate("OCTOPRINT", "192.168.1.20", 80, "identified")
        moonraker = PrinterCandidate("MOONRAKER", "192.168.1.21", 7125, "identified")
        bambu = PrinterCandidate("BAMBU_LAN", "192.168.1.22", 8883, "unverified")

        self.assertEqual(octoprint.endpoint, "http://192.168.1.20")
        self.assertEqual(moonraker.endpoint, "http://192.168.1.21:7125")
        self.assertEqual(bambu.endpoint, "192.168.1.22")
