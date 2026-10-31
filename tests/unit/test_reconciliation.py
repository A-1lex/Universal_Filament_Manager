import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

from ufm.domain.entities import (
    AuditEvent,
    DecisionEvidence,
    InventoryReconciliation,
    ReconciliationTask,
)
from ufm.domain.enums import ReconciliationState, Severity
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


def at(minutes: int = 0) -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC) + timedelta(minutes=minutes))


def mutable() -> dict[str, object]:
    return {
        "id": EntityId.new(), "device_id": EntityId.new(), "created_at": at(),
        "updated_at": at(), "revision": 1,
    }


def immutable() -> dict[str, object]:
    return {"id": EntityId.new(), "device_id": EntityId.new(), "created_at": at()}


class ReconciliationTests(unittest.TestCase):
    def test_terminal_resolution_requires_actor_time_and_reason(self) -> None:
        common = dict(
            **mutable(), reason_code="negative_stock", severity=Severity.ERROR,
            dedupe_key="spool:negative", spool_id=EntityId.new(),
        )
        with self.assertRaises(ValueError):
            ReconciliationTask(**common, state=ReconciliationState.RESOLVED)
        task = ReconciliationTask(
            **common, state=ReconciliationState.RESOLVED, resolved_at=at(1),
            resolved_by=EntityId.new(), resolution_notes="ledger checked",
        )
        self.assertIs(task.state, ReconciliationState.RESOLVED)

    def test_measurement_correction_preserves_signed_delta(self) -> None:
        reconciliation = InventoryReconciliation(
            **immutable(), spool_id=EntityId.new(), evidence_id=EntityId.new(),
            accepted_ledger_cutoff=4, previous_effective=Mass.from_grams(700),
            accepted_remaining=Mass.from_grams(650), policy_version="safe-v1",
            reason="trusted scale", actor_device_id=EntityId.new(),
        )
        self.assertEqual(reconciliation.correction_delta, Mass.from_grams(-50))

    def test_audit_and_evidence_links_are_immutable(self) -> None:
        audit = AuditEvent(
            **immutable(), event_code="mount_rejected", actor_device_id=EntityId.new(),
            correlation_id="command", entity_type="spool", entity_id=EntityId.new(),
        )
        link = DecisionEvidence(
            **immutable(), decision_id=EntityId.new(), evidence_id=EntityId.new(), role="selected",
        )
        for record in (audit, link):
            with self.subTest(record=type(record).__name__), self.assertRaises(FrozenInstanceError):
                record.id = EntityId.new()  # type: ignore[misc]
