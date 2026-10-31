"""Immutable verified-file facts shared across parser and application ports."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class FilamentFact:
    filament_id: int
    logical_material: int
    used_g: str
    mass_mg: int
    used_m: Decimal | None
    tray_info_idx: str | None
    color: str | None
    type: str | None
    mass_provenance: str = "slice_info.used_g:decimal_g_to_mg:ROUND_HALF_UP"


@dataclass(frozen=True)
class LayerFilamentFact:
    logical_materials: tuple[int, ...]
    layer_ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class VerifiedSliceFacts:
    parser_version: str
    file_sha256: str
    plate: int
    metadata_sha256: str
    gcode_sha256: str
    filaments: tuple[FilamentFact, ...]
    layer_filaments: tuple[LayerFilamentFact, ...]
    metadata: tuple[tuple[str, str], ...]
    normalized_xml: str
    gcode_bytes: bytes
    includes_purge: None = None
    quantity: str = "estimate"
