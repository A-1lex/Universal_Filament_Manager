"""Produce auditable UI candidates from local sources, not a parity claim.

Literal controls and click bindings cannot prove runtime visibility or actions
injected by React/Refine. Manual review remains required for every candidate.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "spoolman": Path("D:/Filament_Manager/localization/spoolman/client/src"),
    "haspelsync-downloaded": Path("D:/Filament_Manager/localization/haspelsync/public"),
    "haspelsync-own": ROOT / "linked-stack/haspelsync/public",
}
TAGS = re.compile(
    r"<(?:button|input|select|dialog|Button|Input|Select|Modal|Popconfirm|Tabs|Checkbox|"
    r"Switch|DatePicker|InputNumber|Form\.Item|CreateButton|EditButton|ShowButton|"
    r"DeleteButton|CloneButton|SaveButton|ListButton|RefreshButton|ExportButton|"
    r"List|Create|Edit|Show|Route)(?=[\s/>.])[^>]*>", re.DOTALL,
)
CLICKS = re.compile(r"[^\r\n]*(?:addEventListener\([\"']click[\"']|\.onclick\s*=)[^\r\n]*")


def main() -> None:
    rows = []
    source_files = []
    for project, root in SOURCES.items():
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".tsx", ".js", ".html"}:
                continue
            relative = path.relative_to(root).as_posix()
            content = path.read_text("utf-8-sig")
            source_files.append({"project": project, "file": relative,
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            for kind, pattern in (("literal-control", TAGS), ("click-binding", CLICKS)):
                for match in pattern.finditer(content):
                    line = content.count("\n", 0, match.start()) + 1
                    snippet = " ".join(match.group().split())
                    rows.append({"project": project, "file": relative, "line": line,
                                 "kind": kind, "snippet": snippet[:600],
                                 "review": "needs-semantic-review"})
    rows.sort(key=lambda item: (str(item["project"]), str(item["file"]), int(item["line"]), str(item["kind"])))
    output = ROOT / "docs/LEGACY_UI_CANDIDATES.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["project", "file", "line", "kind", "snippet", "review"])
        writer.writeheader()
        writer.writerows(rows)
    manifest = {"format": 1, "roots": {key: str(value) for key, value in SOURCES.items()},
                "source_files": source_files, "candidates": len(rows),
                "per_project": dict(Counter(str(row["project"]) for row in rows)),
                "limitations": ["Lexical candidates may include comments and hidden controls.",
                                "Dynamically/framework-generated controls may be absent.",
                                "Downloaded source is not necessarily latest upstream.",
                                "This file does not prove any native UI parity."]}
    (ROOT / "docs/LEGACY_UI_SOURCE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"source_files": len(source_files), "candidates": len(rows),
                      "per_project": manifest["per_project"]}))


if __name__ == "__main__":
    main()
