"""Optional Qt smoke test with real stock commands and no printer network."""

import csv
import io
import json
import os
import re
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import pytest
from sqlalchemy import select

_APPLICATION = None


@pytest.fixture(scope="session")
def qt_application():
    global _APPLICATION
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _APPLICATION = QApplication.instance() or QApplication([])
    _APPLICATION.setQuitOnLastWindowClosed(False)
    yield _APPLICATION
    app = _APPLICATION
    if app is not None:
        from PySide6.QtCore import QCoreApplication, QEvent

        app.closeAllWindows()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    # Keep the QApplication wrapper alive until interpreter shutdown. Explicitly
    # quitting and collecting it here crashes the PySide6 Windows teardown.


def test_studio_translations_have_matching_named_fields() -> None:
    from ufm.ui.i18n import placeholders

    catalog = json.loads(files("ufm.ui").joinpath("studio_strings.json").read_text("utf-8"))
    for pair in catalog.values():
        assert len(pair) == 2
        assert all(isinstance(value, str) and value.strip() for value in pair)
        assert placeholders(pair[0]) == placeholders(pair[1])


def test_inventory_action_registry_matches_ui_handlers_and_test_evidence() -> None:
    from ufm.ui.studio_window import StudioWindow

    root = Path(__file__).resolve().parents[2]
    registry_path = root / "docs" / "UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv"
    with registry_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    strings = json.loads((root / "src" / "ufm" / "ui" / "studio_strings.json").read_text("utf-8"))
    test_sources = "\n".join(path.read_text(encoding="utf-8") for path in (root / "tests").rglob("*.py"))
    assert len(rows) == 23
    assert len({row["control_id"] for row in rows}) == len(rows)
    for row in rows:
        methods = re.findall(r"StudioWindow\.([A-Za-z_]\w*)", row["обробник"])
        assert methods, row["обробник"]
        assert all(hasattr(StudioWindow, method) for method in methods), row["обробник"]
        assert row["статус"].strip()
        assert row["доказ"].strip()
        if row["control_id"] != "history_selection":
            assert row["control_id"] in strings, row["control_id"]
        for evidence_test in row["доказ"].split(";"):
            name = evidence_test.strip()
            if name.startswith("test_"):
                assert name in test_sources, name


def test_system_registry_documents_haspel_booking_review_safety() -> None:
    root = Path(__file__).resolve().parents[2]
    registry_path = root / "docs" / "UFM_STUDIO_SYSTEM_ACTION_REGISTRY_UK.csv"
    with registry_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    action = next(row for row in rows if row["control_id"] == "review_haspel_bookings")
    strings = json.loads((root / "src" / "ufm" / "ui" / "studio_strings.json").read_text("utf-8"))
    source = (root / "src" / "ufm" / "ui" / "studio_window.py").read_text("utf-8")
    assert "authority_review_bookings" in strings
    assert "review_remote_bookings" in source
    assert "authority_booking_unknown" in strings
    assert "authority_booking_confirm" in strings
    assert "will not debit filament" in strings["authority_booking_confirm"][1]
    assert "spool database stock" in strings["authority_booking_confirm"][1]
    assert "pending/uncertain" in action["нормальний стан"]
    assert "не надсилає його повторно" in action["помилка/недоступність"]
    assert action["статус"] == "Реалізовано; acceptance pending"


def test_system_registry_documents_safe_diagnostics_export() -> None:
    root = Path(__file__).resolve().parents[2]
    registry_path = root / "docs" / "UFM_STUDIO_SYSTEM_ACTION_REGISTRY_UK.csv"
    with registry_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    action = next(row for row in rows if row["control_id"] == "export_diagnostics")
    strings = json.loads((root / "src" / "ufm" / "ui" / "studio_strings.json").read_text("utf-8"))
    source = (root / "src" / "ufm" / "ui" / "studio_window.py").read_text("utf-8")
    assert "export_diagnostics" in strings
    assert "build_safe_diagnostic_bundle" in source
    assert "manifest" in action["нормальний стан"]
    assert "сирих полів" in action["нормальний стан"]
    assert "явна згода" in action["нормальний стан"]
    assert action["статус"] == "Реалізовано; acceptance pending"


@pytest.fixture
def studio_workspace(tmp_path, qt_application):
    from ufm.bootstrap.app_container import create_container
    from ufm.bootstrap.settings import AppSettings
    from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
    from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
    from ufm.infrastructure.studio_backend import StudioBackend
    from ufm.platform.common.paths import AppPaths
    from ufm.ui.studio_window import StudioWindow

    app = qt_application
    paths = AppPaths.resolve(tmp_path)
    container = create_container(AppSettings(), paths)
    engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
    try:
        migrate_database(engine)
        backend = StudioBackend(engine, paths)
        window = StudioWindow(backend, container, "uk-UA")
        yield app, backend, window
        # Do not destroy the window, database or QApplication while a worker's
        # native QThread is still running. Deliver its queued finish callback too.
        for task in tuple(window.tasks):
            if task.isRunning() and not task.wait(5000):
                raise RuntimeError("studio_test_worker_did_not_stop")
        app.processEvents()
        window.close()
        window.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent

        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    finally:
        engine.dispose()
        container.close()


def _qr_test_spools(backend, window, app):
    profile_id = backend.add_material("PLA", "PLA")
    backend.add_spool("QR test spool A", profile_id)
    backend.add_spool("QR test spool B", profile_id)
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    return tuple(backend.spools())


@pytest.mark.parametrize("cancel", [False, True])
def test_studio_single_qr_export_writes_svg_or_honors_cancel(
    studio_workspace, monkeypatch, tmp_path, cancel,
) -> None:
    from PySide6.QtWidgets import QFileDialog

    app, backend, window = studio_workspace
    rows = _qr_test_spools(backend, window, app)
    output = tmp_path / "spool.svg"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *_args, **_kwargs: ("" if cancel else str(output), "SVG (*.svg)"),
    )

    window.export_qr_label()

    if cancel:
        assert not output.exists()
    else:
        import xml.etree.ElementTree as ElementTree

        root = ElementTree.fromstring(output.read_bytes())
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert root.attrib["width"] == "80mm"
        assert str(rows[0].id).encode() in output.read_bytes()
        assert b"QR test spool A" in output.read_bytes()
    assert len(backend.spools()) == 2


@pytest.mark.parametrize("cancel", [False, True])
def test_studio_batch_qr_export_creates_separate_svg_files_or_honors_cancel(
    studio_workspace, monkeypatch, tmp_path, cancel,
) -> None:
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    app, backend, window = studio_workspace
    rows = _qr_test_spools(backend, window, app)
    monkeypatch.setattr(window, "select_spools_for_labels", lambda: rows)
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        lambda *_args, **_kwargs: "" if cancel else str(tmp_path),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window.batch_export_qr_labels()

    directories = tuple(tmp_path.glob("ufm-labels-*"))
    if cancel:
        assert directories == ()
    else:
        assert len(directories) == 1
        files = tuple(sorted(directories[0].glob("*.svg")))
        assert len(files) == 2
        contents = [path.read_bytes() for path in files]
        assert all(b"<svg " in payload for payload in contents)
        assert all(b"QR test spool" in payload for payload in contents)
        assert all(str(row.id).encode() in b"".join(contents) for row in rows)
    assert len(backend.spools()) == 2


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("cancel_print_dialog", [False, True])
def test_studio_qr_print_ui_renders_or_cancels_without_physical_printer(
    studio_workspace, monkeypatch, batch, cancel_print_dialog,
) -> None:
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QDialog

    import ufm.ui.studio_window as studio_ui

    app, backend, window = studio_workspace
    rows = _qr_test_spools(backend, window, app)
    monkeypatch.setattr(window, "label_dimensions", lambda: (80.0, 45.0))

    printers = []

    class FakePrinter:
        class PrinterMode:
            HighResolution = object()

        def __init__(self, _mode):
            self.new_pages = 0
            printers.append(self)

        def resolution(self):
            return 96

        def pageLayout(self):
            return self

        def paintRectPixels(self, _resolution):
            return QRect(0, 0, 1200, 1600)

        def newPage(self):
            self.new_pages += 1
            return True

    monkeypatch.setattr(studio_ui, "QPrinter", FakePrinter)

    class FakePrintDialog:
        def __init__(self, _printer, _parent):
            pass

        def exec(self):
            return (
                QDialog.DialogCode.Rejected if cancel_print_dialog
                else QDialog.DialogCode.Accepted
            )

    monkeypatch.setattr(studio_ui, "QPrintDialog", FakePrintDialog)

    class FakePainter:
        def begin(self, _printer):
            return True

        def end(self):
            pass

    monkeypatch.setattr(studio_ui, "QPainter", FakePainter)
    rendered = []

    class FakeSvgRenderer:
        def __init__(self, payload):
            self.payload = bytes(payload)

        def isValid(self):
            return self.payload.startswith(b"<svg ")

        def render(self, _painter, _target):
            rendered.append(self.payload)

    monkeypatch.setattr(studio_ui, "QSvgRenderer", FakeSvgRenderer)
    if batch:
        monkeypatch.setattr(window, "select_spools_for_labels", lambda: rows)
        window.batch_print_qr_labels()
    else:
        window.print_qr_label()

    assert len(printers) == 1
    printer = printers[0]
    expected_pages = 0 if cancel_print_dialog else (len(rows) if batch else 1)
    assert len(rendered) == expected_pages
    assert printer.new_pages == (len(rows) - 1 if batch and expected_pages else 0)
    if not cancel_print_dialog:
        assert all(b"QR test spool" in payload for payload in rendered)
    assert len(backend.spools()) == 2


def test_inventory_selection_filter_and_history(studio_workspace) -> None:
    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    identity = backend.add_spool("Green", profile)
    backend.change_stock(identity, "opening", "723.456", "initial")
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    assert "723.456" in window.history.toPlainText()
    assert window.selected().id == identity
    window.search.setText("PETG")
    assert window.inventory.isRowHidden(0)
    window.search.clear()
    assert not window.inventory.isRowHidden(0)


def test_inventory_empty_normal_unavailable_and_error_states(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    app, backend, window = studio_workspace
    window.refresh()
    assert not window.empty_inventory_hint.isHidden()
    assert all(not button.isEnabled() for button in window.stock_buttons)
    assert all(not button.isEnabled() for button in window.inventory_action_buttons)

    profile = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Unknown stock", profile)
    window.refresh()
    assert window.empty_inventory_hint.isHidden()
    window.inventory.selectRow(0)
    app.processEvents()
    assert window.stock_buttons[0].isEnabled()  # opening balance can be established
    assert not window.stock_buttons[1].isEnabled()  # unknown balance cannot be debited
    assert not window.stock_buttons[2].isEnabled()  # nor adjusted as known stock
    assert all(button.isEnabled() for button in window.inventory_action_buttons)

    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: shown.append(message),
    )
    window.error("provider.unavailable")
    assert shown and "provider.unavailable" in shown[0]
    assert spool_id == window.selected().id

    monkeypatch.setattr(
        QInputDialog, "getText", lambda *_args, **_kwargs: ("not a mass", True),
    )
    window.stock("opening")
    assert shown[-1].endswith("ValueError")
    assert backend.spools()[0].remaining_mg is None
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *_args, **_kwargs: ("125", True),
    )
    window.stock("opening")
    assert backend.spools()[0].remaining_mg == 125_000
    assert "125.000" in window.history.toPlainText()

    read_spools = backend.spools
    monkeypatch.setattr(
        backend, "spools",
        lambda: (_ for _ in ()).throw(RuntimeError("private database detail")),
    )
    window.refresh()
    assert not window.inventory_unavailable_hint.isHidden()
    assert "private database detail" not in window.inventory_unavailable_hint.text()
    assert window.inventory.rowCount() == 0
    assert not window.inventory_views.isEnabled()
    assert not window.add_spool_button.isEnabled()
    assert all(not button.isEnabled() for button in window.stock_buttons)
    assert all(not button.isEnabled() for button in window.inventory_action_buttons)

    monkeypatch.setattr(backend, "spools", read_spools)
    window.refresh()
    assert window.inventory_unavailable_hint.isHidden()
    assert window.inventory_views.isEnabled()
    assert window.inventory.rowCount() == 1


def test_studio_creates_spool_with_metadata_without_opening_stock(
    studio_workspace, monkeypatch,
) -> None:
    _app, backend, window = studio_workspace
    brand_id = backend.add_brand("Spool maker", "spool-create-brand")
    backend.add_material(
        "PLA Profile", "PLA", brand_id=brand_id, product_line="PLA Plus",
        default_color_name="Blue",
    )
    window.refresh()
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)

    def fill_spool(_title, fields):
        widgets = dict(fields)
        widgets["name"].setText("New metadata spool")
        widgets["batch_number"].setText("B-1")
        widgets["lot_number"].setText("LOT-2")
        widgets["nominal_filament"].setText("1000")
        widgets["empty_spool"].setText("225")
        widgets["opened_date"].setText("2026-10-20")
        widgets["manufactured_date"].setText("2026-01-15")
        widgets["expires_date"].setText("2027-01-15")
        widgets["purchase_price"].setText("32,50")
        widgets["purchase_basis"].setText("1000")
        widgets["currency"].setText("UAH")
        widgets["purchase_date"].setText("2026-10-18")
        widgets["color_hex"].setText("#123456")
        return True

    monkeypatch.setattr(window, "form", fill_spool)
    window.add_spool()
    assert errors == []
    row = next(row for row in backend.spools() if row.name == "New metadata spool")
    assert row.brand_id == brand_id
    assert row.product_line == "PLA Plus"
    assert row.batch_number == "B-1"
    assert row.lot_number == "LOT-2"
    assert row.nominal_filament_mg == 1_000_000
    assert row.empty_spool_mg == 225_000
    assert row.opened_date == "2026-10-20"
    assert row.manufactured_date == "2026-01-15"
    assert row.expires_date == "2027-01-15"
    assert row.purchase_price == "32.5"
    assert row.purchase_basis_mg == 1_000_000
    assert row.currency == "UAH"
    assert row.purchase_date == "2026-10-18"
    assert row.color_name == "Blue"
    assert row.color_hex == "#123456"
    assert row.remaining_mg is None
    assert backend.history(row.id) == ()

    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    before = backend.spools()

    def fill_invalid_spool(_title, fields):
        dict(fields)["name"].setText("  ")
        return True

    monkeypatch.setattr(window, "form", fill_invalid_spool)
    window.add_spool()
    assert errors == ["ValueError"]
    assert backend.spools() == before

    def fill_unavailable_spool(_title, fields):
        dict(fields)["name"].setText("Unavailable spool")
        return True

    monkeypatch.setattr(window, "form", fill_unavailable_spool)
    monkeypatch.setattr(
        backend, "add_spool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    window.add_spool()
    assert errors == ["ValueError", "OSError"]
    assert backend.spools() == before


def test_studio_add_spool_empty_catalog_shows_guidance_without_mutation(
    studio_workspace, monkeypatch,
) -> None:
    _app, backend, window = studio_workspace
    window.refresh()
    assert not window.empty_materials_hint.isHidden()
    messages: list[str] = []
    monkeypatch.setattr(window, "info", messages.append)

    window.add_spool()

    assert backend.materials() == ()
    assert backend.spools() == ()
    assert messages == [window.text("no_profiles")]

    backend.add_material("PLA", "PLA")
    window.refresh()
    assert window.empty_materials_hint.isHidden()


@pytest.mark.parametrize("accept", [False, True])
def test_studio_manual_weighing_requires_explicit_reconciliation_confirmation(
    studio_workspace, monkeypatch, accept,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from ufm.infrastructure.persistence.models.schema import inventory_evidence

    app, backend, window = studio_workspace
    profile_id = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Measured spool", profile_id, empty_spool_grams="225")
    backend.change_stock(spool_id, "opening", "900", "measurement-ui-opening")
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    measure_button = next(
        button for button in window.inventory_action_buttons
        if button.text() == window.text("record_measurement")
    )
    assert measure_button.isEnabled()

    def fill_measurement(_title, fields):
        widgets = dict(fields)
        widgets["gross_weight"].setText("1075")
        widgets["tare_weight"].setText("225")
        return True

    messages: list[str] = []
    monkeypatch.setattr(window, "form", fill_measurement)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args, **_kwargs: (
            QMessageBox.StandardButton.Yes if accept else QMessageBox.StandardButton.No
        ),
    )
    monkeypatch.setattr(window, "info", messages.append)
    window.record_measurement()

    with backend.engine.connect() as connection:
        saved = connection.execute(select(inventory_evidence)).mappings().all()
    assert len(saved) == 1
    assert saved[0]["gross_mg"].milligrams == 1_075_000
    assert saved[0]["tare_mg"].milligrams == 225_000
    assert saved[0]["net_mg"].milligrams == 850_000
    assert saved[0]["ledger_cutoff"] == 1
    assert backend.spools()[0].remaining_mg == (850_000 if accept else 900_000)
    history = backend.history(spool_id)
    assert "1 075.000" in window.history.toPlainText()
    assert len(history) == (2 if accept else 1)
    if accept:
        assert history[-1].delta.milligrams == -50_000
        assert history[-1].inventory_reconciliation_id is not None
        assert window.text("measurement_applied") in messages[0]
        assert "Звіряння прийнято" in window.history.toPlainText()
    else:
        assert "залишок не змінено" in messages[0].casefold()
        assert "звіряння не прийнято" in window.history.toPlainText()


@pytest.mark.parametrize("failure", ["invalid_measurement", "unavailable_backend"])
def test_studio_manual_weighing_errors_preserve_stock_and_evidence(
    studio_workspace, monkeypatch, failure,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from ufm.infrastructure.persistence.models.schema import inventory_evidence

    app, backend, window = studio_workspace
    window.refresh()
    assert not next(
        button for button in window.inventory_action_buttons
        if button.text() == window.text("record_measurement")
    ).isEnabled()
    profile_id = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Measurement error", profile_id, empty_spool_grams="220")
    backend.change_stock(spool_id, "opening", "800", "measurement-error-opening")
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(window, "info", lambda _message: None)

    def fill_invalid(_title, fields):
        widgets = dict(fields)
        widgets["gross_weight"].setText("100" if failure == "invalid_measurement" else "1100")
        widgets["tare_weight"].setText("220")
        return True

    monkeypatch.setattr(window, "form", fill_invalid)
    if failure == "unavailable_backend":
        monkeypatch.setattr(
            backend, "record_manual_measurement",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        )
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args, **_kwargs: pytest.fail("failed capture must not ask to reconcile"),
    )
    window.record_measurement()

    with backend.engine.connect() as connection:
        evidence = connection.execute(select(inventory_evidence.c.id)).all()
    assert evidence == []
    assert backend.spools()[0].remaining_mg == 800_000
    assert len(backend.history(spool_id)) == 1
    assert errors == (["ValueError"] if failure == "invalid_measurement" else ["OSError"])


@pytest.mark.parametrize("mode", ["opening", "deduct", "add"])
@pytest.mark.parametrize("failure", ["invalid_amount", "unavailable_backend"])
def test_studio_stock_action_errors_preserve_inventory_and_ledger(
    studio_workspace, monkeypatch, mode, failure,
) -> None:
    from PySide6.QtWidgets import QInputDialog

    app, backend, window = studio_workspace
    profile_id = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool(f"{mode} error", profile_id)
    if mode != "opening":
        backend.change_stock(spool_id, "opening", "800", f"{mode}-error-opening")
    window.refresh()
    app.processEvents()
    selected = backend.spools()[0]
    before_history = backend.history(spool_id)
    before_remaining = selected.remaining_mg
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *_args, **_kwargs: ("not-a-mass", True),
    )
    if failure == "unavailable_backend":
        def unavailable(*_args, **_kwargs):
            raise OSError("offline")

        monkeypatch.setattr(backend, "change_stock", unavailable)
    window.stock(mode)

    assert errors == (["ValueError"] if failure == "invalid_amount" else ["OSError"])
    assert backend.spools()[0].remaining_mg == before_remaining
    assert backend.history(spool_id) == before_history


@pytest.mark.parametrize(
    "action,backend_method",
    [
        ("edit_spool", "edit_spool"),
        ("archive_spool", "archive_spool"),
        ("rebuild_projection", "rebuild_projection"),
        ("compensate_transaction", "compensate"),
    ],
)
def test_studio_inventory_action_unavailable_state_preserves_ledger(
    studio_workspace, monkeypatch, action, backend_method,
) -> None:
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    app, backend, window = studio_workspace
    profile_id = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Unavailable action", profile_id)
    backend.change_stock(spool_id, "opening", "800", "unavailable-action-opening")
    backend.change_stock(spool_id, "deduct", "25", "unavailable-action-deduct")
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    before = backend.spools()[0]
    history = backend.history(spool_id)
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(window, "form", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QInputDialog, "getItem",
        lambda _parent, _title, _label, items, *_args: (items[0], True),
    )

    def run_with_error_callback(operation, callback):
        try:
            result = operation()
        except Exception as error:
            window.error(type(error).__name__)
        else:
            callback(result)

    monkeypatch.setattr(window, "work", run_with_error_callback)

    def unavailable(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(backend, backend_method, unavailable)
    getattr(window, action)()
    assert errors == ["OSError"]
    assert backend.spools()[0].remaining_mg == before.remaining_mg
    assert backend.history(spool_id) == history


@pytest.mark.parametrize("action", ["add_material", "add_brand"])
@pytest.mark.parametrize("failure", ["invalid_input", "unavailable_backend"])
def test_studio_catalog_create_errors_do_not_create_records(
    studio_workspace, monkeypatch, action, failure,
) -> None:
    app, backend, window = studio_workspace
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    def run_with_error_callback(operation, callback):
        try:
            result = operation()
        except Exception as error:
            window.error(type(error).__name__)
        else:
            callback(result)

    monkeypatch.setattr(window, "work", run_with_error_callback)

    if action == "add_material":
        def fill_material(_title, fields):
            values = dict(fields)
            values["name"].setText("Test PLA")
            values["diameter"].setText(
                "invalid" if failure == "invalid_input" else "1.75"
            )
            return True

        monkeypatch.setattr(window, "form", fill_material)
        if failure == "unavailable_backend":
            monkeypatch.setattr(
                backend, "add_material",
                lambda **_kwargs: (_ for _ in ()).throw(OSError("offline")),
            )
        window.add_material()
        assert backend.materials() == ()
    else:
        def fill_brand(_title, fields):
            fields[0][1].setText("" if failure == "invalid_input" else "Test brand")
            return True

        monkeypatch.setattr(window, "form", fill_brand)
        if failure == "unavailable_backend":
            monkeypatch.setattr(
                backend, "add_brand",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
            )
        window.add_brand()
        assert backend.brands() == ()

    assert errors == (["ValueError"] if failure == "invalid_input" else ["OSError"])


@pytest.mark.parametrize("action", ["edit_material", "edit_brand"])
@pytest.mark.parametrize("failure", ["invalid_input", "unavailable_backend"])
def test_studio_catalog_edit_errors_preserve_existing_records(
    studio_workspace, monkeypatch, action, failure,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    app, backend, window = studio_workspace
    if action == "edit_material":
        identity = backend.add_material("Original PLA", "PLA")
        before = next(row for row in backend.materials() if row.id == identity)
        window.refresh()
        window.material_table.selectRow(0)
    else:
        backend.add_brand("Original Brand", "catalog-edit-brand")
        identity = backend.brand_records()[0].id
        before = next(row for row in backend.brand_records() if row.id == identity)
        window.refresh()
        window.brand_table.selectRow(0)
    app.processEvents()
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    def fill_edit(_title, fields):
        if action == "edit_material":
            widgets = dict(fields)
            widgets["name"].setText("Changed PLA")
            widgets["diameter"].setText(
                "invalid" if failure == "invalid_input" else "1.75"
            )
        else:
            fields[0][1].setText("" if failure == "invalid_input" else "Changed Brand")
        return True

    monkeypatch.setattr(window, "form", fill_edit)

    def unavailable(*_args, **_kwargs):
        raise OSError("offline")

    method_name = "edit_material" if action == "edit_material" else "edit_brand"
    if failure == "unavailable_backend":
        monkeypatch.setattr(backend, method_name, unavailable)

    def run_with_error_callback(operation, callback):
        try:
            result = operation()
        except Exception as error:
            window.error(type(error).__name__)
        else:
            callback(result)

    monkeypatch.setattr(window, "work", run_with_error_callback)
    getattr(window, action)()
    after = (
        next(row for row in backend.materials() if row.id == identity)
        if action == "edit_material"
        else next(row for row in backend.brand_records() if row.id == identity)
    )
    assert after == before
    assert errors == (["ValueError"] if failure == "invalid_input" else ["OSError"])


def test_studio_archive_brand_unavailable_state_preserves_brand(studio_workspace, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    app, backend, window = studio_workspace
    backend.add_brand("Protected brand", "brand-archive-offline")
    identity = backend.brand_records()[0].id
    window.refresh()
    window.brand_table.selectRow(0)
    app.processEvents()
    before = backend.brand_records()[0]
    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    def run_with_error_callback(operation, callback):
        try:
            result = operation()
        except Exception as error:
            window.error(type(error).__name__)
        else:
            callback(result)

    monkeypatch.setattr(window, "work", run_with_error_callback)
    monkeypatch.setattr(
        backend, "archive_brand", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    window.archive_brand()
    assert backend.brand_records()[0] == before
    assert backend.brand_records()[0].id == identity
    assert errors == ["OSError"]


def test_inventory_sort_keeps_selected_spool_identity_and_filter(studio_workspace) -> None:
    from PySide6.QtCore import Qt

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    zebra = backend.add_spool("Zebra", profile)
    alpha = backend.add_spool("Alpha", profile)
    backend.change_stock(zebra, "opening", "900", "zebra-opening")
    backend.change_stock(alpha, "opening", "80", "alpha-opening")
    window.refresh()
    window.inventory.sortItems(0, Qt.SortOrder.AscendingOrder)
    app.processEvents()
    assert window.inventory.item(0, 0).text() == "Alpha"
    window.inventory.sortItems(2, Qt.SortOrder.AscendingOrder)
    app.processEvents()
    assert window.inventory.item(0, 0).text() == "Alpha"
    zebra_row = next(
        row for row in range(window.inventory.rowCount())
        if window.inventory.item(row, 0).data(Qt.ItemDataRole.UserRole) == zebra
    )
    window.inventory.selectRow(zebra_row)
    app.processEvents()
    assert window.selected().id == zebra
    window.inventory_view.setCurrentIndex(window.inventory_view.findData("cards"))
    app.processEvents()
    assert window.selected().id == zebra
    assert window.inventory_cards.currentItem().text().startswith("Zebra")
    window.inventory_view.setCurrentIndex(window.inventory_view.findData("table"))
    app.processEvents()
    assert window.selected().id == zebra
    window.search.setText("Zebra")
    visible = [
        window.inventory.item(row, 0).text()
        for row in range(window.inventory.rowCount())
        if not window.inventory.isRowHidden(row)
    ]
    assert visible == ["Zebra"]
    assert alpha != zebra


def test_inventory_column_chooser_keeps_identity_and_is_table_only(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QCheckBox, QDialog

    from ufm.bootstrap.settings import load_settings

    app, backend, window = studio_workspace

    def accept_columns(dialog):
        name = dialog.findChild(QCheckBox, "inventory_column_0")
        material = dialog.findChild(QCheckBox, "inventory_column_1")
        assert name is not None and not name.isEnabled()
        assert material is not None
        material.setChecked(False)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_columns)
    window.choose_inventory_columns()
    app.processEvents()
    assert not window.inventory.isColumnHidden(0)
    assert window.inventory.isColumnHidden(1)
    persisted = load_settings(backend.paths.config / "settings.json")
    assert "name" in persisted.inventory_columns
    assert "material" not in persisted.inventory_columns
    from ufm.ui.studio_window import StudioWindow

    reopened = StudioWindow(backend, replace(window.container, settings=persisted), "uk-UA")
    assert not reopened.inventory.isColumnHidden(0)
    assert reopened.inventory.isColumnHidden(1)
    reopened.close()
    reopened.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(reopened, QEvent.Type.DeferredDelete)
    app.processEvents()
    window.inventory_view.setCurrentIndex(window.inventory_view.findData("cards"))
    app.processEvents()
    assert window.inventory_cards.isVisible() or window.inventory_views.currentWidget() is window.inventory_cards
    window.inventory_view.setCurrentIndex(window.inventory_view.findData("table"))
    app.processEvents()
    assert window.inventory.isColumnHidden(1)

    import ufm.ui.studio_window as studio_module

    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    before_error = tuple(
        window.inventory.isColumnHidden(column)
        for column in range(window.inventory.columnCount())
    )

    def accept_with_unwritable_settings(dialog):
        material = dialog.findChild(QCheckBox, "inventory_column_1")
        assert material is not None
        material.setChecked(not before_error[1])
        return QDialog.DialogCode.Accepted

    with monkeypatch.context() as context:
        context.setattr(QDialog, "exec", accept_with_unwritable_settings)
        context.setattr(
            studio_module, "save_settings",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read-only")),
        )
        window.choose_inventory_columns()

    after_error = tuple(
        window.inventory.isColumnHidden(column)
        for column in range(window.inventory.columnCount())
    )
    assert after_error == before_error
    assert errors == ["settings.invalid"]


def test_inventory_material_and_stock_filters_compose_safely(studio_workspace) -> None:
    app, backend, window = studio_workspace
    pla = backend.add_material("PLA Basic", "PLA")
    petg = backend.add_material("PETG Clear", "PETG")
    known_pla = backend.add_spool("PLA known", pla)
    backend.change_stock(known_pla, "opening", "200", "known-pla-opening")
    unknown_pla = backend.add_spool("PLA unknown", pla)
    backend.add_spool("PETG unknown", petg)
    window.refresh()
    window.material_filter.setCurrentIndex(window.material_filter.findData("PLA"))
    app.processEvents()
    visible = [
        window.inventory.item(row, 0).text()
        for row in range(window.inventory.rowCount())
        if not window.inventory.isRowHidden(row)
    ]
    assert set(visible) == {"PLA known", "PLA unknown"}
    window.stock_filter.setCurrentIndex(window.stock_filter.findData("known"))
    app.processEvents()
    assert [
        window.inventory.item(row, 0).text()
        for row in range(window.inventory.rowCount())
        if not window.inventory.isRowHidden(row)
    ] == ["PLA known"]
    window.stock_filter.setCurrentIndex(window.stock_filter.findData("unknown"))
    app.processEvents()
    assert [
        window.inventory.item(row, 0).text()
        for row in range(window.inventory.rowCount())
        if not window.inventory.isRowHidden(row)
    ] == ["PLA unknown"]
    assert window.selected() is None
    assert not window.stock_buttons[1].isEnabled()  # unknown stock cannot be manually debited
    assert unknown_pla in {row.id for row in backend.spools()}


def test_checkbox_indicators_are_explicitly_visible_in_both_themes(studio_workspace) -> None:
    _, _, window = studio_workspace
    asset = Path(__file__).resolve().parents[2] / "src" / "ufm" / "ui" / "assets" / "checkbox-checked.png"
    assert asset.is_file()

    for dark in (False, True):
        window.dark = dark
        window.apply_theme()
        stylesheet = window.styleSheet()
        assert "QCheckBox::indicator" in stylesheet
        assert "QCheckBox::indicator:checked" in stylesheet
        assert "checkbox-checked.png" in stylesheet


def test_inventory_archive_filter_keeps_archived_spools_read_only(studio_workspace) -> None:
    from ufm.domain.value_objects import EntityId
    from ufm.integrations.printers.configuration import ensure_local_device

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    archived = backend.add_spool("Old spool", profile)
    backend.add_spool("Current spool", profile)
    backend.commands.archive_spool(
        spool_id=EntityId.parse(archived), expected_revision=1,
        actor_device_id=ensure_local_device(backend.engine), command_key="archive-filter-test",
    )
    window.refresh()
    window.lifecycle_filter.setCurrentIndex(window.lifecycle_filter.findData("ARCHIVED"))
    app.processEvents()
    visible = [
        window.inventory.item(row, 0).text()
        for row in range(window.inventory.rowCount())
        if not window.inventory.isRowHidden(row)
    ]
    assert visible == ["Old spool"]
    assert window.selected() is None
    assert not any(button.isEnabled() for button in window.stock_buttons)


def test_studio_edits_and_archives_spool_through_application_commands(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Before edit", profile)
    backend.change_stock(spool_id, "opening", "500", "studio-edit-archive-opening")
    brand_id = backend.add_brand("Metadata Brand", "studio-edit-brand")
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    original_history = backend.history(spool_id)
    pending = []
    monkeypatch.setattr(window, "work", lambda operation, callback: pending.append(operation))
    def accept_spool_edit(title, fields):
        values = dict(fields)
        values["name"].setText("After edit")
        values["low_threshold"].setText("75.5")
        values["product_line"].setText("PLA Plus")
        values["batch_number"].setText("B-2026-09")
        values["lot_number"].setText("L-42")
        values["brand"].setCurrentIndex(values["brand"].findData(brand_id))
        values["nominal_filament"].setText("1000")
        values["empty_spool"].setText("250")
        values["purchase_price"].setText("45.90")
        values["purchase_basis"].setText("750")
        values["currency"].setText("USD")
        values["purchase_date"].setText("2026-09-25")
        values["color"].setText("Ocean blue")
        values["color_hex"].setText("#1166CC")
        values["secondary_color_hex"].setText("#FFFFFF")
        values["notes"].setText("Stored dry")
        return True

    monkeypatch.setattr(window, "form", accept_spool_edit)
    window.edit_spool()
    assert len(pending) == 1
    pending.pop()()
    edited = next(row for row in backend.spools() if row.id == spool_id)
    assert edited.name == "After edit"
    assert edited.low_threshold_mg == 75_500
    assert edited.product_line == "PLA Plus"
    assert edited.batch_number == "B-2026-09"
    assert edited.lot_number == "L-42"
    assert edited.brand_id == brand_id
    assert edited.nominal_filament_mg == 1_000_000
    assert edited.empty_spool_mg == 250_000
    assert edited.purchase_price == "45.9"
    assert edited.purchase_basis_mg == 750_000
    assert edited.currency == "USD"
    assert edited.purchase_date == "2026-09-25"
    assert edited.color_name == "Ocean blue"
    assert edited.color_hex == "#1166CC"
    assert edited.secondary_color_hex == "#FFFFFF"
    assert edited.notes == "Stored dry"
    assert backend.history(spool_id) == original_history
    assert edited.remaining_mg == 500_000

    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.archive_spool()
    assert len(pending) == 1
    pending.pop()()
    archived = next(row for row in backend.spools() if row.id == spool_id)
    assert archived.lifecycle == "ARCHIVED"
    assert archived.remaining_mg == 500_000
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    assert all(not button.isEnabled() for button in window.inventory_action_buttons)
    assert all(not button.isEnabled() for button in window.stock_buttons)


def test_studio_compensation_appends_reversal_and_preserves_history(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Compensate", profile)
    backend.change_stock(spool_id, "opening", "500", "studio-compensate-opening")
    backend.change_stock(spool_id, "deduct", "50", "studio-compensate-use")
    original = backend.history(spool_id)[-1]
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    assert window.compensate_button.isEnabled()

    monkeypatch.setattr(
        QInputDialog, "getItem", lambda parent, title, label, items, *args: (items[-1], True),
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    pending = []
    monkeypatch.setattr(window, "work", lambda operation, callback: pending.append(operation))
    window.compensate_transaction()
    assert len(pending) == 1
    pending.pop()()
    history = backend.history(spool_id)
    assert len(history) == 3
    assert history[-1].compensates_transaction_id == original.id
    assert history[-1].delta.milligrams == 50_000
    assert history[-1].new_effective.milligrams == 500_000


def test_studio_rebuild_projection_requires_confirmation_and_preserves_ledger(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Projection", profile)
    backend.change_stock(spool_id, "opening", "250.125", "studio-rebuild-opening")
    original_history = backend.history(spool_id)
    original = next(row for row in backend.spools() if row.id == spool_id)
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    pending = []
    monkeypatch.setattr(window, "work", lambda operation, callback: pending.append(operation))
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.rebuild_projection()
    assert len(pending) == 1
    pending.pop()()
    rebuilt = next(row for row in backend.spools() if row.id == spool_id)
    assert rebuilt.remaining_mg == original.remaining_mg == 250_125
    assert len(backend.history(spool_id)) == len(original_history)


def test_studio_creates_and_assigns_storage_location_without_stock_mutation(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QInputDialog

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Location target", profile)
    backend.change_stock(spool_id, "opening", "380", "studio-location-opening")
    history_before = backend.history(spool_id)
    pending = []
    monkeypatch.setattr(window, "work", lambda operation, callback: pending.append(operation))
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Dry cabinet", True))
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *args, **kwargs: ("CABINET", True),
    )
    window.add_storage_location()
    assert len(pending) == 1
    pending.pop()()
    locations = backend.storage_locations()
    assert len(locations) == 1
    assert locations[0].name == "Dry cabinet"
    assert locations[0].storage_type == "CABINET"

    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    monkeypatch.setattr(
        QInputDialog, "getItem",
        lambda parent, title, label, items, *args: (items[1], True),
    )
    window.assign_storage_location()
    assert len(pending) == 1
    pending.pop()()
    row = next(item for item in backend.spools() if item.id == spool_id)
    assert row.location == "Dry cabinet"
    assert row.location_id == locations[0].id
    assert row.remaining_mg == 380_000
    assert backend.history(spool_id) == history_before

    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        QInputDialog, "getItem",
        lambda _parent, _title, _label, items, *_args: (items[0], True),
    )
    monkeypatch.setattr(
        backend, "assign_storage_location",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    before = next(item for item in backend.spools() if item.id == spool_id)
    window.assign_storage_location()
    assert len(pending) == 1
    try:
        pending.pop()()
    except OSError as error:
        window.error(type(error).__name__)
    after = next(item for item in backend.spools() if item.id == spool_id)
    assert after == before
    assert backend.history(spool_id) == history_before
    assert errors == ["OSError"]


def test_studio_creates_brand_and_edits_complete_supported_material_profile(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QMessageBox

    app, backend, window = studio_workspace
    assert not window.edit_material_button.isEnabled()
    assert not window.edit_brand_button.isEnabled()
    assert not window.archive_brand_button.isEnabled()

    def fill_brand(title, fields):
        fields[0][1].setText("Acme")
        return True

    monkeypatch.setattr(window, "form", fill_brand)
    window.add_brand()
    brand_id, brand_name = backend.brands()[0]
    assert brand_name == "Acme"

    def fill_profile(title, fields, *, name, density):
        widgets = dict(fields)
        cast(QLineEdit, widgets["name"]).setText(name)
        cast(QComboBox, widgets["material"]).setCurrentText("PLA")
        cast(QLineEdit, widgets["diameter"]).setText("1.75")
        cast(QComboBox, widgets["brand"]).setCurrentIndex(
            cast(QComboBox, widgets["brand"]).findData(brand_id),
        )
        cast(QLineEdit, widgets["product_line"]).setText("Plus")
        cast(QLineEdit, widgets["density"]).setText(density)
        cast(QLineEdit, widgets["subtype"]).setText("Basic")
        cast(QLineEdit, widgets["nozzle_min_c"]).setText("205")
        cast(QLineEdit, widgets["nozzle_max_c"]).setText("230")
        cast(QLineEdit, widgets["bed_min_c"]).setText("50")
        cast(QLineEdit, widgets["bed_max_c"]).setText("60")
        cast(QLineEdit, widgets["max_volumetric_speed_mm3_s"]).setText("15")
        cast(QLineEdit, widgets["drying_temp_c"]).setText("45")
        cast(QLineEdit, widgets["drying_duration_min"]).setText("240")
        cast(QLineEdit, widgets["default_color_name"]).setText("Ocean")
        cast(QLineEdit, widgets["notes"]).setText("Dry before use")
        cast(QCheckBox, widgets["abrasive"]).setChecked(True)
        return True

    from typing import cast

    monkeypatch.setattr(window, "form", lambda title, fields: fill_profile(
        title, fields, name="PLA Basic", density="1.24",
    ))
    window.add_material()
    profile = backend.materials()[0]
    assert profile.brand_id == brand_id
    assert profile.product_line == "Plus"
    assert profile.density_g_cm3 == "1.24"
    assert profile.abrasive is True
    assert profile.subtype == "Basic"
    assert profile.nozzle_min_c == "205"
    assert profile.nozzle_max_c == "230"
    assert profile.bed_min_c == "50"
    assert profile.bed_max_c == "60"
    assert profile.max_volumetric_speed_mm3_s == "15"
    assert profile.drying_temp_c == "45"
    assert profile.drying_duration_min == 240
    assert profile.default_color_name == "Ocean"
    assert profile.notes == "Dry before use"

    spool_id = backend.add_spool("Profile-linked spool", profile.id)
    backend.change_stock(spool_id, "opening", "300", "profile-edit-opening")
    window.refresh()
    window.material_table.selectRow(0)
    app.processEvents()
    pending = []
    monkeypatch.setattr(window, "work", lambda operation, callback: pending.append(operation))
    monkeypatch.setattr(
        window, "form", lambda title, fields: fill_profile(
            title, fields, name="PLA Premium", density="1.25",
        ),
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.edit_material()
    assert len(pending) == 1
    pending.pop()()
    updated = next(item for item in backend.materials() if item.id == profile.id)
    assert updated.name == "PLA Premium"
    assert updated.density_g_cm3 == "1.25"
    assert updated.abrasive is True
    assert updated.nozzle_min_c == "205"
    assert updated.drying_duration_min == 240
    assert next(item for item in backend.spools() if item.id == spool_id).remaining_mg == 300_000


def test_studio_can_rename_and_archive_brand_without_losing_profile_links(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    app, backend, window = studio_workspace
    brand_id = backend.add_brand("Old maker", "brand-create-for-edit")
    profile_id = backend.add_material("Brand PLA", "PLA", brand_id=brand_id)
    spool_id = backend.add_spool("Linked spool", profile_id)
    backend.edit_spool(
        backend.spools()[0], "Linked spool", "", "brand-assignment-for-test", brand_id=brand_id,
    )
    window.refresh()
    window.brand_table.selectRow(0)
    app.processEvents()
    assert window.edit_brand_button.isEnabled()
    assert window.archive_brand_button.isEnabled()

    pending = []
    monkeypatch.setattr(window, "work", lambda operation, callback: pending.append(operation))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    def edit_form(title, fields):
        fields[0][1].setText("New maker")
        return True

    monkeypatch.setattr(window, "form", edit_form)
    window.edit_brand()
    assert len(pending) == 1
    pending.pop()()
    assert next(row for row in backend.brand_records() if row.id == brand_id).name == "New maker"
    assert next(row for row in backend.spools() if row.id == spool_id).brand == "New maker"

    window.refresh()
    window.brand_table.selectRow(0)
    app.processEvents()
    window.archive_brand()
    assert len(pending) == 1
    pending.pop()()
    assert all(row.id != brand_id for row in backend.brand_records())
    assert next(row for row in backend.materials() if row.id == profile_id).brand == "New maker"
    assert next(row for row in backend.spools() if row.id == spool_id).brand == "New maker"

    monkeypatch.setattr(window, "form", lambda _title, _fields: True)
    window.refresh()
    assert window.select_inventory_identity(spool_id)
    window.edit_spool()
    assert len(pending) == 1
    pending.pop()()
    assert next(row for row in backend.spools() if row.id == spool_id).brand_id == brand_id

    window.refresh()
    window.material_table.selectRow(0)
    app.processEvents()
    window.edit_material()
    assert len(pending) == 1
    pending.pop()()
    assert next(row for row in backend.materials() if row.id == profile_id).brand_id == brand_id


def test_spool_read_model_shows_saved_color_and_storage_location(studio_workspace) -> None:
    from sqlalchemy import insert, update

    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.infrastructure.persistence.models.schema import spool, storage_location
    from ufm.integrations.printers.configuration import ensure_local_device

    app, backend, window = studio_workspace
    profile = backend.add_material("PETG", "PETG")
    spool_id = backend.add_spool("Blue PETG", profile)
    location_id = EntityId.new()
    now = UtcDateTime.now()
    with backend.engine.begin() as connection:
        connection.execute(insert(storage_location).values(
            id=location_id, device_id=ensure_local_device(backend.engine),
            created_at=now, updated_at=now, revision=1, deleted_at=None,
            parent_id=None, name="Dry cabinet", type="CABINET", description=None,
            temperature_sensor_id=None, humidity_sensor_id=None,
        ))
        connection.execute(update(spool).where(spool.c.id == EntityId.parse(spool_id)).values(
            color_name="Blue", color_hex="#1E64C8", storage_location_id=location_id,
        ))
    row = next(item for item in backend.spools() if item.id == spool_id)
    assert row.color_name == "Blue"
    assert row.color_hex == "#1E64C8"
    assert row.location == "Dry cabinet"
    window.refresh()
    color_item = window.inventory.item(0, 2)
    assert color_item.text() == "Blue"
    assert color_item.background().color().name() == "#1e64c8"
    assert window.inventory.item(0, 3).text() == "Dry cabinet"
    window.location_filter.setCurrentIndex(window.location_filter.findData("Dry cabinet"))
    app.processEvents()
    assert not window.inventory.isRowHidden(0)
    window.search.setText("no matching spool")
    assert not window.filter_empty_hint.isHidden()
    assert window.selected() is None


def test_theme_toggle_persists_without_changing_inventory(studio_workspace) -> None:
    from ufm.bootstrap.settings import load_settings

    app, backend, window = studio_workspace
    window.toggle_theme()
    app.processEvents()
    settings_path = backend.paths.config / "settings.json"
    assert window.dark is True
    assert load_settings(settings_path).theme == "dark"
    window.toggle_theme()
    assert window.dark is False
    assert load_settings(settings_path).theme == "light"


def test_history_distinguishes_calculated_and_printer_usage(studio_workspace, monkeypatch) -> None:
    from ufm.domain.enums import TransactionType

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    identity = backend.add_spool("Estimate test", profile)
    backend.change_stock(identity, "opening", "1000", "estimate-opening")
    backend.change_stock(identity, "deduct", "12.345", "estimate-fixture")
    records = backend.history(identity)
    estimate = replace(records[-1], transaction_type=TransactionType.PRINT_CONSUMPTION,
                       source_type="THREE_MF", description="Розрахункова витрата")
    monkeypatch.setattr(backend, "history", lambda spool_id: (records[0], estimate))
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    window.show_history()
    assert "Розрахункова витрата" in window.history.toPlainText()
    assert "12.345" in window.history.toPlainText()
    window.language = 1
    window.show_history()
    assert "Estimated consumption" in window.history.toPlainText()
    monkeypatch.setattr(backend, "history", lambda spool_id: (
        records[0], replace(estimate, source_type="PRINTER", description=None)))
    window.show_history()
    assert "Estimated consumption" not in window.history.toPlainText()

    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    for method in ("history", "measurement_history", "cost_summary"):
        with monkeypatch.context() as context:
            context.setattr(
                backend, method,
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    OSError("private database detail"),
                ),
            )
            window.history.setPlainText("stale private details")
            window.show_history()
            assert window.history.toPlainText() == ""
            assert window.compensate_button.isEnabled() is False
            assert errors[-1] == "OSError"
    assert "private database detail" not in " ".join(errors)


def test_history_shows_cost_by_currency_and_unknown_cost_count(studio_workspace, monkeypatch) -> None:
    from ufm.application.inventory import InventoryCostSummary
    from ufm.domain.value_objects import EntityId, ExactDecimal, Mass

    app, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    spool_id = backend.add_spool("Cost history", profile)
    backend.change_stock(spool_id, "opening", "1000", "cost-history-opening")
    identity = EntityId.parse(spool_id)
    monkeypatch.setattr(backend, "cost_summary", lambda _: InventoryCostSummary(
        spool_id=identity, confirmed_prints=2, unknown_cost_prints=1,
        unknown_cost_consumed=Mass(4321),
        totals_by_currency=(("EUR", ExactDecimal.parse("0.23")),
                            ("UAH", ExactDecimal.parse("1.10"))),
    ))
    window.refresh()
    window.inventory.selectRow(0)
    app.processEvents()
    window.show_history()
    text = window.history.toPlainText()
    assert "0.23 EUR" in text
    assert "1.1 UAH" in text
    assert "без відомої ціни: 1 (4.321 г)" in text
    window.language = 1
    window.show_history()
    assert "no known price: 1 (4.321 g)" in window.history.toPlainText()


def test_cost_report_dialog_opens_and_csv_text_is_formula_safe(studio_workspace) -> None:
    from PySide6.QtCore import QTimer

    from ufm.ui.studio_window import _safe_csv_value

    app, _, window = studio_workspace
    assert _safe_csv_value("=HYPERLINK(\"https://example.invalid\")").startswith("'=")
    assert _safe_csv_value("PLA spool") == "PLA spool"
    from types import SimpleNamespace

    from ufm.domain.value_objects import ExactDecimal, Mass, UtcDateTime
    from ufm.ui.studio_window import _cost_report_csv

    timestamp = UtcDateTime.parse("2026-10-29T12:00:00.000000Z")
    records = (
        SimpleNamespace(
            transaction=SimpleNamespace(
                delta=Mass(-12_345), unit_cost=ExactDecimal.parse("0.23"),
                currency="UAH", source_type="THREE_MF",
            ),
            print_started_at=timestamp, printer_name="P1S", job_name=" =1+1",
            spool_name="PLA; black",
        ),
        SimpleNamespace(
            transaction=SimpleNamespace(
                delta=Mass(-5_000), unit_cost=None, currency=None, source_type="PRINTER",
            ),
            print_started_at=timestamp, printer_name="P1S", job_name="unknown",
            spool_name="PETG",
        ),
    )
    report = SimpleNamespace(entries=records)
    content = _cost_report_csv(report, lambda key: key, lambda grams: str(grams / 1000))
    assert content.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(content.removeprefix("\ufeff"), newline=""), delimiter=";"))
    assert rows[0] == [
        "cost_date", "printer", "cost_job", "cost_spool", "grams",
        "cost_amount", "currency", "cost_source", "state",
    ]
    assert len(rows[1]) == 9
    assert rows[1][0] == timestamp.isoformat()
    assert rows[1][2] == "' =1+1"
    assert rows[1][3] == "PLA; black"
    assert rows[1][5:9] == ["0.23", "UAH", "THREE_MF", "cost_confirmed"]
    assert rows[2][5:7] == ["", ""]
    QTimer.singleShot(0, lambda: app.activeModalWidget().accept())
    window.show_cost_report()


def test_printer_probe_shows_matches_and_mounts_only_after_confirmation(
    studio_workspace, monkeypatch,
):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QDialog
    from sqlalchemy import insert

    from ufm.application.dto.providers import (
        FeedSlotSnapshot,
        FeedSystemSnapshot,
        Observed,
        PrinterStatusSnapshot,
    )
    from ufm.application.spool_identifiers import SpoolIdentifierCommands
    from ufm.domain.enums import Availability, ConnectionState, FeedSystemKind
    from ufm.domain.value_objects import EntityId, ExactDecimal, UtcDateTime
    from ufm.infrastructure.persistence.models.schema import printer as printer_table
    from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
    from ufm.infrastructure.studio_backend import StudioPrinter
    from ufm.integrations.printers.configuration import ensure_local_device
    from ufm.ui import studio_window as module

    _, backend, window = studio_workspace
    profile = backend.add_material("PLA", "PLA")
    green = backend.add_spool("Green spool", profile)
    red = backend.add_spool("Red spool", profile)
    actor = ensure_local_device(backend.engine)
    commands = SpoolIdentifierCommands(lambda: SQLiteUnitOfWork(backend.engine))
    commands.verify(spool_id=EntityId.parse(green), namespace="bambu", kind="tray_uuid",
                    value="private-green-id", actor_device_id=actor,
                    command_key="verify-green", manual_confirmation=True)
    commands.verify(spool_id=EntityId.parse(red), namespace="bambu", kind="tag_uid",
                    value="private-red-tag", actor_device_id=actor,
                    command_key="verify-red", manual_confirmation=True)

    now = UtcDateTime.now()

    def observed(value=None):
        return Observed(
            availability=Availability.UNKNOWN if value is None else Availability.KNOWN,
            observed_at=now, received_at=now, value=value,
        )

    slots = (
        FeedSlotSnapshot("ams:0", observed(True), observed("private-green-id"),
                         observed(), observed(), observed()),
        FeedSlotSnapshot("ams:1", observed(True), observed("unregistered-private-id"),
                         observed(), observed(), observed()),
        FeedSlotSnapshot("ams:2", observed(True), observed("private-green-id"),
                         observed("private-red-tag"), observed(), observed()),
    )
    system = FeedSystemSnapshot(
        "ams:0", FeedSystemKind.AMS, slots, now, now, complete=False,
    )
    status = PrinterStatusSnapshot(
        printer_id=EntityId.new(), connection_state=ConnectionState.ONLINE,
        observed_at=now, received_at=now, progress=observed(), current_layer=observed(),
        nozzle_temperature_c=observed(ExactDecimal.parse("220")),
        bed_temperature_c=observed(ExactDecimal.parse("60")), feed_systems=(system,),
    )
    with backend.engine.begin() as connection:
        connection.execute(insert(printer_table).values(
            id=status.printer_id, device_id=actor, created_at=now, updated_at=now,
            revision=1, name="Test printer", manufacturer="Bambu Lab", model="P1S",
            enabled=True,
        ))

    async def fake_probe(**_kwargs):
        return SimpleNamespace(status=status, current_job=None)

    monkeypatch.setattr(module, "probe_configured_printer", fake_probe)
    window.printers = (StudioPrinter(
        str(status.printer_id), "Test printer", "P1S", "BAMBU_LAN", "127.0.0.1",
    ),)
    window.fill(window.printer_table, [["Test printer", "P1S", "BAMBU_LAN", "127.0.0.1"]])
    window.printer_table.setCurrentCell(0, 0)
    monkeypatch.setattr(window, "work", lambda operation, callback: callback(operation()))

    window.probe()

    result = window.device_result.toPlainText()
    assert "Green spool (підтверджено)" in result
    assert "котушку не зіставлено" in result
    assert "конфлікт ідентифікаторів" in result
    assert "private-green-id" not in result
    assert "private-red-tag" not in result
    assert backend.history(green) == ()
    assert backend.history(red) == ()
    with SQLiteUnitOfWork(backend.engine) as work:
        assert work.mounts.active_for_spool(EntityId.parse(green)) is None

    prompts: list[str] = []
    notices: list[str] = []
    monkeypatch.setattr(
        QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        module.QMessageBox, "question",
        lambda _parent, _title, message: (
            prompts.append(message) or module.QMessageBox.StandardButton.Yes
        ),
    )
    monkeypatch.setattr(window, "info", notices.append)
    window.mount_verified_feed_slot()
    assert len(prompts) == 1
    assert "Green spool" in prompts[0]
    assert "залишок філаменту не зміниться" in prompts[0]
    assert notices == [window.text("mount_done")]
    with SQLiteUnitOfWork(backend.engine) as work:
        mounted = work.mounts.active_for_spool(EntityId.parse(green))
        assert mounted is not None
        slot = work.slots.get(mounted.feed_slot_id)
        system = work.feed_systems.get(slot.feed_system_id)
        assert system.provider_system_key == "ams:0"
        assert system.kind is FeedSystemKind.AMS
        assert slot.slot_key == "ams:0"
        assert slot.tool_index is None
        assert work.ledger.for_spool(EntityId.parse(green)) == []


def test_spool_identity_enrollment_requires_visible_confirmation(studio_workspace, monkeypatch):
    from datetime import timedelta

    from PySide6.QtWidgets import QDialog

    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
    from ufm.ui import studio_window as module

    app, backend, window = studio_workspace
    profile = backend.add_material("PETG", "PETG")
    spool_id = backend.add_spool("Blue PETG", profile)
    window.refresh()
    window._observed_namespace = "bambu"
    window._observed_at = UtcDateTime.now()
    window._observed_slot_identities = (
        ("ams:0", "0:2", "tray_uuid", "observed-tray-id"),
    )
    prompts: list[str] = []
    information: list[str] = []

    def accept_confirmation(_parent, _title, message):
        prompts.append(message)
        return module.QMessageBox.StandardButton.Yes

    def inline_work(operation, callback):
        callback(operation())

    monkeypatch.setattr(window, "work", inline_work)
    monkeypatch.setattr(window, "info", information.append)
    monkeypatch.setattr(module.QMessageBox, "question", accept_confirmation)
    monkeypatch.setattr(
        QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted,
    )
    window._observed_at = UtcDateTime(UtcDateTime.now().value - timedelta(seconds=121))
    window.verify_feed_identity()
    assert information == [window.text("identity_probe_first")]
    assert prompts == []
    information.clear()
    window._observed_at = UtcDateTime.now()
    window.verify_feed_identity()

    assert len(prompts) == 1
    assert "observed-tray-id" in prompts[0]
    assert information == [window.text("identity_verified_reprobe")]
    with SQLiteUnitOfWork(backend.engine) as work:
        identifier = work.spool_identifiers.by_trusted_identity(
            "bambu", "tray_uuid", "observed-tray-id",
        )
        assert identifier is not None
        assert identifier.spool_id == EntityId.parse(spool_id)
        assert identifier.is_trusted_current
        assert work.ledger.for_spool(EntityId.parse(spool_id)) == []
        assert work.mounts.active_for_spool(EntityId.parse(spool_id)) is None


def test_bambu_enrollment_requires_explicit_certificate_trust(
    studio_workspace, monkeypatch
) -> None:
    from unittest.mock import AsyncMock

    from ufm.application.ports.secrets import SecretValue
    from ufm.integrations.printers.bambu_studio import BambuStudioProfile
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    profile = BambuStudioProfile(
        "192.168.1.5",
        "TEST-SERIAL",
        "Test model",
        SecretValue("not-a-real-code"),
        "ab" * 32,
        "test certificate",
    )
    enrolled = AsyncMock()
    monkeypatch.setattr(module, "configure_bambu_printer", enrolled)
    monkeypatch.setattr(module, "import_bambu_studio_profile", lambda host: profile)
    monkeypatch.setattr(module.QInputDialog, "getText", lambda *args: (profile.host, True))
    monkeypatch.setattr(
        module.QMessageBox, "question", lambda *args: module.QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(window, "work", lambda operation, callback: callback(operation()))
    window.enroll_bambu()
    enrolled.assert_not_called()


def test_studio_discovery_formats_candidates_instead_of_python_repr(
    studio_workspace, monkeypatch,
):
    import ipaddress

    from ufm.integrations.printers.discovery import PrinterCandidate
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    candidates = (
        PrinterCandidate("OCTOPRINT", "192.168.1.20", 80, "identified"),
        PrinterCandidate("BAMBU_LAN", "192.168.1.21", 8883, "unverified"),
    )
    monkeypatch.setattr(
        module, "primary_local_network", lambda: ipaddress.IPv4Network("192.168.1.0/24"),
    )
    monkeypatch.setattr(module, "discover_printers", lambda network: candidates)
    monkeypatch.setattr(
        window, "work", lambda operation, callback: callback(operation()),
    )

    window.discover()

    displayed = window.device_result.toPlainText()
    assert "OctoPrint" in displayed and "порт 80" in displayed
    assert "API" in displayed
    assert "Bambu Lab" in displayed and "(possible)" not in displayed
    assert "порт 8883" in displayed
    assert "не підтверджено" in displayed
    assert "PrinterCandidate(" not in displayed


def test_studio_discovery_replaces_stale_results_before_starting_scan(
    studio_workspace, monkeypatch,
):
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    window.device_result.setPlainText("Old unverified candidate")
    monkeypatch.setattr(module, "primary_local_network", lambda: None)
    monkeypatch.setattr(module, "discover_printers", lambda network: ())
    observed = []

    def work(operation, callback):
        observed.append(window.device_result.toPlainText())
        callback(operation())

    monkeypatch.setattr(window, "work", work)

    window.discover()

    assert observed == [window.text("searching_candidates")]
    assert "Old unverified candidate" not in window.device_result.toPlainText()
    assert window.device_result.toPlainText() == window.text("no_candidates")


def test_network_autofill_populates_without_saving_credentials(studio_workspace, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QLineEdit, QPushButton

    from ufm.integrations.printers.bambu_studio import BambuPrinterIdentity
    from ufm.ui import studio_window as module

    app, _, window = studio_workspace
    identity = BambuPrinterIdentity("192.168.0.189", "Workshop", "01P00TEST1234567",
                                    "Bambu Lab P1S", "a" * 64, "issuer")
    monkeypatch.setattr(module, "identify_bambu_printer", lambda host: identity)
    monkeypatch.setattr(
        window, "work", lambda operation, callback, **kwargs: callback(operation()),
    )
    monkeypatch.setattr(module.QMessageBox, "question",
                        lambda *args: module.QMessageBox.StandardButton.Yes)
    results = []

    def interact():
        dialog = window.findChild(QDialog, "bambu-enrollment")
        dialog.findChild(QPushButton, "network-autofill").click()
        app.processEvents()
        results.append(tuple(dialog.findChild(QLineEdit, f"bambu-{key}").text()
                             for key in ("host", "model", "serial", "access_code")))
        dialog.reject()

    QTimer.singleShot(0, interact)
    window.enroll_bambu_network()
    assert results == [(identity.host, identity.model, identity.serial_number, "")]
    assert window.backend.printers() == ()


def test_network_autofill_failure_clears_busy_hint(studio_workspace, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QLabel, QPushButton

    from ufm.ui import studio_window as module

    app, _, window = studio_workspace
    errors = []

    def fail_identification(host):
        raise FileNotFoundError("redacted local failure")

    monkeypatch.setattr(module, "identify_bambu_printer", fail_identification)
    monkeypatch.setattr(window, "error", errors.append)
    result = {}

    def inspect_when_idle():
        dialog = window.findChild(QDialog, "bambu-enrollment")
        if dialog is None:
            return
        if window.tasks:
            QTimer.singleShot(10, inspect_when_idle)
            return
        button = dialog.findChild(QPushButton, "network-autofill")
        result["hint_reset"] = any(
            label.text() == window.text("network_identify_failed")
            for label in dialog.findChildren(QLabel)
        )
        result["button_enabled"] = button.isEnabled()
        dialog.reject()

    def start_identification():
        dialog = window.findChild(QDialog, "bambu-enrollment")
        dialog.findChild(QPushButton, "network-autofill").click()
        QTimer.singleShot(10, inspect_when_idle)

    QTimer.singleShot(0, start_identification)
    window.enroll_bambu_network()
    assert result == {"hint_reset": True, "button_enabled": True}
    assert errors == ["FileNotFoundError"]
    assert window.backend.printers() == ()


def test_bambu_studio_autofill_fills_confirmed_profile_without_saving(
    studio_workspace, monkeypatch,
):
    from unittest.mock import AsyncMock

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QLineEdit, QPushButton

    from ufm.application.ports.secrets import SecretValue
    from ufm.integrations.printers.bambu_studio import BambuStudioProfile
    from ufm.ui import studio_window as module

    app, _, window = studio_workspace
    profile = BambuStudioProfile(
        "192.168.1.50", "TEST-SERIAL-1234", "Bambu Lab P1S",
        SecretValue("test-code-not-real"), "ab" * 32, "test issuer",
    )
    calls = []
    enrolled = AsyncMock()
    monkeypatch.setattr(
        module, "import_bambu_studio_profile",
        lambda host: calls.append(host) or profile,
    )
    monkeypatch.setattr(module, "configure_bambu_printer", enrolled)
    monkeypatch.setattr(
        module.QMessageBox, "question",
        lambda *args: module.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        window, "work", lambda operation, callback, **kwargs: callback(operation()),
    )
    result = {}

    def interact():
        dialog = window.findChild(QDialog, "bambu-enrollment")
        dialog.findChild(QLineEdit, "bambu-host").setText(profile.host)
        dialog.findChild(QPushButton, "bambu-studio-autofill").click()
        app.processEvents()
        result["fields"] = tuple(
            dialog.findChild(QLineEdit, f"bambu-{key}").text()
            for key in ("host", "name", "model", "serial", "access_code")
        )
        result["masked"] = (
            dialog.findChild(QLineEdit, "bambu-access_code").echoMode()
            == QLineEdit.EchoMode.Password
        )
        dialog.reject()

    QTimer.singleShot(0, interact)
    window.enroll_bambu_network()

    assert calls == [profile.host]
    assert result["fields"] == (
        profile.host, profile.model, profile.model, profile.serial_number,
        "test-code-not-real",
    )
    assert result["masked"] is True
    enrolled.assert_not_called()
    assert window.backend.printers() == ()


def test_bambu_studio_autofill_requires_fingerprint_confirmation(
    studio_workspace, monkeypatch,
):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QLineEdit, QMessageBox, QPushButton

    from ufm.application.ports.secrets import SecretValue
    from ufm.integrations.printers.bambu_studio import BambuStudioProfile
    from ufm.ui import studio_window as module

    app, _, window = studio_workspace
    profile = BambuStudioProfile(
        "192.168.1.50", "TEST-SERIAL-1234", "Bambu Lab P1S",
        SecretValue("test-code-not-real"), "ab" * 32, "test issuer",
    )
    monkeypatch.setattr(module, "import_bambu_studio_profile", lambda host: profile)
    monkeypatch.setattr(
        module.QMessageBox, "question",
        lambda *args: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        window, "work", lambda operation, callback, **kwargs: callback(operation()),
    )
    result = {}

    def interact():
        dialog = window.findChild(QDialog, "bambu-enrollment")
        dialog.findChild(QLineEdit, "bambu-host").setText(profile.host)
        dialog.findChild(QPushButton, "bambu-studio-autofill").click()
        app.processEvents()
        result["serial"] = dialog.findChild(QLineEdit, "bambu-serial").text()
        result["code"] = dialog.findChild(QLineEdit, "bambu-access_code").text()
        dialog.reject()

    QTimer.singleShot(0, interact)
    window.enroll_bambu_network()

    assert result == {"serial": "", "code": ""}
    assert window.backend.printers() == ()


def test_studio_remove_printer_requires_selection_and_confirmation(
    studio_workspace, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    from ufm.domain.value_objects import EntityId
    from ufm.infrastructure.studio_backend import StudioPrinter
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    printer_id = EntityId.new()
    selected = StudioPrinter(
        id=str(printer_id), name="Workshop", model="P1S",
        provider="BAMBU_LAN", host="192.168.0.189",
    )
    window.printers = (selected,)
    window.fill(window.printer_table, [[
        selected.name, selected.model, selected.provider, selected.host,
    ]])
    removed = []
    confirmations = iter((QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(
        module.QMessageBox, "question", lambda *args: next(confirmations),
    )
    monkeypatch.setattr(
        module, "remove_configured_printer",
        lambda **kwargs: removed.append(kwargs) or selected.name,
    )
    monkeypatch.setattr(window, "work", lambda operation, callback: callback(operation()))
    monkeypatch.setattr(window, "info", lambda message: None)

    window.remove_printer()  # no current selection
    assert removed == []
    window.printer_table.setCurrentCell(0, 0)
    window.remove_printer()  # explicit cancel
    assert removed == []
    window.remove_printer()  # explicit confirmation

    assert removed == [{
        "engine": window.backend.engine,
        "secret_store": window.container.secrets,
        "printer_id": printer_id,
    }]
    assert window.backend.printers() == ()


def test_studio_edit_printer_details_preserves_connection_profile(
    studio_workspace, monkeypatch
):
    from ufm.domain.value_objects import EntityId
    from ufm.infrastructure.studio_backend import StudioPrinter
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    printer_id = EntityId.new()
    selected = StudioPrinter(
        id=str(printer_id), name="Workshop", model="P1S",
        provider="BAMBU_LAN", host="192.168.0.189",
    )
    window.printers = (selected,)
    window.fill(window.printer_table, [[
        selected.name, selected.model, selected.provider, selected.host,
    ]])
    window.printer_table.setCurrentCell(0, 0)
    calls = []

    def form(_title, fields):
        values = dict(fields)
        values["name"].setText("Office P1S")
        values["model"].setText("Bambu Lab P1S")
        return True

    monkeypatch.setattr(window, "form", form)
    monkeypatch.setattr(
        module, "update_printer_details",
        lambda **kwargs: calls.append(kwargs) or kwargs["name"],
    )
    monkeypatch.setattr(window, "work", lambda operation, callback: callback(operation()))
    monkeypatch.setattr(window, "info", lambda message: None)

    window.edit_printer()

    assert calls == [{
        "engine": window.backend.engine,
        "printer_id": printer_id,
        "name": "Office P1S",
        "model": "Bambu Lab P1S",
    }]
    assert window.backend.printers() == ()


def test_studio_bambu_connection_edit_is_selection_gated_and_masks_access_code(
    studio_workspace, monkeypatch
):
    from PySide6.QtWidgets import QDialog, QLineEdit

    from ufm.domain.value_objects import EntityId
    from ufm.infrastructure.studio_backend import StudioPrinter
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    bambu_id = EntityId.new()
    local = StudioPrinter(
        id="local-printer", name="Local", model="MK4", provider="MOONRAKER",
        host="192.168.0.10",
    )
    bambu = StudioPrinter(
        id=str(bambu_id), name="Workshop", model="P1S", provider="BAMBU_LAN",
        host="192.168.0.189", serial_number="00P00CABCDEF1234",
    )
    window.printers = (local, bambu)
    window.fill(window.printer_table, [[
        printer.name, printer.model, printer.provider, printer.host,
    ] for printer in window.printers])
    window.printer_table.setCurrentCell(0, 0)
    window.update_printer_actions()
    assert not window.edit_printer_connection_button.isEnabled()
    window.printer_table.setCurrentCell(1, 0)
    window.update_printer_actions()
    assert window.edit_printer_connection_button.isEnabled()

    calls = []
    notices = []

    def accept_dialog(dialog):
        dialog.findChild(QLineEdit, "bambu-edit-host").setText("192.168.0.190")
        dialog.findChild(QLineEdit, "bambu-edit-serial").setText("00P00CABCDEF5678")
        code = dialog.findChild(QLineEdit, "bambu-edit-access-code")
        assert code.echoMode() == QLineEdit.EchoMode.Password
        code.setText("new-lan-code")
        return QDialog.DialogCode.Accepted

    async def update(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(QDialog, "exec", accept_dialog)
    monkeypatch.setattr(module, "update_bambu_printer_connection", update)
    monkeypatch.setattr(window, "work", lambda operation, callback: callback(operation()))
    monkeypatch.setattr(window, "info", notices.append)

    window.edit_printer_connection()

    assert len(calls) == 1
    assert calls[0]["printer_id"] == bambu_id
    assert calls[0]["host"] == "192.168.0.190"
    assert calls[0]["serial_number"] == "00P00CABCDEF5678"
    assert calls[0]["access_code"].reveal() == "new-lan-code"
    assert "new-lan-code" not in notices[0]
    window.printers = (local,)
    window.printer_table.setCurrentCell(0, 0)
    window.update_printer_actions()
    assert not window.edit_printer_connection_button.isEnabled()
    window.edit_printer_connection()
    assert len(calls) == 1


def test_printer_monitor_task_stop_disconnects_provider(qt_application):
    import asyncio
    import threading
    import time

    from ufm.application.dto.providers import PrinterEvent
    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.ui.printer_monitor import PrinterMonitorTask

    now = UtcDateTime.now()
    printer_id = EntityId.new()
    provider_id = EntityId.new()
    event = PrinterEvent(
        provider_instance_id=provider_id,
        printer_id=printer_id,
        source_epoch="test-epoch",
        event_key="1",
        kind="current_job",
        observed_at=now,
        received_at=now,
        payload_hash="a" * 64,
    )
    received = threading.Event()
    disconnected = threading.Event()

    class FakeProvider:
        async def connect(self):
            return None

        async def disconnect(self):
            disconnected.set()

        async def subscribe_events(self):
            while True:
                yield event
                await asyncio.sleep(1)

    task = PrinterMonitorTask(FakeProvider)
    task.event_available.connect(lambda: received.set())
    task.start()
    deadline = time.monotonic() + 3
    while not received.is_set() and time.monotonic() < deadline:
        qt_application.processEvents()
        time.sleep(0.01)

    assert received.is_set()
    assert task.take_latest_event() == event
    task.stop()
    assert task.wait(3000)
    qt_application.processEvents()
    assert disconnected.wait(0.5)
    task.deleteLater()
    qt_application.processEvents()


def test_studio_monitor_details_render_confirmed_printer_snapshot(studio_workspace):
    from ufm.application.dto.providers import (
        FeedSlotSnapshot,
        FeedSystemSnapshot,
        Observed,
        PrinterStatusSnapshot,
    )
    from ufm.domain.enums import Availability, ConnectionState, FeedSystemKind
    from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime

    _, _, window = studio_workspace
    now = UtcDateTime.now()

    def known(value):
        return Observed(Availability.KNOWN, now, now, value=value)

    def unknown():
        return Observed(
            Availability.UNKNOWN, now, now,
            reason_code="provider.field_unavailable",
        )

    slot = FeedSlotSnapshot(
        slot_key="0:0", occupancy=known(True), tray_uuid=unknown(), tag_uid=unknown(),
        assigned_spool_id=unknown(), remaining_mass=known(Mass.from_grams("243.5")),
        remaining_percent=known(62),
    )
    unknown_slot = FeedSlotSnapshot(
        slot_key="0:1", occupancy=unknown(), tray_uuid=unknown(), tag_uid=unknown(),
        assigned_spool_id=unknown(), remaining_mass=unknown(),
    )
    ams = FeedSystemSnapshot(
        provider_system_key="ams:0", kind=FeedSystemKind.AMS, slots=(slot, unknown_slot),
        observed_at=now, received_at=now, complete=False,
    )
    status = PrinterStatusSnapshot(
        printer_id=EntityId.new(), connection_state=ConnectionState.ONLINE,
        observed_at=now, received_at=now, progress=known(4200), current_layer=known(42),
        nozzle_temperature_c=known(ExactDecimal.parse("215.5")),
        bed_temperature_c=known(ExactDecimal.parse("60")), feed_systems=(ams,),
    )

    window.show_monitored_status(status)

    details = window.monitor_details.text()
    assert "215.5" in details
    assert "60" in details
    assert "42" in details
    assert "AMS: 2" in details
    slot_details = window.monitor_slot_details.text()
    assert "AMS · 0:0" in slot_details
    assert "243.5 г" in slot_details
    assert "62%" in slot_details
    assert "0:1" in slot_details
    assert "Невідомо" in slot_details
    assert "private" not in slot_details


def test_studio_monitor_failure_messages_are_localized_and_do_not_expose_raw_errors(
    studio_workspace,
) -> None:
    _, _, window = studio_workspace
    known_errors = (
        ("AuthenticationFailed", "monitor_error_authentication"),
        ("TLSVerificationFailed", "monitor_error_tls"),
        ("ProviderUnavailable", "monitor_error_unavailable"),
        ("UnsupportedCapability", "monitor_error_unsupported"),
        ("InvalidObservation", "monitor_error_invalid_data"),
        ("PrinterEventBufferOverflow", "monitor_error_event_overflow"),
    )
    unknown_error = "PrivateDiagnostic_path_and_LAN_code_must_not_be_shown"

    for language in (0, 1):
        window.language = language
        for error_type, translation_key in known_errors:
            window.printer_monitor_failed(error_type)
            message = window.monitor_status.text()
            assert window.text(translation_key) in message
            assert error_type not in message
        window.printer_monitor_failed(unknown_error)
        message = window.monitor_status.text()
        assert window.text("monitor_error_generic") in message
        assert unknown_error not in message


def test_studio_monitor_capabilities_render_observed_availability(studio_workspace):
    from ufm.application.dto.providers import Observed, PrinterCapabilities
    from ufm.domain.enums import Availability
    from ufm.domain.value_objects import UtcDateTime

    _, _, window = studio_workspace
    now = UtcDateTime.now()
    window._monitor_provider = "BAMBU_LAN"

    def observed(availability, value=None):
        return Observed(
            availability, now, now, value=value,
            reason_code=None if availability is Availability.KNOWN else "provider.field_unavailable",
        )

    known_true = observed(Availability.KNOWN, True)
    known_false = observed(Availability.KNOWN, False)
    capabilities = PrinterCapabilities(
        schema_version=1,
        job_detection=known_true,
        progress=known_true,
        layers=observed(Availability.UNKNOWN),
        temperature=known_true,
        camera=known_false,
        pause=observed(Availability.UNSUPPORTED),
        resume=observed(Availability.UNAVAILABLE),
        cancel=known_false,
        filament_usage=known_false,
        multi_material=known_true,
        file_metadata=known_false,
        local_connection=known_true,
        cloud_connection=known_false,
        push_events=known_true,
        polling=known_false,
    )

    window.show_monitored_capabilities(capabilities)

    rendered = window.monitor_capabilities.text()
    assert window.text("capability_job_detection") in rendered
    assert window.text("capability_layers") in rendered
    assert window.text("monitor_capability_yes") in rendered
    assert window.text("monitor_capability_no") in rendered
    assert window.text("monitor_capability_unknown") in rendered
    assert window.text("monitor_capability_unavailable") in rendered
    assert window.text("monitor_capability_unsupported") in rendered
    assert window.text("monitor_provider_bambu_lan") in rendered
    assert now.isoformat() in rendered


def test_printer_monitor_retries_transient_errors_with_capped_backoff(qt_application):
    import asyncio
    import threading
    import time

    from ufm.application.ports.printers import ProviderUnavailable
    from ufm.ui.printer_monitor import PrinterMonitorTask

    attempts = []
    connected = threading.Event()
    disconnected = threading.Event()

    class FakeProvider:
        async def connect(self):
            attempts.append("connect")
            if len(attempts) == 1:
                raise ProviderUnavailable()
            connected.set()

        async def disconnect(self):
            disconnected.set()

        async def subscribe_events(self):
            await asyncio.sleep(30)
            if False:
                yield None

    class FastRetryMonitor(PrinterMonitorTask):
        @staticmethod
        def _retry_delay(retry_number):
            return 0.01

    states = []
    task = FastRetryMonitor(FakeProvider)
    task.state_changed.connect(states.append)
    task.start()
    deadline = time.monotonic() + 3
    try:
        while (
            not connected.is_set() or not {"offline", "retrying"}.issubset(states)
        ) and time.monotonic() < deadline:
            qt_application.processEvents()
            time.sleep(0.01)

        assert connected.is_set()
        assert attempts == ["connect", "connect"]
        assert "offline" in states
        assert "retrying" in states
    finally:
        task.stop()
        if not task.wait(3000):
            raise RuntimeError("printer_monitor_test_thread_did_not_stop")
        qt_application.processEvents()
        task.deleteLater()
        qt_application.processEvents()
    assert disconnected.is_set()


def test_printer_monitor_preserves_pending_events_in_receive_order(qt_application):
    from ufm.application.dto.providers import PrinterEvent
    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.ui.printer_monitor import PrinterMonitorTask

    base = dict(
        provider_instance_id=EntityId.new(), printer_id=EntityId.new(),
        source_epoch="epoch", kind="current_job", observed_at=UtcDateTime.now(),
        received_at=UtcDateTime.now(), payload_hash="c" * 64,
    )
    first = PrinterEvent(event_key="1", **base)
    latest = PrinterEvent(event_key="2", **base)
    task = PrinterMonitorTask(lambda: None)
    notifications = []
    task.event_available.connect(lambda: notifications.append(True))

    task._publish(first)
    task._publish(latest)

    assert notifications == [True]
    assert task.take_pending_events() == (first, latest)
    task._publish(first)
    assert notifications == [True, True]
    assert task.take_latest_event() == first


def test_printer_monitor_reports_full_bounded_event_buffer_without_dropping_oldest(qt_application):
    from ufm.application.dto.providers import PrinterEvent
    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.ui.printer_monitor import PrinterMonitorTask

    base = dict(
        provider_instance_id=EntityId.new(), printer_id=EntityId.new(),
        source_epoch="epoch", kind="current_job", observed_at=UtcDateTime.now(),
        received_at=UtcDateTime.now(), payload_hash="d" * 64,
    )
    first = PrinterEvent(event_key="1", **base)
    overflow = PrinterEvent(event_key="2", **base)
    task = PrinterMonitorTask(lambda: None)
    task._event_buffer_limit = 1

    assert task._publish(first)
    assert not task._publish(overflow)
    assert task.take_pending_events() == (first,)


def test_printer_monitor_does_not_retry_non_retryable_authentication_error(qt_application):
    import asyncio
    import time

    from ufm.application.ports.printers import AuthenticationFailed
    from ufm.ui.printer_monitor import PrinterMonitorTask

    attempts = []
    failures = []

    class FakeProvider:
        async def connect(self):
            attempts.append(1)
            raise AuthenticationFailed()

        async def disconnect(self):
            return None

        async def subscribe_events(self):
            await asyncio.sleep(0)
            if False:
                yield None

    task = PrinterMonitorTask(FakeProvider)
    task.failed.connect(failures.append)
    task.start()
    deadline = time.monotonic() + 3
    while task.isRunning() and time.monotonic() < deadline:
        qt_application.processEvents()
        time.sleep(0.01)

    assert task.wait(1000)
    qt_application.processEvents()
    assert attempts == [1]
    assert failures == ["AuthenticationFailed"]
    task.deleteLater()
    qt_application.processEvents()


def test_printer_monitor_can_stop_during_reconnect_backoff(qt_application):
    import time

    from ufm.application.ports.printers import ProviderUnavailable
    from ufm.ui.printer_monitor import PrinterMonitorTask

    disconnected = []

    class FakeProvider:
        async def connect(self):
            raise ProviderUnavailable()

        async def disconnect(self):
            disconnected.append(True)

        async def subscribe_events(self):
            if False:
                yield None

    states = []
    task = PrinterMonitorTask(FakeProvider)
    task.state_changed.connect(states.append)
    task.start()
    deadline = time.monotonic() + 3
    while "retrying" not in states and time.monotonic() < deadline:
        qt_application.processEvents()
        time.sleep(0.01)

    assert "retrying" in states
    assert disconnected == [True]
    task.stop()
    assert task.wait(1000)
    qt_application.processEvents()
    assert disconnected == [True]
    task.deleteLater()
    qt_application.processEvents()


def test_printer_monitor_reconnects_after_provider_reports_stale(qt_application):
    import asyncio
    import time

    from ufm.application.dto.providers import ProviderHealth
    from ufm.domain.enums import ProviderHealthState
    from ufm.domain.value_objects import UtcDateTime
    from ufm.ui.printer_monitor import PrinterMonitorTask

    attempts = []
    disconnected = []
    streams_started = []

    class FakeProvider:
        def __init__(self, ordinal):
            self.ordinal = ordinal

        async def connect(self):
            attempts.append(self.ordinal)

        async def disconnect(self):
            disconnected.append(self.ordinal)

        async def health(self):
            state = (
                ProviderHealthState.DEGRADED
                if self.ordinal == 1 else ProviderHealthState.HEALTHY
            )
            return ProviderHealth(
                state=state, checked_at=UtcDateTime.now(),
                reason_code="provider.stale", retryable=True,
            )

        async def subscribe_events(self):
            streams_started.append(self.ordinal)
            await asyncio.sleep(30)
            if False:
                yield None

    def factory():
        return FakeProvider(len(attempts) + 1)

    class FastHealthMonitor(PrinterMonitorTask):
        _health_check_interval_seconds = 0.01

    states = []
    task = FastHealthMonitor(factory)
    task.state_changed.connect(states.append)
    task.start()
    deadline = time.monotonic() + 3
    while (
        len(attempts) < 2 or "stale" not in states or 2 not in streams_started
    ) and time.monotonic() < deadline:
        qt_application.processEvents()
        time.sleep(0.01)

    assert attempts[:2] == [1, 2]
    assert "stale" in states
    assert 2 in streams_started
    assert disconnected.count(1) == 1
    task.stop()
    assert task.wait(3000)
    qt_application.processEvents()
    assert disconnected.count(2) == 1
    task.deleteLater()
    qt_application.processEvents()


def test_printer_monitor_reconnects_after_system_resume(qt_application):
    import asyncio
    import time

    from ufm.application.dto.providers import ProviderHealth
    from ufm.domain.enums import ProviderHealthState
    from ufm.domain.value_objects import UtcDateTime
    from ufm.ui.printer_monitor import PrinterMonitorTask

    attempts = []
    disconnected = []
    streams_started = []

    class FakeProvider:
        async def connect(self):
            attempts.append(len(attempts) + 1)

        async def disconnect(self):
            disconnected.append(len(attempts))

        async def health(self):
            return ProviderHealth(
                state=ProviderHealthState.HEALTHY,
                checked_at=UtcDateTime.now(),
                reason_code="provider.connected",
                retryable=False,
            )

        async def subscribe_events(self):
            streams_started.append(len(attempts))
            await asyncio.sleep(30)
            if False:
                yield None

    class FakeResumeDetector:
        def __init__(self):
            self.calls = 0

        def resumed(self):
            self.calls += 1
            return self.calls == 1

    class FastHealthMonitor(PrinterMonitorTask):
        _health_check_interval_seconds = 0.01

    states = []
    task = FastHealthMonitor(FakeProvider)
    task._resume_detector = FakeResumeDetector()
    task.state_changed.connect(states.append)
    task.start()
    deadline = time.monotonic() + 3
    while (
        len(attempts) < 2 or "stale" not in states or 2 not in streams_started
    ) and time.monotonic() < deadline:
        qt_application.processEvents()
        time.sleep(0.01)

    assert attempts == [1, 2]
    assert "stale" in states
    assert 2 in streams_started
    assert disconnected.count(1) == 1
    task.stop()
    assert task.wait(3000)
    qt_application.processEvents()
    assert disconnected.count(2) == 1
    task.deleteLater()
    qt_application.processEvents()


def test_studio_monitor_is_opt_in_and_stops_when_window_closes(
    studio_workspace, monkeypatch
):
    import asyncio
    import threading
    import time

    from PySide6.QtWidgets import QMessageBox

    from ufm.application.dto.providers import PrinterEvent
    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.infrastructure.studio_backend import StudioPrinter
    from ufm.ui import studio_window as module

    app, _, window = studio_workspace
    printer_id = EntityId.new()
    provider_id = EntityId.new()
    event = PrinterEvent(
        provider_instance_id=provider_id,
        printer_id=printer_id,
        source_epoch="test-epoch",
        event_key="1",
        kind="current_job",
        observed_at=UtcDateTime.now(),
        received_at=UtcDateTime.now(),
        payload_hash="b" * 64,
    )
    disconnected = threading.Event()
    created_for = []

    class FakeProvider:
        async def connect(self):
            return None

        async def disconnect(self):
            disconnected.set()

        async def subscribe_events(self):
            yield event
            await asyncio.sleep(30)

    selected = StudioPrinter(
        id=str(printer_id), name="Workshop", model="P1S",
        provider="BAMBU_LAN", host="192.168.0.189",
    )
    window.printers = (selected,)
    window.fill(window.printer_table, [[
        selected.name, selected.model, selected.provider, selected.host,
    ]])
    window.printer_table.setCurrentCell(0, 0)

    def make_provider(**kwargs):
        created_for.append(kwargs["printer_id"])
        return FakeProvider()

    monkeypatch.setattr(module, "configured_printer_provider", make_provider)
    monkeypatch.setattr(
        module.QMessageBox, "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    assert window._monitor_task is None
    assert created_for == []  # a new app/window never restores printer access silently
    window.toggle_printer_monitor()
    assert window._monitor_task is not None

    deadline = time.monotonic() + 3
    while not window.monitor_status.text().startswith("Workshop ·") and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert "Workshop" in window.monitor_status.text()
    assert created_for == [printer_id]

    window.close()  # closeEvent requests cancellation and defers destruction
    deadline = time.monotonic() + 3
    while window._monitor_task is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert window._monitor_task is None
    assert disconnected.wait(0.5)


def test_studio_import_preview_shows_target_collisions(
    studio_workspace, monkeypatch, tmp_path,
) -> None:
    import sqlite3

    from PySide6.QtWidgets import (
        QDialog,
        QFileDialog,
        QInputDialog,
        QLabel,
        QTableWidget,
    )

    from tests.integration.test_spoolman_importer import create_spoolman_fixture
    from ufm.integrations.spoolman.importer import import_spoolman_database

    app, backend, window = studio_workspace
    source = tmp_path / "spoolman.sqlite3"
    create_spoolman_fixture(source)
    key = "d" * 24
    import_spoolman_database(
        source, backend.paths, engine=backend.engine, source_instance_key=key,
    )
    connection = sqlite3.connect(source)
    try:
        connection.execute("UPDATE filament SET name='PLA Renamed' WHERE id=1")
        connection.execute(
            "UPDATE spool SET used_weight=210.0, lot_nr='B-2',"
            " location='Shelf 2' WHERE id=1",
        )
        connection.execute("UPDATE spool SET archived=0 WHERE id=2")
        connection.execute(
            "INSERT INTO spool (id,filament_id,used_weight,archived)"
            " VALUES (4, 1, 10.0, 0)",
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(
        window, "work", lambda operation, callback, **kwargs: callback(operation()),
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), ""),
    )
    monkeypatch.setattr(
        QInputDialog, "getItem",
        lambda *args, **kwargs: (args[3][1], True),
    )
    captured: dict[str, object] = {}

    def capture_dialog(dialog):
        table = dialog.findChild(QTableWidget)
        captured["rows"] = [
            [table.item(row, column).text()
             for column in range(table.columnCount())]
            for row in range(table.rowCount())
        ]
        captured["labels"] = [
            label.text() for label in dialog.findChildren(QLabel)
        ]
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", capture_dialog)
    window.import_database()
    app.processEvents()

    rows = captured["rows"]
    assert len(rows) == 4
    assert rows[0][0] == "1" and rows[0][11] == window.text("import_target_conflict")
    assert window.text("import_difffield_catalog_profile") in rows[0][12]
    assert window.text("import_difffield_opening_stock") in rows[0][12]
    assert window.text("import_difffield_lot_number") in rows[0][13]
    assert window.text("import_difffield_storage_location") in rows[0][13]
    assert rows[1][11] == window.text("import_target_preserved")
    assert window.text("import_difffield_lifecycle") in rows[1][13]
    assert rows[2][11] == window.text("import_target_consistent")
    assert rows[3][11] == window.text("import_target_new")
    summary = " ".join(captured["labels"])
    assert "нових 1" in summary and "конфліктів 1" in summary
    assert len(backend.spools()) == 3


def test_user_facing_strings_have_no_legacy_brand_names() -> None:
    root = Path(__file__).resolve().parents[2]
    strings = json.loads(
        (root / "src" / "ufm" / "ui" / "studio_strings.json").read_text("utf-8")
    )
    for pair in strings.values():
        for value in pair:
            lowered = value.lower()
            assert "spoolman" not in lowered
            assert "haspelsync" not in lowered
    for locale in ("uk-UA", "en-US"):
        catalog = json.loads(
            (root / "src" / "ufm" / "ui" / "i18n" / f"{locale}.json").read_text("utf-8")
        )
        for value in catalog.values():
            lowered = value.lower()
            assert "spoolman" not in lowered
            assert "haspelsync" not in lowered


def test_niche_buttons_are_hidden_from_studio_pages(studio_workspace) -> None:
    from PySide6.QtWidgets import QPushButton

    _, _, window = studio_workspace
    hidden_texts = {
        window.text(key)
        for key in ("haspel_import_preview", "inspect_slice_file", "batch_print_qr_labels")
    }
    visible_texts = {button.text() for button in window.findChildren(QPushButton)}
    assert hidden_texts.isdisjoint(visible_texts)


def test_devices_page_auto_scan_runs_once_per_opening(studio_workspace, monkeypatch) -> None:
    import ipaddress

    from ufm.integrations.printers.discovery import PrinterCandidate
    from ufm.ui import studio_window as module

    _, _, window = studio_workspace
    calls = []

    def fake_discover(network):
        calls.append(network)
        return (PrinterCandidate("BAMBU_LAN", "192.168.1.30", 8883, "unverified"),)

    monkeypatch.setattr(
        module, "primary_local_network",
        lambda: ipaddress.IPv4Network("192.168.1.0/24"),
    )
    monkeypatch.setattr(module, "discover_printers", fake_discover)
    monkeypatch.setattr(
        window, "work",
        lambda operation, callback, **kwargs: callback(operation()),
    )

    window.switch_page(1)
    assert len(calls) == 1
    assert window.candidate_list.count() == 1
    window.candidate_list.setCurrentRow(0)
    assert window.connect_candidate_button.isEnabled()

    window.refresh()
    assert len(calls) == 1

    window.switch_page(0)
    window.switch_page(1)
    assert len(calls) == 2


def test_connect_candidate_prefills_bambu_enrollment_without_saving(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QLineEdit

    from ufm.integrations.printers.bambu_studio import BambuPrinterIdentity
    from ufm.integrations.printers.discovery import PrinterCandidate
    from ufm.ui import studio_window as module

    app, _, window = studio_workspace
    identity = BambuPrinterIdentity(
        "192.168.0.30", "Workshop", "01P00TEST1234567",
        "Bambu Lab P1S", "b" * 64, "issuer",
    )
    monkeypatch.setattr(module, "identify_bambu_printer", lambda host: identity)
    monkeypatch.setattr(
        window, "work",
        lambda operation, callback, **kwargs: callback(operation()),
    )
    monkeypatch.setattr(
        module.QMessageBox, "question",
        lambda *args: module.QMessageBox.StandardButton.Yes,
    )
    candidate = PrinterCandidate("BAMBU_LAN", "192.168.0.30", 8883, "unverified")
    observed = {}

    def check():
        dialog = window.findChild(QDialog, "bambu-enrollment")
        if dialog is None:
            QTimer.singleShot(10, check)
            return
        serial = dialog.findChild(QLineEdit, "bambu-serial").text()
        if not serial:
            QTimer.singleShot(10, check)
            return
        observed["fields"] = tuple(
            dialog.findChild(QLineEdit, f"bambu-{key}").text()
            for key in ("host", "model", "serial", "access_code")
        )
        dialog.reject()

    QTimer.singleShot(0, check)
    window.enroll_bambu_network(candidate)
    app.processEvents()

    assert observed["fields"] == (
        "192.168.0.30", "Bambu Lab P1S", "01P00TEST1234567", "",
    )
    assert window.backend.printers() == ()


def _sync_work_with_errors(window):
    def run(operation, callback, **_kwargs):
        try:
            result = operation()
        except Exception as error:
            window.error(type(error).__name__)
        else:
            callback(result)

    return run


def test_system_language_and_log_level_save_or_show_error(
    studio_workspace, monkeypatch,
) -> None:
    import ufm.ui.studio_window as module
    from ufm.bootstrap.settings import load_settings

    _app, _backend, window = studio_workspace
    settings_path = window.backend.paths.config / "settings.json"
    infos: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(window, "info", infos.append)
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        module.QMessageBox, "information", lambda *_a, **_k: None,
    )

    index = window.locale_selector.findData("en-US")
    window.locale_selector.setCurrentIndex(index)
    window.save_language()
    assert load_settings(settings_path).locale == "en-US"
    assert window.settings.locale == "en-US"

    index = window.log_level_selector.findData("DEBUG")
    window.log_level_selector.setCurrentIndex(index)
    window.save_log_level()
    assert load_settings(settings_path).log_level == "DEBUG"
    assert window.settings.log_level == "DEBUG"

    before = window.settings
    monkeypatch.setattr(
        module, "save_settings",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")),
    )
    window.save_language()
    window.save_log_level()
    assert errors == ["settings.invalid", "settings.invalid"]
    assert window.settings == before
    assert load_settings(settings_path).locale == "en-US"


def test_system_safe_logs_empty_rendered_and_unavailable(
    studio_workspace, monkeypatch,
) -> None:
    from PySide6.QtWidgets import QDialog, QMessageBox, QTextEdit

    import ufm.ui.studio_window as module

    _app, _backend, window = studio_workspace
    log_path = window.backend.paths.logs / "ufm.log"
    captured: list[QDialog] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        module.QDialog, "exec",
        lambda dialog: captured.append(dialog) or 0,
    )
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda _p, _t, message: warnings.append(message),
    )

    window.view_safe_logs()
    assert captured[-1].findChild(QTextEdit).toPlainText() == window.text("logs_empty")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    valid = json.dumps({
        "timestamp": "2026-11-17T10:00:00+00:00",
        "level": "INFO", "event": "startup_validated",
    })
    log_path.write_text(valid + "\nnot-json\n", encoding="utf-8")
    window.view_safe_logs()
    rendered = captured[-1].findChild(QTextEdit).toPlainText()
    assert "startup_validated" in rendered
    assert window.text("log_record_omitted") in rendered

    from pathlib import Path as _Path

    monkeypatch.setattr(
        _Path, "read_bytes",
        lambda _self: (_ for _ in ()).throw(PermissionError("denied")),
    )
    window.view_safe_logs()
    assert warnings and window.text("logs.unavailable") in warnings[-1]


def test_system_export_inventory_csv_states(
    studio_workspace, monkeypatch, tmp_path,
) -> None:
    from PySide6.QtWidgets import QFileDialog

    app, backend, window = studio_workspace
    monkeypatch.setattr(window, "work", _sync_work_with_errors(window))
    output = tmp_path / "inventory.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *_a, **_k: (str(output), "CSV (*.csv)"),
    )
    infos: list[str] = []
    monkeypatch.setattr(window, "info", infos.append)

    window.export_inventory()
    content = output.read_bytes()
    assert content.startswith(b"\xef\xbb\xbf")
    assert b"spool_id" in content and b"Green" not in content

    profile = backend.add_material("PLA", "PLA")
    backend.add_spool("Exported spool", profile)
    window.export_inventory()
    content = output.read_bytes().decode("utf-8-sig")
    assert "Exported spool" in content
    assert infos and "inventory" in infos[-1].lower() or infos

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *_a, **_k: ("", "CSV (*.csv)"),
    )
    before = output.read_bytes()
    window.export_inventory()
    assert output.read_bytes() == before

    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *_a, **_k: (str(tmp_path / "fail.csv"), "CSV (*.csv)"),
    )
    monkeypatch.setattr(
        backend, "spools",
        lambda: (_ for _ in ()).throw(OSError("offline")),
    )
    window.export_inventory()
    assert errors == ["OSError"]
    assert not (tmp_path / "fail.csv").exists()


def test_system_export_diagnostics_consent_decline_and_unavailable(
    studio_workspace, monkeypatch, tmp_path,
) -> None:
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    _app, _backend, window = studio_workspace
    output = tmp_path / "diagnostics.json"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *_a, **_k: (str(output), "JSON (*.json)"),
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda _p, _t, message: warnings.append(message),
    )
    monkeypatch.setattr(
        QMessageBox, "information", lambda *_a, **_k: None,
    )

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.No,
    )
    window.export_diagnostics()
    assert not output.exists()

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.Yes,
    )
    window.export_diagnostics()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "manifest" in payload

    from pathlib import Path as _Path

    monkeypatch.setattr(
        _Path, "read_bytes",
        lambda _self: (_ for _ in ()).throw(PermissionError("denied")),
    )
    window.export_diagnostics()
    assert warnings and window.text("diagnostics_failed") in warnings[-1]


def test_system_backup_creates_snapshot_or_reports_error(
    studio_workspace, monkeypatch,
) -> None:
    app, backend, window = studio_workspace
    monkeypatch.setattr(window, "work", _sync_work_with_errors(window))
    infos: list[str] = []
    monkeypatch.setattr(window, "info", infos.append)

    window.backup()
    backups = tuple((window.backend.paths.data / "backups").rglob("*.sqlite3"))
    assert backups
    assert infos and str(backups[0].parent) in infos[-1] or infos

    errors: list[str] = []
    monkeypatch.setattr(window, "error", errors.append)
    monkeypatch.setattr(
        backend, "backup",
        lambda: (_ for _ in ()).throw(OSError("offline")),
    )
    window.backup()
    assert errors == ["OSError"]
def test_job_detail_text_explains_decision_fields(studio_workspace) -> None:
    from ufm.infrastructure.studio_backend import (
        StudioJobDetail,
        StudioJobLedgerEntry,
        StudioJobMaterialInfo,
        StudioJobSegmentInfo,
    )

    _app, _backend, window = studio_workspace
    info = StudioJobDetail(
        id="job-1", name="Bracket", file_name="bracket.3mf", plate_name="Plate A",
        printer_name="P1S", status="RUNNING", finalization_state="FINALIZED",
        detected_at="2026-11-18T10:00:00+00:00",
        started_at="2026-11-18T10:01:00+00:00", completed_at=None,
        source_type="printer", slicer_type="Bambu Studio",
        progress_bp=10000, current_layer=20, total_layers=20,
        materials=(StudioJobMaterialInfo(
            id="m1", channel_key="AMS-A1", tool_index=0,
            filament_name="Generic PLA", estimated_mass_mg=12_500_000,
        ),),
        segments=(StudioJobSegmentInfo(
            print_job_material_id="m1", tool_index=0,
            assignment_state="ASSIGNED", source="RFID", confidence_bp=9500,
            started_at="2026-11-18T10:01:00+00:00", ended_at=None,
            spool_name="Black PLA spool",
        ),),
        ledger=(StudioJobLedgerEntry(
            id="t1", spool_name="Black PLA spool", sequence=7,
            transaction_type="PRINT_CONSUMPTION", delta_mg=-12_000_000,
            source_type="THREE_MF", confidence_bp=9000,
            estimate_policy_version="safe-v1",
            description="partial print",
            created_at="2026-11-18T12:00:00+00:00",
        ),),
    )
    rendered = window._job_detail_text(info)
    assert "bracket.3mf" in rendered and "Plate A" in rendered
    assert "Generic PLA" in rendered and "12500 g" in rendered
    assert "Black PLA spool" in rendered
    assert "95%" in rendered and "90%" in rendered
    assert "safe-v1" in rendered and "partial print" in rendered
    assert window.text("PRINT_CONSUMPTION") in rendered


def test_show_print_jobs_empty_state(studio_workspace, monkeypatch) -> None:
    _app, _backend, window = studio_workspace
    infos: list[str] = []
    monkeypatch.setattr(window, "info", infos.append)
    window.show_print_jobs()
    assert infos == [window.text("jobs_empty")]
