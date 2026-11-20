"""Event identifiers approved for local log and diagnostic display/export."""

SAFE_LOG_EVENT_CODES = frozenset({
    "feed_slot_mounted",
    "foundation_started",
    "localization_unavailable",
    "log_message_omitted",
    "printer_discovery_completed",
    "printer_monitor_failed",
    "printer_monitor_started",
    "printer_monitor_state",
    "printer_monitor_stopped",
    "printer_probe_completed",
    "printer_probe_failed",
    "printer_probe_started",
    "spool_identity_verified",
    "spool_sync_completed",
    "startup_validated",
    "task_failed",
})
