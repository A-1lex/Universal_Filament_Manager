import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import insert

from ufm.application.ports.persistence import IdempotencyConflict
from ufm.application.spool_identifiers import SpoolIdentifierCommands
from ufm.domain.entities import Spool
from ufm.domain.value_objects import EntityId, ExactDecimal, UtcDateTime
from ufm.infrastructure.persistence.models.schema import device_identity, filament_profile
from ufm.infrastructure.persistence.sqlite import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork


class SpoolIdentifierCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ufm-identifier-command-")
        self.addCleanup(self.directory.cleanup)
        self.engine = create_sqlite_engine(Path(self.directory.name) / "test.sqlite3")
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.device, self.profile, self.spool = EntityId.new(), EntityId.new(), EntityId.new()
        self.now = UtcDateTime.now()
        with self.engine.begin() as connection:
            connection.execute(insert(device_identity).values(
                id=self.device, name="test", public_id=str(self.device), created_at=self.now,
            ))
            connection.execute(insert(filament_profile).values(
                id=self.profile, device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, name="PLA", material_type="PLA",
                diameter_mm=ExactDecimal.parse("1.75"),
            ))
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(Spool(
                id=self.spool, device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, display_name="PLA",
                filament_profile_id=self.profile,
            ))
            work.commit()
        self.commands = SpoolIdentifierCommands(lambda: SQLiteUnitOfWork(self.engine))

    def verify(self, *, spool_id: EntityId | None = None, value: str = "tray-private-id",
               command_key: str = "verify-tray", manual_confirmation: bool = True):
        return self.commands.verify(
            spool_id=self.spool if spool_id is None else spool_id,
            namespace="bambu", kind="tray_uuid", value=value,
            actor_device_id=self.device, command_key=command_key,
            manual_confirmation=manual_confirmation, at=self.now,
        )

    def test_explicit_confirmation_audits_without_persisting_raw_identifier(self) -> None:
        with self.assertRaisesRegex(ValueError, "spool_identifier.confirmation_required"):
            self.verify(manual_confirmation=False)

        created = self.verify()
        replay = self.verify()
        self.assertEqual(replay, created)
        with SQLiteUnitOfWork(self.engine) as work:
            found = work.spool_identifiers.by_trusted_identity(
                "bambu", "tray_uuid", "tray-private-id",
            )
            self.assertEqual(found, created)
            self.assertEqual(len(work.audit.for_command("verify-tray")), 1)
            self.assertEqual(work.ledger.for_spool(self.spool), [])
            self.assertIsNone(work.mounts.active_for_spool(self.spool))
            params = json.loads(work.audit.for_command("verify-tray")[0].parameters_json)
            self.assertNotIn("tray-private-id", json.dumps(params))
            self.assertIn("request_hash_v1", params)

    def test_reused_command_key_with_different_payload_is_rejected(self) -> None:
        self.verify()
        with self.assertRaises(IdempotencyConflict):
            self.verify(value="different-tray-id")

    def test_identifier_text_and_command_key_reject_control_characters_or_padding(self) -> None:
        for changes in (
            {"value": "tray\nvalue"},
            {"value": " tray-value "},
            {"command_key": " verify-tray "},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.verify(**changes)

    def test_confirmed_identifier_cannot_be_reassigned_to_another_spool(self) -> None:
        self.verify()
        other_spool = EntityId.new()
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(Spool(
                id=other_spool, device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, display_name="Second PLA",
                filament_profile_id=self.profile,
            ))
            work.commit()
        with self.assertRaisesRegex(ValueError, "spool_identifier.identity_conflict"):
            self.verify(spool_id=other_spool, command_key="verify-other-spool")

    def _second_spool(self) -> EntityId:
        other_spool = EntityId.new()
        with SQLiteUnitOfWork(self.engine) as work:
            work.spools.add(Spool(
                id=other_spool, device_id=self.device, created_at=self.now,
                updated_at=self.now, revision=1, display_name="Second PLA",
                filament_profile_id=self.profile,
            ))
            work.commit()
        return other_spool

    def test_rebind_retires_old_binding_and_verifies_new_one(self) -> None:
        first = self.verify()
        other_spool = self._second_spool()

        rebound = self.commands.rebind(
            spool_id=other_spool, namespace="bambu", kind="tray_uuid",
            value="tray-private-id", actor_device_id=self.device,
            command_key="rebind-tray", manual_confirmation=True, at=self.now,
        )
        replay = self.commands.rebind(
            spool_id=other_spool, namespace="bambu", kind="tray_uuid",
            value="tray-private-id", actor_device_id=self.device,
            command_key="rebind-tray", manual_confirmation=True, at=self.now,
        )

        self.assertEqual(replay, rebound)
        self.assertNotEqual(rebound.id, first.id)
        self.assertEqual(rebound.spool_id, other_spool)
        with SQLiteUnitOfWork(self.engine) as work:
            trusted = work.spool_identifiers.by_trusted_identity(
                "bambu", "tray_uuid", "tray-private-id",
            )
            self.assertEqual(trusted, rebound)
            retired = work.spool_identifiers.get(first.id)
            self.assertIsNotNone(retired.retired_at)
            self.assertFalse(retired.is_trusted_current)
            events = work.audit.for_command("rebind-tray")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_code, "spool.identifier_rebound")
            params = json.loads(events[0].parameters_json)
            self.assertNotIn("tray-private-id", json.dumps(params))

    def test_rebind_requires_existing_conflicting_binding(self) -> None:
        other_spool = self._second_spool()
        with self.assertRaisesRegex(ValueError, "spool_identifier.rebind_not_needed"):
            self.commands.rebind(
                spool_id=other_spool, namespace="bambu", kind="tray_uuid",
                value="tray-private-id", actor_device_id=self.device,
                command_key="rebind-missing", manual_confirmation=True, at=self.now,
            )

        self.verify()
        with self.assertRaisesRegex(ValueError, "spool_identifier.rebind_not_needed"):
            self.commands.rebind(
                spool_id=self.spool, namespace="bambu", kind="tray_uuid",
                value="tray-private-id", actor_device_id=self.device,
                command_key="rebind-same", manual_confirmation=True, at=self.now,
            )

