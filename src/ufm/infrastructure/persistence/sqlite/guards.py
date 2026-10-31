"""SQLite history and scope guards, also frozen into each schema migration."""

from typing import Any

from sqlalchemy import MetaData, event
from sqlalchemy.engine import Connection

IMMUTABLE_TABLES = (
    "calibration_record", "job_identity_alias", "inventory_evidence", "consumption_evidence",
    "finalization_record", "consumption_decision", "decision_evidence",
    "consumption_inventory_evidence", "inventory_reconciliation", "filament_transaction",
    "material_transfer", "audit_event", "job_receipt_application",
)


def _trigger(table: str, label: str, operation: str, predicate: str, error: str) -> str:
    # All identifiers and predicates are internal constants, never external input.
    return (
        f"CREATE TRIGGER IF NOT EXISTS guard_{table}_{label} BEFORE {operation} ON {table} "
        f"WHEN {predicate} BEGIN SELECT RAISE(ABORT, '{error}'); END"
    )


def guard_statements() -> list[str]:
    statements = [
        _trigger(table, operation.lower(), operation, "1", "history.immutable")
        for table in IMMUTABLE_TABLES for operation in ("UPDATE", "DELETE")
    ]
    statements.append(_trigger(
        "filament_transaction", "sequence", "INSERT",
        "NEW.sequence <> COALESCE((SELECT MAX(sequence)+1 FROM filament_transaction WHERE spool_id=NEW.spool_id),1) "
        "OR (NEW.sequence>1 AND (NEW.previous_effective_mg IS NOT "
        "(SELECT new_effective_mg FROM filament_transaction WHERE spool_id=NEW.spool_id ORDER BY sequence DESC LIMIT 1) "
        "OR NEW.previous_estimated_mg IS NOT (SELECT new_estimated_mg FROM filament_transaction "
        "WHERE spool_id=NEW.spool_id ORDER BY sequence DESC LIMIT 1)))",
        "ledger.sequence_or_balance_conflict",
    ))
    statements.append(_trigger(
        "filament_transaction", "compensation", "INSERT",
        "NEW.compensates_transaction_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM filament_transaction WHERE id=NEW.compensates_transaction_id AND spool_id=NEW.spool_id)",
        "ledger.compensation_spool_conflict",
    ))
    statements.append(_trigger(
        "filament_transaction", "decision_scope", "INSERT",
        "NEW.decision_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM consumption_decision d "
        "JOIN material_usage_segment s ON s.id=d.material_usage_segment_id "
        "JOIN finalization_record f ON f.id=d.finalization_record_id "
        "WHERE d.id=NEW.decision_id AND s.spool_id=NEW.spool_id AND f.print_job_id=NEW.print_job_id "
        "AND (NEW.compensates_transaction_id IS NOT NULL OR NEW.delta_mg=-d.selected_weight_mg))",
        "ledger.decision_scope_conflict",
    ))
    statements.append(_trigger(
        "consumption_decision", "scope", "INSERT",
        "NOT EXISTS (SELECT 1 FROM material_usage_segment s JOIN print_job_material m ON m.id=s.print_job_material_id "
        "JOIN finalization_record f ON f.print_job_id=m.print_job_id WHERE s.id=NEW.material_usage_segment_id "
        "AND f.id=NEW.finalization_record_id AND s.assignment_state='ASSIGNED' AND s.spool_id IS NOT NULL)",
        "decision.unresolved_or_wrong_job",
    ))
    statements.append(_trigger(
        "consumption_evidence", "scope", "INSERT",
        "NEW.segment_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM material_usage_segment "
        "WHERE id=NEW.segment_id AND print_job_material_id=NEW.print_job_material_id)",
        "evidence.segment_scope_conflict",
    ))
    statements.append(_trigger(
        "decision_evidence", "scope", "INSERT",
        "NOT EXISTS (SELECT 1 FROM consumption_decision d JOIN material_usage_segment s "
        "ON s.id=d.material_usage_segment_id JOIN consumption_evidence e "
        "ON e.print_job_material_id=s.print_job_material_id WHERE d.id=NEW.decision_id "
        "AND e.id=NEW.evidence_id AND (e.segment_id IS NULL OR e.segment_id=s.id))",
        "decision.evidence_scope_conflict",
    ))
    statements.append(_trigger(
        "inventory_reconciliation", "scope", "INSERT",
        "NOT EXISTS (SELECT 1 FROM inventory_evidence WHERE id=NEW.evidence_id AND spool_id=NEW.spool_id)",
        "reconciliation.evidence_scope_conflict",
    ))
    for operation in ("INSERT", "UPDATE"):
        statements.append(_trigger(
            "material_usage_segment", "scope_" + operation.lower(), operation,
            "NEW.assignment_state='ASSIGNED' AND NOT EXISTS (SELECT 1 FROM spool_mount a "
            "JOIN feed_slot slot ON slot.id=a.feed_slot_id JOIN material_feed_system sys ON sys.id=slot.feed_system_id "
            "JOIN print_job_material m ON m.id=NEW.print_job_material_id JOIN print_job j ON j.id=m.print_job_id "
            "WHERE a.id=NEW.spool_mount_id AND a.spool_id=NEW.spool_id AND a.feed_slot_id=NEW.feed_slot_id "
            "AND sys.printer_id=j.printer_id AND NEW.tool_index=m.tool_index "
            "AND NEW.started_at>=a.mounted_at AND (a.unmounted_at IS NULL OR "
            "(NEW.ended_at IS NOT NULL AND NEW.ended_at<=a.unmounted_at)))",
            "segment.mount_scope_conflict",
        ))
        for table, group in (("spool_mount", "(x.spool_id=NEW.spool_id OR x.feed_slot_id=NEW.feed_slot_id)"),
                             ("material_usage_segment", "x.print_job_material_id=NEW.print_job_material_id")):
            start, end = ("mounted_at", "unmounted_at") if table == "spool_mount" else ("started_at", "ended_at")
            # Zero-duration intervals have no occupied time; open intervals do.
            predicate = (
                f"(NEW.{end} IS NULL OR NEW.{end}>NEW.{start}) AND EXISTS (SELECT 1 FROM {table} x "
                f"WHERE x.id<>NEW.id AND {group} AND (x.{end} IS NULL OR x.{end}>x.{start}) "
                f"AND (NEW.{end} IS NULL OR x.{start}<NEW.{end}) AND (x.{end} IS NULL OR NEW.{start}<x.{end}))"
            )
            statements.append(_trigger(table, "overlap_" + operation.lower(), operation, predicate, "history.interval_overlap"))
        statements.append(_trigger(
            "storage_location", "cycle_" + operation.lower(), operation,
            "NEW.parent_id IS NOT NULL AND NEW.id IN (WITH RECURSIVE ancestors(id) AS "
            "(SELECT NEW.parent_id UNION SELECT s.parent_id FROM storage_location s JOIN ancestors a ON s.id=a.id "
            "WHERE s.parent_id IS NOT NULL) SELECT id FROM ancestors)", "storage.cycle",
        ))
        statements.append(_trigger(
            "reservation", "settlement_scope_" + operation.lower(), operation,
            "NEW.settled_finalization_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM print_job_material m "
            "JOIN finalization_record f ON f.print_job_id=m.print_job_id "
            "WHERE m.id=NEW.print_job_material_id AND f.id=NEW.settled_finalization_id)", "reservation.finalization_scope_conflict",
        ))
    statements.append(_trigger(
        "material_usage_segment", "finalized", "UPDATE",
        "EXISTS (SELECT 1 FROM consumption_decision WHERE material_usage_segment_id=OLD.id)",
        "segment.finalized_immutable",
    ))
    statements.append(_trigger("spool_mount", "closed", "UPDATE", "OLD.state='CLOSED'", "mount.closed_immutable"))
    statements.append(_trigger(
        "spool_mount", "identity", "UPDATE",
        "NEW.id<>OLD.id OR NEW.spool_id<>OLD.spool_id OR NEW.feed_slot_id<>OLD.feed_slot_id OR NEW.mounted_at<>OLD.mounted_at",
        "mount.identity_immutable",
    ))
    for table in ("spool_mount", "material_usage_segment", "reservation", "external_event_receipt"):
        statements.append(_trigger(table, "history_delete", "DELETE", "1", "history.immutable"))
    statements.append(_trigger(
        "reservation", "active_identity", "UPDATE", "OLD.status='ACTIVE' AND "
        "(NEW.id<>OLD.id OR NEW.spool_id<>OLD.spool_id OR NEW.print_job_material_id<>OLD.print_job_material_id OR NEW.reserved_mg<>OLD.reserved_mg)",
        "reservation.active_immutable",
    ))
    statements.append(_trigger("reservation", "terminal", "UPDATE", "OLD.status IN ('CONSUMED','RELEASED','EXPIRED')", "reservation.terminal_immutable"))
    statements.append(_trigger(
        "reservation", "transition", "UPDATE",
        "NEW.status<>OLD.status AND NOT ((OLD.status='PENDING' AND NEW.status IN ('ACTIVE','RELEASED','EXPIRED')) "
        "OR (OLD.status='ACTIVE' AND NEW.status IN ('CONSUMED','RELEASED','EXPIRED')))", "reservation.invalid_transition",
    ))
    statements.extend(projection_guard_statements())
    return statements


def projection_guard_statements() -> list[str]:
    """Scope guards introduced by the additive job-projection revision."""
    protected = (
        "last_receipt_id", "observed_state", "observed_at", "source_sequence", "completed_layers",
        "first_terminal_receipt_id", "first_terminal_state", "terminal_seen_at",
    )
    statements = [_trigger(
        "job_projection_state", "terminal_facts", "UPDATE",
        "OLD.first_terminal_receipt_id IS NOT NULL AND ("
        + " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in protected) + ")",
        "job_projection.terminal_facts_immutable",
    )]
    for table, receipt_column in (("job_receipt_application", "receipt_id"),
                                  ("job_projection_state", "last_receipt_id")):
        for operation in ("INSERT", "UPDATE"):
            statements.append(_trigger(
                table, "scope_" + operation.lower(), operation,
                "NOT EXISTS (SELECT 1 FROM external_event_receipt r JOIN print_job j "
                f"ON j.printer_id=r.printer_id WHERE r.id=NEW.{receipt_column} AND j.id=NEW.print_job_id)",
                "job_projection.receipt_scope_conflict",
            ))
    for operation in ("INSERT", "UPDATE"):
        statements.append(_trigger(
            "job_projection_state", "terminal_scope_" + operation.lower(), operation,
            "NEW.first_terminal_receipt_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM external_event_receipt r JOIN print_job j ON j.printer_id=r.printer_id "
            "WHERE r.id=NEW.first_terminal_receipt_id AND j.id=NEW.print_job_id)",
            "job_projection.receipt_scope_conflict",
        ))
    return statements


def register_guards(metadata: MetaData) -> None:
    @event.listens_for(metadata, "after_create")
    def create_guards(_metadata: MetaData, connection: Connection, **_kw: Any) -> None:
        if connection.dialect.name == "sqlite":
            for statement in guard_statements():
                connection.exec_driver_sql(statement)
