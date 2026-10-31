"""Bounded Bambu SSDP identity discovery; never requests or guesses credentials."""

import ipaddress
import re
import selectors
import socket
import time
from dataclasses import dataclass

from ufm.integrations.printers.bambu_studio import (
    BambuPrinterIdentity,
    BambuStudioImportError,
    _certificate_chain,
    _private_host,
)

_GROUP = "239.255.255.250"
_PORTS = (1990, 2021)
_LIMIT = 8192
_MODELS = {
    "C12": "Bambu Lab P1S", "C11": "Bambu Lab P1P", "C13": "Bambu Lab X1E",
    "BL-P001": "Bambu Lab X1 Carbon", "BL-P002": "Bambu Lab X1",
    "N1": "Bambu Lab A1 mini", "N2S": "Bambu Lab A1",
}


@dataclass(frozen=True, slots=True)
class BambuAdvertisement:
    host: str
    name: str
    serial_number: str
    model_code: str


def parse_bambu_advertisement(data: bytes, sender: str) -> BambuAdvertisement | None:
    if len(data) > _LIMIT:
        return None
    try:
        address = ipaddress.ip_address(_private_host(sender))
        if address.version != 4:
            return None
        lines = data.decode("utf-8").splitlines()
        if not lines or lines[0] not in ("NOTIFY * HTTP/1.1", "HTTP/1.1 200 OK"):
            return None
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line.strip():
                continue
            key, separator, value = line.partition(":")
            key = key.strip().lower()
            if not separator or key in headers:
                return None
            headers[key] = value.strip()
        if not headers.get("nt", headers.get("st", "")).startswith("urn:bambulab-com:device:"):
            return None
        # Treat Location as data, never follow an advertised URL or another host.
        if headers.get("location") != str(address):
            return None
        serial = headers.get("usn", "").removeprefix("uuid:").split("::", 1)[0]
        model = headers.get("devmodel.bambu.com", "")
        name = headers.get("devname.bambu.com", "").strip()
        if (not re.fullmatch(r"[A-Za-z0-9]{8,64}", serial)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", model)
            or len(name) > 200 or any(ord(char) < 32 for char in name)):
            return None
        return BambuAdvertisement(str(address), name, serial, model)
    except (ValueError, UnicodeError, BambuStudioImportError):
        return None


def discover_bambu_printers(timeout: float = 5.0) -> tuple[BambuAdvertisement, ...]:
    if not 0 < timeout <= 10:
        raise ValueError("printer.discovery_timeout_invalid")
    found: dict[str, BambuAdvertisement] = {}
    ambiguous: set[str] = set()
    request = (
        "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\nMX: 1\r\n'
        "ST: urn:bambulab-com:device:3dprinter:1\r\n\r\n"
    ).encode("ascii")
    sockets: list[socket.socket] = []
    with selectors.DefaultSelector() as selector:
        try:
            # Studio can own 2021 exclusively. Other announcement/response ports
            # remain optional, with direct IP/certificate identification as fallback.
            for port in (*_PORTS, 0):
                connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sockets.append(connection)
                try:
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    connection.bind(("", port))
                    if port:
                        membership = socket.inet_aton(_GROUP) + socket.inet_aton("0.0.0.0")
                        connection.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
                    connection.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                    connection.setblocking(False)
                    selector.register(connection, selectors.EVENT_READ)
                    connection.sendto(request, (_GROUP, 1900))
                except OSError:
                    # An unavailable socket must not reach select().
                    try:
                        selector.unregister(connection)
                    except KeyError:
                        pass
                    connection.close()
            deadline = time.monotonic() + timeout
            received = 0
            while selector.get_map() and received < 256:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                for key, _ in selector.select(remaining):
                    incoming = key.fileobj
                    assert isinstance(incoming, socket.socket)
                    try:
                        data, sender = incoming.recvfrom(_LIMIT + 1)
                    except (OSError, BlockingIOError):
                        continue
                    received += 1
                    candidate = parse_bambu_advertisement(data, sender[0])
                    if candidate is None:
                        continue
                    previous = found.get(candidate.host)
                    if previous and (previous.serial_number, previous.model_code) != (
                        candidate.serial_number, candidate.model_code,
                    ):
                        ambiguous.add(candidate.host)
                    found[candidate.host] = candidate
        finally:
            for connection in sockets:
                connection.close()
    return tuple(found[host] for host in sorted(found) if host not in ambiguous)


def identify_bambu_printer(host: str = "") -> BambuPrinterIdentity:
    clean_host = _private_host(host) if host.strip() else ""
    try:
        advertisements = discover_bambu_printers()
    except OSError:
        advertisements = ()
    candidates = tuple(item for item in advertisements if not clean_host or item.host == clean_host)
    if not clean_host:
        if len(candidates) != 1:
            raise BambuStudioImportError("printer.network_multiple" if candidates else
                                        "printer.network_not_found")
        clean_host = candidates[0].host
    serial, fingerprint, root = _certificate_chain(clean_host)
    candidate = candidates[0] if candidates else None
    if candidate is not None and candidate.serial_number != serial:
        raise BambuStudioImportError("printer.network_identity_mismatch")
    model = _MODELS.get(candidate.model_code, candidate.model_code) if candidate else None
    # Vendor profile C12.json documents the P1S serial prefix 01P. Do not guess
    # other model names from a generic open MQTT port or a shared hardware code.
    if model is None and serial.startswith("01P"):
        model = "Bambu Lab P1S"
    return BambuPrinterIdentity(
        clean_host, (candidate.name if candidate else "") or model or serial,
        serial, model, fingerprint, root,
    )
