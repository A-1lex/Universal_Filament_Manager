"""Calculated proposals are keyed by file material, independently of tools."""

import unittest

from ufm.application.calculated_finalization import (
    FinalizationRejected,
    _materials_by_logical_index,
)
from ufm.domain.entities import PrintJobMaterial
from ufm.domain.value_objects import EntityId, UtcDateTime


def material(logical: int | None, tool: int) -> PrintJobMaterial:
    now, device_id = UtcDateTime.now(), EntityId.new()
    return PrintJobMaterial(
        id=EntityId.new(),
        device_id=device_id,
        created_at=now,
        updated_at=now,
        revision=1,
        print_job_id=EntityId.new(),
        channel_key=f"channel-{logical}-{tool}",
        tool_index=tool,
        logical_material_index=logical,
    )


class CalculatedMaterialMappingTests(unittest.TestCase):
    def test_multiple_logical_materials_can_share_one_physical_tool(self) -> None:
        first, second = material(0, 0), material(5, 0)
        result = _materials_by_logical_index([first, second], {0, 5})
        self.assertEqual(result, {0: first, 5: second})

    def test_single_legacy_row_can_bind_only_single_slice_material(self) -> None:
        row = material(None, 0)
        self.assertEqual(_materials_by_logical_index([row], {5}), {5: row})
        with self.assertRaisesRegex(FinalizationRejected, "mapping_required"):
            _materials_by_logical_index([row], {0, 5})

    def test_partial_or_duplicate_logical_mapping_is_rejected(self) -> None:
        with self.assertRaisesRegex(FinalizationRejected, "mapping_incomplete"):
            _materials_by_logical_index([material(0, 0), material(None, 0)], {0, 5})
        with self.assertRaisesRegex(FinalizationRejected, "mapping_conflict"):
            _materials_by_logical_index([material(5, 0), material(5, 1)], {5})
        with self.assertRaisesRegex(FinalizationRejected, "mapping_conflict"):
            _materials_by_logical_index([material(0, 0)], {5})


if __name__ == "__main__":
    unittest.main()
