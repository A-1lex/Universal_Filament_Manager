"""Strict offline G-code extrusion subsets; lengths and masses are estimates, never stock."""

import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal

VERSION = "marlin-linear-e-preflight-v1"
BAMBU_VERSION = "bambu-e-preflight-v1"
MASS_METHOD = "gcode-cylinder-mass-v1"
Dialect = Literal["marlin-linear-v1", "bambu-v1"]
MAX_BYTES = 64 * 1024 * 1024
MAX_LINES = 2_000_000
MAX_LINE_BYTES = 4096
MAX_COMMENT_BYTES = 16384
MAX_BUCKETS = 65536
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_PARAMETER = re.compile(rf"\s*([A-Z])({_NUMBER})")
_NO_EXTRUSION = {"G4", "M104", "M109", "M140", "M190", "M106", "M107", "M400"}


class GcodeRejected(ValueError):
    """Stable errors contain no source line or path."""


@dataclass(frozen=True)
class ExtrusionBucket:
    tool: int
    layer: int | None
    fresh_mm: Decimal


@dataclass(frozen=True)
class DeclaredVendorExtrusion:
    """Length a vendor command declares for firmware-side extrusion (not a G1 E move)."""

    kind: Literal["load_line", "flush"]
    tool: int
    layer: int | None
    length_mm: Decimal


@dataclass(frozen=True)
class SlicerFilament:
    tool: int
    filament_id: int
    length_mm: Decimal
    weight_g: Decimal
    diameter_mm: Decimal
    density_g_cm3: Decimal


@dataclass(frozen=True)
class SlicerHeader:
    generator: str
    layer_count: int
    filaments: tuple[SlicerFilament, ...]


@dataclass(frozen=True)
class ExtrusionReport:
    parser_version: str
    file_sha256: str
    dialect: Dialect
    buckets: tuple[ExtrusionBucket, ...]
    quantity: Literal["estimate"] = "estimate"
    includes_purge: None = None
    conditional_buckets: tuple[ExtrusionBucket, ...] = ()
    declared_vendor: tuple[DeclaredVendorExtrusion, ...] = ()
    slicer: SlicerHeader | None = None


@dataclass(frozen=True)
class ToolMassEstimate:
    tool: int
    filament_id: int
    modelled_mm: Decimal
    load_line_mm: Decimal
    flush_share_mm: Decimal
    conditional_mm: Decimal
    estimated_mm: Decimal
    slicer_mm: Decimal
    diameter_mm: Decimal
    density_g_cm3: Decimal
    estimated_mass_mg: int
    slicer_mass_mg: int


@dataclass(frozen=True)
class GcodeMassEstimate:
    method: str
    parser_version: str
    file_sha256: str
    relative_tolerance: Decimal
    absolute_tolerance_mm: Decimal
    flush_mm: Decimal
    tools: tuple[ToolMassEstimate, ...]
    consistent: bool
    quantity: Literal["estimate"] = "estimate"


def _parameters(text: str) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    offset = 0
    while offset < len(text):
        match = _PARAMETER.match(text, offset)
        if match is None or len(match[2]) > 24 or match[1] in result:
            raise GcodeRejected("gcode.parameters_invalid")
        value = Decimal(match[2])
        exponent = value.as_tuple().exponent
        if not value.is_finite() or not isinstance(exponent, int) or abs(value) > 1_000_000_000 or exponent < -6:
            raise GcodeRejected("gcode.number_out_of_range")
        result[match[1]] = value
        offset = match.end()
    return result


def inspect_extrusion(
    data: bytes, *, expected_sha256: str, dialect: Dialect,
) -> ExtrusionReport:
    if dialect not in ("marlin-linear-v1", "bambu-v1"):
        raise GcodeRejected("gcode.dialect_unsupported")
    if type(data) is not bytes or not data or len(data) > MAX_BYTES:
        raise GcodeRejected("gcode.size_invalid")
    digest = hashlib.sha256(data).hexdigest()
    if type(expected_sha256) is not str or digest != expected_sha256:
        raise GcodeRejected("gcode.hash_mismatch")
    # Bound line count before allocating decoded lines. No code is executed.
    if data.count(b"\n") + 1 > MAX_LINES:
        raise GcodeRejected("gcode.too_many_lines")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise GcodeRejected("gcode.encoding_invalid") from None
    if dialect == "bambu-v1":
        return _inspect_bambu(text, digest)
    mode: bool | None = None  # True means relative E.
    millimetres = False
    tool: int | None = None
    position: Decimal | None = None
    layer: int | None = None
    debts: dict[int, Decimal] = defaultdict(Decimal)
    buckets: dict[tuple[int, int | None], Decimal] = defaultdict(Decimal)
    for source_line in io.StringIO(text):
        raw = source_line.rstrip("\r\n")
        comment_only = raw.lstrip().startswith(";")
        limit = MAX_COMMENT_BYTES if comment_only else MAX_LINE_BYTES
        if len(raw.encode()) > limit or any(ord(char) < 32 and char != "\t" for char in raw):
            raise GcodeRejected("gcode.line_invalid")
        marker = re.fullmatch(r"\s*;LAYER:([0-9]{1,7})\s*", raw)
        if marker is not None:
            next_layer = int(marker[1])
            if next_layer > 1_000_000 or (layer is not None and next_layer <= layer):
                raise GcodeRejected("gcode.layer_invalid")
            layer = next_layer
            continue
        code = raw.partition(";")[0].strip().upper()
        if not code:
            continue
        head = re.fullmatch(r"([GMT])([0-9]{1,4})(.*)", code)
        if head is None:
            raise GcodeRejected("gcode.syntax_unsupported")
        command = head[1] + str(int(head[2]))
        params = _parameters(head[3].strip())
        if head[1] == "T":
            index = int(head[2])
            if params or index > 15:
                raise GcodeRejected("gcode.tool_unsupported")
            tool, position = index, None
        elif command in {"M82", "M83", "G90", "G91", "G21"}:
            if params:
                raise GcodeRejected("gcode.mode_invalid")
            if command == "G21":
                millimetres = True
            else:
                mode = command in {"M83", "G91"}
        elif command == "G92":
            if not params or not params.keys() <= {"X", "Y", "Z", "E"}:
                raise GcodeRejected("gcode.reset_unsupported")
            if "E" in params:
                if not millimetres or tool is None:
                    raise GcodeRejected("gcode.initialization_required")
                position = params["E"]
        elif command in {"G0", "G1", "G2", "G3"}:
            if not params.keys() <= {"X", "Y", "Z", "E", "F", "I", "J", "K", "R"}:
                raise GcodeRejected("gcode.motion_unsupported")
            if "E" not in params:
                continue
            if not millimetres or tool is None or mode is None or (not mode and position is None):
                raise GcodeRejected("gcode.initialization_required")
            if mode:
                delta = params["E"]
            else:
                assert position is not None
                delta = params["E"] - position
            position = (None if position is None else position + delta) if mode else params["E"]
            if delta < 0:
                debts[tool] -= delta
            else:
                recovered = min(debts[tool], delta)
                debts[tool] -= recovered
                fresh = delta - recovered
                if fresh:
                    buckets[(tool, layer)] += fresh
                    if len(buckets) > MAX_BUCKETS or buckets[(tool, layer)] > 1_000_000_000_000:
                        raise GcodeRejected("gcode.complexity_exceeded")
        elif command in _NO_EXTRUSION:
            if "E" in params:
                raise GcodeRejected("gcode.extrusion_unsupported")
        else:
            # Includes firmware retract, volumetric/flow modes, macros, binary,
            # checksummed streams and vendor extensions; no silent guessing.
            raise GcodeRejected("gcode.command_unsupported")
    if tool is None or mode is None or not millimetres:
        raise GcodeRejected("gcode.initialization_required")
    return ExtrusionReport(VERSION, digest, dialect, tuple(
        ExtrusionBucket(key[0], key[1], value) for key, value in sorted(
            buckets.items(), key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1]))))


# Bambu Studio output, evidenced by P2S fixtures. Opaque commands are skipped
# only because they carry no filament motion; anything else is rejected.
_BAMBU_OPAQUE = frozenset({
    "G4", "G17", "G28", "G29", "G29.1", "G29.2", "G29.99", "G150", "G150.1", "G150.2",
    "G150.3", "G380", "G389", "M17", "M18", "M73", "M73.2", "M104", "M106", "M107",
    "M109", "M140", "M142", "M145", "M190", "M191", "M201", "M201.2", "M203", "M204",
    "M205", "M211", "M220", "M400", "M500", "M620.6", "M620.11", "M620.15", "M621",
    "M622.1", "M628", "M629", "M630", "M960", "M970.2", "M970.3", "M971", "M972",
    "M974", "M975", "M981", "M982.2", "M983.1", "M983.3", "M983.4", "M985.1", "M991",
    "M993", "M1002", "M1003", "M1004", "M1006", "M1010", "M1010.1", "M1015.3",
    "M1015.4", "M1031",
})
# For these the letter E is a limit, tone or tuning value, not filament motion.
_BAMBU_E_NOT_MOTION = frozenset({"M201", "M203", "M205", "M1006", "M985.1"})
_LOOSE_E = re.compile(rf"(?:^|\s)E({_NUMBER})(?=\s|$)")
_LOOSE_L = re.compile(rf"(?:^|\s)L({_NUMBER})(?=\s|$)")
_PI = Decimal("3.14159265358979323846264338327950288")


def _loose_number(pattern: re.Pattern[str], text: str) -> Decimal | None:
    found = pattern.findall(text)
    if len(found) > 1:
        raise GcodeRejected("gcode.parameters_invalid")
    if not found or len(found[0]) > 24:
        return None if not found else _invalid_number()
    value = Decimal(found[0])
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or abs(value) > 1_000_000_000 or exponent < -6:
        raise GcodeRejected("gcode.number_out_of_range")
    return value


def _invalid_number() -> Decimal:
    raise GcodeRejected("gcode.number_out_of_range")


def _header_list(value: str, separator: str = ",") -> tuple[Decimal, ...]:
    items = value.split(separator)
    if not 1 <= len(items) <= 64:
        raise GcodeRejected("gcode.header_invalid")
    try:
        result = tuple(Decimal(item.strip()) for item in items)
    except ArithmeticError:
        raise GcodeRejected("gcode.header_invalid") from None
    if any(not item.is_finite() or item < 0 or item > 1_000_000_000 for item in result):
        raise GcodeRejected("gcode.header_invalid")
    return result


def _bambu_header(text: str) -> SlicerHeader:
    lines = text[:MAX_COMMENT_BYTES * 4].splitlines()
    if not lines or lines[0].strip() != "; HEADER_BLOCK_START":
        raise GcodeRejected("gcode.header_invalid")
    fields: dict[str, str] = {}
    generator: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "; HEADER_BLOCK_END":
            break
        if generator is None and re.fullmatch(r"; BambuStudio [0-9][0-9.]{0,31}", stripped):
            generator = stripped[2:]
            continue
        key, separator, value = stripped.removeprefix("; ").partition(":")
        if separator and key in fields:
            raise GcodeRejected("gcode.header_invalid")
        if separator:
            fields[key.strip()] = value.strip()
    else:
        raise GcodeRejected("gcode.header_invalid")
    required = ("total layer number", "total filament length [mm]",
                "total filament weight [g]", "filament_density", "filament_diameter", "filament")
    if generator is None or any(key not in fields for key in required):
        raise GcodeRejected("gcode.header_invalid")
    layers = _header_list(fields["total layer number"])
    lengths = _header_list(fields["total filament length [mm]"])
    weights = _header_list(fields["total filament weight [g]"])
    densities = _header_list(fields["filament_density"])
    diameters = _header_list(fields["filament_diameter"])
    ids = _header_list(fields["filament"])
    if (len(layers) != 1 or layers[0] != int(layers[0]) or not len(ids) == len(lengths) == len(weights)
            or any(item != int(item) or not 1 <= item <= min(len(densities), len(diameters), 16)
                   for item in ids) or len(set(ids)) != len(ids)):
        raise GcodeRejected("gcode.header_invalid")
    filaments = []
    for filament, length, weight in zip(ids, lengths, weights, strict=True):
        index = int(filament) - 1
        if not densities[index] or not diameters[index]:
            raise GcodeRejected("gcode.header_invalid")
        filaments.append(SlicerFilament(index, index + 1, length, weight,
                                        diameters[index], densities[index]))
    return SlicerHeader(generator, int(layers[0]), tuple(filaments))


def _inspect_bambu(text: str, digest: str) -> ExtrusionReport:
    header = _bambu_header(text)
    e_relative: bool | None = None
    axes_relative: bool | None = None
    millimetres = True  # G20 is rejected, so inch units can never be selected.
    tool: int | None = None
    pending_tool: int | None = None
    position: Decimal | None = None
    layer: int | None = None
    layers_seen = 0
    conditional: tuple[bool | None, bool | None, bool, Decimal | None] | None = None
    debts: dict[int, Decimal] = defaultdict(Decimal)
    conditional_debts: dict[int, Decimal] = defaultdict(Decimal)
    buckets: dict[tuple[int, int | None], Decimal] = defaultdict(Decimal)
    conditional_buckets: dict[tuple[int, int | None], Decimal] = defaultdict(Decimal)
    declared: list[DeclaredVendorExtrusion] = []
    for source_line in io.StringIO(text):
        raw = source_line.rstrip("\r\n")
        comment_only = raw.lstrip().startswith(";")
        limit = MAX_COMMENT_BYTES if comment_only else MAX_LINE_BYTES
        if len(raw.encode()) > limit or any(ord(char) < 32 and char != "\t" for char in raw):
            raise GcodeRejected("gcode.line_invalid")
        if re.fullmatch(r"\s*; CHANGE_LAYER\s*", raw):
            if conditional is not None:
                raise GcodeRejected("gcode.conditional_unsupported")
            layer = 0 if layer is None else layer + 1
            layers_seen += 1
            if layers_seen > 1_000_000:
                raise GcodeRejected("gcode.layer_invalid")
            continue
        code = raw.partition(";")[0].strip().upper()
        if not code:
            continue
        if re.fullmatch(r"SYNC(?:\s+[RT][0-9]{1,6})+", code):
            continue
        head = re.fullmatch(r"([GMT])([0-9]{1,5})(?:\.([0-9]{1,2}))?(\s.*|)", code)
        if head is None:
            raise GcodeRejected("gcode.syntax_unsupported")
        command = head[1] + str(int(head[2])) + ("" if head[3] is None else "." + str(int(head[3])))
        rest = head[4].strip()
        target, target_debts = ((buckets, debts) if conditional is None
                                else (conditional_buckets, conditional_debts))
        if head[1] == "T":
            index = int(head[2])
            if rest or head[3] is not None or conditional is not None or (index > 15 and index != 65535):
                raise GcodeRejected("gcode.tool_unsupported")
            tool, position = (None if index == 65535 else index), None
        elif command in {"M82", "M83", "G90", "G91", "G21"}:
            if rest:
                raise GcodeRejected("gcode.mode_invalid")
            if command == "G21":
                millimetres = True
            elif command in {"M82", "M83"}:
                e_relative = command == "M83"
            else:
                axes_relative = command == "G91"
        elif command == "G92":
            params = _parameters(rest)
            if not params or not params.keys() <= {"X", "Y", "Z", "E"}:
                raise GcodeRejected("gcode.reset_unsupported")
            if "E" in params:
                if not millimetres or tool is None:
                    raise GcodeRejected("gcode.initialization_required")
                position = params["E"]
        elif command in {"G0", "G1", "G2", "G3"}:
            params = _parameters(rest)
            allowed = {"X", "Y", "Z", "E", "F", "I", "J", "K", "R"}
            if command in {"G2", "G3"}:
                allowed.add("P")
            if not params.keys() <= allowed:
                raise GcodeRejected("gcode.motion_unsupported")
            if "E" not in params:
                continue
            # Matches the slicer's own processor: E is relative under M83 or G91.
            relative = None if e_relative is None or axes_relative is None else (
                e_relative or axes_relative)
            if not millimetres or tool is None or relative is None or (
                    not relative and position is None):
                raise GcodeRejected("gcode.initialization_required")
            if relative:
                delta = params["E"]
                position = None if position is None else position + delta
            else:
                assert position is not None
                delta = params["E"] - position
                position = params["E"]
            if delta < 0:
                target_debts[tool] -= delta
            else:
                recovered = min(target_debts[tool], delta)
                target_debts[tool] -= recovered
                fresh = delta - recovered
                if fresh:
                    target[(tool, layer)] += fresh
                    if (len(buckets) + len(conditional_buckets) > MAX_BUCKETS
                            or target[(tool, layer)] > 1_000_000_000_000):
                        raise GcodeRejected("gcode.complexity_exceeded")
        elif command == "M622":
            if conditional is not None or not re.fullmatch(r"J[0-9]{1,3}", rest):
                raise GcodeRejected("gcode.conditional_unsupported")
            # Printer-side condition: extrusion inside may or may not run.
            conditional = (e_relative, axes_relative, millimetres, position)
            conditional_debts.clear()
        elif command == "M623":
            if conditional is None or rest:
                raise GcodeRejected("gcode.conditional_unsupported")
            before = conditional
            conditional = None
            e_relative = e_relative if e_relative == before[0] else None
            axes_relative = axes_relative if axes_relative == before[1] else None
            millimetres = millimetres and before[2]
            position = position if position == before[3] else None
        elif command == "M620":
            if rest == "M":
                continue
            selected = re.fullmatch(r"S([0-9]{1,5})A?", rest)
            if selected is None or conditional is not None:
                raise GcodeRejected("gcode.tool_unsupported")
            index = int(selected[1])
            if index > 15 and index != 65535:
                raise GcodeRejected("gcode.tool_unsupported")
            pending_tool = None if index == 65535 else index
        elif command == "M620.10":
            if conditional is not None or not re.fullmatch(r"(?:\s*[A-Z][+-]?[0-9.]*)+", rest):
                raise GcodeRejected("gcode.parameters_invalid")
            flush = _loose_number(_LOOSE_L, rest)
            # A1 configures the incoming filament; its L is the firmware flush length.
            if flush is not None and re.search(r"(?:^|\s)A1(?=\s|$)", rest):
                if pending_tool is None or flush < 0:
                    raise GcodeRejected("gcode.flush_unsupported")
                if flush:
                    declared.append(DeclaredVendorExtrusion("flush", pending_tool, layer, flush))
        elif command == "G130":
            load = _loose_number(_LOOSE_E, rest)
            if conditional is not None or tool is None or load is None or load < 0:
                raise GcodeRejected("gcode.extrusion_unsupported")
            if load:
                declared.append(DeclaredVendorExtrusion("load_line", tool, layer, load))
        elif command == "M221":
            if rest != "S100":
                raise GcodeRejected("gcode.command_unsupported")
        elif command in _BAMBU_OPAQUE:
            if command not in _BAMBU_E_NOT_MOTION and _loose_number(_LOOSE_E, rest):
                raise GcodeRejected("gcode.extrusion_unsupported")
        else:
            raise GcodeRejected("gcode.command_unsupported")
    if conditional is not None or not millimetres or layers_seen != header.layer_count:
        raise GcodeRejected("gcode.initialization_required" if conditional is None and
                            layers_seen == header.layer_count else "gcode.structure_invalid")

    def ordered(values: dict[tuple[int, int | None], Decimal]) -> tuple[ExtrusionBucket, ...]:
        return tuple(ExtrusionBucket(key[0], key[1], value) for key, value in sorted(
            values.items(), key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1])))

    return ExtrusionReport(BAMBU_VERSION, digest, "bambu-v1", ordered(buckets),
                           conditional_buckets=ordered(conditional_buckets),
                           declared_vendor=tuple(declared), slicer=header)


def _mass_mg(length_mm: Decimal, diameter_mm: Decimal, density_g_cm3: Decimal) -> int:
    # mm^3 multiplied by g/cm^3 is mg.
    radius = diameter_mm / 2
    return int((_PI * radius * radius * length_mm * density_g_cm3).quantize(
        Decimal(1), rounding=ROUND_HALF_UP))


def estimate_mass(
    report: ExtrusionReport, *, relative_tolerance: Decimal = Decimal("0.01"),
    absolute_tolerance_mm: Decimal = Decimal(5),
) -> GcodeMassEstimate:
    """Convert parsed extrusion to per-tool mass and cross-check the slicer header.

    Per tool: modelled G0-G3 extrusion, plus the vendor load line, plus a share of
    firmware flush. The flush split follows the slicer's per-filament remainder
    over modelled motion, falling back to the incoming tool. The slicer totals
    exclude the load line. Conditional (printer-decided) extrusion is reported but
    excluded. ``consistent`` is false when motion and header disagree beyond tolerance.
    """
    if report.slicer is None:
        raise GcodeRejected("gcode.material_unknown")
    if relative_tolerance < 0 or absolute_tolerance_mm < 0:
        raise GcodeRejected("gcode.tolerance_invalid")
    modelled: dict[int, Decimal] = defaultdict(Decimal)
    conditional: dict[int, Decimal] = defaultdict(Decimal)
    load: dict[int, Decimal] = defaultdict(Decimal)
    incoming_flush: dict[int, Decimal] = defaultdict(Decimal)
    for bucket in report.buckets:
        modelled[bucket.tool] += bucket.fresh_mm
    for bucket in report.conditional_buckets:
        conditional[bucket.tool] += bucket.fresh_mm
    for item in report.declared_vendor:
        (load if item.kind == "load_line" else incoming_flush)[item.tool] += item.length_mm
    filaments = report.slicer.filaments
    flush = sum(incoming_flush.values(), Decimal(0))
    remainders = {f.tool: max(Decimal(0), f.length_mm - modelled[f.tool])
                  for f in filaments}
    remainder_total = sum(remainders.values(), Decimal(0))
    tools = []
    for f in filaments:
        share = (flush * remainders[f.tool] / remainder_total if flush and remainder_total
                 else incoming_flush[f.tool]).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        estimated = modelled[f.tool] + load[f.tool] + share
        tools.append(ToolMassEstimate(
            f.tool, f.filament_id, modelled[f.tool], load[f.tool], share,
            conditional[f.tool], estimated, f.length_mm, f.diameter_mm,
            f.density_g_cm3, _mass_mg(estimated, f.diameter_mm, f.density_g_cm3),
            int((f.weight_g * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
        ))

    def close(expected: Decimal, actual: Decimal) -> bool:
        return abs(expected - actual) <= max(absolute_tolerance_mm, expected * relative_tolerance)

    slicer_total = sum((item.length_mm for item in filaments), Decimal(0))
    modelled_total = sum(modelled.values(), Decimal(0))
    known = {item.tool for item in filaments}
    consistent = (
        not (set(modelled) | set(load) | set(incoming_flush) | set(conditional)) - known
        and close(slicer_total, modelled_total + flush)
        and all(close(item.slicer_mm, item.modelled_mm + item.flush_share_mm) for item in tools))
    return GcodeMassEstimate(
        MASS_METHOD, report.parser_version, report.file_sha256, relative_tolerance,
        absolute_tolerance_mm, flush, tuple(tools), bool(consistent))


def inspect_gcode_file_for_local_review(path: str | Path) -> ExtrusionReport:
    """Review an explicitly selected standalone file using its exact bounded bytes."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError:
        raise GcodeRejected("gcode.file_unreadable") from None
    digest = hashlib.sha256(data).hexdigest()
    head = data[:4096]
    bambu = head.startswith(b"; HEADER_BLOCK_START") and b"\n; BambuStudio " in head
    return inspect_extrusion(data, expected_sha256=digest,
                             dialect="bambu-v1" if bambu else "marlin-linear-v1")
