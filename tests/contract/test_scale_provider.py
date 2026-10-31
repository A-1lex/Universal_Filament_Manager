import inspect
import unittest
from datetime import UTC, datetime

from ufm.application.dto import Observed, WeightReading
from ufm.application.ports import ScaleProvider
from ufm.domain.enums import Availability
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 11, tzinfo=UTC))


def known[ValueT](value: ValueT) -> Observed[ValueT]:
    return Observed(Availability.KNOWN, now(), now(), value)


class ScaleProviderContractTests(unittest.TestCase):
    def test_scale_port_is_async_and_cannot_mutate_inventory(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(ScaleProvider.read))
        self.assertTrue(inspect.iscoroutinefunction(ScaleProvider.tare))
        self.assertFalse(hasattr(ScaleProvider, "adjust_stock"))

    def test_reading_enforces_exact_gross_tare_net_relation(self) -> None:
        reading = WeightReading(
            sensor_id=EntityId.new(),
            associated_spool_id=EntityId.new(),
            gross_mass=known(Mass.from_grams("1100")),
            tare_mass=known(Mass.from_grams("250")),
            net_mass=known(Mass.from_grams("850")),
            stable=known(True),
            interval_start=now(),
            interval_end=now(),
            observed_at=now(),
            received_at=now(),
        )
        self.assertEqual(reading.net_mass.value, Mass.from_grams("850"))
        with self.assertRaisesRegex(ValueError, "mass_relation_invalid"):
            WeightReading(
                sensor_id=EntityId.new(),
                associated_spool_id=None,
                gross_mass=known(Mass.from_grams("1100")),
                tare_mass=known(Mass.from_grams("250")),
                net_mass=known(Mass.from_grams("849")),
                stable=known(True),
                interval_start=now(),
                interval_end=now(),
                observed_at=now(),
                received_at=now(),
            )

    def test_calibration_id_and_version_form_one_scope(self) -> None:
        unknown_mass = Observed[Mass](Availability.UNKNOWN, now(), now())
        with self.assertRaisesRegex(ValueError, "calibration_scope_invalid"):
            WeightReading(
                sensor_id=EntityId.new(),
                associated_spool_id=None,
                gross_mass=unknown_mass,
                tare_mass=unknown_mass,
                net_mass=unknown_mass,
                stable=Observed[bool](Availability.UNKNOWN, now(), now()),
                interval_start=now(),
                interval_end=now(),
                observed_at=now(),
                received_at=now(),
                calibration_id=EntityId.new(),
            )
