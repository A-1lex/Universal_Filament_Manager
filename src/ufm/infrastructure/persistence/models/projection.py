"""Durable job facts and immutable receipt application history."""

from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Table, Text

from ufm.infrastructure.persistence.models.common import (
    _immutable_columns,
    _mutable_columns,
    metadata,
)
from ufm.infrastructure.persistence.models.types import EntityIdType, UtcDateTimeType


def _reference(name: str, table: str, *, nullable: bool = False) -> Column[Any]:
    return Column(name, EntityIdType(), ForeignKey(f"{table}.id", ondelete="RESTRICT",
                                                onupdate="RESTRICT"), nullable=nullable)


job_projection_state = Table(
    "job_projection_state", metadata, *_mutable_columns(),
    _reference("print_job_id", "print_job"),
    _reference("last_receipt_id", "external_event_receipt"),
    Column("observed_state", Text(), nullable=False),
    Column("observed_at", UtcDateTimeType(), nullable=False),
    Column("source_sequence", Integer(), nullable=False),
    Column("completed_layers", Integer()),
    _reference("first_terminal_receipt_id", "external_event_receipt", nullable=True),
    Column("first_terminal_state", Text()),
    Column("terminal_seen_at", UtcDateTimeType()),
    CheckConstraint("observed_state IN ('started','running','paused','completed','failed','cancelled')",
                    name="observed_state_enum"),
    CheckConstraint("length(observed_at) = 27", name="observed_at_format"),
    CheckConstraint("typeof(source_sequence) = 'integer' AND source_sequence BETWEEN 0 AND 1000000000000",
                    name="source_sequence_range"),
    CheckConstraint("completed_layers IS NULL OR (typeof(completed_layers) = 'integer' "
                    "AND completed_layers BETWEEN 0 AND 1000000000000)", name="completed_layers_range"),
    CheckConstraint("first_terminal_state IS NULL OR first_terminal_state IN ('completed','failed','cancelled')",
                    name="terminal_state_enum"),
    CheckConstraint("(first_terminal_receipt_id IS NULL AND first_terminal_state IS NULL AND terminal_seen_at IS NULL "
                    "AND observed_state IN ('started','running','paused')) "
                    "OR (first_terminal_receipt_id IS NOT NULL AND first_terminal_state IS NOT NULL "
                    "AND terminal_seen_at IS NOT NULL AND length(terminal_seen_at) = 27 "
                    "AND first_terminal_state = observed_state AND terminal_seen_at = observed_at)", name="terminal_shape"),
)
Index("uq_job_projection_state_print_job_id", job_projection_state.c.print_job_id, unique=True)
Index("ix_job_projection_state_device_id", job_projection_state.c.device_id)

job_receipt_application = Table(
    "job_receipt_application", metadata, *_immutable_columns(),
    _reference("receipt_id", "external_event_receipt"),
    _reference("print_job_id", "print_job"),
    Column("contract_version", Text(), nullable=False),
    Column("outcome", Text(), nullable=False),
    Column("reason_code", Text(), nullable=False),
    Column("request_hash", Text(), nullable=False),
    CheckConstraint("contract_version = 'job-receipt-projection-v1'", name="contract_version"),
    CheckConstraint("outcome IN ('APPLIED','IGNORED_STALE','CONFLICT')", name="outcome_enum"),
    CheckConstraint("length(reason_code) BETWEEN 1 AND 200", name="reason_code_length"),
    CheckConstraint("length(request_hash) = 64 AND request_hash NOT GLOB '*[^0-9a-f]*'",
                    name="request_hash_format"),
)
Index("uq_job_receipt_application_receipt_id", job_receipt_application.c.receipt_id, unique=True)
Index("ix_job_receipt_application_print_job_id", job_receipt_application.c.print_job_id)
Index("ix_job_receipt_application_device_id", job_receipt_application.c.device_id)
