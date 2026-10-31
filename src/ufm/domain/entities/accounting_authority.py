"""Durable operator-reviewed owner state for estimated print accounting."""

import re
from dataclasses import dataclass

from ufm.domain.entities.base import EntityRecord
from ufm.domain.enums import PrinterAccountingMode
from ufm.domain.value_objects import EntityId, UtcDateTime


@dataclass(frozen=True, slots=True, kw_only=True)
class PrinterAccountingAuthority(EntityRecord):
    printer_id: EntityId
    mode: PrinterAccountingMode
    snapshot_sha256: str | None = None
    legacy_writer_disabled_at: UtcDateTime | None = None
    reconciled_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        super(PrinterAccountingAuthority, self).__post_init__()
        if self.mode in {PrinterAccountingMode.CUTOVER_READY, PrinterAccountingMode.UFM_ACTIVE}:
            if (
                self.snapshot_sha256 is None
                or re.fullmatch(r"[0-9a-f]{64}", self.snapshot_sha256) is None
                or self.legacy_writer_disabled_at is None
                or self.reconciled_at is None
            ):
                raise ValueError("printer_authority.cutover_evidence_required")
        elif self.snapshot_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", self.snapshot_sha256
        ) is None:
            raise ValueError("printer_authority.snapshot_invalid")
        for value in (self.legacy_writer_disabled_at, self.reconciled_at):
            if value is not None and value < self.created_at:
                raise ValueError("printer_authority.evidence_time_invalid")
