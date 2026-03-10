"""
Pydantic models for allocation request/response schemas.
"""
from typing import Optional
from pydantic import BaseModel


class AllocationBase(BaseModel):
    """Fields for allocation operations."""
    project_id: str
    employee_id: int
    allocated_fte: float
    allocation_date: str
    role: Optional[str] = None
    bill_rate: Optional[float] = None


class AllocationCreate(AllocationBase):
    """Schema for creating or upserting an allocation."""
    pass


class AllocationUpdate(BaseModel):
    """Schema for updating an allocation."""
    allocated_fte: Optional[float] = None
    allocation_date: Optional[str] = None
    role: Optional[str] = None
    bill_rate: Optional[float] = None


class AllocationResponse(AllocationBase):
    """Schema returned when reading an allocation."""
    id: int
    project_name: Optional[str] = None
    employee_name: Optional[str] = None
    effective_rate: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}
