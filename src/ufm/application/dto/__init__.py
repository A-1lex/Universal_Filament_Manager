"""Immutable normalized application-boundary models."""

from ufm.application.dto.operations import (
    BackupDestination,
    BackupFile,
    BackupManifest,
    BackupSource,
    DeliveryResult,
    Notification,
    RestoreResult,
    RestoreTarget,
    VerificationResult,
)
from ufm.application.dto.providers import (
    CurrentJobObservation,
    FeedSlotSnapshot,
    FeedSystemSnapshot,
    Observed,
    PrinterCapabilities,
    PrinterEvent,
    PrinterStatusSnapshot,
    PrintJobSnapshot,
    ProviderHealth,
    ProviderMaterialSlotMapping,
)
from ufm.application.dto.scales import TareResult, WeightReading
from ufm.application.dto.slicers import (
    ParseLimits,
    PlateEstimate,
    ProjectInput,
    SlicerProject,
    ToolMaterialEstimate,
)
from ufm.application.dto.sync import SyncBatch, SyncChange, SyncConflict, SyncResult

__all__ = [
    "BackupDestination", "BackupFile", "BackupManifest", "BackupSource",
    "CurrentJobObservation", "DeliveryResult", "FeedSlotSnapshot", "FeedSystemSnapshot",
    "Notification", "Observed", "ParseLimits", "PlateEstimate", "PrinterCapabilities",
    "PrinterEvent", "PrinterStatusSnapshot", "PrintJobSnapshot", "ProjectInput",
    "ProviderHealth", "ProviderMaterialSlotMapping", "RestoreResult", "RestoreTarget", "SlicerProject", "SyncBatch",
    "SyncChange", "SyncConflict", "SyncResult", "TareResult", "ToolMaterialEstimate",
    "VerificationResult", "WeightReading",
]
