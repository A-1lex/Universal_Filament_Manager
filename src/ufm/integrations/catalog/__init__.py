"""Offline suggestions from a pinned MIT SpoolmanDB dataset; never measured facts."""

import json
from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files

SOURCE_COMMIT = "8f1a99f9cda7a58ca3118d6bd28c707647caa3db"
SOURCE_URL = f"https://github.com/Donkie/SpoolmanDB/blob/{SOURCE_COMMIT}/materials.json"


@dataclass(frozen=True, slots=True)
class MaterialSuggestion:
    name: str
    density_g_cm3: Decimal
    extruder_temp_c: int | None
    bed_temp_c: int | None
    source_url: str = SOURCE_URL


def load_material_catalog() -> tuple[MaterialSuggestion, ...]:
    """Load bundled suggestions without network, DB writes or type-name coercion.

    Preserve upstream labels, including blends/custom names. Missing temperatures
    remain unknown. Density is a generic reference, not a calibrated spool property.
    """
    data = json.loads(files(__package__).joinpath("materials.json").read_text("utf-8"),
                      parse_float=Decimal)
    return tuple(MaterialSuggestion(
        name=row["material"], density_g_cm3=Decimal(row["density"]),
        extruder_temp_c=row.get("extruder_temp"), bed_temp_c=row.get("bed_temp"),
    ) for row in data)
