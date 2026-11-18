"""Loopback read-only inventory API contract checks (no printer/network access)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest


@pytest.fixture
def api_backend(tmp_path):
    from ufm.bootstrap.app_container import create_container
    from ufm.bootstrap.settings import AppSettings
    from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
    from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
    from ufm.infrastructure.studio_backend import StudioBackend
    from ufm.platform.common.paths import AppPaths

    paths = AppPaths.resolve(tmp_path)
    container = create_container(AppSettings(), paths)
    engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
    try:
        migrate_database(engine)
        yield StudioBackend(engine, paths)
    finally:
        engine.dispose()
        container.close()


@pytest.fixture
def api_server(api_backend):
    from ufm.integrations.local_api import LocalApiServer

    server = LocalApiServer(api_backend, port=0)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _request(server, path: str, method: str = "GET") -> tuple[int, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.port}{path}", method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_local_api_serves_health_info_and_empty_catalog(api_server) -> None:
    status, payload = _request(api_server, "/api/v1/health")
    assert status == 200 and payload == {"status": "ok"}

    status, payload = _request(api_server, "/api/v1/info")
    assert status == 200
    assert payload["name"] == "Universal Filament Manager"
    assert payload["api"] == "spoolman-v1-readonly-subset"

    for path in (
        "/api/v1/spool", "/api/v1/filament", "/api/v1/material",
        "/api/v1/vendor", "/api/v1/location",
    ):
        status, payload = _request(api_server, path)
        assert status == 200 and payload == [], path


def test_local_api_spool_payload_matches_spoolman_shape(api_server, api_backend) -> None:
    brand_id = api_backend.add_brand("TestBrand", "api-brand")
    profile_id = api_backend.add_material(
        "Test PLA", "PLA", brand_id=brand_id,
    )
    api_backend.create_storage_location("Shelf A", "SHELF", "api-loc")
    spool_id = api_backend.add_spool(
        "API spool", profile_id, lot_number="L-42",
    )
    location_id = api_backend.storage_locations()[0].id
    spool_row = next(row for row in api_backend.spools() if row.id == spool_id)
    api_backend.assign_storage_location(spool_row, location_id, "api-assign")
    api_backend.change_stock(spool_id, "opening", "250", "api-opening")

    status, payload = _request(api_server, "/api/v1/spool")
    assert status == 200 and len(payload) == 1
    spool = payload[0]
    assert spool["id"] == spool_id
    assert spool["name"] == "API spool"
    assert spool["lot_nr"] == "L-42"
    assert spool["archived"] is False
    assert spool["remaining_weight"] == 250.0
    filament = spool["filament"]
    assert filament["id"] == profile_id
    assert filament["material"] == {"id": "PLA", "name": "PLA"}
    assert filament["vendor"] == {"id": brand_id, "name": "TestBrand"}
    assert spool["location"] == {"id": location_id, "name": "Shelf A"}

    status, payload = _request(api_server, f"/api/v1/spool/{spool_id}")
    assert status == 200 and payload["id"] == spool_id

    status, payload = _request(api_server, "/api/v1/spool/missing")
    assert status == 404

    status, payload = _request(api_server, "/api/v1/filament")
    assert status == 200 and payload[0]["id"] == profile_id

    status, payload = _request(api_server, "/api/v1/vendor")
    assert status == 200 and payload == [{"id": brand_id, "name": "TestBrand"}]

    status, payload = _request(api_server, "/api/v1/material")
    assert status == 200 and payload == [{"id": "PLA", "name": "PLA"}]

    status, payload = _request(api_server, "/api/v1/location")
    assert status == 200
    assert payload[0]["name"] == "Shelf A"


def test_local_api_rejects_writes_and_unknown_paths(api_server) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        status, payload = _request(api_server, "/api/v1/spool", method=method)
        assert status == 405, method
        assert payload["detail"] == "method not allowed"

    status, payload = _request(api_server, "/api/v1/unknown")
    assert status == 404


def test_local_api_start_stop_is_idempotent(api_backend) -> None:
    from ufm.integrations.local_api import LocalApiServer

    server = LocalApiServer(api_backend, port=0)
    assert not server.running
    first = server.start()
    assert server.running and first == server.port and first > 0
    assert server.start() == first
    server.stop()
    server.stop()
    assert not server.running
