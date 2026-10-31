"""Build consent-ready diagnostic data without exporting identifiers or raw fields."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime

from ufm.infrastructure.logging.events import SAFE_LOG_EVENT_CODES

_MAX_LOG_BYTES = 512 * 1024
_MAX_EVENTS = 300
_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_EVENT = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+\Z")


def build_safe_diagnostic_bundle(log_bytes: bytes, generated_at: datetime) -> bytes:
    """Return bounded JSON containing only validated timestamp, level and event codes."""
    if (
        type(log_bytes) is not bytes
        or len(log_bytes) > _MAX_LOG_BYTES
        or not isinstance(generated_at, datetime)
        or generated_at.tzinfo is None
    ):
        raise ValueError("diagnostics.input_invalid")

    lines = log_bytes.splitlines()
    selected = lines[-_MAX_EVENTS:]
    omitted = len(lines) - len(selected)
    events: list[dict[str, str]] = []
    for raw_line in selected:
        try:
            record = json.loads(raw_line.decode("utf-8"))
            timestamp = record.get("timestamp") if isinstance(record, dict) else None
            level = record.get("level") if isinstance(record, dict) else None
            event = record.get("event") if isinstance(record, dict) else None
            if (
                not isinstance(timestamp, str)
                or len(timestamp) > 40
                or level not in _LEVELS
                or not isinstance(event, str)
                or len(event) > 80
                or event not in SAFE_LOG_EVENT_CODES
                or _EVENT.fullmatch(event) is None
            ):
                raise ValueError("diagnostics.record_invalid")
            parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                raise ValueError("diagnostics.timestamp_invalid")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            omitted += 1
            continue
        events.append({
            "timestamp": parsed_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "level": level,
            "event": event,
        })

    canonical_events = json.dumps(
        events, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    payload = {
        "manifest": {
            "schema": "ufm-diagnostics-v1",
            "createdAt": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "includedRecords": len(events),
            "omittedRecords": omitted,
            "eventsSha256": hashlib.sha256(canonical_events).hexdigest(),
        },
        "events": events,
    }
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
