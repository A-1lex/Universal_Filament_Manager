"""Transactional commands for physical spool placement."""

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from enum import StrEnum

from ufm.application.dto.providers import FeedSlotSnapshot
from ufm.application.ports.persistence import (
    IdempotencyConflict,
    NotFound,
    RevisionConflict,
    UnitOfWork,
)
from ufm.domain.entities import (
    AuditEvent,
    FeedSlot,
    MaterialFeedSystem,
    MaterialUsageSegment,
    ReconciliationTask,
    SpoolMount,
)
from ufm.domain.enums import (
    AssignmentSource,
    FeedSystemKind,
    MountState,
    ReconciliationState,
    Severity,
    SlotAssignment,
    SpoolLifecycle,
)
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime

UnitOfWorkFactory = Callable[[], UnitOfWork]


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def provider_slot_snapshot_audit_proof(
    *,
    printer_id: EntityId,
    system_id: EntityId,
    provider_system_key: str,
    system_kind: FeedSystemKind,
    slot_id: EntityId,
    snapshot: FeedSlotSnapshot,
    observed_at: UtcDateTime,
    received_at: UtcDateTime,
    source_epoch: str | None,
    source_sequence: int | None,
) -> tuple[str, str]:
    """Recreate the opaque audit identity and payload hash for an observed slot."""

    def identity_hash(value: str | None) -> str | None:
        return None if value is None else hashlib.sha256(value.encode("utf-8")).hexdigest()

    def observation(value: object, availability: object) -> dict[str, object]:
        if isinstance(value, str):
            safe_value: object = identity_hash(value)
        elif isinstance(value, Mass):
            safe_value = value.milligrams
        else:
            safe_value = value
        return {"availability": str(availability), "value": safe_value}

    source_epoch_hash = identity_hash(source_epoch)
    snapshot_payload: dict[str, object] = {
            "slot_key": snapshot.slot_key,
            "occupancy": observation(snapshot.occupancy.value, snapshot.occupancy.availability),
            "tray_uuid": observation(snapshot.tray_uuid.value, snapshot.tray_uuid.availability),
            "tag_uid": observation(snapshot.tag_uid.value, snapshot.tag_uid.availability),
            "assigned_spool_id": observation(
                None
                if snapshot.assigned_spool_id.value is None
                else str(snapshot.assigned_spool_id.value),
                snapshot.assigned_spool_id.availability,
            ),
            "remaining_mass": observation(
                snapshot.remaining_mass.value,
                snapshot.remaining_mass.availability,
            ),
        }
    if (
        snapshot.remaining_percent is not None
        and snapshot.remaining_percent.availability.value == "KNOWN"
    ):
        snapshot_payload["remaining_percent"] = observation(
            snapshot.remaining_percent.value,
            snapshot.remaining_percent.availability,
        )
    snapshot_hash = _hash_json(snapshot_payload)
    event_identity = {
        "system_id": str(system_id),
        "slot_id": str(slot_id),
        "source_epoch_sha256": source_epoch_hash,
        "source_sequence": source_sequence,
        "received_at": received_at.isoformat() if source_sequence is None else None,
    }
    command_key = f"provider-slot-snapshot-{_hash_json(event_identity)}"
    fingerprint = _hash_json(
        {
            **event_identity,
            "printer_id": str(printer_id),
            "provider_system_key": provider_system_key,
            "system_kind": system_kind.value,
            "slot_key": snapshot.slot_key,
            "observed_at": observed_at.isoformat(),
            "received_at": received_at.isoformat(),
            "snapshot_sha256": snapshot_hash,
        }
    )
    return command_key, fingerprint


class ProviderSlotSnapshotDisposition(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"
    UNTRACKED = "UNTRACKED"


class TopologyCommands:
    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    @contextmanager
    def _mount_attempt(
        self,
        mount_id: EntityId,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime,
    ) -> Iterator[UnitOfWork]:
        try:
            with self._unit_of_work() as work:
                yield work
        except ValueError as error:
            codes = {
                "spool_mount.slot_occupied": "spool.mount_rejected.slot_occupied",
                "spool_mount.spool_already_mounted": "spool.mount_rejected.spool_already_mounted",
            }
            event_code = codes.get(str(error))
            if event_code is None:
                raise
            # The failed transaction has exited and rolled back before this new writer.
            # If recording fails, propagate that failure rather than claim audit success.
            with self._unit_of_work() as audit_work:
                self._audit(audit_work, actor_device_id, at, event_code, command_key, mount_id)
                audit_work.commit()
            raise

    def create_external_slot(
        self,
        *,
        system_id: EntityId,
        slot_id: EntityId,
        printer_id: EntityId,
        system_name: str,
        slot_key: str,
        actor_device_id: EntityId,
        command_key: str,
        tool_index: int | None = 0,
        system_kind: FeedSystemKind = FeedSystemKind.EXTERNAL,
        provider_system_key: str | None = "external",
        at: UtcDateTime | None = None,
    ) -> FeedSlot:
        occurred_at = at or UtcDateTime.now()
        request = dict(
            operation="create_external_slot",
            system_id=str(system_id),
            slot_id=str(slot_id),
            printer_id=str(printer_id),
            system_name=system_name,
            slot_key=slot_key,
            actor=str(actor_device_id),
            tool_index=tool_index,
            system_kind=system_kind.value,
            provider_system_key=provider_system_key,
        )
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1
                    or event.event_code != "feed_slot.created"
                    or event.entity_type != "feed_slot"
                    or event.entity_id != slot_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.slots.get(slot_id)
            work.printers.get(printer_id)
            try:
                existing = work.slots.get(slot_id)
            except NotFound:
                existing = None
            if existing is not None:
                raise IdempotencyConflict()
            system = MaterialFeedSystem(
                id=system_id,
                device_id=actor_device_id,
                created_at=occurred_at,
                updated_at=occurred_at,
                revision=1,
                printer_id=printer_id,
                kind=system_kind,
                name=system_name,
                provider_system_key=provider_system_key,
            )
            try:
                existing_system = work.feed_systems.get(system_id)
            except NotFound:
                work.feed_systems.add(system)
            else:
                if (
                    existing_system.printer_id != printer_id
                    or existing_system.kind is not system_kind
                    or existing_system.name != system_name
                    or existing_system.provider_system_key != provider_system_key
                ):
                    raise IdempotencyConflict()
            slot = FeedSlot(
                id=slot_id,
                device_id=actor_device_id,
                created_at=occurred_at,
                updated_at=occurred_at,
                revision=1,
                feed_system_id=system_id,
                slot_key=slot_key,
                tool_index=tool_index,
                assignment_state=SlotAssignment.EMPTY,
            )
            work.slots.add(slot)
            self._audit(
                work,
                actor_device_id,
                occurred_at,
                "feed_slot.created",
                command_key,
                slot_id,
                entity_type="feed_slot",
                fingerprint=fingerprint,
            )
            work.commit()
            return slot

    def observe_provider_slot(
        self,
        *,
        printer_id: EntityId,
        system_id: EntityId,
        provider_system_key: str,
        system_kind: FeedSystemKind,
        slot_id: EntityId,
        snapshot: FeedSlotSnapshot,
        observed_at: UtcDateTime,
        received_at: UtcDateTime,
        source_epoch: str | None,
        source_sequence: int | None,
        actor_device_id: EntityId,
    ) -> ProviderSlotSnapshotDisposition:
        """Persist ordering metadata for an already known slot, never its assignment."""
        command_key, fingerprint = provider_slot_snapshot_audit_proof(
            printer_id=printer_id,
            system_id=system_id,
            provider_system_key=provider_system_key,
            system_kind=system_kind,
            slot_id=slot_id,
            snapshot=snapshot,
            observed_at=observed_at,
            received_at=received_at,
            source_epoch=source_epoch,
            source_sequence=source_sequence,
        )

        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1
                    or event.event_code != "feed_slot.snapshot_observed"
                    or event.entity_type != "feed_slot"
                    or event.entity_id != slot_id
                    or event.actor_device_id != actor_device_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                work.slots.get(slot_id)
                return ProviderSlotSnapshotDisposition.DUPLICATE

            try:
                slot = work.slots.get(slot_id)
            except NotFound:
                return ProviderSlotSnapshotDisposition.UNTRACKED
            system = work.feed_systems.get(slot.feed_system_id)
            if (
                system.id != system_id
                or system.printer_id != printer_id
                or system.provider_system_key != provider_system_key
                or system.kind is not system_kind
                or slot.slot_key != snapshot.slot_key
            ):
                raise ValueError("provider_snapshot.topology_mismatch")

            previous_received = slot.received_at
            if previous_received is not None and received_at <= previous_received:
                return ProviderSlotSnapshotDisposition.STALE
            if (
                slot.source_epoch == source_epoch
                and slot.source_sequence is not None
                and source_sequence is not None
                and source_sequence <= slot.source_sequence
            ):
                return ProviderSlotSnapshotDisposition.STALE
            if slot.source_epoch == source_epoch and (slot.source_sequence is None) != (
                source_sequence is None
            ):
                return ProviderSlotSnapshotDisposition.STALE

            updated = replace(
                slot,
                observed_at=observed_at,
                received_at=received_at,
                source_epoch=source_epoch,
                source_sequence=source_sequence,
                updated_at=received_at,
                revision=slot.revision + 1,
            )
            work.slots.save(updated, slot.revision)
            self._audit(
                work,
                actor_device_id,
                received_at,
                "feed_slot.snapshot_observed",
                command_key,
                slot_id,
                entity_type="feed_slot",
                fingerprint=fingerprint,
            )
            work.commit()
            return ProviderSlotSnapshotDisposition.APPLIED

    def mark_assignment_unknown(
        self,
        *,
        slot_id: EntityId,
        expected_slot_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        material_id: EntityId | None = None,
        at: UtcDateTime | None = None,
    ) -> FeedSlot:
        occurred_at = at or UtcDateTime.now()
        request = dict(
            operation="mark_assignment_unknown",
            slot_id=str(slot_id),
            expected_slot_revision=expected_slot_revision,
            actor=str(actor_device_id),
            material_id=None if material_id is None else str(material_id),
        )
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1
                    or event.event_code != "feed_slot.assignment_unknown"
                    or event.entity_type != "feed_slot"
                    or event.entity_id != slot_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.slots.get(slot_id)
            slot = work.slots.get(slot_id)
            mounted = work.mounts.active_for_slot(slot_id)
            current = self._segment_for_slot(work, slot_id, material_id)
            job_id = None
            if material_id is not None:
                job = work.jobs.for_material(material_id)
                system = work.feed_systems.get(slot.feed_system_id)
                if job.printer_id != system.printer_id:
                    raise ValueError("usage_segment.printer_mismatch")
                job_id = job.id
                if current is not None and current.feed_slot_id != slot_id:
                    raise ValueError("usage_segment.slot_mismatch")
                if slot.tool_index is None:
                    raise ValueError("usage_segment.tool_index_unknown")
                if work.jobs.get_material(material_id).tool_index != slot.tool_index:
                    raise ValueError("usage_segment.tool_mismatch")
            task_key = f"feed_slot:{slot_id}:unknown:{material_id or 'unscoped'}"
            task = work.reconciliations.open_task_by_dedupe(task_key)
            already_unknown = (
                slot.assignment_state is SlotAssignment.ACTIVE_SPOOL_UNKNOWN
                and mounted is None
                and (
                    material_id is None
                    or (
                        current is not None
                        and current.assignment_state is SlotAssignment.ACTIVE_SPOOL_UNKNOWN
                    )
                )
            )
            if slot.revision != expected_slot_revision:
                raise RevisionConflict()
            if mounted is not None:
                work.mounts.close(mounted.id, occurred_at, mounted.revision)
            if material_id is not None and not already_unknown:
                if current is not None:
                    self._close_segment(work, slot_id, material_id, occurred_at)
                assert slot.tool_index is not None
                work.segments.add(
                    MaterialUsageSegment(
                        id=EntityId.new(),
                        device_id=actor_device_id,
                        created_at=occurred_at,
                        updated_at=occurred_at,
                        revision=1,
                        print_job_material_id=material_id,
                        tool_index=slot.tool_index,
                        assignment_state=SlotAssignment.ACTIVE_SPOOL_UNKNOWN,
                        started_at=occurred_at,
                        source=AssignmentSource.MANUAL.value,
                        confidence_bp=0,
                        feed_slot_id=slot_id,
                    )
                )
            if task is None:
                work.reconciliations.add_task(
                    ReconciliationTask(
                        id=EntityId.new(),
                        device_id=actor_device_id,
                        created_at=occurred_at,
                        updated_at=occurred_at,
                        revision=1,
                        reason_code="ACTIVE_SPOOL_UNKNOWN",
                        severity=Severity.ERROR,
                        state=ReconciliationState.OPEN,
                        dedupe_key=task_key,
                        feed_slot_id=slot_id,
                        print_job_id=job_id,
                        suggested_action="resolve_physical_spool_assignment",
                    )
                )
            updated = replace(
                slot,
                assignment_state=SlotAssignment.ACTIVE_SPOOL_UNKNOWN,
                updated_at=occurred_at,
                revision=slot.revision + 1,
            )
            work.slots.save(updated, slot.revision)
            self._audit(
                work,
                actor_device_id,
                occurred_at,
                "feed_slot.assignment_unknown",
                command_key,
                slot_id,
                entity_type="feed_slot",
                fingerprint=fingerprint,
            )
            work.commit()
            return updated

    def mount_spool(
        self,
        *,
        mount_id: EntityId,
        slot_id: EntityId,
        spool_id: EntityId,
        actor_device_id: EntityId,
        command_key: str,
        assignment_source: AssignmentSource = AssignmentSource.MANUAL,
        confidence_bp: int = 10_000,
        material_id: EntityId | None = None,
        segment_id: EntityId | None = None,
        at: UtcDateTime | None = None,
    ) -> SpoolMount:
        occurred_at = at or UtcDateTime.now()
        request = dict(
            operation="mount_spool",
            mount_id=str(mount_id),
            slot_id=str(slot_id),
            spool_id=str(spool_id),
            actor=str(actor_device_id),
            assignment_source=assignment_source.value,
            confidence_bp=confidence_bp,
            material_id=None if material_id is None else str(material_id),
            segment_id=None if segment_id is None else str(segment_id),
        )
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._mount_attempt(mount_id, actor_device_id, command_key, occurred_at) as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1
                    or event.event_code != "spool.mounted"
                    or event.entity_type != "spool_mount"
                    or event.entity_id != mount_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.mounts.get(mount_id)
            slot = work.slots.get(slot_id)
            spool = work.spools.get(spool_id)
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool_mount.archived_spool")
            slot_mount = work.mounts.active_for_slot(slot_id)
            if slot_mount is not None:
                if slot_mount.spool_id == spool_id:
                    raise IdempotencyConflict()
                raise ValueError("spool_mount.slot_occupied")
            if work.mounts.active_for_spool(spool_id) is not None:
                raise ValueError("spool_mount.spool_already_mounted")
            mounted = SpoolMount(
                id=mount_id,
                device_id=actor_device_id,
                created_at=occurred_at,
                updated_at=occurred_at,
                revision=1,
                feed_slot_id=slot_id,
                spool_id=spool_id,
                state=MountState.ACTIVE,
                mounted_at=occurred_at,
                assignment_source=assignment_source,
                confidence_bp=confidence_bp,
            )
            work.mounts.add(mounted)
            work.slots.save(
                replace(
                    slot,
                    assignment_state=SlotAssignment.ASSIGNED,
                    updated_at=occurred_at,
                    revision=slot.revision + 1,
                ),
                slot.revision,
            )
            self._rotate_segment(
                work,
                material_id=material_id,
                new_segment_id=segment_id,
                slot_id=slot_id,
                mount=mounted,
                tool_index=slot.tool_index,
                actor_device_id=actor_device_id,
                at=occurred_at,
                assignment_source=assignment_source,
                confidence_bp=confidence_bp,
            )
            self._audit(
                work,
                actor_device_id,
                occurred_at,
                "spool.mounted",
                command_key,
                mounted.id,
                fingerprint=fingerprint,
            )
            work.commit()
            return mounted

    def unmount_slot(
        self,
        *,
        slot_id: EntityId,
        expected_mount_id: EntityId,
        actor_device_id: EntityId,
        command_key: str,
        material_id: EntityId | None = None,
        at: UtcDateTime | None = None,
    ) -> SpoolMount:
        occurred_at = at or UtcDateTime.now()
        request = dict(
            operation="unmount_slot",
            slot_id=str(slot_id),
            expected_mount_id=str(expected_mount_id),
            actor=str(actor_device_id),
            material_id=None if material_id is None else str(material_id),
        )
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1
                    or event.event_code != "spool.unmounted"
                    or event.entity_type != "spool_mount"
                    or event.entity_id != expected_mount_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.mounts.get(expected_mount_id)
            slot = work.slots.get(slot_id)
            expected = work.mounts.get(expected_mount_id)
            if expected.feed_slot_id != slot_id:
                raise RevisionConflict()
            if expected.state is MountState.CLOSED:
                raise IdempotencyConflict()
            mounted = work.mounts.active_for_slot(slot_id)
            if mounted is None or mounted.id != expected_mount_id:
                raise RevisionConflict()
            work.mounts.close(mounted.id, occurred_at, mounted.revision)
            work.slots.save(
                replace(
                    slot,
                    assignment_state=SlotAssignment.EMPTY,
                    updated_at=occurred_at,
                    revision=slot.revision + 1,
                ),
                slot.revision,
            )
            self._close_segment(work, slot_id, material_id, occurred_at)
            closed = replace(
                mounted,
                state=MountState.CLOSED,
                unmounted_at=occurred_at,
                updated_at=occurred_at,
                revision=mounted.revision + 1,
            )
            self._audit(
                work,
                actor_device_id,
                occurred_at,
                "spool.unmounted",
                command_key,
                mounted.id,
                fingerprint=fingerprint,
            )
            work.commit()
            return closed

    def swap_spool(
        self,
        *,
        expected_mount_id: EntityId,
        new_mount_id: EntityId,
        slot_id: EntityId,
        new_spool_id: EntityId,
        actor_device_id: EntityId,
        command_key: str,
        assignment_source: AssignmentSource = AssignmentSource.MANUAL,
        confidence_bp: int = 10_000,
        material_id: EntityId | None = None,
        new_segment_id: EntityId | None = None,
        at: UtcDateTime | None = None,
    ) -> SpoolMount:
        occurred_at = at or UtcDateTime.now()
        request = dict(
            operation="swap_spool",
            expected_mount_id=str(expected_mount_id),
            new_mount_id=str(new_mount_id),
            slot_id=str(slot_id),
            new_spool_id=str(new_spool_id),
            actor=str(actor_device_id),
            assignment_source=assignment_source.value,
            confidence_bp=confidence_bp,
            material_id=None if material_id is None else str(material_id),
            new_segment_id=None if new_segment_id is None else str(new_segment_id),
        )
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._mount_attempt(new_mount_id, actor_device_id, command_key, occurred_at) as work:
            events = work.audit.for_command(command_key)
            if events:
                event = events[0]
                if (
                    len(events) != 1
                    or event.event_code != "spool.swapped"
                    or event.entity_type != "spool_mount"
                    or event.entity_id != new_mount_id
                    or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
                ):
                    raise IdempotencyConflict()
                return work.mounts.get(new_mount_id)
            slot = work.slots.get(slot_id)
            current = work.mounts.active_for_slot(slot_id)
            if current is None:
                raise ValueError("spool_mount.slot_empty")
            if current.spool_id == new_spool_id:
                raise IdempotencyConflict()
            if current.id != expected_mount_id:
                raise RevisionConflict()
            spool = work.spools.get(new_spool_id)
            if spool.lifecycle is SpoolLifecycle.ARCHIVED:
                raise ValueError("spool_mount.archived_spool")
            if work.mounts.active_for_spool(new_spool_id) is not None:
                raise ValueError("spool_mount.spool_already_mounted")
            work.mounts.close(current.id, occurred_at, current.revision)
            mounted = SpoolMount(
                id=new_mount_id,
                device_id=actor_device_id,
                created_at=occurred_at,
                updated_at=occurred_at,
                revision=1,
                feed_slot_id=slot_id,
                spool_id=new_spool_id,
                state=MountState.ACTIVE,
                mounted_at=occurred_at,
                assignment_source=assignment_source,
                confidence_bp=confidence_bp,
            )
            work.mounts.add(mounted)
            work.slots.save(
                replace(
                    slot,
                    assignment_state=SlotAssignment.ASSIGNED,
                    updated_at=occurred_at,
                    revision=slot.revision + 1,
                ),
                slot.revision,
            )
            self._rotate_segment(
                work,
                material_id=material_id,
                new_segment_id=new_segment_id,
                slot_id=slot_id,
                mount=mounted,
                tool_index=slot.tool_index,
                actor_device_id=actor_device_id,
                at=occurred_at,
                assignment_source=assignment_source,
                confidence_bp=confidence_bp,
            )
            self._audit(
                work,
                actor_device_id,
                occurred_at,
                "spool.swapped",
                command_key,
                mounted.id,
                fingerprint=fingerprint,
            )
            work.commit()
            return mounted

    @staticmethod
    def _segment_for_slot(
        work: UnitOfWork,
        slot_id: EntityId,
        material_id: EntityId | None,
    ) -> MaterialUsageSegment | None:
        active = work.segments.active_for_slot(slot_id)
        if any(segment.print_job_material_id != material_id for segment in active):
            raise ValueError("usage_segment.material_required")
        current = None if material_id is None else work.segments.active_for_material(material_id)
        if current is not None and current.feed_slot_id != slot_id:
            raise ValueError("usage_segment.slot_mismatch")
        return current

    @staticmethod
    def _close_segment(
        work: UnitOfWork, slot_id: EntityId, material_id: EntityId | None, at: UtcDateTime
    ) -> None:
        current = TopologyCommands._segment_for_slot(work, slot_id, material_id)
        if material_id is None:
            return
        if current is None:
            raise ValueError("usage_segment.active_missing")
        work.segments.save(
            replace(
                current,
                ended_at=at,
                updated_at=at,
                revision=current.revision + 1,
            ),
            current.revision,
        )

    @staticmethod
    def _rotate_segment(
        work: UnitOfWork,
        *,
        material_id: EntityId | None,
        new_segment_id: EntityId | None,
        slot_id: EntityId,
        mount: SpoolMount,
        tool_index: int | None,
        actor_device_id: EntityId,
        at: UtcDateTime,
        assignment_source: AssignmentSource,
        confidence_bp: int,
    ) -> None:
        if (material_id is None) != (new_segment_id is None):
            raise ValueError("usage_segment.arguments_incomplete")
        current = TopologyCommands._segment_for_slot(work, slot_id, material_id)
        if material_id is None or new_segment_id is None:
            return
        if tool_index is None:
            raise ValueError("usage_segment.tool_index_unknown")
        if current is not None:
            work.segments.save(
                replace(
                    current,
                    ended_at=at,
                    updated_at=at,
                    revision=current.revision + 1,
                ),
                current.revision,
            )
        work.segments.add(
            MaterialUsageSegment(
                id=new_segment_id,
                device_id=actor_device_id,
                created_at=at,
                updated_at=at,
                revision=1,
                print_job_material_id=material_id,
                tool_index=tool_index,
                assignment_state=SlotAssignment.ASSIGNED,
                started_at=at,
                source=assignment_source.value,
                confidence_bp=confidence_bp,
                feed_slot_id=slot_id,
                spool_mount_id=mount.id,
                spool_id=mount.spool_id,
            )
        )

    @staticmethod
    def _audit(
        work: UnitOfWork,
        actor_device_id: EntityId,
        at: UtcDateTime,
        event_code: str,
        command_key: str,
        mount_id: EntityId,
        *,
        entity_type: str = "spool_mount",
        fingerprint: str | None = None,
    ) -> None:
        work.audit.append(
            AuditEvent(
                id=EntityId.new(),
                device_id=actor_device_id,
                created_at=at,
                event_code=event_code,
                actor_device_id=actor_device_id,
                correlation_id=command_key,
                entity_type=entity_type,
                entity_id=mount_id,
                parameters_json=(
                    "{}"
                    if fingerprint is None
                    else json.dumps({"request_hash_v1": fingerprint}, sort_keys=True)
                ),
            )
        )
