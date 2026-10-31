"""Real SQLite accounting constraints, independent of application pre-validation."""

import unittest

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from tests.integration.test_schema_spool_segments import now
from ufm.domain.value_objects import EntityId, Mass
from ufm.infrastructure.persistence.models.accounting import (
    consumption_decision,
    consumption_evidence,
    finalization_record,
    reservation,
)
from ufm.infrastructure.persistence.models.ledger import filament_transaction
from ufm.infrastructure.persistence.models.schema import (
    material_usage_segment,
    print_job,
    print_job_material,
    spool,
    spool_mount,
)


class AccountingSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        from tests.integration.test_schema_spool_segments import SpoolSegmentSchemaTests

        fixture = SpoolSegmentSchemaTests()
        self.addCleanup(fixture.tearDown)
        fixture.setUp()
        self.engine, self.device_id = fixture.engine, fixture.device_id
        self.printer_id, self.slot_ids = fixture.printer_id, fixture.slot_ids
        self.mutable, self.spool_values = fixture.mutable, fixture.spool_values
        self.spool_id, self.job_id, self.material_id = (EntityId.new() for _ in range(3))
        self.mount_id, self.segment_id = EntityId.new(), EntityId.new()
        with self.engine.begin() as connection:
            connection.execute(insert(spool).values(**self.spool_values(self.spool_id)))
            connection.execute(insert(print_job).values(
                **self.mutable(self.job_id), printer_id=self.printer_id, source_type="manual",
                status="COMPLETED", finalization_state="NOT_STARTED", detected_at=now(),
            ))
            connection.execute(insert(print_job_material).values(
                **self.mutable(self.material_id), print_job_id=self.job_id,
                channel_key="tool-0", tool_index=0,
            ))
            connection.execute(insert(spool_mount).values(
                **self.mutable(self.mount_id), feed_slot_id=self.slot_ids[0],
                spool_id=self.spool_id, state="ACTIVE", mounted_at=now(),
                assignment_source="MANUAL", confidence_bp=10000,
            ))
            connection.execute(insert(material_usage_segment).values(
                **self.mutable(self.segment_id), print_job_material_id=self.material_id,
                feed_slot_id=self.slot_ids[0], spool_mount_id=self.mount_id,
                spool_id=self.spool_id, tool_index=0, assignment_state="ASSIGNED",
                started_at=now(), ended_at=now(), source="manual", confidence_bp=10000,
            ))

    def immutable(self) -> dict[str, object]:
        return dict(id=EntityId.new(), device_id=self.device_id, created_at=now())

    def finalization(self, **overrides: object) -> dict[str, object]:
        return {
            **self.immutable(), "print_job_id": self.job_id,
            "idempotency_key": str(EntityId.new()), "request_hash": "request",
            "result_hash": "result", "started_at": now(), "completed_at": now(),
            **overrides,
        }

    def test_different_completion_keys_cannot_finalize_same_job_twice(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(**self.finalization()))
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(**self.finalization()))

    def test_only_one_active_claim_per_spool_and_material(self) -> None:
        for attempt in range(2):
            values = dict(
                **self.mutable(), spool_id=self.spool_id, print_job_material_id=self.material_id,
                reserved_mg=Mass(420000), status="ACTIVE", activated_at=now(),
            )
            if attempt == 0:
                with self.engine.begin() as connection:
                    connection.execute(insert(reservation).values(**values))
            else:
                with self.assertRaises(IntegrityError), self.engine.begin() as connection:
                    connection.execute(insert(reservation).values(**values))

    def test_consumed_reservation_requires_complete_settlement(self) -> None:
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(reservation).values(
                **self.mutable(), spool_id=self.spool_id, print_job_material_id=self.material_id,
                reserved_mg=Mass(420000), status="CONSUMED", activated_at=now(), consumed_at=now(),
            ))

    def test_remaining_mass_and_fractional_consumption_are_rejected(self) -> None:
        common = dict(
            **self.immutable(), print_job_material_id=self.material_id, source_type="PRINTER",
            quantity_kind="REMAINING_MASS", mode="ABSOLUTE", weight_mg=Mass(1000),
            confidence_bp=10000, captured_at=now(), received_at=now(), scope_key="job-total",
        )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(consumption_evidence).values(**common))
        common["quantity_kind"], common["mode"] = "CONSUMED_MASS", "DELTA"
        with self.engine.begin() as connection:
            connection.execute(insert(consumption_evidence).values(**common))
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(text("UPDATE consumption_evidence SET weight_mg=0.5"))

    def test_zero_decision_is_auditable_without_a_fake_debit(self) -> None:
        final = self.finalization()
        with self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(**final))
            connection.execute(insert(consumption_decision).values(
                **self.immutable(), finalization_record_id=final["id"],
                material_usage_segment_id=self.segment_id, selected_weight_mg=Mass(0),
                confidence_bp=10000, strategy="manual", policy_version="safe-v1",
                reason_code="confirmed_zero_usage", finalized_at=now(),
            ))
            self.assertEqual(connection.execute(select(consumption_decision.c.selected_weight_mg)).scalar_one(), Mass(0))

    def test_failed_transaction_rolls_back_claim_and_finalization_together(self) -> None:
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(**self.finalization()))
            connection.execute(insert(reservation).values(
                **self.mutable(), spool_id=self.spool_id, print_job_material_id=self.material_id,
                reserved_mg=Mass(-1), status="PENDING",
            ))
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(finalization_record)).all(), [])

    def ledger_entry(self, **overrides: object) -> dict[str, object]:
        return {
            **self.immutable(), "spool_id": self.spool_id, "sequence": 1,
            "transaction_type": "INITIAL_STOCK", "delta_mg": Mass(1000),
            "previous_effective_mg": None, "new_effective_mg": Mass(1000),
            "command_key": str(EntityId.new()), "command_item": 0,
            "source_type": "MANUAL", "confidence_bp": 10000,
            "estimate_policy_version": "safe-v1", **overrides,
        }

    def test_ledger_rejects_gaps_and_wrong_previous_balance(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(insert(filament_transaction).values(**self.ledger_entry()))
        for sequence, previous in ((3, 1000), (2, 999)):
            with self.subTest(sequence=sequence, previous=previous):
                with self.assertRaises(IntegrityError), self.engine.begin() as connection:
                    connection.execute(insert(filament_transaction).values(**self.ledger_entry(
                        sequence=sequence, transaction_type="MANUAL_USE", delta_mg=Mass(-100),
                        previous_effective_mg=Mass(previous), new_effective_mg=Mass(previous - 100),
                    )))

    def test_history_cannot_be_updated_deleted_or_replaced(self) -> None:
        final = self.finalization()
        with self.engine.begin() as connection:
            connection.execute(insert(finalization_record).values(**final))
            connection.execute(insert(filament_transaction).values(**self.ledger_entry()))
        for statement in (
            update(finalization_record).values(result_hash="changed"),
            delete(finalization_record), delete(filament_transaction),
            update(filament_transaction).values(command_key="changed"),
            insert(finalization_record).prefix_with("OR REPLACE").values(**self.finalization()),
        ):
            with self.subTest(statement=str(statement)):
                with self.assertRaises(IntegrityError), self.engine.begin() as connection:
                    connection.execute(statement)
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(finalization_record.c.id)).scalar_one(), final["id"])

    def test_negative_calculated_balance_is_retained_not_clamped(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(insert(filament_transaction).values(**self.ledger_entry()))
            connection.execute(insert(filament_transaction).values(**self.ledger_entry(
                sequence=2, transaction_type="MANUAL_USE", delta_mg=Mass(-1500),
                previous_effective_mg=Mass(1000), new_effective_mg=Mass(-500),
            )))
            stored = connection.execute(select(filament_transaction.c.new_effective_mg)
                                        .where(filament_transaction.c.sequence == 2)).scalar_one()
            self.assertEqual(stored, Mass(-500))

    def test_finalized_segment_cannot_change_attribution(self) -> None:
        self.test_zero_decision_is_auditable_without_a_fake_debit()
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(update(material_usage_segment).values(source="changed"))

    def test_active_claim_cannot_resize_in_place(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(insert(reservation).values(
                **self.mutable(), spool_id=self.spool_id, print_job_material_id=self.material_id,
                reserved_mg=Mass(420000), status="ACTIVE", activated_at=now(),
            ))
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(update(reservation).values(reserved_mg=Mass(1)))

    def test_unknown_segment_cannot_receive_a_consumption_decision(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(update(material_usage_segment).values(
                assignment_state="ACTIVE_SPOOL_UNKNOWN", spool_id=None, spool_mount_id=None,
            ))
        with self.assertRaises(IntegrityError):
            self.test_zero_decision_is_auditable_without_a_fake_debit()
