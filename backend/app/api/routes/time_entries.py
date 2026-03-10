"""
Time entry query endpoints.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.core.database import DatabaseManager, get_db
from app.services.data_processor import df_to_records

router = APIRouter(prefix="/time-entries", tags=["Time Entries"])


@router.get("/", response_model=list[dict[str, Any]])
def list_time_entries(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    employee_id: Optional[int] = Query(None, description="Filter by employee ID"),
    start_date: Optional[str] = Query(None, description="Filter entries on or after this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter entries on or before this date (YYYY-MM-DD)"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return time entries with optional filters.

    Each record includes joined employee_name and project_name fields.
    """
    df = db.get_time_entries(
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        project_id=project_id,
    )
    return df_to_records(df)


@router.get("/date-range")
def get_time_entries_date_range(
    db: DatabaseManager = Depends(get_db),
):
    """Return the min and max dates of existing time entries."""
    result = db.get_existing_time_entries_date_range()
    if result is None:
        return {"min_date": None, "max_date": None}
    return {"min_date": result[0], "max_date": result[1]}


@router.get("/by-month", response_model=list[dict[str, Any]])
def get_time_entries_by_month(
    project_id: str = Query(..., description="Project ID (required)"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return time entries grouped by employee and month for a specific project.

    Useful for building monthly hour breakdowns.
    """
    df = db.get_time_entries_by_month(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
    )
    return df_to_records(df)
