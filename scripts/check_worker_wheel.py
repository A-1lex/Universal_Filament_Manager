"""Offline worker-module wheel smoke outside the checkout, using installed deps.

This does not certify the native EXE or supply the unbundled Node engine.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

CHILD = r'''
import hashlib,importlib,json,sys
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
names=("ufm.application.calculated_finalization","ufm.application.receipt_ingestion",
       "ufm.application.dto.providers","ufm.integrations.printers.bambu_lan",
       "ufm.application.job_material_mapping",
       "ufm.application.mounted_material_mapping",
       "ufm.application.job_projection","ufm.application.topology",
       "ufm.domain.entities.job_projection",
       "ufm.application.slice_binding","ufm.integrations.slice_artifact_store",
       "ufm.application.projection_drain","ufm.application.slot_spool_identity",
       "ufm.application.spool_identifiers",
       "ufm.integrations.sliced_files","ufm.integrations.gcode_extrusion",
       "ufm.integrations.haspel_calculation","ufm.integrations.calculation_worker")
for name in names:
    module=importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(root),name
from ufm.integrations.gcode_extrusion import inspect_extrusion
data=b"G21\nT0\nM83\nG1 E10\nG1 E-2\nG1 E3\n"
report=inspect_extrusion(data,expected_sha256=hashlib.sha256(data).hexdigest(),dialect="marlin-linear-v1")
assert report.buckets[0].fresh_mm==Decimal(11)
from ufm.application.calculated_finalization import EstimatedUsagePolicy
assert EstimatedUsagePolicy().enabled is False
entry=files("ufm.integrations").joinpath("haspel_worker.mjs")
assert entry.is_file()
from ufm.integrations.printers.bambu_lan import material_slot_mappings_from_report
mapping=material_slot_mappings_from_report({"print":{"mapping":[0,3,65535,0xFF00,0xFE00]}})
assert [(item.logical_material,item.disposition,item.provider_system_key,item.provider_slot_key)
        for item in mapping]==[(0,"reported_slot","ams:0","0:0"),
        (1,"reported_slot","ams:0","0:3"),(2,"unused",None,None),
        (3,"reported_slot","external","external"),(4,"unsupported",None,None)]
from ufm.application.dto.worker_protocol import JobMessage,decode_worker_message
job=decode_worker_message(json.dumps({"v":1,"kind":"job","request_id":"wheel-check",
    "printer_id":"00000000-0000-4000-8000-000000000001","source_epoch":"epoch-1",
    "sequence":1,"observed_at":"2026-10-28T00:00:00Z","occurrence_key":"run-1",
    "state":"running","material_slot_mappings":[{"logical_material":5,
    "disposition":"reported_slot","provider_system_key":"ams:0",
    "provider_slot_key":"0:3"}]}).encode())
assert isinstance(job,JobMessage) and job.material_slot_mappings[0].logical_material==5
from ufm.application.job_material_mapping import JobMaterialMappingState,resolve_job_material_slots
assert JobMaterialMappingState.MATCHED.value=="MATCHED" and callable(resolve_job_material_slots)
from ufm.application.mounted_material_mapping import MountedMaterialState,resolve_mounted_material
assert MountedMaterialState.MATCHED.value=="MATCHED" and callable(resolve_mounted_material)
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import LATEST_REVISION,migrate_database
engine=create_sqlite_engine(root/"wheel-smoke.sqlite3")
try:
    assert migrate_database(engine)==LATEST_REVISION
    assert migrate_database(engine)==LATEST_REVISION
    from ufm.application.job_projection import JobProjectionCommands
    from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
    assert not JobProjectionCommands(lambda:SQLiteUnitOfWork(engine)).pending()
finally:
    engine.dispose()
import io,zipfile
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,"w") as archive:
    archive.writestr("Metadata/slice_info.config",'<config><plate><metadata key="index" value="1"/><filament id="1" used_g="1"/></plate></config>')
    archive.writestr("Metadata/plate_1.gcode","M83\nT0\nG1 E1\n")
from ufm.integrations.slice_artifact_store import SliceArtifactStore
data=buffer.getvalue()
store=SliceArtifactStore(root/"verified-artifacts")
artifact=store.store_bytes(data,expected_sha256=hashlib.sha256(data).hexdigest(),plate=1)
loaded=store.load(expected_sha256=artifact.facts.file_sha256,plate=1)
assert loaded.facts==artifact.facts and loaded.facts.filaments[0].mass_mg==1000
print(json.dumps({"imported_modules":list(names),"migration":LATEST_REVISION,
    "gcode_fresh_mm":str(report.buckets[0].fresh_mm),"calculated_policy_default":False,
    "canonical_entrypoint_in_wheel":True,"projection_queue_empty":True,
    "verified_artifact_reloaded":True,"printer_mapping_decoder":True,
    "job_mapping_receipt_contract":True,"job_material_slot_resolver":True,
    "mounted_material_resolver":True,
    "standalone_node_engine_bundled":False}))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="ufm-worker-wheel-") as directory:
        root = Path(directory).resolve()
        with zipfile.ZipFile(wheel) as archive:
            members = archive.infolist()
            for member in members:
                path = Path(member.filename)
                if (not (root / path).resolve().is_relative_to(root)
                        or "\\" in member.filename or path.is_absolute()
                        or any(part in {".env", "__pycache__"} for part in path.parts)
                        or path.suffix.lower() in {".sqlite3", ".sqlite", ".db", ".log"}):
                    raise RuntimeError("Unexpected wheel member")
            archive.extractall(root)
        result = subprocess.run([sys.executable, "-I", "-c", CHILD, str(root)],
                                cwd=root, text=True, capture_output=True, timeout=30, check=True)
        report = json.loads(result.stdout)
    report["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    report["wheel_filename"] = wheel.name
    report["member_count"] = len(members)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
