"""
Pydantic models for analytics response schemas.
"""
from typing import Any, Optional
from pydantic import BaseModel, Field


class OverviewKPIs(BaseModel):
    """Dashboard overview key performance indicators."""
    total_projects: int = 0
    active_projects: int = 0
    completed_projects: int = 0
    total_employees: int = 0
    billable_employees: int = 0
    total_quoted_value: float = 0.0
    total_awarded_value: float = 0.0
    total_budget_used: float = 0.0
    total_hours_logged: float = 0.0
    total_billable_hours: float = 0.0
    avg_utilization: float = 0.0


class BurnRateEntry(BaseModel):
    """Single period in a burn-rate series."""
    period: str
    burn_rate: float
    cumulative_burn: float


class ProjectHealthEntry(BaseModel):
    """Health metrics for a single project."""
    id: str
    name: str
    status: Optional[str] = None
    budget_health: Optional[float] = 0.0
    schedule_progress: Optional[float] = 0.0
    profit_margin: Optional[float] = 0.0
    health_score: Optional[float] = 0.0


class PerformanceMetrics(BaseModel):
    """Performance metrics grouped by actuals, projected, possible."""
    actuals: dict[str, Any] = {}
    projected: dict[str, Any] = {}
    possible: dict[str, Any] = {}


class ForecastEntry(BaseModel):
    """Completion forecast for a single project."""
    project_name: str
    current_progress: float
    avg_daily_burn: float
    remaining_hours: float
    days_to_complete: float
    forecast_completion: str
    scheduled_end: Optional[str] = None
    on_track: bool = False


# ---- Endpoint 1: Client Analysis ----

class ClientAnalysisEntry(BaseModel):
    """Revenue and cost breakdown for a single client."""
    client: str
    revenue: float = 0.0
    labor_cost: float = 0.0
    expenses: float = 0.0
    total_cost: float = 0.0
    profit: float = 0.0
    margin_pct: float = 0.0


# ---- Endpoint 2: Year Forecast ----

class YearForecastMonth(BaseModel):
    """Single month in a year forecast."""
    month: int
    month_name: str
    revenue: float = 0.0
    data_type: str = "Actual"


class YearForecastResponse(BaseModel):
    """Full year revenue forecast."""
    ytd_actual: float = 0.0
    projected_remaining: float = 0.0
    full_year_forecast: float = 0.0
    months: list[YearForecastMonth] = []


# ---- Endpoint 3 & 4: Funding Review ----

class FundingReviewEntry(BaseModel):
    """Funding review data for a single project."""
    project_id: str
    project_name: str
    client: Optional[str] = None
    project_manager: Optional[str] = None
    status: Optional[str] = None
    quoted_value: float = 0.0
    awarded_value: float = 0.0
    budget_used: float = 0.0
    remaining: float = 0.0
    avg_monthly_invoice: float = 0.0
    funding_runway_months: Optional[float] = None
    funding_pct: float = 0.0
    health_label: str = "N/A"
    current_month_potential: float = 0.0


class MonthlyRevenueEntry(BaseModel):
    """Monthly revenue data point."""
    month: str
    revenue: float = 0.0


class FundingReviewDetailResponse(FundingReviewEntry):
    """Detailed funding review for a single project with revenue history."""
    past_month_revenue: float = 0.0
    monthly_revenue_history: list[MonthlyRevenueEntry] = []


# ---- Endpoint 5: Detailed Utilization ----

class EmployeeMonthUtilization(BaseModel):
    """Single month utilization for an employee."""
    month: str
    possible_hours: float = 0.0
    actual_hours: float = 0.0
    actual_billable_hours: float = 0.0
    projected_hours: float = 0.0
    pto_hours: float = 0.0
    holiday_hours: float = 0.0
    utilization_pct: Optional[float] = None


class DetailedUtilizationEntry(BaseModel):
    """Detailed utilization data for a single employee."""
    employee_id: int
    employee_name: str
    role: Optional[str] = None
    billable: int = 0
    possible_hours: float = 0.0
    actual_hours: float = 0.0
    actual_billable_hours: float = 0.0
    projected_hours: float = 0.0
    pto_hours: float = 0.0
    holiday_hours: float = 0.0
    utilization_pct: Optional[float] = None
    monthly_breakdown: list[EmployeeMonthUtilization] = []


# ---- Endpoint 6: Allocation Planning ----

class AllocationProjectBreakdown(BaseModel):
    """Allocation breakdown for a single project assignment."""
    project_id: str
    project_name: str
    allocated_fte: float = 0.0
    allocated_hours: float = 0.0
    bill_rate: float = 0.0


class AllocationPlanningEntry(BaseModel):
    """Allocation planning data for a single employee."""
    employee_id: int
    employee_name: str
    target_fte: float = 0.0
    possible_hours: float = 0.0
    allocated_hours: float = 0.0
    allocation_pct: float = 0.0
    variance: float = 0.0
    status: str = "Under-Allocated"
    project_breakdown: list[AllocationProjectBreakdown] = []


# ---- Endpoint 7: Project Utilization ----

class ProjectUtilizationEntry(BaseModel):
    """Utilization data for a single project."""
    project_id: str
    project_name: str
    allocated_hours: float = 0.0
    actual_billable_hours: float = 0.0
    utilization_pct: Optional[float] = None
    revenue_gap: float = 0.0
    health_label: str = "N/A"


# ---- Endpoint 8: Combined Performance ----

class CombinedMonthlyBreakdown(BaseModel):
    """Single month in combined performance view."""
    month: str
    month_type: str = "past"  # past, active, future
    actual_hours: float = 0.0
    projected_hours: float = 0.0
    combined_hours: float = 0.0
    actual_revenue: float = 0.0
    projected_revenue: float = 0.0
    combined_revenue: float = 0.0
    cumulative_revenue: float = 0.0
    budget_pct: Optional[float] = None
    status: Optional[str] = None


class CombinedPerformanceSummary(BaseModel):
    """Summary section of combined performance response."""
    total_hours: float = 0.0
    total_accrued: float = 0.0
    budget_status: str = "Unknown"
    budget_pct: float = 0.0


class CombinedPerformanceResponse(BaseModel):
    """Combined actual + projected performance for a project."""
    summary: CombinedPerformanceSummary = Field(default_factory=CombinedPerformanceSummary)
    monthly_breakdown: list[CombinedMonthlyBreakdown] = []


# ---- Overview Dashboard Endpoints ----

class MonthlyUtilizationTrendEntry(BaseModel):
    """Single month in the utilization trend chart."""
    month: int
    month_name: str
    avg_utilization: float = 0.0
    data_type: str = "Actual"  # "Actual" or "Projected"


class EmployeeBillableUtilizationEntry(BaseModel):
    """Billable utilization for a single employee."""
    employee_id: int
    name: str
    utilization_pct: float = 0.0


class MonthlyBurnRateEntry(BaseModel):
    """Monthly burn rate breakdown."""
    month: str  # "YYYY-MM"
    labor_cost: float = 0.0
    expense_cost: float = 0.0
    total_burn: float = 0.0
