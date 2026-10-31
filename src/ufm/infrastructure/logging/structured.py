"""Credential-safe JSON logs using trusted event codes and allowlisted fields.

Pass a stable English identifier as the message and metadata with
``extra={"fields": {...}}``. Free-form messages, exception bodies, tracebacks,
unknown fields, and URLs are deliberately omitted. Register opaque secrets on
the shared RedactionFilter before use. Pattern redaction cannot recognize every
unknown secret: callers must never put arbitrary provider payloads in fields.
This logger is not a replacement for persistent domain audit records.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import re
from datetime import UTC, datetime
from itertools import islice
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .events import SAFE_LOG_EVENT_CODES

_EVENT = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+\Z")
_SENSITIVE = re.compile(
    r"password|passwd|secret|token|access.?code|authorization|cookie|session|credential",
    re.IGNORECASE,
)
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"\b(password|passwd|secret|token|access[_ -]?code|authorization|cookie|session)"
    r"\b\s*[:=]\s*[^,;\n]+",
    re.IGNORECASE,
)
_FIELDS = frozenset({
    "component", "operation", "status", "error_code", "printer_id", "job_id",
    "spool_id", "correlation_id", "attempt", "duration_ms", "count", "details",
})


class RedactionFilter(logging.Filter):
    """Return a safe record copy on Python 3.12, leaving other consumers intact."""

    def __init__(self) -> None:
        super().__init__()
        self._secrets: frozenset[str] = frozenset()

    def register_secret(self, secret: str) -> None:
        if secret:
            self._secrets = self._secrets | {secret}

    def _text(self, value: str) -> str:
        for secret in sorted(self._secrets, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        value = _URL.sub("[REDACTED_URL]", value)
        return _ASSIGNMENT.sub(r"\1=[REDACTED]", value)[:512]

    def sanitize(self, value: object, depth: int = 0) -> object:
        if depth > 6:
            return "[OMITTED]"
        if type(value) is dict:
            result: dict[str, object] = {}
            for key, item in islice(value.items(), 32):
                if type(key) is not str:
                    continue
                if _SENSITIVE.search(key):
                    # Do not echo dynamic keys, which may themselves hold secrets.
                    continue
                if key in _FIELDS:
                    result[key] = self.sanitize(item, depth + 1)
            return result
        if type(value) is list or type(value) is tuple:
            return [self.sanitize(item, depth + 1) for item in value[:32]]
        if type(value) is str:
            return self._text(value)
        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            return value if value.bit_length() <= 64 else "[OMITTED]"
        if type(value) is float and math.isfinite(value):
            return value
        return "[OMITTED]"

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        safe = copy.copy(record)
        event = record.msg
        safe.msg = (
            event if type(event) is str and event in SAFE_LOG_EVENT_CODES
            and _EVENT.fullmatch(event)
            and self._text(event) == event and not record.args else "log_message_omitted"
        )
        safe.args = ()
        safe.exc_info = None
        safe.exc_text = None
        safe.stack_info = None
        safe.__dict__["fields"] = self.sanitize(record.__dict__.get("fields", {}))
        return safe


class SafeJsonFormatter(logging.Formatter):
    """Sanitize again at formatting time, including direct formatter calls."""

    def __init__(self, redaction: RedactionFilter | None = None) -> None:
        super().__init__()
        self.redaction = redaction if redaction is not None else RedactionFilter()

    def format(self, record: logging.LogRecord) -> str:
        safe = self.redaction.filter(record)
        return json.dumps({
            "timestamp": datetime.fromtimestamp(safe.created, UTC).isoformat(),
            "level": logging.getLevelName(safe.levelno),
            "event": safe.msg,
            "fields": safe.__dict__["fields"],
        }, ensure_ascii=True, allow_nan=False)


def configure_logging(log_dir: Path | None = None, level: str = "INFO") -> logging.Logger:
    """Configure console and optional rotating file sinks; never configure root.

    Reconfiguration is intended for application startup, before worker threads.
    Access ``handler.formatter.redaction.register_secret`` to register secrets;
    the formatter and redactor are shared by every handler. Registration is reset
    on reconfiguration. File logs retain up to three 1 MiB backup files.
    """
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Unsupported log level")
    formatter = SafeJsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(
            log_dir / "ufm.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8",
        ))
    logger = logging.getLogger("ufm")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = False
    logger.setLevel(level)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(formatter.redaction)
        logger.addHandler(handler)
    return logger
