"""Framework-neutral application interfaces."""

from ufm.application.ports.backups import BackupInvalid, BackupProvider
from ufm.application.ports.notifications import NotificationProvider
from ufm.application.ports.persistence import (
    AuditRepository,
    DecisionRepository,
    EvidenceRepository,
    FinalizationRepository,
    IdempotencyConflict,
    JobRepository,
    LedgerRepository,
    MountRepository,
    NotFound,
    PersistenceUnavailable,
    ReceiptRepository,
    ReconciliationRepository,
    ReservationRepository,
    RevisionConflict,
    SpoolRepository,
    UnitOfWork,
)
from ufm.application.ports.printers import (
    AuthenticationFailed,
    CommandResult,
    InvalidObservation,
    PrinterControl,
    PrinterProvider,
    ProviderError,
    ProviderUnavailable,
    UnsupportedCapability,
)
from ufm.application.ports.scales import ScaleProvider
from ufm.application.ports.secrets import SecretStore, SecretValue
from ufm.application.ports.slicers import ParseRejected, SlicerProvider
from ufm.application.ports.sync import SyncProvider

__all__ = [
    "AuditRepository", "AuthenticationFailed", "BackupInvalid", "BackupProvider", "CommandResult",
    "DecisionRepository", "EvidenceRepository", "FinalizationRepository", "IdempotencyConflict",
    "InvalidObservation", "JobRepository", "LedgerRepository", "MountRepository", "NotFound",
    "NotificationProvider", "ParseRejected", "PersistenceUnavailable", "PrinterControl",
    "PrinterProvider", "ProviderError", "ProviderUnavailable", "ReceiptRepository",
    "ReconciliationRepository", "ReservationRepository", "RevisionConflict", "ScaleProvider",
    "SecretStore", "SecretValue", "SlicerProvider", "SpoolRepository", "SyncProvider",
    "UnitOfWork", "UnsupportedCapability",
]
