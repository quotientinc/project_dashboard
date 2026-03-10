"""
Project CRUD endpoints.

Project IDs are TEXT (Deltek charge numbers like "220300.00.001.00").
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import DatabaseManager, get_db
from app.models.projects import (
    ProjectCreate,
    ProjectPhaseCreate,
    ProjectPhaseResponse,
    ProjectPhaseUpdate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.data_processor import df_to_records

router = APIRouter(prefix="/projects", tags=["Projects"])

logger = logging.getLogger(__name__)


@router.get("/", response_model=list[ProjectResponse])
def list_projects(
    status: Optional[list[str]] = Query(None, description="Filter by status(es)"),
    start_date: Optional[str] = Query(None, description="Filter by start_date >= value"),
    end_date: Optional[str] = Query(None, description="Filter by end_date <= value"),
    client: Optional[str] = Query(None, description="Filter by client name (exact)"),
    project_manager: Optional[str] = Query(None, description="Filter by project manager (exact)"),
    db: DatabaseManager = Depends(get_db),
):
    """Return all projects, optionally filtered by status, date range, client, or PM."""
    filters = {}
    if status:
        filters["status"] = status
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date

    df = db.get_projects(filters=filters if filters else None)

    # Apply additional filters not supported by DatabaseManager.get_projects
    if client and not df.empty:
        df = df[df["client"] == client]
    if project_manager and not df.empty:
        df = df[df["project_manager"] == project_manager]

    return df_to_records(df)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: DatabaseManager = Depends(get_db),
):
    """Return a single project by ID."""
    df = db.get_projects()
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    project = df[df["id"] == project_id]
    if project.empty:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    records = df_to_records(project)
    return records[0]


@router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(
    body: ProjectCreate,
    db: DatabaseManager = Depends(get_db),
):
    """Create a new project."""
    project_data = body.model_dump(exclude_none=True)
    try:
        db.add_project(project_data)
    except Exception as exc:
        logger.exception("Failed to add project")
        raise HTTPException(status_code=400, detail=str(exc))

    # Return the newly created project
    return get_project(body.id, db)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: DatabaseManager = Depends(get_db),
):
    """Update an existing project."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        db.update_project(project_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return get_project(project_id, db)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: DatabaseManager = Depends(get_db),
):
    """Delete a project by ID."""
    cursor = db.conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    db.conn.commit()


# ---- Project Phases sub-routes ----

@router.get("/{project_id}/phases", response_model=list[ProjectPhaseResponse])
def list_project_phases(
    project_id: str,
    db: DatabaseManager = Depends(get_db),
):
    """List all phases for a project."""
    df = db.get_project_phases(project_id=project_id)
    return df_to_records(df)


@router.post("/{project_id}/phases", response_model=ProjectPhaseResponse, status_code=201)
def create_project_phase(
    project_id: str,
    body: ProjectPhaseCreate,
    db: DatabaseManager = Depends(get_db),
):
    """Create a new phase for a project."""
    phase_data = body.model_dump(exclude_none=True)
    phase_data["project_id"] = project_id
    phase_id = db.add_project_phase(phase_data)

    df = db.get_project_phases(project_id=project_id)
    phase = df[df["id"] == phase_id]
    if phase.empty:
        raise HTTPException(status_code=500, detail="Phase created but could not be retrieved")
    return df_to_records(phase)[0]


@router.put("/{project_id}/phases/{phase_id}", response_model=ProjectPhaseResponse)
def update_project_phase(
    project_id: str,
    phase_id: int,
    body: ProjectPhaseUpdate,
    db: DatabaseManager = Depends(get_db),
):
    """Update a project phase."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    rows = db.update_project_phase(phase_id, updates)
    if rows == 0:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found")

    df = db.get_project_phases(project_id=project_id)
    phase = df[df["id"] == phase_id]
    if phase.empty:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found after update")
    return df_to_records(phase)[0]


@router.delete("/{project_id}/phases/{phase_id}", status_code=204)
def delete_project_phase(
    project_id: str,
    phase_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """Delete a project phase."""
    db.delete_project_phase(phase_id)
