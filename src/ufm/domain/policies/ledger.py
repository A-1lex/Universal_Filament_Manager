"""Replay validation for a spool's append-only ledger."""

from collections.abc import Iterable

from ufm.domain.entities.ledger import FilamentTransaction


def validate_ledger_history(entries: Iterable[FilamentTransaction]) -> None:
    history = tuple(entries)
    if not history:
        return
    spool_id = history[0].spool_id
    commands: set[tuple[str, int]] = set()
    previous: FilamentTransaction | None = None
    for expected_sequence, entry in enumerate(history, start=1):
        if entry.spool_id != spool_id or entry.sequence != expected_sequence:
            raise ValueError("ledger.history_sequence_invalid")
        command = (entry.command_key, entry.command_item)
        if command in commands:
            raise ValueError("ledger.command_duplicate")
        commands.add(command)
        if previous is not None and entry.previous_effective != previous.new_effective:
            raise ValueError("ledger.history_balance_invalid")
        if previous is not None and entry.previous_estimated != previous.new_estimated:
            raise ValueError("ledger.history_estimate_invalid")
        previous = entry
