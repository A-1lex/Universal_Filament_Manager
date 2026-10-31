"""Trusted identifier binding integrity."""

from collections.abc import Iterable

from ufm.domain.entities.configuration import SpoolIdentifier
from ufm.domain.value_objects import EntityId


def validate_identifier_bindings(identifiers: Iterable[SpoolIdentifier]) -> None:
    bindings: dict[tuple[str, str, str], EntityId] = {}
    for identifier in identifiers:
        if not identifier.is_trusted_current:
            continue
        key = (identifier.namespace, identifier.kind, identifier.value)
        existing = bindings.get(key)
        if existing is not None and existing != identifier.spool_id:
            raise ValueError("spool_identifier.binding_conflict")
        bindings[key] = identifier.spool_id
