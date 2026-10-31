"""Synthetic Spoolman v1 wire examples; no downloaded personal inventory."""

import json
import unittest
from decimal import Decimal

from ufm.integrations.spoolman.preview import PreviewRejected, preview_spools


def spool(spool_id: int = 1, remaining: object = 500.125) -> dict[str, object]:
    return {
        "id": spool_id,
        "filament": {"id": 2, "name": "Black", "material": "PLA",
                     "vendor": {"name": "Example"}},
        "remaining_weight": remaining,
        "used_weight": 499.875,
        "spool_weight": 140,
        "archived": False,
        "location": "Shelf",
    }


class SpoolmanPreviewTests(unittest.TestCase):
    def test_exact_remaining_not_used_or_gross_mass(self) -> None:
        payload = json.dumps([spool()]).encode()
        result = preview_spools(payload, source_instance="local-inventory")
        item = result.spools[0]
        self.assertEqual(item.estimated_remaining.milligrams, 500125)
        self.assertEqual(item.name, "Black")
        self.assertEqual(item.vendor, "Example")
        self.assertEqual(item.source_key, ("local-inventory", 1))
        self.assertEqual(len(result.source_fingerprint), 64)
        self.assertEqual(result.warnings, ("spoolman.preview_only",))

    def test_unknown_and_zero_are_distinct_and_never_inferred(self) -> None:
        items = [spool(1, None), spool(2, 0), spool(3)]
        del items[2]["remaining_weight"]
        result = preview_spools(json.dumps(items).encode(), source_instance="local")
        self.assertIsNone(result.spools[0].estimated_remaining)
        self.assertEqual(result.spools[1].estimated_remaining.milligrams, 0)
        self.assertIsNone(result.spools[2].estimated_remaining)

    def test_decimal_json_is_not_converted_through_float(self) -> None:
        payload = b'[{"id":1,"filament":{"id":2},"archived":true,"remaining_weight":0.001}]'
        result = preview_spools(payload, source_instance="local")
        self.assertEqual(result.spools[0].estimated_remaining.grams, Decimal("0.001"))
        self.assertTrue(result.spools[0].archived)

    def test_duplicate_ids_and_duplicate_json_keys_reject_entire_preview(self) -> None:
        payloads = [json.dumps([spool(), spool()]).encode(),
                    b'[{"id":1,"id":2,"filament":{"id":2},"archived":false}]']
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(PreviewRejected):
                preview_spools(payload, source_instance="local")

    def test_invalid_mass_and_metadata_fail_closed(self) -> None:
        for quantity in (-1, True, "12", 0.0001, float("nan"), float("inf"), 1e100):
            with self.subTest(quantity=quantity), self.assertRaises(PreviewRejected):
                preview_spools(json.dumps([spool(remaining=quantity)]).encode(),
                               source_instance="local")
        for field, value in (("id", True), ("id", 0), ("archived", "false"),
                             ("location", "x" * 501), ("filament", None)):
            item = spool()
            item[field] = value
            with self.subTest(field=field), self.assertRaises(PreviewRejected):
                preview_spools(json.dumps([item]).encode(), source_instance="local")

    def test_limits_encoding_shape_and_instance_are_checked(self) -> None:
        for payload in (b"\xff", b"{}", b"[null]", b"[", b"[" * 40 + b"]" * 40):
            with self.subTest(payload=payload), self.assertRaises(PreviewRejected):
                preview_spools(payload, source_instance="local")
        with self.assertRaises(PreviewRejected):
            preview_spools(b"[]", source_instance="local", max_input_bytes=1)
        with self.assertRaises(PreviewRejected):
            preview_spools(json.dumps([spool(1), spool(2)]).encode(),
                           source_instance="local", max_spools=1)
        with self.assertRaises(PreviewRejected):
            preview_spools(b"[]", source_instance="https://user:secret@host")

    def test_extra_payload_is_not_retained_and_errors_are_sanitized(self) -> None:
        item = spool()
        item["extra"] = {"token": "do-not-retain"}
        result = preview_spools(json.dumps([item]).encode(), source_instance="local")
        self.assertNotIn("do-not-retain", repr(result))
        with self.assertRaises(PreviewRejected) as error:
            preview_spools(b'{"token":"do-not-retain"}', source_instance="local")
        self.assertEqual(str(error.exception), "spoolman.preview_rejected")

