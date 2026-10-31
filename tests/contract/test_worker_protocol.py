"""Protect an accounting boundary from coercion, omission and forged outcomes."""

import json
import unittest
from uuid import uuid4

from ufm.application.dto.worker_protocol import (
    ProposalMessage,
    WorkerProtocolRejected,
    decode_worker_message,
)


class WorkerProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.common = {"v": 1, "request_id": "request-1", "printer_id": str(uuid4()),
                       "source_epoch": "epoch-1", "sequence": 1,
                       "observed_at": "2026-10-27T08:00:00Z"}
        self.proposal = {**self.common, "kind": "proposal", "occurrence_key": "run-1",
                         "file_sha256": "a" * 64, "evidence_id": str(uuid4()),
                         "policy_version": "three-mf-v1", "quantity": "estimate",
                         "label": "Розрахункова витрата", "confidence_bp": 8000,
                         "status": "ready", "partial": True,
                         "materials": [{"logical_material": 0, "mass_mg": 12345}],
                         "allocations": [self.allocation(5000), self.allocation(7345)]}

    def allocation(self, mass: int) -> dict[str, object]:
        return {"allocation_id": str(uuid4()), "logical_material": 0,
                "segment_id": str(uuid4()), "spool_id": str(uuid4()), "mass_mg": mass}

    def decode(self, payload: dict[str, object]) -> object:
        return decode_worker_message(json.dumps(payload, ensure_ascii=False).encode())

    def test_partial_multispool_proposal_preserves_exact_mg(self) -> None:
        proposal = self.decode(self.proposal)
        self.assertIsInstance(proposal, ProposalMessage)
        assert isinstance(proposal, ProposalMessage)
        self.assertEqual(sum(item.mass_mg for item in proposal.allocations), 12345)
        self.assertTrue(proposal.partial)
        self.assertEqual(proposal.quantity, "estimate")

    def test_untrusted_frame_rejects_coercion_and_extra_commands(self) -> None:
        for patch in ({"v": True}, {"v": 2}, {"sequence": "1"},
                      {"confidence_bp": 10001}, {"quantity": "measurement"},
                      {"observed_at": "2026-10-27T08:00:00"},
                      {"sql": "update spool"}, {"label": "Фактична витрата"},
                      {"file_sha256": "A" * 64}):
            with self.subTest(patch=patch), self.assertRaises(WorkerProtocolRejected):
                self.decode({**self.proposal, **patch})

    def test_ready_rejects_omission_overallocation_and_duplicate_identity(self) -> None:
        allocations = self.proposal["allocations"]
        assert isinstance(allocations, list)
        for items in ([], [self.allocation(12346)], [allocations[0], allocations[0]],
                      [{**allocations[0], "mass_mg": True}],
                      [{**allocations[0], "mass_mg": 12.345}],
                      [{**allocations[0], "logical_material": 1}]):
            with self.subTest(items=items), self.assertRaises(WorkerProtocolRejected):
                self.decode({**self.proposal, "allocations": items})

    def test_incomplete_mapping_remains_proposal_not_commit(self) -> None:
        result = self.decode({**self.proposal, "status": "needs_mapping", "allocations": []})
        self.assertIsInstance(result, ProposalMessage)
        assert isinstance(result, ProposalMessage)
        self.assertEqual(result.status, "needs_mapping")

    def test_worker_cannot_forge_finalization_acknowledgement(self) -> None:
        with self.assertRaises(WorkerProtocolRejected):
            self.decode({**self.common, "kind": "finalization_outcome", "job_id": str(uuid4()),
                         "receipt_id": str(uuid4()), "outcome": "committed",
                         "finalization_id": str(uuid4())})

    def test_file_evidence_cannot_claim_physical_measurement(self) -> None:
        evidence = {**self.common, "kind": "evidence", "occurrence_key": "run-1",
                    "file_sha256": "a" * 64, "plate": 1, "source": "three_mf",
                    "quantity": "estimate", "confidence_bp": 8000, "includes_purge": None,
                    "interval_start": "2026-10-27T07:00:00Z", "interval_end": "2026-10-27T08:00:00Z"}
        self.decode(evidence)
        for patch in ({"quantity": "measurement"}, {"interval_end": "2026-10-27T06:00:00Z"}):
            with self.subTest(patch=patch), self.assertRaises(WorkerProtocolRejected):
                self.decode({**evidence, **patch})

    def test_frame_size_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            decode_worker_message(b" " * (512 * 1024 + 1))

    def test_duplicate_slot_and_material_are_rejected(self) -> None:
        material = self.proposal["materials"]
        assert isinstance(material, list)
        with self.assertRaises(WorkerProtocolRejected):
            self.decode({**self.proposal, "materials": material + material})
        slot = {"slot_key": "ams-0:slot-0", "logical_material": 0, "identifier": None}
        with self.assertRaises(WorkerProtocolRejected):
            self.decode({**self.common, "kind": "slots", "slots": [slot, slot]})

    def test_job_material_slot_mapping_is_explicit_and_fail_closed(self) -> None:
        message = {**self.common, "kind": "job", "occurrence_key": "run-1", "state": "running",
                   "material_slot_mappings": [
                       {"logical_material": 5, "disposition": "reported_slot",
                        "provider_system_key": "ams:0", "provider_slot_key": "0:3"},
                       {"logical_material": 6, "disposition": "unused"},
                       {"logical_material": 7, "disposition": "unsupported"},
                   ]}
        decoded = self.decode(message)
        self.assertEqual(decoded.material_slot_mappings[0].logical_material, 5)
        for mappings in (
            [message["material_slot_mappings"][0]] * 2,
            [{"logical_material": 5, "disposition": "reported_slot"}],
            [{"logical_material": 5, "disposition": "unused", "provider_system_key": "ams:0"}],
        ):
            with self.subTest(mappings=mappings), self.assertRaises(WorkerProtocolRejected):
                self.decode({**message, "material_slot_mappings": mappings})

    def test_duplicate_json_keys_and_nonstandard_numbers_are_rejected(self) -> None:
        valid = json.dumps(self.proposal)
        for payload in (valid.replace('"v": 1', '"v": 1, "v": 1', 1),
                        valid.replace('"sequence": 1', '"sequence": NaN', 1),
                        valid.replace('"sequence": 1', '"sequence": Infinity', 1)):
            with self.subTest(payload=payload), self.assertRaises(WorkerProtocolRejected):
                decode_worker_message(payload.encode())

    def test_rejection_does_not_echo_untrusted_payload(self) -> None:
        with self.assertRaises(WorkerProtocolRejected) as caught:
            self.decode({**self.proposal, "secret": "private-marker-123"})
        self.assertEqual(str(caught.exception), "worker.frame_invalid")
        self.assertNotIn("private-marker", str(caught.exception))

    def test_version_must_be_explicit(self) -> None:
        missing = {key: value for key, value in self.proposal.items() if key != "v"}
        with self.assertRaises(WorkerProtocolRejected):
            self.decode(missing)
