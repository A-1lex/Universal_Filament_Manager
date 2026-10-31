"""Audited use cases for storage locations and spool placement."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

from ufm.application.ports.persistence import (
    IdempotencyConflict,
    NotFound,
    RevisionConflict,
    UnitOfWork,
)
from ufm.domain.entities import AuditEvent, StorageLocation
from ufm.domain.entities.inventory import Spool
from ufm.domain.enums import SpoolLifecycle, StorageType
from ufm.domain.value_objects import EntityId, UtcDateTime

UnitOfWorkFactory = Callable[[], UnitOfWork]


class StorageCommands:
    """Create storage locations and move spools without touching their stock ledger."""

    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def create_location(
        self,
        *,
        location_id: EntityId,
        name: str,
        storage_type: StorageType,
        parent_id: EntityId | None,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> StorageLocation:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="create_location", location_id=str(location_id), name=name,
            storage_type=storage_type.value, parent_id=None if parent_id is None else str(parent_id),
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay(
                work, command_key, "storage.location_created", "storage_location",
                location_id, fingerprint,
            )
            if replay:
                return work.storage_locations.get(location_id)
            if parent_id is not None:
                parent = work.storage_locations.get(parent_id)
                if parent.deleted_at is not None:
                    raise NotFound()
            location = StorageLocation(
                id=location_id, device_id=actor_device_id, created_at=occurred_at,
                updated_at=occurred_at, revision=1, name=name.strip(),
                storage_type=storage_type, parent_id=parent_id,
            )
            work.storage_locations.add(location)
            self._audit(work, actor_device_id, occurred_at, "storage.location_created",
                        command_key, "storage_location", location_id, fingerprint)
            work.commit()
            return location

    def assign_spool(
        self,
        *,
        spool_id: EntityId,
        expected_revision: int,
        location_id: EntityId | None,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Spool:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="assign_spool", spool_id=str(spool_id),
            expected_revision=expected_revision,
            location_id=None if location_id is None else str(location_id),
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay(
                work, command_key, "storage.spool_location_changed", "spool",
                spool_id, fingerprint,
            )
            if replay:
                return work.spools.get(spool_id)
            spool = work.spools.get(spool_id)
            if spool.revision != expected_revision:
                raise RevisionConflict()
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool.archived_read_only")
            if location_id is not None:
                location = work.storage_locations.get(location_id)
                if location.deleted_at is not None:
                    raise NotFound()
            if spool.storage_location_id == location_id:
                return spool
            updated = replace(
                spool, storage_location_id=location_id,
                updated_at=occurred_at, revision=spool.revision + 1,
            )
            work.spools.save(updated, expected_revision)
            self._audit(work, actor_device_id, occurred_at, "storage.spool_location_changed",
                        command_key, "spool", spool_id, fingerprint)
            work.commit()
            return updated

    @staticmethod
    def _fingerprint(**values: object) -> str:
        payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("ascii")).hexdigest()

    @staticmethod
    def _replay(
        work: UnitOfWork, command_key: str, event_code: str, entity_type: str,
        entity_id: EntityId, fingerprint: str,
    ) -> bool:
        events = work.audit.for_command(command_key)
        if not events:
            return False
        if (
            len(events) != 1 or events[0].event_code != event_code
            or events[0].entity_type != entity_type or events[0].entity_id != entity_id
            or json.loads(events[0].parameters_json) != {"request_hash_v1": fingerprint}
        ):
            raise IdempotencyConflict()
        return True

    @staticmethod
    def _audit(
        work: UnitOfWork, actor: EntityId, at: UtcDateTime, event_code: str,
        command_key: str, entity_type: str, entity_id: EntityId, fingerprint: str,
    ) -> None:
        work.audit.append(AuditEvent(
            id=EntityId.new(), device_id=actor, created_at=at, actor_device_id=actor,
            event_code=event_code, correlation_id=command_key, entity_type=entity_type,
            entity_id=entity_id,
            parameters_json=json.dumps({"request_hash_v1": fingerprint}, sort_keys=True),
        ))
