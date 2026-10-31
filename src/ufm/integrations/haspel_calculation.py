"""Read-only verified-3MF to canonical calculation proposal adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from ufm.application.dto.worker_protocol import (
    Digest,
    Envelope,
    MaterialEstimate,
    ProposalMessage,
    Token,
)
from ufm.integrations.calculation_worker import (
    CalculationWorkerTransport,
    WorkerScope,
    WorkerTransportRejected,
)
from ufm.integrations.sliced_files import VerifiedSliceFacts

FULL_POLICY: Literal["three-mf-full-mg-preview-v1"] = "three-mf-full-mg-preview-v1"
PARTIAL_POLICY: Literal["haspel-range-cent-preview-v1"] = "haspel-range-cent-preview-v1"


class CalculationRequest(Envelope):
    kind: Literal["calculate"]
    occurrence_key: Token
    file_sha256: Digest
    evidence_id: UUID
    policy_version: Literal["three-mf-full-mg-preview-v1", "haspel-range-cent-preview-v1"]
    completed_layer: Annotated[int, Field(strict=True, ge=-1, le=1_000_000)] | None
    metadata_xml: Annotated[str, Field(min_length=1, max_length=512 * 1024)]
    materials: Annotated[tuple[MaterialEstimate, ...], Field(min_length=1, max_length=256)]


@dataclass(frozen=True, slots=True)
class HaspelCalculator:
    transport: CalculationWorkerTransport

    async def calculate(
        self,
        facts: VerifiedSliceFacts,
        *,
        scope: WorkerScope,
        occurrence_key: str,
        evidence_id: UUID,
        observed_at: datetime,
        sequence: int,
        completed_layer: int | None = None,
    ) -> ProposalMessage:
        policy = FULL_POLICY if completed_layer is None else PARTIAL_POLICY
        source = {item.logical_material: item.mass_mg for item in facts.filaments}
        if len(source) != len(facts.filaments):
            raise WorkerTransportRejected("worker.facts_invalid")
        request = CalculationRequest(
            v=1, kind="calculate", request_id=scope.request_id, printer_id=scope.printer_id,
            source_epoch=scope.source_epoch, sequence=sequence, observed_at=observed_at,
            occurrence_key=occurrence_key, file_sha256=facts.file_sha256,
            evidence_id=evidence_id, policy_version=policy, completed_layer=completed_layer,
            metadata_xml=facts.normalized_xml,
            materials=tuple(MaterialEstimate(logical_material=key, mass_mg=mass)
                            for key, mass in source.items()),
        )
        response = await self.transport.exchange(request.model_dump_json().encode(), scope)
        if not isinstance(response, ProposalMessage):
            raise WorkerTransportRejected("worker.proposal_required")
        returned = {item.logical_material: item.mass_mg for item in response.materials}
        if (response.sequence != sequence or response.occurrence_key != occurrence_key
                or response.file_sha256 != facts.file_sha256 or response.evidence_id != evidence_id
                or response.policy_version != policy or response.partial != (completed_layer is not None)
                or response.status != "needs_mapping" or response.allocations or response.confidence_bp != 0
                or returned.keys() != source.keys()
                or any(mass > source[key] for key, mass in returned.items())
                or (completed_layer is None and returned != source)):
            raise WorkerTransportRejected("worker.proposal_mismatch")
        return response
