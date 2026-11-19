"""Read-model checks for print job detail aggregation (no printer/network)."""

from __future__ import annotations

import pytest
from sqlalchemy import insert


@pytest.fixture
def job_backend(tmp_path):
    from ufm.bootstrap.app_container import create_container
    from ufm.bootstrap.settings import AppSettings
    from ufm.infrastructure.persistence.sqlite.engine import create_sqlite_engine
    from ufm.infrastructure.persistence.sqlite.migrate import migrate_database
    from ufm.infrastructure.studio_backend import StudioBackend
    from ufm.platform.common.paths import AppPaths

    paths = AppPaths.resolve(tmp_path)
    container = create_container(AppSettings(), paths)
    engine = create_sqlite_engine(paths.data / "ufm.sqlite3")
    try:
        migrate_database(engine)
        yield StudioBackend(engine, paths)
    finally:
        engine.dispose()
        container.close()


def test_recent_jobs_and_job_detail_empty_states(job_backend) -> None:
    from ufm.domain.value_objects import EntityId

    assert job_backend.recent_jobs() == ()
    assert job_backend.job_detail(str(EntityId.new())) is None


def test_job_detail_aggregates_job_fields(job_backend) -> None:
    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.infrastructure.persistence.models.schema import print_job, printer
    from ufm.integrations.printers.configuration import ensure_local_device

    backend = job_backend
    device = ensure_local_device(backend.engine)
    now = UtcDateTime.now()
    printer_id = EntityId.new()
    job_id = EntityId.new()
    with backend.engine.begin() as connection:
        connection.execute(insert(printer).values(
            id=printer_id, device_id=device, created_at=now, updated_at=now,
            revision=1, deleted_at=None, name="Detail Printer", enabled=True,
        ))
        connection.execute(insert(print_job).values(
            id=job_id, device_id=device, created_at=now, updated_at=now,
            revision=1, deleted_at=None, printer_id=printer_id,
            source_type="printer", status="RUNNING",
            finalization_state="NOT_STARTED", detected_at=now,
            name="Bracket job", file_name="bracket.3mf", plate_name="Plate A",
            slicer_type="Bambu Studio", started_at=now,
            progress_bp=5000, current_layer=10, total_layers=20,
        ))

    rows = backend.recent_jobs()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == str(job_id)
    assert row.printer_name == "Detail Printer"
    assert row.status == "RUNNING"
    assert row.file_name == "bracket.3mf"

    detail = backend.job_detail(str(job_id))
    assert detail is not None
    assert detail.printer_name == "Detail Printer"
    assert detail.plate_name == "Plate A"
    assert detail.slicer_type == "Bambu Studio"
    assert detail.progress_bp == 5000
    assert detail.materials == ()
    assert detail.segments == ()
    assert detail.ledger == ()


def test_open_reconciliation_tasks_empty(job_backend) -> None:
    assert job_backend.open_reconciliation_tasks() == ()


def test_open_reconciliation_tasks_lists_open_with_names(job_backend) -> None:
    from ufm.domain.entities import ReconciliationTask
    from ufm.domain.enums import ReconciliationState, Severity
    from ufm.domain.value_objects import EntityId, UtcDateTime
    from ufm.infrastructure.persistence.sqlite.unit_of_work import SQLiteUnitOfWork
    from ufm.integrations.printers.configuration import ensure_local_device

    backend = job_backend
    device = ensure_local_device(backend.engine)
    now = UtcDateTime.now()
    with SQLiteUnitOfWork(backend.engine) as work:
        work.reconciliations.add_task(ReconciliationTask(
            id=EntityId.new(), device_id=device, created_at=now, updated_at=now,
            revision=1, reason_code="RESERVATION_SHORTAGE", severity=Severity.WARNING,
            state=ReconciliationState.OPEN, dedupe_key="studio-recon-test-1",
            suggested_action="review_spool_stock",
        ))
        work.reconciliations.add_task(ReconciliationTask(
            id=EntityId.new(), device_id=device, created_at=now, updated_at=now,
            revision=1, reason_code="DONE_TASK", severity=Severity.INFO,
            state=ReconciliationState.RESOLVED, dedupe_key="studio-recon-test-2",
            resolved_at=now, resolved_by=device, resolution_notes="ok",
        ))
        work.commit()

    tasks = backend.open_reconciliation_tasks()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.reason_code == "RESERVATION_SHORTAGE"
    assert task.severity == "WARNING"
    assert task.state == "OPEN"
    assert task.suggested_action == "review_spool_stock"
    assert task.spool_name is None
    assert task.job_name is None
