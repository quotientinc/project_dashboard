"""
Expense query endpoints.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.core.database import DatabaseManager, get_db
from app.services.data_processor import df_to_records

router = APIRouter(prefix="/expenses", tags=["Expenses"])


@router.get("/", response_model=list[dict[str, Any]])
def list_expenses(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    category: Optional[str] = Query(None, description="Filter by expense category"),
    start_date: Optional[str] = Query(None, description="Filter expenses on or after this date"),
    end_date: Optional[str] = Query(None, description="Filter expenses on or before this date"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return expenses with optional filters.

    Each record includes the joined project_name field.
    """
    df = db.get_expenses(project_id=project_id)

    if not df.empty:
        if category:
            df = df[df["category"] == category]
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

    return df_to_records(df)
