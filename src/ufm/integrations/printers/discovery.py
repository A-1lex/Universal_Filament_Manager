"""Bounded discovery of common printer services on the primary private LAN."""

from __future__ import annotations

import concurrent.futures
import http.client
import ipaddress
import json
import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

_DISCOVERY_PORTS = (80, 7125, 8883)
_CONNECT_TIMEOUT_SECONDS = 0.35
_HTTP_RESPONSE_LIMIT = 64 * 1024
_MAX_DISCOVERY_HOSTS = 256
_PRIVATE_IPV4_NETWORKS = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


class PrinterDiscoveryError(RuntimeError):
    """The primary private LAN could not be determined or safely searched."""


@dataclass(frozen=True, slots=True)
class PrinterCandidate:
    provider_type: str
    host: str
    port: int
    confidence: str

    @property
    def name(self) -> str:
        provider = {
            "OCTOPRINT": "OctoPrint",
            "MOONRAKER": "Moonraker",
            "BAMBU_LAN": "Bambu Lab",
        }[self.provider_type]
        return f"{provider} — {self.host}"

    @property
    def endpoint(self) -> str:
        if self.provider_type == "BAMBU_LAN":
            return self.host
        return (
            f"http://{self.host}"
            if self.port == 80 else f"http://{self.host}:{self.port}"
        )


def primary_local_network() -> ipaddress.IPv4Network:
    """Return the primary Windows private LAN, capped to at most 256 addresses."""
    if sys.platform != "win32":
        raise PrinterDiscoveryError("printer.discovery_windows_only")

    script = (
        "$route = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "
        "'0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1; "
        "if ($null -eq $route) { exit 2 }; "
        "Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex "
        "$route.InterfaceIndex -AddressState Preferred | "
        "Where-Object { $_.IPAddress -notlike '169.254.*' } | "
        "Select-Object -First 1 IPAddress,PrefixLength | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script),
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PrinterDiscoveryError("printer.discovery_network_unavailable") from None
    if result.returncode != 0:
        raise PrinterDiscoveryError("printer.discovery_network_unavailable")
    try:
        details: Any = json.loads(result.stdout)
        address = ipaddress.IPv4Address(details["IPAddress"])
        prefix = details["PrefixLength"]
        if type(prefix) is not int or not 1 <= prefix <= 32:
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise PrinterDiscoveryError("printer.discovery_network_unavailable") from None
    if not any(address in private for private in _PRIVATE_IPV4_NETWORKS):
        raise PrinterDiscoveryError("printer.discovery_private_lan_only")
    if prefix < 24:
        prefix = 24
    return ipaddress.IPv4Network((address, prefix), strict=False)


def _http_candidate(
    host: str,
    port: int,
    status: int,
    body: bytes,
) -> PrinterCandidate | None:
    try:
        payload: Any = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None

    if port == 80 and (
        status in (401, 403)
        or (
            isinstance(payload, dict)
            and isinstance(payload.get("api"), str)
            and isinstance(payload.get("server"), str)
        )
    ):
        return PrinterCandidate(
            "OCTOPRINT", host, port,
            "unverified" if status in (401, 403) else "identified",
        )
    if port == 7125 and (
        status in (401, 403)
        or (isinstance(payload, dict) and isinstance(payload.get("result"), dict))
    ):
        return PrinterCandidate(
            "MOONRAKER", host, port,
            "unverified" if status in (401, 403) else "identified",
        )
    return None


def _probe_port(host: str, port: int) -> PrinterCandidate | None:
    try:
        with socket.create_connection(
            (host, port), timeout=_CONNECT_TIMEOUT_SECONDS,
        ):
            pass
    except OSError:
        return None

    if port == 8883:
        return PrinterCandidate("BAMBU_LAN", host, port, "unverified")
    if port not in (80, 7125):
        return None

    path = "/api/version" if port == 80 else "/server/info"
    connection = http.client.HTTPConnection(
        host, port, timeout=_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            return None
        body = response.read(_HTTP_RESPONSE_LIMIT + 1)
        if len(body) > _HTTP_RESPONSE_LIMIT:
            return None
        return _http_candidate(host, port, response.status, body)
    except (OSError, http.client.HTTPException, TimeoutError):
        return None
    finally:
        connection.close()


def _probe_host(host: str) -> list[PrinterCandidate]:
    return [
        candidate
        for port in _DISCOVERY_PORTS
        if (candidate := _probe_port(host, port)) is not None
    ]


def discover_printers(
    network: ipaddress.IPv4Network,
) -> tuple[PrinterCandidate, ...]:
    """Check only the three supported service ports on a bounded private IPv4 LAN."""
    if (
        not isinstance(network, ipaddress.IPv4Network)
        or not any(network.subnet_of(private) for private in _PRIVATE_IPV4_NETWORKS)
        or network.num_addresses > _MAX_DISCOVERY_HOSTS
    ):
        raise PrinterDiscoveryError("printer.discovery_network_too_large")

    hosts = [str(address) for address in network.hosts()]
    candidates: list[PrinterCandidate] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        for found in executor.map(_probe_host, hosts):
            candidates.extend(found)
    return tuple(sorted(candidates, key=lambda item: (item.host, item.port)))
