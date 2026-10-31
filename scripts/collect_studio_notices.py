"""Collect installed runtime dependency metadata and notices for release review."""

import argparse
import json
import shutil
import sys
import tomllib
from collections.abc import Iterable
from importlib.metadata import distribution
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _observed_license_metadata(
    license_expression: str | None,
    license_name: str | None,
    classifiers: Iterable[str],
) -> str:
    declared = license_expression or license_name
    if declared:
        return declared
    observed_classifiers = sorted({
        value.removeprefix("License :: ")
        for value in classifiers
        if value.startswith("License :: ")
    })
    if observed_classifiers:
        return "Classifier metadata only: " + " | ".join(observed_classifiers)
    return "not specified"


def collect(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pending = [("universal-filament-manager", frozenset({"desktop"}))]
    for extra, requirements in (("", project.get("dependencies", ())),
                                ("desktop", project.get("optional-dependencies", {}).get("desktop", ()))):
        environment: dict[str, str] = {
            key: str(value) for key, value in default_environment().items()
        }
        environment["extra"] = extra
        for raw in requirements:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate(environment):
                pending.append((requirement.name, frozenset(requirement.extras)))
    visited: set[tuple[str, frozenset[str]]] = set()
    packages: dict[str, dict[str, str | int | list[str]]] = {}
    while pending:
        name, extras = pending.pop()
        normalized = canonicalize_name(name)
        key = normalized, extras
        if key in visited:
            continue
        visited.add(key)
        installed = distribution(name)
        folder = destination / normalized
        folder.mkdir(exist_ok=True)
        notice_files: list[str] = []
        for item in installed.files or ():
            if any(part == ".." for part in item.parts):
                continue
            if any(marker in item.name.lower() for marker in ("license", "copying", "notice")):
                source = Path(str(installed.locate_file(item)))
                if source.is_file():
                    output = folder / str(item).replace("/", "__").replace("\\", "__")
                    shutil.copy2(source, output)
                    notice_files.append(output.name)
        metadata = installed.read_text("METADATA")
        if metadata:
            (folder / "METADATA.txt").write_text(metadata, encoding="utf-8")
        packages[normalized] = {
            "name": installed.metadata["Name"] or name, "version": installed.version,
            "license_metadata": _observed_license_metadata(
                installed.metadata.get("License-Expression"),
                installed.metadata.get("License"),
                installed.metadata.get_all("Classifier", []),
            ),
            "notice_files_copied": len(notice_files),
            "notice_files": sorted(notice_files),
        }
        for raw in installed.requires or ():
            dependency = Requirement(raw)
            if dependency.marker is None or any(
                dependency.marker.evaluate({"extra": extra}) for extra in extras | {""}
            ):
                pending.append((dependency.name, frozenset(dependency.extras)))
    # The bootloader is a build dependency but its notice belongs with the EXE.
    bootloader = distribution("pyinstaller")
    for item in bootloader.files or ():
        if item.name.lower() in {"copying.txt", "copying"}:
            source = Path(str(bootloader.locate_file(item)))
            if source.is_file():
                shutil.copy2(source, destination / "PyInstaller-COPYING.txt")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")
    (destination / "runtime-dependencies.json").write_text(
        json.dumps({
            "purpose": (
                "Installed dependency inventory seeded from pyproject runtime and desktop "
                "requirements; not a complete SBOM or license approval"
            ),
            "source_project": project["name"],
            "source_version": project["version"],
            "included_extra": "desktop",
            "python": sys.version.split()[0],
            "packages": sorted(packages.values(), key=lambda item: str(item["name"])),
        }, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"Collected runtime metadata for {len(packages)} distributions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    collect(parser.parse_args().destination)
