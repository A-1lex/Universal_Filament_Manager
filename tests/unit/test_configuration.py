import unittest
from datetime import UTC, datetime

from ufm.domain.entities import ConnectionProfile, FeatureFlag, SpoolIdentifier
from ufm.domain.enums import ConnectionMode
from ufm.domain.policies import validate_identifier_bindings
from ufm.domain.value_objects import EntityId, UtcDateTime


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC))


def mutable() -> dict[str, object]:
    return {
        "id": EntityId.new(), "device_id": EntityId.new(), "created_at": now(),
        "updated_at": now(), "revision": 1,
    }


def identifier(spool: EntityId, *, kind: str, verified: bool = True) -> SpoolIdentifier:
    return SpoolIdentifier(
        **mutable(), spool_id=spool, namespace="bambu", kind=kind, value="identifier",
        verified_at=now() if verified else None,
    )


class ConfigurationTests(unittest.TestCase):
    def test_connection_stores_only_credential_reference(self) -> None:
        profile = ConnectionProfile(
            **mutable(), printer_id=EntityId.new(), provider_type="bambu",
            connection_mode=ConnectionMode.LOCAL, tls_enabled=True,
            credential_ref="ufm:credential:12345678-1234-1234-1234-123456789abc",
        )
        self.assertFalse(hasattr(profile, "password"))
        self.assertFalse(hasattr(profile, "access_code"))
        with self.assertRaises(ValueError):
            ConnectionProfile(
                **mutable(), printer_id=EntityId.new(), provider_type="bambu",
                connection_mode=ConnectionMode.LOCAL, tls_enabled=True,
                credential_ref="plaintext-secret",
            )

    def test_port_and_feature_rollout_bounds_are_strict(self) -> None:
        with self.assertRaises(ValueError):
            ConnectionProfile(
                **mutable(), printer_id=EntityId.new(), provider_type="generic",
                connection_mode=ConnectionMode.LOCAL, tls_enabled=False, port=65_536,
            )
        with self.assertRaises(ValueError):
            FeatureFlag(
                **mutable(), key="experimental", enabled=True, scope_type="global",
                rollout_bp=10_001,
            )

    def test_tray_uuid_and_tag_uid_are_independent_identifier_kinds(self) -> None:
        spool = EntityId.new()
        tray = identifier(spool, kind="tray_uuid")
        tag = identifier(spool, kind="tag_uid")
        validate_identifier_bindings([tray, tag])
        self.assertNotEqual(tray.kind, tag.kind)

    def test_trusted_identifier_cannot_bind_two_spools(self) -> None:
        with self.assertRaises(ValueError):
            validate_identifier_bindings([
                identifier(EntityId.new(), kind="tray_uuid"),
                identifier(EntityId.new(), kind="tray_uuid"),
            ])
        validate_identifier_bindings([
            identifier(EntityId.new(), kind="tray_uuid", verified=False),
            identifier(EntityId.new(), kind="tray_uuid", verified=False),
        ])
