"""SQLAlchemy Core metadata for schema v1, built in dependency-ordered slices."""



from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
)

from ufm.domain.enums import (
    AssignmentSource,
    ConnectionMode,
    EvidenceSource,
    FeedSystemKind,
    FinalizationState,
    InventoryHealth,
    MaterialType,
    MountState,
    PrinterAccountingMode,
    PrintStatus,
    ReceiptState,
    SensorType,
    SlotAssignment,
    SpoolLifecycle,
    StorageType,
)
from ufm.domain.value_objects import MAX_ABS_MILLIGRAMS
from ufm.infrastructure.persistence.models import accounting as accounting
from ufm.infrastructure.persistence.models import ledger as ledger
from ufm.infrastructure.persistence.models.common import (
    _immutable_columns,
    _mutable_columns,
    _values,
)
from ufm.infrastructure.persistence.models.common import (
    metadata as metadata,
)
from ufm.infrastructure.persistence.models.types import (
    EntityIdType,
    ExactDecimalType,
    MassType,
    UtcDateTimeType,
)

device_identity = Table(
    "device_identity",
    metadata,
    Column("id", EntityIdType(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("public_id", Text(), nullable=False),
    Column("created_at", UtcDateTimeType(), nullable=False),
    Column("last_seen_at", UtcDateTimeType()),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
    CheckConstraint("length(public_id) BETWEEN 1 AND 500", name="public_id_length"),
    CheckConstraint("length(created_at) = 27", name="created_at_format"),
    CheckConstraint("last_seen_at IS NULL OR last_seen_at >= created_at", name="last_seen_order"),
    UniqueConstraint("public_id"),
)

spoolman_import_source = Table(
    "spoolman_import_source",
    metadata,
    Column("source_instance_key", Text(), primary_key=True),
    Column(
        "device_id", EntityIdType(),
        ForeignKey("device_identity.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False, unique=True,
    ),
    Column("display_name", Text(), nullable=False),
    Column("created_at", UtcDateTimeType(), nullable=False),
    Column("last_seen_at", UtcDateTimeType(), nullable=False),
    Column("snapshot_sha256", Text()),
    CheckConstraint(
        "length(source_instance_key) IN (24, 32) "
        "AND source_instance_key NOT GLOB '*[^0-9a-f]*'",
        name="source_key_format",
    ),
    CheckConstraint("length(display_name) BETWEEN 1 AND 200", name="display_name_length"),
    CheckConstraint(
        "length(created_at) = 27 AND length(last_seen_at) = 27 "
        "AND last_seen_at >= created_at",
        name="timestamps_valid",
    ),
    CheckConstraint(
        "snapshot_sha256 IS NULL OR (length(snapshot_sha256) = 64 "
        "AND snapshot_sha256 NOT GLOB '*[^0-9a-f]*')",
        name="snapshot_digest_format",
    ),
)

brand = Table(
    "brand",
    metadata,
    *_mutable_columns(),
    Column("name", Text(), nullable=False),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
)

sensor_device = Table(
    "sensor_device",
    metadata,
    *_mutable_columns(),
    Column("name", Text(), nullable=False),
    Column("device_type", Text(), nullable=False),
    Column("provider_type", Text(), nullable=False),
    Column("connection_config_ref", Text()),
    Column("enabled", Boolean(), nullable=False),
    Column("last_seen_at", UtcDateTimeType()),
    Column("metadata_json", Text()),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
    CheckConstraint("length(provider_type) BETWEEN 1 AND 200", name="provider_length"),
    CheckConstraint(f"device_type IN ({_values(SensorType)})", name="device_type_enum"),
    CheckConstraint("enabled IN (0, 1)", name="enabled_bool"),
)

storage_location = Table(
    "storage_location",
    metadata,
    *_mutable_columns(),
    Column(
        "parent_id",
        EntityIdType(),
        ForeignKey("storage_location.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    Column("name", Text(), nullable=False),
    Column("type", Text(), nullable=False),
    Column("description", Text()),
    Column(
        "temperature_sensor_id",
        EntityIdType(),
        ForeignKey("sensor_device.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    Column(
        "humidity_sensor_id",
        EntityIdType(),
        ForeignKey("sensor_device.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
    CheckConstraint(f"type IN ({_values(StorageType)})", name="type_enum"),
    CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_self_parent"),
)

filament_profile = Table(
    "filament_profile",
    metadata,
    *_mutable_columns(),
    Column("brand_id", EntityIdType(), ForeignKey("brand.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column("name", Text(), nullable=False),
    Column("product_line", Text()),
    Column("material_type", Text(), nullable=False),
    Column("custom_material_name", Text()),
    Column("subtype", Text()),
    Column("diameter_mm", ExactDecimalType(), nullable=False),
    Column("density_g_cm3", ExactDecimalType()),
    Column("nozzle_min_c", ExactDecimalType()),
    Column("nozzle_max_c", ExactDecimalType()),
    Column("bed_min_c", ExactDecimalType()),
    Column("bed_max_c", ExactDecimalType()),
    Column("chamber_min_c", ExactDecimalType()),
    Column("chamber_max_c", ExactDecimalType()),
    Column("max_volumetric_speed_mm3_s", ExactDecimalType()),
    Column("drying_temp_c", ExactDecimalType()),
    Column("drying_duration_min", Integer()),
    Column("abrasive", Boolean()),
    Column("flexible", Boolean()),
    Column("hygroscopic", Boolean()),
    Column("soluble", Boolean()),
    Column("filled_material", Boolean()),
    Column("default_color_name", Text()),
    Column("notes", Text()),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
    CheckConstraint(f"material_type IN ({_values(MaterialType)})", name="material_type_enum"),
    CheckConstraint(
        "(material_type = 'CUSTOM' AND custom_material_name IS NOT NULL "
        "AND length(custom_material_name) BETWEEN 1 AND 200) "
        "OR (material_type <> 'CUSTOM' AND custom_material_name IS NULL)",
        name="custom_material_shape",
    ),
    CheckConstraint("CAST(diameter_mm AS NUMERIC) > 0", name="diameter_positive"),
    CheckConstraint("density_g_cm3 IS NULL OR CAST(density_g_cm3 AS NUMERIC) > 0", name="density_positive"),
    CheckConstraint("drying_duration_min IS NULL OR drying_duration_min >= 0", name="drying_duration"),
    CheckConstraint(
        "(nozzle_min_c IS NULL OR nozzle_max_c IS NULL OR "
        "CAST(nozzle_max_c AS NUMERIC) >= CAST(nozzle_min_c AS NUMERIC))",
        name="nozzle_range",
    ),
    CheckConstraint(
        "(bed_min_c IS NULL OR bed_max_c IS NULL OR "
        "CAST(bed_max_c AS NUMERIC) >= CAST(bed_min_c AS NUMERIC))",
        name="bed_range",
    ),
    CheckConstraint(
        "abrasive IS NULL OR abrasive IN (0, 1)", name="abrasive_bool"
    ),
    CheckConstraint("flexible IS NULL OR flexible IN (0, 1)", name="flexible_bool"),
    CheckConstraint("hygroscopic IS NULL OR hygroscopic IN (0, 1)", name="hygroscopic_bool"),
    CheckConstraint("soluble IS NULL OR soluble IN (0, 1)", name="soluble_bool"),
    CheckConstraint("filled_material IS NULL OR filled_material IN (0, 1)", name="filled_bool"),
)

printer = Table(
    "printer",
    metadata,
    *_mutable_columns(),
    Column("name", Text(), nullable=False),
    Column("manufacturer", Text()),
    Column("model", Text()),
    Column("serial_number", Text()),
    Column("enabled", Boolean(), nullable=False),
    Column("default_slicer_key", Text()),
    Column("nozzle_diameter_mm", ExactDecimalType()),
    Column("build_x_mm", ExactDecimalType()),
    Column("build_y_mm", ExactDecimalType()),
    Column("build_z_mm", ExactDecimalType()),
    Column("has_enclosure", Boolean()),
    Column("has_camera", Boolean()),
    Column("has_filament_sensor", Boolean()),
    Column("has_multi_material_system", Boolean()),
    Column("firmware_version", Text()),
    Column("last_seen_at", UtcDateTimeType()),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
    CheckConstraint("enabled IN (0, 1)", name="enabled_bool"),
    CheckConstraint(
        "nozzle_diameter_mm IS NULL OR CAST(nozzle_diameter_mm AS NUMERIC) > 0",
        name="nozzle_positive",
    ),
    CheckConstraint(
        "(build_x_mm IS NULL OR CAST(build_x_mm AS NUMERIC) > 0) AND "
        "(build_y_mm IS NULL OR CAST(build_y_mm AS NUMERIC) > 0) AND "
        "(build_z_mm IS NULL OR CAST(build_z_mm AS NUMERIC) > 0)",
        name="build_volume_positive",
    ),
    CheckConstraint(
        "(has_enclosure IS NULL OR has_enclosure IN (0, 1)) AND "
        "(has_camera IS NULL OR has_camera IN (0, 1)) AND "
        "(has_filament_sensor IS NULL OR has_filament_sensor IN (0, 1)) AND "
        "(has_multi_material_system IS NULL OR has_multi_material_system IN (0, 1))",
        name="capability_bools",
    ),
)

printer_accounting_authority = Table(
    "printer_accounting_authority",
    metadata,
    *_mutable_columns(),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("mode", Text(), nullable=False),
    Column("snapshot_sha256", Text()),
    Column("legacy_writer_disabled_at", UtcDateTimeType()),
    Column("reconciled_at", UtcDateTimeType()),
    CheckConstraint(f"mode IN ({_values(PrinterAccountingMode)})", name="mode_enum"),
    CheckConstraint(
        "snapshot_sha256 IS NULL OR "
        "(length(snapshot_sha256) = 64 AND snapshot_sha256 NOT GLOB '*[^0-9a-f]*')",
        name="snapshot_digest_format",
    ),
    CheckConstraint(
        "mode NOT IN ('CUTOVER_READY', 'UFM_ACTIVE') OR "
        "(snapshot_sha256 IS NOT NULL AND legacy_writer_disabled_at IS NOT NULL "
        "AND reconciled_at IS NOT NULL)",
        name="cutover_evidence_required",
    ),
    CheckConstraint(
        "(legacy_writer_disabled_at IS NULL OR legacy_writer_disabled_at >= created_at) AND "
        "(reconciled_at IS NULL OR reconciled_at >= created_at)",
        name="evidence_time_order",
    ),
    UniqueConstraint("printer_id"),
)

connection_profile = Table(
    "connection_profile",
    metadata,
    *_mutable_columns(),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("provider_type", Text(), nullable=False),
    Column("connection_mode", Text(), nullable=False),
    Column("host", Text()),
    Column("port", Integer()),
    Column("tls_enabled", Boolean(), nullable=False),
    Column("credential_ref", Text()),
    Column("cloud_account_ref", Text()),
    Column("extra_config_json", Text()),
    CheckConstraint("length(provider_type) BETWEEN 1 AND 200", name="provider_length"),
    CheckConstraint(f"connection_mode IN ({_values(ConnectionMode)})", name="mode_enum"),
    CheckConstraint("port IS NULL OR (typeof(port) = 'integer' AND port BETWEEN 1 AND 65535)", name="port_range"),
    CheckConstraint("tls_enabled IN (0, 1)", name="tls_bool"),
    CheckConstraint(
        "credential_ref IS NULL OR credential_ref LIKE 'ufm:credential:%'",
        name="credential_reference",
    ),
    UniqueConstraint("printer_id"),
)

haspel_authority_connection = Table(
    "haspel_authority_connection",
    metadata,
    *_mutable_columns(),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("endpoint_origin", Text(), nullable=False),
    Column("haspel_printer_id", Text(), nullable=False),
    Column("credential_ref", Text(), nullable=False),
    Column("observed_capability_version", Integer()),
    Column("observed_owner", Text()),
    Column("observed_revision", Integer()),
    Column("observed_pending_count", Integer()),
    Column("observed_uncertain_count", Integer()),
    Column("observed_active_count", Integer()),
    Column("observed_at", UtcDateTimeType()),
    CheckConstraint(
        "length(endpoint_origin) BETWEEN 1 AND 2000",
        name="endpoint_origin_length",
    ),
    CheckConstraint(
        "length(haspel_printer_id) BETWEEN 1 AND 200 "
        "AND haspel_printer_id NOT GLOB '*[^ -~]*'",
        name="haspel_printer_id_format",
    ),
    CheckConstraint(
        "credential_ref LIKE 'ufm:credential:%'",
        name="credential_reference",
    ),
    CheckConstraint(
        "observed_owner IS NULL OR observed_owner IN "
        "('LEGACY_ACTIVE', 'UFM_ACTIVE', 'REVIEW_ONLY')",
        name="observed_owner_enum",
    ),
    CheckConstraint(
        "observed_capability_version IS NULL OR observed_capability_version = 1",
        name="observed_capability_version",
    ),
    CheckConstraint(
        "observed_revision IS NULL OR "
        "(typeof(observed_revision) = 'integer' AND observed_revision >= 0)",
        name="observed_revision_range",
    ),
    CheckConstraint(
        "(observed_at IS NULL AND observed_capability_version IS NULL "
        "AND observed_owner IS NULL AND observed_revision IS NULL "
        "AND observed_pending_count IS NULL AND observed_uncertain_count IS NULL "
        "AND observed_active_count IS NULL) OR "
        "(observed_at IS NOT NULL AND observed_capability_version = 1 "
        "AND observed_owner IS NOT NULL AND observed_revision IS NOT NULL "
        "AND observed_pending_count IS NOT NULL AND observed_uncertain_count IS NOT NULL "
        "AND observed_active_count IS NOT NULL)",
        name="observed_snapshot_complete",
    ),
    CheckConstraint(
        "(observed_pending_count IS NULL OR "
        "(typeof(observed_pending_count) = 'integer' AND observed_pending_count >= 0)) "
        "AND (observed_uncertain_count IS NULL OR "
        "(typeof(observed_uncertain_count) = 'integer' AND observed_uncertain_count >= 0)) "
        "AND (observed_active_count IS NULL OR "
        "(typeof(observed_active_count) = 'integer' AND observed_active_count >= 0))",
        name="observed_counts_nonnegative",
    ),
    CheckConstraint(
        "observed_at IS NULL OR (length(observed_at) = 27 AND observed_at >= created_at)",
        name="observed_time_order",
    ),
    UniqueConstraint("printer_id"),
)

material_feed_system = Table(
    "material_feed_system",
    metadata,
    *_mutable_columns(),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("provider_system_key", Text()),
    Column("kind", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    CheckConstraint(f"kind IN ({_values(FeedSystemKind)})", name="kind_enum"),
    CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
)
Index(
    "uq_material_feed_system_provider_key",
    material_feed_system.c.printer_id,
    material_feed_system.c.provider_system_key,
    unique=True,
    sqlite_where=material_feed_system.c.provider_system_key.is_not(None),
)

feed_slot = Table(
    "feed_slot",
    metadata,
    *_mutable_columns(),
    Column(
        "feed_system_id",
        EntityIdType(),
        ForeignKey("material_feed_system.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("slot_key", Text(), nullable=False),
    Column("tool_index", Integer()),
    Column("assignment_state", Text(), nullable=False),
    Column("observed_at", UtcDateTimeType()),
    Column("received_at", UtcDateTimeType()),
    Column("source_epoch", Text()),
    Column("source_sequence", Integer()),
    CheckConstraint("length(slot_key) BETWEEN 1 AND 200", name="slot_key_length"),
    CheckConstraint("tool_index IS NULL OR tool_index >= 0", name="tool_index_nonnegative"),
    CheckConstraint(f"assignment_state IN ({_values(SlotAssignment)})", name="assignment_enum"),
    CheckConstraint("source_sequence IS NULL OR source_sequence >= 0", name="source_sequence"),
    UniqueConstraint("feed_system_id", "slot_key"),
)

calibration_record = Table(
    "calibration_record",
    metadata,
    *_immutable_columns(),
    Column(
        "sensor_id",
        EntityIdType(),
        ForeignKey("sensor_device.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("version", Integer(), nullable=False),
    Column("calibration_type", Text(), nullable=False),
    Column("reference_value", ExactDecimalType(), nullable=False),
    Column("reference_unit", Text(), nullable=False),
    Column("offset", ExactDecimalType(), nullable=False),
    Column("scale_factor", ExactDecimalType(), nullable=False),
    Column("temperature_c", ExactDecimalType()),
    Column("performed_at", UtcDateTimeType(), nullable=False),
    Column("expires_at", UtcDateTimeType()),
    Column("notes", Text()),
    CheckConstraint("typeof(version) = 'integer' AND version >= 1", name="version_positive"),
    CheckConstraint("length(calibration_type) BETWEEN 1 AND 200", name="type_length"),
    CheckConstraint("length(reference_unit) BETWEEN 1 AND 100", name="unit_length"),
    CheckConstraint("CAST(scale_factor AS NUMERIC) <> 0", name="scale_factor_nonzero"),
    CheckConstraint("expires_at IS NULL OR expires_at >= performed_at", name="expiry_order"),
    UniqueConstraint("sensor_id", "version"),
)

project = Table(
    "project",
    metadata,
    *_mutable_columns(),
    Column("name", Text(), nullable=False),
    Column("description", Text()),
    CheckConstraint("length(name) BETWEEN 1 AND 500", name="name_length"),
)

print_job = Table(
    "print_job",
    metadata,
    *_mutable_columns(),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("project_id", EntityIdType(), ForeignKey("project.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column("external_job_id", Text()),
    Column("name", Text()),
    Column("file_name", Text()),
    Column("file_hash", Text()),
    Column("plate_name", Text()),
    Column("source_type", Text(), nullable=False),
    Column("slicer_type", Text()),
    Column("status", Text(), nullable=False),
    Column("finalization_state", Text(), nullable=False),
    Column("detected_at", UtcDateTimeType(), nullable=False),
    Column("started_at", UtcDateTimeType()),
    Column("paused_at", UtcDateTimeType()),
    Column("completed_at", UtcDateTimeType()),
    Column("failed_at", UtcDateTimeType()),
    Column("cancelled_at", UtcDateTimeType()),
    Column("estimated_duration_sec", Integer()),
    Column("actual_duration_sec", Integer()),
    Column("progress_bp", Integer()),
    Column("current_layer", Integer()),
    Column("total_layers", Integer()),
    Column("thumbnail_uri", Text()),
    Column("failure_code", Text()),
    Column("failure_reason", Text()),
    CheckConstraint("length(source_type) BETWEEN 1 AND 200", name="source_length"),
    CheckConstraint(f"status IN ({_values(PrintStatus)})", name="status_enum"),
    CheckConstraint(
        f"finalization_state IN ({_values(FinalizationState)})",
        name="finalization_state_enum",
    ),
    CheckConstraint("progress_bp IS NULL OR progress_bp BETWEEN 0 AND 10000", name="progress_range"),
    CheckConstraint("current_layer IS NULL OR current_layer >= 0", name="current_layer_nonnegative"),
    CheckConstraint("total_layers IS NULL OR total_layers >= 0", name="total_layers_nonnegative"),
    CheckConstraint(
        "current_layer IS NULL OR total_layers IS NULL OR current_layer <= total_layers",
        name="layer_order",
    ),
    CheckConstraint(
        "estimated_duration_sec IS NULL OR estimated_duration_sec >= 0",
        name="estimated_duration_nonnegative",
    ),
    CheckConstraint(
        "actual_duration_sec IS NULL OR actual_duration_sec >= 0",
        name="actual_duration_nonnegative",
    ),
)

job_identity_alias = Table(
    "job_identity_alias",
    metadata,
    *_immutable_columns(),
    Column(
        "print_job_id",
        EntityIdType(),
        ForeignKey("print_job.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("provider", EntityIdType(), nullable=False),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("source_type", Text(), nullable=False),
    Column("source_epoch", Text(), nullable=False),
    Column("occurrence_key", Text(), nullable=False),
    Column("external_job_id", Text()),
    Column("started_at", UtcDateTimeType()),
    Column("file_hash", Text()),
    Column("project_reference", Text()),
    CheckConstraint("length(source_type) BETWEEN 1 AND 200", name="source_length"),
    CheckConstraint("length(source_epoch) BETWEEN 1 AND 500", name="epoch_length"),
    CheckConstraint("length(occurrence_key) BETWEEN 1 AND 500", name="occurrence_length"),
    UniqueConstraint("provider", "printer_id", "source_type", "source_epoch", "occurrence_key"),
)

print_job_material = Table(
    "print_job_material",
    metadata,
    *_mutable_columns(),
    Column(
        "print_job_id",
        EntityIdType(),
        ForeignKey("print_job.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("channel_key", Text(), nullable=False),
    Column("tool_index", Integer(), nullable=False),
    Column("extruder_index", Integer()),
    Column(
        "filament_profile_id",
        EntityIdType(),
        ForeignKey("filament_profile.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    Column("estimated_mg", MassType()),
    Column("estimated_length_mm", Integer()),
    Column(
        "logical_material_index",
        Integer(),
        CheckConstraint(
            "logical_material_index IS NULL OR (typeof(logical_material_index) = 'integer' "
            "AND logical_material_index BETWEEN 0 AND 255)",
            name="logical_material_range",
        ),
    ),
    CheckConstraint("length(channel_key) BETWEEN 1 AND 200", name="channel_length"),
    CheckConstraint("typeof(tool_index) = 'integer' AND tool_index >= 0", name="tool_nonnegative"),
    CheckConstraint("extruder_index IS NULL OR extruder_index >= 0", name="extruder_nonnegative"),
    CheckConstraint("estimated_mg IS NULL OR estimated_mg >= 0", name="estimated_mass_nonnegative"),
    CheckConstraint(
        "estimated_length_mm IS NULL OR estimated_length_mm >= 0",
        name="estimated_length_nonnegative",
    ),
    UniqueConstraint("print_job_id", "channel_key"),
)

external_event_receipt = Table(
    "external_event_receipt",
    metadata,
    *_mutable_columns(),
    Column("provider", EntityIdType(), nullable=False),
    Column(
        "printer_id",
        EntityIdType(),
        ForeignKey("printer.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("source_epoch", Text(), nullable=False),
    Column("event_key", Text(), nullable=False),
    Column("event_type", Text(), nullable=False),
    Column("payload_hash", Text(), nullable=False),
    Column("received_at", UtcDateTimeType(), nullable=False),
    Column("processed_at", UtcDateTimeType()),
    Column("processing_result", Text(), nullable=False),
    Column("reason_code", Text()),
    Column("sanitized_metadata", Text()),
    CheckConstraint("length(source_epoch) BETWEEN 1 AND 500", name="epoch_length"),
    CheckConstraint("length(event_key) BETWEEN 1 AND 500", name="event_key_length"),
    CheckConstraint("length(event_type) BETWEEN 1 AND 200", name="event_type_length"),
    CheckConstraint("length(payload_hash) BETWEEN 1 AND 500", name="payload_hash_length"),
    CheckConstraint(f"processing_result IN ({_values(ReceiptState)})", name="result_enum"),
    CheckConstraint(
        "(processing_result = 'PROCESSED' AND processed_at IS NOT NULL) OR "
        "(processing_result <> 'PROCESSED' AND processed_at IS NULL)",
        name="processed_shape",
    ),
    UniqueConstraint("provider", "printer_id", "source_epoch", "event_key"),
)

spool = Table(
    "spool",
    metadata,
    *_mutable_columns(),
    Column("display_name", Text(), nullable=False),
    Column("brand_id", EntityIdType(), ForeignKey("brand.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column(
        "filament_profile_id",
        EntityIdType(),
        ForeignKey("filament_profile.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("product_line", Text()),
    Column("batch_number", Text()),
    Column("lot_number", Text()),
    Column("color_name", Text()),
    Column("color_hex", Text()),
    Column("secondary_color_hex", Text()),
    Column("diameter_mm", ExactDecimalType(), nullable=False),
    Column("density_g_cm3", ExactDecimalType()),
    Column("nominal_filament_mg", MassType()),
    Column("empty_spool_mg", MassType()),
    Column("estimated_remaining_mg", MassType()),
    Column("measured_remaining_mg", MassType()),
    Column("effective_remaining_mg", MassType()),
    Column("measured_at", UtcDateTimeType()),
    Column(
        "measured_evidence_id",
        EntityIdType(),
        ForeignKey("inventory_evidence.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    Column("ledger_sequence", Integer(), nullable=False, server_default="0"),
    Column("purchase_price", ExactDecimalType()),
    Column("currency", Text()),
    Column("purchase_date", Text()),
    Column("opened_at", UtcDateTimeType()),
    Column("manufactured_at", UtcDateTimeType()),
    Column("expires_at", UtcDateTimeType()),
    Column(
        "storage_location_id",
        EntityIdType(),
        ForeignKey("storage_location.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    Column("lifecycle", Text(), nullable=False),
    Column("inventory_health", Text(), nullable=False),
    Column("low_threshold_mg", MassType()),
    Column("low_threshold_bp", Integer()),
    Column("image_uri", Text()),
    Column("notes", Text()),
    Column("archived_at", UtcDateTimeType()),
    Column(
        "purchase_basis_mg", MassType(),
        CheckConstraint(
            f"purchase_basis_mg IS NULL OR (typeof(purchase_basis_mg) = 'integer' "
            f"AND purchase_basis_mg BETWEEN 1 AND {MAX_ABS_MILLIGRAMS})",
            name="purchase_basis_positive",
        ),
    ),
    CheckConstraint("length(display_name) BETWEEN 1 AND 200", name="name_length"),
    CheckConstraint("CAST(diameter_mm AS NUMERIC) > 0", name="diameter_positive"),
    CheckConstraint("density_g_cm3 IS NULL OR CAST(density_g_cm3 AS NUMERIC) > 0", name="density_positive"),
    CheckConstraint(
        f"nominal_filament_mg IS NULL OR (typeof(nominal_filament_mg) = 'integer' "
        f"AND nominal_filament_mg BETWEEN 0 AND {MAX_ABS_MILLIGRAMS})",
        name="nominal_mass_range",
    ),
    CheckConstraint(
        f"empty_spool_mg IS NULL OR (typeof(empty_spool_mg) = 'integer' "
        f"AND empty_spool_mg BETWEEN 0 AND {MAX_ABS_MILLIGRAMS})",
        name="empty_mass_range",
    ),
    CheckConstraint(
        f"measured_remaining_mg IS NULL OR (typeof(measured_remaining_mg) = 'integer' "
        f"AND measured_remaining_mg BETWEEN 0 AND {MAX_ABS_MILLIGRAMS})",
        name="measured_mass_range",
    ),
    CheckConstraint(
        f"estimated_remaining_mg IS NULL OR (typeof(estimated_remaining_mg) = 'integer' "
        f"AND abs(estimated_remaining_mg) <= {MAX_ABS_MILLIGRAMS})",
        name="estimated_mass_range",
    ),
    CheckConstraint(
        f"effective_remaining_mg IS NULL OR (typeof(effective_remaining_mg) = 'integer' "
        f"AND abs(effective_remaining_mg) <= {MAX_ABS_MILLIGRAMS})",
        name="effective_mass_range",
    ),
    CheckConstraint("typeof(ledger_sequence) = 'integer' AND ledger_sequence >= 0", name="ledger_sequence"),
    CheckConstraint(
        "(purchase_price IS NULL AND currency IS NULL) OR "
        "(purchase_price IS NOT NULL AND CAST(purchase_price AS NUMERIC) >= 0 "
        "AND currency GLOB '[A-Z][A-Z][A-Z]')",
        name="purchase_money_shape",
    ),
    CheckConstraint(f"lifecycle IN ({_values(SpoolLifecycle)})", name="lifecycle_enum"),
    CheckConstraint(f"inventory_health IN ({_values(InventoryHealth)})", name="health_enum"),
    CheckConstraint(
        "effective_remaining_mg IS NULL OR effective_remaining_mg >= 0 "
        "OR inventory_health = 'QUARANTINED'",
        name="negative_effective_quarantined",
    ),
    CheckConstraint("low_threshold_mg IS NULL OR low_threshold_mg >= 0", name="low_mass_nonnegative"),
    CheckConstraint("low_threshold_bp IS NULL OR low_threshold_bp BETWEEN 0 AND 10000", name="low_bp_range"),
    CheckConstraint(
        "(lifecycle = 'ARCHIVED' AND archived_at IS NOT NULL) OR "
        "(lifecycle <> 'ARCHIVED' AND archived_at IS NULL)",
        name="archived_shape",
    ),
)

spool_identifier = Table(
    "spool_identifier",
    metadata,
    *_mutable_columns(),
    Column(
        "spool_id",
        EntityIdType(),
        ForeignKey("spool.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("namespace", Text(), nullable=False),
    Column("kind", Text(), nullable=False),
    Column("value", Text(), nullable=False),
    Column("verified_at", UtcDateTimeType()),
    Column("retired_at", UtcDateTimeType()),
    CheckConstraint("length(namespace) BETWEEN 1 AND 200", name="namespace_length"),
    CheckConstraint("length(kind) BETWEEN 1 AND 200", name="kind_length"),
    CheckConstraint("length(value) BETWEEN 1 AND 500", name="value_length"),
    CheckConstraint(
        "retired_at IS NULL OR verified_at IS NULL OR retired_at >= verified_at",
        name="retirement_order",
    ),
)
Index(
    "uq_spool_identifier_trusted_current",
    spool_identifier.c.namespace,
    spool_identifier.c.kind,
    spool_identifier.c.value,
    unique=True,
    sqlite_where=(
        spool_identifier.c.retired_at.is_(None)
        & spool_identifier.c.verified_at.is_not(None)
    ),
)

inventory_evidence = Table(
    "inventory_evidence",
    metadata,
    *_immutable_columns(),
    Column(
        "spool_id",
        EntityIdType(),
        ForeignKey("spool.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("sensor_id", EntityIdType(), ForeignKey("sensor_device.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column(
        "calibration_id",
        EntityIdType(),
        ForeignKey("calibration_record.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    Column("gross_mg", MassType()),
    Column("tare_mg", MassType()),
    Column("net_mg", MassType()),
    Column("captured_at", UtcDateTimeType(), nullable=False),
    Column("received_at", UtcDateTimeType(), nullable=False),
    Column("stability_bp", Integer()),
    Column("stable_duration_ms", Integer()),
    Column("ledger_cutoff", Integer()),
    Column("source_type", Text(), nullable=False),
    Column("external_reference", Text()),
    Column("metadata_json", Text()),
    CheckConstraint("gross_mg IS NOT NULL OR tare_mg IS NOT NULL OR net_mg IS NOT NULL", name="mass_present"),
    CheckConstraint("gross_mg IS NULL OR gross_mg >= 0", name="gross_nonnegative"),
    CheckConstraint("tare_mg IS NULL OR tare_mg >= 0", name="tare_nonnegative"),
    CheckConstraint("net_mg IS NULL OR net_mg >= 0", name="net_nonnegative"),
    CheckConstraint(
        "gross_mg IS NULL OR tare_mg IS NULL OR net_mg IS NULL OR net_mg = gross_mg - tare_mg",
        name="net_relation",
    ),
    CheckConstraint("stability_bp IS NULL OR stability_bp BETWEEN 0 AND 10000", name="stability_range"),
    CheckConstraint("stable_duration_ms IS NULL OR stable_duration_ms >= 0", name="stable_duration"),
    CheckConstraint("ledger_cutoff IS NULL OR ledger_cutoff >= 0", name="ledger_cutoff"),
    CheckConstraint(f"source_type IN ({_values(EvidenceSource)})", name="source_enum"),
)

spool_mount = Table(
    "spool_mount",
    metadata,
    *_mutable_columns(),
    Column(
        "feed_slot_id",
        EntityIdType(),
        ForeignKey("feed_slot.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("spool_id", EntityIdType(), ForeignKey("spool.id", ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False),
    Column("state", Text(), nullable=False),
    Column("mounted_at", UtcDateTimeType(), nullable=False),
    Column("unmounted_at", UtcDateTimeType()),
    Column("assignment_source", Text(), nullable=False),
    Column("confidence_bp", Integer(), nullable=False),
    Column(
        "source_receipt_id",
        EntityIdType(),
        ForeignKey("external_event_receipt.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    ),
    CheckConstraint(f"state IN ({_values(MountState)})", name="state_enum"),
    CheckConstraint(f"assignment_source IN ({_values(AssignmentSource)})", name="source_enum"),
    CheckConstraint("confidence_bp BETWEEN 0 AND 10000", name="confidence_range"),
    CheckConstraint(
        "(state = 'ACTIVE' AND unmounted_at IS NULL) OR "
        "(state = 'CLOSED' AND unmounted_at IS NOT NULL AND unmounted_at >= mounted_at)",
        name="interval_shape",
    ),
)
Index(
    "uq_spool_mount_active_spool",
    spool_mount.c.spool_id,
    unique=True,
    sqlite_where=spool_mount.c.state == "ACTIVE",
)
Index(
    "uq_spool_mount_active_slot",
    spool_mount.c.feed_slot_id,
    unique=True,
    sqlite_where=spool_mount.c.state == "ACTIVE",
)

material_usage_segment = Table(
    "material_usage_segment",
    metadata,
    *_mutable_columns(),
    Column(
        "print_job_material_id",
        EntityIdType(),
        ForeignKey("print_job_material.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    ),
    Column("feed_slot_id", EntityIdType(), ForeignKey("feed_slot.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column("spool_mount_id", EntityIdType(), ForeignKey("spool_mount.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column("spool_id", EntityIdType(), ForeignKey("spool.id", ondelete="RESTRICT", onupdate="RESTRICT")),
    Column("tool_index", Integer(), nullable=False),
    Column("assignment_state", Text(), nullable=False),
    Column("started_at", UtcDateTimeType(), nullable=False),
    Column("ended_at", UtcDateTimeType()),
    Column("estimated_usage_mg", MassType()),
    Column("source", Text(), nullable=False),
    Column("confidence_bp", Integer(), nullable=False),
    CheckConstraint("tool_index >= 0", name="tool_nonnegative"),
    CheckConstraint(f"assignment_state IN ({_values(SlotAssignment)})", name="assignment_enum"),
    CheckConstraint("assignment_state <> 'EMPTY'", name="not_empty"),
    CheckConstraint(
        "assignment_state <> 'ASSIGNED' OR "
        "(feed_slot_id IS NOT NULL AND spool_mount_id IS NOT NULL AND spool_id IS NOT NULL)",
        name="assigned_shape",
    ),
    CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="interval_order"),
    CheckConstraint("estimated_usage_mg IS NULL OR estimated_usage_mg >= 0", name="estimated_nonnegative"),
    CheckConstraint("length(source) BETWEEN 1 AND 200", name="source_length"),
    CheckConstraint("confidence_bp BETWEEN 0 AND 10000", name="confidence_range"),
)
Index(
    "uq_material_usage_segment_open",
    material_usage_segment.c.print_job_material_id,
    unique=True,
    sqlite_where=material_usage_segment.c.ended_at.is_(None),
)

for table in (
    brand,
    sensor_device,
    storage_location,
    filament_profile,
    printer,
    printer_accounting_authority,
    connection_profile,
    haspel_authority_connection,
    material_feed_system,
    feed_slot,
    project,
    print_job,
    print_job_material,
    external_event_receipt,
    spool,
    spool_identifier,
    spool_mount,
    material_usage_segment,
):
    Index(f"ix_{table.name}_device_id", table.c.device_id)

Index("ix_storage_location_parent_id", storage_location.c.parent_id)
Index("ix_filament_profile_brand_id", filament_profile.c.brand_id)
Index("ix_material_feed_system_printer_id", material_feed_system.c.printer_id)
Index("ix_feed_slot_feed_system_id", feed_slot.c.feed_system_id)
Index("ix_calibration_record_device_id", calibration_record.c.device_id)
Index("ix_calibration_record_sensor_id", calibration_record.c.sensor_id)
Index("ix_print_job_printer_status", print_job.c.printer_id, print_job.c.status, print_job.c.detected_at)
Index("ix_print_job_finalization_state", print_job.c.finalization_state)
Index("ix_job_identity_alias_device_id", job_identity_alias.c.device_id)
Index("ix_job_identity_alias_print_job_id", job_identity_alias.c.print_job_id)
Index("ix_print_job_material_print_job_id", print_job_material.c.print_job_id)
Index("ix_external_event_receipt_printer_id", external_event_receipt.c.printer_id)
Index("ix_external_event_receipt_result_received", external_event_receipt.c.processing_result, external_event_receipt.c.received_at)
Index("ix_spool_storage_location_id", spool.c.storage_location_id)
Index("ix_spool_lifecycle_health", spool.c.lifecycle, spool.c.inventory_health)
Index("ix_spool_identifier_spool_id", spool_identifier.c.spool_id)
Index("ix_inventory_evidence_device_id", inventory_evidence.c.device_id)
Index("ix_inventory_evidence_spool_captured", inventory_evidence.c.spool_id, inventory_evidence.c.captured_at)
Index("ix_spool_mount_slot_time", spool_mount.c.feed_slot_id, spool_mount.c.mounted_at)
Index("ix_spool_mount_spool_time", spool_mount.c.spool_id, spool_mount.c.mounted_at)
Index("ix_material_usage_segment_material_time", material_usage_segment.c.print_job_material_id, material_usage_segment.c.started_at)

# Register only after every table module has joined the shared metadata graph.
from ufm.infrastructure.persistence.models.projection import (  # noqa: E402, F401
    job_projection_state,
    job_receipt_application,
)
from ufm.infrastructure.persistence.sqlite.guards import register_guards  # noqa: E402

register_guards(metadata)
