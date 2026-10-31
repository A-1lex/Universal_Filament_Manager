"""Small local Windows desktop interface for inventory and legacy import."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from ufm.application.inventory import InventoryCommands
from ufm.application.ports.persistence import PersistenceError
from ufm.application.ports.printers import (
    AuthenticationFailed,
    ProviderError,
    TLSVerificationFailed,
)
from ufm.application.ports.secrets import (
    SecretNotFound,
    SecretStore,
    SecretStoreUnavailable,
    SecretValue,
)
from ufm.bootstrap.app_container import create_container
from ufm.bootstrap.settings import AppSettings, SettingsError, load_settings
from ufm.domain.value_objects import EntityId, Mass
from ufm.infrastructure.backup.sqlite_snapshot import BackupInvalid
from ufm.infrastructure.persistence.models.schema import (
    brand,
    connection_profile,
    filament_profile,
    printer,
    spool,
)
from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
from ufm.infrastructure.persistence.sqlite.migrate import MigrationRequired, migrate_database
from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
from ufm.integrations.printers.bambu_discovery import identify_bambu_printer
from ufm.integrations.printers.bambu_studio import (
    BambuPrinterIdentity,
    BambuStudioImportError,
    BambuStudioProfile,
    import_bambu_studio_profile,
    store_bambu_root_certificate,
)
from ufm.integrations.printers.configuration import (
    PrinterConfigurationError,
    configure_bambu_printer,
    configure_local_printer,
    ensure_local_device,
    probe_configured_printer,
    remove_configured_printer,
)
from ufm.integrations.printers.discovery import (
    PrinterCandidate,
    PrinterDiscoveryError,
    discover_printers,
    primary_local_network,
)
from ufm.integrations.spoolman.importer import (
    SpoolmanImportPreview,
    SpoolmanImportRejected,
    default_spoolman_import_source_key,
    import_spoolman_database,
    new_spoolman_source_key,
    preview_spoolman_database,
    spoolman_import_source_label,
)
from ufm.platform.common.paths import AppPaths
from ufm.ui.i18n import TranslationError, Translator


class DesktopApp:
    def __init__(
        self,
        *,
        root: Any,
        tk_module: Any,
        ttk: Any,
        filedialog: Any,
        messagebox: Any,
        translator: Translator,
        paths: AppPaths,
        engine: Engine,
        secrets: SecretStore,
    ) -> None:
        self.root = root
        self.tk = tk_module
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.translator = translator
        self.paths = paths
        self.engine = engine
        self.secrets = secrets
        self.inventory_commands = InventoryCommands(
            lambda: SQLiteUnitOfWork(self.engine),
        )
        self._inventory_rows: list[Any] = []
        self._printer_action_busy = False
        self.tree: Any
        self.printer_tree: Any
        self.status: Any
        self.search_var: Any
        self._build()
        self.refresh()

    def _text(self, key: str) -> str:
        return self.translator.text(key)

    def _build(self) -> None:
        self.root.title(self._text("desktop.title"))
        self.root.geometry("920x720")
        self.root.minsize(720, 540)

        outer = self.ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        self.ttk.Label(
            outer, text=self._text("desktop.heading"), font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")
        self.ttk.Label(
            outer, text=self._text("desktop.local_data") + " " + str(self.paths.data),
            wraplength=880, style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 16))

        actions = self.ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 14))
        self.ttk.Button(
            actions, text=self._text("desktop.refresh"), command=self.refresh,
        ).pack(side="left")
        self.ttk.Button(
            actions, text=self._text("desktop.import"), command=self.import_spoolman,
        ).pack(side="left", padx=(8, 0))

        notebook = self.ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        inventory_page = self.ttk.Frame(notebook, padding=14)
        printers_page = self.ttk.Frame(notebook, padding=14)
        notebook.add(inventory_page, text=self._text("desktop.inventory_tab"))
        notebook.add(printers_page, text=self._text("desktop.printers_tab"))

        metrics = self.ttk.Frame(inventory_page)
        metrics.pack(fill="x", pady=(0, 12))
        self.metric_spools = self._metric(metrics, "desktop.metric_spools", 0)
        self.metric_stock = self._metric(metrics, "desktop.metric_stock", 1)
        self.metric_low = self._metric(metrics, "desktop.metric_low_stock", 2)

        search_row = self.ttk.Frame(inventory_page)
        search_row.pack(fill="x", pady=(0, 8))
        self.ttk.Label(search_row, text=self._text("desktop.search")).pack(side="left")
        self.search_var = self.tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._render_inventory())
        self.ttk.Entry(search_row, textvariable=self.search_var, width=38).pack(
            side="left", padx=(8, 0),
        )

        columns = ("material", "remaining", "lifecycle")
        self.tree = self.ttk.Treeview(
            inventory_page, columns=columns, show="headings", height=15,
            selectmode="browse",
        )
        for column, key, width in (
            ("material", "desktop.material", 430),
            ("remaining", "desktop.remaining", 180),
            ("lifecycle", "desktop.lifecycle", 160),
        ):
            self.tree.heading(column, text=self._text(key))
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        inventory_actions = self.ttk.Frame(inventory_page)
        inventory_actions.pack(fill="x", pady=(10, 0))
        self.ttk.Button(
            inventory_actions, text=self._text("desktop.stock_action"),
            command=self.change_stock,
        ).pack(side="left")
        self.ttk.Button(
            inventory_actions, text=self._text("desktop.add_spool"),
            command=self.add_spool,
        ).pack(side="left", padx=(8, 0))
        self.ttk.Button(
            inventory_actions, text=self._text("desktop.ledger_history"),
            command=self.show_history,
        ).pack(side="left", padx=(8, 0))

        self.ttk.Label(
            printers_page, text=self._text("desktop.printers_heading"),
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 5))
        self.ttk.Label(
            printers_page, text=self._text("desktop.printer_monitoring_notice"),
            wraplength=820, style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 12))
        printer_columns = ("name", "manufacturer", "model", "provider", "endpoint")
        printer_table = self.ttk.Frame(printers_page)
        printer_table.pack(fill="both", expand=True)
        self.printer_tree = self.ttk.Treeview(
            printer_table, columns=printer_columns, show="headings", height=12,
            selectmode="browse",
        )
        for column, key, width in (
            ("name", "desktop.printer_name", 180),
            ("manufacturer", "desktop.manufacturer", 160),
            ("model", "desktop.model", 140),
            ("provider", "desktop.provider", 140),
            ("endpoint", "desktop.endpoint", 260),
        ):
            self.printer_tree.heading(column, text=self._text(key))
            self.printer_tree.column(
                column, width=width, anchor="w",
                stretch=column in {"name", "endpoint"},
            )
        printer_scrollbar = self.ttk.Scrollbar(
            printer_table, orient="vertical", command=self.printer_tree.yview,
        )
        printer_horizontal_scrollbar = self.ttk.Scrollbar(
            printer_table, orient="horizontal", command=self.printer_tree.xview,
        )
        self.printer_tree.configure(
            yscrollcommand=printer_scrollbar.set,
            xscrollcommand=printer_horizontal_scrollbar.set,
        )
        self.printer_tree.grid(row=0, column=0, sticky="nsew")
        printer_scrollbar.grid(row=0, column=1, sticky="ns")
        printer_horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        printer_table.columnconfigure(0, weight=1)
        printer_table.rowconfigure(0, weight=1)
        printer_actions = self.ttk.Frame(printers_page)
        printer_actions.pack(fill="x", pady=(10, 0))
        self.ttk.Button(
            printer_actions, text=self._text("desktop.add_printer"),
            command=self.add_printer,
        ).pack(side="left")
        self.printer_discovery_button = self.ttk.Button(
            printer_actions,
            text=self._text("desktop.discover_printers"),
            command=self.discover_local_printers,
        )
        self.printer_discovery_button.pack(side="left", padx=(8, 0))
        self.printer_status_button = self.ttk.Button(
            printer_actions,
            text=self._text("desktop.check_printer_status"),
            command=self.check_printer_status,
        )
        self.printer_status_button.pack(side="right")
        self.printer_remove_button = self.ttk.Button(
            printer_actions,
            text=self._text("desktop.remove_printer"),
            command=self.remove_selected_printer,
        )
        self.printer_remove_button.pack(side="right", padx=(8, 0))
        self.printer_tree.bind("<<TreeviewSelect>>", self._update_printer_actions)
        self.printer_tree.bind("<Double-1>", lambda _: self.check_printer_status())
        self.printer_tree.bind("<Delete>", lambda _: self.remove_selected_printer())

        self.status = self.ttk.Label(outer, text="", anchor="w")
        self.status.pack(fill="x", pady=(10, 0))

    def _metric(self, parent: Any, label_key: str, column: int) -> Any:
        card = self.ttk.LabelFrame(parent, text=self._text(label_key), padding=(12, 8))
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        parent.columnconfigure(column, weight=1)
        value = self.ttk.Label(card, text="—", font=("Segoe UI", 16, "bold"))
        value.pack(anchor="w")
        return value

    def refresh(self) -> None:
        try:
            with self.engine.connect() as connection:
                inventory_rows = connection.execute(
                    select(
                        spool.c.id,
                        spool.c.display_name,
                        filament_profile.c.name,
                        filament_profile.c.material_type,
                        spool.c.effective_remaining_mg,
                        spool.c.lifecycle,
                        spool.c.low_threshold_mg,
                    ).join(
                        filament_profile,
                        filament_profile.c.id == spool.c.filament_profile_id,
                    ).order_by(spool.c.display_name, spool.c.id)
                ).all()
                configured_printers = connection.execute(
                    select(
                        printer.c.name, printer.c.manufacturer, printer.c.model,
                        printer.c.id,
                        connection_profile.c.provider_type,
                        connection_profile.c.host, connection_profile.c.port,
                    ).join(
                        connection_profile,
                        connection_profile.c.printer_id == printer.c.id,
                    ).order_by(printer.c.name, printer.c.id)
                ).all()
        except SQLAlchemyError:
            self.messagebox.showerror(
                self._text("desktop.error_title"), self._text("desktop.database_error"),
                parent=self.root,
            )
            return

        self._inventory_rows = list(inventory_rows)
        known = [row.effective_remaining_mg for row in inventory_rows
                 if row.effective_remaining_mg is not None]
        self.metric_spools.configure(text=str(len(inventory_rows)))
        self.metric_stock.configure(
            text=self.translator.text(
                "desktop.grams",
                amount=f"{sum(item.grams for item in known):.3f}",
            )
        )
        low_count = sum(
            row.effective_remaining_mg is not None
            and row.low_threshold_mg is not None
            and row.effective_remaining_mg <= row.low_threshold_mg
            for row in inventory_rows
        )
        self.metric_low.configure(text=str(low_count))
        self._render_inventory()
        self.status.configure(
            text=self.translator.text(
                "desktop.inventory_summary",
                total=len(inventory_rows),
                known=len(known),
                unknown=len(inventory_rows) - len(known),
            ),
        )
        for item in self.printer_tree.get_children():
            self.printer_tree.delete(item)
        for row in configured_printers:
            host = f"[{row.host}]" if row.host is not None and ":" in row.host else row.host
            endpoint = host if row.port in (None, 80) else f"{host}:{row.port}"
            provider_name = {
                "OCTOPRINT": "OctoPrint",
                "MOONRAKER": "Moonraker",
                "BAMBU_LAN": "Bambu Lab (LAN)",
            }.get(row.provider_type, row.provider_type)
            self.printer_tree.insert(
                "", "end",
                values=(row.name, row.manufacturer or "", row.model or "",
                        provider_name, endpoint),
                iid=str(row.id),
            )
        self._update_printer_actions()

    def _render_inventory(self) -> None:
        if not hasattr(self, "tree"):
            return
        query = self.search_var.get().strip().casefold() if hasattr(self, "search_var") else ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self._inventory_rows:
            label = f"{row.display_name} — {row.name} ({row.material_type})"
            if query and query not in label.casefold():
                continue
            remaining = (
                self._text("desktop.unknown")
                if row.effective_remaining_mg is None
                else self.translator.text(
                    "desktop.grams",
                    amount=f"{row.effective_remaining_mg.grams:.3f}",
                )
            )
            lifecycle = self._text(f"desktop.lifecycle_{row.lifecycle}")
            self.tree.insert(
                "", "end", iid=str(row.id),
                values=(label, remaining, lifecycle),
            )

    def _selected_spool(self) -> EntityId | None:
        selected = self.tree.selection()
        return None if not selected else EntityId.parse(selected[0])

    def change_stock(self) -> None:
        spool_id = self._selected_spool()
        if spool_id is None:
            self.messagebox.showwarning(
                self._text("desktop.stock_action"),
                self._text("desktop.select_spool_first"), parent=self.root,
            )
            return
        try:
            availability = self.inventory_commands.availability(spool_id)
        except (PersistenceError, SQLAlchemyError, ValueError) as error:
            self._show_inventory_error(error)
            return
        opening_required = availability.effective is None
        window = self.tk.Toplevel(self.root)
        window.title(self._text("desktop.stock_action"))
        window.transient(self.root)
        window.grab_set()
        form = self.ttk.Frame(window, padding=18)
        form.pack(fill="both", expand=True)
        self.ttk.Label(
            form, text=self.translator.text(
                "desktop.stock_target", spool=self._spool_label(spool_id),
            ),
            font=("Segoe UI", 12, "bold"), wraplength=460,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.ttk.Label(form, text=self._text("desktop.stock_action_type")).grid(
            row=1, column=0, sticky="w", pady=5,
        )
        mode_options = (
            ("opening", "desktop.stock_opening"),
        ) if opening_required else (
            ("add", "desktop.stock_add"),
            ("deduct", "desktop.stock_deduct"),
        )
        mode_by_label = {self._text(label): mode for mode, label in mode_options}
        mode = self.ttk.Combobox(
            form, state="readonly", values=tuple(mode_by_label),
        )
        mode.current(0)
        mode.grid(row=1, column=1, sticky="ew", pady=5)
        self.ttk.Label(form, text=self._text("desktop.amount_grams")).grid(
            row=2, column=0, sticky="w", pady=5,
        )
        amount = self.ttk.Entry(form, width=22)
        amount.grid(row=2, column=1, sticky="ew", pady=5)
        self.ttk.Label(
            form,
            text=(self._text("desktop.opening_stock_notice") if opening_required
                  else self._text("desktop.manual_stock_notice")),
            wraplength=460,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 12))
        form.columnconfigure(1, weight=1)

        def save() -> None:
            try:
                mass = Mass.from_grams(amount.get().strip())
                if mass.milligrams <= 0:
                    raise ValueError("desktop.amount_must_be_positive")
                selected_mode = mode_by_label[mode.get()]
                if selected_mode == "deduct" and (
                    availability.available is None or mass > availability.available
                ):
                    raise ValueError("desktop.stock_deduction_exceeds_available")
            except (ValueError, TypeError) as error:
                self._show_inventory_error(error, parent=window)
                return
            summary_key = {
                "opening": "desktop.confirm_opening",
                "add": "desktop.confirm_add",
                "deduct": "desktop.confirm_deduct",
            }[selected_mode]
            if not self.messagebox.askyesno(
                self._text("desktop.stock_action"),
                self.translator.text(
                    summary_key,
                    spool=self._spool_label(spool_id),
                    amount=f"{mass.grams:.3f}",
                ),
                parent=window,
            ):
                return
            try:
                actor = ensure_local_device(self.engine)
                key = f"desktop-stock-{uuid4()}"
                if selected_mode == "opening":
                    self.inventory_commands.establish_opening_stock(
                        spool_id=spool_id, amount=mass, command_key=key,
                        actor_device_id=actor,
                    )
                elif selected_mode == "deduct":
                    self.inventory_commands.deduct_manual(
                        spool_id=spool_id, amount=mass, command_key=key,
                        actor_device_id=actor,
                    )
                else:
                    self.inventory_commands.adjust(
                        spool_id=spool_id, delta=mass, command_key=key,
                        actor_device_id=actor,
                    )
            except (PersistenceError, SQLAlchemyError, ValueError) as error:
                self._show_inventory_error(error, parent=window)
                return
            window.destroy()
            self.refresh()
            self.messagebox.showinfo(
                self._text("desktop.stock_saved"),
                self._text("desktop.stock_saved_result"), parent=self.root,
            )

        self.ttk.Button(
            form, text=self._text("desktop.save"), command=save,
        ).grid(row=4, column=1, sticky="e")
        amount.focus_set()

    def add_spool(self) -> None:
        try:
            with self.engine.connect() as connection:
                profiles = connection.execute(
                    select(
                        filament_profile.c.id,
                        filament_profile.c.name,
                        filament_profile.c.material_type,
                        brand.c.name.label("brand_name"),
                    ).select_from(
                        filament_profile.outerjoin(
                            brand, brand.c.id == filament_profile.c.brand_id,
                        )
                    ).order_by(brand.c.name, filament_profile.c.name)
                ).all()
        except SQLAlchemyError as error:
            self._show_inventory_error(error)
            return
        if not profiles:
            self.messagebox.showinfo(
                self._text("desktop.add_spool"),
                self._text("desktop.no_material_profiles"),
                parent=self.root,
            )
            return
        window = self.tk.Toplevel(self.root)
        window.title(self._text("desktop.add_spool"))
        window.transient(self.root)
        window.grab_set()
        form = self.ttk.Frame(window, padding=18)
        form.pack(fill="both", expand=True)
        self.ttk.Label(form, text=self._text("desktop.spool_name")).grid(
            row=0, column=0, sticky="w", pady=5,
        )
        name = self.ttk.Entry(form, width=38)
        name.grid(row=0, column=1, sticky="ew", pady=5)
        self.ttk.Label(form, text=self._text("desktop.material_profile")).grid(
            row=1, column=0, sticky="w", pady=5,
        )
        labels: list[str] = []
        profile_ids: dict[str, EntityId] = {}
        for profile in profiles:
            prefix = f"{profile.brand_name} · " if profile.brand_name else ""
            label = f"{prefix}{profile.name} ({profile.material_type})"
            candidate = label
            suffix = 2
            while candidate in profile_ids:
                candidate = f"{label} #{suffix}"
                suffix += 1
            labels.append(candidate)
            profile_ids[candidate] = profile.id
        profile_box = self.ttk.Combobox(
            form, state="readonly", values=tuple(labels), width=36,
        )
        profile_box.current(0)
        profile_box.grid(row=1, column=1, sticky="ew", pady=5)
        self.ttk.Label(form, text=self._text("desktop.opening_stock_optional")).grid(
            row=2, column=0, sticky="w", pady=5,
        )
        opening = self.ttk.Entry(form, width=20)
        opening.grid(row=2, column=1, sticky="ew", pady=5)
        self.ttk.Label(
            form, text=self._text("desktop.new_spool_profile_notice"),
            wraplength=460,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 12))
        form.columnconfigure(1, weight=1)

        def save() -> None:
            spool_name = name.get().strip()
            if not spool_name:
                self._show_inventory_error(
                    ValueError("spool.name_invalid"), parent=window,
                )
                return
            try:
                initial_mass = (
                    None if not opening.get().strip()
                    else Mass.from_grams(opening.get().strip())
                )
                if initial_mass is not None and initial_mass.milligrams < 0:
                    raise ValueError("inventory.opening_negative")
            except (ValueError, TypeError) as error:
                self._show_inventory_error(error, parent=window)
                return
            if not self.messagebox.askyesno(
                self._text("desktop.add_spool"),
                self.translator.text(
                    "desktop.confirm_new_spool",
                    spool=spool_name,
                    profile=profile_box.get(),
                ),
                parent=window,
            ):
                return
            spool_created = False
            try:
                actor = ensure_local_device(self.engine)
                spool_id = EntityId.new()
                self.inventory_commands.create_spool(
                    spool_id=spool_id,
                    filament_profile_id=profile_ids[profile_box.get()],
                    display_name=spool_name,
                    actor_device_id=actor,
                    command_key=f"desktop-create-spool-{uuid4()}",
                )
                spool_created = True
                if initial_mass is not None:
                    self.inventory_commands.establish_opening_stock(
                        spool_id=spool_id,
                        amount=initial_mass,
                        actor_device_id=actor,
                        command_key=f"desktop-opening-stock-{uuid4()}",
                    )
            except (PersistenceError, SQLAlchemyError, ValueError) as error:
                if spool_created:
                    self.refresh()
                    self.messagebox.showerror(
                        self._text("desktop.error_title"),
                        f"{self._text('desktop.spool_created_opening_failed')}\n\n{error}",
                        parent=window,
                    )
                else:
                    self._show_inventory_error(error, parent=window)
                return
            window.destroy()
            self.refresh()
            self.messagebox.showinfo(
                self._text("desktop.spool_created"),
                self._text("desktop.spool_created_result"),
                parent=self.root,
            )

        self.ttk.Button(
            form, text=self._text("desktop.save"), command=save,
        ).grid(row=4, column=1, sticky="e")
        name.focus_set()

    def show_history(self) -> None:
        spool_id = self._selected_spool()
        if spool_id is None:
            self.messagebox.showwarning(
                self._text("desktop.ledger_history"),
                self._text("desktop.select_spool_first"), parent=self.root,
            )
            return
        try:
            history = self.inventory_commands.history(spool_id)
        except (PersistenceError, SQLAlchemyError, ValueError) as error:
            self._show_inventory_error(error)
            return
        window = self.tk.Toplevel(self.root)
        window.title(self._text("desktop.ledger_history"))
        window.geometry("780x360")
        frame = self.ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        self.ttk.Label(
            frame, text=self._spool_label(spool_id),
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        columns = ("date", "type", "delta", "balance")
        table = self.ttk.Treeview(
            frame, columns=columns, show="headings", height=12,
        )
        for column, key, width in (
            ("date", "desktop.ledger_date", 170),
            ("type", "desktop.ledger_type", 240),
            ("delta", "desktop.ledger_change", 140),
            ("balance", "desktop.ledger_balance", 140),
        ):
            table.heading(column, text=self._text(key))
            table.column(column, width=width, anchor="w")
        for entry in history:
            date_label = entry.created_at.value.astimezone().strftime("%Y-%m-%d %H:%M")
            type_key = f"desktop.transaction_{entry.transaction_type.value}"
            type_label = self._text(type_key)
            table.insert(
                "", "end",
                values=(
                    date_label, type_label,
                    self.translator.text("desktop.grams", amount=f"{entry.delta.grams:+.3f}"),
                    self.translator.text(
                        "desktop.grams", amount=f"{entry.new_effective.grams:.3f}",
                    ),
                ),
            )
        table.pack(fill="both", expand=True)

    def _spool_label(self, spool_id: EntityId) -> str:
        for row in self._inventory_rows:
            if row.id == spool_id:
                return f"{row.display_name} — {row.name} ({row.material_type})"
        return str(spool_id)

    def _update_printer_actions(self, *_: object) -> None:
        selected = bool(self.printer_tree.selection())
        state = "normal" if selected and not self._printer_action_busy else "disabled"
        self.printer_status_button.configure(state=state)
        self.printer_remove_button.configure(state=state)

    def remove_selected_printer(self) -> None:
        selected = self.printer_tree.selection()
        if not selected:
            self.messagebox.showwarning(
                self._text("desktop.remove_printer"),
                self._text("desktop.select_printer_first"),
                parent=self.root,
            )
            return
        item = self.printer_tree.item(selected[0])
        values = item.get("values", ())
        name = values[0] if values else ""
        if not self.messagebox.askyesno(
            self._text("desktop.remove_printer"),
            self.translator.text("desktop.remove_printer_confirmation", name=name),
            parent=self.root,
        ):
            return

        self._printer_action_busy = True
        self._update_printer_actions()
        try:
            removed_name = remove_configured_printer(
                engine=self.engine,
                secret_store=self.secrets,
                printer_id=EntityId.parse(selected[0]),
            )
        except SecretNotFound:
            self.messagebox.showerror(
                self._text("desktop.error_title"),
                self._text("desktop.printer_remove_failed"),
                parent=self.root,
            )
            return
        except SecretStoreUnavailable:
            self.messagebox.showerror(
                self._text("desktop.error_title"),
                self._text("secrets.unavailable"),
                parent=self.root,
            )
            return
        except (PrinterConfigurationError, PersistenceError, OSError, ValueError, SQLAlchemyError):
            self.messagebox.showerror(
                self._text("desktop.error_title"),
                self._text("desktop.printer_remove_failed"),
                parent=self.root,
            )
            return
        finally:
            self._printer_action_busy = False
            self._update_printer_actions()

        self.refresh()
        self.messagebox.showinfo(
            self._text("desktop.remove_printer"),
            self.translator.text("desktop.printer_removed_result", name=removed_name),
            parent=self.root,
        )

    def _show_inventory_error(self, error: Exception, *, parent: Any = None) -> None:
        error_messages = {
            "inventory.amount_must_be_positive": "desktop.amount_must_be_positive",
            "inventory.manual_deduction_invalid": "desktop.amount_must_be_positive",
            "inventory.manual_deduction_exceeds_available":
                "desktop.stock_deduction_exceeds_available",
            "inventory.opening_required": "desktop.opening_stock_required",
            "inventory.opening_already_established": "desktop.opening_stock_already_set",
            "inventory.opening_negative": "desktop.opening_stock_cannot_be_negative",
            "spool.archived_read_only": "desktop.archived_spool_read_only",
            "spool.name_invalid": "desktop.spool_name_required",
        }
        key = error_messages.get(str(error))
        message = self._text("desktop.inventory_operation_failed")
        if key is not None:
            message = self._text(key)
        elif str(error):
            message += f"\n\n{error}"
        self.messagebox.showerror(
            self._text("desktop.error_title"), message,
            parent=self.root if parent is None else parent,
        )

    def check_printer_status(self) -> None:
        selected = self.printer_tree.selection()
        if not selected:
            self.messagebox.showwarning(
                self._text("desktop.check_printer_status"),
                self._text("desktop.select_printer_first"),
                parent=self.root,
            )
            return
        printer_id = EntityId.parse(selected[0])
        self._printer_action_busy = True
        self.printer_status_button.configure(text=self._text("desktop.checking_bambu"))
        self._update_printer_actions()

        def complete(result: Any | None, error: Exception | None) -> None:
            self._printer_action_busy = False
            self.printer_status_button.configure(text=self._text("desktop.check_printer_status"))
            self._update_printer_actions()
            if error is not None:
                if isinstance(error, TLSVerificationFailed):
                    message = self._text("desktop.printer_tls_failed")
                elif isinstance(error, AuthenticationFailed):
                    message = self._text("desktop.printer_auth_failed")
                elif isinstance(error, SecretStoreUnavailable):
                    message = self._text("secrets.unavailable")
                elif isinstance(error, ProviderError) and error.code == "provider.unavailable":
                    message = self._text("desktop.printer_unavailable")
                elif isinstance(error, ProviderError) and error.code == "provider.invalid_observation":
                    message = self._text("desktop.printer_invalid_observation")
                elif isinstance(error, ProviderError):
                    message = self._text("desktop.printer_status_failed")
                else:
                    message = self._text("desktop.printer_status_failed")
                self.messagebox.showerror(
                    self._text("desktop.error_title"), message, parent=self.root,
                )
                return
            if result is None:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.printer_status_failed"), parent=self.root,
                )
                return
            snapshot = result.status
            job = result.current_job
            if job.job is None:
                state = (
                    self._text("desktop.job_IDLE")
                    if job.availability.value == "KNOWN"
                    else self._text("desktop.unknown")
                )
            else:
                state = self._text(f"desktop.job_{job.job.status.value}")
            progress_value = (
                self._text("desktop.unknown")
                if job.job is None or job.job.progress_bp is None
                else f"{job.job.progress_bp / 100:.1f}%"
            )
            nozzle = (
                self._text("desktop.unknown")
                if snapshot.nozzle_temperature_c.value is None
                else snapshot.nozzle_temperature_c.value.canonical()
            )
            bed = (
                self._text("desktop.unknown")
                if snapshot.bed_temperature_c.value is None
                else snapshot.bed_temperature_c.value.canonical()
            )
            feed_lines = [
                f"{self._text('desktop.feed_system')} {system.provider_system_key}: "
                f"{len(system.slots)}"
                for system in snapshot.feed_systems
            ]
            message = self.translator.text(
                "desktop.printer_status_result",
                state=state,
                progress=progress_value,
                layer=(
                    self._text("desktop.unknown")
                    if snapshot.current_layer.value is None
                    else str(snapshot.current_layer.value)
                ),
                nozzle=nozzle,
                bed=bed,
                feeds=(
                    "\n".join(feed_lines)
                    if feed_lines else self._text("desktop.feed_systems_unknown")
                ),
            )
            self.messagebox.showinfo(
                self._text("desktop.check_printer_status"), message, parent=self.root,
            )

        def worker() -> None:
            try:
                result = asyncio.run(probe_configured_printer(
                    engine=self.engine,
                    secret_store=self.secrets,
                    printer_id=printer_id,
                ))
            except (
                AuthenticationFailed, ProviderError, SecretNotFound,
                SecretStoreUnavailable, PrinterConfigurationError,
                PersistenceError, OSError, ValueError, SQLAlchemyError,
            ) as error:
                self.root.after(0, lambda error=error: complete(None, error))
                return
            self.root.after(0, lambda result=result: complete(result, None))

        threading.Thread(target=worker, name="ufm-printer-status", daemon=True).start()

    def discover_local_printers(self) -> None:
        try:
            network = primary_local_network()
        except PrinterDiscoveryError as error:
            self.messagebox.showerror(
                self._text("desktop.error_title"),
                self._discovery_error_message(error),
                parent=self.root,
            )
            return
        if not self.messagebox.askyesno(
            self._text("desktop.discover_printers"),
            self.translator.text(
                "desktop.discovery_confirmation",
                network=str(network),
            ),
            parent=self.root,
        ):
            return

        self.printer_discovery_button.configure(
            state="disabled", text=self._text("desktop.discovering_printers"),
        )

        def complete(
            candidates: tuple[PrinterCandidate, ...] | None,
            error: Exception | None,
        ) -> None:
            self.printer_discovery_button.configure(
                state="normal", text=self._text("desktop.discover_printers"),
            )
            if error is not None:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._discovery_error_message(error),
                    parent=self.root,
                )
                return
            if not candidates:
                self.messagebox.showinfo(
                    self._text("desktop.discover_printers"),
                    self._text("desktop.discovery_no_printers"),
                    parent=self.root,
                )
                return
            self._show_printer_candidates(candidates)

        def worker() -> None:
            try:
                result = discover_printers(network)
            except (PrinterDiscoveryError, OSError, ValueError) as error:
                self.root.after(0, lambda error=error: complete(None, error))
                return
            self.root.after(0, lambda result=result: complete(result, None))

        threading.Thread(target=worker, name="ufm-printer-discovery", daemon=True).start()

    def _discovery_error_message(self, error: Exception) -> str:
        if isinstance(error, PrinterDiscoveryError):
            return self._text(str(error))
        return self._text("desktop.discovery_failed")

    def _show_printer_candidates(
        self,
        candidates: tuple[PrinterCandidate, ...],
    ) -> None:
        window = self.tk.Toplevel(self.root)
        window.title(self._text("desktop.discovery_results"))
        window.transient(self.root)
        window.grab_set()
        self.ttk.Label(
            window, text=self._text("desktop.discovery_results_notice"),
            wraplength=620, padding=12,
        ).pack(anchor="w")
        tree = self.ttk.Treeview(
            window, columns=("provider", "host", "port", "confidence"),
            show="headings", height=min(8, len(candidates)), selectmode="browse",
        )
        for column, key, width in (
            ("provider", "desktop.provider", 180),
            ("host", "desktop.endpoint", 180),
            ("port", "desktop.discovery_port", 80),
            ("confidence", "desktop.discovery_confidence", 180),
        ):
            tree.heading(column, text=self._text(key))
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=12)
        candidate_by_id: dict[str, PrinterCandidate] = {}
        provider_names = {
            "OCTOPRINT": "OctoPrint",
            "MOONRAKER": "Moonraker",
            "BAMBU_LAN": "Bambu Lab (possible)",
        }
        for index, candidate in enumerate(candidates):
            item_id = str(index)
            candidate_by_id[item_id] = candidate
            provider_name = provider_names[candidate.provider_type]
            if (
                candidate.confidence == "unverified"
                and candidate.provider_type != "BAMBU_LAN"
            ):
                provider_name += " (?)"
            tree.insert(
                "", "end", iid=item_id,
                values=(
                    provider_name,
                    candidate.host,
                    candidate.port,
                    self._text(
                        "desktop.discovery_unverified"
                        if candidate.confidence == "unverified"
                        else "desktop.discovery_identified"
                    ),
                ),
            )
        actions = self.ttk.Frame(window, padding=12)
        actions.pack(fill="x")

        def configure_selected() -> None:
            selected = tree.selection()
            if not selected:
                self.messagebox.showwarning(
                    self._text("desktop.discovery_results"),
                    self._text("desktop.discovery_select_printer"),
                    parent=window,
                )
                return
            candidate = candidate_by_id[selected[0]]
            window.destroy()
            self.add_printer(candidate)

        self.ttk.Button(
            actions, text=self._text("desktop.discovery_configure"),
            command=configure_selected,
        ).pack(side="right")

    def add_printer(self, candidate: PrinterCandidate | None = None) -> None:
        window = self.tk.Toplevel(self.root)
        window.title(self._text("desktop.add_printer"))
        window.transient(self.root)
        window.grab_set()
        form = self.ttk.Frame(window, padding=16)
        form.pack(fill="both", expand=True)
        fields: dict[str, Any] = {}
        provider_labels = {
            "OctoPrint": "OCTOPRINT",
            "Moonraker": "MOONRAKER",
            "Bambu Lab (LAN)": "BAMBU_LAN",
        }
        field_rows = (
            ("name", "desktop.printer_name"),
            ("manufacturer", "desktop.manufacturer"),
            ("model", "desktop.model"),
            ("endpoint", "desktop.endpoint"),
        )
        field_labels: dict[str, Any] = {}
        for row_index, (key, label_key) in enumerate(field_rows):
            label = self.ttk.Label(form, text=self._text(label_key))
            label.grid(
                row=row_index, column=0, sticky="w", pady=4,
            )
            entry = self.ttk.Entry(form, width=44)
            entry.grid(row=row_index, column=1, sticky="ew", pady=4)
            fields[key] = entry
            field_labels[key] = label
        provider_row = len(fields)
        self.ttk.Label(
            form, text=self._text("desktop.provider"),
        ).grid(row=provider_row, column=0, sticky="w", pady=4)
        provider = self.ttk.Combobox(
            form, state="readonly", values=tuple(provider_labels),
        )
        provider.current(0)
        provider.grid(row=provider_row, column=1, sticky="ew", pady=4)
        credential_label = self.ttk.Label(form, text=self._text("desktop.api_token"))
        credential_label.grid(row=provider_row + 1, column=0, sticky="w", pady=4)
        token = self.ttk.Entry(form, width=44, show="*")
        token.grid(row=provider_row + 1, column=1, sticky="ew", pady=4)

        def toggle_secret_visibility() -> None:
            visible = bool(show_secret.get())
            token.configure(show="" if visible else "*")
            show_secret_button.configure(
                text=self._text(
                    "desktop.hide_secret" if visible else "desktop.show_secret",
                ),
            )

        show_secret = self.tk.BooleanVar(value=False)
        show_secret_button = self.ttk.Button(
            form,
            text=self._text("desktop.show_secret"),
            command=toggle_secret_visibility,
        )
        show_secret_button.grid(
            row=provider_row + 1, column=2, padx=(6, 0), pady=4,
        )
        serial_row = provider_row + 2
        serial_label = self.ttk.Label(form, text=self._text("desktop.serial_number"))
        serial_entry = self.ttk.Entry(form, width=44)
        serial_label.grid(row=serial_row, column=0, sticky="w", pady=4)
        serial_entry.grid(row=serial_row, column=1, sticky="ew", pady=4)
        certificate_row = serial_row + 1
        certificate_label = self.ttk.Label(form, text=self._text("desktop.ca_certificate"))
        certificate_entry = self.ttk.Entry(form, width=36)
        certificate_entry.grid(row=certificate_row, column=1, sticky="ew", pady=4)
        certificate_label.grid(row=certificate_row, column=0, sticky="w", pady=4)
        certificate_button = self.ttk.Button(
            form, text=self._text("desktop.choose_certificate"),
            command=lambda: self._choose_certificate(certificate_entry),
        )
        certificate_button.grid(row=certificate_row, column=2, padx=(6, 0), pady=4)
        auto_fill_button = self.ttk.Button(
            form,
            text=self._text("desktop.bambu_studio_import"),
        )
        auto_fill_button.grid(
            row=certificate_row + 1, column=1, sticky="w", pady=(4, 0),
        )
        network_fill_button = self.ttk.Button(form, text=self._text("desktop.network_autofill"))
        network_fill_button.grid(row=certificate_row + 2, column=1, sticky="w", pady=(4, 0))
        notice = self.ttk.Label(form, wraplength=480)
        notice.grid(
            row=certificate_row + 3, column=0, columnspan=3,
            sticky="w", pady=(8, 12),
        )
        certificate_sha256: str | None = None

        def update_provider_fields(*_: object) -> None:
            bambu = provider_labels.get(provider.get()) == "BAMBU_LAN"
            for widget in (serial_label, serial_entry, certificate_label,
                           certificate_entry, certificate_button, auto_fill_button,
                           network_fill_button):
                if bambu:
                    widget.grid()
                else:
                    widget.grid_remove()
            field_labels["endpoint"].configure(
                text=self._text(
                    "desktop.bambu_ip" if bambu else "desktop.endpoint",
                ),
            )
            credential_label.configure(
                text=self._text(
                    "desktop.bambu_access_code" if bambu else "desktop.api_token",
                ),
            )
            if bambu:
                fields["manufacturer"].delete(0, "end")
                fields["manufacturer"].insert(0, "Bambu Lab")
                notice.configure(text=self._text("desktop.bambu_lan_notice"))
            else:
                notice.configure(text=self._text("desktop.local_endpoint_notice"))

        provider.bind("<<ComboboxSelected>>", update_provider_fields)
        import_busy = False

        def finish_bambu_import(
            profile: BambuStudioProfile | None,
            error: BambuStudioImportError | None,
        ) -> None:
            nonlocal import_busy, certificate_sha256
            import_busy = False
            auto_fill_button.configure(
                state="normal", text=self._text("desktop.bambu_studio_import"),
            )
            if error is not None:
                error_keys = {
                    "printer.studio_invalid_host": "desktop.bambu_studio_invalid_host",
                    "printer.studio_certificate_unavailable": "desktop.bambu_studio_certificate_failed",
                    "printer.studio_identity_unavailable": "desktop.bambu_studio_identity_failed",
                    "printer.studio_settings_unavailable": "desktop.bambu_studio_settings_missing",
                    "printer.studio_settings_invalid": "desktop.bambu_studio_settings_invalid",
                    "printer.studio_profile_not_found": "desktop.bambu_studio_profile_missing",
                    "printer.studio_profile_ambiguous": "desktop.bambu_studio_profile_ambiguous",
                }
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text(error_keys.get(
                        error.code, "desktop.bambu_studio_import_failed",
                    )),
                    parent=window,
                )
                return
            if profile is None:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.bambu_studio_import_failed"),
                    parent=window,
                )
                return
            confirmed = self.messagebox.askyesno(
                self._text("desktop.bambu_studio_trust_title"),
                self.translator.text(
                    "desktop.bambu_studio_trust_confirmation",
                    host=profile.host,
                    fingerprint=profile.certificate_sha256,
                ),
                parent=window,
            )
            if not confirmed:
                return
            try:
                certificate_path = store_bambu_root_certificate(
                    self.paths.config, profile,
                )
            except (OSError, ValueError):
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.bambu_studio_certificate_save_failed"),
                    parent=window,
                )
                return

            fields["manufacturer"].delete(0, "end")
            fields["manufacturer"].insert(0, "Bambu Lab")
            fields["endpoint"].delete(0, "end")
            fields["endpoint"].insert(0, profile.host)
            fields["name"].delete(0, "end")
            fields["name"].insert(0, profile.model or "Bambu Lab")
            if profile.model:
                fields["model"].delete(0, "end")
                fields["model"].insert(0, profile.model)
            serial_entry.delete(0, "end")
            serial_entry.insert(0, profile.serial_number)
            token.delete(0, "end")
            token.insert(0, profile.access_code.reveal())
            certificate_entry.delete(0, "end")
            certificate_entry.insert(0, str(certificate_path))
            certificate_sha256 = profile.certificate_sha256
            notice.configure(text=self._text("desktop.bambu_studio_imported"))

        def import_from_bambu_studio() -> None:
            nonlocal import_busy
            if import_busy or connection_busy:
                return
            host = fields["endpoint"].get().strip()
            if not host:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.bambu_studio_enter_ip"),
                    parent=window,
                )
                return
            import_busy = True
            auto_fill_button.configure(
                state="disabled",
                text=self._text("desktop.bambu_studio_importing"),
            )

            def worker() -> None:
                try:
                    imported = import_bambu_studio_profile(host)
                except BambuStudioImportError as error:
                    self.root.after(
                        0,
                        lambda error=error: finish_bambu_import(None, error),
                    )
                    return
                self.root.after(
                    0,
                    lambda imported=imported: finish_bambu_import(imported, None),
                )

            threading.Thread(
                target=worker,
                name="ufm-bambu-studio-import",
                daemon=True,
            ).start()

        auto_fill_button.configure(command=import_from_bambu_studio)

        def finish_network_import(
            identity: BambuPrinterIdentity | None, error: Exception | None, requested_host: str,
        ) -> None:
            nonlocal import_busy, certificate_sha256
            import_busy = False
            if not window.winfo_exists():
                return
            network_fill_button.configure(state="normal", text=self._text("desktop.network_autofill"))
            if fields["endpoint"].get().strip() != requested_host:
                return
            if provider_labels.get(provider.get()) != "BAMBU_LAN":
                return
            if error is not None or identity is None:
                self.messagebox.showerror(self._text("desktop.error_title"),
                                          self._text("desktop.network_autofill_failed"), parent=window)
                return
            if not self.messagebox.askyesno(
                self._text("desktop.bambu_studio_trust_title"),
                self.translator.text("desktop.bambu_studio_trust_confirmation",
                                     host=identity.host, fingerprint=identity.certificate_sha256),
                parent=window,
            ):
                return
            try:
                certificate_path = store_bambu_root_certificate(self.paths.config, identity)
            except (OSError, ValueError):
                self.messagebox.showerror(self._text("desktop.error_title"),
                                          self._text("desktop.bambu_studio_certificate_save_failed"),
                                          parent=window)
                return
            for key, value in (("name", identity.name), ("manufacturer", "Bambu Lab"),
                               ("endpoint", identity.host)):
                fields[key].delete(0, "end")
                fields[key].insert(0, value)
            if identity.model:
                fields["model"].delete(0, "end")
                fields["model"].insert(0, identity.model)
            serial_entry.delete(0, "end")
            serial_entry.insert(0, identity.serial_number)
            certificate_entry.delete(0, "end")
            certificate_entry.insert(0, str(certificate_path))
            certificate_sha256 = identity.certificate_sha256
            notice.configure(text=self._text("desktop.network_autofilled"))

        def import_from_network() -> None:
            nonlocal import_busy
            if import_busy or connection_busy:
                return
            import_busy = True
            host = fields["endpoint"].get().strip()
            network_fill_button.configure(state="disabled", text=self._text("desktop.network_searching"))

            def worker() -> None:
                try:
                    identity = identify_bambu_printer(host)
                except (BambuStudioImportError, OSError, ValueError) as error:
                    self.root.after(0, lambda error=error: finish_network_import(None, error, host))
                else:
                    self.root.after(0, lambda: finish_network_import(identity, None, host))

            threading.Thread(target=worker, name="ufm-network-autofill", daemon=True).start()

        network_fill_button.configure(command=import_from_network)

        def clear_certificate_pin(*_: object) -> None:
            nonlocal certificate_sha256
            certificate_sha256 = None

        fields["endpoint"].bind("<KeyRelease>", clear_certificate_pin)
        serial_entry.bind("<KeyRelease>", clear_certificate_pin)

        def choose_certificate() -> None:
            clear_certificate_pin()
            self._choose_certificate(certificate_entry)

        certificate_button.configure(command=choose_certificate)
        if candidate is not None:
            provider.current(
                tuple(provider_labels).index({
                    "OCTOPRINT": "OctoPrint",
                    "MOONRAKER": "Moonraker",
                    "BAMBU_LAN": "Bambu Lab (LAN)",
                }[candidate.provider_type]),
            )
            fields["name"].insert(
                0,
                candidate.name if candidate.confidence == "identified"
                else self.translator.text(
                    "desktop.discovery_possible_name",
                    provider=provider_labels.get(
                        {
                            "OCTOPRINT": "OctoPrint",
                            "MOONRAKER": "Moonraker",
                            "BAMBU_LAN": "Bambu Lab (LAN)",
                        }[candidate.provider_type],
                        candidate.provider_type,
                    ),
                    host=candidate.host,
                ),
            )
            fields["endpoint"].insert(0, candidate.endpoint)
            if candidate.provider_type == "BAMBU_LAN":
                fields["manufacturer"].insert(0, "Bambu Lab")
        update_provider_fields()
        form.columnconfigure(1, weight=1)
        save_button: Any = None
        connection_busy = False

        def report_printer_setup(
            configured: Any | None,
            error: Exception | None,
        ) -> None:
            nonlocal connection_busy
            connection_busy = False
            save_button.configure(state="normal", text=self._text("desktop.test_and_save"))
            if error is not None:
                if isinstance(error, TLSVerificationFailed):
                    message = self._text("desktop.printer_tls_failed")
                elif isinstance(error, AuthenticationFailed):
                    message = self._text("desktop.printer_auth_failed")
                elif isinstance(error, ProviderError) and error.code == "provider.unavailable":
                    message = self._text("desktop.printer_unavailable")
                elif isinstance(error, ProviderError) and error.code == "provider.invalid_observation":
                    message = self._text("desktop.printer_invalid_observation")
                elif isinstance(error, ProviderError):
                    message = self._text("desktop.printer_status_failed")
                elif isinstance(error, SecretStoreUnavailable):
                    message = self._text("secrets.unavailable")
                else:
                    message = self._text("desktop.printer_setup_failed")
                self.messagebox.showerror(
                    self._text("desktop.error_title"), message, parent=window,
                )
                return
            if configured is None:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.printer_setup_failed"), parent=window,
                )
                return
            self.refresh()
            self.messagebox.showinfo(
                self._text("desktop.printer_added"),
                self.translator.text(
                    "desktop.printer_added_result",
                    name=configured.name,
                    provider=configured.provider_type,
                    endpoint=configured.endpoint,
                ),
                parent=window,
            )
            window.destroy()

        def configure_bambu_in_background() -> None:
            nonlocal connection_busy
            if connection_busy:
                return
            required_values = (
                fields["name"].get(),
                fields["model"].get(),
                fields["endpoint"].get(),
                serial_entry.get(),
                token.get(),
            )
            if any(not value.strip() for value in required_values):
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.bambu_required_fields"),
                    parent=window,
                )
                return
            token_value = token.get().strip()
            values = {
                "name": fields["name"].get(),
                "model": fields["model"].get(),
                "host": fields["endpoint"].get().strip(),
                "serial_number": serial_entry.get().strip(),
                "access_code": SecretValue(token_value),
                "ca_certificate": (
                    None if not certificate_entry.get().strip()
                    else Path(certificate_entry.get().strip())
                ),
                "certificate_sha256": certificate_sha256,
            }
            connection_busy = True
            save_button.configure(
                state="disabled", text=self._text("desktop.checking_bambu"),
            )

            def worker() -> None:
                try:
                    result = asyncio.run(configure_bambu_printer(
                        engine=self.engine,
                        secret_store=self.secrets,
                        **values,
                    ))
                except (
                    AuthenticationFailed, ProviderError, SecretStoreUnavailable,
                    PrinterConfigurationError, PersistenceError, OSError, ValueError,
                    SQLAlchemyError,
                ) as error:
                    self.root.after(
                        0, lambda error=error: report_printer_setup(None, error),
                    )
                    return
                self.root.after(
                    0, lambda result=result: report_printer_setup(result, None),
                )

            threading.Thread(target=worker, name="ufm-bambu-connect", daemon=True).start()

        def save_printer() -> None:
            provider_type = provider_labels[provider.get()]
            if provider_type == "BAMBU_LAN":
                configure_bambu_in_background()
                return
            token_value = token.get().strip()
            try:
                configured = asyncio.run(configure_local_printer(
                    engine=self.engine,
                    secret_store=self.secrets,
                    name=fields["name"].get(),
                    manufacturer=fields["manufacturer"].get(),
                    model=fields["model"].get(),
                    provider_type=provider_type,
                    endpoint=fields["endpoint"].get(),
                    token=None if not token_value else SecretValue(token_value),
                ))
            except AuthenticationFailed:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.printer_auth_failed"),
                    parent=window,
                )
                return
            except ProviderError as error:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self.translator.text(
                        "desktop.printer_connection_failed", reason=error.code,
                    ),
                    parent=window,
                )
                return
            except SecretStoreUnavailable:
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("secrets.unavailable"),
                    parent=window,
                )
                return
            except (
                PrinterConfigurationError, PersistenceError, OSError, ValueError,
                SQLAlchemyError,
            ):
                self.messagebox.showerror(
                    self._text("desktop.error_title"),
                    self._text("desktop.printer_setup_failed"),
                    parent=window,
                )
                return
            report_printer_setup(configured, None)

        save_button = self.ttk.Button(
            form, text=self._text("desktop.test_and_save"), command=save_printer,
        )
        save_button.grid(row=certificate_row + 4, column=1, sticky="e")

    def _choose_certificate(self, entry: Any) -> None:
        path = self.filedialog.askopenfilename(
            parent=self.root,
            title=self._text("desktop.ca_certificate"),
            filetypes=(
                (self._text("desktop.certificate_files"), "*.pem *.crt *.cer"),
                (self._text("desktop.all_files"), "*.*"),
            ),
        )
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def import_spoolman(self) -> None:
        source = self.filedialog.askopenfilename(
            parent=self.root,
            title=self._text("desktop.select_spoolman"),
            initialdir=str(Path.home()),
            filetypes=(
                (self._text("desktop.sqlite_files"), "*.db *.sqlite *.sqlite3"),
                (self._text("desktop.all_files"), "*.*"),
            ),
        )
        if not source:
            return
        source_path = Path(source)
        try:
            preview = preview_spoolman_database(source_path, engine=self.engine)
        except (SpoolmanImportRejected, OSError, SQLAlchemyError):
            self.messagebox.showerror(
                self._text("desktop.error_title"),
                self._text("desktop.import_invalid"),
                parent=self.root,
            )
            return
        source_instance_key = self._choose_spoolman_source(preview)
        if source_instance_key is None:
            return
        summary = self.translator.text(
            "desktop.import_confirmation",
            source_instance_key=source_instance_key,
            spools=preview.spool_count,
            known=preview.known_stock_count,
            unknown=preview.unknown_stock_count,
            archived=preview.archived_count,
            lots=preview.lot_number_count,
            colors=preview.color_count,
            locations=preview.location_count,
            metadata_unknown=preview.unsupported_metadata_count,
        )
        if not self.messagebox.askyesno(
            self._text("desktop.import"), summary, parent=self.root,
        ):
            return
        try:
            result = import_spoolman_database(
                source_path, self.paths, engine=self.engine,
                source_instance_key=source_instance_key,
                expected_source_fingerprint=preview.source_fingerprint,
            )
        except (
            SpoolmanImportRejected, BackupInvalid, MigrationRequired, PersistenceError,
            OSError, ValueError, SQLAlchemyError,
        ):
            self.messagebox.showerror(
                self._text("desktop.error_title"),
                self._text("desktop.import_failed"),
                parent=self.root,
            )
            self.refresh()
            return
        self.refresh()
        target_backup = (
            self._text("desktop.no_existing_ufm_backup")
            if result.target_backup is None else str(result.target_backup)
        )
        self.messagebox.showinfo(
            self._text("desktop.import_complete"),
            self.translator.text(
                "desktop.import_result",
                count=result.processed_count,
                source_backup=str(result.source_backup),
                target_backup=target_backup,
                source_instance_key=result.source_instance_key,
            ),
            parent=self.root,
        )

    def _choose_spoolman_source(self, preview: SpoolmanImportPreview) -> str | None:
        window = self.tk.Toplevel(self.root)
        window.title(self._text("desktop.import_source_title"))
        window.transient(self.root)
        window.grab_set()
        form = self.ttk.Frame(window, padding=18)
        form.pack(fill="both", expand=True)
        self.ttk.Label(
            form, text=self._text("desktop.import_source_prompt"), wraplength=480,
        ).pack(anchor="w", pady=(0, 10))
        new_label = self._text("desktop.import_source_new")
        labels = [new_label]
        keys: dict[str, str] = {}
        for item in preview.source_instances:
            label = spoolman_import_source_label(
                item, unverified_label=self._text("desktop.import_source_unverified"),
                recovery_label=self._text("desktop.import_source_recovery_counts"),
            )
            labels.append(label)
            keys[label] = item.source_instance_key
        default_source_key = default_spoolman_import_source_key(
            preview.source_instances, preview.suggested_source_instance_key,
        )
        suggested_label = next(
            (label for label, key in keys.items()
             if key == default_source_key),
            new_label,
        )
        selected = self.tk.StringVar(master=window, value=suggested_label)
        chooser = self.ttk.Combobox(
            form, state="readonly", values=tuple(labels), textvariable=selected,
            width=62,
        )
        chooser.pack(fill="x", pady=(0, 12))
        result: list[str | None] = [None]

        def accept() -> None:
            result[0] = keys.get(selected.get()) or new_spoolman_source_key()
            window.destroy()

        def cancel() -> None:
            window.destroy()

        buttons = self.ttk.Frame(form)
        buttons.pack(fill="x")
        self.ttk.Button(
            buttons, text=self._text("desktop.import_source_cancel"), command=cancel,
        ).pack(side="right", padx=(8, 0))
        self.ttk.Button(
            buttons, text=self._text("desktop.import_source_continue"), command=accept,
        ).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)
        window.wait_window()
        return result[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ufm-desktop", allow_abbrev=False)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--locale", choices=("uk-UA", "en-US"))
    args = parser.parse_args(argv)
    container = None
    engine = None
    try:
        paths = AppPaths.resolve(args.data_dir)
        settings = load_settings(paths.config / "settings.json")
        if args.locale:
            settings = AppSettings.model_validate({
                **settings.model_dump(), "locale": args.locale,
            })
        container = create_container(settings, paths)
        engine = create_sqlite_engine(
            paths.data / "ufm.sqlite3",
            busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        )
        migrate_database(engine)
    except (
        SettingsError, ValidationError, OSError, MigrationRequired, SQLAlchemyError,
        TranslationError,
    ):
        print("Desktop startup failed. Check local settings and database access.", file=sys.stderr)
        if engine is not None:
            engine.dispose()
        if container is not None:
            container.close()
        return 1
    assert container is not None
    assert engine is not None
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        app = DesktopApp(
            root=tk.Tk(), tk_module=tk, ttk=ttk, filedialog=filedialog,
            messagebox=messagebox, translator=container.translator,
            paths=paths, engine=engine, secrets=container.secrets,
        )
        app.root.mainloop()
        return 0
    except (OSError, ImportError, TranslationError):
        print("Desktop interface could not be started.", file=sys.stderr)
        return 1
    except tk.TclError:
        print("Desktop interface could not be started.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
        container.close()


if __name__ == "__main__":
    raise SystemExit(main())
