"""Desktop read models; stock mutations always pass through InventoryCommands."""

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from ufm.application.accounting_authority import PrinterAccountingAuthorityCommands
from ufm.application.catalog import CatalogCommands
from ufm.application.inventory import (
    InventoryCommands,
    InventoryCostReport,
    InventoryCostSummary,
    InventoryMeasurementRecord,
)
from ufm.application.ports.persistence import NotFound
from ufm.application.ports.secrets import SecretStore, SecretValue
from ufm.application.storage import StorageCommands
from ufm.domain.entities.accounting import InventoryEvidence
from ufm.domain.entities.catalog import Brand, FilamentProfile
from ufm.domain.entities.ledger import FilamentTransaction
from ufm.domain.enums import EvidenceSource, MaterialType, PrinterAccountingMode, StorageType
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime
from ufm.infrastructure.backup.sqlite_snapshot import create_snapshot
from ufm.infrastructure.persistence.models.schema import (
    brand,
    connection_profile,
    filament_profile,
    haspel_authority_connection,
    print_job,
    printer,
    spool,
    storage_location,
)
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.haspelsync.authority_client import (
    AuthorityOwner,
    HaspelAuthorityClient,
    HaspelAuthoritySnapshot,
    HaspelAuthorityUnavailable,
    HaspelBookingRecord,
)
from ufm.integrations.printers.configuration import ensure_local_device
from ufm.integrations.spoolman.importer import (
    SpoolmanImportSourceInfo,
    list_spoolman_import_sources,
)
from ufm.platform.common.paths import AppPaths


@dataclass(frozen=True)
class StudioSpool:
    id: str
    revision: int
    name: str
    profile: str
    material: str
    remaining_mg: int | None
    lifecycle: str
    health: str
    color_name: str | None
    color_hex: str | None
    location: str | None
    location_id: str | None
    profile_id: str
    low_threshold_mg: int | None
    product_line: str | None = None
    batch_number: str | None = None
    lot_number: str | None = None
    secondary_color_hex: str | None = None
    image_uri: str | None = None
    notes: str | None = None
    brand_id: str | None = None
    brand: str | None = None
    nominal_filament_mg: int | None = None
    empty_spool_mg: int | None = None
    opened_date: str | None = None
    manufactured_date: str | None = None
    expires_date: str | None = None
    purchase_price: str | None = None
    purchase_basis_mg: int | None = None
    currency: str | None = None
    purchase_date: str | None = None


@dataclass(frozen=True)
class StudioBrand:
    id: str
    revision: int
    name: str


@dataclass(frozen=True)
class StudioMaterial:
    id: str
    name: str
    material: str
    brand_id: str | None = None
    brand: str | None = None
    product_line: str | None = None
    diameter_mm: str = "1.75"
    density_g_cm3: str | None = None
    custom_material_name: str | None = None
    abrasive: bool = False
    flexible: bool = False
    hygroscopic: bool = False
    soluble: bool = False
    filled_material: bool = False
    subtype: str | None = None
    nozzle_min_c: str | None = None
    nozzle_max_c: str | None = None
    bed_min_c: str | None = None
    bed_max_c: str | None = None
    chamber_min_c: str | None = None
    chamber_max_c: str | None = None
    max_volumetric_speed_mm3_s: str | None = None
    drying_temp_c: str | None = None
    drying_duration_min: int | None = None
    default_color_name: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class StudioPrinter:
    id: str
    name: str
    model: str
    provider: str
    host: str
    serial_number: str = ""


@dataclass(frozen=True)
class StudioLocation:
    id: str
    name: str
    storage_type: str
    parent_id: str | None


def _iso(value: UtcDateTime | None) -> str | None:
    return None if value is None else value.value.isoformat()


@dataclass(frozen=True)
class StudioJobRow:
    id: str
    name: str | None
    file_name: str | None
    plate_name: str | None
    printer_name: str
    status: str
    finalization_state: str
    detected_at: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class StudioJobMaterialInfo:
    id: str
    channel_key: str
    tool_index: int
    filament_name: str | None
    estimated_mass_mg: int | None


@dataclass(frozen=True)
class StudioJobSegmentInfo:
    print_job_material_id: str
    tool_index: int
    assignment_state: str
    source: str
    confidence_bp: int
    started_at: str | None
    ended_at: str | None
    spool_name: str | None


@dataclass(frozen=True)
class StudioJobLedgerEntry:
    id: str
    spool_name: str | None
    sequence: int
    transaction_type: str
    delta_mg: int
    source_type: str
    confidence_bp: int
    estimate_policy_version: str
    description: str | None
    created_at: str | None


@dataclass(frozen=True)
class StudioJobDetail(StudioJobRow):
    source_type: str
    slicer_type: str | None
    progress_bp: int | None
    current_layer: int | None
    total_layers: int | None
    materials: tuple[StudioJobMaterialInfo, ...]
    segments: tuple[StudioJobSegmentInfo, ...]
    ledger: tuple[StudioJobLedgerEntry, ...]


@dataclass(frozen=True)
class StudioAccountingAuthority:
    mode: str
    revision: int
    snapshot_sha256: str | None = None
    legacy_writer_disabled_at: str | None = None
    reconciled_at: str | None = None


@dataclass(frozen=True)
class StudioHaspelAuthorityConnection:
    endpoint_origin: str
    haspel_printer_id: str
    credential_configured: bool
    local_revision: int
    observed: HaspelAuthoritySnapshot | None = None


class StudioBackend:
    def __init__(self, engine: Engine, paths: AppPaths) -> None:
        self.engine = engine
        self.paths = paths
        self.commands = InventoryCommands(lambda: SQLiteUnitOfWork(engine))
        self.storage_commands = StorageCommands(lambda: SQLiteUnitOfWork(engine))
        self.catalog_commands = CatalogCommands(lambda: SQLiteUnitOfWork(engine))
        self.accounting_authority_commands = PrinterAccountingAuthorityCommands(
            lambda: SQLiteUnitOfWork(engine),
        )

    def accounting_authority(self, printer_id: str) -> StudioAccountingAuthority | None:
        with SQLiteUnitOfWork(self.engine) as work:
            authority = work.printer_accounting_authorities.for_printer(EntityId.parse(printer_id))
        if authority is None:
            return None
        return StudioAccountingAuthority(
            authority.mode.value, authority.revision, authority.snapshot_sha256,
            None if authority.legacy_writer_disabled_at is None
            else authority.legacy_writer_disabled_at.isoformat(),
            None if authority.reconciled_at is None else authority.reconciled_at.isoformat(),
        )

    def transition_accounting_authority(
        self, printer_id: str, mode: str, expected_revision: int, *,
        snapshot_sha256: str | None = None,
        legacy_writer_disabled_at: str | None = None,
        reconciled_at: str | None = None,
    ) -> StudioAccountingAuthority:
        authority = self.accounting_authority_commands.transition(
            printer_id=EntityId.parse(printer_id),
            mode=PrinterAccountingMode(mode),
            actor_device_id=ensure_local_device(self.engine),
            command_key=f"studio-accounting-authority-{uuid4()}",
            expected_revision=expected_revision,
            snapshot_sha256=snapshot_sha256,
            legacy_writer_disabled_at=(
                None if legacy_writer_disabled_at is None
                else UtcDateTime.parse(legacy_writer_disabled_at)
            ),
            reconciled_at=(
                None if reconciled_at is None else UtcDateTime.parse(reconciled_at)
            ),
        )
        return StudioAccountingAuthority(
            authority.mode.value, authority.revision, authority.snapshot_sha256,
            None if authority.legacy_writer_disabled_at is None
            else authority.legacy_writer_disabled_at.isoformat(),
            None if authority.reconciled_at is None else authority.reconciled_at.isoformat(),
        )

    def haspel_authority_connection(
        self, printer_id: str,
    ) -> StudioHaspelAuthorityConnection | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(
                haspel_authority_connection.c.endpoint_origin,
                haspel_authority_connection.c.haspel_printer_id,
                haspel_authority_connection.c.credential_ref,
                haspel_authority_connection.c.revision,
                haspel_authority_connection.c.observed_capability_version,
                haspel_authority_connection.c.observed_owner,
                haspel_authority_connection.c.observed_revision,
                haspel_authority_connection.c.observed_pending_count,
                haspel_authority_connection.c.observed_uncertain_count,
                haspel_authority_connection.c.observed_active_count,
            ).where(
                haspel_authority_connection.c.printer_id == EntityId.parse(printer_id),
                haspel_authority_connection.c.deleted_at.is_(None),
            )).mappings().one_or_none()
        if row is None:
            return None
        observed = None
        if row["observed_capability_version"] is not None:
            observed = HaspelAuthoritySnapshot(
                printer_id=row["haspel_printer_id"],
                owner=row["observed_owner"],
                revision=row["observed_revision"],
                pending_count=row["observed_pending_count"],
                uncertain_count=row["observed_uncertain_count"],
                active_count=row["observed_active_count"],
                capability_version=row["observed_capability_version"],
            )
        return StudioHaspelAuthorityConnection(
            endpoint_origin=row["endpoint_origin"],
            haspel_printer_id=row["haspel_printer_id"],
            credential_configured=bool(row["credential_ref"]),
            local_revision=row["revision"],
            observed=observed,
        )

    def configure_haspel_authority_connection(
        self,
        printer_id: str,
        endpoint_origin: str,
        haspel_printer_id: str,
        api_key: SecretValue,
        secret_store: SecretStore,
    ) -> tuple[StudioHaspelAuthorityConnection, HaspelAuthoritySnapshot]:
        identity = EntityId.parse(printer_id)
        # Verify the explicit target before persisting either endpoint or secret.
        snapshot = HaspelAuthorityClient(
            endpoint_origin, haspel_printer_id, api_key,
        ).read()
        new_reference = secret_store.put(api_key)
        old_reference: str | None = None
        actor = ensure_local_device(self.engine)
        now = UtcDateTime.now()
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(select(
                    haspel_authority_connection.c.revision,
                    haspel_authority_connection.c.credential_ref,
                ).where(
                    haspel_authority_connection.c.printer_id == identity,
                    haspel_authority_connection.c.deleted_at.is_(None),
                )).mappings().one_or_none()
                values = {
                    "device_id": actor,
                    "updated_at": now,
                    "endpoint_origin": endpoint_origin.strip().rstrip("/"),
                    "haspel_printer_id": haspel_printer_id,
                    "credential_ref": new_reference,
                    "observed_capability_version": snapshot.capability_version,
                    "observed_owner": snapshot.owner,
                    "observed_revision": snapshot.revision,
                    "observed_pending_count": snapshot.pending_count,
                    "observed_uncertain_count": snapshot.uncertain_count,
                    "observed_active_count": snapshot.active_count,
                    "observed_at": now,
                }
                if existing is None:
                    connection.execute(insert(haspel_authority_connection).values(
                        id=EntityId.new(), device_id=actor, created_at=now,
                        updated_at=now, revision=1, deleted_at=None,
                        printer_id=identity, **{k: v for k, v in values.items()
                                              if k not in {"device_id", "updated_at"}},
                    ))
                else:
                    old_reference = existing["credential_ref"]
                    result = connection.execute(update(haspel_authority_connection).where(
                        haspel_authority_connection.c.printer_id == identity,
                        haspel_authority_connection.c.revision == existing["revision"],
                        haspel_authority_connection.c.deleted_at.is_(None),
                    ).values(**values, revision=existing["revision"] + 1))
                    if result.rowcount != 1:
                        raise HaspelAuthorityUnavailable()
        except Exception:
            try:
                secret_store.delete(new_reference)
            except Exception:
                pass
            raise
        if old_reference is not None:
            try:
                secret_store.delete(old_reference)
            except Exception:
                # The connection no longer points to this old OS-secret entry.
                pass
        connection_info = self.haspel_authority_connection(printer_id)
        if connection_info is None:
            raise HaspelAuthorityUnavailable()
        return connection_info, snapshot

    def verify_haspel_authority_connection(
        self,
        printer_id: str,
        endpoint_origin: str,
        haspel_printer_id: str,
        api_key: SecretValue | None,
        secret_store: SecretStore,
    ) -> tuple[StudioHaspelAuthorityConnection, HaspelAuthoritySnapshot]:
        if api_key is not None:
            return self.configure_haspel_authority_connection(
                printer_id, endpoint_origin, haspel_printer_id, api_key, secret_store,
            )
        existing = self.haspel_authority_connection(printer_id)
        if (
            existing is None
            or existing.endpoint_origin != endpoint_origin.strip().rstrip("/")
            or existing.haspel_printer_id != haspel_printer_id
            or not existing.credential_configured
        ):
            raise HaspelAuthorityUnavailable()
        snapshot = self.read_haspel_authority(printer_id, secret_store)
        refreshed = self.haspel_authority_connection(printer_id)
        if refreshed is None:
            raise HaspelAuthorityUnavailable()
        return refreshed, snapshot

    def read_haspel_authority(
        self, printer_id: str, secret_store: SecretStore,
    ) -> HaspelAuthoritySnapshot:
        connection_info, credential_ref = self._haspel_connection_details(printer_id)
        try:
            credential = secret_store.get(credential_ref)
        except Exception:
            raise HaspelAuthorityUnavailable() from None
        snapshot = HaspelAuthorityClient(
            connection_info.endpoint_origin,
            connection_info.haspel_printer_id,
            credential,
        ).read()
        self._record_haspel_authority_observation(printer_id, connection_info, snapshot)
        return snapshot

    def transfer_haspel_authority(
        self,
        printer_id: str,
        owner: AuthorityOwner,
        expected_revision: int,
        secret_store: SecretStore,
    ) -> HaspelAuthoritySnapshot:
        connection_info, credential_ref = self._haspel_connection_details(printer_id)
        try:
            credential = secret_store.get(credential_ref)
        except Exception:
            raise HaspelAuthorityUnavailable() from None
        snapshot = HaspelAuthorityClient(
            connection_info.endpoint_origin,
            connection_info.haspel_printer_id,
            credential,
        ).transfer(owner, expected_revision)
        self._record_haspel_authority_observation(printer_id, connection_info, snapshot)
        return snapshot

    def list_haspel_bookings(
        self, printer_id: str, secret_store: SecretStore,
    ) -> tuple[HaspelBookingRecord, ...]:
        """Reads the selected HaspelSync printer journal using its stored credential."""
        connection_info, credential_ref = self._haspel_connection_details(printer_id)
        try:
            credential = secret_store.get(credential_ref)
        except Exception:
            raise HaspelAuthorityUnavailable() from None
        return HaspelAuthorityClient(
            connection_info.endpoint_origin,
            connection_info.haspel_printer_id,
            credential,
        ).list_bookings()

    def resolve_haspel_booking(
        self,
        printer_id: str,
        booking_id: str,
        resolution: str,
        note: str,
        secret_store: SecretStore,
    ) -> tuple[HaspelBookingRecord, HaspelAuthoritySnapshot | None]:
        """Records an operator-reviewed journal outcome without repeating consumption."""
        connection_info, credential_ref = self._haspel_connection_details(printer_id)
        try:
            credential = secret_store.get(credential_ref)
        except Exception:
            raise HaspelAuthorityUnavailable() from None
        client = HaspelAuthorityClient(
            connection_info.endpoint_origin,
            connection_info.haspel_printer_id,
            credential,
        )
        record = client.resolve_booking(booking_id, resolution, note)
        try:
            snapshot = client.read()
        except HaspelAuthorityUnavailable:
            return record, None
        self._record_haspel_authority_observation(printer_id, connection_info, snapshot)
        return record, snapshot

    def activate_ufm_authority_with_haspel(
        self,
        printer_id: str,
        expected_local_revision: int,
        expected_remote_revision: int,
        snapshot_sha256: str,
        legacy_writer_disabled_at: str,
        reconciled_at: str,
        secret_store: SecretStore,
    ) -> tuple[StudioAccountingAuthority, HaspelAuthoritySnapshot]:
        local_before = self.accounting_authority(printer_id)
        if (
            local_before is None
            or local_before.mode != PrinterAccountingMode.CUTOVER_READY.value
            or local_before.revision != expected_local_revision
        ):
            raise HaspelAuthorityUnavailable()

        connection_info, credential_ref = self._haspel_connection_details(printer_id)
        try:
            credential = secret_store.get(credential_ref)
        except Exception:
            raise HaspelAuthorityUnavailable() from None
        remote_client = HaspelAuthorityClient(
            connection_info.endpoint_origin,
            connection_info.haspel_printer_id,
            credential,
        )
        remote_before = remote_client.read()
        if (
            remote_before.owner != "LEGACY_ACTIVE"
            or remote_before.revision != expected_remote_revision
            or remote_before.pending_count != 0
            or remote_before.uncertain_count != 0
            or remote_before.active_count != 0
        ):
            raise HaspelAuthorityUnavailable()

        transferred = remote_client.transfer("UFM_ACTIVE", expected_remote_revision)
        if (
            transferred.owner != "UFM_ACTIVE"
            or transferred.revision != expected_remote_revision + 1
            or transferred.pending_count != 0
            or transferred.uncertain_count != 0
            or transferred.active_count != 0
        ):
            raise HaspelAuthorityUnavailable()
        try:
            self._record_haspel_authority_observation(
                printer_id, connection_info, transferred,
            )
        except Exception:
            # Cached observations never authorize the transition.
            pass

        try:
            local_after = self.transition_accounting_authority(
                printer_id,
                PrinterAccountingMode.UFM_ACTIVE.value,
                expected_local_revision,
                snapshot_sha256=snapshot_sha256,
                legacy_writer_disabled_at=legacy_writer_disabled_at,
                reconciled_at=reconciled_at,
            )
        except Exception:
            observed_local = self.accounting_authority(printer_id)
            if (
                observed_local is not None
                and observed_local.mode == PrinterAccountingMode.UFM_ACTIVE.value
                and observed_local.snapshot_sha256 == snapshot_sha256
            ):
                return observed_local, transferred

            # If the local commit did not activate UFM, best-effort freeze the
            # selected Haspel service. Failure leaves the transition unresolved.
            try:
                observed_remote = remote_client.read()
                if (
                    observed_remote.owner == "UFM_ACTIVE"
                    and observed_remote.revision == transferred.revision
                    and observed_remote.pending_count == 0
                    and observed_remote.uncertain_count == 0
                    and observed_remote.active_count == 0
                ):
                    remote_client.transfer("REVIEW_ONLY", observed_remote.revision)
            except Exception:
                pass
            raise HaspelAuthorityUnavailable() from None

        return local_after, transferred

    def _haspel_connection_details(
        self, printer_id: str,
    ) -> tuple[StudioHaspelAuthorityConnection, str]:
        details = self.haspel_authority_connection(printer_id)
        if details is None:
            raise HaspelAuthorityUnavailable()
        with self.engine.connect() as connection:
            reference = connection.execute(select(
                haspel_authority_connection.c.credential_ref,
            ).where(
                haspel_authority_connection.c.printer_id == EntityId.parse(printer_id),
                haspel_authority_connection.c.deleted_at.is_(None),
            )).scalar_one_or_none()
        if not isinstance(reference, str) or not reference:
            raise HaspelAuthorityUnavailable()
        return details, reference

    def _record_haspel_authority_observation(
        self,
        printer_id: str,
        connection_info: StudioHaspelAuthorityConnection,
        snapshot: HaspelAuthoritySnapshot,
    ) -> None:
        identity = EntityId.parse(printer_id)
        actor = ensure_local_device(self.engine)
        now = UtcDateTime.now()
        with self.engine.begin() as connection:
            result = connection.execute(update(haspel_authority_connection).where(
                haspel_authority_connection.c.printer_id == identity,
                haspel_authority_connection.c.revision == connection_info.local_revision,
                haspel_authority_connection.c.deleted_at.is_(None),
            ).values(
                device_id=actor,
                updated_at=now,
                revision=connection_info.local_revision + 1,
                observed_capability_version=snapshot.capability_version,
                observed_owner=snapshot.owner,
                observed_revision=snapshot.revision,
                observed_pending_count=snapshot.pending_count,
                observed_uncertain_count=snapshot.uncertain_count,
                observed_active_count=snapshot.active_count,
                observed_at=now,
            ))
            if result.rowcount != 1:
                raise HaspelAuthorityUnavailable()

    def storage_locations(self) -> tuple[StudioLocation, ...]:
        with SQLiteUnitOfWork(self.engine) as work:
            locations = work.storage_locations.all()
        return tuple(StudioLocation(
            str(item.id), item.name, item.storage_type.value,
            None if item.parent_id is None else str(item.parent_id),
        ) for item in locations)

    def spools(self) -> tuple[StudioSpool, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(
                spool.c.id, spool.c.display_name, filament_profile.c.name,
                spool.c.revision,
                filament_profile.c.material_type, spool.c.effective_remaining_mg,
                spool.c.lifecycle, spool.c.inventory_health, spool.c.color_name,
                spool.c.color_hex, spool.c.storage_location_id,
                storage_location.c.name, spool.c.low_threshold_mg,
                spool.c.product_line, spool.c.batch_number, spool.c.lot_number,
                spool.c.secondary_color_hex, spool.c.image_uri, spool.c.notes,
                spool.c.brand_id, brand.c.name, spool.c.nominal_filament_mg,
                spool.c.empty_spool_mg, spool.c.opened_at, spool.c.manufactured_at,
                spool.c.expires_at, spool.c.purchase_price, spool.c.currency,
                spool.c.purchase_date, spool.c.purchase_basis_mg,
                filament_profile.c.id,
            ).join(filament_profile, spool.c.filament_profile_id == filament_profile.c.id)
                .outerjoin(storage_location,
                           spool.c.storage_location_id == storage_location.c.id)
                .outerjoin(brand, spool.c.brand_id == brand.c.id)
                .where(spool.c.deleted_at.is_(None)).order_by(spool.c.display_name)).all()
        return tuple(StudioSpool(
            id=str(row[0]), revision=row[3], name=row[1], profile=row[2], material=row[4],
            remaining_mg=None if row[5] is None else row[5].milligrams,
            lifecycle=row[6], health=row[7], color_name=row[8], color_hex=row[9],
            location=row[11], location_id=None if row[10] is None else str(row[10]),
            low_threshold_mg=None if row[12] is None else row[12].milligrams,
            product_line=row[13], batch_number=row[14], lot_number=row[15],
            secondary_color_hex=row[16], image_uri=row[17], notes=row[18],
            brand_id=None if row[19] is None else str(row[19]), brand=row[20],
            nominal_filament_mg=None if row[21] is None else row[21].milligrams,
            empty_spool_mg=None if row[22] is None else row[22].milligrams,
            opened_date=None if row[23] is None else row[23].value.date().isoformat(),
            manufactured_date=None if row[24] is None else row[24].value.date().isoformat(),
            expires_date=None if row[25] is None else row[25].value.date().isoformat(),
            purchase_price=None if row[26] is None else row[26].canonical(),
            currency=row[27], purchase_date=row[28],
            purchase_basis_mg=None if row[29] is None else row[29].milligrams,
            profile_id=str(row[30]),
        ) for row in rows)

    def materials(self) -> tuple[StudioMaterial, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(
                filament_profile.c.id, filament_profile.c.name, filament_profile.c.material_type,
                brand.c.id, brand.c.name, filament_profile.c.product_line, filament_profile.c.diameter_mm,
                filament_profile.c.density_g_cm3, filament_profile.c.custom_material_name,
                filament_profile.c.abrasive, filament_profile.c.flexible,
                filament_profile.c.hygroscopic, filament_profile.c.soluble,
                filament_profile.c.filled_material,
                filament_profile.c.subtype, filament_profile.c.nozzle_min_c,
                filament_profile.c.nozzle_max_c, filament_profile.c.bed_min_c,
                filament_profile.c.bed_max_c, filament_profile.c.chamber_min_c,
                filament_profile.c.chamber_max_c,
                filament_profile.c.max_volumetric_speed_mm3_s,
                filament_profile.c.drying_temp_c, filament_profile.c.drying_duration_min,
                filament_profile.c.default_color_name, filament_profile.c.notes,
            ).select_from(filament_profile.outerjoin(
                brand, brand.c.id == filament_profile.c.brand_id,
            )).where(filament_profile.c.deleted_at.is_(None))
                .order_by(filament_profile.c.name)).all()
        return tuple(StudioMaterial(
            id=str(row[0]), name=row[1], material=row[2],
            brand_id=None if row[3] is None else str(row[3]), brand=row[4],
            product_line=row[5], diameter_mm=row[6].canonical(),
            density_g_cm3=None if row[7] is None else row[7].canonical(),
            custom_material_name=row[8], abrasive=bool(row[9]), flexible=bool(row[10]),
            hygroscopic=bool(row[11]), soluble=bool(row[12]), filled_material=bool(row[13]),
            subtype=row[14], nozzle_min_c=self._decimal_text(row[15]),
            nozzle_max_c=self._decimal_text(row[16]), bed_min_c=self._decimal_text(row[17]),
            bed_max_c=self._decimal_text(row[18]), chamber_min_c=self._decimal_text(row[19]),
            chamber_max_c=self._decimal_text(row[20]),
            max_volumetric_speed_mm3_s=self._decimal_text(row[21]),
            drying_temp_c=self._decimal_text(row[22]), drying_duration_min=row[23],
            default_color_name=row[24], notes=row[25],
        ) for row in rows)

    @staticmethod
    def _decimal_text(value: ExactDecimal | None) -> str | None:
        return None if value is None else value.canonical()

    def printers(self) -> tuple[StudioPrinter, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(
                printer.c.id, printer.c.name, printer.c.model,
                connection_profile.c.provider_type, connection_profile.c.host,
                printer.c.serial_number,
            ).join(connection_profile, printer.c.id == connection_profile.c.printer_id)
                .where(printer.c.enabled.is_(True)).order_by(printer.c.name)).all()
        return tuple(StudioPrinter(
            str(r[0]), r[1], r[2] or "", r[3], r[4], r[5] or "",
        ) for r in rows)

    def recent_jobs(self, limit: int = 50) -> tuple[StudioJobRow, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    print_job.c.id, print_job.c.name, print_job.c.file_name,
                    print_job.c.plate_name, printer.c.name,
                    print_job.c.status, print_job.c.finalization_state,
                    print_job.c.detected_at, print_job.c.started_at,
                    print_job.c.completed_at,
                ).join(printer, print_job.c.printer_id == printer.c.id)
                .where(print_job.c.deleted_at.is_(None))
                .order_by(print_job.c.detected_at.desc())
                .limit(min(max(limit, 1), 500))
            ).all()
        return tuple(StudioJobRow(
            id=str(row[0]), name=row[1], file_name=row[2], plate_name=row[3],
            printer_name=row[4], status=str(row[5]), finalization_state=str(row[6]),
            detected_at=_iso(row[7]), started_at=_iso(row[8]), completed_at=_iso(row[9]),
        ) for row in rows)

    @staticmethod
    def _entity_name(repository: object, identity: EntityId | None) -> str | None:
        if identity is None:
            return None
        try:
            entity = repository.get(identity)  # type: ignore[attr-defined]
        except NotFound:
            return None
        name = getattr(entity, "display_name", getattr(entity, "name", None))
        return name if type(name) is str else None

    def job_detail(self, job_id: str) -> StudioJobDetail | None:
        identity = EntityId.parse(job_id)
        with SQLiteUnitOfWork(self.engine) as work:
            try:
                job = work.jobs.get(identity)
            except NotFound:
                return None
            try:
                printer_name = work.printers.get(job.printer_id).name
            except NotFound:
                printer_name = str(job.printer_id)
            materials = work.jobs.materials_for_job(identity)
            segments = work.segments.for_job(identity)
            entries = work.ledger.for_job(identity)

            profile_names: dict[str, str | None] = {}
            for material in materials:
                if material.filament_profile_id is not None:
                    key = str(material.filament_profile_id)
                    if key not in profile_names:
                        profile_names[key] = self._entity_name(
                            work.filament_profiles, material.filament_profile_id,
                        )
            spool_names: dict[str, str | None] = {}
            wanted_spools = {
                segment.spool_id for segment in segments if segment.spool_id is not None
            } | {entry.spool_id for entry in entries}
            for spool_id in wanted_spools:
                spool_names[str(spool_id)] = self._entity_name(work.spools, spool_id)

        return StudioJobDetail(
            id=str(job.id), name=job.name, file_name=job.file_name,
            plate_name=job.plate_name, printer_name=printer_name,
            status=str(job.status), finalization_state=str(job.finalization_state),
            detected_at=_iso(job.detected_at), started_at=_iso(job.started_at),
            completed_at=_iso(job.completed_at),
            source_type=job.source_type, slicer_type=job.slicer_type,
            progress_bp=job.progress_bp, current_layer=job.current_layer,
            total_layers=job.total_layers,
            materials=tuple(StudioJobMaterialInfo(
                id=str(item.id), channel_key=item.channel_key,
                tool_index=item.tool_index,
                filament_name=(
                    None if item.filament_profile_id is None
                    else profile_names.get(str(item.filament_profile_id))
                ),
                estimated_mass_mg=(
                    None if item.estimated_mass is None
                    else item.estimated_mass.milligrams
                ),
            ) for item in materials),
            segments=tuple(StudioJobSegmentInfo(
                print_job_material_id=str(item.print_job_material_id),
                tool_index=item.tool_index,
                assignment_state=str(item.assignment_state),
                source=item.source, confidence_bp=item.confidence_bp,
                started_at=_iso(item.started_at), ended_at=_iso(item.ended_at),
                spool_name=spool_names.get(
                    "" if item.spool_id is None else str(item.spool_id)
                ),
            ) for item in segments),
            ledger=tuple(StudioJobLedgerEntry(
                id=str(item.id),
                spool_name=spool_names.get(str(item.spool_id)),
                sequence=item.sequence,
                transaction_type=str(item.transaction_type),
                delta_mg=item.delta.milligrams,
                source_type=item.source_type,
                confidence_bp=item.confidence_bp,
                estimate_policy_version=item.estimate_policy_version,
                description=item.description,
                created_at=_iso(item.created_at),
            ) for item in entries),
        )

    def spoolman_import_sources(self) -> tuple[SpoolmanImportSourceInfo, ...]:
        return list_spoolman_import_sources(self.engine)

    def add_material(
        self, name: str, material: str, diameter: str = "1.75", *, brand_id: str | None = None,
        product_line: str | None = None, density: str | None = None,
        custom_material_name: str | None = None,
        abrasive: bool = False, flexible: bool = False, hygroscopic: bool = False,
        soluble: bool = False, filled_material: bool = False,
        subtype: str | None = None, nozzle_min_c: str | None = None,
        nozzle_max_c: str | None = None, bed_min_c: str | None = None,
        bed_max_c: str | None = None, chamber_min_c: str | None = None,
        chamber_max_c: str | None = None, max_volumetric_speed_mm3_s: str | None = None,
        drying_temp_c: str | None = None, drying_duration_min: str | None = None,
        default_color_name: str | None = None, notes: str | None = None,
    ) -> str:
        actor = ensure_local_device(self.engine)
        now = UtcDateTime.now()
        profile = FilamentProfile(
            id=EntityId.new(), device_id=actor, created_at=now, updated_at=now, revision=1,
            name=name.strip(), material_type=MaterialType(material),
            diameter_mm=ExactDecimal.parse(diameter),
            brand_id=None if brand_id is None else EntityId.parse(brand_id),
            product_line=None if not product_line else product_line.strip(),
            density_g_cm3=None if not density else ExactDecimal.parse(density),
            custom_material_name=(
                (custom_material_name or name).strip() if material == "CUSTOM" else None
            ),
            abrasive=abrasive, flexible=flexible, hygroscopic=hygroscopic,
            soluble=soluble, filled_material=filled_material,
            subtype=self._optional_text(subtype),
            nozzle_min_c=self._optional_decimal(nozzle_min_c),
            nozzle_max_c=self._optional_decimal(nozzle_max_c),
            bed_min_c=self._optional_decimal(bed_min_c),
            bed_max_c=self._optional_decimal(bed_max_c),
            chamber_min_c=self._optional_decimal(chamber_min_c),
            chamber_max_c=self._optional_decimal(chamber_max_c),
            max_volumetric_speed_mm3_s=self._optional_decimal(max_volumetric_speed_mm3_s),
            drying_temp_c=self._optional_decimal(drying_temp_c),
            drying_duration_min=self._optional_integer(drying_duration_min),
            default_color_name=self._optional_text(default_color_name),
            notes=self._optional_text(notes),
        )
        self.catalog_commands.save_profile(
            profile=profile, expected_revision=None, actor_device_id=actor,
            command_key=f"studio-profile-{uuid4()}",
        )
        return str(profile.id)

    def brands(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.id, item.name) for item in self.brand_records())

    def brand_records(self) -> tuple[StudioBrand, ...]:
        with SQLiteUnitOfWork(self.engine) as work:
            values = work.brands.all()
        return tuple(StudioBrand(str(item.id), item.revision, item.name) for item in values)

    def add_brand(self, name: str, command_key: str) -> str:
        actor = ensure_local_device(self.engine)
        now = UtcDateTime.now()
        brand_entity = Brand(
            id=EntityId.new(), device_id=actor, created_at=now, updated_at=now,
            revision=1, name=name.strip(),
        )
        self.catalog_commands.create_brand(
            brand=brand_entity, actor_device_id=actor, command_key=command_key,
        )
        return str(brand_entity.id)

    def edit_brand(self, row: StudioBrand, name: str, command_key: str) -> None:
        self.catalog_commands.edit_brand(
            brand_id=EntityId.parse(row.id), expected_revision=row.revision,
            name=name.strip(), actor_device_id=ensure_local_device(self.engine),
            command_key=command_key,
        )

    def archive_brand(self, row: StudioBrand, command_key: str) -> None:
        self.catalog_commands.archive_brand(
            brand_id=EntityId.parse(row.id), expected_revision=row.revision,
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def edit_material(
        self, profile_id: str, *, name: str, material: str, diameter: str,
        brand_id: str | None, product_line: str | None, density: str | None,
        custom_material_name: str | None, abrasive: bool, flexible: bool,
        hygroscopic: bool, soluble: bool, filled_material: bool, command_key: str,
        subtype: str | None = None, nozzle_min_c: str | None = None,
        nozzle_max_c: str | None = None, bed_min_c: str | None = None,
        bed_max_c: str | None = None, chamber_min_c: str | None = None,
        chamber_max_c: str | None = None, max_volumetric_speed_mm3_s: str | None = None,
        drying_temp_c: str | None = None, drying_duration_min: str | None = None,
        default_color_name: str | None = None, notes: str | None = None,
    ) -> None:
        identity = EntityId.parse(profile_id)
        with SQLiteUnitOfWork(self.engine) as work:
            current = work.filament_profiles.get(identity)
        updated = replace(
            current, name=name.strip(), material_type=MaterialType(material),
            diameter_mm=ExactDecimal.parse(diameter),
            brand_id=None if brand_id is None else EntityId.parse(brand_id),
            product_line=None if not product_line else product_line.strip(),
            density_g_cm3=None if not density else ExactDecimal.parse(density),
            custom_material_name=(
                (custom_material_name or name).strip() if material == "CUSTOM" else None
            ),
            abrasive=abrasive, flexible=flexible, hygroscopic=hygroscopic,
            soluble=soluble, filled_material=filled_material,
            subtype=self._optional_text(subtype),
            nozzle_min_c=self._optional_decimal(nozzle_min_c),
            nozzle_max_c=self._optional_decimal(nozzle_max_c),
            bed_min_c=self._optional_decimal(bed_min_c),
            bed_max_c=self._optional_decimal(bed_max_c),
            chamber_min_c=self._optional_decimal(chamber_min_c),
            chamber_max_c=self._optional_decimal(chamber_max_c),
            max_volumetric_speed_mm3_s=self._optional_decimal(max_volumetric_speed_mm3_s),
            drying_temp_c=self._optional_decimal(drying_temp_c),
            drying_duration_min=self._optional_integer(drying_duration_min),
            default_color_name=self._optional_text(default_color_name),
            notes=self._optional_text(notes),
            updated_at=UtcDateTime.now(), revision=current.revision + 1,
        )
        self.catalog_commands.save_profile(
            profile=updated, expected_revision=current.revision,
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def add_spool(
        self, name: str, profile_id: str, *, brand_id: str | None = None,
        product_line: str | None = None, batch_number: str | None = None,
        lot_number: str | None = None, color_name: str | None = None,
        color_hex: str | None = None, secondary_color_hex: str | None = None,
        image_uri: str | None = None, notes: str | None = None,
        nominal_grams: str | None = None, empty_spool_grams: str | None = None,
        opened_date: str | None = None, manufactured_date: str | None = None,
        expires_date: str | None = None, purchase_price: str | None = None,
        purchase_basis_grams: str | None = None,
        currency: str | None = None, purchase_date: str | None = None,
    ) -> str:
        identity = EntityId.new()
        self.commands.create_spool(
            spool_id=identity, filament_profile_id=EntityId.parse(profile_id), display_name=name,
            actor_device_id=ensure_local_device(self.engine), command_key=f"studio-spool-{uuid4()}",
            brand_id=None if brand_id is None else EntityId.parse(brand_id),
            product_line=self._optional_text(product_line),
            batch_number=self._optional_text(batch_number), lot_number=self._optional_text(lot_number),
            color_name=self._optional_text(color_name), color_hex=self._optional_text(color_hex),
            secondary_color_hex=self._optional_text(secondary_color_hex),
            image_uri=self._optional_text(image_uri), notes=self._optional_text(notes),
            nominal_filament=(
                None if nominal_grams is None or not nominal_grams.strip()
                else Mass.from_grams(nominal_grams.strip().replace(",", "."))
            ),
            empty_spool=(
                None if empty_spool_grams is None or not empty_spool_grams.strip()
                else Mass.from_grams(empty_spool_grams.strip().replace(",", "."))
            ),
            opened_at=self._optional_date(opened_date),
            manufactured_at=self._optional_date(manufactured_date),
            expires_at=self._optional_date(expires_date),
            purchase_price=self._optional_decimal(purchase_price),
            purchase_basis=(
                None if purchase_basis_grams is None or not purchase_basis_grams.strip()
                else Mass.from_grams(purchase_basis_grams.strip().replace(",", "."))
            ),
            currency=self._optional_text(currency),
            purchase_date=self._optional_text(purchase_date),
        )
        return str(identity)

    def change_stock(self, spool_id: str, mode: str, grams: str, command_key: str) -> None:
        amount = Mass.from_grams(grams.strip().replace(",", "."))
        if amount.milligrams < 0 or (mode != "opening" and amount.milligrams == 0):
            raise ValueError("studio.positive_mass_required")
        actor = ensure_local_device(self.engine)
        identity = EntityId.parse(spool_id)
        if mode == "opening":
            self.commands.establish_opening_stock(
                spool_id=identity, amount=amount, command_key=command_key, actor_device_id=actor,
            )
        elif mode == "deduct":
            self.commands.deduct_manual(
                spool_id=identity, amount=amount, command_key=command_key, actor_device_id=actor,
            )
        elif mode == "add":
            self.commands.adjust(
                spool_id=identity, delta=amount, command_key=command_key, actor_device_id=actor,
            )
        else:
            raise ValueError("studio.invalid_stock_mode")

    def record_manual_measurement(
        self, spool_id: str, gross_grams: str, tare_grams: str, command_key: str,
    ) -> InventoryEvidence:
        gross = Mass.from_grams(gross_grams.strip().replace(",", "."))
        tare = Mass.from_grams(tare_grams.strip().replace(",", "."))
        net = Mass(gross.milligrams - tare.milligrams)
        return self.commands.record_inventory_measurement(
            spool_id=EntityId.parse(spool_id), source=EvidenceSource.MANUAL,
            gross=gross, tare=tare, net=net,
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def accept_manual_measurement(
        self, row: StudioSpool, evidence_id: EntityId, reason: str, command_key: str,
    ) -> None:
        self.commands.accept_inventory_measurement(
            spool_id=EntityId.parse(row.id), evidence_id=evidence_id,
            expected_revision=row.revision,
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
            reason=reason,
        )

    def history(self, spool_id: str) -> tuple[FilamentTransaction, ...]:
        return self.commands.history(EntityId.parse(spool_id))

    def cost_summary(self, spool_id: str) -> InventoryCostSummary:
        return self.commands.cost_summary(EntityId.parse(spool_id))

    def cost_report(
        self, started_at: UtcDateTime, until: UtcDateTime,
        printer_id: str | None = None,
    ) -> InventoryCostReport:
        return self.commands.cost_report(
            started_at=started_at, until=until,
            printer_id=None if printer_id is None else EntityId.parse(printer_id),
        )

    def measurement_history(self, spool_id: str) -> tuple[InventoryMeasurementRecord, ...]:
        return self.commands.measurement_history(EntityId.parse(spool_id))

    def edit_spool(
        self, row: StudioSpool, name: str, threshold_grams: str, command_key: str,
        *, product_line: str | None = None, batch_number: str | None = None,
        lot_number: str | None = None, color_name: str | None = None,
        color_hex: str | None = None, secondary_color_hex: str | None = None,
        image_uri: str | None = None, notes: str | None = None,
        brand_id: str | None = None, nominal_grams: str = "", empty_spool_grams: str = "",
        opened_date: str | None = None, manufactured_date: str | None = None,
        expires_date: str | None = None, purchase_price: str | None = None,
        purchase_basis_grams: str | None = None,
        currency: str | None = None, purchase_date: str | None = None,
    ) -> None:
        threshold = (
            None if not threshold_grams.strip()
            else Mass.from_grams(threshold_grams.strip().replace(",", "."))
        )
        nominal = None if not nominal_grams.strip() else Mass.from_grams(
            nominal_grams.strip().replace(",", "."),
        )
        empty = None if not empty_spool_grams.strip() else Mass.from_grams(
            empty_spool_grams.strip().replace(",", "."),
        )
        self.commands.edit_spool(
            spool_id=EntityId.parse(row.id), expected_revision=row.revision,
            display_name=name.strip(), low_threshold=threshold,
            product_line=product_line, batch_number=batch_number, lot_number=lot_number,
            color_name=color_name, color_hex=color_hex,
            secondary_color_hex=secondary_color_hex, image_uri=image_uri, notes=notes,
            brand_id=None if brand_id is None else EntityId.parse(brand_id),
            nominal_filament=nominal, empty_spool=empty,
            opened_at=self._optional_date(opened_date),
            manufactured_at=self._optional_date(manufactured_date),
            expires_at=self._optional_date(expires_date),
            purchase_price=self._optional_decimal(purchase_price),
            purchase_basis=(
                None if purchase_basis_grams is None or not purchase_basis_grams.strip()
                else Mass.from_grams(purchase_basis_grams.strip().replace(",", "."))
            ),
            currency=self._optional_text(currency),
            purchase_date=self._optional_text(purchase_date),
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def archive_spool(self, row: StudioSpool, command_key: str) -> None:
        self.commands.archive_spool(
            spool_id=EntityId.parse(row.id), expected_revision=row.revision,
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def compensate(self, transaction_id: str, command_key: str) -> None:
        self.commands.compensate(
            transaction_id=EntityId.parse(transaction_id), command_key=command_key,
            actor_device_id=ensure_local_device(self.engine),
        )

    def rebuild_projection(self, row: StudioSpool, command_key: str) -> None:
        self.commands.rebuild_projection(
            spool_id=EntityId.parse(row.id), expected_revision=row.revision,
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def create_storage_location(self, name: str, storage_type: str, command_key: str) -> str:
        identity = EntityId.new()
        self.storage_commands.create_location(
            location_id=identity, name=name.strip(), storage_type=StorageType(storage_type),
            parent_id=None, actor_device_id=ensure_local_device(self.engine),
            command_key=command_key,
        )
        return str(identity)

    @staticmethod
    def _optional_decimal(value: str | None) -> ExactDecimal | None:
        return None if value is None or not value.strip() else ExactDecimal.parse(value.strip().replace(",", "."))

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        return None if value is None or not value.strip() else value.strip()

    @staticmethod
    def _optional_integer(value: str | None) -> int | None:
        return None if value is None or not value.strip() else int(value.strip())

    @staticmethod
    def _optional_date(value: str | None) -> UtcDateTime | None:
        if value is None or not value.strip():
            return None
        date_text = value.strip()
        if len(date_text) != 10:
            raise ValueError("spool.date_invalid")
        return UtcDateTime.parse(f"{date_text}T00:00:00.000000Z")

    def assign_storage_location(
        self, row: StudioSpool, location_id: str | None, command_key: str,
    ) -> None:
        self.storage_commands.assign_spool(
            spool_id=EntityId.parse(row.id), expected_revision=row.revision,
            location_id=None if location_id is None else EntityId.parse(location_id),
            actor_device_id=ensure_local_device(self.engine), command_key=command_key,
        )

    def backup(self) -> Path:
        return create_snapshot(
            self.paths.data / "ufm.sqlite3", self.paths.data / "backups" / str(uuid4()),
        )
