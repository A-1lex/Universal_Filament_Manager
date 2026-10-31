"""Explicit per-printer cutover transitions for estimated accounting."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import replace

from ufm.application.ports.persistence import IdempotencyConflict, RevisionConflict, UnitOfWork
from ufm.domain.entities import AuditEvent, PrinterAccountingAuthority
from ufm.domain.enums import PrinterAccountingMode
from ufm.domain.value_objects import EntityId, UtcDateTime


class AccountingAuthorityRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)


def _request_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


class PrinterAccountingAuthorityCommands:
    """Persist operator-attested transitions; never control the external Haspel service."""

    def __init__(self, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def transition(
        self,
        *,
        printer_id: EntityId,
        mode: PrinterAccountingMode,
        actor_device_id: EntityId,
        command_key: str,
        expected_revision: int,
        snapshot_sha256: str | None = None,
        legacy_writer_disabled_at: UtcDateTime | None = None,
        reconciled_at: UtcDateTime | None = None,
        at: UtcDateTime | None = None,
    ) -> PrinterAccountingAuthority:
        occurred_at = at or UtcDateTime.now()
        if (
            not isinstance(printer_id, EntityId)
            or not isinstance(actor_device_id, EntityId)
            or not isinstance(mode, PrinterAccountingMode)
            or type(command_key) is not str
            or not command_key.strip()
            or len(command_key) > 500
            or type(expected_revision) is not int
            or expected_revision < 0
            or (snapshot_sha256 is not None
                and re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256) is None)
        ):
            raise AccountingAuthorityRejected("accounting_authority.request_invalid")
        if any(
            evidence_time is not None and evidence_time > occurred_at
            for evidence_time in (legacy_writer_disabled_at, reconciled_at)
        ):
            raise AccountingAuthorityRejected("accounting_authority.cutover_time_invalid")

        request_hash = _request_hash({
            "printer": str(printer_id),
            "mode": mode.value,
            "actor": str(actor_device_id),
            "revision": expected_revision,
            "snapshot": snapshot_sha256,
            "legacy_writer_disabled_at": (
                None if legacy_writer_disabled_at is None
                else legacy_writer_disabled_at.isoformat()
            ),
            "reconciled_at": None if reconciled_at is None else reconciled_at.isoformat(),
            "at": occurred_at.isoformat(),
        })
        with self._unit_of_work() as work:
            events = work.audit.for_command(command_key)
            if events:
                if len(events) != 1:
                    raise IdempotencyConflict()
                try:
                    parameters = json.loads(events[0].parameters_json)
                except (TypeError, ValueError):
                    raise IdempotencyConflict() from None
                authority = work.printer_accounting_authorities.for_printer(printer_id)
                if (
                    events[0].event_code != "printer.accounting_authority.changed"
                    or events[0].entity_id != printer_id
                    or parameters.get("request_hash_v1") != request_hash
                    or authority is None
                    or parameters.get("revision") != authority.revision
                    or parameters.get("mode") != authority.mode.value
                ):
                    raise IdempotencyConflict()
                return authority

            work.printers.get(printer_id)
            current = work.printer_accounting_authorities.for_printer(printer_id)
            actual_revision = 0 if current is None else current.revision
            if actual_revision != expected_revision:
                raise RevisionConflict()

            if current is None:
                if mode not in {PrinterAccountingMode.REVIEW_ONLY, PrinterAccountingMode.LEGACY_ACTIVE}:
                    raise AccountingAuthorityRejected("accounting_authority.initial_mode_invalid")
                if any(value is not None for value in (
                    snapshot_sha256, legacy_writer_disabled_at, reconciled_at,
                )):
                    raise AccountingAuthorityRejected("accounting_authority.initial_evidence_invalid")
                authority = PrinterAccountingAuthority(
                    id=EntityId.new(),
                    device_id=actor_device_id,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                    revision=1,
                    printer_id=printer_id,
                    mode=mode,
                )
                work.printer_accounting_authorities.add(authority)
                previous_mode: str | None = None
            else:
                previous_mode = current.mode.value
                self._validate_transition(
                    current,
                    mode,
                    snapshot_sha256,
                    legacy_writer_disabled_at,
                    reconciled_at,
                )
                authority = replace(
                    current,
                    device_id=actor_device_id,
                    updated_at=occurred_at,
                    revision=current.revision + 1,
                    mode=mode,
                    snapshot_sha256=(
                        snapshot_sha256 if mode is PrinterAccountingMode.CUTOVER_READY
                        else current.snapshot_sha256 if mode is PrinterAccountingMode.UFM_ACTIVE
                        else None
                    ),
                    legacy_writer_disabled_at=(
                        legacy_writer_disabled_at if mode is PrinterAccountingMode.CUTOVER_READY
                        else current.legacy_writer_disabled_at
                        if mode is PrinterAccountingMode.UFM_ACTIVE else None
                    ),
                    reconciled_at=(
                        reconciled_at if mode is PrinterAccountingMode.CUTOVER_READY
                        else current.reconciled_at
                        if mode is PrinterAccountingMode.UFM_ACTIVE else None
                    ),
                )
                work.printer_accounting_authorities.save(authority, current.revision)

            work.audit.append(AuditEvent(
                id=EntityId.new(),
                device_id=actor_device_id,
                created_at=occurred_at,
                actor_device_id=actor_device_id,
                event_code="printer.accounting_authority.changed",
                correlation_id=command_key,
                entity_type="printer",
                entity_id=printer_id,
                parameters_json=json.dumps({
                    "request_hash_v1": request_hash,
                    "from_mode": previous_mode,
                    "mode": authority.mode.value,
                    "revision": authority.revision,
                    "snapshot_sha256": authority.snapshot_sha256,
                    "legacy_writer_disabled_at": (
                        None if authority.legacy_writer_disabled_at is None
                        else authority.legacy_writer_disabled_at.isoformat()
                    ),
                    "reconciled_at": (
                        None if authority.reconciled_at is None
                        else authority.reconciled_at.isoformat()
                    ),
                }, sort_keys=True, separators=(",", ":")),
            ))
            work.commit()
            return authority

    @staticmethod
    def _validate_transition(
        current: PrinterAccountingAuthority,
        target: PrinterAccountingMode,
        snapshot_sha256: str | None,
        legacy_writer_disabled_at: UtcDateTime | None,
        reconciled_at: UtcDateTime | None,
    ) -> None:
        allowed = {
            PrinterAccountingMode.REVIEW_ONLY: {PrinterAccountingMode.LEGACY_ACTIVE},
            PrinterAccountingMode.LEGACY_ACTIVE: {
                PrinterAccountingMode.REVIEW_ONLY,
                PrinterAccountingMode.CUTOVER_READY,
            },
            PrinterAccountingMode.CUTOVER_READY: {
                PrinterAccountingMode.REVIEW_ONLY,
                PrinterAccountingMode.UFM_ACTIVE,
            },
            PrinterAccountingMode.UFM_ACTIVE: {PrinterAccountingMode.REVIEW_ONLY},
        }
        if target not in allowed[current.mode]:
            raise AccountingAuthorityRejected("accounting_authority.transition_invalid")
        if target is PrinterAccountingMode.CUTOVER_READY and (
            snapshot_sha256 is None or legacy_writer_disabled_at is None or reconciled_at is None
        ):
            raise AccountingAuthorityRejected("accounting_authority.cutover_evidence_required")
        if target is PrinterAccountingMode.UFM_ACTIVE and (
            snapshot_sha256 != current.snapshot_sha256
            or legacy_writer_disabled_at != current.legacy_writer_disabled_at
            or reconciled_at != current.reconciled_at
        ):
            raise AccountingAuthorityRejected("accounting_authority.cutover_evidence_mismatch")
        if target not in {
            PrinterAccountingMode.CUTOVER_READY,
            PrinterAccountingMode.UFM_ACTIVE,
            PrinterAccountingMode.REVIEW_ONLY,
        } and any(value is not None for value in (
            snapshot_sha256, legacy_writer_disabled_at, reconciled_at,
        )):
            raise AccountingAuthorityRejected("accounting_authority.unexpected_evidence")
        if target is PrinterAccountingMode.REVIEW_ONLY and (
            snapshot_sha256 is not None
            or legacy_writer_disabled_at is not None
            or reconciled_at is not None
        ):
            raise AccountingAuthorityRejected("accounting_authority.unexpected_evidence")
