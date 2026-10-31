import unittest
from datetime import UTC, datetime

from ufm.domain.entities import Spool
from ufm.domain.enums import InventoryHealth
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def spool(**changes: object) -> Spool:
    timestamp = UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC))
    values: dict[str, object] = {
        "id": EntityId.new(), "device_id": EntityId.new(), "created_at": timestamp,
        "updated_at": timestamp, "revision": 1, "display_name": "PLA Black",
        "filament_profile_id": EntityId.new(),
    }
    values.update(changes)
    return Spool(**values)  # type: ignore[arg-type]


class SpoolTests(unittest.TestCase):
    def test_nominal_mass_does_not_fabricate_an_opening_balance(self) -> None:
        item = spool(nominal_filament=Mass.from_grams(1000))
        self.assertIsNone(item.estimated_remaining)
        self.assertIsNone(item.effective_remaining)
        self.assertIsNone(item.available(Mass(0)))

    def test_available_is_derived_and_unknown_remains_unknown(self) -> None:
        item = spool(effective_remaining=Mass.from_grams(700))
        self.assertEqual(item.available(Mass.from_grams(420)), Mass.from_grams(280))
        self.assertNotIn("reserved", item.__dataclass_fields__)

    def test_negative_effective_stock_is_preserved_only_with_quarantine(self) -> None:
        with self.assertRaises(ValueError):
            spool(effective_remaining=Mass(-1))
        item = spool(effective_remaining=Mass(-1), inventory_health=InventoryHealth.QUARANTINED)
        self.assertEqual(item.effective_remaining, Mass(-1))

    def test_physical_inputs_and_reservations_cannot_be_negative(self) -> None:
        for field in ("nominal_filament", "empty_spool", "measured_remaining", "low_threshold"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                spool(**{field: Mass(-1)})
        with self.assertRaises(ValueError):
            spool(effective_remaining=Mass(100)).available(Mass(-1))
