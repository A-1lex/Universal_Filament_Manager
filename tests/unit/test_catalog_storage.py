import unittest
from datetime import UTC, datetime, timedelta

from ufm.domain.entities import CalibrationRecord, FilamentProfile, StorageLocation
from ufm.domain.enums import MaterialType, StorageType
from ufm.domain.policies import validate_storage_tree
from ufm.domain.value_objects import EntityId, ExactDecimal, UtcDateTime


def at(minutes: int = 0) -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC) + timedelta(minutes=minutes))


def mutable(entity_id: EntityId | None = None) -> dict[str, object]:
    return {
        "id": entity_id or EntityId.new(), "device_id": EntityId.new(),
        "created_at": at(), "updated_at": at(), "revision": 1,
    }


class ExactDecimalTests(unittest.TestCase):
    def test_canonical_decimal_has_no_float_path(self) -> None:
        self.assertEqual(ExactDecimal.parse("1.7500").canonical(), "1.75")
        self.assertEqual(ExactDecimal.parse("-0.0").canonical(), "0")
        for value in (1.75, True, "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                ExactDecimal.parse(value)  # type: ignore[arg-type]


class CatalogTests(unittest.TestCase):
    def test_custom_material_requires_name_and_physical_values_are_positive(self) -> None:
        common = dict(
            **mutable(), name="Custom", material_type=MaterialType.CUSTOM,
            diameter_mm=ExactDecimal.parse("1.75"),
        )
        with self.assertRaises(ValueError):
            FilamentProfile(**common)
        profile = FilamentProfile(**common, custom_material_name="PLA-CF")
        self.assertEqual(profile.diameter_mm.canonical(), "1.75")
        with self.assertRaises(ValueError):
            FilamentProfile(
                **mutable(), name="PLA", material_type=MaterialType.PLA,
                diameter_mm=ExactDecimal.parse("0"),
            )

    def test_calibration_expiry_and_scale_factor_are_validated(self) -> None:
        common = dict(
            id=EntityId.new(), device_id=EntityId.new(), created_at=at(),
            sensor_id=EntityId.new(), version=1, calibration_type="scale",
            reference_value=ExactDecimal.parse("1000"), reference_unit="g",
            offset=ExactDecimal.parse("0"), scale_factor=ExactDecimal.parse("1"),
            performed_at=at(1),
        )
        with self.assertRaises(ValueError):
            CalibrationRecord(**common, expires_at=at(0))


class StorageTests(unittest.TestCase):
    def test_hierarchy_accepts_tree_and_rejects_cycle(self) -> None:
        root_id, child_id = EntityId.new(), EntityId.new()
        root = StorageLocation(
            **mutable(root_id), name="Workshop", storage_type=StorageType.ROOM,
        )
        child = StorageLocation(
            **mutable(child_id), name="Cabinet", storage_type=StorageType.CABINET,
            parent_id=root_id,
        )
        validate_storage_tree([root, child])
        cyclic_root = StorageLocation(
            **mutable(root_id), name="Workshop", storage_type=StorageType.ROOM,
            parent_id=child_id,
        )
        with self.assertRaises(ValueError):
            validate_storage_tree([cyclic_root, child])
