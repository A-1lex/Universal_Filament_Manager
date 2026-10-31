"""Lossless SQLAlchemy mappings for domain boundary values."""

from typing import Any

from sqlalchemy import BigInteger, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime


class EntityIdType(TypeDecorator[EntityId]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: EntityId | None, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, EntityId):
            raise TypeError("identity.invalid")
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> EntityId | None:
        del dialect
        if value is None:
            return None
        return EntityId.parse(value)


class UtcDateTimeType(TypeDecorator[UtcDateTime]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: UtcDateTime | None, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, UtcDateTime):
            raise TypeError("time.invalid")
        return value.isoformat()

    def process_result_value(self, value: Any, dialect: Dialect) -> UtcDateTime | None:
        del dialect
        if value is None:
            return None
        return UtcDateTime.parse(value)


class ExactDecimalType(TypeDecorator[ExactDecimal]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: ExactDecimal | None, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, ExactDecimal):
            raise TypeError("decimal.invalid")
        return value.canonical()

    def process_result_value(self, value: Any, dialect: Dialect) -> ExactDecimal | None:
        del dialect
        if value is None:
            return None
        return ExactDecimal.parse(value)


class MassType(TypeDecorator[Mass]):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Mass | None, dialect: Dialect) -> int | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, Mass):
            raise TypeError("mass.milligrams_invalid")
        return value.milligrams

    def process_result_value(self, value: Any, dialect: Dialect) -> Mass | None:
        del dialect
        if value is None:
            return None
        return Mass(value)
