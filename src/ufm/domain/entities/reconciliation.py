"""First-class reconciliation, alert, and audit records."""

import json
from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord, ImmutableRecord
from ufm.domain.enums import ReconciliationState, Severity
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def _required(value: str, code: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 500:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationTask(EntityRecord):
    reason_code: str
    severity: Severity
    state: ReconciliationState
    dedupe_key: str
    spool_id: EntityId | None = None
    print_job_id: EntityId | None = None
    feed_slot_id: EntityId | None = None
    suggested_action: str | None = None
    resolved_at: UtcDateTime | None = None
    resolved_by: EntityId | None = None
    resolution_notes: str | None = None

    def __post_init__(self) -> None:
        super(ReconciliationTask, self).__post_init__()
        _required(self.reason_code, "reconciliation.reason_invalid")
        _required(self.dedupe_key, "reconciliation.dedupe_invalid")
        is_terminal = self.state in {
            ReconciliationState.RESOLVED,
            ReconciliationState.DISMISSED,
        }
        has_resolution = (
            self.resolved_at is not None
            and self.resolved_by is not None
            and self.resolution_notes is not None
            and bool(self.resolution_notes.strip())
        )
        if is_terminal != has_resolution:
            raise ValueError("reconciliation.resolution_shape_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class AlertEvent(EntityRecord):
    severity: Severity
    message_key: str
    dedupe_key: str
    raised_at: UtcDateTime
    reconciliation_task_id: EntityId | None = None
    spool_id: EntityId | None = None
    print_job_id: EntityId | None = None
    acknowledged_at: UtcDateTime | None = None
    resolved_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        super(AlertEvent, self).__post_init__()
        _required(self.message_key, "alert.message_key_invalid")
        _required(self.dedupe_key, "alert.dedupe_key_invalid")
        if self.acknowledged_at is not None and self.acknowledged_at < self.raised_at:
            raise ValueError("alert.acknowledged_at_invalid")
        if self.resolved_at is not None and self.resolved_at < self.raised_at:
            raise ValueError("alert.resolved_at_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent(ImmutableRecord):
    event_code: str
    actor_device_id: EntityId
    correlation_id: str
    entity_type: str
    entity_id: EntityId
    parameters_json: str = "{}"

    def __post_init__(self) -> None:
        for value in (self.event_code, self.correlation_id, self.entity_type):
            _required(value, "audit.field_invalid")
        if type(self.parameters_json) is not str or len(self.parameters_json) > 4096:
            raise ValueError("audit.parameters_invalid")
        try:
            parameters = json.loads(self.parameters_json)
        except ValueError:
            raise ValueError("audit.parameters_invalid") from None
        if not isinstance(parameters, dict):
            raise ValueError("audit.parameters_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisionEvidence(ImmutableRecord):
    decision_id: EntityId
    evidence_id: EntityId
    role: str

    def __post_init__(self) -> None:
        _required(self.role, "decision_evidence.role_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumptionInventoryEvidence(ImmutableRecord):
    consumption_evidence_id: EntityId
    inventory_evidence_id: EntityId
    role: str

    def __post_init__(self) -> None:
        _required(self.role, "consumption_inventory_evidence.role_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryReconciliation(ImmutableRecord):
    spool_id: EntityId
    evidence_id: EntityId
    accepted_ledger_cutoff: int
    accepted_remaining: Mass
    policy_version: str
    reason: str
    actor_device_id: EntityId
    previous_effective: Mass | None = None
    estimated_before: Mass | None = None
    estimated_after: Mass | None = None

    def __post_init__(self) -> None:
        if type(self.accepted_ledger_cutoff) is not int or self.accepted_ledger_cutoff < 0:
            raise ValueError("inventory_reconciliation.cutoff_invalid")
        if self.accepted_remaining.milligrams < 0:
            raise ValueError("inventory_reconciliation.mass_invalid")
        _required(self.policy_version, "inventory_reconciliation.policy_invalid")
        _required(self.reason, "inventory_reconciliation.reason_invalid")

    @property
    def correction_delta(self) -> Mass:
        if self.previous_effective is None:
            return self.accepted_remaining
        return self.accepted_remaining - self.previous_effective
