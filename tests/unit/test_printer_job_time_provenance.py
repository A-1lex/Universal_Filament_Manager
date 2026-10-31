import unittest
from datetime import UTC, datetime

from ufm.application.dto.providers import PrintJobSnapshot
from ufm.domain.enums import PrintStatus
from ufm.domain.value_objects import UtcDateTime


class PrintJobStartTimeProvenanceTests(unittest.TestCase):
    def snapshot(self, **changes: object) -> PrintJobSnapshot:
        values: dict[str, object] = {
            "source": "BAMBU_LAN",
            "source_epoch": "epoch-1",
            "status": PrintStatus.RUNNING,
            "observed_at": UtcDateTime(datetime(2026, 10, 28, 12, tzinfo=UTC)),
            "received_at": UtcDateTime(datetime(2026, 10, 28, 12, tzinfo=UTC)),
        }
        values.update(changes)
        return PrintJobSnapshot(**values)  # type: ignore[arg-type]

    def test_timestamp_and_explicit_source_are_required_as_a_pair(self) -> None:
        started_at = UtcDateTime(datetime(2026, 10, 28, 11, tzinfo=UTC))
        for changes in (
            {"exact_started_at": started_at},
            {"exact_started_at_source": "printer_reported"},
            {"exact_started_at": started_at, "exact_started_at_source": "adapter_observed"},
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                ValueError, "job_snapshot.start_time_provenance_required"
            ):
                self.snapshot(**changes)

    def test_source_reported_timestamp_is_accepted(self) -> None:
        started_at = UtcDateTime(datetime(2026, 10, 28, 11, tzinfo=UTC))
        snapshot = self.snapshot(
            exact_started_at=started_at,
            exact_started_at_source="printer_reported",
        )
        self.assertEqual(snapshot.exact_started_at, started_at)
