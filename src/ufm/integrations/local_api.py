"""Loopback read-only HTTP API exposing UFM inventory to local consumers.

Implements a Spoolman v1-compatible GET subset so existing slicer,
Moonraker/OctoPrint/Home Assistant style consumers can read stock.
Write methods are intentionally unsupported (405); accounting mutations
never pass through this surface.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

import ufm

if TYPE_CHECKING:
    from ufm.infrastructure.studio_backend import (
        StudioBackend,
        StudioMaterial,
        StudioSpool,
    )


class _ApiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], backend: StudioBackend) -> None:
        super().__init__(address, _ApiRequestHandler)
        self.backend = backend


class LocalApiServer:
    """Hosts the read-only inventory API on a daemon thread."""

    def __init__(self, backend: StudioBackend, *, host: str = "127.0.0.1", port: int = 7912) -> None:
        self._backend = backend
        self._host = host
        self._port = port
        self._server: _ApiHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        """Bind and start serving; returns the actual bound port."""
        if self._server is not None:
            return self.port
        server = _ApiHTTPServer((self._host, self._port), self._backend)
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="ufm-local-api",
            daemon=True,
        )
        self._thread.start()
        return server.server_address[1]

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)

    @property
    def port(self) -> int:
        if self._server is None:
            return self._port
        return int(self._server.server_address[1])

    @property
    def running(self) -> bool:
        return self._server is not None


def _grams(milligrams: int | None) -> float | None:
    return None if milligrams is None else milligrams / 1000


def _filament_payload(material: StudioMaterial) -> dict[str, Any]:
    try:
        diameter = float(material.diameter_mm)
    except (TypeError, ValueError):
        diameter = 1.75
    density = None
    if material.density_g_cm3 is not None:
        try:
            density = float(material.density_g_cm3)
        except ValueError:
            density = None
    return {
        "id": material.id,
        "name": material.name,
        "material": {"id": material.material, "name": material.material},
        "vendor": (
            {"id": material.brand_id, "name": material.brand}
            if material.brand_id is not None else None
        ),
        "diameter": diameter,
        "density": density,
        "extra": {
            "product_line": material.product_line,
            "subtype": material.subtype,
            "abrasive": material.abrasive,
            "flexible": material.flexible,
            "hygroscopic": material.hygroscopic,
            "soluble": material.soluble,
            "filled_material": material.filled_material,
            "custom_material_name": material.custom_material_name,
        },
    }


def _spool_payload(
    spool: StudioSpool,
    filament: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "id": spool.id,
        "name": spool.name,
        "registered": spool.opened_date,
        "first_used": None,
        "last_used": None,
        "remaining_weight": _grams(spool.remaining_mg),
        "remaining_length": None,
        "filament": filament,
        "location": (
            {"id": spool.location_id, "name": spool.location}
            if spool.location_id is not None else None
        ),
        "lot_nr": spool.lot_number,
        "archived": spool.lifecycle == "ARCHIVED",
        "extra": {
            "material": spool.material,
            "profile": spool.profile,
            "color_name": spool.color_name,
            "color_hex": spool.color_hex,
            "secondary_color_hex": spool.secondary_color_hex,
            "health": spool.health,
            "lifecycle": spool.lifecycle,
            "product_line": spool.product_line,
            "batch_number": spool.batch_number,
            "low_threshold_grams": _grams(spool.low_threshold_mg),
            "nominal_filament_grams": _grams(spool.nominal_filament_mg),
            "empty_spool_grams": _grams(spool.empty_spool_mg),
            "notes": spool.notes,
            "revision": spool.revision,
        },
    }


def _catalog_payloads(backend: StudioBackend) -> tuple[
    dict[str, dict[str, Any]], dict[str, StudioSpool],
]:
    filaments = {
        material.id: _filament_payload(material)
        for material in backend.materials()
    }
    spools = {spool.id: spool for spool in backend.spools()}
    return filaments, spools


def _route_get(backend: StudioBackend, path: str) -> tuple[int, Any]:
    if path in {"/api/v1/health", "/health"}:
        return 200, {"status": "ok"}
    if path in {"/api/v1/info", "/info"}:
        return 200, {
            "name": "Universal Filament Manager",
            "version": ufm.__version__,
            "api": "spoolman-v1-readonly-subset",
        }
    if path == "/api/v1/spool/group":
        return 200, {}
    if path == "/api/v1/spool":
        filaments, spools = _catalog_payloads(backend)
        return 200, [
            _spool_payload(spool, filaments.get(spool.profile_id))
            for spool in spools.values()
        ]
    if path.startswith("/api/v1/spool/") or path.startswith("/spool/"):
        prefix = "/api/v1/spool/" if path.startswith("/api/v1/") else "/spool/"
        spool_id = unquote(path[len(prefix):])
        filaments, spools = _catalog_payloads(backend)
        spool = spools.get(spool_id)
        if spool is None:
            return 404, {"detail": "spool not found"}
        return 200, _spool_payload(spool, filaments.get(spool.profile_id))
    if path in {"/api/v1/filament", "/api/v1/filament/"}:
        filaments, _spools = _catalog_payloads(backend)
        return 200, list(filaments.values())
    if path.startswith("/api/v1/filament/"):
        filament_id = unquote(path[len("/api/v1/filament/"):])
        filaments, _spools = _catalog_payloads(backend)
        payload = filaments.get(filament_id)
        if payload is None:
            return 404, {"detail": "filament not found"}
        return 200, payload
    if path in {"/api/v1/material", "/api/v1/material/"}:
        names = sorted({material.material for material in backend.materials()})
        return 200, [{"id": name, "name": name} for name in names]
    if path in {"/api/v1/vendor", "/api/v1/vendor/"}:
        return 200, [
            {"id": brand.id, "name": brand.name}
            for brand in backend.brand_records()
        ]
    if path.startswith("/api/v1/vendor/"):
        vendor_id = unquote(path[len("/api/v1/vendor/"):])
        for brand in backend.brand_records():
            if brand.id == vendor_id:
                return 200, {"id": brand.id, "name": brand.name}
        return 404, {"detail": "vendor not found"}
    if path in {"/api/v1/location", "/api/v1/location/"}:
        return 200, [
            {"id": item.id, "name": item.name, "parent_id": item.parent_id}
            for item in backend.storage_locations()
        ]
    return 404, {"detail": "not found"}


class _ApiRequestHandler(BaseHTTPRequestHandler):
    server_version = "UfmLocalApi"
    protocol_version = "HTTP/1.1"
    timeout = 10

    @property
    def _api_server(self) -> _ApiHTTPServer:
        return self.server  # type: ignore[return-value]

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            status, payload = _route_get(self._api_server.backend, path)
        except Exception:
            status, payload = 500, {"detail": "internal error"}
        self._send_json(status, payload)

    def _method_not_allowed(self) -> None:
        body = b'{"detail": "method not allowed"}'
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_PATCH = do_DELETE = _method_not_allowed  # noqa: N815

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return
