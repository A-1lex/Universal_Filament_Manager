"""Explicit, durable job/file/plate binding; no print-state or stock inference."""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ufm.application.dto.slice_facts import VerifiedSliceFacts
from ufm.application.ports.persistence import IdempotencyConflict, UnitOfWork
from ufm.application.ports.slice_artifacts import SliceArtifactStore, StoredSliceArtifact
from ufm.domain.entities import AuditEvent, PrintJob
from ufm.domain.enums import FinalizationState
from ufm.domain.value_objects import EntityId, UtcDateTime
from ufm.domain.value_objects.json_object import json_object

VERSION = "verified-slice-binding-v1"
EVENT = "print.slice_bound"


class SliceBindingRejected(ValueError):
    pass


@dataclass(frozen=True)
class BoundSlice:
    job_id: EntityId
    binding_id: EntityId
    facts: VerifiedSliceFacts
    archive_path: Path


def _key(job_id: EntityId) -> str:
    return f"job:{job_id}:slice_binding"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


class VerifiedSliceBindings:
    def __init__(self, unit_of_work: Callable[[], UnitOfWork], artifact_store: SliceArtifactStore) -> None:
        self._unit_of_work, self._artifacts = unit_of_work, artifact_store

    def bind_local(self, *, job_id: EntityId, source_path: Path, expected_sha256: str,
                   plate: int, actor_device_id: EntityId, manual_confirmation: bool = False,
                   at: UtcDateTime | None = None) -> BoundSlice:
        if (type(expected_sha256) is not str or re.fullmatch("[0-9a-f]{64}", expected_sha256) is None
                or type(plate) is not int or not 1 <= plate <= 1_000_000
                or type(manual_confirmation) is not bool):
            raise SliceBindingRejected("binding.request_invalid")
        now = at or UtcDateTime.now()
        request_hash = _hash({"version": VERSION, "job": str(job_id), "file": expected_sha256,
                              "plate": plate, "actor": str(actor_device_id), "manual": manual_confirmation})
        with self._unit_of_work() as work:
            job = work.jobs.get(job_id)
            prior = self._prior(work, job)
            if prior is not None:
                if (json_object(prior.parameters_json).get("request_hash") != request_hash
                        or prior.actor_device_id != actor_device_id):
                    raise IdempotencyConflict()
                previous = prior
            else:
                self._verify_new(work, job, expected_sha256, plate, manual_confirmation, now)
                previous = None
            fingerprint = _hash(asdict(job))
        if previous is not None:
            # Repeat uses the persistent artifact, even if the selected source is gone.
            return self.resolve(job_id=job_id)
        try:
            artifact = self._artifacts.store_file(source_path, expected_sha256=expected_sha256, plate=plate)
        except (ValueError, OSError):
            raise SliceBindingRejected("binding.artifact_unavailable") from None
        self._verify_artifact(artifact, expected_sha256, plate)
        with self._unit_of_work() as work:
            current = work.jobs.get(job_id)
            prior = self._prior(work, current)
            if prior is not None:
                if json_object(prior.parameters_json).get("request_hash") != request_hash:
                    raise IdempotencyConflict()
                self._verify_metadata(prior, current, artifact)
                return BoundSlice(job_id, prior.id, artifact.facts, artifact.archive_path)
            if _hash(asdict(current)) != fingerprint:
                raise IdempotencyConflict()
            self._verify_new(work, current, expected_sha256, plate, manual_confirmation, now)
            facts = artifact.facts
            params = {"version": VERSION, "request_hash": request_hash,
                      "file_sha256": facts.file_sha256, "plate": facts.plate,
                      "parser_version": facts.parser_version, "metadata_sha256": facts.metadata_sha256,
                      "gcode_sha256": facts.gcode_sha256, "manual_confirmation": manual_confirmation,
                      "quantity": "estimate", "includes_purge": facts.includes_purge}
            audit = AuditEvent(id=EntityId.new(), device_id=actor_device_id, created_at=now,
                actor_device_id=actor_device_id, correlation_id=_key(job_id),
                event_code=EVENT, entity_type="print_job", entity_id=job_id,
                parameters_json=json.dumps(params, sort_keys=True))
            work.jobs.save(replace(current, file_hash=expected_sha256, plate_name=str(plate),
                                   updated_at=now, revision=current.revision + 1), current.revision)
            work.audit.append(audit)
            work.commit()
            return BoundSlice(job_id, audit.id, facts, artifact.archive_path)

    def resolve(self, *, job_id: EntityId) -> BoundSlice:
        with self._unit_of_work() as work:
            job = work.jobs.get(job_id)
            prior = self._prior(work, job)
            if prior is None:
                raise SliceBindingRejected("binding.missing")
            params = json_object(prior.parameters_json)
            digest, plate = params.get("file_sha256"), params.get("plate")
            if type(digest) is not str or type(plate) is not int:
                raise SliceBindingRejected("binding.provenance_invalid")
        try:
            artifact = self._artifacts.load(expected_sha256=digest, plate=plate)
        except (ValueError, OSError):
            raise SliceBindingRejected("binding.artifact_unavailable") from None
        self._verify_artifact(artifact, digest, plate)
        with self._unit_of_work() as work:
            current = work.jobs.get(job_id)
            current_prior = self._prior(work, current)
            if current_prior != prior:
                raise IdempotencyConflict()
            self._verify_metadata(prior, current, artifact)
        return BoundSlice(job_id, prior.id, artifact.facts, artifact.archive_path)

    @staticmethod
    def _prior(work: UnitOfWork, job: PrintJob) -> AuditEvent | None:
        events = work.audit.for_command(_key(job.id))
        if not events:
            return None
        if (len(events) != 1 or events[0].event_code != EVENT or events[0].entity_type != "print_job"
                or events[0].entity_id != job.id):
            raise IdempotencyConflict()
        return events[0]

    @staticmethod
    def _verify_new(work: UnitOfWork, job: PrintJob, digest: str, plate: int,
                    confirmed: bool, now: UtcDateTime) -> None:
        printer = work.printers.get(job.printer_id)
        if (job.deleted_at is not None or printer.deleted_at is not None or not printer.enabled
                or job.finalization_state in {FinalizationState.IN_PROGRESS, FinalizationState.FINALIZED}
                or job.updated_at > now):
            raise SliceBindingRejected("binding.job_unavailable")
        if (job.file_hash is not None and job.file_hash != digest) or (job.plate_name is not None and job.plate_name != str(plate)):
            raise SliceBindingRejected("binding.identity_mismatch")
        if (job.file_hash is None or job.plate_name is None) and not confirmed:
            raise SliceBindingRejected("binding.manual_confirmation_required")

    @staticmethod
    def _verify_artifact(artifact: StoredSliceArtifact, digest: str, plate: int) -> None:
        facts = artifact.facts
        if (facts.file_sha256 != digest or facts.plate != plate or facts.quantity != "estimate"
                or type(facts.plate) is not int or not facts.parser_version or facts.includes_purge is not None):
            raise SliceBindingRejected("binding.artifact_invalid")

    @staticmethod
    def _verify_metadata(event: AuditEvent, job: PrintJob, artifact: StoredSliceArtifact) -> None:
        facts = artifact.facts
        params = json_object(event.parameters_json)
        expected = {"version": VERSION, "file_sha256": facts.file_sha256, "plate": facts.plate,
                    "parser_version": facts.parser_version, "metadata_sha256": facts.metadata_sha256,
                    "gcode_sha256": facts.gcode_sha256, "quantity": "estimate", "includes_purge": facts.includes_purge}
        request_hash = _hash({"version": VERSION, "job": str(job.id), "file": facts.file_sha256,
                              "plate": facts.plate, "actor": str(event.actor_device_id),
                              "manual": params.get("manual_confirmation")})
        if (job.deleted_at is not None or job.file_hash != facts.file_sha256 or job.plate_name != str(facts.plate)
                or params.keys() != expected.keys() | {"request_hash", "manual_confirmation"}
                or any(type(params.get(key)) is not type(value) or params.get(key) != value for key, value in expected.items())
                or type(params.get("manual_confirmation")) is not bool
                or params.get("request_hash") != request_hash):
            raise SliceBindingRejected("binding.provenance_mismatch")
