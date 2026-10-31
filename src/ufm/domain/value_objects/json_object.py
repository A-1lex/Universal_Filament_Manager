"""Bounded JSON object values used by immutable evidence and ledger records."""

import json
import math
from typing import Any


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("json_object.invalid")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("json_object.invalid")


def json_object(value: str) -> dict[str, Any]:
    if type(value) is not str or len(value) > 65536:
        raise ValueError("json_object.invalid")
    try:
        result = json.loads(value, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError):
        raise ValueError("json_object.invalid") from None
    if not isinstance(result, dict):
        raise ValueError("json_object.invalid")
    pending: list[tuple[Any, int]] = [(result, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("json_object.invalid")
        if isinstance(item, dict):
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            pending.extend((value, depth + 1) for value in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("json_object.invalid")
    return result
