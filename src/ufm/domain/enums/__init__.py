"""Persistable domain enums and validated lifecycle transitions."""

from enum import StrEnum


class SpoolLifecycle(StrEnum):
    NEW = "NEW"
    OPEN = "OPEN"
    ARCHIVED = "ARCHIVED"


class InventoryHealth(StrEnum):
    CONSISTENT = "CONSISTENT"
    QUARANTINED = "QUARANTINED"


class StockLevel(StrEnum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    LOW = "LOW"
    EMPTY = "EMPTY"


class Availability(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    STALE = "STALE"


class PrintStatus(StrEnum):
    DETECTED = "DETECTED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FinalizationState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    FINALIZED = "FINALIZED"


class PrinterAccountingMode(StrEnum):
    """Per-printer accounting owner; unknown/absent state must never write."""

    REVIEW_ONLY = "REVIEW_ONLY"
    LEGACY_ACTIVE = "LEGACY_ACTIVE"
    CUTOVER_READY = "CUTOVER_READY"
    UFM_ACTIVE = "UFM_ACTIVE"


class ReservationState(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class MountState(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class SlotAssignment(StrEnum):
    EMPTY = "EMPTY"
    ASSIGNED = "ASSIGNED"
    ACTIVE_SPOOL_UNKNOWN = "ACTIVE_SPOOL_UNKNOWN"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"


class FeedSystemKind(StrEnum):
    EXTERNAL = "EXTERNAL"
    AMS = "AMS"
    AMS_LITE = "AMS_LITE"
    MMU = "MMU"
    IDEX = "IDEX"
    TOOL_CHANGER = "TOOL_CHANGER"
    GENERIC = "GENERIC"


class ConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


class ProviderHealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


class ReceiptState(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    REJECTED = "REJECTED"


class ReconciliationState(StrEnum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class EvidenceSource(StrEnum):
    SCALE = "SCALE"
    PRINTER = "PRINTER"
    AMS = "AMS"
    SLICER = "SLICER"
    THREE_MF = "THREE_MF"
    GCODE = "GCODE"
    PROGRESS_ESTIMATE = "PROGRESS_ESTIMATE"
    MANUAL = "MANUAL"


class QuantityKind(StrEnum):
    CONSUMED_MASS = "CONSUMED_MASS"
    REMAINING_MASS = "REMAINING_MASS"
    LENGTH = "LENGTH"


class EvidenceMode(StrEnum):
    DELTA = "DELTA"
    CUMULATIVE = "CUMULATIVE"
    ABSOLUTE = "ABSOLUTE"
    ESTIMATE = "ESTIMATE"


class AssignmentSource(StrEnum):
    MANUAL = "MANUAL"
    QR = "QR"
    NFC = "NFC"
    PROVIDER = "PROVIDER"
    SCALE_ASSOCIATION = "SCALE_ASSOCIATION"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class TransactionType(StrEnum):
    INITIAL_STOCK = "INITIAL_STOCK"
    PRINT_CONSUMPTION = "PRINT_CONSUMPTION"
    PURGE = "PURGE"
    LOAD = "LOAD"
    UNLOAD = "UNLOAD"
    WASTE = "WASTE"
    FAILED_PRINT = "FAILED_PRINT"
    MANUAL_USE = "MANUAL_USE"
    MEASUREMENT_CORRECTION = "MEASUREMENT_CORRECTION"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    RETURN = "RETURN"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"


class MaterialType(StrEnum):
    PLA = "PLA"
    PETG = "PETG"
    ABS = "ABS"
    ASA = "ASA"
    TPU = "TPU"
    PA = "PA"
    PC = "PC"
    PVA = "PVA"
    HIPS = "HIPS"
    PP = "PP"
    PEEK = "PEEK"
    PEI = "PEI"
    CUSTOM = "CUSTOM"


class StorageType(StrEnum):
    ROOM = "ROOM"
    CABINET = "CABINET"
    SHELF = "SHELF"
    DRY_BOX = "DRY_BOX"
    BIN = "BIN"
    OTHER = "OTHER"


class SensorType(StrEnum):
    SCALE = "SCALE"
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    RFID_READER = "RFID_READER"
    NFC_READER = "NFC_READER"
    CAMERA = "CAMERA"
    OTHER = "OTHER"


class ConnectionMode(StrEnum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"
    MANUAL = "MANUAL"


__all__ = [
    "AssignmentSource", "Availability", "ConnectionMode", "ConnectionState",
    "EvidenceMode", "EvidenceSource", "FeedSystemKind", "FinalizationState",
    "InventoryHealth", "MaterialType", "MountState", "PrintStatus", "ProviderHealthState",
    "QuantityKind", "ReceiptState", "ReconciliationState", "ReservationState", "SensorType",
    "Severity", "SlotAssignment", "SpoolLifecycle", "StockLevel", "StorageType",
    "TransactionType",
]
