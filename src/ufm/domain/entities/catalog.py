"""Manufacturer-neutral filament catalog and storage/sensor records."""

from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord, ImmutableRecord
from ufm.domain.enums import MaterialType, SensorType, StorageType
from ufm.domain.value_objects import EntityId, ExactDecimal, UtcDateTime


def _name(value: str, code: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 200:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class Brand(EntityRecord):
    name: str

    def __post_init__(self) -> None:
        super(Brand, self).__post_init__()
        _name(self.name, "brand.name_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class FilamentProfile(EntityRecord):
    name: str
    material_type: MaterialType
    diameter_mm: ExactDecimal
    subtype: str | None = None
    brand_id: EntityId | None = None
    product_line: str | None = None
    custom_material_name: str | None = None
    density_g_cm3: ExactDecimal | None = None
    abrasive: bool = False
    flexible: bool = False
    hygroscopic: bool = False
    soluble: bool = False
    filled_material: bool = False
    nozzle_min_c: ExactDecimal | None = None
    nozzle_max_c: ExactDecimal | None = None
    bed_min_c: ExactDecimal | None = None
    bed_max_c: ExactDecimal | None = None
    chamber_min_c: ExactDecimal | None = None
    chamber_max_c: ExactDecimal | None = None
    max_volumetric_speed_mm3_s: ExactDecimal | None = None
    drying_temp_c: ExactDecimal | None = None
    drying_duration_min: int | None = None
    default_color_name: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        super(FilamentProfile, self).__post_init__()
        _name(self.name, "filament_profile.name_invalid")
        if self.diameter_mm.value <= 0:
            raise ValueError("filament_profile.diameter_invalid")
        if self.density_g_cm3 is not None and self.density_g_cm3.value <= 0:
            raise ValueError("filament_profile.density_invalid")
        for field_name in (
            "nozzle_min_c", "nozzle_max_c", "bed_min_c", "bed_max_c",
            "chamber_min_c", "chamber_max_c", "max_volumetric_speed_mm3_s",
            "drying_temp_c",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, ExactDecimal):
                raise TypeError(f"filament_profile.{field_name}_invalid")
            if value is not None and value.value < 0:
                raise ValueError(f"filament_profile.{field_name}_invalid")
        for low, high, code in (
            (self.nozzle_min_c, self.nozzle_max_c, "nozzle"),
            (self.bed_min_c, self.bed_max_c, "bed"),
            (self.chamber_min_c, self.chamber_max_c, "chamber"),
        ):
            if low is not None and high is not None and high.value < low.value:
                raise ValueError(f"filament_profile.{code}_range_invalid")
        if (
            self.max_volumetric_speed_mm3_s is not None
            and self.max_volumetric_speed_mm3_s.value <= 0
        ):
            raise ValueError("filament_profile.volumetric_speed_invalid")
        if self.drying_duration_min is not None and (
            type(self.drying_duration_min) is not int or self.drying_duration_min < 0
        ):
            raise ValueError("filament_profile.drying_duration_invalid")
        for field_name, limit in (("subtype", 200), ("default_color_name", 200), ("notes", 4000)):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not str or len(value) > limit):
                raise ValueError(f"filament_profile.{field_name}_invalid")
        if self.material_type is MaterialType.CUSTOM:
            if self.custom_material_name is None:
                raise ValueError("filament_profile.custom_name_required")
            _name(self.custom_material_name, "filament_profile.custom_name_invalid")
        elif self.custom_material_name is not None:
            raise ValueError("filament_profile.custom_name_forbidden")
        for flag in (
            self.abrasive, self.flexible, self.hygroscopic, self.soluble,
            self.filled_material,
        ):
            if type(flag) is not bool:
                raise TypeError("filament_profile.flag_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageLocation(EntityRecord):
    name: str
    storage_type: StorageType
    parent_id: EntityId | None = None
    description: str | None = None
    temperature_sensor_id: EntityId | None = None
    humidity_sensor_id: EntityId | None = None

    def __post_init__(self) -> None:
        super(StorageLocation, self).__post_init__()
        _name(self.name, "storage.name_invalid")
        if self.parent_id == self.id:
            raise ValueError("storage.self_parent")


@dataclass(frozen=True, slots=True, kw_only=True)
class SensorDevice(EntityRecord):
    name: str
    sensor_type: SensorType
    provider_type: str
    enabled: bool = True
    connection_config_ref: str | None = None
    last_seen_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        super(SensorDevice, self).__post_init__()
        _name(self.name, "sensor.name_invalid")
        _name(self.provider_type, "sensor.provider_invalid")
        if type(self.enabled) is not bool:
            raise TypeError("sensor.enabled_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class CalibrationRecord(ImmutableRecord):
    sensor_id: EntityId
    version: int
    calibration_type: str
    reference_value: ExactDecimal
    reference_unit: str
    offset: ExactDecimal
    scale_factor: ExactDecimal
    performed_at: UtcDateTime
    expires_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 1:
            raise ValueError("calibration.version_invalid")
        _name(self.calibration_type, "calibration.type_invalid")
        _name(self.reference_unit, "calibration.unit_invalid")
        if self.scale_factor.value == 0:
            raise ValueError("calibration.scale_factor_invalid")
        if self.expires_at is not None and self.expires_at < self.performed_at:
            raise ValueError("calibration.expiry_invalid")
