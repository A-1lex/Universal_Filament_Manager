"""Durable observation cursors, separate from physical print/accounting facts."""

import re
from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord, ImmutableRecord
from ufm.domain.value_objects import EntityId, UtcDateTime

JOB_PROJECTION_VERSION = "job-receipt-projection-v1"
OBSERVED_STATES = frozenset({"started", "running", "paused", "completed", "failed", "cancelled"})
TERMINAL_OBSERVATIONS = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True, kw_only=True)
class JobProjectionState(EntityRecord):
    print_job_id: EntityId
    last_receipt_id: EntityId
    observed_state: str
    observed_at: UtcDateTime
    source_sequence: int
    completed_layers: int | None = None
    first_terminal_receipt_id: EntityId | None = None
    first_terminal_state: str | None = None
    terminal_seen_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        super(JobProjectionState, self).__post_init__()
        if self.observed_state not in OBSERVED_STATES:
            raise ValueError("projection.state_invalid")
        for value in (self.source_sequence, self.completed_layers):
            if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
                raise ValueError("projection.count_invalid")
        if self.source_sequence is None:
            raise ValueError("projection.count_invalid")
        terminal = (self.first_terminal_receipt_id, self.first_terminal_state, self.terminal_seen_at)
        if any(value is not None for value in terminal):
            if (any(value is None for value in terminal)
                    or self.first_terminal_state not in TERMINAL_OBSERVATIONS
                    or self.observed_state != self.first_terminal_state
                    or self.terminal_seen_at != self.observed_at):
                raise ValueError("projection.terminal_invalid")
        elif self.observed_state in TERMINAL_OBSERVATIONS:
            raise ValueError("projection.terminal_required")


@dataclass(frozen=True, slots=True, kw_only=True)
class JobReceiptApplication(ImmutableRecord):
    receipt_id: EntityId
    print_job_id: EntityId
    contract_version: str
    outcome: str
    reason_code: str
    request_hash: str

    def __post_init__(self) -> None:
        if (self.contract_version != JOB_PROJECTION_VERSION
                or self.outcome not in {"APPLIED", "IGNORED_STALE", "CONFLICT"}
                or type(self.reason_code) is not str or not 1 <= len(self.reason_code) <= 200
                or type(self.request_hash) is not str or re.fullmatch("[0-9a-f]{64}", self.request_hash) is None):
            raise ValueError("projection.application_invalid")
