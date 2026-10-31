"""Hierarchical storage integrity."""

from collections.abc import Iterable

from ufm.domain.entities.catalog import StorageLocation


def validate_storage_tree(locations: Iterable[StorageLocation]) -> None:
    by_id = {location.id: location for location in locations}
    for location in by_id.values():
        visited = {location.id}
        parent_id = location.parent_id
        while parent_id is not None and parent_id in by_id:
            if parent_id in visited:
                raise ValueError("storage.cycle")
            visited.add(parent_id)
            parent_id = by_id[parent_id].parent_id
