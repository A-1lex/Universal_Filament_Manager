import io
import json
import logging
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from ufm.infrastructure.logging import RedactionFilter, SafeJsonFormatter, configure_logging


class LoggingTests(unittest.TestCase):
    def test_nested_fields_urls_registered_secrets_and_unknown_payloads_are_safe(self):
        redactor = RedactionFilter()
        redactor.register_secret("opaque-private-value")
        record = logging.makeLogRecord({
            "msg": "startup_validated", "levelno": logging.ERROR,
            "fields": {
                "details": {"password": "private-password", "Authorization": "Bearer private",
                            "status": "opaque-private-value", "access_code": "private-code",
                            "cookie": "private-cookie", "raw": "private-payload"},
                "operation": "https://user:private@host/api?token=private-token",
                "status": "token=private-token",
            },
        })
        output = SafeJsonFormatter(redactor).format(record)
        assert "private" not in output
        assert "[REDACTED_URL]" in output
        assert json.loads(output)["timestamp"].endswith("+00:00")
        assert record.fields["details"]["password"] == "private-password"


    def test_exception_and_stack_payloads_are_never_rendered(self):
        try:
            raise RuntimeError("password=private-body")
        except RuntimeError:
            import sys
            record = logging.makeLogRecord({
                "msg": "startup_validated", "levelno": logging.ERROR,
                "exc_info": sys.exc_info(), "exc_text": "private-cached",
                "stack_info": "private-stack",
                "fields": {"details": RuntimeError("private-object")},
            })
        output = SafeJsonFormatter().format(record)
        assert "private" not in output
        assert record.exc_info is not None


    def test_raw_messages_are_omitted(self):
        for message, args in (
            ("password=private", ()),
            ("printer_serial_123456", ()),
            ("startup_validated %s", ("private",)),
        ):
            record = logging.makeLogRecord({"msg": message, "args": args, "levelno": 20})
            assert json.loads(SafeJsonFormatter().format(record))["event"] == "log_message_omitted"


    def test_console_and_rotating_file_use_same_policy_and_reconfigure(self):
        root_handlers = logging.getLogger().handlers[:]
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()) as console:
            log_dir = Path(directory)
            logger = configure_logging(log_dir)
            try:
                old_handlers = logger.handlers[:]
                formatter = logger.handlers[0].formatter
                assert isinstance(formatter, SafeJsonFormatter)
                formatter.redaction.register_secret("opaque-private-value")
                logger.info("foundation_started", extra={"fields": {"status": "opaque-private-value"}})
                file_output = (log_dir / "ufm.log").read_text(encoding="utf-8")
                assert console.getvalue() == file_output
                assert "opaque-private-value" not in file_output
                configure_logging()
                assert len(logger.handlers) == 1
                assert old_handlers[1].stream is None
                assert logging.getLogger().handlers == root_handlers
                assert not logger.propagate
            finally:
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()


    def test_unbounded_numbers_and_recursive_fields_are_omitted(self):
        fields = {"count": 10 ** 10000}
        fields["details"] = fields
        record = logging.makeLogRecord({"msg": "startup_validated", "levelno": 20, "fields": fields})
        parsed = json.loads(SafeJsonFormatter().format(record))
        assert parsed["fields"]["count"] == "[OMITTED]"
