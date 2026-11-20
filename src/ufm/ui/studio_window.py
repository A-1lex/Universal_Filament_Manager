"""Native Qt workspace. Network work runs off the GUI thread, on user action."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import partial
from importlib.resources import files
from pathlib import Path
from typing import TypedDict, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from PySide6.QtCore import (
    QByteArray,
    QCoreApplication,
    QDate,
    QEvent,
    QIODevice,
    QLocale,
    QRectF,
    QSaveFile,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QDoubleValidator,
    QFontDatabase,
    QIcon,
    QIntValidator,
    QPainter,
    QStandardItemModel,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ufm.application.dto.providers import (
    Observed,
    PrinterCapabilities,
    PrinterEvent,
    PrinterStatusSnapshot,
)
from ufm.application.dto.slice_facts import VerifiedSliceFacts
from ufm.application.inventory import InventoryCostReport
from ufm.application.ports.persistence import NotFound
from ufm.application.ports.secrets import SecretValue
from ufm.application.slot_spool_identity import (
    SlotSpoolMatchState,
    resolve_feed_slot_spool,
)
from ufm.application.spool_identifiers import SpoolIdentifierCommands
from ufm.application.topology import TopologyCommands
from ufm.bootstrap.app_container import AppContainer, create_container
from ufm.bootstrap.settings import AppSettings, InventoryColumn, save_settings
from ufm.domain.enums import (
    AssignmentSource,
    Availability,
    FeedSystemKind,
    MaterialType,
    PrinterAccountingMode,
)
from ufm.domain.value_objects import EntityId, UtcDateTime
from ufm.infrastructure.diagnostics import build_safe_diagnostic_bundle
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.infrastructure.studio_backend import (
    StudioAccountingAuthority,
    StudioBackend,
    StudioBrand,
    StudioHaspelAuthorityConnection,
    StudioJobDetail,
    StudioMaterial,
    StudioPrinter,
    StudioReconciliationTask,
    StudioSpool,
)
from ufm.integrations.gcode_extrusion import (
    ExtrusionReport,
    inspect_gcode_file_for_local_review,
)
from ufm.integrations.haspelsync import (
    HaspelAuthoritySnapshot,
    HaspelCutoverPreview,
    HaspelCutoverPreviewRejected,
    HaspelSyncImportPreview,
    preview_haspelsync_cutover,
    preview_haspelsync_files,
)
from ufm.integrations.haspelsync.authority_client import (
    HaspelAuthorityConflict,
    HaspelBookingRecord,
    HaspelBookingResolutionUnknown,
)
from ufm.integrations.local_api import LocalApiServer
from ufm.integrations.printers.bambu_discovery import identify_bambu_printer
from ufm.integrations.printers.bambu_studio import (
    BambuPrinterIdentity,
    BambuStudioImportError,
    BambuStudioProfile,
    import_bambu_studio_profile,
    store_bambu_root_certificate,
)
from ufm.integrations.printers.configuration import (
    configure_bambu_printer,
    configure_local_printer,
    configured_printer_provider,
    ensure_local_device,
    probe_configured_printer,
    remove_configured_printer,
    update_bambu_printer_connection,
    update_printer_details,
)
from ufm.integrations.printers.discovery import (
    PrinterCandidate,
    discover_printers,
    primary_local_network,
)
from ufm.integrations.qr import spool_label_card_svg
from ufm.integrations.sliced_files import (
    inspect_3mf_file_for_local_review,
    list_3mf_plates_for_local_review,
)
from ufm.integrations.spoolman.importer import (
    SpoolmanCutoverPreview,
    SpoolmanImportPreview,
    SpoolmanImportRejected,
    SpoolmanImportResult,
    SpoolmanTargetPreview,
    default_spoolman_import_source_key,
    import_spoolman_database,
    new_spoolman_source_key,
    preview_spoolman_cutover,
    preview_spoolman_database,
    preview_spoolman_target_state,
    spoolman_import_source_label,
)
from ufm.platform.common.paths import AppPaths
from ufm.ui.printer_monitor import PrinterMonitorTask


class MaterialFormValues(TypedDict):
    name: str
    material: str
    diameter: str
    brand_id: str | None
    product_line: str | None
    density: str | None
    custom_material_name: str | None
    abrasive: bool
    flexible: bool
    hygroscopic: bool
    soluble: bool
    filled_material: bool
    subtype: str | None
    nozzle_min_c: str | None
    nozzle_max_c: str | None
    bed_min_c: str | None
    bed_max_c: str | None
    chamber_min_c: str | None
    chamber_max_c: str | None
    max_volumetric_speed_mm3_s: str | None
    drying_temp_c: str | None
    drying_duration_min: str | None
    default_color_name: str | None
    notes: str | None


class Task(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], object], parent: QWidget) -> None:
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            result = self.operation()
        except Exception as error:
            # Do not expose endpoint credentials, provider payloads or exception text.
            self.failed.emit(type(error).__name__)
        else:
            self.completed.emit(result)


@dataclass(frozen=True)
class ObservedSlotSync:
    system_key: str
    slot_key: str
    match_state: SlotSpoolMatchState
    material_hint: str | None
    color_hint: str | None
    remaining_percent: int | None
    tray_uuid: str | None
    tag_uid: str | None


class MassTableItem(QTableWidgetItem):
    def __init__(self, text: str, milligrams: int | None) -> None:
        super().__init__(text)
        self.milligrams = milligrams

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, MassTableItem):
            left = self.milligrams if self.milligrams is not None else -1
            right = other.milligrams if other.milligrams is not None else -1
            return left < right
        return super().__lt__(other)


def _safe_csv_value(value: object) -> str:
    text = str(value)
    if re.match(r"^[\s\ufeff]*[=+\-@]|^[\t\r\n]", text):
        return "'" + text
    return text


def _combined_cutover_evidence_sha256(
    haspel: HaspelCutoverPreview, spoolman: SpoolmanCutoverPreview,
) -> str:
    payload = json.dumps({
        "schema": "ufm-accounting-cutover-evidence-v1",
        "haspel_journal_sha256": haspel.evidence_sha256,
        "spoolman_source_instance": spoolman.source_instance_key,
        "spoolman_source_fingerprint": spoolman.source_fingerprint,
        "spoolman_source_unchanged": spoolman.source_unchanged_since_import,
        "spoolman_last_imported_at_ms": spoolman.last_imported_at_ms,
        "latest_haspel_activity_at_ms": haspel.latest_activity_at_ms,
        "spoolman_counts": [
            spoolman.spool_count, spoolman.matched_count,
            spoolman.mismatch_count, spoolman.missing_count,
            spoolman.unexpected_count,
        ],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _cost_report_csv(
    report: InventoryCostReport,
    text: Callable[[str], str],
    mass: Callable[[int], str],
) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([text(key) for key in (
        "cost_date", "printer", "cost_job", "cost_spool", "grams",
        "cost_amount", "currency", "cost_source", "state",
    )])
    for item in report.entries:
        record = item.transaction
        writer.writerow([_safe_csv_value(value) for value in (
            item.print_started_at.isoformat(), item.printer_name, item.job_name,
            item.spool_name, mass(-record.delta.milligrams),
            "" if record.unit_cost is None else record.unit_cost.canonical(),
            record.currency or "", record.source_type, text("cost_confirmed"),
        )])
    return "\ufeff" + output.getvalue()


def _inventory_csv(rows: tuple[StudioSpool, ...]) -> str:
    """Stable, spreadsheet-safe inventory export; intentionally excludes printer secrets."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow((
        "schema", "spool_id", "revision", "name", "brand", "profile", "material",
        "product_line", "batch_number", "lot_number", "color_name", "color_hex",
        "secondary_color_hex", "remaining_g", "nominal_filament_g", "empty_spool_g",
        "low_threshold_g", "lifecycle", "health", "location", "opened_date",
        "manufactured_date", "expires_date", "purchase_price", "currency",
        "purchase_date", "purchase_basis_g", "notes",
    ))

    def grams(milligrams: int | None) -> str:
        if milligrams is None:
            return ""
        sign = "-" if milligrams < 0 else ""
        absolute = abs(milligrams)
        return f"{sign}{absolute // 1000}.{absolute % 1000:03d}"

    for row in rows:
        values: tuple[object, ...] = (
            "ufm_inventory_v1", row.id, row.revision, row.name, row.brand or "",
            row.profile, row.material, row.product_line or "", row.batch_number or "",
            row.lot_number or "", row.color_name or "", row.color_hex or "",
            row.secondary_color_hex or "", grams(row.remaining_mg),
            grams(row.nominal_filament_mg), grams(row.empty_spool_mg),
            grams(row.low_threshold_mg), row.lifecycle, row.health, row.location or "",
            row.opened_date or "", row.manufactured_date or "", row.expires_date or "",
            row.purchase_price or "", row.currency or "", row.purchase_date or "",
            grams(row.purchase_basis_mg), row.notes or "",
        )
        writer.writerow([_safe_csv_value(value) for value in values])
    return "\ufeff" + output.getvalue()


class StudioWindow(QMainWindow):
    def __init__(self, backend: StudioBackend, container: AppContainer, locale: str) -> None:
        super().__init__()
        self.backend = backend
        self.container = container
        self.settings = container.settings
        payload = json.loads(files("ufm.ui").joinpath("studio_strings.json").read_text("utf-8"))
        self.strings: dict[str, list[str]] = payload
        self.language = 0 if locale == "uk-UA" else 1
        self.dark = container.settings.theme == "dark"
        self.tasks: list[Task] = []
        self.rows: tuple[StudioSpool, ...] = ()
        self.brand_rows: tuple[StudioBrand, ...] = ()
        self.profiles: tuple[StudioMaterial, ...] = ()
        self.printers: tuple[StudioPrinter, ...] = ()
        self._observed_slot_identities: tuple[tuple[str, str, str, str], ...] = ()
        self._observed_slots: tuple[ObservedSlotSync, ...] = ()
        self._observed_namespace: str | None = None
        self._observed_at: UtcDateTime | None = None
        self._mount_candidates: tuple[tuple[str, str, FeedSystemKind, EntityId, str], ...] = ()
        self._candidates: tuple[PrinterCandidate, ...] = ()
        self._observed_printer_id: EntityId | None = None
        self._monitor_task: PrinterMonitorTask | None = None
        self._monitor_printer_name = ""
        self._monitor_provider = ""
        self._monitor_failed = False
        self._close_when_idle = False
        self._history_signal_connected = False
        self._local_api: LocalApiServer | None = None
        self.setWindowTitle(self.text("title"))
        self.resize(1360, 860)
        self.setMinimumSize(1080, 700)
        icon = Path(__file__).with_name("assets") / "ufm.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        top = QFrame()
        top.setObjectName("top")
        top_row = QHBoxLayout(top)
        logo = QLabel("UFM STUDIO")
        logo.setObjectName("logo")
        top_row.addWidget(logo)
        top_row.addStretch()
        top_row.addWidget(QLabel(self.text("local")))
        top_row.addWidget(self.button("theme", self.toggle_theme))
        outer.addWidget(top)
        body = QHBoxLayout()
        body.setContentsMargins(16, 10, 16, 14)
        outer.addLayout(body, 1)
        side = QVBoxLayout()
        side.addWidget(QLabel(self.text("workspace")))
        self.nav = QListWidget()
        self.nav.setFixedWidth(175)
        for key in ("inventory", "printers", "materials", "settings"):
            self.nav.addItem(self.text(key))
        side.addWidget(self.nav)
        side.addWidget(QLabel(self.text("build_label")))
        body.addLayout(side)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.make_inventory()
        self._history_signal_connected = True
        self.make_printers()
        self.make_materials()
        self.make_system()
        self.nav.currentRowChanged.connect(self.switch_page)
        self.nav.setCurrentRow(0)
        self.refresh()
        self.apply_theme()
        self._sync_local_api()

    def text(self, key: str, **params: str | int) -> str:
        values = self.strings.get(key)
        return (key if values is None else values[self.language]).format_map(params)

    def button(self, key: str, action: Callable[[], None]) -> QPushButton:
        button = QPushButton(self.text(key))
        button.setMinimumHeight(34)
        button.clicked.connect(action)
        return button

    def page(self, key: str) -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 12, 18, 12)
        title = QLabel(self.text(key))
        title.setObjectName("heading")
        layout.addWidget(title)
        self.pages.addWidget(page)
        return layout

    def table(self, keys: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(keys))
        table.setHorizontalHeaderLabels([self.text(k) for k in keys])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    def fill(
        self,
        table: QTableWidget,
        rows: list[list[str]],
        identities: tuple[str, ...] = (),
        search_values: tuple[str, ...] = (),
        mass_values: tuple[int | None, ...] = (),
        mass_column: int | None = None,
        material_values: tuple[str, ...] = (),
        known_stock_values: tuple[bool, ...] = (),
        lifecycle_values: tuple[str, ...] = (),
        location_values: tuple[str, ...] = (),
        color_values: tuple[str | None, ...] = (),
    ) -> None:
        sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate(row):
                item = (
                    MassTableItem(value, mass_values[index]) if column == mass_column
                    else QTableWidgetItem(value)
                )
                if column == 0 and identities:
                    item.setData(Qt.ItemDataRole.UserRole, identities[index])
                    for role, values in enumerate((
                        search_values, material_values, known_stock_values,
                        lifecycle_values, location_values,
                    ), start=1):
                        if values:
                            item.setData(Qt.ItemDataRole.UserRole + role, values[index])
                if column == 2 and color_values:
                    self.apply_color_swatch(item, color_values[index])
                table.setItem(index, column, item)
        table.setSortingEnabled(sorting)

    @staticmethod
    def apply_color_swatch(
        item: QTableWidgetItem | QListWidgetItem, color_value: str | None,
    ) -> None:
        if not isinstance(color_value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color_value) is None:
            return
        color = QColor(color_value)
        item.setBackground(QBrush(color))
        luminance = (
            0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()
        ) / 255
        foreground = QColor("#111827" if luminance > 0.52 else "#ffffff")
        item.setForeground(QBrush(foreground))

    def refresh_cards(self) -> None:
        self.inventory_cards.clear()
        for row in self.rows:
            item = QListWidgetItem(
                f"{row.name}\n{row.profile} · {row.material}\n"
                f"{self.mass(row.remaining_mg)} г · {self.text(row.lifecycle)}\n"
                f"{row.location or self.text('unknown')} · "
                f"{row.color_name or row.color_hex or self.text('unknown')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, row.id)
            item.setData(Qt.ItemDataRole.UserRole + 1,
                         f"{row.name} {row.profile} {row.material} "
                         f"{row.color_name or ''} {row.color_hex or ''} {row.location or ''}")
            item.setData(Qt.ItemDataRole.UserRole + 2, row.material)
            item.setData(Qt.ItemDataRole.UserRole + 3, row.remaining_mg is not None)
            item.setData(Qt.ItemDataRole.UserRole + 4, row.lifecycle)
            item.setData(Qt.ItemDataRole.UserRole + 5, row.location or "")
            item.setSizeHint(QSize(230, 100))
            self.apply_color_swatch(item, row.color_hex)
            self.inventory_cards.addItem(item)

    def make_inventory(self) -> None:
        layout = self.page("inventory")
        layout.addWidget(QLabel(self.text("subtitle")))
        stats = QHBoxLayout()
        self.metrics: list[QLabel] = []
        for key in ("spools_count", "known_mass", "unknown_count", "printers_count"):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(self.text(key)))
            value = QLabel("—")
            value.setObjectName("metric")
            card_layout.addWidget(value)
            stats.addWidget(card)
            self.metrics.append(value)
        layout.addLayout(stats)
        filters = QGridLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.text("search"))
        self.search.textChanged.connect(self.filter_rows)
        filters.addWidget(self.search, 0, 0, 1, 2)
        self.material_filter = QComboBox()
        self.material_filter.addItem(self.text("filter_all_materials"), "")
        self.material_filter.currentIndexChanged.connect(self.filter_rows)
        filters.addWidget(self.material_filter, 0, 2)
        self.stock_filter = QComboBox()
        for label_key, stock_key in (("filter_all_stock", "all"),
                                     ("filter_known_stock", "known"),
                                     ("filter_unknown_stock", "unknown")):
            self.stock_filter.addItem(self.text(label_key), stock_key)
        self.stock_filter.currentIndexChanged.connect(self.filter_rows)
        filters.addWidget(self.stock_filter, 0, 3)
        self.lifecycle_filter = QComboBox()
        for label_key, lifecycle_key in (("filter_all_lifecycle", "all"),
                                         ("NEW", "NEW"), ("OPEN", "OPEN"),
                                         ("ARCHIVED", "ARCHIVED")):
            self.lifecycle_filter.addItem(self.text(label_key), lifecycle_key)
        self.lifecycle_filter.currentIndexChanged.connect(self.filter_rows)
        filters.addWidget(self.lifecycle_filter, 1, 0)
        self.location_filter = QComboBox()
        self.location_filter.addItem(self.text("filter_all_locations"), "")
        self.location_filter.currentIndexChanged.connect(self.filter_rows)
        filters.addWidget(self.location_filter, 1, 1)
        self.inventory_view = QComboBox()
        self.inventory_view.addItem(self.text("view_table"), "table")
        self.inventory_view.addItem(self.text("view_cards"), "cards")
        filters.addWidget(self.inventory_view, 1, 2)
        filters.addWidget(self.button("choose_columns", self.choose_inventory_columns), 1, 3)
        filters.setColumnStretch(0, 2)
        for column in range(1, 4):
            filters.setColumnStretch(column, 1)
        layout.addLayout(filters)

        actions = QGridLayout()
        self.add_spool_button = self.button("new_spool", self.add_spool)
        action_buttons = [self.add_spool_button]
        self.add_location_button = self.button("new_location", self.add_storage_location)
        action_buttons.extend((
            self.add_location_button,
            self.button("cost_report", self.show_cost_report),
            self.button("batch_export_qr_labels", self.batch_export_qr_labels),
            self.button("refresh", self.refresh),
        ))
        for index, button in enumerate(action_buttons):
            actions.addWidget(button, index // 4, index % 4)
        for column in range(4):
            actions.setColumnStretch(column, 1)
        layout.addLayout(actions)
        content = QHBoxLayout()
        self.inventory = self.table((
            "name", "material", "color", "location", "remaining", "state", "health",
        ))
        self.apply_inventory_columns({
            index for index, key in enumerate(
                ("name", "material", "color", "location", "remaining", "state", "health")
            ) if key in self.settings.inventory_columns
        })
        self.inventory.setSortingEnabled(True)
        self.inventory.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.inventory.itemSelectionChanged.connect(self.show_history)
        self.inventory_cards = QListWidget()
        self.inventory_cards.setViewMode(QListView.ViewMode.IconMode)
        self.inventory_cards.setFlow(QListView.Flow.LeftToRight)
        self.inventory_cards.setResizeMode(QListView.ResizeMode.Adjust)
        self.inventory_cards.setMovement(QListView.Movement.Static)
        self.inventory_cards.setWrapping(True)
        self.inventory_cards.setWordWrap(True)
        self.inventory_cards.setGridSize(QSize(250, 112))
        self.inventory_cards.setSpacing(8)
        self.inventory_cards.itemSelectionChanged.connect(self.show_history)
        self.inventory_views = QStackedWidget()
        self.inventory_views.addWidget(self.inventory)
        self.inventory_views.addWidget(self.inventory_cards)
        self.inventory_view.currentIndexChanged.connect(self.switch_inventory_view)
        content.addWidget(self.inventory_views, 3)
        inspector = QFrame()
        inspector.setObjectName("card")
        detail = QVBoxLayout(inspector)
        detail.addWidget(QLabel(self.text("inspector")))
        self.selection = QLabel(self.text("select"))
        self.selection.setWordWrap(True)
        detail.addWidget(self.selection)
        self.stock_buttons: list[QPushButton] = []
        for key in ("opening", "deduct", "add"):
            button = self.button(key, partial(self.stock, key))
            self.stock_buttons.append(button)
            detail.addWidget(button)
        self.inventory_action_buttons = [
            self.button("edit_spool", self.edit_spool),
            self.button("record_measurement", self.record_measurement),
            self.button("archive_spool", self.archive_spool),
            self.button("rebuild_projection", self.rebuild_projection),
            self.button("assign_location", self.assign_storage_location),
        ]
        for button in self.inventory_action_buttons:
            button.setEnabled(False)
            detail.addWidget(button)
        self.qr_label_button = self.button("export_qr_label", self.export_qr_label)
        self.qr_label_button.setEnabled(False)
        detail.addWidget(self.qr_label_button)
        self.print_qr_label_button = self.button("print_qr_label", self.print_qr_label)
        self.print_qr_label_button.setEnabled(False)
        detail.addWidget(self.print_qr_label_button)
        self.compensate_button = self.button("compensate", self.compensate_transaction)
        self.compensate_button.setEnabled(False)
        detail.addWidget(self.compensate_button)
        detail.addWidget(QLabel(self.text("history")))
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        detail.addWidget(self.history, 1)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        inspector_scroll.setWidget(inspector)
        content.addWidget(inspector_scroll, 2)
        layout.addLayout(content, 1)
        self.empty_inventory_hint = QLabel(self.text("empty_inventory"))
        self.empty_inventory_hint.setObjectName("notice")
        self.empty_inventory_hint.setWordWrap(True)
        self.empty_inventory_hint.hide()
        layout.addWidget(self.empty_inventory_hint)
        self.inventory_unavailable_hint = QLabel(self.text("inventory_unavailable"))
        self.inventory_unavailable_hint.setObjectName("notice")
        self.inventory_unavailable_hint.setWordWrap(True)
        self.inventory_unavailable_hint.hide()
        layout.addWidget(self.inventory_unavailable_hint)
        self.filter_empty_hint = QLabel(self.text("filter_no_results"))
        self.filter_empty_hint.setObjectName("notice")
        self.filter_empty_hint.hide()
        layout.addWidget(self.filter_empty_hint)
        gate = QLabel(self.text("auto_gate"))
        gate.setWordWrap(True)
        gate.setObjectName("notice")
        layout.addWidget(gate)

    def make_printers(self) -> None:
        layout = self.page("printers")
        toolbar = QGridLayout()
        actions = [
            self.button("discover", self.discover),
            self.button("probe", self.probe),
            self.button("verify_identity_button", self.verify_feed_identity),
            self.button("sync_spools_button", self.sync_observed_spools),
            self.button("mount_verified_button", self.mount_verified_feed_slot),
            self.button("enrollment", self.enroll_local),
            self.button("bambu_import", self.enroll_bambu),
            self.button("network_autofill", self.enroll_bambu_network),
        ]
        self.accounting_authority_button = self.button(
            "accounting_authority", self.manage_accounting_authority,
        )
        self.accounting_authority_button.setEnabled(False)
        actions.append(self.accounting_authority_button)
        self.remove_printer_button = self.button("remove_printer", self.remove_printer)
        self.remove_printer_button.setEnabled(False)
        actions.append(self.remove_printer_button)
        self.edit_printer_button = self.button("edit_printer", self.edit_printer)
        self.edit_printer_button.setEnabled(False)
        actions.append(self.edit_printer_button)
        self.edit_printer_connection_button = self.button(
            "edit_printer_connection", self.edit_printer_connection,
        )
        self.edit_printer_connection_button.setEnabled(False)
        actions.append(self.edit_printer_connection_button)
        self.monitor_button = self.button("monitor_start", self.toggle_printer_monitor)
        actions.append(self.monitor_button)
        actions.append(self.button("print_jobs", self.show_print_jobs))
        actions.append(self.button("recon_tasks", self.show_reconciliation_tasks))
        for index, button in enumerate(actions):
            toolbar.addWidget(button, index // 4, index % 4)
        for column in range(4):
            toolbar.setColumnStretch(column, 1)
        layout.addLayout(toolbar)
        self.printer_table = self.table(("name", "model", "provider", "host"))
        self.printer_table.itemSelectionChanged.connect(self.update_printer_actions)
        layout.addWidget(self.printer_table, 1)
        for key in ("discovery_hint", "control_gate"):
            hint = QLabel(self.text(key))
            hint.setWordWrap(True)
            layout.addWidget(hint)
        self.monitor_status = QLabel(self.text("monitor_idle"))
        self.monitor_status.setWordWrap(True)
        layout.addWidget(self.monitor_status)
        self.monitor_details = QLabel(self.text("monitor_details_idle"))
        self.monitor_details.setWordWrap(True)
        layout.addWidget(self.monitor_details)
        self.monitor_capabilities = QLabel(self.text("monitor_capabilities_idle"))
        self.monitor_capabilities.setWordWrap(True)
        layout.addWidget(self.monitor_capabilities)
        self.monitor_slot_details = QLabel(self.text("monitor_slots_idle"))
        self.monitor_slot_details.setWordWrap(True)
        layout.addWidget(self.monitor_slot_details)
        self.device_result = QTextEdit()
        self.device_result.setReadOnly(True)
        self.device_result.setMaximumHeight(90)
        layout.addWidget(self.device_result)
        self.candidate_list = QListWidget()
        self.candidate_list.setVisible(False)
        self.candidate_list.setMaximumHeight(110)
        self.candidate_list.currentRowChanged.connect(self.update_candidate_actions)
        layout.addWidget(self.candidate_list)
        self.connect_candidate_button = self.button(
            "connect_candidate", self.connect_candidate,
        )
        self.connect_candidate_button.setEnabled(False)
        layout.addWidget(self.connect_candidate_button)

    def make_materials(self) -> None:
        layout = self.page("materials")
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.button("new_material", self.add_material))
        self.edit_material_button = self.button("edit_material", self.edit_material)
        self.edit_material_button.setEnabled(False)
        toolbar.addWidget(self.edit_material_button)
        toolbar.addWidget(self.button("new_brand", self.add_brand))
        self.edit_brand_button = self.button("edit_brand", self.edit_brand)
        self.edit_brand_button.setEnabled(False)
        toolbar.addWidget(self.edit_brand_button)
        self.archive_brand_button = self.button("archive_brand", self.archive_brand)
        self.archive_brand_button.setEnabled(False)
        toolbar.addWidget(self.archive_brand_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.empty_materials_hint = QLabel(self.text("no_profiles"))
        self.empty_materials_hint.setObjectName("notice")
        self.empty_materials_hint.setWordWrap(True)
        self.empty_materials_hint.hide()
        layout.addWidget(self.empty_materials_hint)
        self.material_table = self.table(("name", "brand", "material", "diameter", "density"))
        self.material_table.itemSelectionChanged.connect(self.update_material_actions)
        layout.addWidget(self.material_table)
        self.brand_table = self.table(("brand",))
        self.brand_table.itemSelectionChanged.connect(self.update_brand_actions)
        layout.addWidget(self.brand_table)

    def inspect_local_slice_file(self) -> None:
        """Review a local supported slice file; this action never changes stock."""
        filename, _ = QFileDialog.getOpenFileName(
            self, self.text("inspect_slice_title"), "",
            "Sliced files (*.3mf *.gcode);;3MF (*.3mf);;G-code (*.gcode)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() == ".3mf":
            pending: dict[str, object] = {}

            def store_plates(result: object) -> None:
                pending["plates"] = result

            def choose_plate() -> None:
                plates = pending.get("plates")
                if not isinstance(plates, tuple) or not plates or not self.isVisible():
                    return
                selected, accepted = QInputDialog.getItem(
                    self, self.text("inspect_3mf_title"),
                    self.text("inspect_3mf_plate_prompt"),
                    [str(plate) for plate in plates], 0, False,
                )
                if not accepted:
                    return
                plate = int(selected)
                self.work(
                    lambda: inspect_3mf_file_for_local_review(path, plate=plate),
                    self.show_local_3mf_review,
                )

            self.work(
                lambda: list_3mf_plates_for_local_review(path),
                store_plates, after_finished=choose_plate,
            )
        elif path.suffix.casefold() == ".gcode":
            self.work(
                lambda: inspect_gcode_file_for_local_review(path),
                self.show_local_gcode_review,
            )
        else:
            self.error("slice.file_type_unsupported")

    def show_local_3mf_review(self, result: object) -> None:
        facts = cast(VerifiedSliceFacts, result)
        materials = "\n".join(
            self.text(
                "inspect_3mf_material_line", index=item.logical_material,
                grams=item.used_g,
            )
            for item in facts.filaments
        )
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle(self.text("inspect_3mf_title"))
        message.setText(self.text(
            "inspect_3mf_summary", sha256=facts.file_sha256, plate=facts.plate,
            parser=facts.parser_version, count=len(facts.filaments),
            grams=f"{sum(item.mass_mg for item in facts.filaments) / 1000:.3f}",
        ))
        message.setDetailedText(materials)
        message.exec()

    def show_local_gcode_review(self, result: object) -> None:
        report = cast(ExtrusionReport, result)
        details = "\n".join(
            self.text(
                "inspect_gcode_bucket_line", tool=bucket.tool,
                layer=(self.text("inspect_gcode_unknown_layer")
                       if bucket.layer is None else bucket.layer),
                millimetres=format(bucket.fresh_mm, "f"),
            )
            for bucket in report.buckets
        ) or self.text("inspect_gcode_no_extrusion")
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle(self.text("inspect_slice_title"))
        message.setText(self.text(
            "inspect_gcode_summary", sha256=report.file_sha256,
            parser=report.parser_version, dialect=report.dialect,
            buckets=len(report.buckets),
        ))
        message.setDetailedText(details)
        message.exec()

    def make_system(self) -> None:
        layout = self.page("settings")
        hint = QLabel(self.text("system_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        locale_row = QHBoxLayout()
        locale_row.addWidget(QLabel(self.text("application_language")))
        self.locale_selector = QComboBox()
        self.locale_selector.addItem(self.text("language_ukrainian"), "uk-UA")
        self.locale_selector.addItem(self.text("language_english"), "en-US")
        self.locale_selector.setCurrentIndex(self.locale_selector.findData(self.settings.locale))
        locale_row.addWidget(self.locale_selector)
        locale_row.addWidget(self.button("save_language", self.save_language))
        layout.addLayout(locale_row)
        log_row = QHBoxLayout()
        log_row.addWidget(QLabel(self.text("log_level")))
        self.log_level_selector = QComboBox()
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            self.log_level_selector.addItem(self.text(f"log_level_{level}"), level)
        self.log_level_selector.setCurrentIndex(
            self.log_level_selector.findData(self.settings.log_level)
        )
        log_row.addWidget(self.log_level_selector)
        log_row.addWidget(self.button("save_log_level", self.save_log_level))
        layout.addLayout(log_row)
        api_hint = QLabel(self.text("local_api_hint"))
        api_hint.setWordWrap(True)
        layout.addWidget(api_hint)
        api_row = QHBoxLayout()
        api_row.addWidget(QLabel(self.text("local_api_port")))
        self.local_api_port = QSpinBox()
        self.local_api_port.setRange(1, 65535)
        self.local_api_port.setValue(self.settings.local_api_port)
        api_row.addWidget(self.local_api_port)
        self.local_api_button = self.button("local_api_off", self.toggle_local_api)
        api_row.addWidget(self.local_api_button)
        api_row.addStretch(1)
        layout.addLayout(api_row)
        for key, action in (
            ("export_inventory", self.export_inventory),
            ("import", self.import_database),
            ("backup", self.backup),
        ):
            layout.addWidget(self.button(key, action))
        layout.addWidget(self.button("view_safe_logs", self.view_safe_logs))
        layout.addWidget(self.button("export_diagnostics", self.export_diagnostics))
        path = QLabel(str(self.backend.paths.data))
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path)
        layout.addStretch()

    def save_language(self) -> None:
        locale = self.locale_selector.currentData()
        if locale not in ("uk-UA", "en-US"):
            return
        previous_locale = self.settings.locale
        settings = self.settings.model_copy(update={"locale": locale})
        try:
            save_settings(settings, self.backend.paths.config / "settings.json")
        except (OSError, ValueError):
            self.error("settings.invalid")
            return
        self.settings = settings
        if locale != previous_locale:
            QMessageBox.information(
                self, self.text("save_language"), self.text("language_restart_required"),
            )

    def save_log_level(self) -> None:
        level = self.log_level_selector.currentData()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            return
        settings = self.settings.model_copy(update={"log_level": level})
        try:
            save_settings(settings, self.backend.paths.config / "settings.json")
        except (OSError, ValueError):
            self.error("settings.invalid")
            return
        self.settings = settings
        self.container.logger.setLevel(level)

    def _sync_local_api(self) -> None:
        if not self.settings.local_api_enabled:
            return
        try:
            self._start_local_api(self.settings.local_api_port, persist=False)
        except Exception:
            self.error("local_api_start_failed")

    def _start_local_api(self, port: int, *, persist: bool) -> None:
        if self._local_api is not None and self._local_api.running:
            return
        server = LocalApiServer(self.backend, port=port)
        bound = server.start()
        self._local_api = server
        if persist:
            settings = self.settings.model_copy(
                update={"local_api_enabled": True, "local_api_port": bound}
            )
            try:
                save_settings(settings, self.backend.paths.config / "settings.json")
            except (OSError, ValueError):
                server.stop()
                self._local_api = None
                raise
            self.settings = settings
            self.local_api_port.setValue(bound)
        self._update_local_api_button()

    def _stop_local_api(self, *, persist: bool) -> None:
        if self._local_api is not None:
            self._local_api.stop()
            self._local_api = None
        if persist:
            settings = self.settings.model_copy(update={"local_api_enabled": False})
            try:
                save_settings(settings, self.backend.paths.config / "settings.json")
            except (OSError, ValueError):
                self.error("settings.invalid")
                return
            self.settings = settings
        self._update_local_api_button()

    def _update_local_api_button(self) -> None:
        running = self._local_api is not None and self._local_api.running
        self.local_api_button.setText(
            self.text("local_api_on" if running else "local_api_off")
        )

    def toggle_local_api(self) -> None:
        running = self._local_api is not None and self._local_api.running
        if running:
            self._stop_local_api(persist=True)
            return
        port = self.local_api_port.value()
        try:
            self._start_local_api(port, persist=True)
        except Exception:
            self.error("local_api_start_failed")

    def view_safe_logs(self) -> None:
        path = self.backend.paths.logs / "ufm.log"
        try:
            content = path.read_bytes()[-512 * 1024:]
        except FileNotFoundError:
            content = b""
        except OSError:
            QMessageBox.warning(
                self, self.text("view_safe_logs"), self.text("logs.unavailable"),
            )
            return
        safe_lines: list[str] = []
        for raw_line in content.splitlines()[-300:]:
            if len(raw_line) > 2048:
                safe_lines.append(self.text("log_record_omitted"))
                continue
            try:
                record = json.loads(raw_line.decode("utf-8"))
                if not isinstance(record, dict):
                    raise ValueError("log.record_invalid")
                timestamp, level, event = (
                    record.get("timestamp"), record.get("level"), record.get("event")
                )
                if (
                    not isinstance(timestamp, str) or len(timestamp) > 40
                    or level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
                    or not isinstance(event, str) or len(event) > 80
                    or re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", event) is None
                ):
                    raise ValueError("log.record_invalid")
                rendered_time = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
                safe_lines.append(f"{rendered_time} [{level}] {event}")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
                safe_lines.append(self.text("log_record_omitted"))
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("view_safe_logs"))
        dialog.resize(900, 560)
        layout = QVBoxLayout(dialog)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText("\n".join(safe_lines) or self.text("logs_empty"))
        layout.addWidget(viewer, 1)
        close = QPushButton(self.text("close"))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def export_diagnostics(self) -> None:
        """Preview and export a consented bundle containing only safe log event metadata."""
        source = self.backend.paths.logs / "ufm.log"
        try:
            log_bytes = source.read_bytes()[-512 * 1024:]
            payload = build_safe_diagnostic_bundle(log_bytes, datetime.now().astimezone())
        except FileNotFoundError:
            payload = build_safe_diagnostic_bundle(b"", datetime.now().astimezone())
        except (OSError, ValueError):
            QMessageBox.warning(
                self, self.text("export_diagnostics"), self.text("diagnostics_failed"),
            )
            return
        manifest = json.loads(payload)["manifest"]
        preview = self.text(
            "diagnostics_preview",
            included=manifest["includedRecords"],
            omitted=manifest["omittedRecords"],
            digest=manifest["eventsSha256"],
        )
        if QMessageBox.question(
            self,
            self.text("diagnostics_consent_title"),
            preview,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            self.text("diagnostics_save_title"),
            "UFM_diagnostics.json",
            "JSON (*.json)",
        )
        if not file_name:
            return
        destination = QSaveFile(file_name)
        if (
            not destination.open(QIODevice.OpenModeFlag.WriteOnly)
            or destination.write(payload) != len(payload)
            or not destination.commit()
        ):
            destination.cancelWriting()
            QMessageBox.warning(
                self, self.text("export_diagnostics"), self.text("diagnostics_failed"),
            )
            return
        QMessageBox.information(
            self, self.text("export_diagnostics"), self.text("diagnostics_saved"),
        )

    def refresh(self) -> None:
        selected = self.selected()
        try:
            rows = self.backend.spools()
            brand_rows = self.backend.brand_records()
            profiles = self.backend.materials()
            printers = self.backend.printers()
        except Exception:
            # A local database may be temporarily unavailable (e.g. locked or
            # moved). Clear stale data and prevent inventory mutations until a
            # successful refresh; never display raw exception details.
            self.rows = ()
            self.brand_rows = ()
            self.profiles = ()
            self.printers = ()
            self.fill(self.inventory, [], ())
            self.inventory_cards.clear()
            self.empty_materials_hint.hide()
            self.fill(self.material_table, [])
            self.fill(self.brand_table, [], (), ())
            self.fill(self.printer_table, [])
            for label in self.metrics:
                label.setText("—")
            self.empty_inventory_hint.hide()
            self.filter_empty_hint.hide()
            self.inventory_unavailable_hint.show()
            self.inventory_views.setEnabled(False)
            self.add_spool_button.setEnabled(False)
            self.add_location_button.setEnabled(False)
            for button in (*self.stock_buttons, *self.inventory_action_buttons):
                button.setEnabled(False)
            self.compensate_button.setEnabled(False)
            self.selection.setText(self.text("inventory_unavailable"))
            self.history.clear()
            self.statusBar().showMessage(self.text("inventory_unavailable"))
            return

        self.rows = rows
        self.brand_rows = brand_rows
        self.profiles = profiles
        self.printers = printers
        self.inventory_unavailable_hint.hide()
        self.inventory_views.setEnabled(True)
        self.add_spool_button.setEnabled(True)
        self.add_location_button.setEnabled(True)
        self.fill(self.inventory, [[
            r.name, r.material, r.color_name or r.color_hex or self.text("unknown"),
            r.location or self.text("unknown"), self.mass(r.remaining_mg),
            self.text(r.lifecycle), self.text(r.health),
        ] for r in self.rows],
            tuple(row.id for row in self.rows),
            tuple(f"{row.name} {row.profile} {row.material} "
                  f"{row.color_name or ''} {row.color_hex or ''} "
                  f"{row.location or ''}" for row in self.rows),
            tuple(row.remaining_mg for row in self.rows), 4,
            tuple(row.material for row in self.rows),
            tuple(row.remaining_mg is not None for row in self.rows),
            tuple(row.lifecycle for row in self.rows),
            tuple(row.location or "" for row in self.rows),
            tuple(row.color_hex for row in self.rows))
        self.refresh_cards()
        self.fill(self.material_table, [[
            p.name, p.brand or self.text("unknown"), p.material,
            p.diameter_mm, p.density_g_cm3 or self.text("unknown"),
        ] for p in self.profiles])
        self.empty_materials_hint.setVisible(not self.profiles)
        for index, profile in enumerate(self.profiles):
            identity_cell = self.material_table.item(index, 0)
            if identity_cell is not None:
                identity_cell.setData(Qt.ItemDataRole.UserRole, profile.id)
        self.update_material_actions()
        self.fill(self.brand_table, [[entry.name] for entry in self.brand_rows],
                  tuple(entry.id for entry in self.brand_rows),
                  tuple(entry.name for entry in self.brand_rows))
        self.update_brand_actions()
        self.fill(self.printer_table, [[p.name, p.model, p.provider, p.host] for p in self.printers])
        self.update_printer_actions()
        counts = [str(len(self.rows)), self.mass(sum(
            r.remaining_mg for r in self.rows if r.remaining_mg is not None
        )), str(sum(r.remaining_mg is None for r in self.rows)), str(len(self.printers))]
        for label, count in zip(self.metrics, counts, strict=True):
            label.setText(count)
        self.empty_inventory_hint.setVisible(not self.rows)
        selected_material = self.material_filter.currentData()
        self.material_filter.blockSignals(True)
        self.material_filter.clear()
        self.material_filter.addItem(self.text("filter_all_materials"), "")
        for material in sorted({row.material for row in self.rows}):
            self.material_filter.addItem(material, material)
        material_index = self.material_filter.findData(selected_material)
        self.material_filter.setCurrentIndex(max(0, material_index))
        self.material_filter.blockSignals(False)
        selected_location = self.location_filter.currentData()
        self.location_filter.blockSignals(True)
        self.location_filter.clear()
        self.location_filter.addItem(self.text("filter_all_locations"), "")
        for location in sorted({row.location for row in self.rows if row.location}):
            self.location_filter.addItem(location, location)
        location_index = self.location_filter.findData(selected_location)
        self.location_filter.setCurrentIndex(max(0, location_index))
        self.location_filter.blockSignals(False)
        self.filter_rows()
        restored = selected is not None and self.select_inventory_identity(selected.id)
        if not restored:
            first_visible = next((
                item.data(Qt.ItemDataRole.UserRole)
                for index in range(self.inventory.rowCount())
                if (item := self.inventory.item(index, 0)) is not None
                and not self.inventory.isRowHidden(index)
            ), None)
            if first_visible is not None:
                self.select_inventory_identity(str(first_visible))
            else:
                self.clear_inventory_selection()
        self.show_history()
        self.statusBar().showMessage(self.text("ready"))

    def select_inventory_identity(self, identity: str) -> bool:
        if self.inventory_views.currentIndex() == 1:
            for index in range(self.inventory_cards.count()):
                card_item = self.inventory_cards.item(index)
                if (card_item.data(Qt.ItemDataRole.UserRole) == identity
                        and not card_item.isHidden()):
                    self.inventory_cards.setCurrentItem(card_item)
                    return True
            return False
        for index in range(self.inventory.rowCount()):
            table_item = self.inventory.item(index, 0)
            if (table_item is not None and not self.inventory.isRowHidden(index)
                    and table_item.data(Qt.ItemDataRole.UserRole) == identity):
                self.inventory.selectRow(index)
                return True
        return False

    def clear_inventory_selection(self) -> None:
        self.inventory.clearSelection()
        self.inventory.setCurrentCell(-1, -1)
        self.inventory_cards.clearSelection()
        self.inventory_cards.setCurrentRow(-1)

    def switch_inventory_view(self, index: int) -> None:
        selected = self.selected()
        self.inventory_views.setCurrentIndex(index)
        if selected is None or not self.select_inventory_identity(selected.id):
            self.clear_inventory_selection()

    def apply_inventory_columns(self, visible_columns: set[int]) -> None:
        """Apply the table-only column preference; keep the identity column visible."""
        visible = set(visible_columns)
        visible.add(0)
        for column in range(self.inventory.columnCount()):
            self.inventory.setColumnHidden(column, column not in visible)

    def choose_inventory_columns(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("choose_columns"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.text("columns_hint")))
        checks: list[QCheckBox] = []
        labels = ("name", "material", "color", "location", "remaining", "state", "health")
        for column, key in enumerate(labels):
            check = QCheckBox(self.text(key))
            check.setChecked(not self.inventory.isColumnHidden(column))
            if column == 0:
                check.setChecked(True)
                check.setEnabled(False)
            check.setObjectName(f"inventory_column_{column}")
            checks.append(check)
            layout.addWidget(check)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = tuple(
                cast(InventoryColumn, key)
                for key, check in zip(labels, checks, strict=True)
                if check.isChecked() or key == "name"
            )
            settings = self.settings.model_copy(update={"inventory_columns": selected})
            try:
                save_settings(settings, self.backend.paths.config / "settings.json")
            except (OSError, ValueError):
                self.error("settings.invalid")
                return
            self.settings = settings
            visible = {index for index, check in enumerate(checks) if check.isChecked()}
            self.apply_inventory_columns(visible)
        self.show_history()

    def mass(self, mg: int | None) -> str:
        if mg is None:
            return self.text("unknown")
        sign = "−" if mg < 0 else ""
        absolute = abs(mg)
        return f"{sign}{absolute // 1000:,}.{absolute % 1000:03d}".replace(",", " ")

    def selected(self) -> StudioSpool | None:
        identity: object | None = None
        if self.inventory_views.currentIndex() == 1:
            card_item = self.inventory_cards.currentItem()
            if card_item is not None:
                identity = card_item.data(Qt.ItemDataRole.UserRole)
        else:
            index = self.inventory.currentRow()
            if index >= 0:
                table_item = self.inventory.item(index, 0)
                if table_item is not None:
                    identity = table_item.data(Qt.ItemDataRole.UserRole)
        return next((row for row in self.rows if row.id == identity), None)

    def filter_rows(self) -> None:
        query = self.search.text().strip().casefold()
        material = self.material_filter.currentData()
        stock = self.stock_filter.currentData()
        lifecycle = self.lifecycle_filter.currentData()
        location = self.location_filter.currentData()
        def matches(item: QTableWidgetItem | QListWidgetItem | None) -> bool:
            search_text = "" if item is None else str(
                item.data(Qt.ItemDataRole.UserRole + 1) or item.text()
            )
            row_material = None if item is None else item.data(Qt.ItemDataRole.UserRole + 2)
            known_stock = bool(
                item is not None and item.data(Qt.ItemDataRole.UserRole + 3)
            )
            row_lifecycle = None if item is None else item.data(Qt.ItemDataRole.UserRole + 4)
            row_location = None if item is None else item.data(Qt.ItemDataRole.UserRole + 5)
            matches_search = query in search_text.casefold()
            matches_material = not material or row_material == material
            matches_stock = (
                stock == "all" or (stock == "known" and known_stock)
                or (stock == "unknown" and not known_stock)
            )
            matches_lifecycle = lifecycle == "all" or row_lifecycle == lifecycle
            matches_location = not location or row_location == location
            return all((matches_search, matches_material, matches_stock,
                        matches_lifecycle, matches_location))

        for index in range(self.inventory.rowCount()):
            table_item = self.inventory.item(index, 0)
            self.inventory.setRowHidden(index, not matches(table_item))
        for index in range(self.inventory_cards.count()):
            card_item = self.inventory_cards.item(index)
            card_item.setHidden(not matches(card_item))
        self.filter_empty_hint.setVisible(
            bool(self.rows) and not any(
                not self.inventory.isRowHidden(index)
                for index in range(self.inventory.rowCount())
            ),
        )
        current = self.inventory.currentRow()
        if current >= 0 and self.inventory.isRowHidden(current):
            self.inventory.setCurrentCell(-1, -1)
            self.show_history()
        card = self.inventory_cards.currentItem()
        if card is not None and card.isHidden():
            self.inventory_cards.setCurrentRow(-1)
            self.show_history()

    def show_history(self) -> None:
        selected = self.selected()
        for index, button in enumerate(self.stock_buttons):
            active = selected is not None and selected.lifecycle != "ARCHIVED" and not self.tasks
            known = selected is not None and selected.remaining_mg is not None
            button.setEnabled(bool(active and (not known if index == 0 else known)))
        for button in self.inventory_action_buttons:
            button.setEnabled(bool(
                selected is not None and selected.lifecycle != "ARCHIVED" and not self.tasks
            ))
        self.qr_label_button.setEnabled(selected is not None)
        self.print_qr_label_button.setEnabled(selected is not None)
        self.compensate_button.setEnabled(False)
        if selected is None:
            self.selection.setText(self.text("select"))
            self.history.clear()
            return
        self.selection.setText(f"{selected.name}\n{selected.profile}\n{selected.id}")
        try:
            records = self.backend.history(selected.id)
            measurement_records = self.backend.measurement_history(selected.id)
            cost = self.backend.cost_summary(selected.id)
        except Exception as error:
            self.history.clear()
            self.error(type(error).__name__)
            return
        compensated = {
            str(record.compensates_transaction_id)
            for record in records if record.compensates_transaction_id is not None
        }
        self.compensate_button.setEnabled(bool(
            selected.lifecycle != "ARCHIVED" and not self.tasks and any(
                record.delta.milligrams != 0
                and record.compensates_transaction_id is None
                and str(record.id) not in compensated for record in records
            )
        ))
        measurement_lines = []
        for item in measurement_records:
            evidence = item.evidence
            state = (
                self.text("measurement_not_applied")
                if item.reconciliation is None else self.text(
                    "measurement_accepted_state",
                    remaining=self.mass(item.reconciliation.accepted_remaining.milligrams),
                )
            )
            measurement_lines.append(self.text(
                "measurement_record_line", source=evidence.source.value,
                captured=evidence.captured_at.value.astimezone().strftime("%d.%m.%Y %H:%M"),
                gross=self.mass(None if evidence.gross is None else evidence.gross.milligrams),
                tare=self.mass(None if evidence.tare is None else evidence.tare.milligrams),
                net=self.mass(None if evidence.net is None else evidence.net.milligrams),
                ledger_cutoff=(
                    "—" if evidence.ledger_cutoff is None else str(evidence.ledger_cutoff)
                ),
                state=state,
            ))
        ledger_lines = []
        for record in records:
            estimated = record.source_type in {
                "THREE_MF", "GCODE", "SLICER", "PROGRESS_ESTIMATE",
            }
            line = (
                f"#{record.sequence}  {self.text(record.transaction_type.value)}"
                f"{(' · ' + self.text('calculated_consumption')) if estimated else ''}\n"
                f"{self.mass(record.delta.milligrams)} → {self.mass(record.new_effective.milligrams)} g\n"
                f"{record.created_at.value.astimezone().strftime('%d.%m.%Y %H:%M')}"
            )
            if estimated:
                details = []
                if record.print_job_id is not None:
                    details.append(self.text(
                        "calculated_job_detail", job_id=str(record.print_job_id),
                    ))
                if record.source_receipt_id is not None:
                    details.append(self.text(
                        "calculated_receipt_detail", receipt_id=str(record.source_receipt_id),
                    ))
                # Display only a small, validated provenance subset. Never render
                # arbitrary metadata_json or a path supplied by a persisted record.
                if record.source_type == "THREE_MF" and len(record.metadata_json) <= 4096:
                    try:
                        metadata = json.loads(record.metadata_json)
                    except (TypeError, ValueError):
                        metadata = None
                    if type(metadata) is dict:
                        digest = metadata.get("file_sha256")
                        plate = metadata.get("plate")
                        if (
                            metadata.get("quantity") == "estimate"
                            and metadata.get("label") == "Розрахункова витрата"
                            and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest)
                            and type(plate) is int and 1 <= plate <= 1_000_000
                        ):
                            details.append(self.text(
                                "calculated_file_plate_detail",
                                sha256=digest[:12], plate=plate,
                            ))
                if details:
                    line += "\n" + "\n".join(details)
            if record.unit_cost is not None and record.currency is not None:
                line += "\n" + self.text(
                    "cost_entry", amount=record.unit_cost.canonical(), currency=record.currency,
                )
            ledger_lines.append(line)
        cost_lines = []
        if cost.confirmed_prints:
            totals = ", ".join(
                f"{amount.canonical()} {currency}"
                for currency, amount in cost.totals_by_currency
            ) or self.text("cost_none_known")
            cost_lines.append(self.text(
                "cost_summary", totals=totals,
                unknown=cost.unknown_cost_prints,
                unknown_mass=self.mass(cost.unknown_cost_consumed.milligrams),
            ))
        self.history.setPlainText("\n\n".join(
            [*cost_lines, *measurement_lines, *ledger_lines]
        ) or self.text("history_empty"))

    def export_qr_label(self) -> None:
        selected = self.selected()
        if selected is None:
            return
        filename = f"ufm-spool-{selected.id}.svg"
        path, _ = QFileDialog.getSaveFileName(
            self, self.text("export_qr_label"), filename, "SVG (*.svg)",
        )
        if not path:
            return
        try:
            Path(path).write_bytes(self.selected_spool_label_svg(selected))
        except (OSError, ValueError):
            QMessageBox.warning(
                self, self.text("export_qr_label"), self.text("qr_label_export_failed"),
            )

    def print_qr_label(self) -> None:
        selected = self.selected()
        if selected is None:
            return
        self.print_qr_labels((selected,))

    def batch_print_qr_labels(self) -> None:
        selected_rows = self.select_spools_for_labels()
        if selected_rows:
            self.print_qr_labels(selected_rows)

    def batch_export_qr_labels(self) -> None:
        selected_rows = self.select_spools_for_labels()
        if not selected_rows:
            return
        directory = QFileDialog.getExistingDirectory(
            self, self.text("batch_export_qr_labels"), str(Path.home()),
        )
        if not directory:
            return
        output = Path(directory) / f"ufm-labels-{uuid4().hex[:8]}"
        try:
            output.mkdir()
            for row in selected_rows:
                (output / f"ufm-spool-{row.id}.svg").write_bytes(
                    self.selected_spool_label_svg(row)
                )
        except (OSError, ValueError):
            QMessageBox.warning(
                self, self.text("batch_export_qr_labels"),
                self.text("qr_label_batch_export_failed", path=str(output)),
            )
            return
        QMessageBox.information(
            self, self.text("batch_export_qr_labels"),
            self.text("qr_label_batch_export_done", count=len(selected_rows), path=str(output)),
        )

    def select_spools_for_labels(self) -> tuple[StudioSpool, ...]:
        if not self.rows:
            return ()
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("batch_labels_title"))
        dialog.resize(520, 480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.text("batch_labels_hint")))
        choices = QListWidget()
        for row in self.rows:
            item = QListWidgetItem(
                f"{row.name} · {row.profile} · {self.mass(row.remaining_mg)} г"
            )
            item.setData(Qt.ItemDataRole.UserRole, row.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            choices.addItem(item)
        layout.addWidget(choices, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.text("continue"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ()
        selected_ids = {
            choices.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(choices.count())
            if choices.item(index).checkState() == Qt.CheckState.Checked
        }
        return tuple(row for row in self.rows if row.id in selected_ids)

    def print_qr_labels(self, rows: tuple[StudioSpool, ...]) -> None:
        dimensions = self.label_dimensions()
        if dimensions is None:
            return
        width_mm, height_mm = dimensions
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            painter = QPainter()
            if not painter.begin(printer):
                raise OSError("qr.printer_unavailable")
            try:
                page = printer.pageLayout().paintRectPixels(printer.resolution())
                width = round(width_mm * printer.resolution() / 25.4)
                height = round(height_mm * printer.resolution() / 25.4)
                fit = min(1.0, page.width() / width, page.height() / height)
                width = round(width * fit)
                height = round(height * fit)
                for index, row in enumerate(rows):
                    if index and not printer.newPage():
                        raise OSError("qr.new_page_failed")
                    renderer = QSvgRenderer(QByteArray(self.selected_spool_label_svg(row)))
                    if not renderer.isValid():
                        raise ValueError("qr.renderer_invalid")
                    target = QRectF(
                        page.x() + (page.width() - width) / 2,
                        page.y() + (page.height() - height) / 2,
                        width,
                        height,
                    )
                    renderer.render(painter, target)
            finally:
                painter.end()
        except (OSError, ValueError, RuntimeError):
            QMessageBox.warning(
                self, self.text("print_qr_label"), self.text("qr_label_print_failed"),
            )

    def label_dimensions(self) -> tuple[float, float] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("label_size_dialog"))
        form = QFormLayout(dialog)
        width = QDoubleSpinBox()
        width.setRange(20, 300)
        width.setDecimals(1)
        width.setSuffix(" mm")
        width.setValue(80)
        height = QDoubleSpinBox()
        height.setRange(20, 300)
        height.setDecimals(1)
        height.setSuffix(" mm")
        height.setValue(45)
        form.addRow(self.text("label_width"), width)
        form.addRow(self.text("label_height"), height)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.text("continue"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return width.value(), height.value()

    def selected_spool_label_svg(self, selected: StudioSpool) -> bytes:
        material = " · ".join(
            value for value in (selected.brand, selected.profile, selected.material) if value
        ) or self.text("unknown")
        color_name = selected.color_name or selected.color_hex or self.text("unknown")
        return spool_label_card_svg(
            EntityId.parse(selected.id),
            name=selected.name or self.text("unknown"),
            material=material,
            color=selected.color_hex,
            color_label=f"{self.text('color')}: {color_name}",
            remaining_label=f"{self.text('remaining')}: {self.mass(selected.remaining_mg)} g",
        )

    def show_cost_report(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("cost_report"))
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        filters = QFormLayout()
        from_date = QDateEdit()
        from_date.setCalendarPopup(True)
        from_date.setDisplayFormat("yyyy-MM-dd")
        from_date.setDate(QDate.currentDate().addDays(-30))
        until_date = QDateEdit()
        until_date.setCalendarPopup(True)
        until_date.setDisplayFormat("yyyy-MM-dd")
        until_date.setDate(QDate.currentDate())
        printer_filter = QComboBox()
        printer_filter.addItem(self.text("all_printers"), "")
        for printer in self.backend.printers():
            printer_filter.addItem(printer.name, printer.id)
        filters.addRow(self.text("cost_from"), from_date)
        filters.addRow(self.text("cost_until"), until_date)
        filters.addRow(self.text("printer"), printer_filter)
        layout.addLayout(filters)
        preview = QTextEdit()
        preview.setReadOnly(True)
        layout.addWidget(preview, 1)
        actions = QHBoxLayout()
        load = QPushButton(self.text("cost_load"))
        export = QPushButton(self.text("cost_export"))
        export.setEnabled(False)
        close = QPushButton(self.text("close"))
        actions.addWidget(load)
        actions.addWidget(export)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        current_report = None

        def run_report() -> None:
            nonlocal current_report
            try:
                start_local = datetime.combine(
                    date.fromisoformat(from_date.date().toString("yyyy-MM-dd")), time.min,
                ).astimezone()
                end_local = datetime.combine(
                    date.fromisoformat(
                        until_date.date().addDays(1).toString("yyyy-MM-dd")
                    ), time.min,
                ).astimezone()
                current_report = self.backend.cost_report(
                    UtcDateTime(start_local), UtcDateTime(end_local),
                    printer_filter.currentData() or None,
                )
            except (ValueError, OSError, RuntimeError):
                current_report = None
                export.setEnabled(False)
                QMessageBox.warning(dialog, self.text("cost_report"), self.text("cost_report_failed"))
                return
            totals = ", ".join(
                f"{amount.canonical()} {currency}"
                for currency, amount in current_report.totals_by_currency
            ) or self.text("cost_none_known")
            lines = [self.text(
                "cost_report_summary", prints=current_report.print_count,
                mass=self.mass(current_report.consumed.milligrams), totals=totals,
                unknown=current_report.unknown_cost_prints,
                unknown_mass=self.mass(current_report.unknown_cost_consumed.milligrams),
            )]
            for item in current_report.entries:
                record = item.transaction
                cost = (
                    self.text("cost_entry", amount=record.unit_cost.canonical(), currency=record.currency)
                    if record.unit_cost is not None and record.currency is not None
                    else self.text("cost_unknown")
                )
                lines.append(
                    f"{item.print_started_at.value.astimezone().strftime('%Y-%m-%d %H:%M')} · "
                    f"{item.printer_name} · {item.job_name} · {item.spool_name} · "
                    f"{self.mass(-record.delta.milligrams)} г · {cost}"
                )
            preview.setPlainText("\n\n".join(lines))
            export.setEnabled(bool(current_report.entries))

        def export_report() -> None:
            if current_report is None:
                return
            path, _ = QFileDialog.getSaveFileName(
                dialog, self.text("cost_export"), "ufm-filament-report.csv", "CSV (*.csv)",
            )
            if not path:
                return
            try:
                Path(path).write_text(
                    _cost_report_csv(current_report, self.text, self.mass), encoding="utf-8",
                )
            except OSError:
                QMessageBox.warning(dialog, self.text("cost_export"), self.text("cost_export_failed"))

        load.clicked.connect(run_report)
        export.clicked.connect(export_report)
        close.clicked.connect(dialog.accept)
        run_report()
        dialog.exec()

    def edit_spool(self) -> None:
        row = self.selected()
        if row is None or row.lifecycle == "ARCHIVED":
            return
        name = QLineEdit(row.name)
        threshold = QLineEdit(
            "" if row.low_threshold_mg is None else self.mass(row.low_threshold_mg)
        )
        product_line = QLineEdit(row.product_line or "")
        batch_number = QLineEdit(row.batch_number or "")
        lot_number = QLineEdit(row.lot_number or "")
        brand = QComboBox()
        brand.addItem(self.text("no_brand"), None)
        for identity, label in self.backend.brands():
            brand.addItem(label, identity)
        if row.brand_id is not None and brand.findData(row.brand_id) < 0:
            brand.addItem(self.text("archived_brand_option", name=row.brand or row.brand_id), row.brand_id)
            cast(QStandardItemModel, brand.model()).item(brand.count() - 1).setEnabled(False)
        brand.setCurrentIndex(max(0, brand.findData(row.brand_id)))
        nominal = QLineEdit(
            "" if row.nominal_filament_mg is None else self.mass(row.nominal_filament_mg)
        )
        empty_spool = QLineEdit(
            "" if row.empty_spool_mg is None else self.mass(row.empty_spool_mg)
        )
        opened_date = QLineEdit(row.opened_date or "")
        manufactured_date = QLineEdit(row.manufactured_date or "")
        expires_date = QLineEdit(row.expires_date or "")
        purchase_price = QLineEdit(row.purchase_price or "")
        purchase_basis = QLineEdit(
            "" if row.purchase_basis_mg is None else self.mass(row.purchase_basis_mg)
        )
        currency = QLineEdit(row.currency or "")
        purchase_date = QLineEdit(row.purchase_date or "")
        color_name = QLineEdit(row.color_name or "")
        color_hex = QLineEdit(row.color_hex or "")
        secondary_color_hex = QLineEdit(row.secondary_color_hex or "")
        image_uri = QLineEdit(row.image_uri or "")
        notes = QLineEdit(row.notes or "")
        fields = [
            ("name", name), ("low_threshold", threshold),
            ("product_line", product_line), ("batch_number", batch_number),
            ("lot_number", lot_number), ("color", color_name),
            ("brand", brand), ("nominal_filament", nominal), ("empty_spool", empty_spool),
            ("opened_date", opened_date), ("manufactured_date", manufactured_date),
            ("expires_date", expires_date),
            ("purchase_price", purchase_price), ("purchase_basis", purchase_basis),
            ("currency", currency),
            ("purchase_date", purchase_date),
            ("color_hex", color_hex), ("secondary_color_hex", secondary_color_hex),
            ("image_uri", image_uri), ("notes", notes),
        ]
        if not self.form("edit_spool", fields):
            return
        self.work(
            lambda: self.backend.edit_spool(
                row, name.text(), threshold.text(), f"studio-edit-spool-{uuid4()}",
                brand_id=brand.currentData(), nominal_grams=nominal.text(),
                empty_spool_grams=empty_spool.text(),
                opened_date=opened_date.text().strip() or None,
                manufactured_date=manufactured_date.text().strip() or None,
                expires_date=expires_date.text().strip() or None,
                purchase_price=purchase_price.text().strip() or None,
                purchase_basis_grams=purchase_basis.text().strip() or None,
                currency=currency.text().strip() or None,
                purchase_date=purchase_date.text().strip() or None,
                product_line=product_line.text().strip() or None,
                batch_number=batch_number.text().strip() or None,
                lot_number=lot_number.text().strip() or None,
                color_name=color_name.text().strip() or None,
                color_hex=color_hex.text().strip() or None,
                secondary_color_hex=secondary_color_hex.text().strip() or None,
                image_uri=image_uri.text().strip() or None, notes=notes.text().strip() or None,
            ),
            lambda _: self.info(self.text("spool_saved")),
        )

    def record_measurement(self) -> None:
        row = self.selected()
        if row is None or row.lifecycle == "ARCHIVED":
            return
        gross = QLineEdit()
        tare = QLineEdit(
            "" if row.empty_spool_mg is None else self.mass(row.empty_spool_mg)
        )
        if not self.form("record_measurement", [
            ("gross_weight", gross), ("tare_weight", tare),
        ]):
            return

        def capture_and_confirm() -> None:
            evidence = self.backend.record_manual_measurement(
                row.id, gross.text(), tare.text(), f"studio-measurement-{uuid4()}",
            )
            if evidence.net is None:
                raise ValueError("inventory.measurement_net_missing")
            net_text = self.mass(evidence.net.milligrams)
            if row.remaining_mg is None:
                prompt = self.text("measurement_opening_prompt", net=net_text)
            else:
                delta = evidence.net.milligrams - row.remaining_mg
                prompt = self.text(
                    "measurement_confirm_prompt", net=net_text,
                    current=self.mass(row.remaining_mg), delta=self.mass(delta),
                )
            accepted = QMessageBox.question(
                self, self.text("measurement_confirm_title"), prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
            if not accepted:
                self.info(self.text("measurement_saved", net=net_text))
                return
            self.backend.accept_manual_measurement(
                row, evidence.id, self.text("manual_measurement_reason"),
                f"studio-measurement-accept-{uuid4()}",
            )
            self.info(self.text("measurement_applied"))

        self.protect(capture_and_confirm)

    def archive_spool(self) -> None:
        row = self.selected()
        if row is None or row.lifecycle == "ARCHIVED":
            return
        answer = QMessageBox.question(
            self, self.text("archive_spool"), self.text("archive_confirm", name=row.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.work(
            lambda: self.backend.archive_spool(row, f"studio-archive-spool-{uuid4()}"),
            lambda _: self.info(self.text("spool_archived")),
        )

    def rebuild_projection(self) -> None:
        row = self.selected()
        if row is None or row.lifecycle == "ARCHIVED":
            return
        answer = QMessageBox.question(
            self, self.text("rebuild_projection"), self.text("rebuild_projection_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.work(
            lambda: self.backend.rebuild_projection(row, f"studio-rebuild-projection-{uuid4()}"),
            lambda _: self.info(self.text("rebuild_projection_done")),
        )

    def add_storage_location(self) -> None:
        name, accepted = QInputDialog.getText(
            self, self.text("new_location"), self.text("location_name"),
        )
        if not accepted:
            return
        if not name.strip():
            self.error("storage.name_invalid")
            return
        types = ("ROOM", "CABINET", "SHELF", "DRY_BOX", "BIN", "OTHER")
        storage_type, accepted = QInputDialog.getItem(
            self, self.text("new_location"), self.text("location_type"),
            list(types), 0, False,
        )
        if not accepted:
            return
        self.work(
            lambda: self.backend.create_storage_location(
                name, storage_type, f"studio-create-location-{uuid4()}"),
            lambda _: self.info(self.text("location_created")),
        )

    def assign_storage_location(self) -> None:
        row = self.selected()
        if row is None or row.lifecycle == "ARCHIVED":
            return
        locations = self.backend.storage_locations()
        choices = [self.text("no_location")] + [
            f"{location.name} · {location.storage_type} · {location.id[:8]}"
            for location in locations
        ]
        current = 0
        if row.location_id is not None:
            current = next((
                index + 1 for index, location in enumerate(locations)
                if location.id == row.location_id
            ), 0)
        choice, accepted = QInputDialog.getItem(
            self, self.text("assign_location"), self.text("location_select"),
            choices, current, False,
        )
        if not accepted or choice not in choices:
            return
        index = choices.index(choice)
        location_id = None if index == 0 else locations[index - 1].id
        if location_id == row.location_id:
            return
        self.work(
            lambda: self.backend.assign_storage_location(
                row, location_id, f"studio-assign-location-{uuid4()}"),
            lambda _: self.info(self.text("location_assigned")),
        )

    def compensate_transaction(self) -> None:
        row = self.selected()
        if row is None or row.lifecycle == "ARCHIVED":
            return
        records = self.backend.history(row.id)
        compensated = {
            str(record.compensates_transaction_id)
            for record in records if record.compensates_transaction_id is not None
        }
        eligible = tuple(
            record for record in records
            if record.delta.milligrams != 0
            and record.compensates_transaction_id is None
            and str(record.id) not in compensated
        )
        if not eligible:
            return
        choices = [
            self.text("compensate_choice", sequence=record.sequence,
                      kind=self.text(record.transaction_type.value),
                      amount=self.mass(record.delta.milligrams))
            for record in eligible
        ]
        choice, accepted = QInputDialog.getItem(
            self, self.text("compensate"), self.text("compensate_select"), choices, 0, False,
        )
        if not accepted or choice not in choices:
            return
        record = eligible[choices.index(choice)]
        answer = QMessageBox.question(
            self, self.text("compensate"), self.text("compensate_confirm", sequence=record.sequence,
                                                        amount=self.mass(record.delta.milligrams)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.work(
            lambda: self.backend.compensate(str(record.id), f"studio-compensate-{uuid4()}"),
            lambda _: self.info(self.text("compensate_done")),
        )

    def info(self, text: str) -> None:
        QMessageBox.information(self, self.text("title"), text)

    def error(self, code: str) -> None:
        QMessageBox.warning(self, self.text("error"), self.text("error_hint", code=code))

    def protect(self, operation: Callable[[], object]) -> None:
        try:
            operation()
        except Exception as error:
            self.error(type(error).__name__)
        self.refresh()

    def _log(self, event: str, **fields: object) -> None:
        self.container.logger.info(event, extra={"fields": fields})

    def work(
        self,
        operation: Callable[[], object],
        callback: Callable[[object], None],
        *,
        after_finished: Callable[[], None] | None = None,
        after_failed: Callable[[str], None] | None = None,
    ) -> None:
        if self.tasks or self._monitor_task is not None:
            return
        self.pages.setEnabled(False)
        self.statusBar().showMessage(self.text("busy"))
        task = Task(operation, self)
        self.tasks.append(task)
        task.completed.connect(callback)

        def failed(code: str) -> None:
            self._log("task_failed", error_code=code)
            self.error(code)
            if after_failed is not None:
                after_failed(code)

        task.failed.connect(failed)
        task.finished.connect(lambda: self.finish_task(task, after_finished))
        task.start()

    def finish_task(
        self, task: Task, after_finished: Callable[[], None] | None = None,
    ) -> None:
        self.tasks.remove(task)
        task.deleteLater()
        self.pages.setEnabled(True)
        self.refresh()
        self.close_when_idle()
        if after_finished is not None and self.isVisible():
            after_finished()

    def stock(self, mode: str) -> None:
        row = self.selected()
        if row is None:
            return
        amount, accepted = QInputDialog.getText(self, self.text(mode), self.text("grams"))
        if accepted:
            self.protect(lambda: self.backend.change_stock(
                row.id, mode, amount, f"studio-{uuid4()}",
            ))

    def form(self, title: str, fields: list[tuple[str, QWidget]]) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text(title))
        dialog.resize(620, 620)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QFormLayout(content)
        for key, widget in fields:
            layout.addRow(self.text(key), widget)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        validation = QLabel()
        validation.setWordWrap(True)
        validation.hide()
        outer.addWidget(validation)
        buttons = QDialogButtonBox()
        buttons.addButton(self.text("save"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.text("cancel"), QDialogButtonBox.ButtonRole.RejectRole)

        def accept_form() -> None:
            for key, widget in fields:
                if not isinstance(widget, QLineEdit):
                    continue
                value = widget.text()
                if widget.property("ufm_required") and not value.strip():
                    validation.setText(self.text("form_required", field=self.text(key)))
                    validation.show()
                    widget.setFocus()
                    return
                validator = widget.validator()
                if value and validator is not None and not widget.hasAcceptableInput():
                    validation.setText(self.text("form_invalid_value", field=self.text(key)))
                    validation.show()
                    widget.setFocus()
                    return
            dialog.accept()

        buttons.accepted.connect(accept_form)
        buttons.rejected.connect(dialog.reject)
        outer.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def numeric_field(
        value: str, minimum: float, maximum: float, decimals: int = 6,
    ) -> QLineEdit:
        field = QLineEdit(value)
        validator = QDoubleValidator(minimum, maximum, decimals, field)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setLocale(QLocale.c())
        field.setValidator(validator)
        return field

    def material_fields(self, profile: StudioMaterial | None = None) -> dict[str, QWidget]:
        name_field = QLineEdit("" if profile is None else profile.name)
        name_field.setMaxLength(200)
        name_field.setProperty("ufm_required", True)
        diameter = self.numeric_field(
            "1.75" if profile is None else profile.diameter_mm, 0.000001, 5,
        )
        diameter.setProperty("ufm_required", True)
        values: dict[str, QWidget] = {
            "name": name_field,
            "material": QComboBox(),
            "diameter": diameter,
            "brand": QComboBox(),
            "product_line": QLineEdit("" if profile is None else profile.product_line or ""),
            "density": self.numeric_field(
                "" if profile is None else profile.density_g_cm3 or "", 0.000001, 100,
            ),
            "custom_material_name": QLineEdit(
                "" if profile is None else profile.custom_material_name or ""
            ),
        }
        for key in ("product_line", "custom_material_name"):
            cast(QLineEdit, values[key]).setMaxLength(200)
        for key in (
            "subtype", "nozzle_min_c", "nozzle_max_c", "bed_min_c", "bed_max_c",
            "chamber_min_c", "chamber_max_c", "max_volumetric_speed_mm3_s",
            "drying_temp_c", "drying_duration_min", "default_color_name", "notes",
        ):
            value = "" if profile is None else (getattr(profile, key) or "")
            if key == "drying_duration_min":
                field = QLineEdit(str(value))
                field.setValidator(QIntValidator(0, 100000, field))
            elif key in {"density", "nozzle_min_c", "nozzle_max_c", "bed_min_c",
                         "bed_max_c", "chamber_min_c", "chamber_max_c",
                         "max_volumetric_speed_mm3_s", "drying_temp_c"}:
                minimum = 0.000001 if key in {"density", "max_volumetric_speed_mm3_s"} else 0
                maximum = 100 if key == "density" else 10000 if key == "max_volumetric_speed_mm3_s" else 2000
                field = self.numeric_field(str(value), minimum, maximum)
            else:
                field = QLineEdit(str(value))
            field.setMaxLength(4000 if key == "notes" else 200)
            values[key] = field
        material = cast(QComboBox, values["material"])
        material.addItems([item.value for item in MaterialType])
        if profile is not None:
            material.setCurrentText(profile.material)
        brand = cast(QComboBox, values["brand"])
        brand.addItem(self.text("no_brand"), "")
        for brand_id, name in self.backend.brands():
            brand.addItem(name, brand_id)
        if profile is not None and profile.brand_id is not None:
            if brand.findData(profile.brand_id) < 0:
                brand.addItem(
                    self.text("archived_brand_option", name=profile.brand or profile.brand_id),
                    profile.brand_id,
                )
                cast(QStandardItemModel, brand.model()).item(
                    brand.count() - 1
                ).setEnabled(False)
            brand.setCurrentIndex(brand.findData(profile.brand_id))
        for key in ("abrasive", "flexible", "hygroscopic", "soluble", "filled_material"):
            check = QCheckBox()
            if profile is not None:
                check.setChecked(bool(getattr(profile, key)))
            values[key] = check
        return values

    def material_form_fields(self, values: dict[str, QWidget]) -> list[tuple[str, QWidget]]:
        return [(key, values[key]) for key in (
            "name", "material", "diameter", "brand", "product_line", "density",
            "custom_material_name", "abrasive", "flexible", "hygroscopic", "soluble",
            "filled_material", "subtype", "nozzle_min_c", "nozzle_max_c", "bed_min_c",
            "bed_max_c", "chamber_min_c", "chamber_max_c", "max_volumetric_speed_mm3_s",
            "drying_temp_c", "drying_duration_min", "default_color_name", "notes",
        )]

    def material_values(self, values: dict[str, QWidget]) -> MaterialFormValues:
        brand = cast(QComboBox, values["brand"])
        return {
            "name": cast(QLineEdit, values["name"]).text(),
            "material": cast(QComboBox, values["material"]).currentText(),
            "diameter": cast(QLineEdit, values["diameter"]).text(),
            "brand_id": str(brand.currentData()) or None,
            "product_line": cast(QLineEdit, values["product_line"]).text() or None,
            "density": cast(QLineEdit, values["density"]).text() or None,
            "custom_material_name": (
                cast(QLineEdit, values["custom_material_name"]).text() or None
            ),
            "abrasive": cast(QCheckBox, values["abrasive"]).isChecked(),
            "flexible": cast(QCheckBox, values["flexible"]).isChecked(),
            "hygroscopic": cast(QCheckBox, values["hygroscopic"]).isChecked(),
            "soluble": cast(QCheckBox, values["soluble"]).isChecked(),
            "filled_material": cast(QCheckBox, values["filled_material"]).isChecked(),
            "subtype": cast(QLineEdit, values["subtype"]).text().strip() or None,
            "nozzle_min_c": cast(QLineEdit, values["nozzle_min_c"]).text().strip() or None,
            "nozzle_max_c": cast(QLineEdit, values["nozzle_max_c"]).text().strip() or None,
            "bed_min_c": cast(QLineEdit, values["bed_min_c"]).text().strip() or None,
            "bed_max_c": cast(QLineEdit, values["bed_max_c"]).text().strip() or None,
            "chamber_min_c": cast(QLineEdit, values["chamber_min_c"]).text().strip() or None,
            "chamber_max_c": cast(QLineEdit, values["chamber_max_c"]).text().strip() or None,
            "max_volumetric_speed_mm3_s": cast(
                QLineEdit, values["max_volumetric_speed_mm3_s"],
            ).text().strip() or None,
            "drying_temp_c": cast(QLineEdit, values["drying_temp_c"]).text().strip() or None,
            "drying_duration_min": cast(
                QLineEdit, values["drying_duration_min"],
            ).text().strip() or None,
            "default_color_name": cast(
                QLineEdit, values["default_color_name"],
            ).text().strip() or None,
            "notes": cast(QLineEdit, values["notes"]).text().strip() or None,
        }

    def add_material(self) -> None:
        values = self.material_fields()
        if self.form("new_material", self.material_form_fields(values)):
            self.protect(lambda: self.backend.add_material(**self.material_values(values)))

    def add_brand(self) -> None:
        name = QLineEdit()
        name.setMaxLength(200)
        name.setProperty("ufm_required", True)
        if self.form("new_brand", [("name", name)]):
            self.protect(lambda: self.backend.add_brand(
                name.text(), f"studio-brand-{uuid4()}",
            ))

    def update_material_actions(self) -> None:
        self.edit_material_button.setEnabled(self.material_table.currentRow() >= 0)

    def selected_brand(self) -> StudioBrand | None:
        row = self.brand_table.currentRow()
        item = None if row < 0 else self.brand_table.item(row, 0)
        if item is None:
            return None
        identity = str(item.data(Qt.ItemDataRole.UserRole))
        return next((entry for entry in self.brand_rows if entry.id == identity), None)

    def update_brand_actions(self) -> None:
        available = self.selected_brand() is not None and not self.tasks
        self.edit_brand_button.setEnabled(bool(available))
        self.archive_brand_button.setEnabled(bool(available))

    def edit_brand(self) -> None:
        row = self.selected_brand()
        if row is None:
            return
        name = QLineEdit(row.name)
        name.setMaxLength(200)
        name.setProperty("ufm_required", True)
        if not self.form("edit_brand", [("name", name)]):
            return
        answer = QMessageBox.question(
            self, self.text("edit_brand"), self.text("brand_edit_scope"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.work(
            lambda: self.backend.edit_brand(row, name.text(), f"studio-edit-brand-{uuid4()}"),
            lambda _: self.info(self.text("brand_saved")),
        )

    def archive_brand(self) -> None:
        row = self.selected_brand()
        if row is None:
            return
        answer = QMessageBox.question(
            self, self.text("archive_brand"), self.text("brand_archive_confirm", name=row.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.work(
            lambda: self.backend.archive_brand(row, f"studio-archive-brand-{uuid4()}"),
            lambda _: self.info(self.text("brand_archived")),
        )

    def edit_material(self) -> None:
        item = self.material_table.item(self.material_table.currentRow(), 0)
        if item is None:
            return
        profile_id = str(item.data(Qt.ItemDataRole.UserRole))
        profile = next((entry for entry in self.profiles if entry.id == profile_id), None)
        if profile is None:
            return
        values = self.material_fields(profile)
        if not self.form("edit_material", self.material_form_fields(values)):
            return
        answer = QMessageBox.question(
            self, self.text("edit_material"), self.text("profile_edit_scope"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.work(
            lambda: self.backend.edit_material(
                profile_id, **self.material_values(values),
                command_key=f"studio-edit-profile-{uuid4()}",
            ),
            lambda _: self.info(self.text("profile_saved")),
        )

    def add_spool(self) -> None:
        if not self.profiles:
            self.info(self.text("no_profiles"))
            return
        name, profile, brand = QLineEdit(), QComboBox(), QComboBox()
        name.setMaxLength(200)
        name.setProperty("ufm_required", True)
        for entry in self.profiles:
            profile.addItem(f"{entry.name} · {entry.material}", entry.id)
        brand.addItem(self.text("no_brand"), None)
        active_brands = self.backend.brands()
        for brand_id, label in active_brands:
            brand.addItem(label, brand_id)
        initial_profile = self.profiles[0]
        if initial_profile.brand_id is not None:
            brand.setCurrentIndex(max(0, brand.findData(initial_profile.brand_id)))
        product_line = QLineEdit(initial_profile.product_line or "")
        batch_number, lot_number = QLineEdit(), QLineEdit()
        nominal, empty_spool = QLineEdit(), QLineEdit()
        opened_date, manufactured_date, expires_date = QLineEdit(), QLineEdit(), QLineEdit()
        purchase_price, purchase_basis, currency, purchase_date = (
            QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(),
        )
        color_name = QLineEdit(initial_profile.default_color_name or "")
        color_hex, secondary_color_hex = QLineEdit(), QLineEdit()
        image_uri, notes = QLineEdit(), QLineEdit()
        notes.setMaxLength(4000)

        def apply_profile_defaults(index: int) -> None:
            selected_id = profile.itemData(index)
            selected_profile = next((p for p in self.profiles if p.id == selected_id), None)
            if selected_profile is None:
                return
            product_line.setText(selected_profile.product_line or "")
            color_name.setText(selected_profile.default_color_name or "")
            brand_index = brand.findData(selected_profile.brand_id)
            brand.setCurrentIndex(max(0, brand_index))

        profile.currentIndexChanged.connect(apply_profile_defaults)
        apply_profile_defaults(profile.currentIndex())
        fields = [
            ("name", name), ("profile", profile), ("brand", brand),
            ("product_line", product_line), ("batch_number", batch_number),
            ("lot_number", lot_number), ("nominal_filament", nominal),
            ("empty_spool", empty_spool), ("color", color_name),
            ("opened_date", opened_date), ("manufactured_date", manufactured_date),
            ("expires_date", expires_date),
            ("purchase_price", purchase_price), ("purchase_basis", purchase_basis),
            ("currency", currency),
            ("purchase_date", purchase_date),
            ("color_hex", color_hex), ("secondary_color_hex", secondary_color_hex),
            ("image_uri", image_uri), ("notes", notes),
        ]
        if self.form("new_spool", fields):
            self.protect(lambda: self.backend.add_spool(
                name.text(), str(profile.currentData()),
                brand_id=None if brand.currentData() is None else str(brand.currentData()),
                product_line=product_line.text(), batch_number=batch_number.text(),
                lot_number=lot_number.text(), nominal_grams=nominal.text(),
                empty_spool_grams=empty_spool.text(), color_name=color_name.text(),
                opened_date=opened_date.text().strip() or None,
                manufactured_date=manufactured_date.text().strip() or None,
                expires_date=expires_date.text().strip() or None,
                purchase_price=purchase_price.text().strip() or None,
                purchase_basis_grams=purchase_basis.text().strip() or None,
                currency=currency.text().strip() or None,
                purchase_date=purchase_date.text().strip() or None,
                color_hex=color_hex.text(), secondary_color_hex=secondary_color_hex.text(),
                image_uri=image_uri.text(), notes=notes.text(),
            ))

    def backup(self) -> None:
        self.work(self.backend.backup, lambda result: self.info(str(result)))

    def export_inventory(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, self.text("export_inventory"), "ufm-inventory.csv", "CSV (*.csv)",
        )
        if not filename:
            return
        target = Path(filename)

        def export() -> str:
            content = _inventory_csv(self.backend.spools()).encode("utf-8")
            output = QSaveFile(str(target))
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError("inventory.export_open_failed")
            if output.write(content) != len(content) or not output.commit():
                output.cancelWriting()
                raise OSError("inventory.export_commit_failed")
            return str(target)

        self.work(
            export,
            lambda result: self.info(
                self.text("inventory_exported", path=str(result)),
            ),
        )

    def import_database(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, self.text("import"))
        if not filename:
            return
        path = Path(filename)

        def confirm(result: object) -> None:
            preview = cast(SpoolmanImportPreview, result)
            new_source_label = self.text("import_source_new")
            source_labels = [new_source_label]
            source_keys: dict[str, str] = {}
            for source in preview.source_instances:
                label = spoolman_import_source_label(
                    source, unverified_label=self.text("import_source_unverified"),
                    recovery_label=(
                        self.strings["import_source_recovery_counts"][self.language]
                    ),
                )
                source_labels.append(label)
                source_keys[label] = source.source_instance_key
            default_source_key = default_spoolman_import_source_key(
                preview.source_instances, preview.suggested_source_instance_key,
            )
            selected_default = next((
                index for index, label in enumerate(source_labels)
                if source_keys.get(label) == default_source_key
            ), 0)
            selected_label, accepted = QInputDialog.getItem(
                self, self.text("import_source_title"),
                self.text("import_source_prompt"), source_labels,
                selected_default, False,
            )
            if not accepted:
                return
            source_instance_key = source_keys.get(selected_label) or new_spoolman_source_key()
            message = self.text("import_confirm", spools=preview.spool_count,
                                source_instance_key=source_instance_key,
                                profiles=preview.filament_count,
                                known=preview.known_stock_count,
                                unknown=preview.unknown_stock_count,
                                prices=preview.purchase_price_count,
                                prices_unknown=preview.purchase_price_not_imported_count,
                                lots=preview.lot_number_count, colors=preview.color_count,
                                locations=preview.location_count,
                                metadata_unknown=preview.unsupported_metadata_count)

            def show_detail(target: object) -> None:
                target_preview = cast(SpoolmanTargetPreview, target)
                target_by_id = {row.spool_id: row for row in target_preview.rows}
                detail = QDialog(self)
                detail.setWindowTitle(self.text("import_preview_title"))
                detail.resize(1050, 560)
                detail_layout = QVBoxLayout(detail)
                summary = QLabel(message)
                summary.setWordWrap(True)
                detail_layout.addWidget(summary)
                target_summary = QLabel(self.text(
                    "import_target_summary",
                    new=target_preview.new_count,
                    consistent=target_preview.consistent_count,
                    preserved=target_preview.preserved_count,
                    conflict=target_preview.conflict_count,
                ))
                target_summary.setWordWrap(True)
                detail_layout.addWidget(target_summary)
                table = QTableWidget(detail)
                headers = [
                    self.text("import_col_spool"), self.text("import_col_filament"),
                    self.text("import_col_material"), self.text("import_col_vendor"),
                    self.text("import_col_nominal"), self.text("import_col_tare"),
                    self.text("import_col_remaining"), self.text("import_col_price"),
                    self.text("import_col_state"), self.text("import_col_metadata"),
                    self.text("import_col_omitted"), self.text("import_col_target"),
                    self.text("import_col_conflicts"),
                    self.text("import_col_preserved"),
                ]
                table.setColumnCount(len(headers))
                table.setHorizontalHeaderLabels(headers)
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
                table.setAlternatingRowColors(True)
                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                table.horizontalHeader().setStretchLastSection(True)
                page_size = 200
                page_count = max(1, (len(preview.spools) + page_size - 1) // page_size)
                page_index = 0
                page_label = QLabel(detail)
                previous_page = QPushButton(self.text("import_page_previous"), detail)
                next_page = QPushButton(self.text("import_page_next"), detail)

                def mass_text(milligrams: int | None) -> str:
                    if milligrams is None:
                        return self.text("unknown")
                    return f"{milligrams // 1000}.{milligrams % 1000:03d} г"

                omitted_labels = {
                    "lot_nr": "import_omitted_lot", "color_hex": "import_omitted_color",
                    "location": "import_omitted_location", "price": "import_omitted_price",
                }

                def render_page() -> None:
                    nonlocal page_index
                    page_index = min(max(page_index, 0), page_count - 1)
                    start = page_index * page_size
                    page_rows = preview.spools[start:start + page_size]
                    table.setRowCount(len(page_rows))
                    for row_index, spool_preview in enumerate(page_rows):
                        price = self.text("unknown")
                        if spool_preview.purchase_price is not None:
                            price = (
                                f"{spool_preview.purchase_price} {spool_preview.currency} · "
                                f"{mass_text(spool_preview.purchase_basis_mg)}"
                            )
                        metadata = " · ".join(filter(None, (
                            spool_preview.lot_number, spool_preview.color_hex,
                            spool_preview.location,
                        ))) or self.text("none")
                        target_row = target_by_id.get(spool_preview.spool_id)
                        if target_row is None:
                            target_values = (
                                self.text("unknown"), self.text("none"),
                                self.text("none"),
                            )
                        else:
                            target_values = (
                                self.text(f"import_target_{target_row.state}"),
                                ", ".join(
                                    self.text(f"import_difffield_{name}")
                                    for name in target_row.conflict_fields
                                ) or self.text("none"),
                                ", ".join(
                                    self.text(f"import_difffield_{name}")
                                    for name in target_row.preserved_fields
                                ) or self.text("none"),
                            )
                        values = (
                            str(spool_preview.spool_id), spool_preview.name,
                            spool_preview.material, spool_preview.vendor or self.text("unknown"),
                            mass_text(spool_preview.nominal_mg),
                            mass_text(spool_preview.empty_spool_mg),
                            mass_text(spool_preview.remaining_mg), price,
                            self.text("import_state_archived") if spool_preview.archived else
                                self.text("import_state_active"),
                            metadata,
                            ", ".join(self.text(omitted_labels[key])
                                       for key in spool_preview.omitted_fields) or self.text("none"),
                            *target_values,
                        )
                        for column, value in enumerate(values):
                            table.setItem(row_index, column, QTableWidgetItem(value))
                    page_label.setText(self.text(
                        "import_page_status", page=page_index + 1, pages=page_count,
                        start=0 if not preview.spools else start + 1,
                        end=min(start + len(page_rows), len(preview.spools)),
                        total=len(preview.spools),
                    ))
                    previous_page.setEnabled(page_index > 0)
                    next_page.setEnabled(page_index + 1 < page_count)

                def change_page(offset: int) -> None:
                    nonlocal page_index
                    page_index += offset
                    render_page()

                previous_page.clicked.connect(lambda: change_page(-1))
                next_page.clicked.connect(lambda: change_page(1))
                page_controls = QHBoxLayout()
                page_controls.addWidget(previous_page)
                page_controls.addWidget(page_label)
                page_controls.addWidget(next_page)
                page_controls.addStretch()
                detail_layout.addLayout(page_controls)
                render_page()
                detail_layout.addWidget(table)
                buttons = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                    parent=detail,
                )
                buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.text("import"))
                buttons.accepted.connect(detail.accept)
                buttons.rejected.connect(detail.reject)
                detail_layout.addWidget(buttons)
                if detail.exec() == QDialog.DialogCode.Accepted:
                    # Run after QThread.finished has restored the workspace.
                    QTimer.singleShot(0, lambda: self.work(
                        lambda: import_spoolman_database(path, self.backend.paths,
                                                        engine=self.backend.engine,
                                                        source_instance_key=source_instance_key,
                                                        expected_source_fingerprint=preview.source_fingerprint),
                        completed,
                    ))

            # The completed callback still owns its finished task; defer the
            # read-only target comparison until the workspace is restored.
            QTimer.singleShot(0, lambda: self.work(
                lambda: preview_spoolman_target_state(
                    path, engine=self.backend.engine,
                    source_instance_key=source_instance_key,
                ),
                show_detail,
            ))

        def completed(result: object) -> None:
            imported = cast(SpoolmanImportResult, result)
            self.info(self.text("import_done", count=imported.processed_count,
                                source_instance_key=imported.source_instance_key,
                                mapping_report=str(imported.mapping_report),
                                path=str(imported.source_backup)))

        self.work(lambda: preview_spoolman_database(
            path, engine=self.backend.engine,
        ), confirm)

    def preview_haspelsync_config(self) -> None:
        """Preview selected HaspelSync files without applying their settings."""
        selected: list[Path] = []
        for key in (
            "haspel_select_printers", "haspel_select_mappings", "haspel_select_id_map",
        ):
            filename, _ = QFileDialog.getOpenFileName(
                self, self.text(key), "", "JSON (*.json)",
            )
            if not filename:
                return
            selected.append(Path(filename))

        def display(result: object) -> None:
            preview = cast(HaspelSyncImportPreview, result)
            configured = {
                printer.serial_number.strip().upper(): printer
                for printer in self.printers if printer.serial_number.strip()
            }
            printer_lines: list[str] = []
            for item in preview.printers:
                target = configured.get(item.serial_number.upper())
                if target is None:
                    printer_lines.append(self.text(
                        "haspel_unmatched_printer",
                        source=item.display_name, serial=item.serial_number,
                    ))
                else:
                    printer_lines.append(self.text(
                        "haspel_matched_printer",
                        source=item.display_name, serial=item.serial_number,
                        target=target.name,
                    ))
            if not printer_lines:
                printer_lines.append(self.text("haspel_no_printers"))
            all_mapping_lines = [
                f"{item.printer_serial} · {item.source_slot_label} → "
                f"{item.provider_system_key or self.text('haspel_unsupported')} / "
                f"{item.provider_slot_key or self.text('haspel_unsupported')} → "
                f"{item.ufm_spool_id or self.text('haspel_unresolved')}"
                for item in preview.mappings
            ]
            mapping_lines = all_mapping_lines[:100] or [self.text("haspel_no_mappings")]
            omitted = max(0, len(all_mapping_lines) - len(mapping_lines))
            summary = self.text(
                "haspel_import_summary",
                printers="\n".join(printer_lines),
                mappings="\n".join(mapping_lines),
                unresolved=preview.unresolved_spool_count,
                unsupported=preview.unsupported_slot_count,
                orphan=preview.orphan_printer_count,
                duplicates=preview.duplicate_target_spool_count,
                omitted=omitted,
            )
            dialog = QMessageBox(
                QMessageBox.Icon.Information, self.text("haspel_import_preview"),
                summary, QMessageBox.StandardButton.Ok, self,
            )
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.exec()

        self.work(lambda: preview_haspelsync_files(*selected), display)

    def switch_page(self, row: int) -> None:
        self.pages.setCurrentIndex(row)
        if row == 1:
            self.discover()

    def update_candidate_actions(self, row: int) -> None:
        self.connect_candidate_button.setEnabled(
            0 <= row < len(self._candidates)
        )

    def connect_candidate(self) -> None:
        row = self.candidate_list.currentRow()
        if not 0 <= row < len(self._candidates):
            return
        candidate = self._candidates[row]
        if candidate.provider_type == "BAMBU_LAN":
            self.enroll_bambu_network(candidate)
        else:
            self.enroll_local(candidate)

    def show_print_jobs(self) -> None:
        try:
            jobs = self.backend.recent_jobs()
        except Exception as error:
            self.error(type(error).__name__)
            return
        if not jobs:
            self.info(self.text("jobs_empty"))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("print_jobs_title"))
        dialog.setMinimumSize(880, 520)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(jobs), 6)
        table.setHorizontalHeaderLabels([
            self.text("job_col_job"), self.text("job_col_file"),
            self.text("job_col_plate"), self.text("job_col_printer"),
            self.text("job_col_status"), self.text("job_col_started"),
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row_index, job in enumerate(jobs):
            values = [
                job.name or job.file_name or job.id,
                job.file_name or "—",
                job.plate_name or "—",
                job.printer_name,
                f"{self.text(job.status)} / {self.text(job.finalization_state)}",
                job.started_at or job.detected_at or "—",
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(value))
        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setMinimumHeight(160)

        def show_detail() -> None:
            row = table.currentRow()
            if not 0 <= row < len(jobs):
                return
            try:
                info = self.backend.job_detail(jobs[row].id)
            except Exception as error:
                self.error(type(error).__name__)
                return
            detail.setPlainText(
                self.text("job_missing") if info is None
                else self._job_detail_text(info)
            )

        table.itemSelectionChanged.connect(show_detail)
        layout.addWidget(table, 3)
        layout.addWidget(detail, 2)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        table.selectRow(0)
        dialog.exec()

    def show_reconciliation_tasks(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("recon_tasks_title"))
        dialog.setMinimumSize(960, 480)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels([
            self.text("recon_col_reason"), self.text("recon_col_severity"),
            self.text("recon_col_state"), self.text("recon_col_spool"),
            self.text("recon_col_job"), self.text("recon_col_action"),
            self.text("recon_col_created"),
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        actions_row = QHBoxLayout()
        resolve_button = QPushButton(self.text("recon_resolve"))
        dismiss_button = QPushButton(self.text("recon_dismiss"))
        actions_row.addWidget(resolve_button)
        actions_row.addWidget(dismiss_button)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        tasks: list[StudioReconciliationTask] = []

        def reload() -> None:
            nonlocal tasks
            try:
                tasks = list(self.backend.open_reconciliation_tasks())
            except Exception as error:
                self.error(type(error).__name__)
                tasks = []
            table.setRowCount(len(tasks))
            for row_index, task in enumerate(tasks):
                values = [
                    task.reason_code,
                    self.text(task.severity),
                    self.text(task.state),
                    task.spool_name or "—",
                    task.job_name or "—",
                    task.suggested_action or "—",
                    task.created_at or "—",
                ]
                for column, value in enumerate(values):
                    table.setItem(row_index, column, QTableWidgetItem(value))
            resolve_button.setEnabled(bool(tasks))
            dismiss_button.setEnabled(bool(tasks))

        def resolve(outcome: str) -> None:
            row = table.currentRow()
            if not 0 <= row < len(tasks):
                return
            notes, accepted = QInputDialog.getMultiLineText(
                dialog, self.text("recon_note_title"),
                self.text("recon_note_prompt"),
            )
            if not accepted:
                return
            try:
                self.backend.resolve_reconciliation_task(
                    tasks[row].id, outcome, notes,
                )
            except Exception as error:
                self.error(type(error).__name__)
                return
            reload()

        resolve_button.clicked.connect(lambda: resolve("resolved"))
        dismiss_button.clicked.connect(lambda: resolve("dismissed"))
        table.itemSelectionChanged.connect(
            lambda: resolve_button.setEnabled(table.currentRow() >= 0)
        )
        reload()
        if not tasks:
            dialog.accept()
            self.info(self.text("recon_tasks_empty"))
            return
        dialog.exec()

    @staticmethod
    def _dash(value: object) -> str:
        return "—" if value is None else str(value)

    def _job_detail_text(self, info: StudioJobDetail) -> str:
        progress = (
            "—" if info.progress_bp is None else f"{info.progress_bp / 100:g}%"
        )
        layer = "—" if info.current_layer is None else str(info.current_layer)
        total = "—" if info.total_layers is None else str(info.total_layers)
        sections = [self.text(
            "job_detail_header",
            name=self._dash(info.name or info.file_name or info.id),
            file=self._dash(info.file_name), plate=self._dash(info.plate_name),
            printer=info.printer_name,
            status=self.text(info.status),
            finalization=self.text(info.finalization_state),
            source=info.source_type, slicer=self._dash(info.slicer_type),
            progress=progress, layer=layer, total=total,
            detected=self._dash(info.detected_at), started=self._dash(info.started_at),
            completed=self._dash(info.completed_at),
        )]
        if info.materials:
            lines = [self.text("job_section_materials")]
            for material in info.materials:
                lines.append(self.text(
                    "job_material_line", channel=material.channel_key,
                    tool=material.tool_index,
                    filament=self._dash(material.filament_name),
                    mass=(
                        "—" if material.estimated_mass_mg is None
                        else f"{material.estimated_mass_mg / 1000:g} g"
                    ),
                ))
            sections.append("\n".join(lines))
        if info.segments:
            lines = [self.text("job_section_segments")]
            for segment in info.segments:
                lines.append(self.text(
                    "job_segment_line", tool=segment.tool_index,
                    state=self.text(segment.assignment_state),
                    source=segment.source,
                    confidence=f"{segment.confidence_bp / 100:g}",
                    started=self._dash(segment.started_at), ended=self._dash(segment.ended_at),
                    spool=self._dash(segment.spool_name),
                ))
            sections.append("\n".join(lines))
        if info.ledger:
            lines = [self.text("job_section_ledger")]
            for entry in info.ledger:
                desc = "" if entry.description is None else f" · {entry.description}"
                lines.append(self.text(
                    "job_ledger_line", seq=entry.sequence,
                    type=self.text(entry.transaction_type),
                    delta=f"{entry.delta_mg / 1000:g}",
                    source=entry.source_type,
                    confidence=f"{entry.confidence_bp / 100:g}",
                    policy=entry.estimate_policy_version, desc=desc,
                ))
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def discover(self) -> None:
        if self.tasks or self._monitor_task is not None:
            return

        def scan() -> object:
            return discover_printers(primary_local_network())

        def display(result: object) -> None:
            self._candidates = ()
            self.candidate_list.clear()
            self.candidate_list.setVisible(False)
            self.connect_candidate_button.setEnabled(False)
            if not result:
                self.device_result.setPlainText(self.text("no_candidates"))
                return
            if not isinstance(result, tuple) or any(
                not isinstance(candidate, PrinterCandidate) for candidate in result
            ):
                self.device_result.setPlainText(self.text("discovery_failed"))
                return
            self._candidates = cast(tuple[PrinterCandidate, ...], result)
            confidence_key = {
                "identified": "discovery_identified",
                "unverified": "discovery_unverified",
            }
            lines = [
                self.text(
                    "discovery_candidate",
                    name=candidate.name,
                    port=candidate.port,
                    confidence=self.text(
                        confidence_key.get(candidate.confidence, "discovery_unverified"),
                    ),
                )
                for candidate in result
            ]
            for candidate in result:
                item = QListWidgetItem(
                    f"{candidate.name}:{candidate.port} · "
                    f"{self.text(confidence_key.get(candidate.confidence, 'discovery_unverified'))}"
                )
                self.candidate_list.addItem(item)
            self.candidate_list.setVisible(True)
            self.device_result.setPlainText("\n".join(lines))
            self._log("printer_discovery_completed", count=len(result))

        self.device_result.setPlainText(self.text("searching_candidates"))
        self.work(scan, display)

    def probe(self) -> None:
        if self._monitor_task is not None:
            self.info(self.text("monitor_stop_before_probe"))
            return
        index = self.printer_table.currentRow()
        if not 0 <= index < len(self.printers):
            return
        identity = EntityId.parse(self.printers[index].id)
        provider_type = self.printers[index].provider
        self._observed_slot_identities = ()
        self._observed_namespace = None
        self._observed_at = None
        self._mount_candidates = ()
        self._observed_printer_id = None
        self._observed_slots = ()

        def observe() -> object:
            result = asyncio.run(probe_configured_printer(
                engine=self.backend.engine, secret_store=self.container.secrets, printer_id=identity,
            ))
            status = result.status
            namespace = {
                "BAMBU_LAN": "bambu",
                "MOONRAKER": "moonraker",
                "OCTOPRINT": "octoprint",
            }.get(provider_type)
            mappings: list[tuple[str, str, SlotSpoolMatchState, str | None]] = []
            mount_candidates: list[tuple[str, str, FeedSystemKind, EntityId, str]] = []
            identities: list[tuple[str, str, str, str]] = []
            slot_details: list[ObservedSlotSync] = []
            if namespace is not None:
                topology = TopologyCommands(lambda: SQLiteUnitOfWork(self.backend.engine))
                actor_device_id = ensure_local_device(self.backend.engine)
                for system in status.feed_systems:
                    system_id = EntityId.parse(str(uuid5(
                        NAMESPACE_URL,
                        f"ufm:feed-system:{namespace}:{identity}:{system.provider_system_key}",
                    )))
                    for slot in system.slots:
                        slot_id = EntityId.parse(str(uuid5(
                            NAMESPACE_URL, f"ufm:feed-slot:{system_id}:{slot.slot_key}",
                        )))
                        topology.observe_provider_slot(
                            printer_id=identity, system_id=system_id,
                            provider_system_key=system.provider_system_key,
                            system_kind=system.kind, slot_id=slot_id, snapshot=slot,
                            observed_at=system.observed_at, received_at=system.received_at,
                            source_epoch=system.source_epoch,
                            source_sequence=system.source_sequence,
                            actor_device_id=actor_device_id,
                        )
                with SQLiteUnitOfWork(self.backend.engine) as work:
                    for system in status.feed_systems:
                        for slot in system.slots:
                            for kind, observation in (
                                ("tray_uuid", slot.tray_uuid), ("tag_uid", slot.tag_uid),
                            ):
                                if observation.value is not None:
                                    identities.append((system.provider_system_key, slot.slot_key,
                                                       kind, observation.value))
                            match = resolve_feed_slot_spool(
                                slot, namespace=namespace,
                                identifiers=work.spool_identifiers,
                            )
                            spool_name = (
                                work.spools.get(match.spool_id).display_name
                                if match.state is SlotSpoolMatchState.MATCHED
                                and match.spool_id is not None else None
                            )
                            mappings.append((system.provider_system_key, slot.slot_key,
                                             match.state, spool_name))
                            slot_details.append(ObservedSlotSync(
                                system.provider_system_key, slot.slot_key, match.state,
                                slot.material_hint, slot.color_hint,
                                None if slot.remaining_percent is None
                                else slot.remaining_percent.value,
                                None if slot.tray_uuid is None else slot.tray_uuid.value,
                                None if slot.tag_uid is None else slot.tag_uid.value,
                            ))
                            if match.state is SlotSpoolMatchState.MATCHED and match.spool_id is not None:
                                mount_candidates.append((
                                    system.provider_system_key, slot.slot_key, system.kind,
                                    match.spool_id, spool_name or "",
                                ))
            return (status, tuple(mappings), namespace, tuple(identities),
                    tuple(mount_candidates), tuple(slot_details))

        def display(result: object) -> None:
            status, mappings, namespace, identities, mount_candidates, slot_details = cast(
                tuple[PrinterStatusSnapshot,
                      tuple[tuple[str, str, SlotSpoolMatchState, str | None], ...],
                      str | None, tuple[tuple[str, str, str, str], ...],
                      tuple[tuple[str, str, FeedSystemKind, EntityId, str], ...],
                      tuple[ObservedSlotSync, ...]], result,
            )
            self._observed_namespace = namespace
            self._observed_at = status.observed_at
            self._observed_slot_identities = identities
            self._observed_printer_id = status.printer_id
            self._mount_candidates = mount_candidates
            self._observed_slots = slot_details
            message = self.text(
                "probe_done", state=str(status.connection_state),
                nozzle=(status.nozzle_temperature_c.value.canonical()
                        if status.nozzle_temperature_c.value is not None else self.text("unknown")),
                bed=(status.bed_temperature_c.value.canonical()
                     if status.bed_temperature_c.value is not None else self.text("unknown")),
                time=status.observed_at.isoformat(),
            )
            if mappings:
                lines = [message, "", self.text("feed_mapping_heading")]
                for system, slot, state, spool_name in mappings:
                    key = {
                        SlotSpoolMatchState.MATCHED: "feed_mapping_matched",
                        SlotSpoolMatchState.UNKNOWN: "feed_mapping_unknown",
                        SlotSpoolMatchState.CONFLICT: "feed_mapping_conflict",
                    }[state]
                    lines.append(self.text(
                        key, system=system, slot=slot,
                        spool=spool_name or self.text("unknown"),
                    ))
                message = "\n".join(lines)
            self.device_result.setPlainText(message)
            self._log(
                "printer_probe_completed", printer_id=str(status.printer_id),
                count=len(mappings), status=str(status.connection_state),
            )

        self._log("printer_probe_started", printer_id=str(identity))
        self.work(
            observe, display,
            after_failed=lambda code: self._log(
                "printer_probe_failed", printer_id=str(identity), error_code=code,
            ),
        )

    def update_printer_actions(self) -> None:
        index = self.printer_table.currentRow()
        enabled = (
            not self.tasks and self._monitor_task is None
            and 0 <= index < len(self.printers)
        )
        self.remove_printer_button.setEnabled(enabled)
        self.edit_printer_button.setEnabled(enabled)
        self.edit_printer_connection_button.setEnabled(
            enabled and self.printers[index].provider == "BAMBU_LAN"
        )
        self.accounting_authority_button.setEnabled(enabled)

    def manage_accounting_authority(self) -> None:
        index = self.printer_table.currentRow()
        if self.tasks or self._monitor_task is not None or not 0 <= index < len(self.printers):
            return
        printer = self.printers[index]

        def open_wizard(result: object) -> None:
            current, saved_connection = cast(
                tuple[
                    StudioAccountingAuthority | None,
                    StudioHaspelAuthorityConnection | None,
                ],
                result,
            )
            current_mode = (
                PrinterAccountingMode.REVIEW_ONLY if current is None
                else PrinterAccountingMode(current.mode)
            )
            allowed = ({
                PrinterAccountingMode.REVIEW_ONLY: (PrinterAccountingMode.LEGACY_ACTIVE,),
                PrinterAccountingMode.LEGACY_ACTIVE: (
                    PrinterAccountingMode.REVIEW_ONLY, PrinterAccountingMode.CUTOVER_READY,
                ),
                PrinterAccountingMode.CUTOVER_READY: (
                    PrinterAccountingMode.REVIEW_ONLY, PrinterAccountingMode.UFM_ACTIVE,
                ),
                PrinterAccountingMode.UFM_ACTIVE: (PrinterAccountingMode.REVIEW_ONLY,),
            }[current_mode] if current is not None else (
                PrinterAccountingMode.REVIEW_ONLY, PrinterAccountingMode.LEGACY_ACTIVE,
            ))
            dialog = QDialog(self)
            dialog.setWindowTitle(self.text("accounting_authority"))
            dialog.setMinimumWidth(700)
            layout = QVBoxLayout(dialog)
            current_label = QLabel(self.text(
                "authority_current", printer=printer.name,
                mode=self.text(f"authority_mode_{current_mode.value}"),
                revision=0 if current is None else current.revision,
                snapshot=self.text("unknown") if current is None or current.snapshot_sha256 is None
                else current.snapshot_sha256,
                writer_time=self.text("unknown") if current is None
                or current.legacy_writer_disabled_at is None
                else current.legacy_writer_disabled_at,
                reconciled_time=self.text("unknown") if current is None
                or current.reconciled_at is None else current.reconciled_at,
            ))
            current_label.setWordWrap(True)
            layout.addWidget(current_label)
            notice = QLabel(self.text("authority_local_notice"))
            notice.setWordWrap(True)
            layout.addWidget(notice)
            remote_form = QFormLayout()
            endpoint_edit = QLineEdit()
            endpoint_edit.setPlaceholderText("https://haspel-host:port")
            haspel_printer_edit = QLineEdit()
            api_key_edit = QLineEdit()
            api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            api_key_edit.setPlaceholderText(self.text("authority_remote_key_optional"))
            if saved_connection is not None:
                endpoint_edit.setText(saved_connection.endpoint_origin)
                haspel_printer_edit.setText(saved_connection.haspel_printer_id)
            remote_form.addRow(self.text("authority_remote_endpoint"), endpoint_edit)
            remote_form.addRow(self.text("authority_remote_printer"), haspel_printer_edit)
            remote_form.addRow(self.text("authority_remote_key"), api_key_edit)
            layout.addLayout(remote_form)
            remote_actions = QHBoxLayout()
            verify_remote_button = QPushButton(self.text("authority_remote_verify"))
            review_bookings_button = QPushButton(self.text("authority_review_bookings"))
            review_bookings_button.setObjectName("authority_review_bookings")
            review_bookings_button.setEnabled(False)
            remote_status = QLabel(self.text("authority_remote_unknown"))
            remote_status.setWordWrap(True)
            remote_actions.addWidget(verify_remote_button)
            remote_actions.addWidget(review_bookings_button)
            remote_actions.addWidget(remote_status, 1)
            layout.addLayout(remote_actions)
            remote_warning = QLabel(self.text("authority_remote_warning"))
            remote_warning.setWordWrap(True)
            layout.addWidget(remote_warning)
            target = QComboBox()
            for mode in allowed:
                target.addItem(self.text(f"authority_mode_{mode.value}"), mode.value)
            layout.addWidget(target)
            snapshot_row = QHBoxLayout()
            snapshot_label = QLabel(self.text("authority_snapshot_missing"))
            snapshot_label.setWordWrap(True)
            journal_paths: list[tuple[Path, Path, Path] | None] = [None]
            spoolman_source_key: list[str | None] = [None]
            cutover_preview: list[HaspelCutoverPreview | None] = [None]
            spoolman_preview: list[SpoolmanCutoverPreview | None] = [None]
            live_remote_snapshot: list[HaspelAuthoritySnapshot | None] = [None]
            choose_snapshot = QPushButton(self.text("authority_choose_snapshot"))
            snapshot_row.addWidget(choose_snapshot)
            snapshot_row.addWidget(snapshot_label, 1)
            layout.addLayout(snapshot_row)
            legacy_confirm = QCheckBox(self.text("authority_legacy_stopped"))
            source_confirm = QCheckBox(self.text("authority_source_confirm"))
            reconcile_confirm = QCheckBox(self.text("authority_reconciled"))
            layout.addWidget(legacy_confirm)
            layout.addWidget(source_confirm)
            layout.addWidget(reconcile_confirm)
            active_confirm = QCheckBox(self.text("authority_active_confirm"))
            layout.addWidget(active_confirm)
            warning = QLabel(self.text("authority_timestamp_warning"))
            warning.setWordWrap(True)
            layout.addWidget(warning)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.text("continue"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.text("cancel"))
            layout.addWidget(buttons)

            def verify_remote() -> None:
                endpoint = endpoint_edit.text().strip()
                haspel_printer_id = haspel_printer_edit.text().strip()
                entered_key = api_key_edit.text()
                try:
                    credential = SecretValue(entered_key) if entered_key else None
                except ValueError:
                    api_key_edit.clear()
                    QMessageBox.warning(
                        dialog, self.text("error"), self.text("authority_remote_invalid"),
                    )
                    return
                api_key_edit.clear()
                live_remote_snapshot[0] = None
                verify_remote_button.setEnabled(False)
                update_controls()

                def operation() -> tuple[
                    StudioHaspelAuthorityConnection | None,
                    HaspelAuthoritySnapshot | None,
                ]:
                    try:
                        connection, snapshot = self.backend.verify_haspel_authority_connection(
                            printer.id,
                            endpoint,
                            haspel_printer_id,
                            credential,
                            self.container.secrets,
                        )
                        return connection, snapshot
                    except Exception:
                        return None, None

                def remote_result(result: object) -> None:
                    connection, snapshot = cast(
                        tuple[
                            StudioHaspelAuthorityConnection | None,
                            HaspelAuthoritySnapshot | None,
                        ],
                        result,
                    )
                    if connection is None or snapshot is None:
                        remote_status.setText(self.text("authority_remote_failed"))
                        verify_remote_button.setEnabled(True)
                        update_controls()
                        return
                    endpoint_edit.setText(connection.endpoint_origin)
                    haspel_printer_edit.setText(connection.haspel_printer_id)
                    live_remote_snapshot[0] = snapshot
                    remote_status.setText(self.text(
                        "authority_remote_status",
                        owner=self.text(f"authority_mode_{snapshot.owner}"),
                        revision=snapshot.revision,
                        pending=snapshot.pending_count,
                        uncertain=snapshot.uncertain_count,
                        active=snapshot.active_count,
                    ))
                    verify_remote_button.setEnabled(True)
                    update_controls()

                self.work(operation, remote_result)

            def review_remote_bookings() -> None:
                if live_remote_snapshot[0] is None:
                    return

                def operation() -> tuple[bool, tuple[HaspelBookingRecord, ...]]:
                    try:
                        return True, self.backend.list_haspel_bookings(
                            printer.id, self.container.secrets,
                        )
                    except Exception:
                        return False, ()

                def show_bookings(result: object) -> None:
                    loaded, records = cast(
                        tuple[bool, tuple[HaspelBookingRecord, ...]], result,
                    )
                    if not loaded:
                        QMessageBox.warning(
                            dialog, self.text("error"),
                            self.text("authority_bookings_failed"),
                        )
                        return
                    unresolved = tuple(
                        item for item in records if item.status in {"pending", "uncertain"}
                    )
                    if not unresolved:
                        QMessageBox.information(
                            dialog, self.text("authority_review_bookings"),
                            self.text("authority_no_unresolved_bookings"),
                        )
                        return
                    review_dialog = QDialog(dialog)
                    review_dialog.setWindowTitle(self.text("authority_review_bookings"))
                    review_dialog.resize(820, 440)
                    review_layout = QVBoxLayout(review_dialog)
                    review_list = QListWidget(review_dialog)
                    for record in unresolved:
                        job = record.job_name or record.item_key
                        label = self.text(
                            "authority_booking_row",
                            status=record.status,
                            job=job,
                            spool=record.spool_id,
                            grams=f"{record.grams:g}",
                            terminal=record.terminal_state,
                        )
                        item = QListWidgetItem(label)
                        item.setData(Qt.ItemDataRole.UserRole, record.id)
                        review_list.addItem(item)
                    review_list.setCurrentRow(0)
                    review_layout.addWidget(review_list)
                    detail = QLabel(self.text("authority_booking_select"))
                    detail.setWordWrap(True)
                    review_layout.addWidget(detail)
                    records_by_id = {record.id: record for record in unresolved}

                    def show_booking_details(current_item: QListWidgetItem | None) -> None:
                        if current_item is None:
                            detail.setText(self.text("authority_booking_select"))
                            return
                        record = records_by_id[str(current_item.data(Qt.ItemDataRole.UserRole))]
                        detail.setText(self.text(
                            "authority_booking_details",
                            id=record.id,
                            item=record.item_key,
                            started=record.started_at,
                            created=record.created_at,
                        ))

                    review_list.currentItemChanged.connect(
                        lambda current_item, _previous: show_booking_details(current_item),
                    )
                    show_booking_details(review_list.currentItem())
                    controls = QHBoxLayout()
                    applied_button = QPushButton(self.text("authority_booking_applied"))
                    not_applied_button = QPushButton(self.text("authority_booking_not_applied"))
                    close_button = QPushButton(self.text("close"))
                    controls.addWidget(applied_button)
                    controls.addWidget(not_applied_button)
                    controls.addStretch(1)
                    controls.addWidget(close_button)
                    review_layout.addLayout(controls)
                    selected: list[tuple[str, str, str] | None] = [None]

                    def begin_resolution(resolution: str, label: str) -> None:
                        current_item = review_list.currentItem()
                        if current_item is None:
                            QMessageBox.information(
                                review_dialog, self.text("authority_review_bookings"),
                                self.text("authority_booking_select"),
                            )
                            return
                        note, accepted = QInputDialog.getMultiLineText(
                            review_dialog,
                            self.text("authority_booking_note_title"),
                            self.text("authority_booking_note_prompt"),
                        )
                        if not accepted:
                            return
                        if not note.strip() or len(note) > 500:
                            QMessageBox.warning(
                                review_dialog, self.text("error"),
                                self.text("authority_booking_note_invalid"),
                            )
                            return
                        confirmation = QMessageBox.question(
                            review_dialog,
                            self.text("authority_booking_confirm_title"),
                            self.text("authority_booking_confirm", resolution=label),
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No,
                        )
                        if confirmation != QMessageBox.StandardButton.Yes:
                            return
                        selected[0] = (
                            resolution,
                            str(current_item.data(Qt.ItemDataRole.UserRole)),
                            note.strip(),
                        )
                        review_dialog.accept()

                    applied_button.clicked.connect(
                        lambda: begin_resolution("applied", applied_button.text()),
                    )
                    not_applied_button.clicked.connect(
                        lambda: begin_resolution("not_applied", not_applied_button.text()),
                    )
                    close_button.clicked.connect(review_dialog.reject)
                    if review_dialog.exec() != QDialog.DialogCode.Accepted or selected[0] is None:
                        return
                    resolution, booking_id, note = selected[0]

                    def resolve_booking() -> tuple[str, object]:
                        try:
                            return "resolved", self.backend.resolve_haspel_booking(
                                printer.id, booking_id, resolution, note,
                                self.container.secrets,
                            )
                        except HaspelBookingResolutionUnknown:
                            return "unknown", None
                        except HaspelAuthorityConflict:
                            return "conflict", None
                        except Exception:
                            return "failed", None

                    def resolution_result(result: object) -> None:
                        state, payload = cast(tuple[str, object], result)
                        if state == "resolved":
                            _record, snapshot = cast(
                                tuple[HaspelBookingRecord, HaspelAuthoritySnapshot | None],
                                payload,
                            )
                            if snapshot is not None:
                                live_remote_snapshot[0] = snapshot
                                remote_status.setText(self.text(
                                    "authority_remote_status",
                                    owner=self.text(f"authority_mode_{snapshot.owner}"),
                                    revision=snapshot.revision,
                                    pending=snapshot.pending_count,
                                    uncertain=snapshot.uncertain_count,
                                    active=snapshot.active_count,
                                ))
                            else:
                                live_remote_snapshot[0] = None
                                remote_status.setText(self.text("authority_remote_unknown"))
                            QMessageBox.information(
                                dialog, self.text("authority_review_bookings"),
                                self.text("authority_booking_saved"),
                            )
                        else:
                            live_remote_snapshot[0] = None
                            remote_status.setText(self.text("authority_remote_unknown"))
                            message_key = {
                                "unknown": "authority_booking_unknown",
                                "conflict": "authority_booking_conflict",
                                "failed": "authority_bookings_failed",
                            }[state]
                            QMessageBox.warning(
                                dialog, self.text("error"), self.text(message_key),
                            )
                        update_controls()

                    self.work(
                        resolve_booking,
                        resolution_result,
                    )

                self.work(operation, show_bookings)

            def pick_snapshot() -> None:
                bookings_file, _ = QFileDialog.getOpenFileName(
                    dialog, self.text("authority_choose_snapshot"), "",
                    "JSON (*.json)",
                )
                if not bookings_file:
                    return
                accounting_file, _ = QFileDialog.getOpenFileName(
                    dialog, self.text("authority_choose_accounting"),
                    str(Path(bookings_file).parent), "JSON (*.json)",
                )
                if not accounting_file:
                    return
                spoolman_file, _ = QFileDialog.getOpenFileName(
                    dialog, self.text("authority_choose_spoolman"),
                    str(Path(accounting_file).parent), "SQLite databases (*.db *.sqlite *.sqlite3)",
                )
                if not spoolman_file:
                    return
                sources = self.backend.spoolman_import_sources()
                if not sources:
                    self.error("authority.source_missing")
                    return
                source_choices = [
                    f"{source.display_name} · {source.source_instance_key[:8]}"
                    for source in sources
                ]
                source_choice, accepted = QInputDialog.getItem(
                    dialog, self.text("authority_source_title"),
                    self.text("authority_source_prompt"), source_choices, 0, False,
                )
                if not accepted:
                    return
                selected_source = sources[source_choices.index(source_choice)]
                selected = (
                    Path(bookings_file), Path(accounting_file), Path(spoolman_file),
                )
                try:
                    preview = preview_haspelsync_cutover(
                        selected[0], selected[1], printer.serial_number,
                    )
                    inventory_preview = preview_spoolman_cutover(
                        selected[2], engine=self.backend.engine,
                        source_instance_key=selected_source.source_instance_key,
                    )
                except (HaspelCutoverPreviewRejected, SpoolmanImportRejected):
                    self.error("authority.snapshot_unreadable")
                    return
                journal_paths[0] = selected
                spoolman_source_key[0] = selected_source.source_instance_key
                cutover_preview[0] = preview
                spoolman_preview[0] = inventory_preview
                combined_digest = _combined_cutover_evidence_sha256(preview, inventory_preview)
                counts: dict[str, str | int] = {
                    "booking_pending": preview.printer_bookings[0],
                    "booking_booked": preview.printer_bookings[1],
                    "booking_uncertain": preview.printer_bookings[2],
                    "booking_dismissed": preview.printer_bookings[3],
                    "weighing_pending": preview.global_weighings[0],
                    "weighing_recorded": preview.global_weighings[1],
                    "weighing_uncertain": preview.global_weighings[2],
                    "weighing_rejected": preview.global_weighings[3],
                    "journal_ready": self.text("yes") if preview.ready else self.text("no"),
                    "source_unchanged": self.text("yes")
                    if inventory_preview.source_unchanged_since_import else self.text("no"),
                    "events_current": self.text("yes")
                    if preview.latest_activity_at_ms <= inventory_preview.last_imported_at_ms
                    else self.text("no"),
                    "stock_count": inventory_preview.spool_count,
                    "stock_matched": inventory_preview.matched_count,
                    "stock_mismatch": inventory_preview.mismatch_count,
                    "stock_missing": inventory_preview.missing_count,
                    "stock_extra": inventory_preview.unexpected_count,
                    "ready": self.text("yes")
                    if preview.ready and inventory_preview.ready and (
                        preview.latest_activity_at_ms <= inventory_preview.last_imported_at_ms
                    ) else self.text("no"),
                    "digest": combined_digest,
                }
                snapshot_label.setText(self.text("authority_cutover_preview", **counts))

            def update_controls() -> None:
                selected_mode = PrinterAccountingMode(str(target.currentData()))
                needs_cutover = selected_mode is PrinterAccountingMode.CUTOVER_READY
                needs_active = selected_mode is PrinterAccountingMode.UFM_ACTIVE
                needs_evidence = needs_cutover or needs_active
                snapshot_label.setVisible(needs_evidence)
                choose_snapshot.setVisible(needs_evidence)
                legacy_confirm.setVisible(needs_evidence)
                source_confirm.setVisible(needs_evidence)
                reconcile_confirm.setVisible(needs_evidence)
                active_confirm.setVisible(needs_active)
                remote_snapshot = live_remote_snapshot[0]
                remote_ready = (
                    remote_snapshot is not None
                    and remote_snapshot.owner == "LEGACY_ACTIVE"
                    and remote_snapshot.pending_count == 0
                    and remote_snapshot.uncertain_count == 0
                    and remote_snapshot.active_count == 0
                )
                review_bookings_button.setEnabled(remote_snapshot is not None)
                accept_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
                if accept_button is not None:
                    accept_button.setEnabled(not needs_active or remote_ready)

            def invalidate_remote(*_args: object) -> None:
                if live_remote_snapshot[0] is not None:
                    live_remote_snapshot[0] = None
                    remote_status.setText(self.text("authority_remote_unknown"))
                    update_controls()

            choose_snapshot.clicked.connect(pick_snapshot)
            verify_remote_button.clicked.connect(verify_remote)
            review_bookings_button.clicked.connect(review_remote_bookings)
            endpoint_edit.textChanged.connect(invalidate_remote)
            haspel_printer_edit.textChanged.connect(invalidate_remote)
            target.currentIndexChanged.connect(update_controls)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            update_controls()
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            selected_mode = PrinterAccountingMode(str(target.currentData()))
            snapshot_hash: str | None = None
            disabled_at: str | None = None
            reconciled_at: str | None = None
            if selected_mode is PrinterAccountingMode.CUTOVER_READY:
                if journal_paths[0] is None or cutover_preview[0] is None \
                        or spoolman_preview[0] is None or spoolman_source_key[0] is None \
                        or not cutover_preview[0].ready \
                        or not spoolman_preview[0].ready \
                        or not legacy_confirm.isChecked() or not source_confirm.isChecked() \
                        or not reconcile_confirm.isChecked():
                    self.error("authority.evidence_required")
                    return
                # Re-read both journals after confirmation; changed or unresolved data blocks cutover.
                try:
                    refreshed_preview = preview_haspelsync_cutover(
                        journal_paths[0][0], journal_paths[0][1], printer.serial_number,
                    )
                    refreshed_inventory = preview_spoolman_cutover(
                        journal_paths[0][2], engine=self.backend.engine,
                        source_instance_key=spoolman_source_key[0],
                    )
                except (HaspelCutoverPreviewRejected, SpoolmanImportRejected):
                    self.error("authority.snapshot_unreadable")
                    return
                if (
                    not refreshed_preview.ready or not refreshed_inventory.ready
                    or refreshed_preview.latest_activity_at_ms > refreshed_inventory.last_imported_at_ms
                    or _combined_cutover_evidence_sha256(
                        refreshed_preview, refreshed_inventory,
                    ) != _combined_cutover_evidence_sha256(
                        cutover_preview[0], spoolman_preview[0],
                    )
                ):
                    self.error("authority.evidence_required")
                    return
                snapshot_hash = _combined_cutover_evidence_sha256(
                    refreshed_preview, refreshed_inventory,
                )
                now = str(UtcDateTime.now())
                disabled_at = now
                reconciled_at = now
            elif selected_mode is PrinterAccountingMode.UFM_ACTIVE:
                live_snapshot = live_remote_snapshot[0]
                if (
                    current is None or not active_confirm.isChecked()
                    or live_snapshot is None
                    or live_snapshot.owner != "LEGACY_ACTIVE"
                    or live_snapshot.pending_count != 0
                    or live_snapshot.uncertain_count != 0
                    or live_snapshot.active_count != 0
                    or journal_paths[0] is None or cutover_preview[0] is None
                    or spoolman_preview[0] is None or spoolman_source_key[0] is None
                    or not cutover_preview[0].ready or not spoolman_preview[0].ready
                    or not legacy_confirm.isChecked() or not source_confirm.isChecked()
                    or not reconcile_confirm.isChecked()
                ):
                    if (
                        live_snapshot is None
                        or live_snapshot.owner != "LEGACY_ACTIVE"
                        or live_snapshot.pending_count != 0
                        or live_snapshot.uncertain_count != 0
                        or live_snapshot.active_count != 0
                    ):
                        QMessageBox.warning(
                            dialog, self.text("error"),
                            self.text("authority_remote_activation_required"),
                        )
                    else:
                        self.error("authority.evidence_required")
                    return
                try:
                    refreshed_preview = preview_haspelsync_cutover(
                        journal_paths[0][0], journal_paths[0][1], printer.serial_number,
                    )
                    refreshed_inventory = preview_spoolman_cutover(
                        journal_paths[0][2], engine=self.backend.engine,
                        source_instance_key=spoolman_source_key[0],
                    )
                except (HaspelCutoverPreviewRejected, SpoolmanImportRejected):
                    self.error("authority.snapshot_unreadable")
                    return
                refreshed_hash = _combined_cutover_evidence_sha256(
                    refreshed_preview, refreshed_inventory,
                )
                if (
                    not refreshed_preview.ready or not refreshed_inventory.ready
                    or refreshed_preview.latest_activity_at_ms
                    > refreshed_inventory.last_imported_at_ms
                    or refreshed_hash != current.snapshot_sha256
                ):
                    self.error("authority.evidence_required")
                    return
                snapshot_hash = refreshed_hash
                disabled_at = current.legacy_writer_disabled_at
                reconciled_at = current.reconciled_at
            summary = self.text(
                "authority_transition_confirm", printer=printer.name,
                mode=self.text(f"authority_mode_{selected_mode.value}"),
            )
            if selected_mode in {
                PrinterAccountingMode.CUTOVER_READY, PrinterAccountingMode.UFM_ACTIVE,
            }:
                summary += "\n\n" + self.text("authority_timestamp_warning")
            if selected_mode is PrinterAccountingMode.UFM_ACTIVE:
                summary += "\n\n" + self.text("authority_remote_transfer_warning")
            if QMessageBox.question(
                self, self.text("accounting_authority"), summary,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            expected_local_revision = 0 if current is None else current.revision

            def save_transition() -> object:
                if selected_mode is PrinterAccountingMode.UFM_ACTIVE:
                    live_snapshot = live_remote_snapshot[0]
                    if live_snapshot is None:
                        return None
                    try:
                        return self.backend.activate_ufm_authority_with_haspel(
                            printer.id,
                            expected_local_revision,
                            live_snapshot.revision,
                            cast(str, snapshot_hash),
                            cast(str, disabled_at),
                            cast(str, reconciled_at),
                            self.container.secrets,
                        )
                    except Exception:
                        return None
                return self.backend.transition_accounting_authority(
                    printer.id, selected_mode.value, expected_local_revision,
                    snapshot_sha256=snapshot_hash,
                    legacy_writer_disabled_at=disabled_at,
                    reconciled_at=reconciled_at,
                )

            def transition_saved(result: object) -> None:
                if result is None:
                    QMessageBox.warning(
                        self, self.text("error"),
                        self.text("authority_remote_activation_failed"),
                    )
                    return
                saved = cast(StudioAccountingAuthority, result)
                if selected_mode is PrinterAccountingMode.UFM_ACTIVE:
                    saved, remote_saved = cast(
                        tuple[StudioAccountingAuthority, HaspelAuthoritySnapshot], result,
                    )
                    message = self.text(
                        "authority_remote_transferred", revision=remote_saved.revision,
                    )
                else:
                    message = ""
                message = "\n\n".join(part for part in (
                    message,
                    self.text(
                        "authority_saved", mode=saved.mode, revision=saved.revision,
                    ),
                ) if part)
                self.info(message)

            self.work(save_transition, transition_saved)

        self.work(
            lambda: (
                self.backend.accounting_authority(printer.id),
                self.backend.haspel_authority_connection(printer.id),
            ),
            open_wizard,
        )

    def toggle_printer_monitor(self) -> None:
        task = self._monitor_task
        if task is not None:
            self.monitor_button.setEnabled(False)
            self.monitor_status.setText(self.text("monitor_stopping"))
            task.stop()
            return

        index = self.printer_table.currentRow()
        if not 0 <= index < len(self.printers):
            self.info(self.text("monitor_select_printer"))
            return
        selected = self.printers[index]
        if QMessageBox.question(
            self, self.text("monitor_start"),
            self.text("monitor_confirmation", name=selected.name),
        ) != QMessageBox.StandardButton.Yes:
            return

        identity = EntityId.parse(selected.id)
        task = PrinterMonitorTask(
            lambda: configured_printer_provider(
                engine=self.backend.engine,
                secret_store=self.container.secrets,
                printer_id=identity,
            ),
            self,
        )
        self._monitor_task = task
        self._monitor_printer_name = selected.name
        self._monitor_provider = selected.provider
        self._monitor_failed = False
        self.printer_table.setEnabled(False)
        self.remove_printer_button.setEnabled(False)
        self.monitor_button.setText(self.text("monitor_stop"))
        self.monitor_status.setText(self.text("monitor_connecting", name=selected.name))
        self.monitor_details.setText(self.text("monitor_details_idle"))
        self.monitor_capabilities.setText(self.text("monitor_capabilities_idle"))
        self.monitor_slot_details.setText(self.text("monitor_slots_idle"))
        task.event_available.connect(self.show_latest_monitored_event)
        task.status_available.connect(self.show_latest_monitored_status)
        task.capabilities_available.connect(self.show_latest_monitored_capabilities)
        task.state_changed.connect(self.printer_monitor_state_changed)
        task.failed.connect(self.printer_monitor_failed)
        task.finished.connect(self.finish_printer_monitor)
        task.start()
        self._log("printer_monitor_started", printer_id=str(identity))

    def show_latest_monitored_event(self) -> None:
        task = self._monitor_task
        if task is None:
            return
        self.show_monitored_event(task.take_latest_event())

    def show_latest_monitored_status(self) -> None:
        task = self._monitor_task
        if task is None:
            return
        status = task.take_latest_status()
        if status is None:
            return
        self.show_monitored_status(status)

    def show_monitored_status(self, status: PrinterStatusSnapshot) -> None:
        unavailable_text = {
            Availability.UNKNOWN: self.text("monitor_capability_unknown"),
            Availability.UNAVAILABLE: self.text("monitor_capability_unavailable"),
            Availability.UNSUPPORTED: self.text("monitor_capability_unsupported"),
        }

        def display[ValueT](
            observation: Observed[ValueT], format_value: Callable[[ValueT], str],
        ) -> str:
            if observation.value is not None:
                return format_value(observation.value)
            return unavailable_text[observation.availability]

        nozzle = (
            display(status.nozzle_temperature_c, lambda value: f"{value.canonical()} °C")
        )
        bed = (
            display(status.bed_temperature_c, lambda value: f"{value.canonical()} °C")
        )
        layer = display(status.current_layer, str)
        progress = display(status.progress, lambda value: f"{value / 100:.0f}%")
        feeds = "; ".join(
            f"{system.kind.value}: {len(system.slots)}"
            for system in status.feed_systems
        ) or self.text("monitor_no_feed_system")
        self.monitor_details.setText(self.text(
            "monitor_details", nozzle=nozzle, bed=bed, layer=layer,
            progress=progress, feeds=feeds,
        ))
        slot_rows = []
        for system in status.feed_systems:
            system_key = f"feed_kind_{system.kind.value.lower()}"
            system_label = self.text(
                system_key if system_key in self.strings else "feed_kind_generic",
            )
            for slot in system.slots:
                occupancy_key = (
                    "monitor_slot_loaded" if slot.occupancy.value is True
                    else "monitor_slot_empty" if slot.occupancy.value is False
                    else None
                )
                occupancy = (
                    self.text(occupancy_key) if occupancy_key is not None
                    else unavailable_text[slot.occupancy.availability]
                )
                remaining = display(
                    slot.remaining_mass,
                    lambda value: f"{value.grams:f} {self.text('grams_short')} ",
                ).strip()
                percent = (
                    display(slot.remaining_percent, lambda value: f"{value}%")
                    if slot.remaining_percent is not None
                    else unavailable_text[Availability.UNKNOWN]
                )
                slot_rows.append(self.text(
                    "monitor_slot", system=system_label, slot=slot.slot_key,
                    occupancy=occupancy, mass=remaining, percent=percent,
                ))
        self.monitor_slot_details.setText(self.text(
            "monitor_slots", slots=" · ".join(slot_rows),
        ) if slot_rows else self.text("monitor_no_feed_system"))

    def show_latest_monitored_capabilities(self) -> None:
        task = self._monitor_task
        if task is None:
            return
        capabilities = task.take_latest_capabilities()
        if capabilities is not None:
            self.show_monitored_capabilities(capabilities)

    def show_monitored_capabilities(self, capabilities: PrinterCapabilities) -> None:
        capability_rows = (
            ("job_detection", capabilities.job_detection),
            ("progress", capabilities.progress),
            ("layers", capabilities.layers),
            ("temperature", capabilities.temperature),
            ("camera", capabilities.camera),
            ("pause", capabilities.pause),
            ("resume", capabilities.resume),
            ("cancel", capabilities.cancel),
            ("filament_usage", capabilities.filament_usage),
            ("multi_material", capabilities.multi_material),
            ("file_metadata", capabilities.file_metadata),
            ("local_connection", capabilities.local_connection),
            ("cloud_connection", capabilities.cloud_connection),
            ("push_events", capabilities.push_events),
            ("polling", capabilities.polling),
        )
        availability_text = {
            Availability.UNKNOWN: self.text("monitor_capability_unknown"),
            Availability.UNAVAILABLE: self.text("monitor_capability_unavailable"),
            Availability.UNSUPPORTED: self.text("monitor_capability_unsupported"),
        }
        entries = []
        for key, observation in capability_rows:
            value = (
                self.text("monitor_capability_yes") if observation.value is True
                else self.text("monitor_capability_no") if observation.value is False
                else availability_text[observation.availability]
            )
            entries.append(self.text(f"capability_{key}") + ": " + value)
        checked_at = max(
            observation.observed_at for _, observation in capability_rows
        ).isoformat()
        provider_key = f"monitor_provider_{self._monitor_provider.lower()}"
        provider_label = self.text(
            provider_key if provider_key in self.strings else "monitor_provider_unknown",
        )
        self.monitor_capabilities.setText(self.text(
            "monitor_capabilities", provider=provider_label, time=checked_at,
            features=" · ".join(entries),
        ))

    def show_monitored_event(self, event: object) -> None:
        if not isinstance(event, PrinterEvent):
            return
        job = event.job
        state = self.text("monitor_no_job") if job is None else self.text(
            f"monitor_job_{job.status.value.lower()}",
        )
        progress = "—" if job is None or job.progress_bp is None else f"{job.progress_bp / 100:.0f}%"
        layer = self.text("unknown") if job is None or job.current_layer is None else str(job.current_layer)
        self.monitor_status.setText(self.text(
            "monitor_observed", name=self._monitor_printer_name,
            state=state, progress=progress, layer=layer,
        ))

    def printer_monitor_state_changed(self, state: str) -> None:
        self._log("printer_monitor_state", details=state)
        if state == "online":
            self.monitor_status.setText(self.text(
                "monitor_online", name=self._monitor_printer_name,
            ))
        elif state == "offline":
            self.monitor_status.setText(self.text(
                "monitor_offline", name=self._monitor_printer_name,
            ))
        elif state == "stale":
            self.monitor_status.setText(self.text(
                "monitor_stale", name=self._monitor_printer_name,
            ))
        elif state == "retrying":
            self.monitor_status.setText(self.text(
                "monitor_retrying", name=self._monitor_printer_name,
            ))
        elif state == "connecting":
            self.monitor_status.setText(self.text(
                "monitor_connecting", name=self._monitor_printer_name,
            ))

    def printer_monitor_failed(self, error_type: str) -> None:
        self._monitor_failed = True
        self._log("printer_monitor_failed", error_code=error_type)
        error_key = {
            "AuthenticationFailed": "monitor_error_authentication",
            "TLSVerificationFailed": "monitor_error_tls",
            "ProviderUnavailable": "monitor_error_unavailable",
            "UnsupportedCapability": "monitor_error_unsupported",
            "InvalidObservation": "monitor_error_invalid_data",
            "PrinterEventBufferOverflow": "monitor_error_event_overflow",
        }.get(error_type, "monitor_error_generic")
        self.monitor_status.setText(self.text(
            "monitor_failed", error=self.text(error_key),
        ))

    def finish_printer_monitor(self) -> None:
        self._log("printer_monitor_stopped", status="failed" if self._monitor_failed else "ok")
        task = self._monitor_task
        self._monitor_task = None
        self.printer_table.setEnabled(True)
        self.monitor_button.setEnabled(True)
        self.monitor_button.setText(self.text("monitor_start"))
        self.update_printer_actions()
        if not self._monitor_failed:
            self.monitor_status.setText(self.text("monitor_idle"))
        if task is not None:
            task.deleteLater()
        self.close_when_idle()

    def close_when_idle(self) -> None:
        if self._close_when_idle and not self.tasks and self._monitor_task is None:
            QTimer.singleShot(0, self.close)

    def remove_printer(self) -> None:
        index = self.printer_table.currentRow()
        if self.tasks or self._monitor_task is not None or not 0 <= index < len(self.printers):
            return
        selected = self.printers[index]
        if QMessageBox.question(
            self, self.text("remove_printer"),
            self.text("remove_printer_confirmation", name=selected.name),
        ) != QMessageBox.StandardButton.Yes:
            return

        def remove() -> object:
            return remove_configured_printer(
                engine=self.backend.engine,
                secret_store=self.container.secrets,
                printer_id=EntityId.parse(selected.id),
            )

        def completed(name: object) -> None:
            self.refresh()
            self.info(self.text("printer_removed", name=str(name)))

        self.work(remove, completed)

    def edit_printer(self) -> None:
        index = self.printer_table.currentRow()
        if self.tasks or self._monitor_task is not None or not 0 <= index < len(self.printers):
            return
        selected = self.printers[index]
        name, model = QLineEdit(selected.name), QLineEdit(selected.model)
        if not self.form("edit_printer_details", [("name", name), ("model", model)]):
            return

        def update_details() -> object:
            return update_printer_details(
                engine=self.backend.engine,
                printer_id=EntityId.parse(selected.id),
                name=name.text(),
                model=model.text(),
            )

        def completed(updated_name: object) -> None:
            self.refresh()
            self.info(self.text("printer_details_updated", name=str(updated_name)))

        self.work(update_details, completed)

    def edit_printer_connection(self) -> None:
        index = self.printer_table.currentRow()
        if self.tasks or self._monitor_task is not None or not 0 <= index < len(self.printers):
            return
        selected = self.printers[index]
        if selected.provider != "BAMBU_LAN":
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.text("edit_printer_connection"))
        dialog.resize(560, 300)
        layout = QFormLayout(dialog)
        host = QLineEdit(selected.host)
        host.setObjectName("bambu-edit-host")
        serial = QLineEdit(selected.serial_number)
        serial.setObjectName("bambu-edit-serial")
        access_code = QLineEdit()
        access_code.setObjectName("bambu-edit-access-code")
        access_code.setEchoMode(QLineEdit.EchoMode.Password)
        access_code.setPlaceholderText(self.text("access_code_required"))
        layout.addRow(self.text("host"), host)
        layout.addRow(self.text("serial"), serial)
        layout.addRow(self.text("access_code"), access_code)
        hint = QLabel(self.text("edit_printer_connection_hint"))
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(self.text("test_save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.text("cancel"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            access_code.clear()
            return

        new_host = host.text()
        new_serial = serial.text()
        secret = SecretValue(access_code.text())
        access_code.clear()

        def update_connection() -> object:
            return asyncio.run(update_bambu_printer_connection(
                engine=self.backend.engine,
                secret_store=self.container.secrets,
                printer_id=EntityId.parse(selected.id),
                host=new_host,
                serial_number=new_serial,
                access_code=secret,
            ))

        def completed(_: object) -> None:
            self.refresh()
            self.info(self.text("printer_connection_updated", name=selected.name))

        self.work(update_connection, completed)

    def sync_observed_spools(self) -> None:
        if (not self._observed_slots or self._observed_namespace is None
                or not self._snapshot_is_fresh()):
            self.info(self.text("sync_probe_first"))
            return
        candidates = [
            slot for slot in self._observed_slots
            if slot.match_state is SlotSpoolMatchState.UNKNOWN
            and (slot.tray_uuid is not None or slot.tag_uid is not None)
        ]
        if not candidates:
            self.info(self.text("sync_none"))
            return
        dialog = QDialog(self)
        dialog.setObjectName("observed-spool-sync")
        dialog.setWindowTitle(self.text("sync_title"))
        layout = QFormLayout(dialog)
        slot_combo = QComboBox()
        slot_combo.setObjectName("observed-spool-sync-slot")
        for index, slot in enumerate(candidates):
            hints = " · ".join(
                part for part in (
                    slot.material_hint,
                    slot.color_hint,
                    None if slot.remaining_percent is None
                    else f"{slot.remaining_percent}%",
                ) if part
            )
            slot_combo.addItem(
                f"{slot.system_key} · {slot.slot_key} · {hints or self.text('unknown')}",
                index,
            )
        spool_combo = QComboBox()
        spool_combo.setObjectName("observed-spool-sync-target")
        for item in self.rows:
            spool_combo.addItem(item.name, item.id)
        new_marker = "__new__"
        spool_combo.addItem(self.text("sync_new_spool"), new_marker)
        layout.addRow(self.text("sync_slot"), slot_combo)
        layout.addRow(self.text("spool"), spool_combo)
        buttons = QDialogButtonBox()
        buttons.addButton(self.text("confirm"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.text("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        slot = candidates[int(slot_combo.currentData())]
        target = spool_combo.currentData()
        material = (slot.material_hint or "").strip().upper()
        material_type = material if material in {item.value for item in MaterialType} else "CUSTOM"
        auto_name = " ".join(
            part for part in (slot.material_hint or "Filament", slot.slot_key) if part
        )[:200]

        def enroll() -> object:
            actor = ensure_local_device(self.backend.engine)
            if target == new_marker:
                profile_id = self._profile_id_for_material(material_type, material)
                spool_id = self.backend.add_spool(
                    auto_name, profile_id,
                    color_hex=slot.color_hint,
                    notes=f"Auto-enrolled from {slot.system_key} {slot.slot_key}",
                )
            else:
                spool_id = str(target)
            commands = SpoolIdentifierCommands(
                lambda: SQLiteUnitOfWork(self.backend.engine),
            )
            bound: list[str] = []
            conflicts: list[str] = []
            for kind, value in (("tray_uuid", slot.tray_uuid), ("tag_uid", slot.tag_uid)):
                if value is None:
                    continue
                try:
                    commands.verify(
                        spool_id=EntityId.parse(spool_id),
                        namespace=self._observed_namespace or "",
                        kind=kind, value=value, actor_device_id=actor,
                        command_key=f"studio-slot-sync-{uuid4()}",
                        manual_confirmation=True,
                    )
                    bound.append(kind)
                except ValueError:
                    conflicts.append(kind)
            return bound, conflicts, spool_id

        def done(result: object) -> None:
            bound, conflicts, _spool_id = cast(
                tuple[list[str], list[str], str], result,
            )
            self.refresh()
            self._log(
                "spool_sync_completed", count=len(bound),
                status="partial" if conflicts else "ok",
            )
            if conflicts:
                self.info(self.text(
                    "sync_partial", bound=len(bound), conflicts=len(conflicts),
                ))
            else:
                self.info(self.text("sync_done", bound=len(bound)))

        self.work(enroll, done)

    def _profile_id_for_material(self, material_type: str, raw_hint: str) -> str:
        wanted = material_type.upper()
        for profile in self.profiles:
            if profile.material.upper() == wanted:
                return profile.id
        name = raw_hint.strip() or wanted
        return self.backend.add_material(name, wanted if wanted != "CUSTOM" else "CUSTOM")

    def verify_feed_identity(self) -> None:
        if (not self._observed_slot_identities or self._observed_namespace is None
                or not self._snapshot_is_fresh()):
            self.info(self.text("identity_probe_first"))
            return
        dialog = QDialog(self)
        dialog.setObjectName("spool-identifier-enrollment")
        dialog.setWindowTitle(self.text("verify_identity"))
        layout = QFormLayout(dialog)
        observed = QComboBox()
        observed.setObjectName("spool-identifier-observed")
        choices = self._observed_slot_identities
        bindings: list[tuple[str | None, EntityId | None]] = []
        try:
            with SQLiteUnitOfWork(self.backend.engine) as work:
                for _system, _slot, kind, value in choices:
                    identifier = work.spool_identifiers.by_trusted_identity(
                        self._observed_namespace or "", kind, value,
                    )
                    if identifier is None:
                        bindings.append((None, None))
                        continue
                    try:
                        bound_name = work.spools.get(identifier.spool_id).display_name
                    except NotFound:
                        bound_name = None
                    bindings.append((bound_name, identifier.spool_id))
        except Exception:
            bindings = [(None, None)] * len(choices)
        for index, (system, slot, kind, value) in enumerate(choices):
            bound_name, _bound_id = bindings[index]
            suffix = (
                f" · → {bound_name}" if bound_name
                else f" · → {self.text('identity_unbound')}"
            )
            observed.addItem(
                f"{system} · {slot} · {kind} · …{value[-6:]}{suffix}", index,
            )
        spool = QComboBox()
        spool.setObjectName("spool-identifier-spool")
        for item in self.rows:
            spool.addItem(item.name, item.id)
        if spool.count() == 0:
            self.info(self.text("no_spools_for_identity"))
            return
        layout.addRow(self.text("observed_identity"), observed)
        layout.addRow(self.text("spool"), spool)
        buttons = QDialogButtonBox()
        buttons.addButton(self.text("confirm"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.text("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = choices[int(observed.currentData())]
        system, slot, kind, value = selected
        bound_name, bound_spool_id = bindings[int(observed.currentData())]
        spool_id = EntityId.parse(str(spool.currentData()))
        rebound = bound_spool_id is not None and bound_spool_id != spool_id
        message_key = "identity_rebind_message" if rebound else "identity_confirm_message"
        message = self.text(
            message_key, spool=spool.currentText(), system=system,
            slot=slot, kind=kind, value=value,
            bound=self.text("identity_unbound") if bound_name is None else bound_name,
        )
        if QMessageBox.question(self, self.text("verify_identity"), message) != \
                QMessageBox.StandardButton.Yes:
            return

        def verify() -> object:
            commands = SpoolIdentifierCommands(
                lambda: SQLiteUnitOfWork(self.backend.engine),
            )
            if rebound:
                return commands.rebind(
                    spool_id=spool_id, namespace=self._observed_namespace or "",
                    kind=kind, value=value,
                    actor_device_id=ensure_local_device(self.backend.engine),
                    command_key=f"studio-spool-identity-rebind-{uuid4()}",
                    manual_confirmation=True,
                )
            return commands.verify(
                spool_id=spool_id, namespace=self._observed_namespace or "",
                kind=kind, value=value, actor_device_id=ensure_local_device(self.backend.engine),
                command_key=f"studio-spool-identity-{uuid4()}", manual_confirmation=True,
            )

        done_key = "identity_rebound_reprobe" if rebound else "identity_verified_reprobe"

        def verified(_: object) -> None:
            self._log(
                "spool_identity_verified", spool_id=str(spool_id),
                status="rebound" if rebound else "verified",
            )
            self.info(self.text(done_key))

        self.work(verify, verified)

    def mount_verified_feed_slot(self) -> None:
        if (self._observed_printer_id is None or not self._mount_candidates
                or not self._snapshot_is_fresh()):
            self.info(self.text("mount_probe_first"))
            return
        dialog = QDialog(self)
        dialog.setObjectName("verified-spool-mount")
        dialog.setWindowTitle(self.text("mount_verified_title"))
        layout = QFormLayout(dialog)
        candidate = QComboBox()
        candidate.setObjectName("verified-spool-mount-candidate")
        choices = self._mount_candidates
        for index, (system, slot, _kind, _spool_id, spool_name) in enumerate(choices):
            candidate.addItem(f"{system} · {slot} · {spool_name}", index)
        layout.addRow(self.text("mount_target"), candidate)
        buttons = QDialogButtonBox()
        buttons.addButton(self.text("confirm"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.text("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        system_key, slot_key, system_kind, spool_id, spool_name = choices[
            int(candidate.currentData())
        ]
        printer_id = self._observed_printer_id
        namespace = self._observed_namespace
        printer_name = next(
            (item.name for item in self.printers if item.id == str(printer_id)),
            self.text("printer"),
        )
        message = self.text(
            "mount_confirm_message", printer=printer_name, system=system_key,
            slot=slot_key, spool=spool_name,
        )
        if QMessageBox.question(self, self.text("mount_verified_title"), message) != \
                QMessageBox.StandardButton.Yes:
            return

        def mount() -> object:
            if namespace is None:
                raise ValueError("slot_identity.namespace_invalid")
            system_id = EntityId.parse(str(uuid5(
                NAMESPACE_URL, f"ufm:feed-system:{namespace}:{printer_id}:{system_key}",
            )))
            slot_id = EntityId.parse(str(uuid5(
                NAMESPACE_URL, f"ufm:feed-slot:{system_id}:{slot_key}",
            )))
            topology = TopologyCommands(lambda: SQLiteUnitOfWork(self.backend.engine))
            topology.create_external_slot(
                system_id=system_id, slot_id=slot_id, printer_id=printer_id,
                system_name=f"{namespace} {system_key}", slot_key=slot_key,
                actor_device_id=ensure_local_device(self.backend.engine),
                command_key=f"provider-slot-create-{slot_id}", tool_index=None,
                system_kind=system_kind, provider_system_key=system_key,
            )
            return topology.mount_spool(
                mount_id=EntityId.new(), slot_id=slot_id, spool_id=spool_id,
                actor_device_id=ensure_local_device(self.backend.engine),
                command_key=f"studio-provider-mount-{uuid4()}",
                assignment_source=AssignmentSource.MANUAL, confidence_bp=10_000,
            )

        def mounted(_: object) -> None:
            self._mount_candidates = ()
            self._log("feed_slot_mounted", spool_id=str(spool_id))
            self.info(self.text("mount_done"))

        self.work(mount, mounted)

    def _snapshot_is_fresh(self) -> bool:
        if self._observed_at is None:
            return False
        age = (UtcDateTime.now().value - self._observed_at.value).total_seconds()
        return 0 <= age <= 120

    def enroll_local(self, candidate: PrinterCandidate | None = None) -> None:
        name, manufacturer, model, endpoint, token = (QLineEdit() for _ in range(5))
        token.setEchoMode(QLineEdit.EchoMode.Password)
        provider = QComboBox()
        provider.addItem("Moonraker / Klipper", "MOONRAKER")
        provider.addItem("OctoPrint", "OCTOPRINT")
        if candidate is not None:
            name.setText(candidate.name)
            endpoint.setText(candidate.endpoint)
            index = provider.findData(candidate.provider_type)
            if index >= 0:
                provider.setCurrentIndex(index)
        if not self.form("enrollment", [
            ("name", name), ("manufacturer", manufacturer), ("model", model),
            ("provider", provider), ("endpoint", endpoint), ("token", token),
        ]):
            return
        # Capture text on the GUI thread, then release the dialog's secret field.
        inputs = (name.text(), manufacturer.text(), model.text(), endpoint.text(),
                  str(provider.currentData()))
        credential = SecretValue(token.text()) if token.text() else None
        token.clear()

        def connect() -> object:
            return asyncio.run(configure_local_printer(
                engine=self.backend.engine, secret_store=self.container.secrets,
                name=inputs[0], manufacturer=inputs[1], model=inputs[2],
                endpoint=inputs[3], provider_type=inputs[4], token=credential,
            ))

        self.work(connect, lambda _: self.info(self.text("enrolled")))

    def enroll_bambu(self) -> None:
        host, accepted = QInputDialog.getText(self, self.text("bambu_import"),
                                             self.text("bambu_host"))
        if not accepted or not host.strip():
            return

        def confirm(result: object) -> None:
            profile = cast(BambuStudioProfile, result)
            message = self.text("trust", serial=profile.serial_number,
                                fingerprint=profile.certificate_sha256)
            if QMessageBox.question(self, self.text("enrollment"), message) != QMessageBox.StandardButton.Yes:
                return
            name, model = QLineEdit(profile.serial_number), QLineEdit(profile.model or "")
            if not self.form("enrollment", [("name", name), ("model", model)]):
                return
            clean_name, clean_model = name.text(), model.text()

            def connect() -> object:
                certificate = store_bambu_root_certificate(self.backend.paths.config, profile)
                return asyncio.run(configure_bambu_printer(
                    engine=self.backend.engine, secret_store=self.container.secrets,
                    name=clean_name, model=clean_model, host=profile.host,
                    serial_number=profile.serial_number, access_code=profile.access_code,
                    ca_certificate=certificate, certificate_sha256=profile.certificate_sha256,
                ))

            QTimer.singleShot(0, lambda: self.work(
                connect, lambda _: self.info(self.text("enrolled")),
            ))

        self.work(lambda: import_bambu_studio_profile(host.strip()), confirm)

    def enroll_bambu_network(self, candidate: PrinterCandidate | None = None) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("bambu-enrollment")
        dialog.setWindowTitle(self.text("network_autofill"))
        dialog.setMinimumWidth(550)
        layout = QFormLayout(dialog)
        fields: dict[str, QLineEdit] = {}
        for key in ("host", "name", "model", "serial", "access_code"):
            entry = QLineEdit()
            entry.setObjectName(f"bambu-{key}")
            fields[key] = entry
            layout.addRow(self.text(key), entry)
        if candidate is not None:
            fields["host"].setText(candidate.host)
        fields["serial"].setReadOnly(True)
        fields["access_code"].setEchoMode(QLineEdit.EchoMode.Password)
        hint = QLabel(self.text("network_hint"))
        hint.setWordWrap(True)
        identity: BambuPrinterIdentity | None = None
        identify_button = QPushButton(self.text("network_autofill"))
        identify_button.setObjectName("network-autofill")
        studio_button = QPushButton(self.text("studio_profile_autofill"))
        studio_button.setObjectName("bambu-studio-autofill")
        autofill_buttons = QHBoxLayout()
        autofill_buttons.addWidget(identify_button)
        autofill_buttons.addWidget(studio_button)
        layout.addRow(autofill_buttons)
        layout.addRow(hint)
        buttons = QDialogButtonBox()
        save = buttons.addButton(self.text("test_save"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.text("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        def invalidate() -> None:
            nonlocal identity
            identity = None
            fields["serial"].clear()
            fields["access_code"].clear()

        fields["host"].textEdited.connect(invalidate)

        def populate(result: object) -> None:
            nonlocal identity
            if not dialog.isVisible():
                return
            discovered = cast(BambuPrinterIdentity, result)
            if fields["host"].text().strip() not in ("", discovered.host):
                return
            if QMessageBox.question(self, self.text("enrollment"), self.text(
                "trust", serial=discovered.serial_number,
                fingerprint=discovered.certificate_sha256,
            )) != QMessageBox.StandardButton.Yes:
                return
            if identity is None or (
                identity.host != discovered.host
                or identity.serial_number != discovered.serial_number
                or identity.certificate_sha256 != discovered.certificate_sha256
            ):
                fields["access_code"].clear()
            identity = discovered
            fields["host"].setText(discovered.host)
            fields["name"].setText(discovered.name)
            fields["model"].setText(discovered.model or "")
            fields["serial"].setText(discovered.serial_number)
            hint.setText(self.text("network_filled"))
            identify_button.setEnabled(True)

        def identify() -> None:
            if self.tasks:
                return
            host = fields["host"].text().strip()
            identify_button.setEnabled(False)
            studio_button.setEnabled(False)
            hint.setText(self.text("busy"))
            self.work(
                lambda: identify_bambu_printer(host), populate,
                after_failed=lambda _: hint.setText(self.text("network_identify_failed")),
            )
            if self.tasks:
                self.tasks[-1].finished.connect(restore_autofill_buttons)
            else:
                identify_button.setEnabled(True)
                studio_button.setEnabled(True)

        identify_button.clicked.connect(identify)

        def populate_from_studio(result: object) -> None:
            nonlocal identity
            if not dialog.isVisible():
                return
            if isinstance(result, BambuStudioImportError):
                error_messages = {
                    "printer.studio_invalid_host": "studio_profile_enter_ip",
                    "printer.studio_certificate_unavailable": "studio_profile_certificate_failed",
                    "printer.studio_identity_unavailable": "studio_profile_identity_failed",
                    "printer.studio_settings_unavailable": "studio_profile_settings_missing",
                    "printer.studio_settings_invalid": "studio_profile_settings_invalid",
                    "printer.studio_profile_not_found": "studio_profile_missing",
                    "printer.studio_profile_ambiguous": "studio_profile_ambiguous",
                }
                hint.setText(self.text(error_messages.get(
                    result.code, "studio_profile_failed",
                )))
                return
            profile = cast(BambuStudioProfile, result)
            if fields["host"].text().strip() != profile.host:
                return
            if identity is not None and (
                identity.host != profile.host
                or identity.serial_number != profile.serial_number
                or identity.certificate_sha256 != profile.certificate_sha256
            ):
                invalidate()
                hint.setText(self.text("studio_profile_identity_mismatch"))
                return
            if QMessageBox.question(
                self, self.text("studio_profile_autofill"), self.text(
                    "studio_profile_trust",
                    host=profile.host,
                    serial=profile.serial_number,
                    fingerprint=profile.certificate_sha256,
                ),
            ) != QMessageBox.StandardButton.Yes:
                return
            identity = BambuPrinterIdentity(
                host=profile.host,
                name=profile.model or "Bambu Lab",
                serial_number=profile.serial_number,
                model=profile.model,
                certificate_sha256=profile.certificate_sha256,
                root_certificate_pem=profile.root_certificate_pem,
            )
            fields["host"].setText(profile.host)
            if not fields["name"].text().strip():
                fields["name"].setText(profile.model or "Bambu Lab")
            if profile.model:
                fields["model"].setText(profile.model)
            fields["serial"].setText(profile.serial_number)
            fields["access_code"].setText(profile.access_code.reveal())
            hint.setText(self.text("studio_profile_filled"))

        def import_from_studio() -> None:
            if self.tasks:
                return
            host = fields["host"].text().strip()
            if not host:
                hint.setText(self.text("studio_profile_enter_ip"))
                return
            identify_button.setEnabled(False)
            studio_button.setEnabled(False)
            hint.setText(self.text("studio_profile_importing"))

            def read_profile() -> object:
                try:
                    return import_bambu_studio_profile(host)
                except BambuStudioImportError as error:
                    return error

            self.work(
                read_profile,
                populate_from_studio,
                after_failed=lambda _: hint.setText(self.text("studio_profile_failed")),
            )
            if self.tasks:
                self.tasks[-1].finished.connect(restore_autofill_buttons)
            else:
                identify_button.setEnabled(True)
                studio_button.setEnabled(True)

        studio_button.clicked.connect(import_from_studio)

        def restore_autofill_buttons() -> None:
            if not dialog.isVisible():
                return
            identify_button.setEnabled(True)
            studio_button.setEnabled(True)

        def accept() -> None:
            if self.tasks:
                return
            if (identity is None or identity.host != fields["host"].text().strip()
                or not all(fields[key].text().strip() for key in ("name", "model", "access_code"))):
                hint.setText(self.text("network_required"))
                return
            dialog.accept()

        save.clicked.connect(accept)
        if candidate is not None:
            QTimer.singleShot(0, identify)
        if dialog.exec() != QDialog.DialogCode.Accepted or identity is None:
            fields["access_code"].clear()
            return
        selected = identity
        name, model = fields["name"].text().strip(), fields["model"].text().strip()
        credential = SecretValue(fields["access_code"].text().strip())
        fields["access_code"].clear()

        def connect() -> object:
            certificate = store_bambu_root_certificate(self.backend.paths.config, selected)
            return asyncio.run(configure_bambu_printer(
                engine=self.backend.engine, secret_store=self.container.secrets,
                name=name, model=model, host=selected.host, serial_number=selected.serial_number,
                access_code=credential, ca_certificate=certificate,
                certificate_sha256=selected.certificate_sha256,
            ))

        self.work(connect, lambda _: self.info(self.text("enrolled")))

    def toggle_theme(self) -> None:
        settings = self.settings.model_copy(update={
            "theme": "light" if self.dark else "dark",
        })
        try:
            save_settings(settings, self.backend.paths.config / "settings.json")
        except (OSError, ValueError):
            self.error("settings.invalid")
            return
        self.settings = settings
        self.dark = settings.theme == "dark"
        self.apply_theme()

    def apply_theme(self) -> None:
        background, surface, text, border = (
            ("#161b22", "#202832", "#e6edf3", "#364352") if self.dark else
            ("#f3f5f7", "#ffffff", "#23313e", "#dfe5ea")
        )
        checked_box_icon = (Path(__file__).with_name("assets") / "checkbox-checked.png").as_posix()
        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Segoe UI'; font-size: 13px;
                       color: {text}; background: {background}; }}
            QFrame#top, QFrame#card {{ background: {surface}; border: 1px solid {border};
                                     border-radius: 10px; padding: 10px; }}
            QLabel {{ background: transparent; }}
            QLabel#logo {{ font-size: 21px; font-weight: 700; color: #12b76a; }}
            QLabel#heading {{ font-size: 27px; font-weight: 600; padding-bottom: 6px; }}
            QLabel#metric {{ font-size: 29px; font-weight: 600; }}
            QLabel#notice {{ border-left: 3px solid #12b76a; padding: 12px; }}
            QPushButton {{ background: {surface}; border: 1px solid {border};
                           border-radius: 6px; padding: 5px 12px; }}
            QPushButton:hover {{ border: 1px solid #12b76a; color: #12b76a; }}
            QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border: 2px solid #0d8a59;
            }}
            QPushButton:disabled {{ color: #89949d; }}
            QLineEdit, QComboBox, QTextEdit {{ background: {surface}; padding: 7px;
                           border: 1px solid {border}; border-radius: 6px; }}
            QCheckBox {{ spacing: 8px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #74808b;
                                    border-radius: 3px; background: {surface}; }}
            QCheckBox::indicator:hover {{ border: 1px solid #0d8a59; }}
            QCheckBox::indicator:checked {{ background-color: #12b76a;
                                            border: 1px solid #0d8a59;
                                            image: url("{checked_box_icon}"); }}
            QCheckBox::indicator:disabled {{ background: {background}; border-color: {border}; }}
            QListWidget {{ border: none; background: transparent; outline: none; }}
            QListWidget::item {{ padding: 13px 8px; margin: 3px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: #12b76a; color: white; }}
            QListWidget::item:focus, QTableWidget::item:focus {{
                border: 1px dotted #ffffff;
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QTableWidget {{ background: {surface}; alternate-background-color: {background};
                           border: 1px solid {border}; gridline-color: {border};
                           selection-background-color: #d7f4e5; selection-color: #19382a; }}
            QTableWidget::item:selected {{ background-color: #0d8a59; color: #ffffff; }}
            QHeaderView::section {{ background: {surface}; padding: 10px 6px;
                                   border: none; border-bottom: 1px solid {border}; }}
        """)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tasks or self._monitor_task is not None:
            self._close_when_idle = True
            if self._monitor_task is not None:
                self._monitor_task.stop()
            self.statusBar().showMessage(self.text("busy"))
            event.ignore()
        else:
            if self._local_api is not None:
                self._local_api.stop()
                self._local_api = None
            if self._history_signal_connected:
                self.inventory.itemSelectionChanged.disconnect(self.show_history)
                self._history_signal_connected = False
            event.accept()


def run(paths: AppPaths, settings: AppSettings, capture: Path | None) -> int:
    if capture is not None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    if capture is not None and os.name == "nt":
        # The offscreen platform does not enumerate Windows system fonts.
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setApplicationName("UFM Studio")
    locale = settings.locale
    container = create_container(settings, paths)
    engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
    try:
        migrate_database(engine)
        window = StudioWindow(StudioBackend(engine, paths), container, locale)
        window.show()
        if capture is not None:
            capture.parent.mkdir(parents=True, exist_ok=True)

            def save() -> None:
                if not window.grab().save(str(capture)):
                    app.exit(1)
                else:
                    app.quit()

            QTimer.singleShot(300, save)
        result = app.exec()
        # Destroy native child widgets while QApplication and database are alive.
        # In particular, selection-model signals must not call back during teardown.
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        return result
    finally:
        engine.dispose()
        container.close()
