"""Append-only inventory, audit and reconciliation table definitions."""

from sqlalchemy import CheckConstraint, Column, Index, Integer, Table, Text, UniqueConstraint

from ufm.domain.enums import ReconciliationState, Severity, TransactionType
from ufm.infrastructure.persistence.models.accounting import _json, _mass_check, _ref
from ufm.infrastructure.persistence.models.common import (
    _immutable_columns,
    _mutable_columns,
    _values,
    metadata,
)
from ufm.infrastructure.persistence.models.types import ExactDecimalType, MassType, UtcDateTimeType

material_transfer = Table(
    "material_transfer", metadata, *_immutable_columns(),
    _ref("from_spool_id", "spool"), _ref("to_spool_id", "spool"),
    Column("weight_mg", MassType(), nullable=False), Column("command_key", Text(), nullable=False),
    Column("reason", Text(), nullable=False),
    _mass_check("weight_mg", nullable=False),
    CheckConstraint("weight_mg > 0 AND from_spool_id <> to_spool_id", name="physical_transfer"),
    CheckConstraint("length(command_key) BETWEEN 1 AND 500 AND length(reason) BETWEEN 1 AND 500", name="text_fields"),
    UniqueConstraint("command_key"),
)

filament_transaction = Table(
    "filament_transaction", metadata, *_immutable_columns(),
    _ref("spool_id", "spool"), Column("sequence", Integer(), nullable=False),
    Column("transaction_type", Text(), nullable=False), Column("delta_mg", MassType(), nullable=False),
    Column("previous_effective_mg", MassType()), Column("new_effective_mg", MassType(), nullable=False),
    Column("previous_estimated_mg", MassType()), Column("new_estimated_mg", MassType()),
    Column("estimate_policy_version", Text(), nullable=False),
    Column("command_key", Text(), nullable=False), Column("command_item", Integer(), nullable=False),
    _ref("print_job_id", "print_job", nullable=True),
    _ref("decision_id", "consumption_decision", nullable=True),
    _ref("reservation_id", "reservation", nullable=True),
    _ref("inventory_reconciliation_id", "inventory_reconciliation", nullable=True),
    _ref("compensates_transaction_id", "filament_transaction", nullable=True),
    _ref("transfer_id", "material_transfer", nullable=True),
    Column("source_type", Text(), nullable=False),
    _ref("source_receipt_id", "external_event_receipt", nullable=True),
    Column("confidence_bp", Integer(), nullable=False), Column("unit_cost", ExactDecimalType()),
    Column("currency", Text()), Column("description", Text()), *_json("metadata_json"),
    _mass_check("delta_mg", nullable=False, signed=True),
    _mass_check("previous_effective_mg", signed=True),
    _mass_check("new_effective_mg", nullable=False, signed=True),
    _mass_check("previous_estimated_mg", signed=True), _mass_check("new_estimated_mg", signed=True),
    CheckConstraint("typeof(sequence)='integer' AND sequence >= 1", name="sequence_range"),
    CheckConstraint("typeof(command_item)='integer' AND command_item >= 0", name="item_range"),
    CheckConstraint(f"transaction_type IN ({_values(TransactionType)})", name="type_enum"),
    CheckConstraint(
        "(sequence=1 AND transaction_type='INITIAL_STOCK' AND previous_effective_mg IS NULL "
        "AND delta_mg >= 0 AND new_effective_mg=delta_mg) OR "
        "(sequence>1 AND transaction_type<>'INITIAL_STOCK' AND previous_effective_mg IS NOT NULL "
        "AND new_effective_mg=previous_effective_mg+delta_mg)", name="balance_equation",
    ),
    CheckConstraint(
        "(transaction_type IN ('PRINT_CONSUMPTION','PURGE','LOAD','UNLOAD','WASTE',"
        "'FAILED_PRINT','MANUAL_USE','TRANSFER_OUT') AND delta_mg<0) OR "
        "(transaction_type IN ('TRANSFER_IN','RETURN') AND delta_mg>0) OR "
        "(transaction_type='INITIAL_STOCK' AND delta_mg>=0) OR "
        "transaction_type='MEASUREMENT_CORRECTION' OR "
        "(transaction_type='INVENTORY_ADJUSTMENT' AND delta_mg<>0)", name="delta_direction",
    ),
    CheckConstraint("length(command_key) BETWEEN 1 AND 500 AND length(source_type) BETWEEN 1 AND 500 AND length(estimate_policy_version) BETWEEN 1 AND 500", name="text_fields"),
    CheckConstraint("typeof(confidence_bp)='integer' AND confidence_bp BETWEEN 0 AND 10000", name="confidence_range"),
    CheckConstraint("(unit_cost IS NULL AND currency IS NULL) OR (unit_cost IS NOT NULL AND currency IS NOT NULL AND currency GLOB '[A-Z][A-Z][A-Z]')", name="money_shape"),
    CheckConstraint("compensates_transaction_id IS NULL OR compensates_transaction_id<>id", name="not_self_compensation"),
    UniqueConstraint("spool_id", "sequence"), UniqueConstraint("command_key", "command_item"),
)
Index("uq_filament_transaction_original_decision", filament_transaction.c.decision_id, unique=True,
      sqlite_where=filament_transaction.c.decision_id.is_not(None) & filament_transaction.c.compensates_transaction_id.is_(None))
Index("uq_filament_transaction_reconciliation", filament_transaction.c.inventory_reconciliation_id,
      unique=True, sqlite_where=filament_transaction.c.inventory_reconciliation_id.is_not(None))
Index("ix_filament_transaction_spool_created", filament_transaction.c.spool_id, filament_transaction.c.created_at, filament_transaction.c.sequence)

reconciliation_task = Table(
    "reconciliation_task", metadata, *_mutable_columns(),
    _ref("spool_id", "spool", nullable=True), _ref("print_job_id", "print_job", nullable=True),
    _ref("feed_slot_id", "feed_slot", nullable=True), Column("reason_code", Text(), nullable=False),
    Column("severity", Text(), nullable=False), Column("status", Text(), nullable=False),
    Column("dedupe_key", Text(), nullable=False), Column("suggested_action", Text()),
    Column("resolved_at", UtcDateTimeType()), _ref("resolved_by", "device_identity", nullable=True),
    Column("resolution_notes", Text()),
    CheckConstraint(f"severity IN ({_values(Severity)})", name="severity_enum"),
    CheckConstraint(f"status IN ({_values(ReconciliationState)})", name="status_enum"),
    CheckConstraint("length(reason_code) BETWEEN 1 AND 500 AND length(dedupe_key) BETWEEN 1 AND 500", name="text_fields"),
    CheckConstraint(
        "(status IN ('RESOLVED','DISMISSED') AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL "
        "AND resolution_notes IS NOT NULL AND length(trim(resolution_notes))>0) OR "
        "(status IN ('OPEN','IN_REVIEW') AND resolved_at IS NULL AND resolved_by IS NULL)", name="resolution_shape",
    ),
)
Index("uq_reconciliation_task_open", reconciliation_task.c.dedupe_key, unique=True,
      sqlite_where=reconciliation_task.c.status.in_(("OPEN", "IN_REVIEW")))
Index("ix_reconciliation_task_status_severity", reconciliation_task.c.status, reconciliation_task.c.severity, reconciliation_task.c.created_at)

alert_event = Table(
    "alert_event", metadata, *_mutable_columns(),
    _ref("reconciliation_task_id", "reconciliation_task", nullable=True),
    _ref("spool_id", "spool", nullable=True), _ref("print_job_id", "print_job", nullable=True),
    Column("severity", Text(), nullable=False), Column("message_key", Text(), nullable=False),
    *_json("message_params_json"), Column("dedupe_key", Text(), nullable=False),
    Column("raised_at", UtcDateTimeType(), nullable=False), Column("acknowledged_at", UtcDateTimeType()),
    Column("resolved_at", UtcDateTimeType()),
    CheckConstraint(f"severity IN ({_values(Severity)})", name="severity_enum"),
    CheckConstraint("length(message_key) BETWEEN 1 AND 500 AND length(dedupe_key) BETWEEN 1 AND 500", name="text_fields"),
    CheckConstraint("acknowledged_at IS NULL OR acknowledged_at >= raised_at", name="ack_order"),
    CheckConstraint("resolved_at IS NULL OR resolved_at >= raised_at", name="resolution_order"),
)
Index("uq_alert_event_open", alert_event.c.dedupe_key, unique=True, sqlite_where=alert_event.c.resolved_at.is_(None))

audit_event = Table(
    "audit_event", metadata, *_immutable_columns(), Column("event_code", Text(), nullable=False),
    _ref("actor_device_id", "device_identity"), Column("correlation_id", Text(), nullable=False),
    Column("entity_type", Text(), nullable=False), Column("entity_id", Text(), nullable=False),
    *_json("parameters_json"),
    CheckConstraint("length(event_code) BETWEEN 1 AND 500 AND length(correlation_id) BETWEEN 1 AND 500 AND length(entity_type) BETWEEN 1 AND 500 AND length(entity_id) BETWEEN 1 AND 500", name="text_fields"),
)

pending_effect = Table(
    "pending_effect", metadata, *_mutable_columns(), Column("event_key", Text(), nullable=False),
    Column("effect_type", Text(), nullable=False), *_json("payload_json"),
    Column("state", Text(), nullable=False), Column("attempts", Integer(), nullable=False, server_default="0"),
    Column("next_attempt_at", UtcDateTimeType()), Column("delivered_at", UtcDateTimeType()),
    CheckConstraint("state IN ('PENDING','DELIVERED','FAILED')", name="state_enum"),
    CheckConstraint("typeof(attempts)='integer' AND attempts >= 0", name="attempts_range"),
    CheckConstraint("(state='DELIVERED' AND delivered_at IS NOT NULL) OR (state<>'DELIVERED' AND delivered_at IS NULL)", name="delivered_shape"),
    UniqueConstraint("event_key", "effect_type"),
)
Index("ix_pending_effect_state_retry", pending_effect.c.state, pending_effect.c.next_attempt_at)

for table in (material_transfer, filament_transaction, reconciliation_task, alert_event, audit_event, pending_effect):
    for column in table.columns:
        if column.foreign_keys and not any(tuple(index.columns)[0] is column for index in table.indexes):
            Index(f"ix_{table.name}_{column.name}", column)
