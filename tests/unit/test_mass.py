import unittest
from decimal import Decimal

from ufm.domain.value_objects import MAX_ABS_MILLIGRAMS, Mass, MassPrecisionError


class MassTests(unittest.TestCase):
    def test_grams_roundtrip_exactly_through_integer_milligrams(self) -> None:
        mass = Mass.from_grams(Decimal("123.456"))
        self.assertEqual(mass.milligrams, 123_456)
        self.assertEqual(mass.grams, Decimal("123.456"))

    def test_arithmetic_preserves_negative_physical_evidence(self) -> None:
        result = Mass.from_grams("1") - Mass.from_grams("1.250")
        self.assertEqual(result, Mass(-250))

    def test_fractional_milligrams_are_rejected_instead_of_rounded(self) -> None:
        with self.assertRaises(MassPrecisionError):
            Mass.from_grams("0.0001")

    def test_float_boolean_and_non_finite_inputs_are_rejected(self) -> None:
        for value in (0.1, True, "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                Mass.from_grams(value)  # type: ignore[arg-type]

    def test_unknown_is_none_and_never_equal_to_zero(self) -> None:
        unknown: Mass | None = None
        self.assertIsNone(unknown)
        self.assertNotEqual(unknown, Mass(0))

    def test_schema_safe_integer_range_is_enforced(self) -> None:
        self.assertEqual(Mass(MAX_ABS_MILLIGRAMS).milligrams, MAX_ABS_MILLIGRAMS)
        for value in (MAX_ABS_MILLIGRAMS + 1, -MAX_ABS_MILLIGRAMS - 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Mass(value)
