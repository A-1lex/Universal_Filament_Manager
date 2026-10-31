"""Same-job 3MF/receipt/provider slot join never guesses an accounting target."""

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ufm.application.dto.providers import (
    FeedSlotSnapshot,
    FeedSystemSnapshot,
    Observed,
    PrinterStatusSnapshot,
)
from ufm.application.dto.slice_facts import FilamentFact, LayerFilamentFact, VerifiedSliceFacts
from ufm.application.dto.worker_protocol import JobMessage
from ufm.application.job_material_mapping import (
    JobMaterialMappingState as State,
)
from ufm.application.job_material_mapping import (
    resolve_job_material_slots,
)
from ufm.domain.enums import Availability, ConnectionState, FeedSystemKind
from ufm.domain.value_objects import EntityId, UtcDateTime

AT = UtcDateTime(datetime(2026, 10, 28, 12, tzinfo=UTC))
DIGEST = "a" * 64


def observed(value):
    return Observed(
        Availability.KNOWN if value is not None else Availability.UNKNOWN, AT, AT, value
    )


def slot(key="tray-0", occupied=True):
    return FeedSlotSnapshot(
        key,
        observed(occupied),
        observed("private-tray"),
        observed("private-tag"),
        observed(None),
        observed(None),
    )


def facts(*, logical=(0,), mass=1000, layers=()):
    return VerifiedSliceFacts(
        parser_version="test",
        file_sha256=DIGEST,
        plate=1,
        metadata_sha256="b" * 64,
        gcode_sha256="c" * 64,
        filaments=tuple(
            FilamentFact(item + 1, item, "1", mass, None, None, None, None) for item in logical
        ),
        layer_filaments=tuple(layers),
        metadata=(),
        normalized_xml="",
        gcode_bytes=b"",
    )


def job(*, digest=DIGEST, mappings=()):
    return JobMessage(
        v=1,
        request_id="request-1",
        printer_id=PRINTER_UUID,
        source_epoch="epoch-1",
        sequence=1,
        observed_at=AT.value,
        kind="job",
        occurrence_key="job-1",
        state="running",
        file_sha256=digest,
        material_slot_mappings=tuple(mappings),
    )


PRINTER_UUID = uuid4()
PRINTER_ID = EntityId(PRINTER_UUID)


def status(*, complete=True, received=AT, feed_received=AT, occupied=True):
    feed = FeedSystemSnapshot(
        "ams-0",
        FeedSystemKind.AMS,
        (slot(occupied=occupied),),
        feed_received,
        feed_received,
        complete,
        "epoch-1",
        1,
    )
    return PrinterStatusSnapshot(
        PRINTER_ID,
        ConnectionState.ONLINE,
        received,
        received,
        observed(None),
        observed(None),
        observed(None),
        observed(None),
        (feed,),
        "epoch-1",
        1,
    )


def mapping(logical=0, disposition="reported_slot", system="ams-0", slot_key="tray-0"):
    item = {"logical_material": logical, "disposition": disposition}
    if disposition == "reported_slot":
        item |= {"provider_system_key": system, "provider_slot_key": slot_key}
    return item


class JobMaterialMappingTests(unittest.TestCase):
    def test_explicit_mapping_to_exact_fresh_complete_occupied_slot_matches(self):
        result = resolve_job_material_slots(
            job(mappings=(mapping(),)),
            facts(),
            status(),
            now=AT,
        )
        self.assertEqual(result[0].state, State.MATCHED)
        self.assertEqual(
            (result[0].provider_system_key, result[0].provider_slot_key), ("ams-0", "tray-0")
        )
        self.assertIsNotNone(result[0].slot)

    def test_file_or_printer_mismatch_fails_closed(self):
        result = resolve_job_material_slots(
            job(digest="d" * 64, mappings=(mapping(),)),
            facts(),
            status(),
            now=AT,
        )
        self.assertEqual(result[0].state, State.CONFLICT)
        other = PrinterStatusSnapshot(
            EntityId.new(),
            ConnectionState.ONLINE,
            AT,
            AT,
            observed(None),
            observed(None),
            observed(None),
            observed(None),
            (),
        )
        result = resolve_job_material_slots(job(mappings=(mapping(),)), facts(), other, now=AT)
        self.assertEqual(result[0].state, State.CONFLICT)

    def test_missing_mapping_and_unknown_slot_never_infer_by_position(self):
        missing = resolve_job_material_slots(job(), facts(), status(), now=AT)
        unknown = resolve_job_material_slots(
            job(mappings=(mapping(slot_key="tray-7"),)),
            facts(),
            status(),
            now=AT,
        )
        self.assertEqual(missing[0].state, State.UNKNOWN)
        self.assertIsNone(missing[0].slot)
        self.assertEqual(unknown[0].state, State.UNKNOWN)
        self.assertIsNone(unknown[0].slot)

    def test_stale_incomplete_and_unoccupied_slot_are_not_matches(self):
        old = UtcDateTime(AT.value - timedelta(seconds=121))
        for snap in (
            status(received=old, feed_received=old),
            status(complete=False),
            status(occupied=False),
        ):
            result = resolve_job_material_slots(
                job(mappings=(mapping(),)),
                facts(),
                snap,
                now=AT,
            )
            self.assertEqual(result[0].state, State.UNKNOWN)
            self.assertIsNone(result[0].slot)

    def test_slice_layers_and_unused_claim_must_agree(self):
        layer_use = LayerFilamentFact((0,), ((1, 2),))
        result = resolve_job_material_slots(
            job(mappings=(mapping(disposition="unused"),)),
            facts(mass=0, layers=(layer_use,)),
            status(),
            now=AT,
        )
        self.assertEqual(result[0].state, State.CONFLICT)
        self.assertEqual(result[0].reason_code, "slice_uses_reported_unused_material")

    def test_unsupported_and_unlisted_materials_remain_unavailable(self):
        unsupported = resolve_job_material_slots(
            job(mappings=(mapping(disposition="unsupported"),)),
            facts(),
            status(),
            now=AT,
        )
        self.assertEqual(unsupported[0].state, State.UNSUPPORTED)
        extra = resolve_job_material_slots(
            job(mappings=(mapping(), mapping(logical=1))),
            facts(),
            status(),
            now=AT,
        )
        self.assertEqual(extra[0].state, State.UNKNOWN)
        self.assertEqual(extra[0].reason_code, "mapping_material_not_in_slice")


if __name__ == "__main__":
    unittest.main()
