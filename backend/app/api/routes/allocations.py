"""
Allocation CRUD endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import DatabaseManager, get_db
from app.models.allocations import AllocationCreate, AllocationResponse, AllocationUpdate
from app.services.data_processor import df_to_records

router = APIRouter(prefix="/allocations", tags=["Allocations"])

logger = logging.getLogger(__name__)


@router.get("/", response_model=list[AllocationResponse])
def list_allocations(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    employee_id: Optional[int] = Query(None, description="Filter by employee ID"),
    db: DatabaseManager = Depends(get_db),
):
    """Return allocations, optionally filtered by project and/or employee."""
    df = db.get_allocations(project_id=project_id, employee_id=employee_id)
    return df_to_records(df)


@router.post("/", response_model=AllocationResponse, status_code=201)
def create_or_update_allocation(
    body: AllocationCreate,
    db: DatabaseManager = Depends(get_db),
):
    """
    Create or upsert an allocation.

    Uses ON CONFLICT to update if (employee_id, project_id, allocation_date) already exists.
    """
    allocation_data = body.model_dump(exclude_none=True)
    try:
        allocation_id = db.add_allocation(allocation_data)
    except Exception as exc:
        logger.exception("Failed to add allocation")
        raise HTTPException(status_code=400, detail=str(exc))

    # Retrieve the created/updated allocation
    df = db.get_allocations(
        project_id=body.project_id,
        employee_id=body.employee_id,
    )
    if df.empty:
        raise HTTPException(status_code=500, detail="Allocation created but could not be retrieved")

    # Find the matching record
    match = df[df["allocation_date"].str[:7] == body.allocation_date[:7]]
    if match.empty:
        # Fallback to most recent
        records = df_to_records(df)
        return records[-1]

    return df_to_records(match)[0]


@router.put("/{allocation_id}", response_model=AllocationResponse)
def update_allocation(
    allocation_id: int,
    body: AllocationUpdate,
    db: DatabaseManager = Depends(get_db),
):
    """Update an existing allocation by ID."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        db.update_allocation(allocation_id, updates)
    except Exception as exc:
        logger.exception("Failed to update allocation %d", allocation_id)
        raise HTTPException(status_code=400, detail=str(exc))

    # Retrieve the updated allocation
    df = db.get_allocations()
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Allocation {allocation_id} not found")

    match = df[df["id"] == allocation_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Allocation {allocation_id} not found after update")

    return df_to_records(match)[0]


@router.delete("/{allocation_id}", status_code=204)
def delete_allocation(
    allocation_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """Delete an allocation by ID."""
    db.delete_allocation(allocation_id)
