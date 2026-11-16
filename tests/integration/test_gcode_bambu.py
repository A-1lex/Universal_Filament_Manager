"""Bambu Studio G-code: strict vendor subset, slicer cross-check and mass estimate."""

import hashlib
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from ufm.integrations.gcode_extrusion import (
    GcodeRejected,
    estimate_mass,
    inspect_extrusion,
    inspect_gcode_file_for_local_review,
)

FIXTURES = Path(__file__).parents[2] / "linked-stack" / "haspelsync" / "test" / "fixtures"
HEADER = """; HEADER_BLOCK_START
; BambuStudio 02.08.02.61
; total layer number: {layers}
; total filament length [mm] : {lengths}
; total filament weight [g] : {weights}
; filament_density: 1.24,1.32
; filament_diameter: 1.75,1.75
; filament: {filaments}
; HEADER_BLOCK_END
"""


def fixture(name):
    with zipfile.ZipFile(FIXTURES / name) as archive:
        return archive.read("Metadata/plate_1.gcode")


def inspect(data):
    return inspect_extrusion(data, expected_sha256=hashlib.sha256(data).hexdigest(),
                             dialect="bambu-v1")


def synthetic(body, *, layers=1, lengths="10", weights="0.03", filaments="1"):
    header = HEADER.format(layers=layers, lengths=lengths, weights=weights, filaments=filaments)
    return inspect((header + body).encode())


START = "M620 S0A\nT0\nM621 S0A\nG90\nM83\n; CHANGE_LAYER\n"


class BambuFixtureTests(unittest.TestCase):
    def test_real_p2s_files_parse_and_agree_with_slicer(self):
        expected = {
            "p2s_cube.gcode.3mf": {3: (1972, 1940)},
            "p2s_refill_cube.gcode.3mf": {2: (20121, 20090)},
            "p2s_two_colours.gcode.3mf": {0: (5907, 5870), 1: (684, 680)},
        }
        for name, tools in expected.items():
            with self.subTest(name=name):
                report = inspect(fixture(name))
                self.assertEqual(report.dialect, "bambu-v1")
                self.assertEqual(report.parser_version, "bambu-e-preflight-v1")
                self.assertEqual(report.quantity, "estimate")
                self.assertIsNotNone(report.slicer)
                self.assertTrue(all(bucket.layer is not None for bucket in report.buckets))
                estimate = estimate_mass(report)
                self.assertTrue(estimate.consistent)
                self.assertEqual(estimate.method, "gcode-cylinder-mass-v1")
                self.assertEqual({item.tool: (item.estimated_mass_mg, item.slicer_mass_mg)
                                  for item in estimate.tools}, tools)

    def test_two_colour_flush_is_declared_and_split_by_slicer_remainder(self):
        report = inspect(fixture("p2s_two_colours.gcode.3mf"))
        kinds = [(item.kind, item.tool, item.length_mm) for item in report.declared_vendor]
        self.assertEqual(kinds, [("load_line", 0, Decimal(12)), ("flush", 1, Decimal("78.9928"))])
        estimate = estimate_mass(report)
        self.assertEqual(estimate.flush_mm, Decimal("78.9928"))
        self.assertEqual(sum(item.flush_share_mm for item in estimate.tools), Decimal("78.9928"))
        self.assertEqual(report.slicer.layer_count, 8)
        self.assertEqual(max(bucket.layer for bucket in report.buckets), 7)

    def test_local_review_selects_bambu_only_from_header_signature(self):
        path = FIXTURES / "p2s_cube.gcode.3mf"
        with zipfile.ZipFile(path) as archive:
            data = archive.read("Metadata/plate_1.gcode")
        target = Path(self.id().replace(".", "_") + ".gcode")
        try:
            target.write_bytes(data)
            self.assertEqual(inspect_gcode_file_for_local_review(target).dialect, "bambu-v1")
            with self.assertRaises(GcodeRejected):
                inspect_extrusion(data, expected_sha256=hashlib.sha256(data).hexdigest(),
                                  dialect="marlin-linear-v1")
        finally:
            target.unlink(missing_ok=True)


class BambuSubsetTests(unittest.TestCase):
    def test_conditional_extrusion_is_separate_and_excluded_from_mass(self):
        report = synthetic(START + "G1 X1 E10\nM622 J1\nG1 E5\nM623\n")
        self.assertEqual([(b.tool, b.layer, b.fresh_mm) for b in report.buckets],
                         [(0, 0, Decimal(10))])
        self.assertEqual([b.fresh_mm for b in report.conditional_buckets], [Decimal(5)])
        estimate = estimate_mass(report)
        self.assertTrue(estimate.consistent)
        self.assertEqual(estimate.tools[0].conditional_mm, Decimal(5))
        # pi * 0.875^2 * 10 * 1.24 = 29.825... mg, ROUND_HALF_UP
        self.assertEqual(estimate.tools[0].estimated_mass_mg, 30)

    def test_mode_changed_inside_conditional_becomes_unknown(self):
        with self.assertRaisesRegex(GcodeRejected, "initialization_required"):
            synthetic("M620 S0A\nT0\nM621 S0A\nG90\n; CHANGE_LAYER\nM622 J1\nM83\nM623\nG1 E1\n")
        report = synthetic(START + "M622 J1\nM83\nM623\nG1 E10\n")
        self.assertEqual(report.buckets[0].fresh_mm, Decimal(10))

    def test_g90_does_not_clear_m83_like_the_slicer_processor(self):
        report = synthetic(START + "G91\nG1 Z1\nG90\nG1 E4\nG1 E6\n")
        self.assertEqual(report.buckets[0].fresh_mm, Decimal(10))

    def test_unknown_or_extruding_vendor_commands_reject(self):
        for line in ("M600", "M221 S90", "G20", "M620.11 P1 E-2", "M1002 E5", "G10",
                     "M620.1 X1", "M622 J1\nT1\nM623", "M622 J1\nM622 J1\nM623\nM623",
                     "M623", "M622 J1\n; CHANGE_LAYER\nM623", "T16", "FOO", "G1 E1 W2"):
            with self.subTest(line=line), self.assertRaises(GcodeRejected):
                synthetic(START + line + "\n", layers=2 if "CHANGE_LAYER" in line else 1)
        report = synthetic(START + "M201 X1 E5000\nM1006 A1 E53\nM620.11 P0 E0\nSYNC T5\nG1 E10\n")
        self.assertEqual(report.buckets[0].fresh_mm, Decimal(10))

    def test_header_and_layer_count_are_required(self):
        with self.assertRaisesRegex(GcodeRejected, "header_invalid"):
            inspect(b"M83\nG1 E1\n")
        with self.assertRaisesRegex(GcodeRejected, "header_invalid"):
            synthetic(START, lengths="1,2")
        with self.assertRaisesRegex(GcodeRejected, "structure_invalid"):
            synthetic(START + "; CHANGE_LAYER\nG1 E10\n")

    def test_tool_absent_from_header_or_large_mismatch_is_inconsistent(self):
        stray = synthetic(START + "G1 E10\nM620 S1A\nT1\nM621 S1A\nG1 E1\n")
        self.assertFalse(estimate_mass(stray).consistent)
        drift = synthetic(START + "G1 E100\n")
        self.assertFalse(estimate_mass(drift).consistent)

    def test_flush_falls_back_to_incoming_tool_without_slicer_remainder(self):
        body = (START + "G1 E10\nM620 S1A\nM620.10 A0 L20 H0.4\nM620.10 A1 L20 H0.4\n"
                "T1\nM621 S1A\nG1 E10\n")
        report = synthetic(body, lengths="10,10", weights="0.03,0.03", filaments="1,2")
        estimate = estimate_mass(report)
        self.assertEqual([item.flush_share_mm for item in estimate.tools],
                         [Decimal(0), Decimal(20)])
        self.assertFalse(estimate.consistent)

    def test_marlin_report_has_no_material_facts(self):
        data = b"G21\nT0\nM83\nG1 E1\n"
        report = inspect_extrusion(data, expected_sha256=hashlib.sha256(data).hexdigest(),
                                   dialect="marlin-linear-v1")
        with self.assertRaisesRegex(GcodeRejected, "material_unknown"):
            estimate_mass(report)


if __name__ == "__main__":
    unittest.main()
