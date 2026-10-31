"""Explicit dialect, exact lengths, retraction debt and conservative rejection."""

import hashlib
import unittest
from decimal import Decimal
from unittest.mock import patch

from ufm.integrations.gcode_extrusion import GcodeRejected, inspect_extrusion


def inspect(text):
    data = text.encode()
    return inspect_extrusion(data, expected_sha256=hashlib.sha256(data).hexdigest(), dialect="marlin-linear-v1")


class GcodeExtrusionTests(unittest.TestCase):
    def test_relative_retractions_do_not_count_recovery_twice(self):
        report = inspect("G21\nT0\nM83\nG1 E10\nG1 E-2\n;LAYER:0\nG1 E1\nG1 E3\n")
        self.assertEqual([(b.tool, b.layer, b.fresh_mm) for b in report.buckets],
                         [(0, None, Decimal(10)), (0, 0, Decimal(2))])
        self.assertEqual(report.quantity, "estimate")
        self.assertIsNone(report.includes_purge)

    def test_absolute_reset_is_not_filament_motion(self):
        report = inspect("G21\nT0\nM82\nG92 E0\nG1E10\nG1 E8\nG92 E0\nG1 E3\n")
        self.assertEqual(report.buckets[0].fresh_mm, Decimal(11))

    def test_g90_clears_relative_override_and_tools_remain_separate(self):
        report = inspect("G21\nT0\nM83\nG92 E0\nG1 E2\nG90\nG1 E3\nT1\nG92 E0\nG1 E4\n")
        self.assertEqual([(b.tool, b.fresh_mm) for b in report.buckets], [(0, Decimal(3)), (1, Decimal(4))])

    def test_unknown_modes_and_ambiguous_initialization_reject(self):
        for body in ("G20", "M200 D1.75", "M221 S110", "G10", "G11", "M600", "M900 K0.1",
                     "T1000", "G1 E1 E2", "G1 E1e3", "G1 E1*33", "G92.1",
                     "G1 E0.0000001", ";LAYER:2\n;LAYER:1"):
            with self.subTest(body=body), self.assertRaises(GcodeRejected):
                inspect("G21\nT0\nM83\n" + body)
        for text in ("G1 E1", "G21\nT0\nG1 E1", "G21\nT0\nM82\nG1 E1",
                     "G21\nT0\nM82\nG92 E0\nT1\nG1 E1"):
            with self.subTest(text=text), self.assertRaises(GcodeRejected):
                inspect(text)

    def test_hash_encoding_and_resource_limits_reject(self):
        with self.assertRaisesRegex(GcodeRejected, "hash_mismatch"):
            inspect_extrusion(b"G21", expected_sha256="a" * 64, dialect="marlin-linear-v1")
        for setting, value, text in (("MAX_BYTES", 2, "G21"), ("MAX_LINES", 1, "G21\nT0"),
                                     ("MAX_LINE_BYTES", 2, "G21"),
                                     ("MAX_BUCKETS", 1, "G21\nT0\nM83\nG1 E1\n;LAYER:0\nG1 E1")):
            with self.subTest(setting=setting), patch("ufm.integrations.gcode_extrusion." + setting, value):
                with self.assertRaises(GcodeRejected):
                    inspect(text)

    def test_decimal_exactness_and_non_extrusion_commands(self):
        report = inspect("G21\nT0\nM83\nM104 S200\nG1 X20 F1200\nG1 E.1\nG2 X1 I2 E.2\n")
        self.assertEqual(report.buckets[0].fresh_mm, Decimal("0.3"))

    def test_long_metadata_comment_has_separate_bound_and_no_motion(self):
        report = inspect(";" + "G1 E999 " * 900 + "\nG21\nT0\nM83\nG1 E1\n")
        self.assertEqual(report.buckets[0].fresh_mm, Decimal(1))
        for line in (";" + "x" * 16384, "G1 X1" + " " * 4096):
            with self.subTest(size=len(line)), self.assertRaisesRegex(GcodeRejected, "line_invalid"):
                inspect("G21\nT0\nM83\n" + line)
