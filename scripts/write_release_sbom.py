"""Write a CycloneDX inventory for a verified Windows folder candidate.

The result is deliberately marked incomplete: this records the verified file
tree, packaged Python distributions, selected bundled Node/Qt/Haspel components
and lock-derived Python dependency edges, but does not claim complete native
component attribution or legal approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
import uuid
from pathlib import Path
from urllib.parse import quote

from write_studio_manifest import verify_manifest

_SCHEMA = "https://cyclonedx.org/schema/bom-1.7.schema.json"
_MANIFEST_NAME = "build-manifest.json"
_RUNTIME_INVENTORY = "third-party/runtime-dependencies.json"
_NODE_EXE = "_internal/runtime/node.exe"
_NODE_LICENSE = "_internal/third-party/node/LICENSE"
_HASPEL_ROOT = "_internal/ufm/integrations/haspel_engine/"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _existing_ancestor_has_reparse_point(path: Path) -> bool:
    current: Path | None = path
    while current is not None:
        if current.exists() or current.is_symlink():
            if current.is_symlink() or current.is_junction():
                return True
        current = current.parent if current.parent != current else None
    return False


def _manifest_record(by_path: dict[str, dict[str, object]], relative: str) -> dict[str, object]:
    record = by_path.get(relative)
    if record is None:
        raise ValueError("sbom.required_component_file_missing")
    return record


def build_sbom(
    bundle: Path, output: Path, node_version: str, qt_version: str
) -> dict[str, object]:
    root = bundle.resolve(strict=True)
    requested_destination = output.absolute()
    if not root.is_dir():
        raise ValueError("sbom.bundle_directory_required")
    if _existing_ancestor_has_reparse_point(requested_destination):
        raise ValueError("sbom.output_reparse_point_forbidden")
    destination = requested_destination.resolve()
    if destination == root or root in destination.parents:
        raise ValueError("sbom.output_must_be_outside_bundle")

    file_count = verify_manifest(root)
    manifest_path = root / _MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory_path = root / _RUNTIME_INVENTORY
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    project_root = Path(__file__).resolve().parents[1]
    lock = tomllib.loads((project_root / "uv.lock").read_text(encoding="utf-8"))
    records = manifest["files"]
    by_path = {item["path"]: item for item in records}
    inventory_record = by_path.get(_RUNTIME_INVENTORY)
    if inventory_record is None or _sha256(inventory_path) != inventory_record["sha256"]:
        raise ValueError("sbom.runtime_inventory_not_in_verified_manifest")
    if manifest.get("file_count") != file_count:
        raise ValueError("sbom.manifest_count_mismatch")

    if not re.fullmatch(r"\d+\.\d+\.\d+", node_version):
        raise ValueError("sbom.node_version_invalid")
    if not re.fullmatch(r"\d+\.\d+\.\d+", qt_version):
        raise ValueError("sbom.qt_version_invalid")
    node_record = _manifest_record(by_path, _NODE_EXE)
    node_license_record = _manifest_record(by_path, _NODE_LICENSE)
    qt_paths = sorted(
        relative for relative in by_path
        if relative.startswith("_internal/PySide6/")
        and relative.lower().endswith(".dll")
        and (Path(relative).name.startswith("Qt6") or "/plugins/" in relative)
    )
    required_qt_paths = {
        "_internal/PySide6/Qt6Core.dll",
        "_internal/PySide6/Qt6Gui.dll",
        "_internal/PySide6/Qt6Widgets.dll",
    }
    if not required_qt_paths.issubset(qt_paths):
        raise ValueError("sbom.required_qt_runtime_files_missing")
    haspel_paths = {
        "calculation": _HASPEL_ROOT + "calculation.js",
        "shared": _HASPEL_ROOT + "shared.js",
        "license": _HASPEL_ROOT + "LICENSE",
        "provenance": _HASPEL_ROOT + "PROVENANCE.md",
    }
    haspel_records = {
        key: _manifest_record(by_path, relative)
        for key, relative in haspel_paths.items()
    }
    haspel_provenance = (root / haspel_paths["provenance"]).read_text(encoding="utf-8")
    haspel_version_match = re.search(r"package version `([^`]+)`", haspel_provenance)
    if haspel_version_match is None:
        raise ValueError("sbom.haspel_provenance_version_missing")
    haspel_version = haspel_version_match.group(1)

    project_name = inventory.get("source_project")
    project_version = inventory.get("source_version")
    if (not isinstance(project_name, str) or not isinstance(project_version, str)
            or project_version != manifest.get("version")):
        raise ValueError("sbom.project_identity_invalid")
    packages = inventory.get("packages")
    if not isinstance(packages, list):
        raise ValueError("sbom.package_inventory_invalid")
    included_extra = inventory.get("included_extra")
    if not isinstance(included_extra, str) or not included_extra:
        raise ValueError("sbom.included_extra_missing")

    app_ref = f"pkg:pypi/{quote(_package_name(project_name), safe='-')}@{quote(project_version, safe='.-')}"
    components: list[dict[str, object]] = []
    seen_packages: set[str] = set()
    package_refs: dict[str, str] = {}
    lock_records: dict[str, dict[str, object]] = {}
    app_record_found = False
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("sbom.package_record_invalid")
        name, version = package.get("name"), package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ValueError("sbom.package_identity_invalid")
        normalized = _package_name(name)
        ref = f"pkg:pypi/{quote(normalized, safe='-')}@{quote(version, safe='.-')}"
        if ref in seen_packages:
            raise ValueError("sbom.package_duplicate")
        seen_packages.add(ref)
        if normalized in package_refs:
            raise ValueError("sbom.package_name_ambiguous")
        package_refs[normalized] = ref
        locked = [
            item for item in lock.get("package", [])
            if _package_name(str(item.get("name", ""))) == normalized
            and item.get("version") == version
        ]
        if len(locked) != 1:
            raise ValueError("sbom.lock_package_missing_or_ambiguous")
        lock_records[normalized] = locked[0]
        if normalized == _package_name(project_name):
            app_record_found = version == project_version
            continue
        properties = [{
            "name": "ufm:observed-license-metadata",
            "value": str(package.get("license_metadata", "not specified")),
        }]
        notices = package.get("notice_files", [])
        if not isinstance(notices, list) or any(not isinstance(item, str) for item in notices):
            raise ValueError("sbom.notice_inventory_invalid")
        properties.extend({"name": "ufm:notice-file", "value": item} for item in notices)
        components.append({
            "type": "library",
            "bom-ref": ref,
            "name": name,
            "version": version,
            "purl": ref,
            "scope": "required",
            "properties": properties,
        })
    if not app_record_found:
        raise ValueError("sbom.application_package_not_in_inventory")

    root_lock = lock_records[_package_name(project_name)]
    root_dependencies = list(root_lock.get("dependencies", []))
    optional_dependencies = root_lock.get("optional-dependencies", {})
    selected_optional = optional_dependencies.get(included_extra)
    if not isinstance(selected_optional, list):
        raise ValueError("sbom.selected_extra_not_in_lock")
    root_dependencies.extend(selected_optional)

    def dependency_refs(records: list[object]) -> list[str]:
        refs: set[str] = set()
        for dependency in records:
            if not isinstance(dependency, dict) or not isinstance(dependency.get("name"), str):
                raise ValueError("sbom.lock_dependency_invalid")
            ref = package_refs.get(_package_name(dependency["name"]))
            if ref is not None:
                refs.add(ref)
        return sorted(refs)

    node_ref = f"pkg:generic/node.js@{quote(node_version, safe='.-')}"
    qt_ref = f"pkg:generic/qt@{quote(qt_version, safe='.-')}"
    haspel_ref = (
        "pkg:generic/haspelsync-calculation-resources@"
        + quote(haspel_version, safe='.-+')
    )
    node_file_ref = "urn:ufm:artifact-file:" + quote(_NODE_EXE, safe="/-._~")
    node_license_ref = "urn:ufm:artifact-file:" + quote(_NODE_LICENSE, safe="/-._~")
    qt_file_refs = {
        "urn:ufm:artifact-file:" + quote(relative, safe="/-._~")
        for relative in qt_paths
    }
    haspel_file_refs = {
        "urn:ufm:artifact-file:" + quote(relative, safe="/-._~")
        for relative in haspel_paths.values()
    }
    components.extend([
        {
            "type": "framework",
            "bom-ref": qt_ref,
            "name": "Qt",
            "version": qt_version,
            "purl": qt_ref,
            "scope": "required",
            "properties": [
                {"name": "ufm:version-source", "value": "shared PE ProductVersion across bundled Qt DLLs"},
                {"name": "ufm:payload-path-prefix", "value": "_internal/PySide6/"},
                {"name": "ufm:payload-file-count", "value": str(len(qt_paths))},
            ],
        },
        {
            "type": "framework",
            "bom-ref": node_ref,
            "name": "Node.js",
            "version": node_version,
            "purl": node_ref,
            "scope": "required",
            "hashes": [{"alg": "SHA-256", "content": node_record["sha256"]}],
            "properties": [
                {"name": "ufm:version-source", "value": "bundled PE ProductVersion"},
                {"name": "ufm:bundled-executable", "value": _NODE_EXE},
                {"name": "ufm:notice-file", "value": _NODE_LICENSE},
                {"name": "ufm:notice-file-sha256", "value": str(node_license_record["sha256"])},
            ],
        },
        {
            "type": "library",
            "bom-ref": haspel_ref,
            "name": "HaspelSync Calculation Resources (vendored subset)",
            "version": haspel_version,
            "purl": haspel_ref,
            "scope": "required",
            "properties": [
                {"name": "ufm:scope", "value": "calculation.js, shared.js and upstream LICENSE only"},
                {"name": "ufm:provenance-file", "value": haspel_paths["provenance"]},
                {"name": "ufm:license-file", "value": haspel_paths["license"]},
                {"name": "ufm:calculation-sha256", "value": str(haspel_records["calculation"]["sha256"])},
                {"name": "ufm:shared-sha256", "value": str(haspel_records["shared"]["sha256"])},
                {"name": "ufm:license-sha256", "value": str(haspel_records["license"]["sha256"])},
                {"name": "ufm:provenance-sha256", "value": str(haspel_records["provenance"]["sha256"])},
            ],
        },
    ])

    dependency_graph: list[dict[str, object]] = [{
        "ref": app_ref,
        "dependsOn": sorted(set(dependency_refs(root_dependencies)) | {node_ref, qt_ref, haspel_ref}),
    }]
    dependency_graph.extend([
        {"ref": node_ref, "dependsOn": sorted({node_file_ref, node_license_ref})},
        {"ref": qt_ref, "dependsOn": sorted(qt_file_refs)},
        {"ref": haspel_ref, "dependsOn": sorted(haspel_file_refs)},
    ])
    for name, ref in sorted(package_refs.items()):
        if name == _package_name(project_name):
            continue
        locked_dependencies = lock_records[name].get("dependencies", [])
        if not isinstance(locked_dependencies, list):
            raise ValueError("sbom.lock_dependency_list_invalid")
        dependency_graph.append({"ref": ref, "dependsOn": dependency_refs(locked_dependencies)})

    for record in records:
        relative = record.get("path")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if (not isinstance(relative, str) or not relative or not isinstance(digest, str)
                or _SHA256.fullmatch(digest) is None or type(size) is not int or size < 0):
            raise ValueError("sbom.manifest_record_invalid")
        components.append({
            "type": "file",
            "bom-ref": "urn:ufm:artifact-file:" + quote(relative, safe="/-._~"),
            "name": relative,
            "hashes": [{"alg": "SHA-256", "content": digest}],
            "properties": [{"name": "ufm:file-size-bytes", "value": str(size)}],
        })

    provenance = {
        "bundle_manifest_sha256": _sha256(manifest_path),
        "runtime_inventory_sha256": inventory_record["sha256"],
    }
    serial_material = json.dumps(provenance, sort_keys=True, separators=(",", ":"))
    serial = uuid.uuid5(uuid.NAMESPACE_URL, serial_material)
    timestamp = manifest.get("built_at_utc")
    if not isinstance(timestamp, str):
        raise ValueError("sbom.build_timestamp_missing")

    return {
        "$schema": _SCHEMA,
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "component": {
                "type": "application",
                "bom-ref": app_ref,
                "name": "UFM Studio",
                "version": project_version,
                "purl": app_ref,
                "properties": [
                    {"name": "ufm:sbom-completeness", "value": "incomplete"},
                    {"name": "ufm:inventory-scope", "value": (
                        "Verified bundle files and packaged Python distribution metadata; "
                        "Python dependency edges are read from uv.lock; bundled Node.js "
                        "Qt DLL payload and the minimal vendored Haspel calculation subset are identified; "
                        "other native binary attribution and full dependency completeness "
                        "are not established."
                    )},
                    {"name": "ufm:license-review", "value": (
                        "Observed package metadata only; applicable distribution terms "
                        "and legal approval remain unresolved."
                    )},
                    {"name": "ufm:bundle-manifest-sha256", "value": provenance[
                        "bundle_manifest_sha256"
                    ]},
                    {"name": "ufm:runtime-inventory-sha256", "value": provenance[
                        "runtime_inventory_sha256"
                    ]},
                    {"name": "ufm:verified-file-count", "value": str(file_count)},
                    {"name": "ufm:python-distribution-count", "value": str(len(packages))},
                    {"name": "ufm:dependency-source", "value": "uv.lock"},
                    {"name": "ufm:node-runtime-version", "value": node_version},
                    {"name": "ufm:qt-runtime-version", "value": qt_version},
                    {"name": "ufm:haspel-calculation-subset-version", "value": haspel_version},
                ],
            },
        },
        "components": components,
        "dependencies": dependency_graph,
        "compositions": [{"aggregate": "incomplete", "assemblies": [app_ref]}],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="manifest-verified Windows folder bundle")
    parser.add_argument("output", type=Path, help="CycloneDX 1.7 JSON path outside the bundle")
    parser.add_argument(
        "--node-version", required=True,
        help="Node.js PE ProductVersion read from the bundled node.exe",
    )
    parser.add_argument(
        "--qt-version", required=True,
        help="Shared three-part PE ProductVersion from bundled Qt DLLs",
    )
    args = parser.parse_args()
    bom = build_sbom(args.bundle, args.output, args.node_version, args.qt_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote incomplete CycloneDX inventory: {args.output} "
        f"({len(bom['components'])} components)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"SBOM generation failed: {error}", file=sys.stderr)
        raise SystemExit(2) from None
