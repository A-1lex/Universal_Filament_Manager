"""Framework-neutral domain entities."""

from ufm.domain.entities.accounting import (
    ConsumptionDecision,
    ConsumptionEvidence,
    ExternalEventReceipt,
    FinalizationRecord,
    InventoryEvidence,
    Reservation,
)
from ufm.domain.entities.accounting_authority import PrinterAccountingAuthority
from ufm.domain.entities.catalog import (
    Brand,
    CalibrationRecord,
    FilamentProfile,
    SensorDevice,
    StorageLocation,
)
from ufm.domain.entities.configuration import (
    ConnectionProfile,
    DeviceIdentity,
    FeatureFlag,
    SpoolIdentifier,
)
from ufm.domain.entities.inventory import Spool
from ufm.domain.entities.job_projection import JobProjectionState, JobReceiptApplication
from ufm.domain.entities.ledger import FilamentTransaction, MaterialTransfer
from ufm.domain.entities.printing import (
    JobIdentityAlias,
    MaterialUsageSegment,
    PrintJob,
    PrintJobMaterial,
)
from ufm.domain.entities.reconciliation import (
    AlertEvent,
    AuditEvent,
    ConsumptionInventoryEvidence,
    DecisionEvidence,
    InventoryReconciliation,
    ReconciliationTask,
)
from ufm.domain.entities.topology import FeedSlot, MaterialFeedSystem, Printer, SpoolMount

__all__ = [
    "AlertEvent", "AuditEvent", "Brand", "CalibrationRecord", "ConnectionProfile",
    "ConsumptionDecision", "ConsumptionEvidence", "ConsumptionInventoryEvidence",
    "DecisionEvidence", "DeviceIdentity", "ExternalEventReceipt", "FeatureFlag", "FeedSlot",
    "FilamentProfile", "FilamentTransaction", "FinalizationRecord", "InventoryEvidence",
    "InventoryReconciliation", "JobIdentityAlias", "JobProjectionState", "JobReceiptApplication",
    "MaterialFeedSystem", "MaterialTransfer", "PrinterAccountingAuthority",
    "MaterialUsageSegment", "PrintJob", "PrintJobMaterial", "Printer", "ReconciliationTask",
    "Reservation", "SensorDevice", "Spool", "SpoolIdentifier", "SpoolMount",
    "StorageLocation",
]
