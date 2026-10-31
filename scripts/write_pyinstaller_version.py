"""Generate PyInstaller's Windows version resource from pyproject.toml."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def _version_resource(version: str) -> str:
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[.-][0-9A-Za-z.-]+)?", version)
    if match is None:
        raise ValueError("project.version must start with a three-part numeric version")
    major, minor, patch = (int(part) for part in match.groups())
    if any(part > 65_535 for part in (major, minor, patch)):
        raise ValueError("Windows version components must fit in 16 bits")
    version_tuple = f"({major}, {minor}, {patch}, 0)"
    escaped = version.replace("\\", "\\\\").replace("'", "\\'")
    return f'''# UTF-8 generated from pyproject.toml; do not edit by hand.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Universal Filament Manager'),
        StringStruct('FileDescription', 'UFM Studio'),
        StringStruct('FileVersion', '{escaped}'),
        StringStruct('InternalName', 'UFM Studio'),
        StringStruct('OriginalFilename', 'UFM Studio.exe'),
        StringStruct('ProductName', 'UFM Studio'),
        StringStruct('ProductVersion', '{escaped}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))
    version = project.get("project", {}).get("version")
    if type(version) is not str:
        parser.error("pyproject.toml has no string project.version")
    try:
        content = _version_resource(version)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8", newline="\n")
    print(f"Generated Windows version resource for UFM Studio {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
