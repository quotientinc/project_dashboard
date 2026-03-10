"""
Pydantic models for project request/response schemas.

Project IDs are TEXT (Deltek charge numbers like "220300.00.001.00").
"""
from typing import Optional
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    """Fields shared between create and update operations."""
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    quoted_value: Optional[float] = None
    awarded_value: Optional[float] = None
    client: Optional[str] = None
    project_manager: Optional[str] = None
    billable: Optional[int] = 0


class ProjectCreate(ProjectBase):
    """Schema for creating a new project. ID is required (TEXT)."""
    id: str = Field(..., description="Project ID (Deltek charge number, e.g. '220300.00.001.00')")


class ProjectUpdate(BaseModel):
    """Schema for updating a project. All fields optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    quoted_value: Optional[float] = None
    awarded_value: Optional[float] = None
    client: Optional[str] = None
    project_manager: Optional[str] = None
    billable: Optional[int] = None


class ProjectResponse(ProjectBase):
    """Schema returned when reading a project."""
    id: str
    budget_used: Optional[float] = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ProjectPhaseBase(BaseModel):
    """Fields for project phase operations."""
    phase_name: str
    phase_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    predecessors: Optional[str] = None
    risk: Optional[str] = None
    status: Optional[str] = None
    completion_pct: float = 0.0
    notes: Optional[str] = None


class ProjectPhaseCreate(ProjectPhaseBase):
    """Schema for creating a project phase."""
    project_id: str


class ProjectPhaseUpdate(BaseModel):
    """Schema for updating a project phase."""
    phase_name: Optional[str] = None
    phase_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    predecessors: Optional[str] = None
    risk: Optional[str] = None
    status: Optional[str] = None
    completion_pct: Optional[float] = None
    notes: Optional[str] = None


class ProjectPhaseResponse(ProjectPhaseBase):
    """Schema returned when reading a project phase."""
    id: int
    project_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}
