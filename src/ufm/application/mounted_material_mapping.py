"""Read-only join from a verified job mapping to its durable mounted spool."""

import json
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from ufm.application.dto.providers import FeedSystemSnapshot
from ufm.application.job_material_mapping import (
    JobMaterialMappingState,
    JobMaterialSlotResolution,
)
from ufm.application.ports.persistence import UnitOfWork
from ufm.application.slot_spool_identity import (
    SlotSpoolMatchState,
    resolve_feed_slot_spool,
)
from ufm.application.topology import provider_slot_snapshot_audit_proof
from ufm.domain.entities import SpoolMount
from ufm.domain.enums import SlotAssignment, SpoolLifecycle
from ufm.domain.value_objects import EntityId, UtcDateTime


class MountedMaterialState(StrEnum):
    MATCHED = "MATCHED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    UNMOUNTED = "UNMOUNTED"


@dataclass(frozen=True, slots=True)
class MountedMaterialResolution:
    logical_material: int
    state: MountedMaterialState
    feed_slot_id: EntityId | None = None
    mount_id: EntityId | None = None
    spool_id: EntityId | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if type(self.logical_material) is not int or not 0 <= self.logical_material <= 255:
            raise ValueError("mounted_material.logical_material_invalid")
        values = (self.feed_slot_id, self.mount_id, self.spool_id)
        if self.state is MountedMaterialState.MATCHED and any(item is None for item in values):
            raise ValueError("mounted_material.match_shape_invalid")
        if self.state is not MountedMaterialState.MATCHED and any(
            item is not None for item in values
        ):
            raise ValueError("mounted_material.nonmatch_has_identity")


def resolve_mounted_material(
    work: UnitOfWork,
    *,
    resolution: JobMaterialSlotResolution,
    feed_system: FeedSystemSnapshot,
    printer_id: EntityId,
    identifier_namespace: str,
    now: UtcDateTime,
    max_age: timedelta = timedelta(seconds=120),
) -> MountedMaterialResolution:
    """Require the same durable slot observation, exact RFID identity and active mount.

    The caller supplies the live read-only UnitOfWork; this function performs no
    writes and returns no spool identity unless every exact link agrees.
    """
    logical = resolution.logical_material

    def result(state: MountedMaterialState, reason: str) -> MountedMaterialResolution:
        return MountedMaterialResolution(logical, state, reason_code=reason)

    if resolution.state is not JobMaterialMappingState.MATCHED or resolution.slot is None:
        return result(MountedMaterialState.UNKNOWN, "job_slot_mapping_not_matched")
    slot_snapshot = resolution.slot
    if (
        resolution.provider_system_key != feed_system.provider_system_key
        or resolution.provider_slot_key != slot_snapshot.slot_key
        or slot_snapshot not in feed_system.slots
    ):
        return result(MountedMaterialState.CONFLICT, "provider_snapshot_mapping_mismatch")
    if (
        not feed_system.complete
        or feed_system.received_at > now
        or feed_system.observed_at > feed_system.received_at
        or now.value - feed_system.received_at.value > max_age
        or max_age < timedelta(0)
    ):
        return result(MountedMaterialState.UNKNOWN, "provider_snapshot_not_current")

    slot = work.slots.by_provider_key(
        printer_id,
        feed_system.provider_system_key,
        slot_snapshot.slot_key,
    )
    if slot is None:
        return result(MountedMaterialState.UNKNOWN, "provider_slot_not_persisted")
    system = work.feed_systems.get(slot.feed_system_id)
    if (
        system.printer_id != printer_id
        or system.provider_system_key != feed_system.provider_system_key
        or system.kind is not feed_system.kind
    ):
        return result(MountedMaterialState.CONFLICT, "durable_provider_topology_mismatch")
    if (
        slot.observed_at != feed_system.observed_at
        or slot.received_at != feed_system.received_at
        or slot.source_epoch != feed_system.source_epoch
        or slot.source_sequence != feed_system.source_sequence
    ):
        return result(MountedMaterialState.UNKNOWN, "provider_snapshot_not_durable")
    command_key, fingerprint = provider_slot_snapshot_audit_proof(
        printer_id=printer_id,
        system_id=system.id,
        provider_system_key=feed_system.provider_system_key,
        system_kind=feed_system.kind,
        slot_id=slot.id,
        snapshot=slot_snapshot,
        observed_at=feed_system.observed_at,
        received_at=feed_system.received_at,
        source_epoch=feed_system.source_epoch,
        source_sequence=feed_system.source_sequence,
    )
    events = work.audit.for_command(command_key)
    try:
        proof_matches = (
            len(events) == 1
            and events[0].event_code == "feed_slot.snapshot_observed"
            and events[0].entity_type == "feed_slot"
            and events[0].entity_id == slot.id
            and json.loads(events[0].parameters_json) == {"request_hash_v1": fingerprint}
        )
    except (TypeError, ValueError):
        proof_matches = False
    if not proof_matches:
        return result(MountedMaterialState.UNKNOWN, "provider_snapshot_audit_proof_missing")

    mount: SpoolMount | None = work.mounts.active_for_slot(slot.id)
    if mount is None:
        return result(MountedMaterialState.UNMOUNTED, "provider_slot_has_no_active_mount")
    if slot.assignment_state is not SlotAssignment.ASSIGNED or mount.deleted_at is not None:
        return result(MountedMaterialState.CONFLICT, "durable_mount_state_conflict")

    identity = resolve_feed_slot_spool(
        slot_snapshot,
        namespace=identifier_namespace,
        identifiers=work.spool_identifiers,
    )
    if identity.state is SlotSpoolMatchState.CONFLICT:
        return result(MountedMaterialState.CONFLICT, "provider_identifiers_conflict")
    if identity.state is SlotSpoolMatchState.UNKNOWN:
        return result(MountedMaterialState.UNKNOWN, "provider_identifier_unverified")
    if identity.spool_id != mount.spool_id:
        return result(MountedMaterialState.CONFLICT, "mounted_spool_identity_mismatch")
    spool = work.spools.get(mount.spool_id)
    if spool.deleted_at is not None or spool.lifecycle is SpoolLifecycle.ARCHIVED:
        return result(MountedMaterialState.CONFLICT, "mounted_spool_unavailable")
    return MountedMaterialResolution(
        logical,
        MountedMaterialState.MATCHED,
        slot.id,
        mount.id,
        spool.id,
    )
