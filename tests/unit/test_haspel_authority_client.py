"""No-network contract checks for the bounded Haspel authority client."""

import json
import unittest
from http.client import HTTPMessage
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from ufm.application.ports.secrets import SecretValue
from ufm.integrations.haspelsync.authority_client import (
    HaspelAuthorityClient,
    HaspelAuthorityConflict,
    HaspelAuthorityUnavailable,
    HaspelBookingResolutionUnknown,
)


class HaspelAuthorityClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.printer_id = "printer/#1"
        self.secret = "test-api-key-never-sent-to-network"
        self.client = HaspelAuthorityClient(
            "http://127.0.0.1:8765", self.printer_id, SecretValue(self.secret)
        )

    def response(self, payload: object) -> MagicMock:
        result = MagicMock()
        result.__enter__.return_value = result
        result.__exit__.return_value = False
        result.read.return_value = json.dumps(payload).encode("utf-8")
        return result

    def payload(self, **overrides: object) -> dict[str, object]:
        authority: dict[str, object] = {
            "capabilityVersion": 1,
            "printerId": self.printer_id,
            "owner": "LEGACY_ACTIVE",
            "revision": 4,
            "pendingCount": 0,
            "uncertainCount": 0,
            "activeCount": 0,
        }
        authority.update(overrides)
        return {"ok": True, "authority": authority}

    def test_read_uses_encoded_printer_scope_and_validates_snapshot(self) -> None:
        result = self.response(self.payload())
        with patch.object(self.client._opener, "open", return_value=result) as open_request:
            snapshot = self.client.read()

        request = open_request.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("/printer%2F%231/accounting-authority", request.full_url)
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.secret}")
        self.assertEqual(snapshot.printer_id, self.printer_id)
        self.assertEqual((snapshot.owner, snapshot.revision), ("LEGACY_ACTIVE", 4))

    def test_transfer_sends_revision_cas_and_requires_matching_response(self) -> None:
        result = self.response(self.payload(owner="UFM_ACTIVE", revision=5))
        with patch.object(self.client._opener, "open", return_value=result) as open_request:
            snapshot = self.client.transfer("UFM_ACTIVE", 4)

        request = open_request.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(body["owner"], "UFM_ACTIVE")
        self.assertEqual(body["expectedRevision"], 4)
        self.assertTrue(body["requestId"])
        self.assertEqual((snapshot.owner, snapshot.revision), ("UFM_ACTIVE", 5))

    def test_rejects_wrong_printer_and_boolean_revision(self) -> None:
        with patch.object(
            self.client._opener,
            "open",
            return_value=self.response(self.payload(printerId="another-printer")),
        ):
            with self.assertRaises(HaspelAuthorityUnavailable):
                self.client.read()
        with self.assertRaises(HaspelAuthorityUnavailable):
            self.client.transfer("UFM_ACTIVE", True)

    def test_http_409_is_a_conflict_without_server_detail(self) -> None:
        error = HTTPError(
            "http://127.0.0.1/", 409, "conflict", HTTPMessage(), None
        )
        with patch.object(self.client._opener, "open", side_effect=error):
            with self.assertRaises(HaspelAuthorityConflict) as caught:
                self.client.read()
        self.assertEqual(str(caught.exception), "haspelsync.authority_conflict")

    def test_cleartext_is_limited_to_loopback(self) -> None:
        with self.assertRaises(HaspelAuthorityUnavailable):
            HaspelAuthorityClient("http://192.168.1.25:8080", "P1", SecretValue("key"))

    def booking(self, **overrides: object) -> dict[str, object]:
        record: dict[str, object] = {
            "id": "a" * 64,
            "printerId": self.printer_id,
            "startedAt": 1_700_000_000_000,
            "itemKey": "plate-1:filament-2",
            "spoolId": 42,
            "grams": 3.25,
            "jobName": "part.3mf",
            "terminalState": "FINISH",
            "status": "uncertain",
            "createdAt": 1_700_000_000_100,
            "updatedAt": 1_700_000_000_200,
        }
        record.update(overrides)
        return record

    def booking_response(self, record: dict[str, object]) -> MagicMock:
        return self.response({"ok": True, "bookings": [record]})

    def test_lists_only_validated_printer_scoped_booking_records(self) -> None:
        with patch.object(
            self.client._opener,
            "open",
            return_value=self.booking_response(self.booking()),
        ) as open_request:
            records = self.client.list_bookings()

        request = open_request.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.endswith("/api/print/printer%2F%231/bookings"))
        self.assertEqual(records[0].status, "uncertain")
        self.assertEqual(records[0].spool_id, 42)
        self.assertEqual(records[0].grams, 3.25)

    def test_rejects_malformed_or_cross_printer_booking_data(self) -> None:
        for invalid in (
            self.booking(printerId="other"),
            self.booking(spoolId=True),
            self.booking(grams=float("nan")),
            self.booking(status=[]),
        ):
            with self.subTest(invalid=invalid):
                with patch.object(
                    self.client._opener,
                    "open",
                    return_value=self.booking_response(invalid),
                ):
                    with self.assertRaises(HaspelAuthorityUnavailable):
                        self.client.list_bookings()

    def test_resolution_confirms_by_read_without_replaying_a_lost_post(self) -> None:
        pending = self.booking()
        resolved = self.booking(
            status="booked", resolution="applied", resolutionNote="Verified in Spoolman",
        )
        responses = [
            self.booking_response(pending),
            URLError("response lost after write"),
            self.booking_response(resolved),
        ]
        with patch.object(self.client._opener, "open", side_effect=responses) as open_request:
            record = self.client.resolve_booking(
                "a" * 64, "applied", "Verified in Spoolman",
            )

        requests = [call.args[0] for call in open_request.call_args_list]
        self.assertEqual([request.get_method() for request in requests], ["GET", "POST", "GET"])
        self.assertEqual(json.loads(requests[1].data.decode("utf-8")), {
            "resolution": "applied", "note": "Verified in Spoolman",
        })
        self.assertEqual(record.status, "booked")

    def test_unknown_resolution_is_not_reposted_when_readback_is_unresolved(self) -> None:
        pending = self.booking()
        responses = [
            self.booking_response(pending),
            URLError("response lost"),
            self.booking_response(pending),
        ]
        with patch.object(self.client._opener, "open", side_effect=responses) as open_request:
            with self.assertRaises(HaspelBookingResolutionUnknown):
                self.client.resolve_booking("a" * 64, "applied", "Checked manually")
        self.assertEqual(
            [call.args[0].get_method() for call in open_request.call_args_list],
            ["GET", "POST", "GET"],
        )

    def test_successful_post_with_unavailable_confirmation_is_reported_unknown(self) -> None:
        pending = self.booking()
        responses = [
            self.booking_response(pending),
            self.response({"ok": True}),
            URLError("readback unavailable"),
        ]
        with patch.object(self.client._opener, "open", side_effect=responses) as open_request:
            with self.assertRaises(HaspelBookingResolutionUnknown):
                self.client.resolve_booking("a" * 64, "not_applied", "Verified no debit")
        self.assertEqual(
            [call.args[0].get_method() for call in open_request.call_args_list],
            ["GET", "POST", "GET"],
        )


if __name__ == "__main__":
    unittest.main()
