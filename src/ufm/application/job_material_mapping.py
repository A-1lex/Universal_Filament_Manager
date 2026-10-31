"""Fail-closed join of a printer job, verified slice and exact feed slot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from ufm.application.dto.providers import FeedSlotSnapshot, PrinterStatusSnapshot
from ufm.application.dto.slice_facts import VerifiedSliceFacts
from ufm.application.dto.worker_protocol import JobMessage
from ufm.domain.value_objects import UtcDateTime


class JobMaterialMappingState(StrEnum):
    MATCHED = "MATCHED"
    UNUSED = "UNUSED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class JobMaterialSlotResolution:
    logical_material: int
    state: JobMaterialMappingState
    provider_system_key: str | None = None
    provider_slot_key: str | None = None
    slot: FeedSlotSnapshot | None = None
    reason_code: str | None = None


def resolve_job_material_slots(
    job: JobMessage,
    facts: VerifiedSliceFacts,
    status: PrinterStatusSnapshot,
    *,
    now: UtcDateTime,
    max_age: timedelta = timedelta(seconds=120),
) -> tuple[JobMaterialSlotResolution, ...]:
    """Match only explicit same-file mappings into a fresh, complete slot snapshot.

    This produces observations, not assignments: it never resolves a spool,
    mounts a slot, creates usage segments, reserves stock, or writes a ledger.
    """
    if job.file_sha256 is None or job.file_sha256 != facts.file_sha256:
        return tuple(
            JobMaterialSlotResolution(
                item.logical_material,
                JobMaterialMappingState.CONFLICT,
                reason_code="job_slice_hash_mismatch",
            )
            for item in facts.filaments
        )
    if job.printer_id != status.printer_id.value:
        return tuple(
            JobMaterialSlotResolution(
                item.logical_material,
                JobMaterialMappingState.CONFLICT,
                reason_code="job_printer_mismatch",
            )
            for item in facts.filaments
        )
    if (
        not isinstance(now, UtcDateTime)
        or not isinstance(max_age, timedelta)
        or max_age < timedelta(0)
        or status.received_at > now
        or status.observed_at > status.received_at
    ):
        return _unknown(facts, "slot_snapshot_time_invalid")
    age = now.value - status.received_at.value
    if age > max_age:
        return _unknown(facts, "slot_snapshot_stale")

    fact_by_id = {item.logical_material: item for item in facts.filaments}
    layer_ids = {logical for layer in facts.layer_filaments for logical in layer.logical_materials}
    mapping_by_id = {item.logical_material: item for item in job.material_slot_mappings}
    if len(fact_by_id) != len(facts.filaments) or len(mapping_by_id) != len(
        job.material_slot_mappings
    ):
        return _unknown(facts, "mapping_duplicate_logical_material")
    if set(mapping_by_id) - set(fact_by_id):
        return _unknown(facts, "mapping_material_not_in_slice")

    result: list[JobMaterialSlotResolution] = []
    for logical_material, fact in sorted(fact_by_id.items()):
        mapping = mapping_by_id.get(logical_material)
        if mapping is None:
            result.append(
                JobMaterialSlotResolution(
                    logical_material, JobMaterialMappingState.UNKNOWN, reason_code="mapping_absent"
                )
            )
            continue
        if mapping.disposition == "unsupported":
            result.append(
                JobMaterialSlotResolution(
                    logical_material,
                    JobMaterialMappingState.UNSUPPORTED,
                    reason_code="mapping_unsupported",
                )
            )
            continue
        used = fact.mass_mg > 0 or logical_material in layer_ids
        if mapping.disposition == "unused":
            state = JobMaterialMappingState.CONFLICT if used else JobMaterialMappingState.UNUSED
            result.append(
                JobMaterialSlotResolution(
                    logical_material,
                    state,
                    reason_code="slice_uses_reported_unused_material" if used else None,
                )
            )
            continue

        system_key, slot_key = mapping.provider_system_key, mapping.provider_slot_key
        systems = [
            system for system in status.feed_systems if system.provider_system_key == system_key
        ]
        slots = [slot for system in systems for slot in system.slots if slot.slot_key == slot_key]
        if len(systems) != 1 or len(slots) != 1:
            result.append(
                JobMaterialSlotResolution(
                    logical_material,
                    JobMaterialMappingState.UNKNOWN,
                    provider_system_key=system_key,
                    provider_slot_key=slot_key,
                    reason_code="provider_slot_not_unique",
                )
            )
            continue
        system, slot = systems[0], slots[0]
        if (
            system.received_at > now
            or system.observed_at > system.received_at
            or now.value - system.received_at.value > max_age
        ):
            result.append(
                JobMaterialSlotResolution(
                    logical_material,
                    JobMaterialMappingState.UNKNOWN,
                    provider_system_key=system_key,
                    provider_slot_key=slot_key,
                    reason_code="provider_system_snapshot_stale",
                )
            )
            continue
        if not system.complete:
            result.append(
                JobMaterialSlotResolution(
                    logical_material,
                    JobMaterialMappingState.UNKNOWN,
                    provider_system_key=system_key,
                    provider_slot_key=slot_key,
                    reason_code="provider_system_incomplete",
                )
            )
            continue
        if slot.occupancy.value is not True:
            result.append(
                JobMaterialSlotResolution(
                    logical_material,
                    JobMaterialMappingState.UNKNOWN,
                    provider_system_key=system_key,
                    provider_slot_key=slot_key,
                    reason_code="provider_slot_not_confirmed_occupied",
                )
            )
            continue
        result.append(
            JobMaterialSlotResolution(
                logical_material,
                JobMaterialMappingState.MATCHED,
                provider_system_key=system_key,
                provider_slot_key=slot_key,
                slot=slot,
            )
        )
    return tuple(result)


def _unknown(facts: VerifiedSliceFacts, reason: str) -> tuple[JobMaterialSlotResolution, ...]:
    return tuple(
        JobMaterialSlotResolution(
            item.logical_material, JobMaterialMappingState.UNKNOWN, reason_code=reason
        )
        for item in facts.filaments
    )
