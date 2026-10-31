import unittest
from decimal import Decimal
from xml.etree import ElementTree

from ufm.domain.value_objects import EntityId
from ufm.integrations.catalog import load_material_catalog
from ufm.integrations.qr import parse_spool_label, spool_label_svg, spool_label_text


class ReusedComponentsTests(unittest.TestCase):
    def test_pinned_offline_catalog_preserves_names_and_unknown_temperatures(self) -> None:
        catalog = load_material_catalog()
        self.assertEqual(len(catalog), 34)
        by_name = {item.name: item for item in catalog}
        self.assertEqual(by_name["PLA"].density_g_cm3, Decimal("1.24"))
        self.assertEqual(by_name["PLA"].extruder_temp_c, 210)
        self.assertIsNone(by_name["ABS"].extruder_temp_c)
        self.assertIn("Flexible (TPU)", by_name)
        self.assertEqual(by_name["Flexible (TPE 88A)"].density_g_cm3, Decimal("0.89"))

    def test_label_roundtrip_uses_only_canonical_internal_uuid(self) -> None:
        identity = EntityId.parse("01234567-89ab-4cde-8123-0123456789ab")
        text = spool_label_text(identity)
        self.assertEqual(text, "UFM:SPOOL:01234567-89ab-4cde-8123-0123456789ab")
        self.assertEqual(parse_spool_label(text), identity)
        with self.assertRaises(ValueError):
            spool_label_text(EntityId("invalid"))  # type: ignore[arg-type]

    def test_invalid_labels_cannot_be_urls_commands_or_external_ids(self) -> None:
        for text in ("https://host/spool/1", "UFM:SPOOL:1", "ufm:spool:1", "UFM:SPOOL:",
                     "UFM:SPOOL:01234567-89AB-4CDE-8123-0123456789AB",
                     "UFM:SPOOL:01234567-89ab-4cde-8123-0123456789ab\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_spool_label(text)

    def test_svg_is_bounded_standalone_and_deterministic(self) -> None:
        identity = EntityId.parse("01234567-89ab-4cde-8123-0123456789ab")
        svg = spool_label_svg(identity)
        root = ElementTree.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(svg, spool_label_svg(identity))
        self.assertLess(len(svg), 100_000)
        self.assertNotIn(b"script", svg)
        self.assertNotIn(b"href=", svg)
        for scale in (0, True, 101):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                spool_label_svg(identity, scale=scale)
