"""Immutable provenance must not admit ambiguous or non-finite JSON values."""

import unittest

from ufm.domain.value_objects.json_object import json_object


class JsonObjectTests(unittest.TestCase):
    def test_object_values_preserved(self) -> None:
        self.assertEqual(json_object('{"mass_mg":12345,"coverage":null,"steps":[1,2.5]}'),
                         {"mass_mg": 12345, "coverage": None, "steps": [1, 2.5]})

    def test_ambiguous_and_nonfinite_provenance_rejected(self) -> None:
        for text in ('[]', 'null', '{"mass_mg":1,"mass_mg":2}', '{"x":{"a":1,"a":2}}',
                     '{"x":NaN}', '{"x":Infinity}', '{"x":[1e10000]}', 'bad'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'json_object.invalid'):
                json_object(text)

    def test_bounded_size_and_nesting(self) -> None:
        for text in ('{"x":"' + 'a' * 65536 + '"}', '{"x":' + '[' * 2000 + '0' + ']' * 2000 + '}'):
            with self.subTest(size=len(text)), self.assertRaises(ValueError):
                json_object(text)
