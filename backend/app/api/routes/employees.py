"""
Employee CRUD endpoints.

Employee IDs are INTEGER.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import DatabaseManager, get_db
from app.models.employees import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services.data_processor import df_to_records

router = APIRouter(prefix="/employees", tags=["Employees"])

logger = logging.getLogger(__name__)


@router.get("/", response_model=list[EmployeeResponse])
def list_employees(
    role: Optional[str] = Query(None, description="Filter by role (exact match)"),
    billable: Optional[int] = Query(None, description="Filter by billable status (0 or 1)"),
    pay_type: Optional[str] = Query(None, description="Filter by pay type (Salary or Hourly)"),
    db: DatabaseManager = Depends(get_db),
):
    """Return all employees, optionally filtered."""
    df = db.get_employees()

    if not df.empty:
        if role is not None:
            df = df[df["role"] == role]
        if billable is not None:
            df = df[df["billable"] == billable]
        if pay_type is not None:
            df = df[df["pay_type"] == pay_type]

    return df_to_records(df)


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """Return a single employee by ID."""
    df = db.get_employees()
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found")

    employee = df[df["id"] == employee_id]
    if employee.empty:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found")

    return df_to_records(employee)[0]


@router.post("/", response_model=EmployeeResponse, status_code=201)
def create_employee(
    body: EmployeeCreate,
    db: DatabaseManager = Depends(get_db),
):
    """Create a new employee."""
    employee_data = body.model_dump(exclude_none=True)
    try:
        db.add_employee(employee_data)
    except Exception as exc:
        logger.exception("Failed to add employee")
        raise HTTPException(status_code=400, detail=str(exc))

    return get_employee(body.id, db)


@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    body: EmployeeUpdate,
    db: DatabaseManager = Depends(get_db),
):
    """Update an existing employee."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        db.update_employee(employee_id, updates)
    except Exception as exc:
        logger.exception("Failed to update employee %d", employee_id)
        raise HTTPException(status_code=400, detail=str(exc))

    return get_employee(employee_id, db)


@router.delete("/{employee_id}", status_code=204)
def delete_employee(
    employee_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """Delete an employee by ID."""
    cursor = db.conn.cursor()
    cursor.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found")
    db.conn.commit()
