"""Shared accounting blocker keys; never use filename or delivery counters."""

import hashlib
import json

from ufm.domain.entities import JobIdentityAlias
from ufm.domain.value_objects import EntityId


def lifecycle_conflict_key(job_id: EntityId) -> str:
    return f"job:{job_id}:lifecycle_conflict"


def projection_rejection_key(receipt_id: EntityId) -> str:
    return f"receipt:{receipt_id}:projection_rejected"


def run_quarantine_key(alias: JobIdentityAlias) -> str:
    """Versioned exact alias scope digest, independent of job IDs and filenames."""
    return run_quarantine_key_for_scope(*alias.occurrence_scope)


def run_quarantine_key_for_scope(
    provider_instance_id: EntityId,
    printer_id: EntityId,
    source_type: str,
    source_epoch: str,
    occurrence_key: str,
) -> str:
    """Build the same blocker key before a job alias exists."""
    payload = ["run-quarantine-v1", str(provider_instance_id), str(printer_id),
               source_type, source_epoch, occurrence_key]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return f"run:{digest}:projection_rejected"
