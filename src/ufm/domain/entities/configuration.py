"""Local identity, connection references, identifiers, and feature flags."""

from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord
from ufm.domain.enums import ConnectionMode
from ufm.domain.value_objects import EntityId, UtcDateTime


def _text(value: str, code: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 500:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceIdentity:
    id: EntityId
    name: str
    public_id: str
    created_at: UtcDateTime
    last_seen_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        _text(self.name, "device.name_invalid")
        _text(self.public_id, "device.public_id_invalid")
        if self.last_seen_at is not None and self.last_seen_at < self.created_at:
            raise ValueError("device.last_seen_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionProfile(EntityRecord):
    printer_id: EntityId
    provider_type: str
    connection_mode: ConnectionMode
    tls_enabled: bool
    host: str | None = None
    port: int | None = None
    credential_ref: str | None = None
    cloud_account_ref: str | None = None

    def __post_init__(self) -> None:
        super(ConnectionProfile, self).__post_init__()
        _text(self.provider_type, "connection.provider_invalid")
        if type(self.tls_enabled) is not bool:
            raise TypeError("connection.tls_invalid")
        if self.port is not None and (type(self.port) is not int or not 1 <= self.port <= 65_535):
            raise ValueError("connection.port_invalid")
        if self.credential_ref is not None and not self.credential_ref.startswith("ufm:credential:"):
            raise ValueError("connection.credential_ref_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpoolIdentifier(EntityRecord):
    spool_id: EntityId
    namespace: str
    kind: str
    value: str
    verified_at: UtcDateTime | None = None
    retired_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        super(SpoolIdentifier, self).__post_init__()
        for value in (self.namespace, self.kind, self.value):
            _text(value, "spool_identifier.field_invalid")
        if self.retired_at is not None and self.verified_at is not None and self.retired_at < self.verified_at:
            raise ValueError("spool_identifier.retired_at_invalid")

    @property
    def is_trusted_current(self) -> bool:
        return self.verified_at is not None and self.retired_at is None


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureFlag(EntityRecord):
    key: str
    enabled: bool
    scope_type: str
    scope_id: EntityId | None = None
    rollout_bp: int | None = None

    def __post_init__(self) -> None:
        super(FeatureFlag, self).__post_init__()
        _text(self.key, "feature_flag.key_invalid")
        _text(self.scope_type, "feature_flag.scope_invalid")
        if type(self.enabled) is not bool:
            raise TypeError("feature_flag.enabled_invalid")
        if self.rollout_bp is not None and (
            type(self.rollout_bp) is not int or not 0 <= self.rollout_bp <= 10_000
        ):
            raise ValueError("feature_flag.rollout_invalid")
