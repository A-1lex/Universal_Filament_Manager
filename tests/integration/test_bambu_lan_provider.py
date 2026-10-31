"""Bambu LAN provider normalization and secure profile setup tests."""

import asyncio
import hashlib
import json
import ssl
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from ufm.application.dto import ProviderMaterialSlotMapping
from ufm.application.ports.printers import (
    AuthenticationFailed,
    ProviderUnavailable,
    TLSVerificationFailed,
)
from ufm.application.ports.secrets import SecretStoreUnavailable, SecretValue
from ufm.domain.enums import (
    Availability,
    ConnectionState,
    FeedSystemKind,
    PrintStatus,
    ProviderHealthState,
)
from ufm.domain.value_objects import EntityId, Mass
from ufm.infrastructure.persistence.models.schema import connection_profile, printer
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.integrations.printers import (
    BambuLanProvider,
    configure_bambu_printer,
    probe_configured_printer,
    remove_configured_printer,
)
from ufm.integrations.printers import configuration as printer_configuration
from ufm.integrations.printers.bambu_lan import _PinnedMqttClient
from ufm.integrations.printers.configuration import configured_printer_provider


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


class _FailingDeleteSecrets(_MemorySecrets):
    def delete(self, reference: str) -> None:
        raise SecretStoreUnavailable()


class BambuLanProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.printer_id = EntityId.new()
        self.provider_id = EntityId.new()
        self.provider = BambuLanProvider(
            printer_id=self.printer_id,
            provider_instance_id=self.provider_id,
            host="127.0.0.1",
            serial_number="00P00CABCDEF1234",
            access_code=SecretValue("12345678"),
        )
        self.provider._connected.set()
        self.provider._report = {
            "gcode_state": "RUNNING",
            "mc_percent": 41,
            "layer_num": 12,
            "nozzle_temper": "220.5",
            "bed_temper": 60,
            "ams": {
                "ams": [{
                    "id": 0,
                    "tray": [
                        {"id": 0, "tray_type": "PLA", "tray_uuid": "tray-uuid", "remain": 62},
                        {"id": 1},
                    ],
                }],
            },
            "vt_tray": {"tray_type": "PETG"},
        }

    async def test_disconnect_wakes_waiting_report_reader(self) -> None:
        self.provider._report = {}
        waiting = asyncio.create_task(asyncio.to_thread(self.provider._wait_report))
        await asyncio.sleep(0.02)

        await self.provider.disconnect()

        with self.assertRaises(ProviderUnavailable):
            await asyncio.wait_for(waiting, timeout=1)

    async def test_paho_v2_connack_reason_codes_are_classified_without_int_cast(self) -> None:
        client = Mock()
        self.provider._connected.clear()

        self.provider._on_connect(
            client, None, None, ReasonCode(PacketTypes.CONNACK, "Success"), None,
        )

        self.assertTrue(self.provider._connected.is_set())
        self.assertIsNone(self.provider._connection_error)
        client.subscribe.assert_called_once_with(
            f"device/{self.provider.serial_number}/report", qos=0,
        )
        client.publish.assert_called_once()

        for reason_name in ("Bad user name or password", "Not authorized"):
            with self.subTest(reason_name=reason_name):
                self.provider._connected.clear()
                self.provider._connection_error = None
                client.reset_mock()

                self.provider._on_connect(
                    client, None, None,
                    ReasonCode(PacketTypes.CONNACK, reason_name), None,
                )

                self.assertTrue(self.provider._connected.is_set())
                self.assertIsInstance(
                    self.provider._connection_error, AuthenticationFailed,
                )
                client.subscribe.assert_not_called()
                client.publish.assert_not_called()

        self.provider._connected.clear()
        self.provider._connection_error = None
        client.reset_mock()
        self.provider._on_connect(
            client, None, None,
            ReasonCode(PacketTypes.CONNACK, "Server unavailable"), None,
        )
        self.assertTrue(self.provider._connected.is_set())
        self.assertIsInstance(self.provider._connection_error, ProviderUnavailable)
        client.subscribe.assert_not_called()
        client.publish.assert_not_called()

    async def test_disconnect_preserves_precise_connack_authentication_error(self) -> None:
        self.provider._connected.set()
        self.provider._connection_error = AuthenticationFailed()

        self.provider._on_disconnect(
            Mock(), None, None,
            ReasonCode(PacketTypes.DISCONNECT, "Not authorized"), None,
        )

        self.assertIsInstance(self.provider._connection_error, AuthenticationFailed)
        self.assertFalse(self.provider._connected.is_set())

    async def test_health_requires_a_new_print_report_after_pushall(self) -> None:
        client = Mock()
        self.provider._client = client
        self.provider._report_generation = 4

        def publish(topic, payload, *, qos):
            request = json.loads(payload)
            if request.get("pushing", {}).get("command") == "pushall":
                message = mqtt.MQTTMessage(1)
                message.topic = f"device/{self.provider.serial_number}/report".encode()
                message.payload = b'{"print":{"gcode_state":"IDLE"}}'
                self.provider._on_message(client, None, message)
            return Mock(rc=0)

        client.publish.side_effect = publish

        health = await self.provider.health()

        self.assertEqual(health.state, ProviderHealthState.HEALTHY)
        self.assertEqual(self.provider._report_generation, 5)
        self.assertEqual(client.publish.call_count, 2)
        self.assertEqual(
            [call.kwargs["qos"] for call in client.publish.call_args_list], [1, 0],
        )

    async def test_health_marks_connection_stale_when_pushall_gets_no_fresh_report(self) -> None:
        client = Mock()
        self.provider._client = client
        self.provider._report_generation = 4
        client.publish.return_value = Mock(rc=0)

        with patch("ufm.integrations.printers.bambu_lan._REPORT_TIMEOUT_SECONDS", 0.01):
            health = await self.provider.health()

        self.assertEqual(health.state, ProviderHealthState.DEGRADED)
        self.assertEqual(health.reason_code, "provider.stale")
        self.assertTrue(health.retryable)
        self.assertEqual(client.publish.call_count, 2)

    async def test_reads_running_job_temperatures_and_ams_without_inventing_stock(self) -> None:
        status = await self.provider.get_status()
        job = await self.provider.get_current_job()
        self.assertEqual(status.printer_id, self.printer_id)
        self.assertEqual(status.connection_state, ConnectionState.ONLINE)
        self.assertEqual(status.progress.value, 4100)
        self.assertEqual(status.current_layer.value, 12)
        self.assertEqual(status.nozzle_temperature_c.value.canonical(), "220.5")
        self.assertEqual(len(status.feed_systems), 2)
        ams = status.feed_systems[0]
        self.assertEqual(ams.kind, FeedSystemKind.AMS)
        self.assertFalse(ams.complete)
        self.assertEqual(len(ams.slots), 2)
        self.assertEqual(ams.slots[0].tray_uuid.value, "tray-uuid")
        self.assertEqual(ams.slots[0].remaining_mass.availability, Availability.UNKNOWN)
        self.assertEqual(ams.slots[0].remaining_percent.value, 62)
        self.assertIs(ams.slots[0].remaining_percent.availability, Availability.KNOWN)
        self.assertEqual(ams.slots[0].assigned_spool_id.availability, Availability.UNKNOWN)
        self.assertEqual(job.job.status, PrintStatus.RUNNING)
        self.assertEqual(job.job.current_layer, 12)
        self.assertEqual(job.job.completed_layers, 11)
        self.assertIsNone(job.job.provider_run_key)
        self.assertIsNone(job.job.exact_started_at)
        self.assertIsNone(job.job.exact_started_at_source)

    async def test_reads_exact_ams_grams_and_ignores_invalid_remain_values(self) -> None:
        trays = self.provider._report["ams"]["ams"][0]["tray"]
        trays[0].update({"remain": -1, "remain_g": 243})
        trays.append({"id": 2, "tray_type": "PLA", "remain": 101, "remain_g": -1})

        status = await self.provider.get_status()
        exact, invalid = status.feed_systems[0].slots[0], status.feed_systems[0].slots[2]

        self.assertEqual(exact.remaining_mass.value, Mass.from_grams(243))
        self.assertIs(exact.remaining_percent.availability, Availability.UNKNOWN)
        self.assertIs(invalid.remaining_mass.availability, Availability.UNKNOWN)
        self.assertIs(invalid.remaining_percent.availability, Availability.UNKNOWN)

    async def test_current_layer_is_part_of_job_event_identity(self) -> None:
        first = await self.provider.get_current_job()
        self.assertEqual(first.job.current_layer, 12)
        self.provider._report["layer_num"] = 13
        second = await self.provider.get_current_job()
        self.assertEqual(second.job.current_layer, 13)
        self.assertEqual(second.job.completed_layers, 12)

        events = self.provider.subscribe_events()
        first_event = await anext(events)
        self.provider._report["layer_num"] = 14
        second_event = await anext(events)
        await events.aclose()
        self.assertNotEqual(first_event.payload_hash, second_event.payload_hash)
        self.assertNotEqual(first_event.event_key, second_event.event_key)

    async def test_reported_ids_are_preserved_as_metadata_not_run_identity(self) -> None:
        self.provider._report.update({
            "task_id": "6456",
            "subtask_id": " ",
            "job_id": 0,
        })
        observation = await self.provider.get_current_job()
        self.assertEqual(observation.job.provider_task_id, "6456")
        self.assertIsNone(observation.job.provider_subtask_id)
        self.assertEqual(observation.job.provider_job_id, "0")
        self.assertIsNone(observation.job.provider_run_key)

        events = self.provider.subscribe_events()
        first_event = await anext(events)
        self.provider._report["task_id"] = "6457"
        second_event = await anext(events)
        await events.aclose()
        self.assertNotEqual(first_event.payload_hash, second_event.payload_hash)

    async def test_malformed_reported_id_fails_closed(self) -> None:
        from ufm.application.ports.printers import InvalidObservation

        for value in (True, -1, {}, "x" * 501):
            with self.subTest(value=repr(value)), self.assertRaises(InvalidObservation):
                self.provider._report["task_id"] = value
                await self.provider.get_current_job()

    async def test_vendor_ams_mapping_reports_are_preserved_without_job_join(self) -> None:
        self.provider._report.update({
            "ams_mapping": [0, -1, -1, 3],
            "ams_mapping2": [
                {"ams_id": 0, "slot_id": 0},
                {"ams_id": 255, "slot_id": 255},
                {"ams_id": 255, "slot_id": 255},
                {"ams_id": 0, "slot_id": 3},
            ],
        })
        observation = await self.provider.get_current_job()
        self.assertEqual(observation.job.provider_ams_mapping, (0, -1, -1, 3))
        self.assertEqual(
            observation.job.provider_ams_mapping2,
            ((0, 0), (255, 255), (255, 255), (0, 3)),
        )
        self.assertEqual(observation.job.material_slot_mappings, ())

        events = self.provider.subscribe_events()
        first_event = await anext(events)
        self.provider._report["ams_mapping2"][0]["slot_id"] = 1
        second_event = await anext(events)
        await events.aclose()
        self.assertNotEqual(first_event.payload_hash, second_event.payload_hash)

    async def test_live_mapping_is_decoded_from_flat_provider_report(self) -> None:
        self.provider._report.update({
            "mapping": [0x0003],
        })
        observation = await self.provider.get_current_job()
        self.assertEqual(
            observation.job.material_slot_mappings,
            (ProviderMaterialSlotMapping(0, "reported_slot", "ams:0", "0:3"),),
        )

    async def test_studio_send_mapping_is_not_joined_to_active_job(self) -> None:
        self.provider._report.update({
            "ams_mapping": [0],
            "ams_mapping2": [{"ams_id": 0, "slot_id": 1}],
        })
        observation = await self.provider.get_current_job()
        self.assertEqual(observation.job.material_slot_mappings, ())

    async def test_malformed_vendor_ams_mapping_reports_fail_closed(self) -> None:
        from ufm.application.ports.printers import InvalidObservation

        invalid = (
            ("ams_mapping", [0, True]),
            ("ams_mapping", [0] * 257),
            ("ams_mapping2", [{"ams_id": 0}]),
            ("ams_mapping2", [{"ams_id": 256, "slot_id": 0}]),
        )
        for key, value in invalid:
            with self.subTest(key=key, value=type(value[-1]).__name__), self.assertRaises(InvalidObservation):
                self.provider._report[key] = value
                await self.provider.get_current_job()

    async def test_completed_layer_count_does_not_include_unstarted_layer(self) -> None:
        for raw, completed in ((0, 0), (1, 0), (2, 1), (11, 10)):
            with self.subTest(layer_num=raw):
                self.provider._report["layer_num"] = raw
                job = await self.provider.get_current_job()
                self.assertEqual(job.job.current_layer, raw)
                self.assertEqual(job.job.completed_layers, completed)

    async def test_job_material_mapping_uses_only_explicit_printer_report(self) -> None:
        from ufm.integrations.printers.bambu_lan import material_slot_mappings_from_report

        mapping = material_slot_mappings_from_report({
            "print": {"mapping": [0x0000, 0x0003, 0xFFFF, 0x0100, 0x8000, 0xFF00, 0xFE00]},
        })
        self.assertEqual(
            [(item.logical_material, item.disposition, item.provider_system_key,
              item.provider_slot_key) for item in mapping],
            [
                (0, "reported_slot", "ams:0", "0:0"),
                (1, "reported_slot", "ams:0", "0:3"),
                (2, "unused", None, None),
                (3, "reported_slot", "ams:1", "1:0"),
                (4, "reported_slot", "ams:128", "128:0"),
                (5, "reported_slot", "external", "external"),
                (6, "unsupported", None, None),
            ],
        )
        self.assertEqual(material_slot_mappings_from_report({"print": {}}), ())

    async def test_job_material_mapping_does_not_guess_on_malformed_report(self) -> None:
        from ufm.application.ports.printers import InvalidObservation
        from ufm.integrations.printers.bambu_lan import material_slot_mappings_from_report

        for value in ("0,1", {"0": 0}, [0] * 257):
            with self.subTest(value=type(value).__name__), self.assertRaises(InvalidObservation):
                material_slot_mappings_from_report({"print": {"mapping": value}})
        mapping = material_slot_mappings_from_report({"print": {"mapping": [True, -1, 65536]}})
        self.assertEqual([item.disposition for item in mapping], ["unsupported"] * 3)

    async def test_idle_is_known_but_provides_no_job(self) -> None:
        self.provider._report["gcode_state"] = "IDLE"
        observation = await self.provider.get_current_job()
        self.assertEqual(observation.availability, Availability.KNOWN)
        self.assertIsNone(observation.job)

    async def test_provider_is_read_only_and_does_not_claim_consumption(self) -> None:
        capabilities = await self.provider.get_capabilities()
        self.assertFalse(capabilities.pause.value)
        self.assertFalse(capabilities.cancel.value)
        self.assertFalse(capabilities.filament_usage.value)
        self.assertTrue(capabilities.multi_material.value)
        self.assertTrue(capabilities.local_connection.value)

    async def test_tls_certificate_verification_failure_is_reported_explicitly(self) -> None:
        self.provider._connected.clear()
        with patch("ufm.integrations.printers.bambu_lan.mqtt.Client") as client_factory:
            client = client_factory.return_value
            client.connect.side_effect = ssl.SSLCertVerificationError(
                19, "self-signed certificate in certificate chain",
            )
            with self.assertRaises(TLSVerificationFailed):
                await self.provider.connect()

        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_pinned_client_checks_fingerprint_after_verified_tls_handshake(self) -> None:
        certificate = b"printer certificate"
        fingerprint = hashlib.sha256(certificate).hexdigest()
        client = _PinnedMqttClient(
            certificate_sha256=fingerprint,
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="ufm-test",
            protocol=mqtt.MQTTv311,
        )
        ssl_socket = Mock()
        ssl_socket.getpeercert.return_value = certificate

        with patch.object(mqtt.Client, "_ssl_wrap_socket", return_value=ssl_socket):
            self.assertIs(client._ssl_wrap_socket(Mock()), ssl_socket)
        ssl_socket.close.assert_not_called()

    def test_pinned_client_rejects_a_different_certificate_before_mqtt_connect(self) -> None:
        client = _PinnedMqttClient(
            certificate_sha256=hashlib.sha256(b"expected").hexdigest(),
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="ufm-test",
            protocol=mqtt.MQTTv311,
        )
        ssl_socket = Mock()
        ssl_socket.getpeercert.return_value = b"unexpected"

        with patch.object(mqtt.Client, "_ssl_wrap_socket", return_value=ssl_socket):
            with self.assertRaises(ssl.SSLCertVerificationError):
                client._ssl_wrap_socket(Mock())
        ssl_socket.close.assert_called_once()

    def test_rejects_public_hosts_and_invalid_serials(self) -> None:
        with self.assertRaises(ValueError):
            BambuLanProvider(
                printer_id=self.printer_id,
                provider_instance_id=self.provider_id,
                host="203.0.113.10",
                serial_number="00P00CABCDEF1234",
                access_code=SecretValue("12345678"),
            )
        with self.assertRaises(ValueError):
            BambuLanProvider(
                printer_id=self.printer_id,
                provider_instance_id=self.provider_id,
                host="192.168.1.10",
                serial_number="bad serial",
                access_code=SecretValue("12345678"),
            )

    async def test_configuration_persists_tls_profile_and_only_secret_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            certificate_path = Path(directory) / "trusted-ca.pem"
            certificate_path.write_text("test CA", encoding="ascii")
            with patch(
                "ufm.integrations.printers.configuration.BambuLanProvider",
            ) as provider_factory:
                mocked = provider_factory.return_value
                mocked.connect = AsyncMock()
                mocked.get_status = AsyncMock()
                mocked.disconnect = AsyncMock()
                configured = await configure_bambu_printer(
                    engine=engine,
                    secret_store=secrets,
                    name="P1S",
                    model="P1S",
                    host="192.168.1.20",
                    serial_number="00P00CABCDEF1234",
                    access_code=SecretValue("12345678"),
                    certificate_sha256="a" * 64,
                    ca_certificate=certificate_path,
                )
            try:
                self.assertEqual(configured.provider_type, "BAMBU_LAN")
                self.assertEqual(secrets.values[configured.credential_ref], "12345678")
                with engine.connect() as connection:
                    saved_printer = connection.execute(
                        select(printer.c.manufacturer, printer.c.model, printer.c.serial_number)
                        .where(printer.c.id == configured.printer_id)
                    ).one()
                    saved_profile = connection.execute(
                        select(
                            connection_profile.c.provider_type,
                            connection_profile.c.host,
                            connection_profile.c.port,
                            connection_profile.c.tls_enabled,
                            connection_profile.c.credential_ref,
                            connection_profile.c.extra_config_json,
                        ).where(connection_profile.c.printer_id == configured.printer_id)
                    ).one()
                self.assertEqual(saved_printer, ("Bambu Lab", "P1S", "00P00CABCDEF1234"))
                self.assertEqual(saved_profile.provider_type, "BAMBU_LAN")
                self.assertEqual(saved_profile.host, "192.168.1.20")
                self.assertEqual(saved_profile.port, 8883)
                self.assertTrue(saved_profile.tls_enabled)
                self.assertEqual(saved_profile.credential_ref, configured.credential_ref)
                self.assertEqual(
                    json.loads(saved_profile.extra_config_json)["serial_number"],
                    "00P00CABCDEF1234",
                )
                self.assertEqual(
                    json.loads(saved_profile.extra_config_json)["certificate_sha256"],
                    "a" * 64,
                )
                self.assertNotIn("12345678", repr(saved_profile))
                mocked.connect.assert_awaited_once()
                mocked.get_status.assert_awaited_once()
                mocked.disconnect.assert_awaited_once()
                with patch(
                    "ufm.integrations.printers.configuration.BambuLanProvider",
                ) as probe_factory:
                    probe = probe_factory.return_value
                    probe.connect = AsyncMock()
                    probe.get_status = AsyncMock()
                    probe.get_current_job = AsyncMock()
                    probe.disconnect = AsyncMock()
                    observed = await probe_configured_printer(
                        engine=engine,
                        secret_store=secrets,
                        printer_id=configured.printer_id,
                    )
                    self.assertIs(observed.status, probe.get_status.return_value)
                    self.assertEqual(
                        probe_factory.call_args.kwargs["access_code"].reveal(),
                        "12345678",
                    )
                    self.assertEqual(
                        probe_factory.call_args.kwargs["certificate_sha256"],
                        "a" * 64,
                    )
                    self.assertEqual(
                        probe_factory.call_args.kwargs["serial_number"],
                        "00P00CABCDEF1234",
                    )
                    probe.connect.assert_awaited_once()
                    probe.get_status.assert_awaited_once()
                    probe.get_current_job.assert_awaited_once()
                    probe.disconnect.assert_awaited_once()
                    probe.connect.side_effect = ProviderUnavailable()
                    with self.assertRaises(ProviderUnavailable):
                        await probe_configured_printer(
                            engine=engine,
                            secret_store=secrets,
                            printer_id=configured.printer_id,
                        )
                    self.assertEqual(probe.disconnect.await_count, 2)
                    self.assertEqual(probe.get_status.await_count, 1)
                    self.assertEqual(probe.get_current_job.await_count, 1)
            finally:
                engine.dispose()

    async def test_two_configured_printers_keep_credentials_events_and_slots_isolated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-two-bambu-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            configured = []
            try:
                with patch(
                    "ufm.integrations.printers.configuration.BambuLanProvider",
                ) as provider_factory:
                    provider_factory.return_value.connect = AsyncMock()
                    provider_factory.return_value.get_status = AsyncMock()
                    provider_factory.return_value.disconnect = AsyncMock()
                    for name, model, host, serial, code in (
                        ("Printer A", "A1", "192.168.1.20", "00P00CABCDEF1234", "code-a-123"),
                        ("Printer B", "B1", "192.168.1.21", "00P00CABCDEF5678", "code-b-456"),
                    ):
                        configured.append(await configure_bambu_printer(
                            engine=engine,
                            secret_store=secrets,
                            name=name,
                            model=model,
                            host=host,
                            serial_number=serial,
                            access_code=SecretValue(code),
                        ))

                providers = [
                    configured_printer_provider(
                        engine=engine, secret_store=secrets, printer_id=item.printer_id,
                    )
                    for item in configured
                ]
                first, second = providers
                self.assertIsInstance(first, BambuLanProvider)
                self.assertIsInstance(second, BambuLanProvider)
                self.assertNotEqual(first.printer_id, second.printer_id)
                self.assertNotEqual(first.provider_instance_id, second.provider_instance_id)
                self.assertEqual(
                    (first.host, first.serial_number, first._access_code.reveal()),
                    ("192.168.1.20", "00P00CABCDEF1234", "code-a-123"),
                )
                self.assertEqual(
                    (second.host, second.serial_number, second._access_code.reveal()),
                    ("192.168.1.21", "00P00CABCDEF5678", "code-b-456"),
                )
                self.assertNotEqual(configured[0].credential_ref, configured[1].credential_ref)
                self.assertEqual(
                    {secrets.values[configured[0].credential_ref],
                     secrets.values[configured[1].credential_ref]},
                    {"code-a-123", "code-b-456"},
                )

                for provider, ams_id, tray_type, tray_uuid, remain in (
                    (first, 0, "PLA", "spool-a", 25),
                    (second, 1, "PETG", "spool-b", 75),
                ):
                    provider._connected.set()
                    provider._report = {
                        "gcode_state": "RUNNING",
                        "mc_percent": 10 if ams_id == 0 else 80,
                        "ams": {
                            "ams": [{
                                "id": ams_id,
                                "tray": [{
                                    "id": 0,
                                    "tray_type": tray_type,
                                    "tray_uuid": tray_uuid,
                                    "remain": remain,
                                }],
                            }],
                        },
                    }

                first_status = await first.get_status()
                second_status = await second.get_status()
                self.assertNotEqual(first_status.source_epoch, second_status.source_epoch)
                self.assertEqual(first_status.feed_systems[0].provider_system_key, "ams:0")
                self.assertEqual(second_status.feed_systems[0].provider_system_key, "ams:1")
                self.assertEqual(first_status.feed_systems[0].slots[0].tray_uuid.value, "spool-a")
                self.assertEqual(second_status.feed_systems[0].slots[0].tray_uuid.value, "spool-b")

                first_stream = first.subscribe_events()
                second_stream = second.subscribe_events()
                first_event, second_event = await anext(first_stream), await anext(second_stream)
                await first_stream.aclose()
                await second_stream.aclose()
                self.assertEqual(first_event.printer_id, first.printer_id)
                self.assertEqual(second_event.printer_id, second.printer_id)
                self.assertEqual(first_event.provider_instance_id, first.provider_instance_id)
                self.assertEqual(second_event.provider_instance_id, second.provider_instance_id)
                self.assertNotEqual(first_event.source_epoch, second_event.source_epoch)
                self.assertEqual(first_event.job.progress_bp, 1000)
                self.assertEqual(second_event.job.progress_bp, 8000)
            finally:
                engine.dispose()

    async def test_bambu_connection_edit_tests_before_switch_and_keeps_old_profile_on_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-edit-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            try:
                with patch(
                    "ufm.integrations.printers.configuration.BambuLanProvider",
                ) as enroll_factory:
                    enroll = enroll_factory.return_value
                    enroll.connect = AsyncMock()
                    enroll.get_status = AsyncMock()
                    enroll.disconnect = AsyncMock()
                    configured = await configure_bambu_printer(
                        engine=engine,
                        secret_store=secrets,
                        name="P1S",
                        model="P1S",
                        host="192.168.1.20",
                        serial_number="00P00CABCDEF1234",
                        access_code=SecretValue("old-code-123"),
                    )
                old_credential_ref = configured.credential_ref

                with patch(
                    "ufm.integrations.printers.configuration.BambuLanProvider",
                ) as update_factory:
                    update = update_factory.return_value
                    update.connect = AsyncMock()
                    update.get_status = AsyncMock()
                    update.disconnect = AsyncMock()
                    saved = await printer_configuration.update_bambu_printer_connection(
                        engine=engine,
                        secret_store=secrets,
                        printer_id=configured.printer_id,
                        host="192.168.1.25",
                        serial_number="00P00CABCDEF9876",
                        access_code=SecretValue("new-code-456"),
                    )
                    self.assertEqual(update_factory.call_args.kwargs["host"], "192.168.1.25")
                    self.assertEqual(
                        update_factory.call_args.kwargs["access_code"].reveal(),
                        "new-code-456",
                    )
                    update.connect.assert_awaited_once()
                    update.get_status.assert_awaited_once()
                    update.disconnect.assert_awaited_once()

                self.assertEqual(saved.printer_id, configured.printer_id)
                self.assertEqual(saved.endpoint, "mqtts://192.168.1.25:8883")
                self.assertNotEqual(saved.credential_ref, old_credential_ref)
                self.assertNotIn(old_credential_ref, secrets.values)
                self.assertEqual(secrets.get(saved.credential_ref).reveal(), "new-code-456")
                with engine.connect() as connection:
                    saved_profile = connection.execute(
                        select(
                            connection_profile.c.host,
                            connection_profile.c.credential_ref,
                            connection_profile.c.extra_config_json,
                        ).where(connection_profile.c.printer_id == configured.printer_id)
                    ).one()
                    saved_serial = connection.execute(
                        select(printer.c.serial_number).where(
                            printer.c.id == configured.printer_id,
                        )
                    ).scalar_one()
                self.assertEqual(saved_profile.host, "192.168.1.25")
                self.assertEqual(saved_profile.credential_ref, saved.credential_ref)
                self.assertEqual(saved_serial, "00P00CABCDEF9876")
                self.assertEqual(
                    json.loads(saved_profile.extra_config_json)["serial_number"],
                    "00P00CABCDEF9876",
                )

                with patch(
                    "ufm.integrations.printers.configuration.BambuLanProvider",
                ) as failed_factory:
                    failed = failed_factory.return_value
                    failed.connect = AsyncMock(side_effect=ProviderUnavailable())
                    failed.get_status = AsyncMock()
                    failed.disconnect = AsyncMock()
                    with self.assertRaises(ProviderUnavailable):
                        await printer_configuration.update_bambu_printer_connection(
                            engine=engine,
                            secret_store=secrets,
                            printer_id=configured.printer_id,
                            host="192.168.1.99",
                            serial_number="00P00CABCDEF9999",
                            access_code=SecretValue("bad-code-789"),
                        )
                    failed.disconnect.assert_awaited_once()
                with engine.connect() as connection:
                    current_profile = connection.execute(
                        select(connection_profile.c.host, connection_profile.c.credential_ref)
                        .where(connection_profile.c.printer_id == configured.printer_id)
                    ).one()
                    current_serial = connection.execute(
                        select(printer.c.serial_number).where(
                            printer.c.id == configured.printer_id,
                        )
                    ).scalar_one()
                self.assertEqual(current_profile.host, "192.168.1.25")
                self.assertEqual(current_profile.credential_ref, saved.credential_ref)
                self.assertEqual(current_serial, "00P00CABCDEF9876")
                self.assertEqual(set(secrets.values.values()), {"new-code-456"})
            finally:
                engine.dispose()

    async def test_bambu_connection_edit_restores_working_secret_after_database_rollback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-edit-rollback-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            with patch(
                "ufm.integrations.printers.configuration.BambuLanProvider",
            ) as provider_factory:
                provider = provider_factory.return_value
                provider.connect = AsyncMock()
                provider.get_status = AsyncMock()
                provider.disconnect = AsyncMock()
                configured = await configure_bambu_printer(
                    engine=engine,
                    secret_store=secrets,
                    name="P1S",
                    model="P1S",
                    host="192.168.1.20",
                    serial_number="00P00CABCDEF1234",
                    access_code=SecretValue("old-code-123"),
                )

            real_transaction = printer_configuration.immediate_transaction

            @contextmanager
            def fail_after_write(target: Engine) -> Iterator[Connection]:
                with real_transaction(target) as connection:
                    yield connection
                    raise SQLAlchemyError("injected database failure")

            calls = 0

            def transaction(target: Engine) -> AbstractContextManager[Connection]:
                nonlocal calls
                calls += 1
                return fail_after_write(target) if calls == 1 else real_transaction(target)

            try:
                with patch(
                    "ufm.integrations.printers.configuration.BambuLanProvider",
                ) as update_factory:
                    update = update_factory.return_value
                    update.connect = AsyncMock()
                    update.get_status = AsyncMock()
                    update.disconnect = AsyncMock()
                    with patch(
                        "ufm.integrations.printers.configuration.immediate_transaction",
                        side_effect=transaction,
                    ):
                        with self.assertRaises(SQLAlchemyError):
                            await printer_configuration.update_bambu_printer_connection(
                                engine=engine,
                                secret_store=secrets,
                                printer_id=configured.printer_id,
                                host="192.168.1.25",
                                serial_number="00P00CABCDEF9876",
                                access_code=SecretValue("new-code-456"),
                            )
                with engine.connect() as connection:
                    profile = connection.execute(
                        select(connection_profile.c.host, connection_profile.c.credential_ref)
                        .where(connection_profile.c.printer_id == configured.printer_id)
                    ).one()
                    serial = connection.execute(
                        select(printer.c.serial_number).where(
                            printer.c.id == configured.printer_id,
                        )
                    ).scalar_one()
                self.assertEqual(profile.host, "192.168.1.20")
                self.assertEqual(serial, "00P00CABCDEF1234")
                self.assertNotEqual(profile.credential_ref, configured.credential_ref)
                self.assertEqual(secrets.get(profile.credential_ref).reveal(), "old-code-123")
                self.assertEqual(set(secrets.values.values()), {"old-code-123"})
            finally:
                engine.dispose()

    async def test_removing_printer_deletes_connection_and_secret_but_preserves_record(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            with patch(
                "ufm.integrations.printers.configuration.BambuLanProvider",
            ) as provider_factory:
                mocked = provider_factory.return_value
                mocked.connect = AsyncMock()
                mocked.get_status = AsyncMock()
                mocked.disconnect = AsyncMock()
                configured = await configure_bambu_printer(
                    engine=engine,
                    secret_store=secrets,
                    name="P1S",
                    model="P1S",
                    host="192.168.1.20",
                    serial_number="00P00CABCDEF1234",
                    access_code=SecretValue("12345678"),
                )

            try:
                name = remove_configured_printer(
                    engine=engine,
                    secret_store=secrets,
                    printer_id=configured.printer_id,
                )
                self.assertEqual(name, "P1S")
                self.assertEqual(secrets.values, {})
                with engine.connect() as connection:
                    saved_printer = connection.execute(
                        select(printer.c.name, printer.c.enabled)
                        .where(printer.c.id == configured.printer_id)
                    ).one()
                    profile_count = connection.execute(
                        select(connection_profile.c.id)
                        .where(connection_profile.c.printer_id == configured.printer_id)
                    ).all()
                self.assertEqual(saved_printer, ("P1S", False))
                self.assertEqual(profile_count, [])
            finally:
                engine.dispose()

    async def test_editing_display_details_preserves_host_secret_and_history_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-edit-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            with patch(
                "ufm.integrations.printers.configuration.BambuLanProvider",
            ) as provider_factory:
                mocked = provider_factory.return_value
                mocked.connect = AsyncMock()
                mocked.get_status = AsyncMock()
                mocked.disconnect = AsyncMock()
                configured = await configure_bambu_printer(
                    engine=engine,
                    secret_store=secrets,
                    name="P1S",
                    model="P1S",
                    host="192.168.1.20",
                    serial_number="00P00CABCDEF1234",
                    access_code=SecretValue("12345678"),
                )

            try:
                name = printer_configuration.update_printer_details(
                    engine=engine,
                    printer_id=configured.printer_id,
                    name="Workshop P1S",
                    model="Bambu Lab P1S",
                )
                with engine.connect() as connection:
                    saved_printer = connection.execute(
                        select(printer.c.name, printer.c.model, printer.c.revision)
                        .where(printer.c.id == configured.printer_id)
                    ).one()
                    saved_profile = connection.execute(
                        select(
                            connection_profile.c.host,
                            connection_profile.c.credential_ref,
                            connection_profile.c.extra_config_json,
                        ).where(connection_profile.c.printer_id == configured.printer_id)
                    ).one()
                self.assertEqual(name, "Workshop P1S")
                self.assertEqual(saved_printer.name, "Workshop P1S")
                self.assertEqual(saved_printer.model, "Bambu Lab P1S")
                self.assertEqual(saved_printer.revision, 2)
                self.assertEqual(saved_profile.host, "192.168.1.20")
                self.assertEqual(saved_profile.credential_ref, configured.credential_ref)
                self.assertEqual(secrets.values[configured.credential_ref], "12345678")
            finally:
                engine.dispose()

    async def test_failed_credential_deletion_leaves_printer_configuration_untouched(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            with patch(
                "ufm.integrations.printers.configuration.BambuLanProvider",
            ) as provider_factory:
                mocked = provider_factory.return_value
                mocked.connect = AsyncMock()
                mocked.get_status = AsyncMock()
                mocked.disconnect = AsyncMock()
                configured = await configure_bambu_printer(
                    engine=engine,
                    secret_store=secrets,
                    name="P1S",
                    model="P1S",
                    host="192.168.1.20",
                    serial_number="00P00CABCDEF1234",
                    access_code=SecretValue("12345678"),
                )

            try:
                failing_secrets = _FailingDeleteSecrets()
                failing_secrets.values = secrets.values
                with self.assertRaises(SecretStoreUnavailable):
                    remove_configured_printer(
                        engine=engine,
                        secret_store=failing_secrets,
                        printer_id=configured.printer_id,
                    )
                with engine.connect() as connection:
                    profile_count = connection.execute(
                        select(connection_profile.c.id)
                        .where(connection_profile.c.printer_id == configured.printer_id)
                    ).all()
                self.assertEqual(len(profile_count), 1)
                self.assertEqual(len(secrets.values), 1)
            finally:
                engine.dispose()

    async def test_database_failure_restores_the_removed_credential_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ufm-bambu-") as directory:
            engine = create_sqlite_engine(Path(directory) / "ufm.sqlite3")
            migrate_database(engine)
            secrets = _MemorySecrets()
            with patch(
                "ufm.integrations.printers.configuration.BambuLanProvider",
            ) as provider_factory:
                mocked = provider_factory.return_value
                mocked.connect = AsyncMock()
                mocked.get_status = AsyncMock()
                mocked.disconnect = AsyncMock()
                configured = await configure_bambu_printer(
                    engine=engine,
                    secret_store=secrets,
                    name="P1S",
                    model="P1S",
                    host="192.168.1.20",
                    serial_number="00P00CABCDEF1234",
                    access_code=SecretValue("12345678"),
                )

            real_transaction = printer_configuration.immediate_transaction

            @contextmanager
            def fail_after_write(target: Engine) -> Iterator[Connection]:
                with real_transaction(target) as connection:
                    yield connection
                    raise SQLAlchemyError("injected database failure")

            calls = 0

            def transaction(target: Engine) -> AbstractContextManager[Connection]:
                nonlocal calls
                calls += 1
                return fail_after_write(target) if calls == 1 else real_transaction(target)

            try:
                with patch(
                    "ufm.integrations.printers.configuration.immediate_transaction",
                    side_effect=transaction,
                ):
                    with self.assertRaises(SQLAlchemyError):
                        remove_configured_printer(
                            engine=engine,
                            secret_store=secrets,
                            printer_id=configured.printer_id,
                        )
                with engine.connect() as connection:
                    saved_profile = connection.execute(
                        select(connection_profile.c.credential_ref)
                        .where(connection_profile.c.printer_id == configured.printer_id)
                    ).scalar_one()
                self.assertNotEqual(saved_profile, configured.credential_ref)
                self.assertEqual(
                    secrets.get(saved_profile).reveal(),
                    "12345678",
                )
            finally:
                engine.dispose()
