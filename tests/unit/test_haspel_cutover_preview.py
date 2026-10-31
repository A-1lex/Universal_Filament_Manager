"""Isolated tests for the read-only HaspelSync cutover journal preview."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ufm.integrations.haspelsync.cutover_preview import (
    HaspelCutoverPreviewRejected,
    preview_haspelsync_cutover,
)


def _digest(char: str) -> str:
    return char * 64


def _booking(
    identity: str, printer: str, spool_id: int, status: str,
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": identity,
        "requestHash": _digest("a"),
        "source": _digest("b"),
        "printerId": printer,
        "itemKey": "job-1:slot-0",
        "grams": 3.25,
        "startedAt": 1_700_000_000_000,
        "createdAt": 1_700_000_000_001,
        "updatedAt": 1_700_000_000_002,
        "spoolId": spool_id,
        "status": status,
    }
    if status == "booked":
        record["result"] = {"id": spool_id}
    return record


def _write_journals(
    tmp_path: Path,
    *,
    bookings: dict[str, object] | None = None,
    weighings: list[object] | None = None,
) -> tuple[Path, Path]:
    booking_path = tmp_path / "bookings.json"
    accounting_path = tmp_path / "accounting.json"
    booking_path.write_text(json.dumps({
        "schemaVersion": 1,
        "records": bookings or {},
    }), encoding="utf-8")
    accounting_path.write_text(json.dumps({
        "schemaVersion": 1,
        "profiles": {},
        "weighings": weighings or [],
    }), encoding="utf-8")
    return booking_path, accounting_path


def _weighing(status: str, identity: str, spool_id: int) -> dict[str, object]:
    return {
        "id": identity,
        "requestHash": _digest("c"),
        "source": _digest("d"),
        "spoolId": spool_id,
        "netMilligrams": 425_000,
        "status": status,
        "createdAt": 1_700_000_000_003,
    }


def test_preview_counts_confirmed_and_uncertain_rows_for_selected_printer(
    tmp_path: Path,
) -> None:
    records = {
        _digest("1"): _booking(_digest("1"), "  printer-a  ", 7, "booked"),
        _digest("2"): _booking(_digest("2"), "PRINTER-A", 7, "uncertain"),
        _digest("3"): _booking(_digest("3"), "printer-b", 8, "pending"),
    }
    paths = _write_journals(
        tmp_path,
        bookings=records,
        weighings=[
            _weighing("recorded", "weigh-1", 7),
            _weighing("uncertain", "weigh-2", 7),
            _weighing("rejected", "weigh-3", 8),
        ],
    )

    preview = preview_haspelsync_cutover(*paths, "printer-a")

    assert preview.printer_serial == "PRINTER-A"
    assert preview.printer_bookings == (0, 1, 1, 0)
    assert preview.global_weighings == (0, 1, 1, 1)
    assert preview.unresolved_count == 2
    assert preview.ready is False
    assert len(preview.evidence_sha256) == 64
    assert str(tmp_path) not in repr(preview)


def test_preview_ready_requires_no_pending_or_uncertain_work(tmp_path: Path) -> None:
    paths = _write_journals(
        tmp_path,
        bookings={
            _digest("4"): _booking(_digest("4"), "printer-a", 7, "booked"),
            _digest("5"): _booking(_digest("5"), "printer-a", 7, "dismissed"),
        },
        weighings=[_weighing("recorded", "weigh-4", 7),
                   _weighing("rejected", "weigh-5", 7)],
    )

    preview = preview_haspelsync_cutover(*paths, "PRINTER-A")

    assert preview.unresolved_count == 0
    assert preview.ready is True


@pytest.mark.parametrize(
    ("booking_status", "result"),
    [("future", None), ("booked", {"id": 999})],
)
def test_preview_rejects_unsupported_or_inconsistent_booking(
    tmp_path: Path, booking_status: str, result: object,
) -> None:
    booking = _booking(_digest("6"), "printer-a", 7, "pending")
    booking["status"] = booking_status
    if result is not None:
        booking["result"] = result
    paths = _write_journals(tmp_path, bookings={_digest("6"): booking})

    with pytest.raises(HaspelCutoverPreviewRejected):
        preview_haspelsync_cutover(*paths, "printer-a")


def test_preview_evidence_digest_tracks_both_source_journals(tmp_path: Path) -> None:
    paths = _write_journals(
        tmp_path,
        bookings={_digest("7"): _booking(_digest("7"), "printer-a", 7, "booked")},
    )
    first = preview_haspelsync_cutover(*paths, "printer-a")
    accounting = json.loads(paths[1].read_text(encoding="utf-8"))
    accounting["profiles"]["profile"] = {
        "spoolId": 7,
        "priceMinor": 1,
        "basisMilligrams": 1_000,
        "currency": "UAH",
        "revision": 1,
        "source": _digest("e"),
    }
    paths[1].write_text(json.dumps(accounting), encoding="utf-8")

    second = preview_haspelsync_cutover(*paths, "printer-a")

    assert first.evidence_sha256 != second.evidence_sha256
