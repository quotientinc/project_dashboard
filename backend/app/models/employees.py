"""
Pydantic models for employee request/response schemas.

Employee IDs are INTEGER.
"""
from typing import Optional
from pydantic import BaseModel


class EmployeeBase(BaseModel):
    """Fields shared between create and update operations."""
    name: str
    role: Optional[str] = None
    skills: Optional[str] = None
    hire_date: Optional[str] = None
    term_date: Optional[str] = None
    pay_type: Optional[str] = None
    cost_rate: Optional[float] = None
    annual_salary: Optional[float] = None
    pto_accrual: Optional[float] = None
    holidays: Optional[float] = None
    billable: Optional[int] = 0
    overhead_allocation: Optional[float] = 0.0
    target_allocation: Optional[float] = 0.3


class EmployeeCreate(EmployeeBase):
    """Schema for creating a new employee. ID is required (INTEGER)."""
    id: int


class EmployeeUpdate(BaseModel):
    """Schema for updating an employee. All fields optional."""
    name: Optional[str] = None
    role: Optional[str] = None
    skills: Optional[str] = None
    hire_date: Optional[str] = None
    term_date: Optional[str] = None
    pay_type: Optional[str] = None
    cost_rate: Optional[float] = None
    annual_salary: Optional[float] = None
    pto_accrual: Optional[float] = None
    holidays: Optional[float] = None
    billable: Optional[int] = None
    overhead_allocation: Optional[float] = None
    target_allocation: Optional[float] = None


class EmployeeResponse(EmployeeBase):
    """Schema returned when reading an employee."""
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}
