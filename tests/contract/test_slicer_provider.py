import inspect
import unittest

from ufm.application.dto import (
    ParseLimits,
    PlateEstimate,
    ProjectInput,
    SlicerProject,
    ToolMaterialEstimate,
)
from ufm.application.ports import ParseRejected, SlicerProvider
from ufm.domain.value_objects import Mass


class SlicerProviderContractTests(unittest.TestCase):
    def test_parser_port_is_synchronous_and_has_no_inventory_operation(self) -> None:
        self.assertFalse(inspect.iscoroutinefunction(SlicerProvider.parse_project))
        self.assertFalse(hasattr(SlicerProvider, "consume"))
        self.assertFalse(hasattr(SlicerProvider, "save_spool"))

    def test_project_input_hides_content_from_repr(self) -> None:
        source = ProjectInput("plate.3mf", b"private-project-content")
        self.assertNotIn("private-project-content", repr(source))

    def test_limits_reject_unbounded_or_non_positive_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            ParseLimits(1, 100_001, 1, 1, 1, 1)
        with self.assertRaisesRegex(ValueError, "invalid"):
            ParseLimits(0, 1, 1, 1, 1, 1)

    def test_result_uses_exact_mass_and_explicit_purge_scope(self) -> None:
        estimate = ToolMaterialEstimate(0, "PLA", Mass.from_grams("12.345"), True)
        project = SlicerProject(
            source_fingerprint="sha256:abc",
            project_reference=None,
            plates=(PlateEstimate(0, "plate", (estimate,)),),
            warnings=(),
            parser_version="contract-test",
        )
        self.assertEqual(project.mass_unit, "mg")
        self.assertEqual(project.plates[0].materials[0].mass.milligrams, 12_345)
        self.assertTrue(project.plates[0].materials[0].includes_purge)

    def test_parse_error_has_stable_sanitized_code(self) -> None:
        self.assertEqual(str(ParseRejected()), "slicer.parse_rejected")
