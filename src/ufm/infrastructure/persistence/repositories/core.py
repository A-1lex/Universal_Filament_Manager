"""Typed entity mapping without exposing SQL to application/domain code."""

from dataclasses import fields
from enum import Enum
from typing import Any, Never, get_type_hints

from sqlalchemy import Table, insert, select, update
from sqlalchemy.engine import Connection, CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql import Executable

from ufm.application.ports.persistence import (
    IdempotencyConflict,
    NotFound,
    PersistenceError,
    PersistenceUnavailable,
    RevisionConflict,
)


class Transaction:
    def __init__(self) -> None:
        self.connection: Connection | None = None
        self.failed = False
        self.inventory_ids: set[Any] = set()

    def fail(self, error: PersistenceError) -> Never:
        self.failed = True
        raise error from None

    def execute(self, statement: Executable, *, unique: bool = False) -> CursorResult[Any]:
        if self.connection is None or self.failed:
            raise PersistenceUnavailable()
        try:
            return self.connection.execute(statement)
        except IntegrityError as error:
            duplicate = getattr(error.orig, "sqlite_errorname", "") in {
                "SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_PRIMARYKEY",
            }
            self.fail(IdempotencyConflict() if unique and duplicate else PersistenceError())
        except SQLAlchemyError:
            self.fail(PersistenceUnavailable())


class MappedRepository[T]:
    def __init__(self, transaction: Transaction, table: Table, entity_type: type[T], renames: dict[str, str] | None = None) -> None:
        self.transaction, self.table, self.entity_type = transaction, table, entity_type
        self.renames = renames or {}
        self.hints = get_type_hints(entity_type)

    def values(self, entity: T) -> dict[str, Any]:
        return {
            self.renames.get(field.name, field.name):
            value.value if isinstance(value := getattr(entity, field.name), Enum) else value
            for field in fields(entity)  # type: ignore[arg-type]
        }

    def entity(self, row: RowMapping) -> T:
        values: dict[str, Any] = {}
        for field in fields(self.entity_type):  # type: ignore[arg-type]
            value = row[self.renames.get(field.name, field.name)]
            hint = self.hints[field.name]
            if isinstance(hint, type) and issubclass(hint, Enum):
                value = hint(value)
            values[field.name] = value
        return self.entity_type(**values)

    def get(self, entity_id: Any) -> T:
        result = self.transaction.execute(select(self.table).where(self.table.c.id == entity_id)).mappings().one_or_none()
        if result is None:
            raise NotFound()
        return self.entity(result)

    def add(self, entity: T) -> None:
        self.transaction.execute(insert(self.table).values(**self.values(entity)))

    def save(self, entity: T, expected_revision: int) -> None:
        if type(expected_revision) is not int or expected_revision < 1 or getattr(entity, "revision", None) != expected_revision + 1:
            self.transaction.fail(RevisionConflict())
        values = self.values(entity)
        identifier = values.pop("id")
        result = self.transaction.execute(update(self.table).where(
            self.table.c.id == identifier, self.table.c.revision == expected_revision,
        ).values(**values))
        if result.rowcount != 1:
            self.transaction.fail(RevisionConflict())
