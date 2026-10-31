"""Real Node calculation behind verified-file and bounded process boundaries."""

import hashlib
import io
import shutil
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from ufm.integrations.calculation_worker import (
    CalculationWorkerTransport,
    WorkerScope,
    WorkerTransportRejected,
)
from ufm.integrations.haspel_calculation import FULL_POLICY, PARTIAL_POLICY, HaspelCalculator
from ufm.integrations.sliced_files import inspect_3mf_bytes

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[2]


def facts(*, ranges=True):  # type: ignore[no-untyped-def]
    xml = ('<config><plate><metadata key="index" value="1"/>'
           '<filament id="1" used_g="1.005" tray_info_idx="same" color="#FFFFFF"/>'
           '<filament id="6" used_g="2.345" tray_info_idx="same" color="#FFFFFF"/>'
           '<layer_filament_lists><layer_filament_list filament_list="0" layer_ranges="0 9"/>'
           '<layer_filament_list filament_list="5" layer_ranges="10 19"/>'
           '</layer_filament_lists></plate></config>')
    if not ranges:
        xml = xml[:xml.index('<layer_filament_lists>')] + '</plate></config>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("Metadata/slice_info.config", xml)
        archive.writestr("Metadata/plate_1.gcode", "M83\nT0\nG1 E1\n")
    data = output.getvalue()
    return inspect_3mf_bytes(data, plate=1, expected_sha256=hashlib.sha256(data).hexdigest())


@unittest.skipUnless(NODE, "Node developer runtime unavailable")
class HaspelCalculationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ufm-calculation-")
        self.addCleanup(self.temp.cleanup)
        assert NODE is not None
        self.calculator = HaspelCalculator(CalculationWorkerTransport(
            Path(NODE).resolve(), ROOT / "src/ufm/integrations/haspel_worker.mjs",
            Path(self.temp.name).resolve(), 5))
        self.scope = WorkerScope(uuid4(), "epoch-1", "request-1")
        self.context = dict(scope=self.scope, occurrence_key="run-1", evidence_id=uuid4(),
                            observed_at=datetime(2026, 10, 27, 12, tzinfo=UTC), sequence=1)

    async def test_full_preserves_mg_and_same_colour_sparse_logical_ids(self) -> None:
        result = await self.calculator.calculate(facts(), **self.context)
        self.assertEqual([(item.logical_material, item.mass_mg) for item in result.materials], [(0, 1005), (5, 2345)])
        self.assertEqual(result.policy_version, FULL_POLICY)
        self.assertEqual(result.label, "Розрахункова витрата")
        self.assertEqual(result.status, "needs_mapping")
        self.assertEqual(result.confidence_bp, 0)
        self.assertEqual(result.allocations, ())

    async def test_partial_uses_each_material_ranges_and_caps_rounding(self) -> None:
        for layer, expected in ((-1, [0, 0]), (4, [500, 0]), (19, [1005, 2345])):
            with self.subTest(layer=layer):
                result = await self.calculator.calculate(facts(), completed_layer=layer, **self.context)
                self.assertEqual([item.mass_mg for item in result.materials], expected)
                self.assertEqual(result.policy_version, PARTIAL_POLICY)
                self.assertTrue(result.partial)

    async def test_layer_bool_and_fraction_not_coerced(self) -> None:
        for layer in (True, 1.5, -2):
            with self.subTest(layer=layer), self.assertRaises(ValidationError):
                await self.calculator.calculate(facts(), completed_layer=layer, **self.context)

    async def test_missing_ranges_do_not_activate_global_progress_fallback(self) -> None:
        await self.calculator.calculate(facts(ranges=False), **self.context)
        with self.assertRaises(WorkerTransportRejected):
            await self.calculator.calculate(facts(ranges=False), completed_layer=4, **self.context)
