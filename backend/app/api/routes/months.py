"""
Month/holiday calendar endpoints.
"""
import calendar
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.database import DatabaseManager, get_db
from app.services.data_processor import df_to_records

router = APIRouter(prefix="/months", tags=["Months"])

logger = logging.getLogger(__name__)


class MonthUpdate(BaseModel):
    """Schema for updating a month record."""
    working_days: Optional[int] = None
    holidays: Optional[int] = None
    quarter: Optional[str] = None


class MonthCreate(BaseModel):
    """Schema for creating a month record."""
    year: int
    month: int
    month_name: str
    total_days: int
    working_days: int
    holidays: int = 0
    quarter: str


@router.get("/", response_model=list[dict[str, Any]])
def list_months(
    year: Optional[int] = Query(None, description="Filter by year"),
    db: DatabaseManager = Depends(get_db),
):
    """Return all month records, optionally filtered by year. Sorted by year DESC, month ASC."""
    df = db.get_months(year=year)
    return df_to_records(df)


@router.post("/", status_code=201)
def create_month(
    body: MonthCreate,
    db: DatabaseManager = Depends(get_db),
):
    """Create a new month record."""
    month_data = body.model_dump()
    try:
        month_id = db.add_month(month_data)
    except Exception as exc:
        logger.exception("Failed to add month")
        raise HTTPException(status_code=400, detail=str(exc))

    return {"id": month_id, **month_data}


@router.put("/{month_id}")
def update_month(
    month_id: int,
    body: MonthUpdate,
    db: DatabaseManager = Depends(get_db),
):
    """Update a month record (working_days, holidays, quarter)."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    rows = db.update_month(month_id, updates)
    if rows == 0:
        raise HTTPException(status_code=404, detail=f"Month {month_id} not found")

    # Retrieve the updated record
    df = db.get_months()
    match = df[df["id"] == month_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Month {month_id} not found after update")

    return df_to_records(match)[0]


@router.delete("/{month_id}", status_code=204)
def delete_month(
    month_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """Delete a month record."""
    db.delete_month(month_id)


class GenerateYearRequest(BaseModel):
    """Schema for generating all 12 months for a year."""
    year: int
    copy_holidays_from_previous: bool = False


@router.post("/generate-year", status_code=201)
def generate_year(
    body: GenerateYearRequest,
    db: DatabaseManager = Depends(get_db),
):
    """Generate all 12 months for a given year with calculated working days."""
    year = body.year

    # Check if year already exists
    existing = db.get_months(year=year)
    if not existing.empty:
        raise HTTPException(
            status_code=400,
            detail=f"Year {year} already has {len(existing)} months in the database.",
        )

    # Optionally copy holidays from previous year
    previous_holidays: dict[int, int] = {}
    if body.copy_holidays_from_previous:
        prev_df = db.get_months(year=year - 1)
        if not prev_df.empty:
            previous_holidays = dict(zip(prev_df["month"], prev_df["holidays"]))

    months_to_add = []
    for month_num in range(1, 13):
        total_days = calendar.monthrange(year, month_num)[1]
        month_name = calendar.month_name[month_num]
        quarter = f"Q{((month_num - 1) // 3) + 1}"

        working_days = sum(
            1 for day in range(1, total_days + 1)
            if calendar.weekday(year, month_num, day) < 5
        )

        holidays = previous_holidays.get(month_num, 0)

        months_to_add.append({
            "year": year,
            "month": month_num,
            "month_name": month_name,
            "quarter": quarter,
            "total_days": total_days,
            "working_days": working_days,
            "holidays": int(holidays),
        })

    db.bulk_upsert_months(months_to_add)

    return {"message": f"Generated 12 months for {year}", "months": months_to_add}
