"""
Shared Pydantic models used across multiple route modules.
"""
from typing import Any, Optional
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response body."""
    detail: str


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""
    offset: int = 0
    limit: int = 100


class DateRangeFilter(BaseModel):
    """Reusable date-range filter."""
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ImportSummary(BaseModel):
    """Summary returned after a data import operation."""
    message: str
    summary: dict[str, Any]
