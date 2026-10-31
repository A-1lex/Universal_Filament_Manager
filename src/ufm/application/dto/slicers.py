"""Bounded, vendor-neutral slicer input and parse results."""

from dataclasses import dataclass, field

from ufm.domain.value_objects import Mass


def _text(value: str, code: str, *, limit: int = 500) -> None:
    if type(value) is not str or not value or len(value) > limit:
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class ProjectInput:
    source_name: str
    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.source_name, "project_input.name_invalid")
        if type(self.content) is not bytes:
            raise TypeError("project_input.content_invalid")


@dataclass(frozen=True, slots=True)
class ParseLimits:
    max_input_bytes: int
    max_entries: int
    max_uncompressed_bytes: int
    max_xml_bytes: int
    max_nesting_depth: int
    timeout_ms: int

    def __post_init__(self) -> None:
        values = (
            self.max_input_bytes,
            self.max_entries,
            self.max_uncompressed_bytes,
            self.max_xml_bytes,
            self.max_nesting_depth,
            self.timeout_ms,
        )
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("parse_limits.invalid")
        if self.max_entries > 100_000 or self.max_nesting_depth > 1_000:
            raise ValueError("parse_limits.unsafe")


@dataclass(frozen=True, slots=True)
class ToolMaterialEstimate:
    tool_index: int
    material_key: str | None
    mass: Mass
    includes_purge: bool

    def __post_init__(self) -> None:
        if type(self.tool_index) is not int or self.tool_index < 0:
            raise ValueError("slicer_estimate.tool_index_invalid")
        if self.material_key is not None:
            _text(self.material_key, "slicer_estimate.material_key_invalid")
        if self.mass.milligrams < 0:
            raise ValueError("slicer_estimate.mass_invalid")
        if type(self.includes_purge) is not bool:
            raise TypeError("slicer_estimate.purge_invalid")


@dataclass(frozen=True, slots=True)
class PlateEstimate:
    plate_index: int
    name: str | None
    materials: tuple[ToolMaterialEstimate, ...]

    def __post_init__(self) -> None:
        if type(self.plate_index) is not int or self.plate_index < 0:
            raise ValueError("slicer_plate.index_invalid")
        if self.name is not None:
            _text(self.name, "slicer_plate.name_invalid")
        if type(self.materials) is not tuple or len(self.materials) > 256:
            raise ValueError("slicer_plate.materials_invalid")
        tools = [estimate.tool_index for estimate in self.materials]
        if len(tools) != len(set(tools)):
            raise ValueError("slicer_plate.duplicate_tool")


@dataclass(frozen=True, slots=True)
class SlicerProject:
    source_fingerprint: str
    project_reference: str | None
    plates: tuple[PlateEstimate, ...]
    warnings: tuple[str, ...]
    parser_version: str
    mass_unit: str = "mg"

    def __post_init__(self) -> None:
        _text(self.source_fingerprint, "slicer_project.fingerprint_invalid")
        _text(self.parser_version, "slicer_project.parser_version_invalid")
        if self.project_reference is not None:
            _text(self.project_reference, "slicer_project.reference_invalid")
        if type(self.plates) is not tuple or len(self.plates) > 10_000:
            raise ValueError("slicer_project.plates_invalid")
        indexes = [plate.plate_index for plate in self.plates]
        if len(indexes) != len(set(indexes)):
            raise ValueError("slicer_project.duplicate_plate")
        if type(self.warnings) is not tuple or len(self.warnings) > 1_000:
            raise ValueError("slicer_project.warnings_invalid")
        for warning in self.warnings:
            _text(warning, "slicer_project.warning_invalid", limit=2_000)
        if self.mass_unit != "mg":
            raise ValueError("slicer_project.mass_unit_invalid")
