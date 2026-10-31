"""Read-only local HTTP printer adapter tests using a throwaway loopback server."""

import asyncio
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from sqlalchemy import select

from ufm.application.ports.printers import AuthenticationFailed
from ufm.application.ports.secrets import SecretValue
from ufm.domain.enums import Availability, ConnectionState, PrintStatus
from ufm.domain.value_objects import EntityId
from ufm.infrastructure.persistence.models.schema import connection_profile, printer
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.integrations.printers import (
    MoonrakerProvider,
    OctoPrintProvider,
    configure_local_printer,
)


class _PrinterHandler(BaseHTTPRequestHandler):
    authorization: str | None = None
    rejected = False

    def do_GET(self) -> None:
        token = self.headers.get("X-Api-Key") or self.headers.get("Authorization")
        self.__class__.authorization = token
        if self.__class__.rejected:
            self.send_response(401)
            self.end_headers()
            return
        path = urlsplit(self.path).path
        if path == "/api/version":
            payload = {"api": "0.1", "server": "1.10.0"}
        elif path == "/api/printer":
            payload = {
                "temperature": {
                    "tool0": {"actual": 210.5},
                    "bed": {"actual": 60.0},
                },
            }
        elif path == "/api/job":
            payload = {
                "state": "Paused",
                "job": {"file": {"name": "fixture.gcode"}},
                "progress": {"completion": 50.5},
            }
        elif path == "/server/info":
            payload = {"result": {"klippy_connected": True}}
        elif path == "/printer/objects/query":
            payload = {
                "result": {
                    "status": {
                        "print_stats": {
                            "state": "printing", "filename": "fixture.gcode",
                            "filament_used": 230.8,
                        },
                        "display_status": {"progress": 0.4},
                        "extruder": {"temperature": 215.5},
                        "heater_bed": {"temperature": 55.0},
                    },
                },
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class _MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def put(self, secret: SecretValue) -> str:
        reference = f"ufm:credential:{EntityId.new()}"
        self.values[reference] = secret.reveal()
        return reference

    def get(self, reference: str) -> SecretValue:
        return SecretValue(self.values[reference])

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class LocalPrinterProviderTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _PrinterHandler.authorization = None
        _PrinterHandler.rejected = False
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _PrinterHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        _PrinterHandler.authorization = None
        _PrinterHandler.rejected = False
        self.printer_id = EntityId.new()
        self.provider_id = EntityId.new()

    async def test_octoprint_reads_status_and_active_job_without_mutations(self) -> None:
        provider = OctoPrintProvider(
            printer_id=self.printer_id,
            provider_instance_id=self.provider_id,
            endpoint=self.endpoint,
            token=SecretValue("test-api-token"),
        )
        await provider.connect()
        status = await provider.get_status()
        job = await provider.get_current_job()

        self.assertEqual(status.connection_state, ConnectionState.ONLINE)
        self.assertEqual(status.nozzle_temperature_c.value.canonical(), "210.5")
        self.assertEqual(status.bed_temperature_c.value.canonical(), "60")
        self.assertEqual(status.feed_systems, ())
        self.assertEqual(job.availability, Availability.KNOWN)
        self.assertEqual(job.job.status, PrintStatus.PAUSED)
        self.assertEqual(job.job.progress_bp, 5050)
        self.assertIsNone(job.job.external_job_id)
        self.assertEqual(_PrinterHandler.authorization, "test-api-token")
        capabilities = await provider.get_capabilities()
        self.assertFalse(capabilities.filament_usage.value)

    async def test_moonraker_reads_print_stats_and_reports_usage_as_estimate(self) -> None:
        provider = MoonrakerProvider(
            printer_id=self.printer_id,
            provider_instance_id=self.provider_id,
            endpoint=self.endpoint,
            token=SecretValue("test-bearer-token"),
        )
        await provider.connect()
        status = await provider.get_status()
        job = await provider.get_current_job()

        self.assertEqual(status.progress.value, 4000)
        self.assertEqual(status.current_layer.availability, Availability.UNKNOWN)
        self.assertEqual(status.nozzle_temperature_c.value.canonical(), "215.5")
        self.assertEqual(job.job.status, PrintStatus.RUNNING)
        self.assertEqual(job.job.progress_bp, 4000)
        self.assertIsNone(job.job.provider_run_key)
        self.assertEqual(await provider.estimated_filament_usage_mm(), 231)
        self.assertEqual(_PrinterHandler.authorization, "Bearer test-bearer-token")
        self.assertFalse((await provider.get_capabilities()).filament_usage.value)

    async def test_auth_failure_is_typed_and_does_not_echo_server_body(self) -> None:
        _PrinterHandler.rejected = True
        provider = OctoPrintProvider(
            printer_id=self.printer_id,
            provider_instance_id=self.provider_id,
            endpoint=self.endpoint,
            token=SecretValue("not-logged"),
        )
        with self.assertRaises(AuthenticationFailed) as raised:
            await provider.connect()
        self.assertEqual(str(raised.exception), "provider.authentication_failed")
        self.assertNotIn("not-logged", str(raised.exception))

    async def test_health_reports_unavailable_without_silent_success(self) -> None:
        provider = MoonrakerProvider(
            printer_id=self.printer_id,
            provider_instance_id=self.provider_id,
            endpoint="http://127.0.0.1:1",
        )
        health = await provider.health()
        self.assertEqual(health.reason_code, "provider.unavailable")
        self.assertTrue(health.retryable)

    async def test_configuration_tests_then_saves_only_os_secret_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-local-printer-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            configured = await configure_local_printer(
                engine=engine,
                secret_store=secrets,
                name="Test printer",
                manufacturer="Example",
                model="OctoPrint",
                provider_type="OCTOPRINT",
                endpoint=self.endpoint,
                token=SecretValue("test-api-token"),
            )
            self.assertEqual(configured.provider_type, "OCTOPRINT")
            self.assertEqual(secrets.values[configured.credential_ref], "test-api-token")
            with engine.connect() as connection:
                saved_printer = connection.execute(
                    select(printer.c.name, printer.c.manufacturer, printer.c.model)
                    .where(printer.c.id == configured.printer_id)
                ).one()
                saved_profile = connection.execute(
                    select(
                        connection_profile.c.provider_type,
                        connection_profile.c.connection_mode,
                        connection_profile.c.host,
                        connection_profile.c.credential_ref,
                    ).where(connection_profile.c.printer_id == configured.printer_id)
                ).one()
            engine.dispose()
            self.assertEqual(saved_printer, ("Test printer", "Example", "OctoPrint"))
            self.assertEqual(saved_profile.provider_type, "OCTOPRINT")
            self.assertEqual(saved_profile.connection_mode, "LOCAL")
            self.assertEqual(saved_profile.host, "127.0.0.1")
            self.assertEqual(saved_profile.credential_ref, configured.credential_ref)
            self.assertNotIn("test-api-token", repr(saved_profile))

    async def test_event_polling_emits_first_snapshot_and_suppresses_repeats(self) -> None:
        provider = OctoPrintProvider(
            printer_id=self.printer_id,
            provider_instance_id=self.provider_id,
            endpoint=self.endpoint,
            token=SecretValue("test-api-token"),
        )
        events = provider.subscribe_events()
        event = await anext(events)
        self.assertEqual(event.provider_instance_id, self.provider_id)
        self.assertEqual(event.printer_id, self.printer_id)
        self.assertEqual(event.kind, "current_job")
        self.assertEqual(event.event_key, "1")
        with patch(
            "ufm.integrations.printers.local_http.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await anext(events)
        await events.aclose()

    def test_endpoint_rejects_non_local_and_credential_bearing_urls(self) -> None:
        for endpoint in (
            "https://127.0.0.1",
            "http://user:password@127.0.0.1",
            "http://203.0.113.10",
            "http://printer.local",
            "http://127.0.0.1/path",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    OctoPrintProvider(
                        printer_id=self.printer_id,
                        provider_instance_id=self.provider_id,
                        endpoint=endpoint,
                    )
