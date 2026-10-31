"""Shared metadata and column conventions for schema-v1 modules."""

from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, MetaData

from ufm.infrastructure.persistence.models.types import EntityIdType, UtcDateTimeType

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _values(enum_type: Any) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


def _mutable_columns() -> list[Any]:
    return [
        Column("id", EntityIdType(), primary_key=True),
        Column(
            "device_id",
            EntityIdType(),
            ForeignKey("device_identity.id", ondelete="RESTRICT", onupdate="RESTRICT"),
            nullable=False,
        ),
        Column("created_at", UtcDateTimeType(), nullable=False),
        Column("updated_at", UtcDateTimeType(), nullable=False),
        Column("revision", Integer(), nullable=False),
        Column("deleted_at", UtcDateTimeType()),
        CheckConstraint("typeof(revision) = 'integer' AND revision >= 1", name="revision_valid"),
        CheckConstraint("length(created_at) = 27 AND length(updated_at) = 27", name="times_valid"),
        CheckConstraint("updated_at >= created_at", name="time_order"),
        CheckConstraint("deleted_at IS NULL OR deleted_at >= created_at", name="deletion_time"),
    ]


def _immutable_columns() -> list[Any]:
    return [
        Column("id", EntityIdType(), primary_key=True),
        Column(
            "device_id",
            EntityIdType(),
            ForeignKey("device_identity.id", ondelete="RESTRICT", onupdate="RESTRICT"),
            nullable=False,
        ),
        Column("created_at", UtcDateTimeType(), nullable=False),
        CheckConstraint("length(created_at) = 27", name="created_at_format"),
    ]


