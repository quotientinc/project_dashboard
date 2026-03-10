"""
Analytics endpoints -- overview KPIs, utilization, burn-rate, health,
performance metrics, and forecasts.

These endpoints wrap the existing DataProcessor static methods and
DatabaseManager queries.
"""
import calendar as cal_mod
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import DatabaseManager, get_db
from app.models.analytics import (
    AllocationPlanningEntry,
    AllocationProjectBreakdown,
    BurnRateEntry,
    ClientAnalysisEntry,
    CombinedMonthlyBreakdown,
    CombinedPerformanceResponse,
    CombinedPerformanceSummary,
    DetailedUtilizationEntry,
    EmployeeBillableUtilizationEntry,
    EmployeeMonthUtilization,
    ForecastEntry,
    FundingReviewDetailResponse,
    FundingReviewEntry,
    MonthlyBurnRateEntry,
    MonthlyRevenueEntry,
    MonthlyUtilizationTrendEntry,
    OverviewKPIs,
    PerformanceMetrics,
    ProjectHealthEntry,
    ProjectUtilizationEntry,
    YearForecastMonth,
    YearForecastResponse,
)
from app.services.data_processor import DataProcessor, df_to_records

router = APIRouter(prefix="/analytics", tags=["Analytics"])

logger = logging.getLogger(__name__)


def _get_working_days_in_range(start_date, end_date, months_df, year, month):
    """Calculate working days an employee was active in a specific month.

    Prorates based on hire/term dates relative to the month boundaries.
    Matches the helper `get_working_days_in_range`.
    """
    month_info = months_df[
        (months_df["year"] == year) & (months_df["month"] == month)
    ] if not months_df.empty else pd.DataFrame()

    if month_info.empty:
        return 21  # Default fallback

    working_days_in_month = int(month_info["working_days"].iloc[0])
    holidays_in_month = (
        int(month_info["holidays"].iloc[0])
        if "holidays" in month_info.columns and pd.notna(month_info["holidays"].iloc[0])
        else 0
    )
    working_days_in_month = max(working_days_in_month - holidays_in_month, 0)

    month_start = datetime(year, month, 1).date()
    month_end = datetime(year, month, cal_mod.monthrange(year, month)[1]).date()

    actual_start = max(start_date, month_start)
    actual_end = min(end_date, month_end)

    if actual_end < actual_start:
        return 0

    if actual_start == month_start and actual_end == month_end:
        return working_days_in_month

    days_in_month = (month_end - month_start).days + 1
    days_worked = (actual_end - actual_start).days + 1
    proportion = days_worked / days_in_month

    return int(working_days_in_month * proportion)


@router.get("/overview", response_model=OverviewKPIs)
def get_overview(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: DatabaseManager = Depends(get_db),
):
    """Return dashboard-level KPI summary."""

    projects_df = db.get_projects()
    employees_df = db.get_employees()
    time_entries_df = db.get_time_entries(start_date=start_date, end_date=end_date)

    kpis = OverviewKPIs()

    # Determine billable project IDs for filtering
    billable_project_ids: list = []
    if not projects_df.empty:
        kpis.total_projects = len(projects_df)
        kpis.active_projects = int((projects_df["status"] == "Active").sum())
        kpis.completed_projects = int((projects_df["status"] == "Completed").sum())

        # Filter to billable projects for financial KPIs
        billable_projects_df = projects_df[projects_df["billable"] == 1]
        billable_project_ids = billable_projects_df["id"].tolist()
        if not billable_projects_df.empty:
            kpis.total_quoted_value = float(billable_projects_df["quoted_value"].sum()) if "quoted_value" in billable_projects_df.columns else 0.0
            kpis.total_awarded_value = float(billable_projects_df["awarded_value"].sum()) if "awarded_value" in billable_projects_df.columns else 0.0
            kpis.total_budget_used = float(billable_projects_df["budget_used"].sum()) if "budget_used" in billable_projects_df.columns else 0.0

    if not employees_df.empty:
        kpis.total_employees = len(employees_df)
        kpis.billable_employees = int((employees_df["billable"] == 1).sum())

    # Filter time entries to billable projects
    if not time_entries_df.empty and billable_project_ids:
        time_entries_df = time_entries_df[time_entries_df["project_id"].isin(billable_project_ids)]

    if not time_entries_df.empty:
        kpis.total_hours_logged = float(time_entries_df["hours"].sum())
        if "billable" in time_entries_df.columns:
            kpis.total_billable_hours = float(
                time_entries_df.loc[time_entries_df["billable"] == 1, "hours"].sum()
            )

    # Calculate avg_utilization (YTD billable hours / available hours)
    # Use start_date/end_date if provided, otherwise default to YTD
    now = datetime.now()
    calc_start = start_date or f"{now.year}-01-01"
    calc_end = end_date or now.strftime("%Y-%m-%d")

    if not employees_df.empty:
        billable_employees = employees_df[
            (employees_df["billable"] == 1) &
            (
                (employees_df["term_date"].isna()) |
                (pd.to_datetime(employees_df["term_date"]) >= pd.Timestamp(now))
            )
        ]

        if not billable_employees.empty:
            try:
                performance_data = DataProcessor.get_performance_metrics(
                    start_date=calc_start,
                    end_date=calc_end,
                    constraint=None,
                    db=db,
                )

                month_names = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ]

                # Get full year time entries for PTO calculation
                full_year_te = db.get_time_entries(
                    start_date=f"{now.year}-01-01",
                    end_date=f"{now.year}-12-31",
                )
                billable_emp_ids = billable_employees["id"].tolist()

                ytd_total_billable = 0.0
                ytd_total_possible = 0.0
                ytd_total_pto = 0.0

                for month_num in range(1, now.month + 1):
                    month_name = f"{month_names[month_num - 1]} {now.year}"

                    actual_month_data = performance_data.get("actuals", {}).get(month_name, {})
                    ytd_total_billable += sum(
                        emp_data.get("billable_hours", 0) for emp_data in actual_month_data.values()
                    )

                    possible_month_data = performance_data.get("possible", {}).get(month_name, {})
                    ytd_total_possible += sum(
                        emp_data.get("hours", 0) for emp_data in possible_month_data.values()
                    )

                    # PTO hours
                    if not full_year_te.empty:
                        month_start_str = f"{now.year}-{month_num:02d}-01"
                        month_end_day = cal_mod.monthrange(now.year, month_num)[1]
                        month_end_str = f"{now.year}-{month_num:02d}-{month_end_day}"

                        month_entries = full_year_te[
                            (full_year_te["date"] >= month_start_str) &
                            (full_year_te["date"] <= month_end_str)
                        ]

                        if not month_entries.empty:
                            billable_entries = month_entries[month_entries["employee_id"].isin(billable_emp_ids)]
                            pto_entries = billable_entries[billable_entries["project_id"] == "FRINGE.PTO"]
                            ytd_total_pto += pto_entries["hours"].sum() if not pto_entries.empty else 0

                ytd_available = max(ytd_total_possible - ytd_total_pto, 0)
                kpis.avg_utilization = round((ytd_total_billable / ytd_available * 100), 1) if ytd_available > 0 else 0.0
            except Exception as exc:
                logger.exception("Failed to compute avg_utilization")

    return kpis


@router.get("/utilization", response_model=list[dict[str, Any]])
def get_utilization(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    employee_id: Optional[int] = Query(None, description="Filter by employee ID"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return employee utilization data.

    Utilization is calculated as actual hours vs allocated (projected) hours
    for the given date range.
    """
    time_entries_df = db.get_time_entries(
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
    )
    employees_df = db.get_employees()

    if time_entries_df.empty or employees_df.empty:
        return []

    # Group hours by employee
    employee_hours = (
        time_entries_df.groupby("employee_id")["hours"]
        .sum()
        .reset_index()
        .rename(columns={"hours": "total_hours"})
    )

    # Merge with employee info
    result = employee_hours.merge(
        employees_df[["id", "name", "role", "billable", "target_allocation"]],
        left_on="employee_id",
        right_on="id",
        how="left",
    )

    # Calculate standard hours (160 per month as baseline)
    # Count months in range for a rough capacity estimate
    if start_date and end_date:
        months_diff = (
            (pd.to_datetime(end_date).year - pd.to_datetime(start_date).year) * 12
            + pd.to_datetime(end_date).month
            - pd.to_datetime(start_date).month
            + 1
        )
    else:
        months_diff = 1

    result["standard_hours"] = 160 * months_diff
    result["utilization_pct"] = (result["total_hours"] / result["standard_hours"] * 100).clip(upper=100)

    return df_to_records(result[["employee_id", "name", "role", "total_hours", "standard_hours", "utilization_pct"]])


@router.get("/burn-rate", response_model=list[BurnRateEntry])
def get_burn_rate(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    time_period: str = Query("monthly", description="Aggregation period: daily, weekly, monthly, yearly"),
    db: DatabaseManager = Depends(get_db),
):
    """Return burn-rate analysis for expenses."""
    expenses_df = db.get_expenses(project_id=project_id)

    if expenses_df.empty:
        return []

    burn_df = DataProcessor.calculate_burn_rate(expenses_df, time_period=time_period)
    return df_to_records(burn_df)


@router.get("/health", response_model=list[ProjectHealthEntry])
def get_project_health(
    db: DatabaseManager = Depends(get_db),
):
    """Return health scores for all projects."""
    projects_df = db.get_projects()
    allocations_df = db.get_allocations()

    if projects_df.empty:
        return []

    health_df = DataProcessor.calculate_project_health(projects_df, allocations_df)

    # Select relevant columns
    columns = ["id", "name", "status", "budget_health", "schedule_progress", "profit_margin", "health_score"]
    available = [c for c in columns if c in health_df.columns]
    return df_to_records(health_df[available])


@router.get("/performance", response_model=PerformanceMetrics)
def get_performance(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    employee_id: Optional[int] = Query(None, description="Filter by employee ID"),
    db: DatabaseManager = Depends(get_db),
):
    """Return performance metrics (actuals, projected, possible)."""
    constraint = None
    if project_id:
        constraint = {"project_id": project_id}
    elif employee_id:
        constraint = {"employee_id": str(employee_id)}

    try:
        metrics = DataProcessor.get_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            constraint=constraint,
            db=db,
        )
    except Exception as exc:
        logger.exception("Error computing performance metrics")
        raise HTTPException(status_code=500, detail=f"Error computing performance metrics: {exc}")

    return PerformanceMetrics(
        actuals=metrics.get("actuals", {}),
        projected=metrics.get("projected", {}),
        possible=metrics.get("possible", {}),
    )


@router.get("/forecast", response_model=list[ForecastEntry])
def get_forecast(
    lookback_days: int = Query(30, description="Number of days to look back for velocity calculation"),
    db: DatabaseManager = Depends(get_db),
):
    """Return completion forecasts for active projects."""
    projects_df = db.get_projects()
    time_entries_df = db.get_time_entries()

    if projects_df.empty or time_entries_df.empty:
        return []

    forecast_df = DataProcessor.forecast_project_completion(
        projects_df, time_entries_df, lookback_days=lookback_days
    )

    if forecast_df.empty:
        return []

    # Convert timestamp columns to strings for JSON serialisation
    for col in ["forecast_completion", "scheduled_end"]:
        if col in forecast_df.columns:
            forecast_df[col] = forecast_df[col].astype(str)

    return df_to_records(forecast_df)


def _calculate_entry_revenue(row) -> float:
    """Calculate revenue for a time entry row (amount if present, else hours * hourly_rate)."""
    if pd.notna(row.get("amount")) and row["amount"] != 0:
        return row["amount"]
    elif pd.notna(row.get("hourly_rate")) and pd.notna(row.get("hours")):
        return row["hours"] * row["hourly_rate"]
    return 0.0


# ---------------------------------------------------------------------------
# Overview sub-endpoints: utilization trend, employee utilization, burn rate
# ---------------------------------------------------------------------------


@router.get("/overview/utilization-trend", response_model=list[MonthlyUtilizationTrendEntry])
def get_utilization_trend(
    year: int = Query(None, description="Year for trend. Defaults to current year."),
    db: DatabaseManager = Depends(get_db),
):
    """Return monthly utilization trend for the year (actual + projected)."""

    now = datetime.now()
    target_year = year or now.year

    employees_df = db.get_employees()
    if employees_df.empty:
        return []

    billable_employees = employees_df[
        (employees_df["billable"] == 1)
        & (
            (employees_df["term_date"].isna())
            | (pd.to_datetime(employees_df["term_date"]) >= pd.Timestamp(now))
        )
    ]

    if billable_employees.empty:
        return []

    full_year_start = f"{target_year}-01-01"
    full_year_end = f"{target_year}-12-31"

    try:
        performance_data = DataProcessor.get_performance_metrics(
            start_date=full_year_start,
            end_date=full_year_end,
            constraint=None,
            db=db,
        )
    except Exception:
        logger.exception("Failed to compute utilization trend")
        return []

    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    # Get full year time entries for PTO
    full_year_te = db.get_time_entries(start_date=full_year_start, end_date=full_year_end)
    months_df = db.get_months()
    billable_emp_ids = billable_employees["id"].tolist()

    current_month = now.month if target_year == now.year else 13  # if past year, all actual

    results: list[MonthlyUtilizationTrendEntry] = []

    for month_num in range(1, 13):
        month_name = f"{month_names[month_num - 1]} {target_year}"

        if month_num < current_month:
            data_type = "Actual"
            month_data = performance_data.get("actuals", {}).get(month_name, {})
            possible_data = performance_data.get("possible", {}).get(month_name, {})
            total_billable_hours = sum(
                emp_data.get("billable_hours", 0) for emp_data in month_data.values()
            )
            total_possible_hours = sum(
                emp_data.get("hours", 0) for emp_data in possible_data.values()
            )

        elif month_num == current_month:
            # Gold standard formula for current month
            month_info = (
                months_df[
                    (months_df["year"] == target_year) & (months_df["month"] == current_month)
                ]
                if not months_df.empty
                else pd.DataFrame()
            )

            actual_month_data = performance_data.get("actuals", {}).get(month_name, {})
            projected_month_data = performance_data.get("projected", {}).get(month_name, {})
            possible_month_data = performance_data.get("possible", {}).get(month_name, {})

            actual_billable = sum(
                emp_data.get("billable_hours", 0) for emp_data in actual_month_data.values()
            )

            # Label as "Actual" if we have actual hours, else "Projected"
            data_type = "Actual" if actual_billable > 0 else "Projected"

            total_projected_missing = 0
            if not month_info.empty:
                working_days = int(month_info["working_days"].iloc[0])
                month_holidays = (
                    int(month_info["holidays"].iloc[0])
                    if pd.notna(month_info["holidays"].iloc[0])
                    else 0
                )
                available_working_days = max(working_days - month_holidays, 1)

                # Get last entry dates for employees
                month_start_str = f"{target_year}-{current_month:02d}-01"
                month_end_day = cal_mod.monthrange(target_year, current_month)[1]
                month_end_str = f"{target_year}-{current_month:02d}-{month_end_day}"
                month_end_date = datetime(target_year, current_month, month_end_day).date()
                month_start_date = datetime(target_year, current_month, 1).date()

                month_time_entries = pd.DataFrame()
                if not full_year_te.empty:
                    month_time_entries = full_year_te[
                        (full_year_te["date"] >= month_start_str)
                        & (full_year_te["date"] <= month_end_str)
                    ]

                last_entry_dates: dict = {}
                if not month_time_entries.empty:
                    billable_te = month_time_entries[month_time_entries["billable"] == 1]
                    if not billable_te.empty:
                        last_entry_dates = billable_te.groupby("employee_id")["date"].max().to_dict()

                for emp_id_str, proj_data in projected_month_data.items():
                    proj_hours = proj_data.get("hours", 0)
                    if proj_hours <= 0:
                        continue

                    try:
                        emp_id_int = int(emp_id_str)
                    except (ValueError, TypeError):
                        emp_id_int = emp_id_str

                    last_entry_str = last_entry_dates.get(emp_id_int)
                    if last_entry_str:
                        last_entry = pd.to_datetime(last_entry_str).date()
                        missing_start = last_entry + timedelta(days=1)
                    else:
                        missing_start = month_start_date

                    if missing_start <= month_end_date:
                        # Count working days
                        missing_days = int(np.busday_count(missing_start, month_end_date))
                        if month_end_date.weekday() < 5:
                            missing_days += 1
                        missing_days = max(missing_days, 0)
                    else:
                        missing_days = 0

                    if missing_days > 0 and available_working_days > 0:
                        total_projected_missing += proj_hours * (
                            missing_days / available_working_days
                        )

            total_billable_hours = actual_billable + total_projected_missing
            total_possible_hours = sum(
                emp_data.get("hours", 0) for emp_data in possible_month_data.values()
            )

        else:
            data_type = "Projected"
            month_data = performance_data.get("projected", {}).get(month_name, {})
            possible_data = performance_data.get("possible", {}).get(month_name, {})
            total_billable_hours = sum(
                emp_data.get("hours", 0) for emp_data in month_data.values()
            )
            total_possible_hours = sum(
                emp_data.get("hours", 0) for emp_data in possible_data.values()
            )

        # Get PTO hours
        total_pto_hours = 0
        if not full_year_te.empty:
            month_start_str = f"{target_year}-{month_num:02d}-01"
            month_end_day = cal_mod.monthrange(target_year, month_num)[1]
            month_end_str = f"{target_year}-{month_num:02d}-{month_end_day}"

            month_entries = full_year_te[
                (full_year_te["date"] >= month_start_str)
                & (full_year_te["date"] <= month_end_str)
            ]

            if not month_entries.empty:
                billable_entries = month_entries[
                    month_entries["employee_id"].isin(billable_emp_ids)
                ]
                pto_entries = billable_entries[billable_entries["project_id"] == "FRINGE.PTO"]
                total_pto_hours = pto_entries["hours"].sum() if not pto_entries.empty else 0

        available_hours = max(total_possible_hours - total_pto_hours, 0)
        avg_utilization = (
            (total_billable_hours / available_hours * 100) if available_hours > 0 else 0
        )

        results.append(
            MonthlyUtilizationTrendEntry(
                month=month_num,
                month_name=month_names[month_num - 1],
                avg_utilization=round(avg_utilization, 1),
                data_type=data_type,
            )
        )

    return results


@router.get(
    "/overview/employee-utilization",
    response_model=list[EmployeeBillableUtilizationEntry],
)
def get_employee_billable_utilization(
    year: int = Query(None, description="Year. Defaults to current year."),
    db: DatabaseManager = Depends(get_db),
):
    """Return per-employee billable utilization for the year."""

    now = datetime.now()
    target_year = year or now.year

    employees_df = db.get_employees()
    if employees_df.empty:
        return []

    billable_employees = employees_df[
        (employees_df["billable"] == 1)
        & (
            (employees_df["term_date"].isna())
            | (pd.to_datetime(employees_df["term_date"]) >= pd.Timestamp(now))
        )
    ]

    if billable_employees.empty:
        return []

    full_year_start = f"{target_year}-01-01"
    full_year_end = f"{target_year}-12-31"

    try:
        performance_data = DataProcessor.get_performance_metrics(
            start_date=full_year_start,
            end_date=full_year_end,
            constraint=None,
            db=db,
        )
    except Exception:
        logger.exception("Failed to compute employee billable utilization")
        return []

    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    full_year_te = db.get_time_entries(start_date=full_year_start, end_date=full_year_end)
    months_df = db.get_months()

    current_month = now.month if target_year == now.year else 13

    # Pre-compute current month constants
    cm_month_name = f"{month_names[now.month - 1]} {target_year}" if target_year == now.year else ""
    cm_projected_data = performance_data.get("projected", {}).get(cm_month_name, {})

    cm_available_working_days = 0
    cm_start_date = None
    cm_end_date = None
    cm_billable_entries = pd.DataFrame()

    if target_year == now.year and not months_df.empty:
        cm_month_info = months_df[
            (months_df["year"] == target_year) & (months_df["month"] == now.month)
        ]
        if not cm_month_info.empty:
            wd = int(cm_month_info["working_days"].iloc[0])
            hd = (
                int(cm_month_info["holidays"].iloc[0])
                if pd.notna(cm_month_info["holidays"].iloc[0])
                else 0
            )
            cm_available_working_days = max(wd - hd, 1)

        cm_end_day = cal_mod.monthrange(target_year, now.month)[1]
        cm_start_str = f"{target_year}-{now.month:02d}-01"
        cm_end_str = f"{target_year}-{now.month:02d}-{cm_end_day}"
        cm_start_date = datetime(target_year, now.month, 1).date()
        cm_end_date = datetime(target_year, now.month, cm_end_day).date()

        if not full_year_te.empty:
            cm_billable_entries = full_year_te[
                (full_year_te["date"] >= cm_start_str)
                & (full_year_te["date"] <= cm_end_str)
                & (full_year_te["billable"] == 1)
            ]

    results: list[EmployeeBillableUtilizationEntry] = []

    for _, emp in billable_employees.iterrows():
        emp_id_str = str(emp["id"])

        ytd_billable = 0.0
        ytd_possible = 0.0
        emp_ytd_pto = 0.0

        for month_num in range(1, min(current_month + 1, 13)):
            month_name = f"{month_names[month_num - 1]} {target_year}"

            actual_month_data = performance_data.get("actuals", {}).get(month_name, {})
            emp_actual = actual_month_data.get(emp_id_str, {})
            emp_actual_billable = emp_actual.get("billable_hours", 0)

            # Gold standard for current month
            if month_num == current_month and cm_available_working_days > 0:
                emp_projected = cm_projected_data.get(emp_id_str, {})
                emp_proj_hours = emp_projected.get("hours", 0)

                if emp_proj_hours > 0 and cm_end_date:
                    if not cm_billable_entries.empty:
                        emp_cm_entries = cm_billable_entries[
                            cm_billable_entries["employee_id"] == emp["id"]
                        ]
                        if not emp_cm_entries.empty:
                            last_entry = pd.to_datetime(emp_cm_entries["date"].max()).date()
                            missing_start = last_entry + timedelta(days=1)
                        else:
                            missing_start = cm_start_date
                    else:
                        missing_start = cm_start_date

                    if missing_start and missing_start <= cm_end_date:
                        missing_days = int(np.busday_count(missing_start, cm_end_date))
                        if cm_end_date.weekday() < 5:
                            missing_days += 1
                        missing_days = max(missing_days, 0)
                    else:
                        missing_days = 0

                    if missing_days > 0:
                        emp_projected_missing = emp_proj_hours * (
                            missing_days / cm_available_working_days
                        )
                        ytd_billable += emp_actual_billable + emp_projected_missing
                    else:
                        ytd_billable += emp_actual_billable
                else:
                    ytd_billable += emp_actual_billable
            else:
                ytd_billable += emp_actual_billable

            # Possible hours — adjusted for hire/term dates
            possible_month_data = performance_data.get("possible", {}).get(month_name, {})
            emp_possible = possible_month_data.get(emp_id_str, {})
            possible_hours = emp_possible.get("hours", 0)

            # Prorate possible hours for employees who started/left mid-period
            if pd.notna(emp.get("hire_date")):
                hire_date = pd.to_datetime(emp["hire_date"]).date()
            else:
                hire_date = datetime(target_year, 1, 1).date()

            if pd.notna(emp.get("term_date")):
                term_date = pd.to_datetime(emp["term_date"]).date()
            else:
                term_date = datetime(target_year, 12, 31).date()

            working_days = _get_working_days_in_range(
                hire_date, term_date, months_df, target_year, month_num
            )
            possible_worked_days = emp_possible.get("worked_days", 21)

            if possible_worked_days > 0 and working_days != possible_worked_days:
                daily_rate = possible_hours / possible_worked_days
                adjusted_possible = daily_rate * working_days
            else:
                adjusted_possible = possible_hours

            ytd_possible += adjusted_possible

            # PTO
            if not full_year_te.empty:
                month_start_str = f"{target_year}-{month_num:02d}-01"
                month_end_day = cal_mod.monthrange(target_year, month_num)[1]
                month_end_str = f"{target_year}-{month_num:02d}-{month_end_day}"

                month_entries = full_year_te[
                    (full_year_te["date"] >= month_start_str)
                    & (full_year_te["date"] <= month_end_str)
                ]

                if not month_entries.empty:
                    emp_entries = month_entries[month_entries["employee_id"] == emp["id"]]
                    pto_entries = emp_entries[emp_entries["project_id"] == "FRINGE.PTO"]
                    emp_ytd_pto += pto_entries["hours"].sum() if not pto_entries.empty else 0

        emp_available = max(ytd_possible - emp_ytd_pto, 0)
        utilization_pct = (ytd_billable / emp_available * 100) if emp_available > 0 else 0

        results.append(
            EmployeeBillableUtilizationEntry(
                employee_id=int(emp["id"]),
                name=emp["name"],
                utilization_pct=round(utilization_pct, 1),
            )
        )

    results.sort(key=lambda x: x.utilization_pct, reverse=True)
    return results


@router.get("/overview/burn-rate", response_model=list[MonthlyBurnRateEntry])
def get_monthly_burn_rate(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    billable_only: bool = Query(True, description="Filter to billable projects only"),
    db: DatabaseManager = Depends(get_db),
):
    """Return monthly burn rate (labor + expenses)."""
    projects_df = db.get_projects()

    billable_project_ids: list = []
    if billable_only and not projects_df.empty:
        billable_project_ids = projects_df[projects_df["billable"] == 1]["id"].tolist()

    time_entries_df = db.get_time_entries(start_date=start_date, end_date=end_date)
    expenses_df = db.get_expenses()

    # Filter expenses by date if needed
    if not expenses_df.empty and (start_date or end_date):
        expenses_df["date"] = pd.to_datetime(expenses_df["date"])
        if start_date:
            expenses_df = expenses_df[expenses_df["date"] >= start_date]
        if end_date:
            expenses_df = expenses_df[expenses_df["date"] <= end_date]

    # Filter to billable projects
    if billable_project_ids:
        if not time_entries_df.empty:
            time_entries_df = time_entries_df[
                time_entries_df["project_id"].isin(billable_project_ids)
            ]
        if not expenses_df.empty:
            expenses_df = expenses_df[expenses_df["project_id"].isin(billable_project_ids)]

    # Labor costs by month
    labor_by_month: dict[str, float] = {}
    if not time_entries_df.empty:
        time_entries_df["date"] = pd.to_datetime(time_entries_df["date"])
        time_entries_df["month"] = time_entries_df["date"].dt.to_period("M")
        for month, group in time_entries_df.groupby("month"):
            labor_cost = (group["hours"] * group["hourly_rate"]).sum()
            labor_by_month[str(month)] = float(labor_cost)

    # Expense costs by month
    expense_by_month: dict[str, float] = {}
    if not expenses_df.empty:
        if not pd.api.types.is_datetime64_any_dtype(expenses_df["date"]):
            expenses_df["date"] = pd.to_datetime(expenses_df["date"])
        expenses_df["month"] = expenses_df["date"].dt.to_period("M")
        for month, group in expenses_df.groupby("month"):
            expense_cost = group["amount"].sum()
            expense_by_month[str(month)] = float(expense_cost)

    all_months = sorted(set(list(labor_by_month.keys()) + list(expense_by_month.keys())))

    results: list[MonthlyBurnRateEntry] = []
    for month in all_months:
        labor = labor_by_month.get(month, 0)
        expense = expense_by_month.get(month, 0)
        results.append(
            MonthlyBurnRateEntry(
                month=month,
                labor_cost=round(labor, 2),
                expense_cost=round(expense, 2),
                total_burn=round(labor + expense, 2),
            )
        )

    return results


# ---------------------------------------------------------------------------
# 1. Client Analysis
# ---------------------------------------------------------------------------

@router.get("/client-analysis", response_model=list[ClientAnalysisEntry])
def get_client_analysis(
    year: int = Query(..., description="Calendar year to analyse"),
    db: DatabaseManager = Depends(get_db),
):
    """Return revenue and cost breakdown by client for a given year."""
    projects_df = db.get_projects()
    time_entries_df = db.get_time_entries()
    expenses_df = db.get_expenses()

    if time_entries_df.empty or projects_df.empty:
        return []

    # Filter time entries to year
    time_entries_df["date"] = pd.to_datetime(time_entries_df["date"])
    time_entries_df = time_entries_df[time_entries_df["date"].dt.year == year]

    if time_entries_df.empty:
        return []

    # Calculate revenue per entry
    time_entries_df["revenue"] = time_entries_df.apply(_calculate_entry_revenue, axis=1)

    # Join with projects to get client
    client_df = time_entries_df.merge(
        projects_df[["id", "client"]],
        left_on="project_id",
        right_on="id",
        how="left",
    )

    # Revenue by client
    client_revenue = client_df.groupby("client")["revenue"].sum().reset_index()
    client_revenue.columns = ["client", "revenue"]

    # Labor cost = revenue for billable entries
    client_labor = client_df.groupby("client")["revenue"].sum().reset_index()
    client_labor.columns = ["client", "labor_cost"]

    # Expenses by client (via project)
    if not expenses_df.empty:
        expenses_df["date"] = pd.to_datetime(expenses_df["date"])
        expenses_df = expenses_df[expenses_df["date"].dt.year == year]

        if not expenses_df.empty:
            exp_client = expenses_df.merge(
                projects_df[["id", "client"]],
                left_on="project_id",
                right_on="id",
                how="left",
            )
            client_expenses = exp_client.groupby("client")["amount"].sum().reset_index()
            client_expenses.columns = ["client", "expenses"]
        else:
            client_expenses = pd.DataFrame(columns=["client", "expenses"])
    else:
        client_expenses = pd.DataFrame(columns=["client", "expenses"])

    # Combine
    summary = client_revenue.merge(client_labor, on="client", how="outer")
    summary = summary.merge(client_expenses, on="client", how="outer").fillna(0)
    summary["total_cost"] = summary["labor_cost"] + summary["expenses"]
    summary["profit"] = summary["revenue"] - summary["total_cost"]
    summary["margin_pct"] = summary.apply(
        lambda r: (r["profit"] / r["revenue"] * 100) if r["revenue"] > 0 else 0.0, axis=1
    )

    summary = summary.sort_values("revenue", ascending=False)
    return df_to_records(summary)


# ---------------------------------------------------------------------------
# 2. Year Forecast
# ---------------------------------------------------------------------------

@router.get("/year-forecast", response_model=YearForecastResponse)
def get_year_forecast(
    year: int = Query(..., description="Calendar year to forecast"),
    method: str = Query("allocations", description="Projection method: 'allocations' or 'average'"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return a full-year revenue forecast combining actuals for past months
    and projections for future months.
    """
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Load time entries for the year
    time_entries_df = db.get_time_entries(
        start_date=f"{year}-01-01",
        end_date=f"{year}-12-31",
    )

    # Calculate revenue
    if not time_entries_df.empty:
        time_entries_df["date"] = pd.to_datetime(time_entries_df["date"])
        time_entries_df["revenue"] = time_entries_df.apply(_calculate_entry_revenue, axis=1)
        time_entries_df["month_num"] = time_entries_df["date"].dt.month
        ytd_monthly = time_entries_df.groupby("month_num")["revenue"].sum().to_dict()
    else:
        ytd_monthly = {}

    # Determine which months are actual vs projected
    if year == current_year:
        actual_through = current_month
    elif year < current_year:
        actual_through = 12  # all months are actual for past years
    else:
        actual_through = 0  # all months are projected for future years

    # YTD actual revenue
    ytd_actual = sum(ytd_monthly.get(m, 0) for m in range(1, actual_through + 1))

    # Calculate projected months
    projected_monthly = {}

    if method == "average":
        ytd_avg = ytd_actual / actual_through if actual_through > 0 else 0.0
        for m in range(actual_through + 1, 13):
            projected_monthly[m] = ytd_avg
    else:
        # Allocations-based
        allocations_df = db.get_allocations()
        months_df = db.get_months()

        if not allocations_df.empty and not months_df.empty:
            allocations_df["allocation_date"] = pd.to_datetime(allocations_df["allocation_date"])

            for month_num in range(actual_through + 1, 13):
                month_str = f"{year}-{month_num:02d}"
                month_allocs = allocations_df[
                    allocations_df["allocation_date"].dt.strftime("%Y-%m") == month_str
                ]

                if month_allocs.empty:
                    projected_monthly[month_num] = 0.0
                    continue

                month_info = months_df[
                    (months_df["year"] == year) & (months_df["month"] == month_num)
                ]

                if month_info.empty:
                    projected_monthly[month_num] = 0.0
                    continue

                working_days = int(month_info["working_days"].iloc[0])
                holidays = month_info["holidays"].iloc[0] if "holidays" in month_info.columns else 0
                holidays = holidays if pd.notna(holidays) else 0
                available_days = max(working_days - int(holidays), 0)

                month_revenue = 0.0
                for _, alloc in month_allocs.iterrows():
                    fte = alloc.get("allocated_fte", 0) or 0
                    bill_rate = alloc.get("bill_rate", 0) or 0
                    if pd.notna(fte) and pd.notna(bill_rate):
                        month_revenue += float(fte) * available_days * 8 * float(bill_rate)

                projected_monthly[month_num] = month_revenue
        else:
            # Fallback to average if no allocation data
            ytd_avg = ytd_actual / actual_through if actual_through > 0 else 0.0
            for m in range(actual_through + 1, 13):
                projected_monthly[m] = ytd_avg

    # Build response
    months_list = []
    for m in range(1, 13):
        if m <= actual_through:
            revenue = ytd_monthly.get(m, 0)
            data_type = "Actual"
        else:
            revenue = projected_monthly.get(m, 0)
            data_type = "Projected (Alloc)" if method == "allocations" else "Projected (Avg)"

        months_list.append(YearForecastMonth(
            month=m,
            month_name=datetime(year, m, 1).strftime("%B"),
            revenue=float(revenue),
            data_type=data_type,
        ))

    projected_remaining = sum(projected_monthly.values())
    full_year_forecast = ytd_actual + projected_remaining

    return YearForecastResponse(
        ytd_actual=ytd_actual,
        projected_remaining=projected_remaining,
        full_year_forecast=full_year_forecast,
        months=months_list,
    )


# ---------------------------------------------------------------------------
# 3. Funding Review (all projects)
# ---------------------------------------------------------------------------

def _build_funding_entry(
    project,
    db: DatabaseManager,
    allocations_df=None,
    months_df=None,
) -> FundingReviewEntry:
    """Build a FundingReviewEntry for a single project row.

    Args:
        project: A pandas Series representing a single project row.
        db: DatabaseManager instance.
        allocations_df: Optional pre-fetched allocations DataFrame to avoid
            per-project db.get_allocations() calls.
        months_df: Optional pre-fetched months DataFrame to avoid
            per-project db.get_months() calls.
    """
    from app.services.funding_helpers import (
        calculate_avg_monthly_invoice,
        calculate_current_month_potential,
        calculate_funding_runway,
        get_funding_health_status,
    )

    project_id = str(project["id"])
    awarded_value = float(project.get("awarded_value", 0) or 0)
    budget_used = float(project.get("budget_used", 0) or 0)
    remaining = awarded_value - budget_used
    funding_pct = (remaining / awarded_value * 100) if awarded_value > 0 else 0.0

    avg_monthly = calculate_avg_monthly_invoice(project_id, db, DataProcessor)
    runway = calculate_funding_runway(remaining, avg_monthly)
    health_label = get_funding_health_status(funding_pct)
    current_potential = calculate_current_month_potential(
        project_id, db, allocations_df=allocations_df, months_df=months_df
    )

    # Handle infinity for JSON serialisation
    runway_value = None if runway == float("inf") else float(runway)

    return FundingReviewEntry(
        project_id=project_id,
        project_name=str(project.get("name", project_id)),
        client=project.get("client"),
        project_manager=project.get("project_manager"),
        status=project.get("status"),
        quoted_value=float(project.get("quoted_value", 0) or 0),
        awarded_value=awarded_value,
        budget_used=budget_used,
        remaining=remaining,
        avg_monthly_invoice=float(avg_monthly),
        funding_runway_months=runway_value,
        funding_pct=funding_pct,
        health_label=health_label,
        current_month_potential=float(current_potential),
    )


@router.get("/funding-review", response_model=list[FundingReviewEntry])
def get_funding_review(
    db: DatabaseManager = Depends(get_db),
):
    """Return funding review data for all billable projects."""
    projects_df = db.get_projects()

    if projects_df.empty:
        return []

    billable = projects_df[projects_df.get("billable", pd.Series(dtype=int)) == 1] if "billable" in projects_df.columns else projects_df
    if billable.empty:
        return []

    # Pre-fetch shared data once to avoid N+1 queries in the per-project loop
    all_allocations = db.get_allocations()
    months_df = db.get_months()

    results = []
    for _, project in billable.iterrows():
        try:
            entry = _build_funding_entry(
                project, db,
                allocations_df=all_allocations,
                months_df=months_df,
            )
            results.append(entry)
        except Exception:
            logger.exception("Failed to process funding review entry for project %s", project.get("id", "unknown"))
            continue

    return results


# ---------------------------------------------------------------------------
# 4. Funding Review Detail (single project)
# ---------------------------------------------------------------------------

@router.get("/funding-review/{project_id}", response_model=FundingReviewDetailResponse)
def get_funding_review_detail(
    project_id: str,
    db: DatabaseManager = Depends(get_db),
):
    """Return detailed funding review for a single project including revenue history."""
    from app.services.funding_helpers import (
        calculate_avg_monthly_invoice,
        calculate_current_month_potential,
        calculate_funding_runway,
        get_funding_health_status,
    )



    projects_df = db.get_projects()
    if projects_df.empty:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    project_row = projects_df[projects_df["id"] == project_id]
    if project_row.empty:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    project = project_row.iloc[0]

    # Base funding entry
    base = _build_funding_entry(project, db)

    # Monthly revenue history via performance metrics
    from dateutil.relativedelta import relativedelta

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - relativedelta(months=12)).strftime("%Y-%m-%d")

    monthly_history = []
    past_month_revenue = 0.0

    try:
        metrics = DataProcessor.get_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            constraint={"project_id": project_id},
            db=db,
        )
        actuals = metrics.get("actuals", {})

        for month_name, employees in actuals.items():
            month_rev = sum(
                emp_data.get("revenue", 0)
                for emp_data in employees.values()
            )
            monthly_history.append(MonthlyRevenueEntry(month=month_name, revenue=float(month_rev)))

        # Past month revenue = most recent month's actual
        if monthly_history:
            past_month_revenue = monthly_history[-1].revenue
    except Exception:
        logger.exception("Failed to compute past month revenue for project %s", project_id)

    return FundingReviewDetailResponse(
        **base.model_dump(),
        past_month_revenue=past_month_revenue,
        monthly_revenue_history=monthly_history,
    )


# ---------------------------------------------------------------------------
# 5. Detailed Utilization
# ---------------------------------------------------------------------------

def _parse_time_frame(time_frame: str, year: int):
    """
    Parse a time_frame string into (start_date, end_date) strings.

    Supports: current_month, ytd_company, ytd_gov, qtd_company, qtd_gov,
    q1-q4, and month names like 'january'.
    """
    now = datetime.now()
    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]

    tf = time_frame.lower().strip()

    if tf == "current_month":
        start = datetime(now.year, now.month, 1)
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        end = datetime(now.year, now.month, last_day)
    elif tf == "ytd_company":
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31)
    elif tf == "ytd_gov":
        # Gov fiscal year: Oct prior year - Sep this year
        start = datetime(year - 1, 10, 1)
        end = datetime(year, 9, 30)
    elif tf == "qtd_company":
        # Current quarter to date (company)
        q = (now.month - 1) // 3
        start = datetime(year, q * 3 + 1, 1)
        import calendar
        end_month = min(now.month, q * 3 + 3)
        last_day = calendar.monthrange(year, end_month)[1]
        end = datetime(year, end_month, last_day)
    elif tf == "qtd_gov":
        # Gov quarter: Oct-Dec=Q1, Jan-Mar=Q2, Apr-Jun=Q3, Jul-Sep=Q4
        gov_month = (now.month - 10) % 12  # 0-based from October
        q = gov_month // 3
        gov_q_starts = [(10, year - 1), (1, year), (4, year), (7, year)]
        sm, sy = gov_q_starts[q]
        start = datetime(sy, sm, 1)
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        end = datetime(now.year, now.month, last_day)
    elif tf in ("q1", "q2", "q3", "q4"):
        q = int(tf[1])
        start_month = (q - 1) * 3 + 1
        end_month = q * 3
        start = datetime(year, start_month, 1)
        import calendar
        last_day = calendar.monthrange(year, end_month)[1]
        end = datetime(year, end_month, last_day)
    elif tf in month_names:
        m = month_names.index(tf) + 1
        start = datetime(year, m, 1)
        import calendar
        last_day = calendar.monthrange(year, m)[1]
        end = datetime(year, m, last_day)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid time_frame: {time_frame}")

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@router.get("/utilization/detailed", response_model=list[DetailedUtilizationEntry])
def get_detailed_utilization(
    year: int = Query(..., description="Calendar year"),
    time_frame: str = Query("ytd_company", description="Time frame: current_month, ytd_company, ytd_gov, qtd_company, qtd_gov, q1-q4, or month name"),
    employee_id: Optional[int] = Query(None, description="Filter by employee ID"),
    billable_only: bool = Query(True, description="Filter to billable employees only"),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return detailed utilization for employees using actual months data,
    accounting for hire/term dates, PTO, and holidays.
    """


    start_date_str, end_date_str = _parse_time_frame(time_frame, year)
    start_dt = pd.to_datetime(start_date_str)
    end_dt = pd.to_datetime(end_date_str)

    employees_df = db.get_employees()
    if billable_only and not employees_df.empty:
        employees_df = employees_df[employees_df['billable'] == 1]
    if employees_df.empty:
        return []

    if employee_id is not None:
        employees_df = employees_df[employees_df["id"] == employee_id]
        if employees_df.empty:
            return []

    months_df = db.get_months()
    time_entries_df = db.get_time_entries(start_date=start_date_str, end_date=end_date_str)
    allocations_df = db.get_allocations()

    # Pre-parse dates on time entries
    if not time_entries_df.empty:
        time_entries_df["date"] = pd.to_datetime(time_entries_df["date"])

    # Pre-parse allocation dates
    if not allocations_df.empty:
        allocations_df["allocation_date"] = pd.to_datetime(allocations_df["allocation_date"])

    results = []

    for _, emp in employees_df.iterrows():
        eid = int(emp["id"])
        hire_date = pd.to_datetime(emp.get("hire_date")) if pd.notna(emp.get("hire_date")) else None
        term_date = pd.to_datetime(emp.get("term_date")) if pd.notna(emp.get("term_date")) else None
        pto_annual = float(emp.get("pto_accrual", 0) or 0)
        holidays_annual = float(emp.get("holidays", 0) or 0)

        total_possible = 0.0
        total_actual = 0.0
        total_billable = 0.0
        total_projected = 0.0
        total_pto = 0.0
        total_holiday = 0.0
        monthly_entries = []

        # Iterate over each month in range
        current = start_dt.replace(day=1)
        while current <= end_dt:
            m_year = current.year
            m_month = current.month

            # Check employee active in this month
            if hire_date and current < hire_date.replace(day=1):
                import calendar as cal
                last_day = cal.monthrange(m_year, m_month)[1]
                current = current + pd.DateOffset(months=1)
                continue
            if term_date and current > term_date.replace(day=1) + pd.DateOffset(months=0):
                current = current + pd.DateOffset(months=1)
                continue

            # Get working days from months table
            working_days = 21  # default
            if not months_df.empty:
                month_row = months_df[
                    (months_df["year"] == m_year) & (months_df["month"] == m_month)
                ]
                if not month_row.empty:
                    working_days = int(month_row["working_days"].iloc[0])
                    hol = month_row["holidays"].iloc[0] if "holidays" in month_row.columns else 0
                    hol = hol if pd.notna(hol) else 0
                    working_days = max(working_days - int(hol), 0)

            possible_hrs = working_days * 8.0

            # Prorate for hire/term date within the month
            import calendar as cal
            month_start = pd.Timestamp(m_year, m_month, 1)
            last_day = cal.monthrange(m_year, m_month)[1]
            month_end = pd.Timestamp(m_year, m_month, last_day)

            if hire_date and hire_date > month_start and hire_date <= month_end:
                ratio = (month_end - hire_date).days / (month_end - month_start).days if (month_end - month_start).days > 0 else 1
                possible_hrs *= ratio
            if term_date and term_date >= month_start and term_date < month_end:
                ratio = (term_date - month_start).days / (month_end - month_start).days if (month_end - month_start).days > 0 else 1
                possible_hrs *= ratio

            # PTO and holiday hours (prorated monthly from annual)
            pto_hrs = pto_annual / 12.0
            hol_hrs = holidays_annual / 12.0

            # Actual hours from time entries
            actual_hrs = 0.0
            billable_hrs = 0.0
            if not time_entries_df.empty:
                emp_entries = time_entries_df[
                    (time_entries_df["employee_id"] == eid)
                    & (time_entries_df["date"].dt.year == m_year)
                    & (time_entries_df["date"].dt.month == m_month)
                ]
                if not emp_entries.empty:
                    actual_hrs = float(emp_entries["hours"].sum())
                    if "billable" in emp_entries.columns:
                        billable_hrs = float(emp_entries.loc[emp_entries["billable"] == 1, "hours"].sum())

            # Projected hours from allocations
            proj_hrs = 0.0
            if not allocations_df.empty:
                emp_allocs = allocations_df[
                    (allocations_df["employee_id"] == eid)
                    & (allocations_df["allocation_date"].dt.year == m_year)
                    & (allocations_df["allocation_date"].dt.month == m_month)
                ]
                if not emp_allocs.empty:
                    for _, alloc in emp_allocs.iterrows():
                        fte = float(alloc.get("allocated_fte", 0) or 0)
                        proj_hrs += fte * working_days * 8.0

            # Utilization for this month
            denom = possible_hrs - pto_hrs
            util_pct = (billable_hrs / denom * 100) if denom > 0 else None

            month_label = f"{datetime(m_year, m_month, 1).strftime('%B %Y')}"
            monthly_entries.append(EmployeeMonthUtilization(
                month=month_label,
                possible_hours=round(possible_hrs, 2),
                actual_hours=round(actual_hrs, 2),
                actual_billable_hours=round(billable_hrs, 2),
                projected_hours=round(proj_hrs, 2),
                pto_hours=round(pto_hrs, 2),
                holiday_hours=round(hol_hrs, 2),
                utilization_pct=round(util_pct, 2) if util_pct is not None else None,
            ))

            total_possible += possible_hrs
            total_actual += actual_hrs
            total_billable += billable_hrs
            total_projected += proj_hrs
            total_pto += pto_hrs
            total_holiday += hol_hrs

            current = current + pd.DateOffset(months=1)

        # Overall utilization
        denom = total_possible - total_pto
        overall_util = (total_billable / denom * 100) if denom > 0 else None

        results.append(DetailedUtilizationEntry(
            employee_id=eid,
            employee_name=str(emp.get("name", "")),
            role=emp.get("role"),
            billable=int(emp.get("billable", 0) or 0),
            possible_hours=round(total_possible, 2),
            actual_hours=round(total_actual, 2),
            actual_billable_hours=round(total_billable, 2),
            projected_hours=round(total_projected, 2),
            pto_hours=round(total_pto, 2),
            holiday_hours=round(total_holiday, 2),
            utilization_pct=round(overall_util, 2) if overall_util is not None else None,
            monthly_breakdown=monthly_entries,
        ))

    return results


# ---------------------------------------------------------------------------
# 6. Allocation Planning
# ---------------------------------------------------------------------------

@router.get("/allocation-planning", response_model=list[AllocationPlanningEntry])
def get_allocation_planning(
    year: int = Query(..., description="Calendar year"),
    month: Optional[int] = Query(None, description="Month number (1-12). If omitted, all months in year."),
    employee_id: Optional[int] = Query(None, description="Filter by employee ID"),
    billable_only: bool = Query(True, description="Filter to billable employees only"),
    db: DatabaseManager = Depends(get_db),
):
    """Return allocation planning data showing capacity vs allocated hours per employee."""
    import calendar as cal

    employees_df = db.get_employees()
    if billable_only and not employees_df.empty:
        employees_df = employees_df[employees_df['billable'] == 1]
    if employees_df.empty:
        return []

    if employee_id is not None:
        employees_df = employees_df[employees_df["id"] == employee_id]
        if employees_df.empty:
            return []

    months_df = db.get_months()
    allocations_df = db.get_allocations()

    if not allocations_df.empty:
        allocations_df["allocation_date"] = pd.to_datetime(allocations_df["allocation_date"])

    # Determine month range
    if month is not None:
        month_range = [month]
    else:
        month_range = list(range(1, 13))

    results = []

    for _, emp in employees_df.iterrows():
        eid = int(emp["id"])
        target_alloc = float(emp.get("target_allocation", 0.3) or 0.3)
        target_fte = target_alloc / 100.0 if target_alloc > 1 else target_alloc

        total_possible = 0.0
        total_allocated = 0.0
        project_map = {}  # project_id -> {name, fte, hours, bill_rate}

        for m in month_range:
            # Working days from months table
            working_days = 21
            if not months_df.empty:
                month_row = months_df[
                    (months_df["year"] == year) & (months_df["month"] == m)
                ]
                if not month_row.empty:
                    working_days = int(month_row["working_days"].iloc[0])
                    hol = month_row["holidays"].iloc[0] if "holidays" in month_row.columns else 0
                    hol = hol if pd.notna(hol) else 0
                    working_days = max(working_days - int(hol), 0)

            possible_hrs = working_days * 8.0 * target_fte
            total_possible += possible_hrs

            # Allocations for this employee+month
            if not allocations_df.empty:
                emp_allocs = allocations_df[
                    (allocations_df["employee_id"] == eid)
                    & (allocations_df["allocation_date"].dt.year == year)
                    & (allocations_df["allocation_date"].dt.month == m)
                ]
                for _, alloc in emp_allocs.iterrows():
                    fte = float(alloc.get("allocated_fte", 0) or 0)
                    alloc_hrs = fte * working_days * 8.0
                    total_allocated += alloc_hrs
                    pid = str(alloc.get("project_id", ""))
                    pname = str(alloc.get("project_name", pid))
                    br = float(alloc.get("bill_rate", 0) or 0)

                    if pid in project_map:
                        project_map[pid]["fte"] += fte
                        project_map[pid]["hours"] += alloc_hrs
                    else:
                        project_map[pid] = {
                            "name": pname,
                            "fte": fte,
                            "hours": alloc_hrs,
                            "bill_rate": br,
                        }

        allocation_pct = (total_allocated / total_possible * 100) if total_possible > 0 else 0.0
        variance = total_allocated - total_possible

        if allocation_pct > 120:
            status = "Over-Allocated"
        elif allocation_pct >= 100:
            status = "At Capacity"
        elif allocation_pct >= 80:
            status = "Healthy"
        else:
            status = "Under-Allocated"

        breakdown = [
            AllocationProjectBreakdown(
                project_id=pid,
                project_name=info["name"],
                allocated_fte=round(info["fte"], 4),
                allocated_hours=round(info["hours"], 2),
                bill_rate=info["bill_rate"],
            )
            for pid, info in project_map.items()
        ]

        results.append(AllocationPlanningEntry(
            employee_id=eid,
            employee_name=str(emp.get("name", "")),
            target_fte=round(target_fte, 4),
            possible_hours=round(total_possible, 2),
            allocated_hours=round(total_allocated, 2),
            allocation_pct=round(allocation_pct, 2),
            variance=round(variance, 2),
            status=status,
            project_breakdown=breakdown,
        ))

    return results


# ---------------------------------------------------------------------------
# 7. Project Utilization
# ---------------------------------------------------------------------------

@router.get("/project-utilization", response_model=list[ProjectUtilizationEntry])
def get_project_utilization(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: DatabaseManager = Depends(get_db),
):
    """Return utilization metrics for all billable projects."""
    from app.services.funding_helpers import calculate_all_projects_utilization



    try:
        result_df = calculate_all_projects_utilization(db, DataProcessor, start_date, end_date)
    except Exception as exc:
        logger.exception("Error computing project utilization")
        raise HTTPException(status_code=500, detail=f"Error computing project utilization: {exc}")

    if result_df.empty:
        return []

    return df_to_records(result_df)


# ---------------------------------------------------------------------------
# 8. Combined Performance
# ---------------------------------------------------------------------------

@router.get("/performance/combined", response_model=CombinedPerformanceResponse)
def get_combined_performance(
    project_id: str = Query(..., description="Project ID"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD). Defaults to project start."),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to project end."),
    db: DatabaseManager = Depends(get_db),
):
    """
    Return combined actual + projected performance for a project,
    using actuals for past months, projections for future, and blended for the current month.
    """


    # Get project dates if not provided
    if not start_date or not end_date:
        projects_df = db.get_projects()
        if projects_df.empty:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        proj = projects_df[projects_df["id"] == project_id]
        if proj.empty:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        proj_row = proj.iloc[0]
        if not start_date:
            start_date = str(proj_row.get("start_date", datetime.now().strftime("%Y-%m-%d")))
        if not end_date:
            end_date = str(proj_row.get("end_date", datetime.now().strftime("%Y-%m-%d")))

    try:
        metrics = DataProcessor.get_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            constraint={"project_id": project_id},
            db=db,
        )
    except Exception as exc:
        logger.exception("Error computing combined performance metrics for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Error computing performance metrics: {exc}")

    actuals = metrics.get("actuals", {})
    projected = metrics.get("projected", {})

    now = datetime.now()
    current_month_key = now.strftime("%B %Y")

    # Collect all month keys
    all_months = sorted(
        set(list(actuals.keys()) + list(projected.keys())),
        key=lambda x: pd.to_datetime(x, format="%B %Y"),
    )

    # Get project budget for budget_pct calculation
    projects_df = db.get_projects()
    budget = 0.0
    if not projects_df.empty:
        proj = projects_df[projects_df["id"] == project_id]
        if not proj.empty:
            budget = float(proj.iloc[0].get("awarded_value", 0) or 0)

    monthly_rows = []
    cumulative_rev = 0.0
    total_hours = 0.0
    total_accrued = 0.0

    for month_key in all_months:
        month_dt = pd.to_datetime(month_key, format="%B %Y")

        # Determine month type
        if month_dt.year < now.year or (month_dt.year == now.year and month_dt.month < now.month):
            month_type = "past"
        elif month_dt.year == now.year and month_dt.month == now.month:
            month_type = "active"
        else:
            month_type = "future"

        # Actual hours/revenue
        a_hours = 0.0
        a_revenue = 0.0
        if month_key in actuals:
            for emp_data in actuals[month_key].values():
                a_hours += float(emp_data.get("hours", 0) or 0)
                a_revenue += float(emp_data.get("revenue", 0) or 0)

        # Projected hours/revenue
        p_hours = 0.0
        p_revenue = 0.0
        if month_key in projected:
            for emp_data in projected[month_key].values():
                p_hours += float(emp_data.get("hours", 0) or 0)
                p_revenue += float(emp_data.get("revenue", 0) or 0)

        # Combined logic based on month type
        if month_type == "past":
            combined_hours = a_hours
            combined_revenue = a_revenue
        elif month_type == "active":
            # Blend: use actuals if available, supplement with projected
            combined_hours = max(a_hours, p_hours)
            combined_revenue = max(a_revenue, p_revenue)
        else:
            combined_hours = p_hours
            combined_revenue = p_revenue

        cumulative_rev += combined_revenue
        total_hours += combined_hours
        total_accrued += combined_revenue

        b_pct = (cumulative_rev / budget * 100) if budget > 0 else None

        # Status label
        if b_pct is not None:
            if b_pct > 100:
                status = "Over Budget"
            elif b_pct > 80:
                status = "Near Budget"
            else:
                status = "On Track"
        else:
            status = None

        monthly_rows.append(CombinedMonthlyBreakdown(
            month=month_key,
            month_type=month_type,
            actual_hours=round(a_hours, 2),
            projected_hours=round(p_hours, 2),
            combined_hours=round(combined_hours, 2),
            actual_revenue=round(a_revenue, 2),
            projected_revenue=round(p_revenue, 2),
            combined_revenue=round(combined_revenue, 2),
            cumulative_revenue=round(cumulative_rev, 2),
            budget_pct=round(b_pct, 2) if b_pct is not None else None,
            status=status,
        ))

    # Summary
    overall_pct = (total_accrued / budget * 100) if budget > 0 else 0.0
    if overall_pct > 100:
        budget_status = "Over Budget"
    elif overall_pct > 80:
        budget_status = "Near Budget"
    else:
        budget_status = "On Track"

    return CombinedPerformanceResponse(
        summary=CombinedPerformanceSummary(
            total_hours=round(total_hours, 2),
            total_accrued=round(total_accrued, 2),
            budget_status=budget_status,
            budget_pct=round(overall_pct, 2),
        ),
        monthly_breakdown=monthly_rows,
    )
