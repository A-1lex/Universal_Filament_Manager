"""Accounting tables share one metadata graph and exact storage types."""

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
)

from ufm.domain.enums import EvidenceMode, EvidenceSource, ReservationState
from ufm.domain.value_objects import MAX_ABS_MILLIGRAMS
from ufm.infrastructure.persistence.models.common import (
    _immutable_columns,
    _mutable_columns,
    _values,
    metadata,
)
from ufm.infrastructure.persistence.models.types import EntityIdType, MassType, UtcDateTimeType


def _ref(name: str, target: str, *, nullable: bool = False) -> Column[Any]:
    return Column(name, EntityIdType(), ForeignKey(target + ".id", ondelete="RESTRICT", onupdate="RESTRICT"), nullable=nullable)


def _mass_check(name: str, *, nullable: bool = True, signed: bool = False) -> CheckConstraint:
    lower = -MAX_ABS_MILLIGRAMS if signed else 0
    condition = f"typeof({name})='integer' AND {name} BETWEEN {lower} AND {MAX_ABS_MILLIGRAMS}"
    if nullable:
        condition = f"{name} IS NULL OR ({condition})"
    return CheckConstraint(condition, name=name + "_range")


def _json(name: str) -> list[Any]:
    return [
        Column(name, Text(), nullable=False, server_default="{}"),
        CheckConstraint(f"length({name}) <= 65536 AND json_valid({name}) AND json_type({name})='object'", name=name + "_object"),
    ]


finalization_record = Table(
    "finalization_record", metadata, *_immutable_columns(),
    _ref("print_job_id", "print_job"),
    Column("idempotency_key", Text(), nullable=False),
    Column("request_hash", Text(), nullable=False),
    Column("started_at", UtcDateTimeType(), nullable=False),
    Column("completed_at", UtcDateTimeType(), nullable=False),
    Column("result_hash", Text(), nullable=False),
    UniqueConstraint("print_job_id"), UniqueConstraint("idempotency_key"),
    CheckConstraint("length(idempotency_key) BETWEEN 1 AND 500", name="key_length"),
    CheckConstraint("length(request_hash) BETWEEN 1 AND 500 AND length(result_hash) BETWEEN 1 AND 500", name="hash_lengths"),
    CheckConstraint("completed_at >= started_at", name="interval_order"),
)

reservation = Table(
    "reservation", metadata, *_mutable_columns(),
    _ref("spool_id", "spool"), _ref("print_job_material_id", "print_job_material"),
    Column("reserved_mg", MassType(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("activated_at", UtcDateTimeType()), Column("consumed_at", UtcDateTimeType()),
    Column("released_at", UtcDateTimeType()), Column("expires_at", UtcDateTimeType()),
    _ref("settled_finalization_id", "finalization_record", nullable=True),
    Column("allocated_consumption_mg", MassType()), Column("released_mg", MassType()),
    Column("reason", Text()),
    _mass_check("reserved_mg", nullable=False),
    _mass_check("allocated_consumption_mg"), _mass_check("released_mg"),
    CheckConstraint("reserved_mg > 0", name="positive_claim"),
    CheckConstraint(f"status IN ({_values(ReservationState)})", name="status_enum"),
    CheckConstraint("status NOT IN ('ACTIVE','CONSUMED') OR activated_at IS NOT NULL", name="activation_shape"),
    CheckConstraint("status <> 'RELEASED' OR released_at IS NOT NULL", name="release_shape"),
    CheckConstraint(
        "(status = 'CONSUMED' AND consumed_at IS NOT NULL AND settled_finalization_id IS NOT NULL "
        "AND allocated_consumption_mg IS NOT NULL AND allocated_consumption_mg > 0 "
        "AND released_mg IS NOT NULL AND allocated_consumption_mg + released_mg = reserved_mg) OR "
        "(status <> 'CONSUMED' AND consumed_at IS NULL)", name="consumed_settlement",
    ),
    CheckConstraint(
        "settled_finalization_id IS NULL OR (status IN ('CONSUMED','RELEASED') "
        "AND allocated_consumption_mg IS NOT NULL AND released_mg IS NOT NULL "
        "AND allocated_consumption_mg + released_mg = reserved_mg)", name="settlement_total",
    ),
)
Index("uq_reservation_active_material_spool", reservation.c.spool_id, reservation.c.print_job_material_id,
      unique=True, sqlite_where=reservation.c.status == "ACTIVE")
Index("ix_reservation_spool_status", reservation.c.spool_id, reservation.c.status)
Index("ix_reservation_status_expiry", reservation.c.status, reservation.c.expires_at)

consumption_evidence = Table(
    "consumption_evidence", metadata, *_immutable_columns(),
    _ref("print_job_material_id", "print_job_material"),
    _ref("segment_id", "material_usage_segment", nullable=True),
    Column("source_type", Text(), nullable=False), Column("quantity_kind", Text(), nullable=False),
    Column("mode", Text(), nullable=False), Column("weight_mg", MassType()),
    Column("length_mm", Integer()), Column("confidence_bp", Integer(), nullable=False),
    Column("captured_at", UtcDateTimeType(), nullable=False),
    Column("received_at", UtcDateTimeType(), nullable=False),
    Column("interval_start", UtcDateTimeType()), Column("interval_end", UtcDateTimeType()),
    Column("scope_key", Text(), nullable=False), Column("includes_purge", Boolean(create_constraint=True, name="purge_boolean")),
    _ref("calibration_id", "calibration_record", nullable=True),
    _ref("source_receipt_id", "external_event_receipt", nullable=True),
    Column("external_reference", Text()), *_json("metadata_json"),
    CheckConstraint(f"source_type IN ({_values(EvidenceSource)})", name="source_enum"),
    CheckConstraint(f"mode IN ({_values(EvidenceMode)})", name="mode_enum"),
    CheckConstraint(
        "(quantity_kind='CONSUMED_MASS' AND weight_mg IS NOT NULL AND length_mm IS NULL) OR "
        "(quantity_kind='LENGTH' AND length_mm IS NOT NULL AND weight_mg IS NULL)", name="quantity_shape",
    ),
    _mass_check("weight_mg"),
    CheckConstraint("length_mm IS NULL OR (typeof(length_mm)='integer' AND length_mm >= 0)", name="length_range"),
    CheckConstraint("typeof(confidence_bp)='integer' AND confidence_bp BETWEEN 0 AND 10000", name="confidence_range"),
    CheckConstraint("length(scope_key) BETWEEN 1 AND 500", name="scope_length"),
    CheckConstraint(
        "(interval_start IS NULL AND interval_end IS NULL) OR "
        "(interval_start IS NOT NULL AND interval_end IS NOT NULL AND interval_end >= interval_start)", name="interval_shape",
    ),
)
Index("ix_consumption_evidence_material_captured", consumption_evidence.c.print_job_material_id, consumption_evidence.c.captured_at)

consumption_decision = Table(
    "consumption_decision", metadata, *_immutable_columns(),
    _ref("finalization_record_id", "finalization_record"),
    _ref("material_usage_segment_id", "material_usage_segment"),
    Column("selected_weight_mg", MassType(), nullable=False),
    Column("confidence_bp", Integer(), nullable=False), Column("strategy", Text(), nullable=False),
    Column("policy_version", Text(), nullable=False), *_json("policy_parameters"),
    Column("reason_code", Text(), nullable=False), Column("reason_notes", Text()),
    _ref("resolved_by_device_id", "device_identity", nullable=True),
    Column("finalized_at", UtcDateTimeType(), nullable=False),
    _mass_check("selected_weight_mg", nullable=False),
    CheckConstraint("typeof(confidence_bp)='integer' AND confidence_bp BETWEEN 0 AND 10000", name="confidence_range"),
    CheckConstraint("length(strategy) BETWEEN 1 AND 500 AND length(policy_version) BETWEEN 1 AND 500 AND length(reason_code) BETWEEN 1 AND 500", name="reason_fields"),
    UniqueConstraint("finalization_record_id", "material_usage_segment_id"),
)

decision_evidence = Table(
    "decision_evidence", metadata, *_immutable_columns(),
    _ref("decision_id", "consumption_decision"), _ref("evidence_id", "consumption_evidence"),
    Column("role", Text(), nullable=False), CheckConstraint("length(role) BETWEEN 1 AND 500", name="role_length"),
    UniqueConstraint("decision_id", "evidence_id", "role"),
)

consumption_inventory_evidence = Table(
    "consumption_inventory_evidence", metadata, *_immutable_columns(),
    _ref("consumption_evidence_id", "consumption_evidence"), _ref("inventory_evidence_id", "inventory_evidence"),
    Column("role", Text(), nullable=False), CheckConstraint("length(role) BETWEEN 1 AND 500", name="role_length"),
    UniqueConstraint("consumption_evidence_id", "inventory_evidence_id", "role"),
)

inventory_reconciliation = Table(
    "inventory_reconciliation", metadata, *_immutable_columns(),
    _ref("spool_id", "spool"), _ref("evidence_id", "inventory_evidence"),
    Column("accepted_ledger_cutoff", Integer(), nullable=False),
    Column("previous_effective_mg", MassType()), Column("accepted_remaining_mg", MassType(), nullable=False),
    Column("estimated_before_mg", MassType()), Column("estimated_after_mg", MassType()),
    Column("policy_version", Text(), nullable=False), Column("reason", Text(), nullable=False),
    _ref("actor_device_id", "device_identity"),
    CheckConstraint("typeof(accepted_ledger_cutoff)='integer' AND accepted_ledger_cutoff >= 0", name="cutoff_range"),
    _mass_check("previous_effective_mg", signed=True), _mass_check("accepted_remaining_mg", nullable=False),
    _mass_check("estimated_before_mg", signed=True), _mass_check("estimated_after_mg", signed=True),
    CheckConstraint("length(policy_version) BETWEEN 1 AND 500 AND length(reason) BETWEEN 1 AND 500", name="reason_fields"),
    UniqueConstraint("evidence_id"),
)

for table in (finalization_record, reservation, consumption_evidence, consumption_decision,
              decision_evidence, consumption_inventory_evidence, inventory_reconciliation):
    for column in table.columns:
        if column.foreign_keys and not any(tuple(index.columns)[0] is column for index in table.indexes):
            Index(f"ix_{table.name}_{column.name}", column)
