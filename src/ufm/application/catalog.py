"""Audited catalog writes for filament manufacturers and material profiles."""

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
from ufm.domain.entities import AuditEvent, Brand, FilamentProfile
from ufm.domain.value_objects import EntityId, UtcDateTime

UnitOfWorkFactory = Callable[[], UnitOfWork]


class CatalogCommands:
    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def create_brand(
        self, *, brand: Brand, actor_device_id: EntityId, command_key: str,
    ) -> Brand:
        fingerprint = self._fingerprint({"id": str(brand.id), "name": brand.name,
                                         "actor": str(actor_device_id)})
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "catalog.brand_created", "brand",
                                  brand.id, fingerprint)
            if replay:
                return work.brands.get(brand.id)
            try:
                work.brands.get(brand.id)
            except NotFound:
                pass
            else:
                raise IdempotencyConflict()
            work.brands.add(brand)
            self._audit(work, actor_device_id, brand.created_at, "catalog.brand_created",
                        command_key, "brand", brand.id, fingerprint)
            work.commit()
            return brand

    def edit_brand(
        self, *, brand_id: EntityId, expected_revision: int, name: str,
        actor_device_id: EntityId, command_key: str, at: UtcDateTime | None = None,
    ) -> Brand:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint({
            "id": str(brand_id), "expected_revision": expected_revision,
            "name": name, "actor": str(actor_device_id),
        })
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "catalog.brand_updated", "brand",
                                  brand_id, fingerprint)
            if replay:
                return work.brands.get(brand_id)
            current = work.brands.get(brand_id)
            if current.deleted_at is not None:
                raise NotFound()
            if current.revision != expected_revision:
                raise RevisionConflict()
            updated = replace(
                current, name=name.strip(), revision=current.revision + 1,
                updated_at=occurred_at,
            )
            work.brands.save(updated, expected_revision)
            self._audit(work, actor_device_id, occurred_at, "catalog.brand_updated",
                        command_key, "brand", brand_id, fingerprint)
            work.commit()
            return updated

    def archive_brand(
        self, *, brand_id: EntityId, expected_revision: int,
        actor_device_id: EntityId, command_key: str, at: UtcDateTime | None = None,
    ) -> Brand:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint({
            "id": str(brand_id), "expected_revision": expected_revision,
            "actor": str(actor_device_id),
        })
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "catalog.brand_archived", "brand",
                                  brand_id, fingerprint)
            if replay:
                return work.brands.get(brand_id)
            current = work.brands.get(brand_id)
            if current.deleted_at is not None:
                raise NotFound()
            if current.revision != expected_revision:
                raise RevisionConflict()
            updated = replace(
                current, deleted_at=occurred_at, revision=current.revision + 1,
                updated_at=occurred_at,
            )
            work.brands.save(updated, expected_revision)
            self._audit(work, actor_device_id, occurred_at, "catalog.brand_archived",
                        command_key, "brand", brand_id, fingerprint)
            work.commit()
            return updated

    def save_profile(
        self,
        *,
        profile: FilamentProfile,
        expected_revision: int | None,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> FilamentProfile:
        occurred_at = at or profile.updated_at
        event_code = "catalog.profile_created" if expected_revision is None else "catalog.profile_updated"
        fingerprint = self._fingerprint({
            "id": str(profile.id), "expected_revision": expected_revision,
            "name": profile.name, "material_type": profile.material_type.value,
            "diameter_mm": profile.diameter_mm.canonical(),
            "subtype": profile.subtype,
            "brand_id": None if profile.brand_id is None else str(profile.brand_id),
            "product_line": profile.product_line,
            "custom_material_name": profile.custom_material_name,
            "density_g_cm3": None if profile.density_g_cm3 is None else profile.density_g_cm3.canonical(),
            "abrasive": profile.abrasive, "flexible": profile.flexible,
            "hygroscopic": profile.hygroscopic, "soluble": profile.soluble,
            "filled_material": profile.filled_material, "actor": str(actor_device_id),
            "nozzle_min_c": None if profile.nozzle_min_c is None else profile.nozzle_min_c.canonical(),
            "nozzle_max_c": None if profile.nozzle_max_c is None else profile.nozzle_max_c.canonical(),
            "bed_min_c": None if profile.bed_min_c is None else profile.bed_min_c.canonical(),
            "bed_max_c": None if profile.bed_max_c is None else profile.bed_max_c.canonical(),
            "chamber_min_c": None if profile.chamber_min_c is None else profile.chamber_min_c.canonical(),
            "chamber_max_c": None if profile.chamber_max_c is None else profile.chamber_max_c.canonical(),
            "max_volumetric_speed_mm3_s": (
                None if profile.max_volumetric_speed_mm3_s is None
                else profile.max_volumetric_speed_mm3_s.canonical()
            ),
            "drying_temp_c": None if profile.drying_temp_c is None else profile.drying_temp_c.canonical(),
            "drying_duration_min": profile.drying_duration_min,
            "default_color_name": profile.default_color_name,
            "notes": profile.notes,
        })
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, event_code, "filament_profile",
                                  profile.id, fingerprint)
            if replay:
                return work.filament_profiles.get(profile.id)
            if profile.brand_id is not None:
                brand = work.brands.get(profile.brand_id)
                if brand.deleted_at is not None:
                    existing_brand = (
                        None if expected_revision is None
                        else work.filament_profiles.get(profile.id).brand_id
                    )
                    if existing_brand != profile.brand_id:
                        raise NotFound()
            if expected_revision is None:
                if profile.revision != 1:
                    raise RevisionConflict()
                try:
                    work.filament_profiles.get(profile.id)
                except NotFound:
                    pass
                else:
                    raise IdempotencyConflict()
                work.filament_profiles.add(profile)
            else:
                current = work.filament_profiles.get(profile.id)
                if current.revision != expected_revision or profile.revision != expected_revision + 1:
                    raise RevisionConflict()
                if current.deleted_at is not None:
                    raise NotFound()
                work.filament_profiles.save(profile, expected_revision)
            self._audit(work, actor_device_id, occurred_at, event_code, command_key,
                        "filament_profile", profile.id, fingerprint)
            work.commit()
            return profile

    @staticmethod
    def _fingerprint(payload: dict[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("ascii")).hexdigest()

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
