"""Durable, bounded printer observations; receiving facts never changes stock."""

import hashlib
import json
import re
from collections.abc import Callable, Sequence

from ufm.application.dto.worker_protocol import (
    MAX_WIRE_BYTES,
    JobMessage,
    SlotsMessage,
    StatusMessage,
    decode_worker_message,
)
from ufm.application.ports.persistence import IdempotencyConflict, UnitOfWork
from ufm.domain.entities import ExternalEventReceipt, ReconciliationTask
from ufm.domain.enums import ReceiptState, ReconciliationState, Severity
from ufm.domain.value_objects import EntityId, UtcDateTime
from ufm.domain.value_objects.json_object import json_object


class ReceiptRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)


def receipt_conflict_key(receipt_id: EntityId) -> str:
    return f"receipt:{receipt_id}:payload_conflict"


def _semantic_payload(metadata: str) -> str:
    data = json_object(metadata)
    # Correlation/observation times may legitimately change on redelivery;
    # source facts under the same raw-event digest may not.
    for key in ("request_id", "sequence", "observed_at"):
        data.pop(key, None)
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class ReceiptIngestion:
    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def ingest(
        self, *, provider_instance_id: EntityId, printer_id: EntityId,
        actor_device_id: EntityId, event_key: str, raw_payload: bytes,
        normalized_payload: bytes, received_at: UtcDateTime | None = None,
    ) -> ExternalEventReceipt:
        if (type(raw_payload) is not bytes or not raw_payload or len(raw_payload) > MAX_WIRE_BYTES
                or type(event_key) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,500}", event_key) is None):
            raise ReceiptRejected("receipt.input_invalid")
        try:
            message = decode_worker_message(normalized_payload)
        except ValueError:
            raise ReceiptRejected("receipt.message_invalid") from None
        if not isinstance(message, StatusMessage | JobMessage | SlotsMessage):
            raise ReceiptRejected("receipt.observation_required")
        if message.printer_id != printer_id.value:
            raise ReceiptRejected("receipt.printer_scope_invalid")
        metadata = message.model_dump_json()
        if len(metadata.encode()) > 65536:
            raise ReceiptRejected("receipt.metadata_too_large")
        event_type = ("PRINT_" + message.state.upper() if isinstance(message, JobMessage) else
                      "PRINTER_STATUS" if isinstance(message, StatusMessage) else "FEED_SLOTS")
        digest = hashlib.sha256(raw_payload).hexdigest()
        now = received_at or UtcDateTime.now()
        with self._unit_of_work() as work:
            printer = work.printers.get(printer_id)
            if printer.deleted_at is not None:
                raise ReceiptRejected("receipt.printer_unavailable")
            existing = work.receipts.by_scoped_key(provider_instance_id, printer_id,
                                                   message.source_epoch, event_key)
            if existing is not None:
                if (existing.payload_hash != digest or existing.event_type != event_type
                        or existing.sanitized_metadata is None
                        or _semantic_payload(existing.sanitized_metadata) != _semantic_payload(metadata)):
                    key = receipt_conflict_key(existing.id)
                    if work.reconciliations.open_task_by_dedupe(key) is None:
                        work.reconciliations.add_task(ReconciliationTask(
                            id=EntityId.new(), device_id=actor_device_id,
                            created_at=now, updated_at=now, revision=1,
                            reason_code="RECEIPT_IDENTITY_PAYLOAD_CONFLICT",
                            severity=Severity.ERROR, state=ReconciliationState.OPEN,
                            dedupe_key=key, suggested_action="review_receipt_identity_conflict",
                        ))
                        # The rejection must not roll back the durable incident.
                        work.commit()
                    raise IdempotencyConflict()
                return existing
            receipt = ExternalEventReceipt(
                id=EntityId.new(), device_id=actor_device_id, created_at=now, updated_at=now, revision=1,
                provider_instance_id=provider_instance_id, printer_id=printer_id,
                source_epoch=message.source_epoch, event_key=event_key, event_type=event_type,
                payload_hash=digest, received_at=now, state=ReceiptState.PENDING,
                sanitized_metadata=metadata,
            )
            work.receipts.add_pending(receipt)
            work.commit()
            return receipt

    def pending(self, limit: int = 100) -> Sequence[ExternalEventReceipt]:
        with self._unit_of_work() as work:
            return tuple(work.receipts.pending(limit))
