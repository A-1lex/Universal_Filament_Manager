"""Diagnostics export contains only bounded, allowlisted log event metadata."""

import hashlib
import json
import unittest
from datetime import UTC, datetime

from ufm.infrastructure.diagnostics import build_safe_diagnostic_bundle


class SafeDiagnosticBundleTests(unittest.TestCase):
    def test_bundle_omits_log_fields_paths_and_credentials(self) -> None:
        raw = json.dumps({
            "timestamp": "2026-10-30T12:00:00+02:00",
            "level": "ERROR",
            "event": "foundation_started",
            "fields": {
                "printer_id": "serial-secret",
                "details": "https://user:password@example.invalid/private?token=secret",
                "path": "C:/Users/private/profile",
            },
        }).encode("utf-8")
        result = build_safe_diagnostic_bundle(raw, datetime(2026, 10, 30, tzinfo=UTC))
        bundle = json.loads(result)

        self.assertEqual(bundle["manifest"]["schema"], "ufm-diagnostics-v1")
        self.assertEqual(bundle["manifest"]["includedRecords"], 1)
        self.assertEqual(bundle["manifest"]["omittedRecords"], 0)
        self.assertEqual(bundle["events"], [{
            "timestamp": "2026-10-30T10:00:00Z",
            "level": "ERROR",
            "event": "foundation_started",
        }])
        expected_hash = hashlib.sha256(
            b'[{"event":"foundation_started","level":"ERROR","timestamp":"2026-10-30T10:00:00Z"}]'
        ).hexdigest()
        self.assertEqual(bundle["manifest"]["eventsSha256"], expected_hash)
        self.assertNotIn(b"serial-secret", result)
        self.assertNotIn(b"password", result)
        self.assertNotIn(b"private/profile", result)

    def test_invalid_lines_are_counted_but_never_exported(self) -> None:
        valid = json.dumps({
            "timestamp": "2026-10-30T12:00:00Z",
            "level": "INFO",
            "event": "startup_validated",
            "fields": {"details": "secret-field"},
        }).encode("utf-8")
        content = b"not-json\n" + b"\n".join(
            valid for _ in range(305)
        )
        bundle = json.loads(
            build_safe_diagnostic_bundle(content, datetime(2026, 10, 30, tzinfo=UTC)),
        )
        self.assertEqual(bundle["manifest"]["includedRecords"], 300)
        self.assertEqual(bundle["manifest"]["omittedRecords"], 6)
        self.assertNotIn("fields", bundle["events"][0])
        invalid_tail = build_safe_diagnostic_bundle(
            b"not-json\n" + valid, datetime(2026, 10, 30, tzinfo=UTC),
        )
        invalid_bundle = json.loads(invalid_tail)
        self.assertEqual(invalid_bundle["manifest"]["includedRecords"], 1)
        self.assertEqual(invalid_bundle["manifest"]["omittedRecords"], 1)

    def test_rejects_oversized_or_naive_inputs(self) -> None:
        with self.assertRaises(ValueError):
            build_safe_diagnostic_bundle(b"x" * (512 * 1024 + 1), datetime.now(UTC))
        with self.assertRaises(ValueError):
            build_safe_diagnostic_bundle(b"", datetime(2026, 10, 30))

    def test_unknown_well_formed_event_code_is_omitted(self) -> None:
        raw = json.dumps({
            "timestamp": "2026-10-30T12:00:00Z",
            "level": "INFO",
            "event": "printer_serial_123456",
            "fields": {},
        }).encode("utf-8")
        result = build_safe_diagnostic_bundle(raw, datetime(2026, 10, 30, tzinfo=UTC))
        bundle = json.loads(result)
        self.assertEqual(bundle["manifest"]["includedRecords"], 0)
        self.assertEqual(bundle["manifest"]["omittedRecords"], 1)
        self.assertEqual(bundle["events"], [])
        self.assertNotIn(b"printer_serial_123456", result)


if __name__ == "__main__":
    unittest.main()
