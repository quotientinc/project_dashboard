"""
Data management endpoints -- CSV import/export, Deltek sync, database backup.
"""
import io
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.database import DatabaseManager, get_db
from app.models.common import ImportSummary, MessageResponse
from app.services.csv_importer import (
    TimesheetCSVImporter,
    EmployeeMasterCSVImporter,
    EmployeeReferenceCSVImporter,
    ProjectReferenceCSVImporter,
    AllocationCSVImporter,
    MonthsCSVImporter,
)

router = APIRouter(prefix="/data", tags=["Data Management"])

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------

@router.post("/import/csv/timesheet", response_model=ImportSummary)
async def import_timesheet_csv(
    file: UploadFile = File(..., description="Timesheet CSV file"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Import timesheet data from a CSV upload.

    Extracts projects, employees, and time entries from the CSV.
    Projects and employees are inserted with INSERT OR IGNORE.
    Time entries are bulk-inserted.
    """
    # Save uploaded file to a temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        importer = TimesheetCSVImporter(tmp_path)
        projects, employees, time_entries, summary = importer.import_all()

        db.bulk_insert_projects(projects)
        db.bulk_insert_employees(employees)
        db.bulk_insert_time_entries(time_entries)

        return ImportSummary(
            message="Timesheet CSV imported successfully",
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Timesheet CSV import failed")
        raise HTTPException(status_code=400, detail=f"CSV import failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/import/csv/employees", response_model=ImportSummary)
async def import_employee_csv(
    file: UploadFile = File(..., description="Employee master CSV file"),
    format: str = Query("master", description="CSV format: 'master' or 'reference'"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Import employee data from a CSV upload.

    Supports two formats:
    - 'master': Simple id, name, hire_date, etc.
    - 'reference': Deltek EmployeeReference.csv format with extended fields.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if format == "reference":
            importer = EmployeeReferenceCSVImporter(tmp_path)
        else:
            importer = EmployeeMasterCSVImporter(tmp_path)

        employees, summary = importer.import_all()
        db.upsert_employees(employees, preserve_fields=["skills", "overhead_allocation", "target_allocation"])

        return ImportSummary(
            message=f"Employee CSV ({format}) imported successfully",
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Employee CSV import failed (format=%s)", format)
        raise HTTPException(status_code=400, detail=f"Employee CSV import failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/import/csv/projects", response_model=ImportSummary)
async def import_project_csv(
    file: UploadFile = File(..., description="Project reference CSV file"),
    db: DatabaseManager = Depends(get_db),
):
    """Import project data from a ProjectReference CSV upload."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        importer = ProjectReferenceCSVImporter(tmp_path)
        projects, summary = importer.import_all()
        db.upsert_projects(projects, preserve_fields=["description", "status", "project_manager"])

        return ImportSummary(
            message="Project reference CSV imported successfully",
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Project CSV import failed")
        raise HTTPException(status_code=400, detail=f"Project CSV import failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/import/csv/allocations", response_model=ImportSummary)
async def import_allocation_csv(
    file: UploadFile = File(..., description="Allocation CSV file"),
    db: DatabaseManager = Depends(get_db),
):
    """Import allocation data from a CSV upload."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        importer = AllocationCSVImporter(tmp_path)
        allocations, summary = importer.import_all()

        # Validate foreign keys
        is_valid, errors = db.validate_allocation_foreign_keys(allocations)
        if not is_valid:
            summary["foreign_key_errors"] = errors

        db.bulk_insert_allocations(allocations)

        return ImportSummary(
            message="Allocation CSV imported successfully",
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Allocation CSV import failed")
        raise HTTPException(status_code=400, detail=f"Allocation CSV import failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/import/csv/months", response_model=ImportSummary)
async def import_months_csv(
    file: UploadFile = File(..., description="Months reference CSV file"),
    db: DatabaseManager = Depends(get_db),
):
    """Import month/holiday reference data from a CSV upload."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        importer = MonthsCSVImporter(tmp_path)
        months, summary = importer.import_all()
        db.bulk_upsert_months(months)

        return ImportSummary(
            message="Months CSV imported successfully",
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Months CSV import failed")
        raise HTTPException(status_code=400, detail=f"Months CSV import failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Deltek API Sync
# ---------------------------------------------------------------------------

@router.post("/import/deltek", response_model=ImportSummary)
def sync_from_deltek(
    start_date: str = Query(..., description="Sync start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Sync end date (YYYY-MM-DD)"),
    employee_ids: Optional[list[str]] = Query(None, description="Filter by employee IDs"),
    project_ids: Optional[list[str]] = Query(None, description="Filter by project IDs"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Trigger a Deltek Costpoint API sync for the given date range.

    Requires Deltek API to be configured via environment variables.
    """
    if not settings.deltek_api_enabled or not settings.deltek_api_base_url:
        raise HTTPException(
            status_code=400,
            detail="Deltek API is not configured. Set DELTEK_API_ENABLED=true and provide API credentials.",
        )

    try:
        from app.services.deltek_api_client import DeltekCostpointAPI
        from app.services.deltek_api_importer import DeltekTimesheetAPIImporter

        with DeltekCostpointAPI() as api:
            raw_data = api.fetch_timesheets(
                start_date=start_date,
                end_date=end_date,
                employee_ids=employee_ids,
                project_ids=project_ids,
            )

        importer = DeltekTimesheetAPIImporter(raw_data)
        projects = importer.extract_projects()
        employees = importer.extract_employees()
        time_entries = importer.extract_time_entries()
        summary = importer.get_summary()

        db.upsert_projects(projects, preserve_fields=["description", "status", "project_manager"])
        db.upsert_employees(employees, preserve_fields=["skills", "overhead_allocation", "target_allocation"])
        db.bulk_insert_time_entries(time_entries)

        return ImportSummary(message="Deltek sync completed", summary=summary)

    except ImportError:
        raise HTTPException(status_code=500, detail="Deltek API modules not found")
    except Exception as exc:
        logger.exception("Deltek sync failed")
        raise HTTPException(status_code=500, detail=f"Deltek sync failed: {exc}")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/export/{format}")
def export_data(
    format: str,
    tables: list[str] = Query(
        ["projects", "employees", "allocations", "time_entries", "expenses", "months"],
        description="Tables to include in export",
    ),
    db: DatabaseManager = Depends(get_db),
):
    """
    Export database tables as CSV or Excel.

    Supported formats: 'csv' (ZIP of CSVs) or 'excel' (single XLSX with sheets).
    """
    if format not in ("csv", "excel"):
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'excel'")

    valid_tables = {"projects", "employees", "allocations", "time_entries", "expenses", "months"}
    requested = [t for t in tables if t in valid_tables]

    if not requested:
        raise HTTPException(status_code=400, detail="No valid tables specified")

    # Read all requested tables
    table_data: dict[str, pd.DataFrame] = {}
    for table in requested:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", db.conn)
            table_data[table] = df
        except Exception:
            logger.exception("Failed to read table '%s' for export", table)
            table_data[table] = pd.DataFrame()

    if format == "excel":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            for name, df in table_data.items():
                df.to_excel(writer, sheet_name=name, index=False)
        buf.seek(0)

        filename = f"project_dashboard_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        # CSV: return a ZIP archive
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, df in table_data.items():
                csv_buf = io.StringIO()
                df.to_csv(csv_buf, index=False)
                zf.writestr(f"{name}.csv", csv_buf.getvalue())
        buf.seek(0)

        filename = f"project_dashboard_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

@router.post("/backup", response_model=MessageResponse)
def create_backup(
    db: DatabaseManager = Depends(get_db),
):
    """Create a timestamped backup of the SQLite database file."""
    db_path = Path(settings.database_path)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found")

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"project_dashboard_{timestamp}.db"

    shutil.copy2(str(db_path), str(backup_path))

    return MessageResponse(message=f"Backup created at {backup_path}")


# ---------------------------------------------------------------------------
# Database Info
# ---------------------------------------------------------------------------

@router.get("/info")
def database_info(
    db: DatabaseManager = Depends(get_db),
):
    """Return table row counts and database file size."""
    db_path = Path(settings.database_path)
    file_size = db_path.stat().st_size if db_path.exists() else 0

    tables = ["projects", "employees", "allocations", "time_entries", "expenses", "months"]
    counts: dict[str, int] = {}
    for table in tables:
        try:
            cursor = db.conn.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        except Exception:
            logger.exception("Failed to count rows in table '%s'", table)
            counts[table] = 0

    # Find latest backup
    backup_dir = db_path.parent / "backups"
    last_backup: str | None = None
    if backup_dir.exists():
        backups = sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        if backups:
            last_backup = datetime.fromtimestamp(backups[0].stat().st_mtime).isoformat()

    return {
        "file_size_bytes": file_size,
        "table_counts": counts,
        "last_backup": last_backup,
    }
