"""Explicitly verify external spool IDs before they can drive slot matching."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

from ufm.application.ports.persistence import IdempotencyConflict, UnitOfWork
from ufm.domain.entities import AuditEvent, SpoolIdentifier
from ufm.domain.enums import SpoolLifecycle
from ufm.domain.value_objects import EntityId, UtcDateTime

EVENT = "spool.identifier_verified"
REBOUND = "spool.identifier_rebound"


def _valid_identity(namespace: str, kind: str, value: str) -> None:
    for item, maximum, code in (
        (namespace, 200, "spool_identifier.namespace_invalid"),
        (kind, 200, "spool_identifier.kind_invalid"),
        (value, 500, "spool_identifier.value_invalid"),
    ):
        if (type(item) is not str or not item or item != item.strip()
                or len(item) > maximum or not item.isprintable()):
            raise ValueError(code)


def _hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


class SpoolIdentifierCommands:
    """Create a trusted exact identifier only after an explicit user confirmation."""

    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def verify(
        self,
        *,
        spool_id: EntityId,
        namespace: str,
        kind: str,
        value: str,
        actor_device_id: EntityId,
        command_key: str,
        manual_confirmation: bool,
        at: UtcDateTime | None = None,
    ) -> SpoolIdentifier:
        _valid_identity(namespace, kind, value)
        if (type(command_key) is not str or not command_key.strip()
                or command_key != command_key.strip() or len(command_key) > 500
                or type(manual_confirmation) is not bool or not manual_confirmation):
            raise ValueError("spool_identifier.confirmation_required")
        now = at or UtcDateTime.now()
        request_hash = _hash({
            "operation": EVENT,
            "spool_id": str(spool_id),
            "namespace": namespace,
            "kind": kind,
            "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "actor": str(actor_device_id),
            "manual_confirmation": manual_confirmation,
        })
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1 or event.event_code != EVENT
                    or event.entity_type != "spool_identifier"
                    or event.actor_device_id != actor_device_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": request_hash}
                ):
                    raise IdempotencyConflict()
                existing = work.spool_identifiers.get(event.entity_id)
                if (
                    existing.spool_id != spool_id or existing.namespace != namespace
                    or existing.kind != kind or existing.value != value
                    or not existing.is_trusted_current or existing.deleted_at is not None
                ):
                    raise IdempotencyConflict()
                return existing

            spool = work.spools.get(spool_id)
            if spool.deleted_at is not None or spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool_identifier.spool_unavailable")
            current = work.spool_identifiers.by_trusted_identity(namespace, kind, value)
            if current is not None and current.spool_id != spool_id:
                raise ValueError("spool_identifier.identity_conflict")
            identifier = current or SpoolIdentifier(
                id=EntityId.new(), device_id=actor_device_id, created_at=now,
                updated_at=now, revision=1, deleted_at=None, spool_id=spool_id,
                namespace=namespace, kind=kind, value=value, verified_at=now,
            )
            if current is None:
                work.spool_identifiers.add(identifier)
            audit = AuditEvent(
                id=EntityId.new(), device_id=actor_device_id, created_at=now,
                event_code=EVENT, actor_device_id=actor_device_id,
                correlation_id=command_key, entity_type="spool_identifier",
                entity_id=identifier.id,
                parameters_json=json.dumps({"request_hash_v1": request_hash}, sort_keys=True),
            )
            work.audit.append(audit)
            work.commit()
            return identifier

    def rebind(
        self,
        *,
        spool_id: EntityId,
        namespace: str,
        kind: str,
        value: str,
        actor_device_id: EntityId,
        command_key: str,
        manual_confirmation: bool,
        at: UtcDateTime | None = None,
    ) -> SpoolIdentifier:
        """Move a trusted identifier to another spool after explicit confirmation.

        The previous binding is retired (never deleted) and a new verified
        identifier is created, so the primary history stays auditable.
        """
        _valid_identity(namespace, kind, value)
        if (type(command_key) is not str or not command_key.strip()
                or command_key != command_key.strip() or len(command_key) > 500
                or type(manual_confirmation) is not bool or not manual_confirmation):
            raise ValueError("spool_identifier.confirmation_required")
        now = at or UtcDateTime.now()
        request_hash = _hash({
            "operation": REBOUND,
            "spool_id": str(spool_id),
            "namespace": namespace,
            "kind": kind,
            "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "actor": str(actor_device_id),
            "manual_confirmation": manual_confirmation,
        })
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1 or event.event_code != REBOUND
                    or event.entity_type != "spool_identifier"
                    or event.actor_device_id != actor_device_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": request_hash}
                ):
                    raise IdempotencyConflict()
                rebound = work.spool_identifiers.get(event.entity_id)
                if (
                    rebound.spool_id != spool_id or rebound.namespace != namespace
                    or rebound.kind != kind or rebound.value != value
                    or not rebound.is_trusted_current or rebound.deleted_at is not None
                ):
                    raise IdempotencyConflict()
                return rebound

            current = work.spool_identifiers.by_trusted_identity(namespace, kind, value)
            if current is None or current.spool_id == spool_id:
                raise ValueError("spool_identifier.rebind_not_needed")
            spool = work.spools.get(spool_id)
            if spool.deleted_at is not None or spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool_identifier.spool_unavailable")
            retired = replace(
                current, retired_at=now, updated_at=now,
                revision=current.revision + 1,
            )
            work.spool_identifiers.save(retired, current.revision)
            identifier = SpoolIdentifier(
                id=EntityId.new(), device_id=actor_device_id, created_at=now,
                updated_at=now, revision=1, deleted_at=None, spool_id=spool_id,
                namespace=namespace, kind=kind, value=value, verified_at=now,
            )
            work.spool_identifiers.add(identifier)
            work.audit.append(AuditEvent(
                id=EntityId.new(), device_id=actor_device_id, created_at=now,
                event_code=REBOUND, actor_device_id=actor_device_id,
                correlation_id=command_key, entity_type="spool_identifier",
                entity_id=identifier.id,
                parameters_json=json.dumps({"request_hash_v1": request_hash}, sort_keys=True),
            ))
            work.commit()
            return identifier
