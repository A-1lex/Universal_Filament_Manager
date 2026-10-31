import unittest
from datetime import UTC, datetime, timedelta, timezone

from ufm.domain.value_objects import EntityId, UtcDateTime


class IdentityTests(unittest.TestCase):
    def test_new_identity_is_canonical_and_roundtrips(self) -> None:
        identity = EntityId.new()
        self.assertEqual(EntityId.parse(str(identity)), identity)

    def test_noncanonical_or_invalid_identity_is_rejected(self) -> None:
        canonical = str(EntityId.new())
        for value in (canonical.upper(), "not-a-uuid", "{" + canonical + "}"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EntityId.parse(value)


class UtcDateTimeTests(unittest.TestCase):
    def test_aware_offset_is_normalized_to_utc(self) -> None:
        source = datetime(2026, 9, 10, 15, tzinfo=timezone(timedelta(hours=3)))
        timestamp = UtcDateTime(source)
        self.assertEqual(timestamp.isoformat(), "2026-09-10T12:00:00.000000Z")
        self.assertEqual(UtcDateTime.parse(timestamp.isoformat()), timestamp)
        self.assertIs(timestamp.value.tzinfo, UTC)

    def test_naive_and_non_utc_serialized_timestamps_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            UtcDateTime(datetime(2026, 9, 10))
        for value in (
            "2026-09-10T12:00:00",
            "2026-09-10T12:00:00Z",
            "2026-09-10T15:00:00.000000+03:00",
            "invalidZ",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                UtcDateTime.parse(value)

    def test_canonical_text_sorts_chronologically_within_one_second(self) -> None:
        earlier = UtcDateTime(datetime(2026, 9, 10, 12, microsecond=0, tzinfo=UTC))
        later = UtcDateTime(datetime(2026, 9, 10, 12, microsecond=1, tzinfo=UTC))
        self.assertLess(earlier.isoformat(), later.isoformat())
