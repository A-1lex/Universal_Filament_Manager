"""Strict offline Marlin linear-E subset; lengths are estimates, never stock."""

import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

VERSION = "marlin-linear-e-preflight-v1"
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
class ExtrusionReport:
    parser_version: str
    file_sha256: str
    dialect: Literal["marlin-linear-v1"]
    buckets: tuple[ExtrusionBucket, ...]
    quantity: Literal["estimate"] = "estimate"
    includes_purge: None = None


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
    data: bytes, *, expected_sha256: str, dialect: Literal["marlin-linear-v1"],
) -> ExtrusionReport:
    if dialect != "marlin-linear-v1":
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


def inspect_gcode_file_for_local_review(path: str | Path) -> ExtrusionReport:
    """Review an explicitly selected standalone file using its exact bounded bytes."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError:
        raise GcodeRejected("gcode.file_unreadable") from None
    digest = hashlib.sha256(data).hexdigest()
    return inspect_extrusion(data, expected_sha256=digest, dialect="marlin-linear-v1")
