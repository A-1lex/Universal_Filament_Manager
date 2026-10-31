"""Read-only E03 integration spike against an independent Decimal/XML reference.

This reference covers XML full/range-based estimates only, not a production
Python port, G-code extrusion, network operations or stock finalization.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "linked-stack/haspelsync/test/fixtures"


def reference(xml: str, layer: int | None) -> dict[str, Decimal]:
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("unsupported_xml")
    document = ET.fromstring(xml)
    plate = document.find("plate")
    if plate is None or len(document.findall("plate")) != 1:
        raise ValueError("ambiguous_plate")
    ranges: dict[int, list[tuple[int, int]]] = {}
    total_layers = 0
    for item in plate.findall(".//layer_filament_list"):
        pairs = [tuple(map(int, part.split())) for part in item.attrib.get("layer_ranges", "").split(",") if part.strip()]
        indices = list(map(int, item.attrib.get("filament_list", "").split()))
        if not indices:
            continue
        for start, end in pairs:
            if not 0 <= start <= end <= 1000000:
                raise ValueError("invalid_range")
            total_layers = max(total_layers, end)
        for index in indices:
            ranges.setdefault(index, []).extend(pairs)
    result: dict[str, Decimal] = {}
    for filament in plate.findall("filament"):
        values = filament.attrib
        mass = Decimal(values["used_g"])
        if not mass.is_finite() or not 0 <= mass <= 10000:
            raise ValueError("invalid_mass")
        tray = values.get("tray_info_idx")
        if not tray:
            continue
        color = values.get("color", "").lstrip("#").upper()[:6]
        key = f"{tray}|{color}"
        proportion = Decimal(1)
        if layer is not None:
            pairs = sorted(ranges.get(int(values["id"]) - 1, []))
            merged: list[list[int]] = []
            for start, end in pairs:
                if merged and start <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            if merged:
                total = sum(end - start + 1 for start, end in merged)
                done = sum(max(0, min(layer, end) - start + 1) for start, end in merged)
                proportion = Decimal(done) / Decimal(total)
            else:
                proportion = min(Decimal(1), Decimal(layer + 1) / Decimal(total_layers + 1)) if total_layers else Decimal(0)
        result[key] = result.get(key, Decimal(0)) + mass * proportion
    return {key: value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for key, value in result.items()}


def worker(payload: dict[str, object], node: str, isolation: Path) -> tuple[int, dict[str, object]]:
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}}
    environment.update({"NODE_TEST_CONTEXT": "ufm-spike", "DATA_DIR": str(isolation / "data"),
                        "LOG_DIR": str(isolation / "logs")})
    process = subprocess.run([node, str(Path(__file__).with_name("calculate.mjs"))],
                             input=json.dumps(payload).encode(), capture_output=True,
                             timeout=5, cwd=isolation, env=environment, check=False)
    return process.returncode, json.loads(process.stdout)


def normalized(entries: dict[str, dict[str, object]]) -> dict[str, Decimal]:
    result = {}
    for entry in entries.values():
        color = str(entry["color"]).lstrip("#").upper()[:6]
        result[f'{entry["tray_info_idx"]}|{color}'] = Decimal(str(entry["grams"]))
    return result


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node required for developer experiment only")
    run = ROOT / ".runtime/haspel-worker-spike" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, exist_ok=False)
    checks = []
    for fixture in sorted(FIXTURES.glob("*.config")):
        xml = fixture.read_text("utf-8-sig")
        for layer in (None, -1, 10, 1000000):
            payload = {"v": 1, "op": "calculate", "request_id": "fixture",
                       "xml": xml, "up_to_layer": layer}
            code, response = worker(payload, node, run)
            expected = reference(xml, layer)
            actual = normalized(response["data"]["full" if layer is None else "partial"]) if response.get("ok") else None
            checks.append({"fixture": fixture.name, "layer": layer,
                           "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                           "passed": code == 0 and actual == expected,
                           "expected_g": {key: str(value) for key, value in expected.items()},
                           "actual_g": None if actual is None else {key: str(value) for key, value in actual.items()}})
    valid = (FIXTURES / "four_colours.config").read_text("utf-8-sig")
    for label, patch in (("version", {"v": 2}), ("operation", {"op": "debit"}),
                         ("layer", {"up_to_layer": -2}),
                         ("entity", {"xml": '<!DOCTYPE config [<!ENTITY x "bad">]><config/>'}),
                         ("empty", {"xml": "<config/>"}),
                         ("large", {"xml": "x" * (512 * 1024)}),
                         ("negative", {"xml": re.sub(r'used_g="[^"]+"', 'used_g="-1"', valid, count=1)})):
        payload = {"v": 1, "op": "calculate", "request_id": "reject",
                   "xml": valid, "up_to_layer": None, **patch}
        code, response = worker(payload, node, run)
        checks.append({"rejection": label, "passed": code == 2 and response.get("ok") is False})
    result = {"format": 1, "checks": checks, "passed": sum(item["passed"] for item in checks),
              "failed": sum(not item["passed"] for item in checks),
              "node": subprocess.check_output([node, "--version"], text=True).strip(),
              "limitations": ["XML full/range partial only; no G-code extrusion, ZIP or network.",
                              "Developer spike only; not bundled, not a stock writer.",
                              "Legacy aggregation/rounding are comparison semantics, not new ledger policy."]}
    (run / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"run": str(run), "passed": result["passed"], "failed": result["failed"]}))
    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
