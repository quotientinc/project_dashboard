"""
Employee Utilization Analysis tab - detailed monthly and YTD utilization tracking.
"""
import html

import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, ColumnsAutoSizeMode

from utils.logger import get_logger

logger = get_logger(__name__)


def _get_billable_employees(db, period_start, period_end):
    """Get billable employees active during the given period.

    Returns a DataFrame of employees where billable=1 and who have not been
    terminated before the period start date.
    """
    employees_df = db.get_employees()
    if employees_df.empty:
        return employees_df

    # Filter to billable employees only
    billable_df = employees_df[employees_df['billable'] == 1].copy()

    # Exclude employees terminated before the period start
    period_start_date = pd.to_datetime(period_start).date()
    period_end_date = pd.to_datetime(period_end).date()

    def is_active_in_period(row):
        # Check termination date
        if pd.notna(row.get('term_date')):
            term_date = pd.to_datetime(row['term_date']).date()
            if term_date < period_start_date:
                return False
        # Check hire date
        if pd.notna(row.get('hire_date')):
            hire_date = pd.to_datetime(row['hire_date']).date()
            if hire_date > period_end_date:
                return False
        return True

    billable_df = billable_df[billable_df.apply(is_active_in_period, axis=1)]
    return billable_df


def _get_period_date_range(time_frame, year):
    """Get start and end dates for a time frame period.

    Supports Company FY (calendar year), Government FY (Oct-Sep),
    QTD (quarter-to-date) auto-detection, and legacy quarter names.

    Returns (start_date, end_date) as strings in YYYY-MM-DD format.
    """
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')

    # Company FY (calendar) quarters
    company_quarters = {
        "Q1 (Company)": (f"{year}-01-01", f"{year}-03-31"),
        "Q2 (Company)": (f"{year}-04-01", f"{year}-06-30"),
        "Q3 (Company)": (f"{year}-07-01", f"{year}-09-30"),
        "Q4 (Company)": (f"{year}-10-01", f"{year}-12-31"),
    }

    # Government FY quarters (FY starts Oct 1 of prior calendar year)
    # FY2026 runs Oct 1, 2025 -> Sep 30, 2026
    gov_quarters = {
        "Q1 (Gov)": (f"{year - 1}-10-01", f"{year - 1}-12-31"),
        "Q2 (Gov)": (f"{year}-01-01", f"{year}-03-31"),
        "Q3 (Gov)": (f"{year}-04-01", f"{year}-06-30"),
        "Q4 (Gov)": (f"{year}-07-01", f"{year}-09-30"),
    }

    # Legacy support: map old quarter names to company quarters
    legacy_quarters = {
        "Quarter 1": company_quarters["Q1 (Company)"],
        "Quarter 2": company_quarters["Q2 (Company)"],
        "Quarter 3": company_quarters["Q3 (Company)"],
        "Quarter 4": company_quarters["Q4 (Company)"],
    }

    all_quarters = {**company_quarters, **gov_quarters, **legacy_quarters}

    if time_frame == "Current Month":
        if year == now.year:
            month = now.month
        else:
            month = 1  # Default to January for non-current years
        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"

    elif time_frame == "QTD (Company)":
        # Ordered list of company quarter keys for iteration
        cq_keys = ["Q1 (Company)", "Q2 (Company)", "Q3 (Company)", "Q4 (Company)"]

        if year == now.year:
            # Find which company quarter today falls in
            current_cq = None
            for key in cq_keys:
                qs, qe = company_quarters[key]
                if qs <= today_str <= qe:
                    current_cq = key
                    break

            if current_cq:
                start_date = company_quarters[current_cq][0]
                end_date = today_str
            else:
                # Edge case: today is somehow outside all quarters (should not happen)
                start_date, end_date = company_quarters["Q4 (Company)"]
        else:
            # Non-current year: return Q4 full range as fallback
            start_date, end_date = company_quarters["Q4 (Company)"]

    elif time_frame == "QTD (Gov)":
        # Ordered list of gov quarter keys for iteration
        gq_keys = ["Q1 (Gov)", "Q2 (Gov)", "Q3 (Gov)", "Q4 (Gov)"]

        if year == now.year:
            # Find which gov FY quarter today falls in
            current_gq = None
            for key in gq_keys:
                qs, qe = gov_quarters[key]
                if qs <= today_str <= qe:
                    current_gq = key
                    break

            if current_gq:
                start_date = gov_quarters[current_gq][0]
                end_date = today_str
            else:
                # Today is not in any gov quarter for this FY year.
                # This happens when today is in Oct-Dec of the current calendar year,
                # which belongs to the *next* gov FY. Fall back to Q4 full range.
                start_date, end_date = gov_quarters["Q4 (Gov)"]
        else:
            # Non-current year: return Q4 (Gov) full range as fallback
            start_date, end_date = gov_quarters["Q4 (Gov)"]

    elif time_frame == "YTD (Company)":
        # Calendar year-to-date: Jan 1 -> today (or Dec 31 for past years)
        start_date = f"{year}-01-01"
        if year == now.year:
            end_date = today_str
        else:
            end_date = f"{year}-12-31"

    elif time_frame == "YTD (Gov)":
        # Gov fiscal year-to-date: Oct 1 (prior year) -> today (or Sep 30 for past FY)
        # Gov FY convention: FY2026 = Oct 1, 2025 -> Sep 30, 2026
        start_date = f"{year - 1}-10-01"
        fy_end = f"{year}-09-30"
        if year == now.year and today_str <= fy_end:
            end_date = today_str
        else:
            end_date = fy_end

    elif time_frame in {name for name in calendar.month_name if name}:
        month_num = list(calendar.month_name).index(time_frame)
        last_day = calendar.monthrange(year, month_num)[1]
        start_date = f"{year}-{month_num:02d}-01"
        end_date = f"{year}-{month_num:02d}-{last_day}"

    else:
        if time_frame not in all_quarters:
            raise ValueError(f"Unknown time_frame: {time_frame!r}")
        start_date, end_date = all_quarters[time_frame]

    return start_date, end_date


def _get_months_in_range(start_date, end_date):
    """Return a list of month keys (e.g. 'January 2025') for all months in the date range."""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current.strftime('%B %Y'))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def _get_working_days_in_range(emp_start_date, emp_end_date, months_df, year, month):
    """Calculate working days between employee start and end date for a specific month.

    This is a module-level helper used by _calculate_monthly_utilization_data
    and render_combined_utilization_view.

    Args:
        emp_start_date: Employee's active start date (hire date or month start)
        emp_end_date: Employee's active end date (term date or month end)
        months_df: DataFrame from db.get_months()
        year: The year of the month to check
        month: The month number (1-12)

    Returns:
        int: Number of working days the employee was active in the given month
    """
    # Get month info
    month_info = months_df[
        (months_df['year'] == year) &
        (months_df['month'] == month)
    ]

    if month_info.empty:
        return 21  # Default fallback

    working_days_in_month = int(month_info['working_days'].iloc[0])
    holidays_in_month = int(month_info['holidays'].iloc[0]) if 'holidays' in month_info.columns and pd.notna(month_info['holidays'].iloc[0]) else 0
    working_days_in_month = max(working_days_in_month - holidays_in_month, 0)

    # Calculate the actual working days the employee was active
    month_start = datetime(year, month, 1).date()
    month_end = datetime(year, month, calendar.monthrange(year, month)[1]).date()

    # Determine actual start and end dates for this employee in this month
    actual_start = max(emp_start_date, month_start)
    actual_end = min(emp_end_date, month_end)

    # Guard: if end is before start, employee is not active in this month
    if actual_end < actual_start:
        return 0

    # If they worked the entire month, return full working days
    if actual_start == month_start and actual_end == month_end:
        return working_days_in_month

    # Calculate proportion of month worked
    days_in_month = (month_end - month_start).days + 1
    days_worked = (actual_end - actual_start).days + 1
    proportion = days_worked / days_in_month

    # Return prorated working days
    return int(working_days_in_month * proportion)


def _count_working_days(start_date, end_date):
    """Count weekdays (Mon-Fri) between start_date and end_date inclusive."""
    if end_date < start_date:
        return 0
    count = np.busday_count(start_date, end_date)
    # np.busday_count is start-inclusive, end-exclusive; add 1 if end_date is a weekday
    if end_date.weekday() < 5:
        count += 1
    return int(count)


def _calculate_monthly_utilization_data(db, processor, selected_year, selected_month,
                                        employees_df=None, employee_id=None, include_projected=True):
    """Calculate monthly utilization data for employees.

    This is a shared helper that extracts the data-calculation logic so it can
    be reused by _calculate_period_utilization_data and render_combined_utilization_view.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        selected_year: Year to calculate for
        selected_month: Month number (1-12) to calculate for
        employees_df: Optional pre-filtered employees DataFrame. If None, fetched from db.
        employee_id: Optional employee ID to filter to a single employee.

    Returns:
        tuple: (util_df, month_key, time_entries_df) where util_df is a DataFrame with columns:
            employee_id, name, role, pay_type, possible_hours, projected_hours,
            actual_hours, actual_billable_hours, pto_hours, holiday_hours,
            other_nonbillable_hours, utilization_pct, variance, status,
            ytd_possible_hours, ytd_actual_billable_hours,
            ytd_utilization_pct, status_num, worked_days
    """
    month_names_list = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    # Build date range for this specific month
    start_date = f"{selected_year}-{selected_month:02d}-01"
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    end_date = f"{selected_year}-{selected_month:02d}-{last_day}"

    # Get monthly metrics
    metrics = processor.get_performance_metrics(
        start_date=start_date,
        end_date=end_date
    )

    # Get YTD metrics (January 1st through end of selected month)
    ytd_start_date = f"{selected_year}-01-01"
    ytd_metrics = processor.get_performance_metrics(
        start_date=ytd_start_date,
        end_date=end_date
    )

    month_key = f"{month_names_list[selected_month - 1]} {selected_year}"

    first_day_of_month = datetime(selected_year, selected_month, 1).date()
    last_day_of_month = datetime(selected_year, selected_month, last_day).date()

    # Determine if this is the current (incomplete) month for blending logic.
    # We no longer prorate the denominator; instead we augment the numerator with
    # projected remaining hours from allocations.
    today = datetime.now().date()
    is_current_month = (selected_year == today.year and selected_month == today.month
                        and today < last_day_of_month)

    # Get months data for working days calculation
    months_df = db.get_months()

    # Get time entries for PTO and Holiday calculation
    time_entries_df = db.get_time_entries(start_date=start_date, end_date=end_date)

    # Calculate PTO and Holiday hours by employee for this month
    pto_by_employee = {}
    holiday_by_employee = {}
    if not time_entries_df.empty:
        pto_entries = time_entries_df[time_entries_df['project_id'] == 'FRINGE.PTO']
        if not pto_entries.empty:
            pto_by_employee = pto_entries.groupby('employee_id')['hours'].sum().to_dict()

        # Extract holiday hours (FRINGE.HOL)
        holiday_entries = time_entries_df[time_entries_df['project_id'] == 'FRINGE.HOL']
        if not holiday_entries.empty:
            holiday_by_employee = holiday_entries.groupby('employee_id')['hours'].sum().to_dict()

    # Compute last billable timesheet entry date per employee
    last_entry_dates = {}
    if not time_entries_df.empty:
        billable_entries = time_entries_df[time_entries_df['billable'] == 1]
        if not billable_entries.empty:
            last_entry_dates = billable_entries.groupby('employee_id')['date'].max().to_dict()

    # Get YTD time entries for PTO and Holiday calculation (fetched once, used per-employee in the loop below)
    ytd_time_entries_df = db.get_time_entries(start_date=ytd_start_date, end_date=end_date)

    # Get employees dataframe
    if employees_df is None:
        employees_df = db.get_employees()

    # Filter to specific employee if employee_id is provided
    if employee_id is not None:
        employees_df = employees_df[employees_df['id'] == employee_id]

    # Build utilization data
    util_data = []

    for _, emp in employees_df.iterrows():
        emp_id_str = str(emp['id'])

        # Skip non-billable employees
        if emp.get('billable', 0) != 1:
            continue

        # Determine employee's active date range
        if pd.notna(emp.get('hire_date')):
            hire_date = pd.to_datetime(emp['hire_date']).date()
            if hire_date > last_day_of_month:
                continue  # Skip - hired after this month
        else:
            hire_date = first_day_of_month  # Assume active from start of month

        if pd.notna(emp.get('term_date')):
            term_date = pd.to_datetime(emp['term_date']).date()
            if term_date < first_day_of_month:
                continue  # Skip - terminated before this month
            # Cap at last day of month
            term_date = min(term_date, last_day_of_month)
        else:
            term_date = last_day_of_month

        # Skip if employee is not yet active within the effective date range
        # (e.g., hired Feb 25 but today is Feb 3 — not active yet)
        if hire_date > term_date:
            continue

        # Get data from metrics
        actuals = metrics['actuals'].get(month_key, {}).get(emp_id_str, {
            'hours': 0, 'billable_hours': 0, 'revenue': 0, 'worked_days': 0
        })
        projected = metrics['projected'].get(month_key, {}).get(emp_id_str, {
            'hours': 0, 'revenue': 0, 'worked_days': 0
        })
        possible = metrics['possible'].get(month_key, {}).get(emp_id_str, {
            'hours': 0, 'revenue': 0, 'worked_days': 0
        })

        # Adjust possible hours based on hire/term dates
        possible_hours = possible['hours']
        possible_worked_days = possible['worked_days']

        actual_working_days_in_month = _get_working_days_in_range(
            hire_date, term_date, months_df, selected_year, selected_month
        )

        if actual_working_days_in_month != possible_worked_days and possible_worked_days > 0:
            daily_rate = possible_hours / possible_worked_days
            adjusted_possible_hours = daily_rate * actual_working_days_in_month
        else:
            adjusted_possible_hours = possible_hours

        # Calculate utilization metrics
        actual_hours = actuals['hours']
        actual_billable_hours = actuals['billable_hours']
        projected_hours = projected['hours']
        actual_worked_days = actuals['worked_days']

        # For the current (incomplete) month, augment actual billable hours with
        # projected missing hours based on allocation data (gold standard formula).
        projected_missing_hours = 0.0
        effective_billable_hours = actual_billable_hours

        if include_projected and is_current_month and projected_hours > 0:
            month_info = months_df[
                (months_df['year'] == selected_year) &
                (months_df['month'] == selected_month)
            ]
            if not month_info.empty:
                total_working_days = int(month_info['working_days'].iloc[0])
                month_holidays = int(month_info['holidays'].iloc[0]) if pd.notna(month_info['holidays'].iloc[0]) else 0
                available_working_days = max(total_working_days - month_holidays, 1)

                # Find per-employee last billable timesheet entry
                last_entry_str = last_entry_dates.get(emp['id'])
                if last_entry_str:
                    last_entry = pd.to_datetime(last_entry_str).date()
                else:
                    last_entry = first_day_of_month - timedelta(days=1)

                # Count missing working days from (last_entry+1) to end of month
                missing_start = last_entry + timedelta(days=1)
                if missing_start <= last_day_of_month:
                    missing_working_days = _count_working_days(missing_start, last_day_of_month)
                else:
                    missing_working_days = 0

                if missing_working_days > 0 and available_working_days > 0:
                    projected_missing_hours = projected_hours * (missing_working_days / available_working_days)
                    effective_billable_hours = actual_billable_hours + projected_missing_hours
        elif not include_projected or not is_current_month:
            # Past months or toggle OFF: effective = actual
            effective_billable_hours = actual_billable_hours

        # Get PTO hours for this employee
        pto_hours = pto_by_employee.get(emp['id'], 0)

        # Get Holiday hours for this employee
        holiday_hours = holiday_by_employee.get(emp['id'], 0)

        # Calculate available hours (exclude PTO only; holidays already subtracted in _build_possible_data)
        available_hours = max(adjusted_possible_hours - pto_hours, 0)

        # Calculate other non-billable hours (excluding PTO; all FRINGE entries excluded from actuals)
        total_nonbillable_hours = actual_hours - actual_billable_hours
        other_nonbillable_hours = max(total_nonbillable_hours - pto_hours, 0)

        # Calculate utilization using effective billable hours (actual + projected missing)
        utilization_pct = (effective_billable_hours / available_hours * 100) if available_hours > 0 else 0
        variance = actual_hours - projected_hours

        # Calculate YTD metrics
        ytd_possible_hours = 0
        ytd_actual_billable_hours = 0
        ytd_pto_hours = 0
        ytd_holiday_hours = 0

        for month_num in range(1, selected_month + 1):
            ytd_month_date = datetime(selected_year, month_num, 1)
            ytd_month_key = ytd_month_date.strftime('%B %Y')

            ytd_possible_emp = ytd_metrics['possible'].get(ytd_month_key, {}).get(emp_id_str, {})
            ytd_possible_hours_raw = ytd_possible_emp.get('hours', 0)
            ytd_possible_worked_days = ytd_possible_emp.get('worked_days', 0)

            if ytd_possible_hours_raw > 0 and ytd_possible_worked_days > 0:
                ytd_actual_working_days = _get_working_days_in_range(
                    hire_date, term_date, months_df, selected_year, month_num
                )
                if ytd_actual_working_days != ytd_possible_worked_days:
                    daily_rate = ytd_possible_hours_raw / ytd_possible_worked_days
                    ytd_adjusted_possible_hours = daily_rate * ytd_actual_working_days
                else:
                    ytd_adjusted_possible_hours = ytd_possible_hours_raw
            else:
                ytd_adjusted_possible_hours = ytd_possible_hours_raw

            ytd_possible_hours += ytd_adjusted_possible_hours

            ytd_actuals_emp = ytd_metrics['actuals'].get(ytd_month_key, {}).get(emp_id_str, {})
            if month_num == selected_month and is_current_month and include_projected:
                ytd_actual_billable_hours += effective_billable_hours
            else:
                ytd_actual_billable_hours += ytd_actuals_emp.get('billable_hours', 0)

            # Calculate PTO and Holiday hours for this month from YTD time entries
            if not ytd_time_entries_df.empty:
                # Filter for this specific month
                ytd_month_last_day = calendar.monthrange(selected_year, month_num)[1]
                month_start_str = f"{selected_year}-{month_num:02d}-01"
                month_end_str = f"{selected_year}-{month_num:02d}-{ytd_month_last_day}"

                month_entries = ytd_time_entries_df[
                    (ytd_time_entries_df['date'] >= month_start_str) &
                    (ytd_time_entries_df['date'] <= month_end_str) &
                    (ytd_time_entries_df['employee_id'] == emp['id'])
                ]

                if not month_entries.empty:
                    # PTO hours for this month
                    month_pto = month_entries[month_entries['project_id'] == 'FRINGE.PTO']['hours'].sum()
                    ytd_pto_hours += month_pto

                    # Holiday hours for this month
                    month_holiday = month_entries[month_entries['project_id'] == 'FRINGE.HOL']['hours'].sum()
                    ytd_holiday_hours += month_holiday

        # Calculate YTD available hours (exclude PTO only; holidays already subtracted in _build_possible_data)
        ytd_available_hours = max(ytd_possible_hours - ytd_pto_hours, 0)

        # Calculate YTD utilization percentage using available hours
        ytd_utilization_pct = (ytd_actual_billable_hours / ytd_available_hours * 100) if ytd_available_hours > 0 else 0

        # Determine status (round to match displayed value)
        utilization_pct_r = round(utilization_pct)
        if utilization_pct_r >= 111:
            status = "🟣 Over"
            status_num = 5
        elif utilization_pct_r >= 97:
            status = "🟢 Good"
            status_num = 4
        elif utilization_pct_r >= 80:
            status = "🟡 Fair"
            status_num = 3
        elif utilization_pct_r >= 51:
            status = "🟠 Low"
            status_num = 2
        else:
            status = "🔴 Under"
            status_num = 1

        util_data.append({
            'employee_id': emp['id'],
            'name': emp['name'],
            'role': emp['role'],
            'pay_type': emp.get('pay_type', 'Hourly'),
            'possible_hours': adjusted_possible_hours,
            'projected_hours': projected_hours,
            'actual_hours': actual_hours,
            'actual_billable_hours': actual_billable_hours,
            'pto_hours': pto_hours,
            'holiday_hours': holiday_hours,
            'other_nonbillable_hours': other_nonbillable_hours,
            'projected_missing_hours': projected_missing_hours,
            'effective_billable_hours': effective_billable_hours,
            'utilization_pct': utilization_pct,
            'variance': variance,
            'status': status,
            'ytd_possible_hours': ytd_possible_hours,
            'ytd_actual_billable_hours': ytd_actual_billable_hours,
            'ytd_pto_hours': ytd_pto_hours,
            'ytd_holiday_hours': ytd_holiday_hours,
            'ytd_utilization_pct': ytd_utilization_pct,
            'status_num': status_num,
            'worked_days': actual_worked_days
        })

    util_df = pd.DataFrame(util_data)
    return util_df, month_key, time_entries_df


def _calculate_period_utilization_data(db, processor, start_date, end_date,
                                        employees_df=None, employee_id=None,
                                        include_projected=True):
    """Calculate utilization data aggregated across a date range.

    For single-month ranges, delegates to _calculate_monthly_utilization_data().
    For multi-month ranges, calls per-month and aggregates (sums hours, recalculates percentages).

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        employees_df: Optional pre-loaded employees DataFrame
        employee_id: Optional single employee ID to filter to
        include_projected: Whether to include projected remaining hours for current month

    Returns:
        tuple: (util_df, period_label, time_entries_df)
            - util_df: DataFrame with columns matching _calculate_monthly_utilization_data output
            - period_label: Human-readable label like "February 2026" or "January 2026 - March 2026"
            - time_entries_df: Combined time entries for the period
    """
    month_keys = _get_months_in_range(start_date, end_date)

    if not month_keys:
        return pd.DataFrame(), "", pd.DataFrame()

    # Build a mapping from month name to month number
    month_name_to_num = {name: num for num, name in enumerate(calendar.month_name) if num}

    def _parse_month_key(key):
        """Parse 'January 2026' into (year, month_num)."""
        parts = key.split()
        return int(parts[1]), month_name_to_num[parts[0]]

    # --- Single month: delegate directly ---
    if len(month_keys) == 1:
        year_num, month_num = _parse_month_key(month_keys[0])
        util_df, month_key, time_entries_df = _calculate_monthly_utilization_data(
            db, processor, year_num, month_num,
            employees_df=employees_df, employee_id=employee_id,
            include_projected=include_projected
        )
        return util_df, month_key, time_entries_df

    # --- Multi-month: aggregate across months ---
    all_util_dfs = []
    all_time_entries = []

    for mk in month_keys:
        year_num, month_num = _parse_month_key(mk)
        util_df, _, te_df = _calculate_monthly_utilization_data(
            db, processor, year_num, month_num,
            employees_df=employees_df, employee_id=employee_id,
            include_projected=include_projected
        )
        if not util_df.empty:
            all_util_dfs.append(util_df)
        if te_df is not None and not te_df.empty:
            all_time_entries.append(te_df)

    # Handle case where all months returned empty data
    if not all_util_dfs:
        combined_te = pd.concat(all_time_entries, ignore_index=True) if all_time_entries else pd.DataFrame()
        period_label = f"{month_keys[0]} \u2013 {month_keys[-1]}"
        return pd.DataFrame(), period_label, combined_te

    combined = pd.concat(all_util_dfs, ignore_index=True)

    # Define aggregation rules
    sum_cols = [
        'possible_hours', 'projected_hours', 'actual_hours',
        'actual_billable_hours', 'pto_hours', 'holiday_hours',
        'other_nonbillable_hours', 'projected_missing_hours',
        'effective_billable_hours', 'worked_days',
    ]
    last_cols = [
        'ytd_possible_hours', 'ytd_actual_billable_hours',
        'ytd_pto_hours', 'ytd_holiday_hours',
        'role', 'pay_type',
    ]

    agg_dict = {}
    for col in sum_cols:
        if col in combined.columns:
            agg_dict[col] = 'sum'
    for col in last_cols:
        if col in combined.columns:
            agg_dict[col] = 'last'

    agg_df = combined.groupby(['employee_id', 'name'], as_index=False).agg(agg_dict)

    # Recalculate derived fields using available hours (excluding PTO only; holidays already subtracted)
    agg_df['available_hours'] = (
        agg_df['possible_hours'] - agg_df['pto_hours']
    ).clip(lower=0)

    agg_df['utilization_pct'] = (
        agg_df['effective_billable_hours'] / agg_df['available_hours'] * 100
    ).fillna(0)
    agg_df['utilization_pct'] = agg_df['utilization_pct'].where(
        agg_df['available_hours'] > 0, 0
    )

    agg_df['ytd_available_hours'] = (
        agg_df['ytd_possible_hours'] - agg_df['ytd_pto_hours']
    ).clip(lower=0)
    agg_df['ytd_utilization_pct'] = (
        agg_df['ytd_actual_billable_hours'] / agg_df['ytd_available_hours'] * 100
    ).fillna(0)
    agg_df['ytd_utilization_pct'] = agg_df['ytd_utilization_pct'].where(
        agg_df['ytd_available_hours'] > 0, 0
    )

    agg_df['variance'] = agg_df['actual_hours'] - agg_df['projected_hours']

    # Assign status based on utilization_pct (round to match displayed value)
    _pct_r = agg_df['utilization_pct'].round(0)
    conditions = [
        _pct_r >= 111,
        _pct_r >= 97,
        _pct_r >= 80,
        _pct_r >= 51,
    ]
    status_choices = ["\U0001f7e3 Over", "\U0001f7e2 Good", "\U0001f7e1 Fair", "\U0001f7e0 Low"]
    status_num_choices = [5, 4, 3, 2]

    agg_df['status'] = np.select(conditions, status_choices, default="\U0001f534 Under")
    agg_df['status_num'] = np.select(conditions, status_num_choices, default=1)

    # Drop the temporary available_hours column
    agg_df = agg_df.drop(columns=['available_hours'], errors='ignore')

    # Build period label
    period_label = f"{month_keys[0]} \u2013 {month_keys[-1]}"

    # Combine all time entries
    combined_te = pd.concat(all_time_entries, ignore_index=True) if all_time_entries else pd.DataFrame()

    return agg_df, period_label, combined_te


def render_combined_utilization_view(db, processor, employee_id=None, widget_prefix="main"):
    """Single unified utilization view combining summary, detail, and timeline.

    Combines the three subtabs (Utilization Summary, Monthly Detail, Utilization
    Timeline) into one scrollable view with a shared utilization-band filter.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        employee_id: Optional employee ID to filter to single employee
        widget_prefix: Prefix for widget keys to avoid collisions between pages
    """
    st.markdown("#### Employee Utilization Analysis")

    # Initialize grid selection version
    grid_version_key = f"{widget_prefix}_util_grid_version"
    if grid_version_key not in st.session_state:
        st.session_state[grid_version_key] = 0

    # --- Shared Filters ---
    current_year = datetime.now().year
    year_options = list(range(current_year - 2, current_year + 2))

    if employee_id is not None:
        # Single employee: no band filter
        col1, col2, col_sub, col_fy = st.columns([1, 1.5, 1, 1])
    else:
        col1, col2, col_sub, col_fy, col3 = st.columns([1, 1.5, 1, 1, 2])

    with col1:
        selected_year = st.selectbox(
            "Year",
            options=year_options,
            index=year_options.index(current_year),
            key=f"{widget_prefix}_cutil_year"
        )

    with col2:
        time_frame = st.selectbox(
            "Time Frame",
            ["Monthly", "Quarterly", "QTD", "YTD"],
            key=f"{widget_prefix}_cutil_timeframe"
        )

    selected_month = None
    selected_quarter = None
    fy_type = None

    with col_sub:
        if time_frame == "Monthly":
            month_names = list(calendar.month_name)[1:]  # January through December
            default_month_idx = datetime.now().month - 1 if selected_year == current_year else 0
            selected_month = st.selectbox("Month", month_names, index=default_month_idx,
                key=f"{widget_prefix}_cutil_month")
        elif time_frame == "Quarterly":
            quarters = ["Q1", "Q2", "Q3", "Q4"]
            default_quarter_idx = (datetime.now().month - 1) // 3 if selected_year == current_year else 0
            selected_quarter = st.selectbox("Quarter", quarters, index=default_quarter_idx,
                key=f"{widget_prefix}_cutil_quarter")

    with col_fy:
        if time_frame in ("Quarterly", "QTD", "YTD"):
            fy_type = st.radio("FY Type", ["Company", "Gov"], horizontal=True,
                key=f"{widget_prefix}_cutil_fytype")

    # Build effective_time_frame string for _get_period_date_range()
    if time_frame == "Monthly":
        effective_time_frame = selected_month  # e.g., "February"
    elif time_frame == "Quarterly":
        effective_time_frame = f"{selected_quarter} ({fy_type})"  # e.g., "Q2 (Company)"
    elif time_frame == "QTD":
        effective_time_frame = f"QTD ({fy_type})"  # e.g., "QTD (Gov)"
    elif time_frame == "YTD":
        effective_time_frame = f"YTD ({fy_type})"  # e.g., "YTD (Company)"

    if employee_id is not None:
        # Include all bands so employee always passes filtering
        band_filter = ["< 50%", "50\u201380%", "80\u2013100%", "> 100%"]
    else:
        with col3:
            band_filter = st.multiselect(
                "Utilization Band",
                options=["< 50%", "50\u201380%", "80\u2013100%", "> 100%"],
                default=["< 50%", "50\u201380%", "80\u2013100%", "> 100%"],
                key=f"{widget_prefix}_cutil_band"
            )

    # Toggle for including projected hours in current month utilization
    include_projected = st.checkbox(
        "Include projected hours for current month",
        value=True,
        help="When enabled, missing billable hours are projected using allocation FTE data from the employee's last timesheet entry through end of month.",
        key=f"{widget_prefix}_include_projected"
    )

    # Helper function for band filtering
    def matches_band(pct, bands):
        if not bands:
            return False
        if "< 50%" in bands and pct < 50:
            return True
        if "50\u201380%" in bands and 50 <= pct < 80:
            return True
        if "80\u2013100%" in bands and 80 <= pct <= 100:
            return True
        if "> 100%" in bands and pct > 100:
            return True
        return False

    # Get date range
    start_date, end_date = _get_period_date_range(effective_time_frame, selected_year)
    months_in_range = _get_months_in_range(start_date, end_date)

    # Show resolved date range for current selection
    _start_dt = pd.to_datetime(start_date)
    _end_dt = pd.to_datetime(end_date)
    st.caption(f"Period: {_start_dt.strftime('%b %d, %Y')} - {_end_dt.strftime('%b %d, %Y')}")

    # Get last updated date from time_entries
    last_entry = db.conn.execute("SELECT MAX(date) FROM time_entries").fetchone()
    if last_entry and last_entry[0]:
        st.caption(f"Data last updated: {last_entry[0]}")

    with st.expander("Time Frame Definitions"):
        st.markdown("""| Time Frame | Definition |
|---|---|
| **Monthly** | Any individual calendar month for the selected year |
| **Quarterly** | Calendar or Gov FY quarter (select Q1-Q4 and Company/Gov) |
| **QTD** | Current quarter start -> today (select Company or Gov FY) |
| **YTD** | Year start -> today (Company: Jan 1, Gov: Oct 1 prior year) |

**Gov FY convention:** FY2026 = Oct 1, 2025 -> Sep 30, 2026""")

    try:
        with st.spinner("Loading utilization data..."):
            metrics = processor.get_performance_metrics(
                start_date=start_date,
                end_date=end_date
            )

        billable_df = _get_billable_employees(db, start_date, end_date)

        if employee_id is not None:
            billable_df = billable_df[billable_df['id'] == employee_id]
            if billable_df.empty:
                st.error(f"Employee {employee_id} not found or is not billable")
                return

        if billable_df.empty:
            st.info("No billable employees found for the selected period.")
            return

        # ==============================
        # Compute period utilization data (needed by summary cards, band filter, and detail)
        # This uses PTO/holiday-adjusted utilization calculations.
        # ==============================
        util_df, detail_period_label, time_entries_df = _calculate_period_utilization_data(
            db, processor, start_date, end_date,
            employee_id=employee_id,
            include_projected=include_projected
        )

        # ==============================
        # Build employee_utilizations from util_df (PTO/holiday-adjusted)
        # (used by summary cards and band filter)
        # ==============================
        employee_utilizations = []
        if not util_df.empty:
            for _, row in util_df.iterrows():
                employee_utilizations.append({
                    'id': row['employee_id'],
                    'name': row['name'],
                    'utilization_pct': row['utilization_pct'],
                    'billable_hours': row['actual_billable_hours'],
                    'possible_hours': row['possible_hours'],
                })

        # Apply band filter to get filtered employee IDs (round to match displayed value)
        filtered_employee_ids = set()
        for eu in employee_utilizations:
            if matches_band(round(eu['utilization_pct']), band_filter):
                filtered_employee_ids.add(eu['id'])

        if not filtered_employee_ids:
            st.warning("No employees match the selected utilization bands.")
            return

        # Apply band filter - keep only employees in filtered_employee_ids
        if not util_df.empty:
            util_df = util_df[util_df['employee_id'].isin(filtered_employee_ids)]

        # ==============================
        # SECTION 1: Utilization Summary Cards
        # ==============================
        st.markdown("---")

        st.markdown(f"### Utilization Summary - {effective_time_frame} ({detail_period_label})")

        # Filter employee_utilizations by band
        filtered_utilizations = [eu for eu in employee_utilizations if eu['id'] in filtered_employee_ids]

        if employee_id is not None:
            # --- Single Employee: status indicator + metrics ---
            emp_util = employee_utilizations[0]
            pct = emp_util['utilization_pct']

            # Determine status category
            if pct >= 111:
                status_icon, status_label, bg_color, border_color = '\U0001f7e3', '111%+', '#fce4ec', '#e91e63'
            elif pct >= 97:
                status_icon, status_label, bg_color, border_color = '\U0001f7e2', '97-110%', '#e8f5e9', '#28a745'
            elif pct >= 80:
                status_icon, status_label, bg_color, border_color = '\U0001f7e1', '80-96%', '#fff8e1', '#ffc107'
            elif pct >= 51:
                status_icon, status_label, bg_color, border_color = '\U0001f7e0', '51-79%', '#fff3e0', '#fd7e14'
            else:
                status_icon, status_label, bg_color, border_color = '\U0001f534', '≤50%', '#ffebee', '#dc3545'

            # Get detailed data from util_df (single row)
            if not util_df.empty:
                row = util_df.iloc[0]
                status_cols = st.columns([1.2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
                with status_cols[0]:
                    st.markdown(f"""<div style="background:{bg_color}; border-left:4px solid {border_color};
                        padding:0.5rem 1rem; border-radius:0.3rem; text-align:center;">
                        <small style="color:#666;">Billable Utilization %</small><br>
                        <strong>{status_icon} {status_label}</strong><br>
                        <span style="font-size:1.5rem; font-weight:bold;">{pct:.1f}%</span>
                    </div>""", unsafe_allow_html=True)
                with status_cols[1]:
                    st.metric("Possible Billable Hrs", f"{row['possible_hours']:,.1f}")
                with status_cols[2]:
                    st.metric("Actual Hrs", f"{row['actual_hours']:,.1f}")
                with status_cols[3]:
                    st.metric("Actual Billable Hrs", f"{row['actual_billable_hours']:,.1f}")
                with status_cols[4]:
                    st.metric("Projected Missing Hrs", f"{row['projected_missing_hours']:,.1f}")
                with status_cols[5]:
                    st.metric("Effective Billable Hrs", f"{row['effective_billable_hours']:,.1f}")
                with status_cols[6]:
                    st.metric("PTO Hrs", f"{row['pto_hours']:,.1f}")
                with status_cols[7]:
                    st.metric("Holiday Hrs", f"{row['holiday_hours']:,.1f}")
                with status_cols[8]:
                    st.metric("Other Non-bill", f"{row['other_nonbillable_hours']:,.1f}")
                with status_cols[9]:
                    st.metric("YTD Possible Billable Hrs", f"{row['ytd_possible_hours']:,.1f}")
                with status_cols[10]:
                    st.metric("YTD Actual Billable Hrs", f"{row['ytd_actual_billable_hours']:,.1f}")
                with status_cols[11]:
                    st.metric("YTD Billable Utilization %", f"{row['ytd_utilization_pct']:.1f}%")
            else:
                st.info("No utilization data available for this employee in the selected period.")
        else:
            # --- All Employees: 5 category cards ---
            categories = [
                {
                    'label': '111%+',
                    'icon': '\U0001f7e3',
                    'bg_color': '#fce4ec',
                    'border_color': '#e91e63',
                    'filter': lambda pct: pct >= 111,
                },
                {
                    'label': '97% - 110%',
                    'icon': '\U0001f7e2',
                    'bg_color': '#e8f5e9',
                    'border_color': '#28a745',
                    'filter': lambda pct: 97 <= pct < 111,
                },
                {
                    'label': '80% - 96%',
                    'icon': '\U0001f7e1',
                    'bg_color': '#fff8e1',
                    'border_color': '#ffc107',
                    'filter': lambda pct: 80 <= pct < 97,
                },
                {
                    'label': '51% - 79%',
                    'icon': '\U0001f7e0',
                    'bg_color': '#fff3e0',
                    'border_color': '#fd7e14',
                    'filter': lambda pct: 51 <= pct < 80,
                },
                {
                    'label': '≤ 50%',
                    'icon': '\U0001f534',
                    'bg_color': '#ffebee',
                    'border_color': '#dc3545',
                    'filter': lambda pct: pct < 51,
                },
            ]

            cols = st.columns(5)
            for idx, cat in enumerate(categories):
                matching = [e for e in filtered_utilizations if cat['filter'](round(e['utilization_pct']))]
                count = len(matching)

                if matching:
                    names_lines = [
                        f"{html.escape(e['name'])} ({e['utilization_pct']:.0f}%)"
                        for e in sorted(matching, key=lambda x: x['utilization_pct'], reverse=True)
                    ]
                    names_html = "<br>".join(names_lines)
                else:
                    names_html = "<em>None</em>"

                with cols[idx]:
                    st.markdown(f'''
<div style="background-color: {cat['bg_color']}; padding: 15px; border-radius: 10px; border-left: 5px solid {cat['border_color']}; margin-bottom: 10px;">
    <div style="display: flex; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 24px; margin-right: 8px;">{cat['icon']}</span>
        <span style="font-size: 18px; font-weight: bold;">{cat['label']}</span>
    </div>
    <div style="font-size: 28px; font-weight: bold; margin-bottom: 5px;">{count} Employees</div>
    <div style="font-size: 13px; color: #555;">{names_html}</div>
</div>
''', unsafe_allow_html=True)

            # Combined summary metrics
            if not util_df.empty:
                summary_cols = st.columns(9)
                with summary_cols[0]:
                    st.metric("Employees", len(util_df))
                with summary_cols[1]:
                    st.metric("Total Possible Hrs", f"{util_df['possible_hours'].sum():,.0f}")
                with summary_cols[2]:
                    st.metric("Total Actual Hrs", f"{util_df['actual_hours'].sum():,.0f}")
                with summary_cols[3]:
                    st.metric("Total Billable Hrs", f"{util_df['actual_billable_hours'].sum():,.0f}")
                with summary_cols[4]:
                    st.metric("Total Projected Missing Hrs", f"{util_df['projected_missing_hours'].sum():,.0f}")
                with summary_cols[5]:
                    st.metric("Total Effective Billable Hrs", f"{util_df['effective_billable_hours'].sum():,.0f}")
                with summary_cols[6]:
                    st.metric("Total PTO Hrs", f"{util_df['pto_hours'].sum():,.0f}")
                with summary_cols[7]:
                    st.metric("Total Holiday Hrs", f"{util_df['holiday_hours'].sum():,.0f}")
                with summary_cols[8]:
                    avg_util = util_df['utilization_pct'].mean()
                    st.metric("Avg Utilization", f"{avg_util:.1f}%")
                st.markdown("---")

        # ==============================
        # SECTION 2: Utilization Detail / Project Breakdown
        # ==============================
        if util_df.empty:
            st.info("No billable employees found matching the selected filters for this month.")
        else:
            # Helper function to get project breakdown for an employee
            def get_employee_project_breakdown(emp_id, te_df):
                """Generate project-level breakdown for a specific employee."""
                emp_entries = te_df[te_df['employee_id'] == emp_id]

                if emp_entries.empty:
                    return pd.DataFrame(columns=[
                        'Project Code', 'Project', 'Billable Hrs',
                        'Non-billable Hrs', 'Total Hrs', '% of Total'
                    ])

                breakdown = emp_entries.groupby(
                    ['project_id', 'project_name', 'billable']
                )['hours'].sum().reset_index()

                breakdown_pivot = breakdown.pivot(
                    index=['project_id', 'project_name'],
                    columns='billable',
                    values='hours'
                ).reset_index()
                breakdown_pivot.columns.name = None

                column_map = {'project_id': 'Project Code', 'project_name': 'Project'}
                if 0 in breakdown_pivot.columns:
                    column_map[0] = 'Non-billable Hrs'
                if 1 in breakdown_pivot.columns:
                    column_map[1] = 'Billable Hrs'

                breakdown_pivot = breakdown_pivot.rename(columns=column_map)

                if 'Billable Hrs' not in breakdown_pivot.columns:
                    breakdown_pivot['Billable Hrs'] = 0
                if 'Non-billable Hrs' not in breakdown_pivot.columns:
                    breakdown_pivot['Non-billable Hrs'] = 0

                breakdown_pivot['Total Hrs'] = (
                    breakdown_pivot['Billable Hrs'] + breakdown_pivot['Non-billable Hrs']
                )
                total_hours = breakdown_pivot['Total Hrs'].sum()
                breakdown_pivot['% of Total'] = (
                    breakdown_pivot['Total Hrs'] / total_hours * 100
                ).round(1)

                breakdown_pivot = breakdown_pivot.sort_values('Total Hrs', ascending=False)
                return breakdown_pivot

            if employee_id is not None:
                # --- Single Employee: Logic popover + divider ---
                with st.popover("Logic for Utilization Calculations"):
                    st.markdown("""For each employee in the utilization table:

  | Column                           | Source                                                  | Calculation                                                                          |
  |----------------------------------|---------------------------------------------------------|--------------------------------------------------------------------------------------|
  | Employee                         | employees_df['name']                                    | Direct from employees table                                                          |
  | Possible Billable Hrs            | metrics['possible'][month_key][emp_id]['hours']         | From employees table: (working_days - holidays) x (target_allocation - overhead_allocation) x 8 |
  | Actual Hrs                       | metrics['actuals'][month_key][emp_id]['hours']          | From time_entries table: sum of ALL hours logged (billable + non-billable)           |
  | Actual Billable Hrs              | metrics['actuals'][month_key][emp_id]['billable_hours'] | From time_entries table: sum of hours where billable=1                               |
  | Projected Missing Hrs            | Calculated (current month only)                         | projected_hours x (missing_working_days / available_working_days), where missing_working_days = weekdays from employee's last timesheet entry to end of month |
  | Effective Billable Hrs           | Calculated                                              | actual_billable_hours + projected_missing_hours                                      |
  | PTO Hrs                          | time_entries_df where project_id='FRINGE.PTO'           | Sum of hours from time_entries for PTO project                                       |
  | Holiday Hrs                      | time_entries_df where project_id='FRINGE.HOL'           | Sum of hours from time_entries for Holiday project (for reference; not in denominator)|
  | Other Non-billable Hrs           | Calculated                                              | (actual_hours - actual_billable_hours) - pto_hours                                   |
  | Billable Utilization %           | Calculated                                              | (effective_billable_hours / (possible_hours - pto_hours)) x 100                      |
  | Status                           | Calculated                                              | Based on Billable Utilization %: >=111% Over, 97-110% Good, 80-96% Fair, 51-79% Low, <=50% Under |
  | YTD Possible Billable Hrs        | ytd_metrics['possible']                                 | Sum of possible hours from Jan 1 to end of selected month                            |
  | YTD Actual Billable Hrs          | ytd_metrics['actuals']                                  | Sum of actual billable hours from Jan 1 to end of selected month                     |
  | YTD Billable Utilization %       | Calculated                                              | (ytd_actual_billable_hours / (ytd_possible_hours - ytd_pto_hours)) x 100             |

**Notes:**
- Possible hours use (working_days - holidays) from the months table as the authoritative holiday source.
- For the current month, missing billable hours are projected using allocation FTE data from the employee's last timesheet entry through end of month.
- Effective Billable Hrs = Actual Billable + Projected Missing.
- Use the "Include projected hours" toggle to switch between projected and actual-only views.
- Possible hours are adjusted for employees hired or terminated mid-month (employment proration).
- Billable Utilization % uses available hours (possible - PTO) as the denominator.
- YTD columns show cumulative data from January 1st through the end of the selected month.
""")

            else:
                # --- All Employees: existing AgGrid table, dialog, CSV ---
                def clear_combined_grid_selection():
                    """Callback to clear grid selection when dialog is dismissed."""
                    st.session_state[grid_version_key] = st.session_state.get(grid_version_key, 0) + 1

                @st.dialog("Employee Timesheet & Utilization Detail", width="large", on_dismiss=clear_combined_grid_selection)
                def show_combined_project_breakdown(emp_id, emp_name, mk, te_df):
                    """Display utilization calculation breakdown and timesheet entries for a selected employee."""
                    st.markdown(f"### {emp_name}")
                    st.caption(f"{mk}")

                    # ---- Section A: Billable Utilization Calculation Breakdown ----
                    st.markdown("#### Billable Utilization Calculation")

                    # Look up employee row from util_df (closure)
                    emp_util_rows = util_df[util_df['employee_id'] == emp_id]
                    if emp_util_rows.empty:
                        st.warning(f"No utilization data found for {emp_name} in this period.")
                    else:
                        emp_row = emp_util_rows.iloc[0]

                        # Fetch employee record for target_allocation, overhead_allocation, hire_date, term_date
                        all_employees = db.get_employees()
                        emp_record = all_employees[all_employees['id'] == emp_id]

                        if not emp_record.empty:
                            emp_rec = emp_record.iloc[0]
                            target_alloc = float(emp_rec.get('target_allocation', 0) or 0)
                            overhead_alloc = float(emp_rec.get('overhead_allocation', 0) or 0)
                            fte_pct = target_alloc - overhead_alloc

                            hire_date_val = emp_rec.get('hire_date')
                            term_date_val = emp_rec.get('term_date')
                        else:
                            fte_pct = 1.0
                            hire_date_val = None
                            term_date_val = None

                        # Get months data for working days and holidays
                        months_df = db.get_months()
                        months_in_period = _get_months_in_range(start_date, end_date)

                        # Build month_name_to_num mapping
                        month_name_to_num = {name: num for num, name in enumerate(calendar.month_name) if num}

                        workdays_total = 0
                        holidays_total = 0
                        for mk_period in months_in_period:
                            parts = mk_period.split()
                            m_year = int(parts[1])
                            m_num = month_name_to_num[parts[0]]
                            month_info = months_df[
                                (months_df['year'] == m_year) &
                                (months_df['month'] == m_num)
                            ]
                            if not month_info.empty:
                                workdays_total += int(month_info['working_days'].iloc[0])
                                hol = month_info['holidays'].iloc[0]
                                holidays_total += int(hol) if pd.notna(hol) else 0

                        daily_scheduled_hours = 8.0

                        # Calculate employment proration
                        period_start_dt = pd.to_datetime(start_date).date()
                        period_end_dt = pd.to_datetime(end_date).date()
                        total_days_in_period = (period_end_dt - period_start_dt).days + 1

                        emp_start = period_start_dt
                        emp_end = period_end_dt

                        if hire_date_val and pd.notna(hire_date_val):
                            hd = pd.to_datetime(hire_date_val).date()
                            if hd > period_start_dt:
                                emp_start = hd

                        if term_date_val and pd.notna(term_date_val):
                            td = pd.to_datetime(term_date_val).date()
                            if td < period_end_dt:
                                emp_end = td

                        if emp_start == period_start_dt and emp_end == period_end_dt:
                            employment_proration = 1.0
                        elif emp_end < emp_start:
                            employment_proration = 0.0
                        else:
                            days_worked = (emp_end - emp_start).days + 1
                            employment_proration = days_worked / total_days_in_period

                        # Values from util_df row
                        possible_hours = float(emp_row['possible_hours'])
                        pto_hours = float(emp_row['pto_hours'])
                        available_hours = max(possible_hours - pto_hours, 0)
                        actual_billable_hours = float(emp_row['actual_billable_hours'])
                        projected_missing_hours = float(emp_row['projected_missing_hours'])
                        effective_billable_hours = float(emp_row['effective_billable_hours'])
                        utilization_pct_val = float(emp_row['utilization_pct'])

                        # Color map for variable badges and table rows
                        var_colors = {
                            'workdays': '#dbeafe',
                            'holidays': '#dbeafe',
                            'daily_hrs': '#dbeafe',
                            'fte': '#dbeafe',
                            'proration': '#dbeafe',
                            'possible': '#e0e7ff',
                            'pto': '#fef3c7',
                            'available': '#d1fae5',
                            'actual_billable': '#ede9fe',
                            'projected': '#fce7f3',
                            'effective': '#bae6fd',
                            'utilization': '#fef9c3',
                        }

                        badge = (
                            'display:inline-block;padding:2px 8px;border-radius:4px;'
                            'margin:0 2px;font-size:14px;'
                        )

                        def _badge(color_key, label, bold=False):
                            """Return an HTML span badge with the given color and label."""
                            weight = 'font-weight:600;' if bold else ''
                            return (
                                f'<span style="{badge}background:{var_colors[color_key]};{weight}">'
                                f'{label}</span>'
                            )

                        def _result_badge(color_key, label, larger=False):
                            """Return a result badge (font-weight 700)."""
                            size = 'font-size:16px;' if larger else ''
                            return (
                                f'<span style="{badge}background:{var_colors[color_key]};'
                                f'font-weight:700;{size}">{label}</span>'
                            )

                        def _step_card(accent_color, step_label, formula_html):
                            """Return a styled step card div."""
                            return (
                                f'<div style="margin-bottom:10px;padding:10px 14px;background:#f8fafc;'
                                f'border-radius:8px;border-left:3px solid {accent_color};">'
                                f'<div style="font-size:12px;color:#64748b;margin-bottom:4px;">{step_label}</div>'
                                f'<div style="line-height:1.8;">{formula_html}</div>'
                                f'</div>'
                            )

                        # Step 1: Possible Billable Hours
                        step1_formula = (
                            f'({_badge("workdays", "Workdays")} {_badge("workdays", f"{workdays_total}", bold=True)}'
                            f' &minus; '
                            f'{_badge("holidays", "Holidays")} {_badge("holidays", f"{holidays_total}", bold=True)})'
                            f' &times; '
                            f'{_badge("daily_hrs", "Daily Hrs")} {_badge("daily_hrs", "8.0", bold=True)}'
                            f' &times; '
                            f'{_badge("fte", "FTE%")} {_badge("fte", f"{fte_pct:.2f}", bold=True)}'
                            f' &times; '
                            f'{_badge("proration", "Proration")} {_badge("proration", f"{employment_proration:.2f}", bold=True)}'
                            f' = '
                            f'{_result_badge("possible", f"{possible_hours:.1f}")}'
                        )
                        step1 = _step_card(var_colors['possible'], 'Step 1: Possible Billable Hours', step1_formula)

                        # Step 2: Available Work Hours
                        step2_formula = (
                            f'{_badge("possible", "Possible Billable Hrs")} {_badge("possible", f"{possible_hours:.1f}", bold=True)}'
                            f' &minus; '
                            f'{_badge("pto", "PTO Hours")} {_badge("pto", f"{pto_hours:.1f}", bold=True)}'
                            f' = '
                            f'{_result_badge("available", f"{available_hours:.1f}")}'
                        )
                        step2 = _step_card(var_colors['available'], 'Step 2: Available Work Hours', step2_formula)

                        # Step 3: Effective Billable Hours
                        step3_formula = (
                            f'{_badge("actual_billable", "Actual Billable Hrs")} {_badge("actual_billable", f"{actual_billable_hours:.1f}", bold=True)}'
                            f' + '
                            f'{_badge("projected", "Projected Missing Hrs")} {_badge("projected", f"{projected_missing_hours:.1f}", bold=True)}'
                            f' = '
                            f'{_result_badge("effective", f"{effective_billable_hours:.1f}")}'
                        )
                        step3 = _step_card(var_colors['effective'], 'Step 3: Effective Billable Hours', step3_formula)

                        # Step 4: Billable Utilization
                        if available_hours > 0:
                            step4_formula = (
                                f'{_badge("effective", "Effective Billable Hrs")} {_badge("effective", f"{effective_billable_hours:.1f}", bold=True)}'
                                f' &divide; '
                                f'{_badge("available", "Available Work Hrs")} {_badge("available", f"{available_hours:.1f}", bold=True)}'
                                f' &times; 100'
                                f' = '
                                f'{_result_badge("utilization", f"{utilization_pct_val:.1f}%", larger=True)}'
                            )
                        else:
                            step4_formula = (
                                f'{_badge("effective", "Effective Billable Hrs")} {_badge("effective", f"{effective_billable_hours:.1f}", bold=True)}'
                                f' &divide; '
                                f'{_badge("available", "Available Work Hrs")} {_badge("available", f"{available_hours:.1f}", bold=True)}'
                                f' &times; 100'
                                f' = '
                                f'{_result_badge("utilization", "N/A")}'
                            )
                        step4 = _step_card(var_colors['utilization'], 'Step 4: Billable Utilization', step4_formula)

                        st.markdown(step1 + step2 + step3 + step4, unsafe_allow_html=True)

                        # Note about per-month calculation for multi-month periods
                        if len(_get_months_in_range(start_date, end_date)) > 1:
                            st.caption("Note: For multi-month periods, possible hours are calculated per-month with per-month proration, then summed. The single proration factor shown above is an approximate overall value.")

                        # Variable reference table (styled HTML)
                        ref_rows = [
                            ('Workdays in Period', str(workdays_total), 'Total scheduled working days', 'months table', 'workdays'),
                            ('Holiday Days', str(holidays_total), 'Company holidays in period', 'months table', 'holidays'),
                            ('Daily Scheduled Hours', f'{daily_scheduled_hours:.1f}', 'Standard hours per day', 'Constant', 'daily_hrs'),
                            ('FTE %', f'{fte_pct:.2f}', 'target_allocation - overhead_allocation', 'employees table', 'fte'),
                            ('Employment Proration', f'{employment_proration:.2f}', 'Proportion of period employed', 'Calculated from hire/term dates', 'proration'),
                            ('Possible Billable Hrs', f'{possible_hours:.1f}', '(Workdays-Holidays) x 8 x FTE% x Proration', 'Calculated', 'possible'),
                            ('PTO Hours', f'{pto_hours:.1f}', 'Approved PTO time', 'time_entries (FRINGE.PTO)', 'pto'),
                            ('Available Work Hours', f'{available_hours:.1f}', 'Possible Billable Hrs - PTO Hours', 'Calculated', 'available'),
                            ('Actual Billable Hours', f'{actual_billable_hours:.1f}', 'Billable hours logged', 'time_entries (billable=1)', 'actual_billable'),
                            ('Projected Missing Hrs', f'{projected_missing_hours:.1f}', 'Projected hours for missing days from last timesheet entry to end of month', 'projected_hours x (missing_days / available_days)', 'projected'),
                            ('Effective Billable Hrs', f'{effective_billable_hours:.1f}', 'Actual Billable + Projected Missing', 'Calculated', 'effective'),
                            ('Billable Utilization %', f'{utilization_pct_val:.1f}%', 'Effective Billable / Available x 100', 'Final Result', 'utilization'),
                        ]

                        th_style = 'background:#f1f5f9;padding:8px 12px;text-align:left;border-bottom:2px solid #e2e8f0;font-weight:600;'
                        table_html = (
                            '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
                            f'<tr><th style="{th_style}">Variable</th>'
                            f'<th style="{th_style}">Value</th>'
                            f'<th style="{th_style}">Definition</th>'
                            f'<th style="{th_style}">Source</th></tr>'
                        )

                        for var_name, var_val, var_def, var_src, color_key in ref_rows:
                            bg = var_colors[color_key]
                            is_final = color_key == 'utilization'
                            if is_final:
                                row_style = f'background:{bg};font-weight:700;'
                                table_html += (
                                    f'<tr>'
                                    f'<td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;{row_style}">{var_name}</td>'
                                    f'<td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;{row_style}">{var_val}</td>'
                                    f'<td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;{row_style}">{var_def}</td>'
                                    f'<td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;{row_style}">{var_src}</td>'
                                    f'</tr>'
                                )
                            else:
                                td_base = 'padding:6px 12px;border-bottom:1px solid #e2e8f0;'
                                table_html += (
                                    f'<tr>'
                                    f'<td style="{td_base}background:{bg};">{var_name}</td>'
                                    f'<td style="{td_base}background:{bg};font-weight:600;">{var_val}</td>'
                                    f'<td style="{td_base}">{var_def}</td>'
                                    f'<td style="{td_base}">{var_src}</td>'
                                    f'</tr>'
                                )

                        table_html += '</table>'
                        st.markdown(table_html, unsafe_allow_html=True)

                    # ---- Section B: Hours by Project & Timesheet Entries ----
                    st.markdown("---")

                    emp_te = te_df[te_df['employee_id'] == emp_id].copy() if not te_df.empty else pd.DataFrame()

                    if emp_te.empty:
                        st.info(f"No time entries found for {emp_name} in {mk}")
                    else:
                        # Compute rate column for reuse
                        emp_te['_rate'] = emp_te['hourly_rate'].fillna(0) if 'hourly_rate' in emp_te.columns else 0.0
                        emp_te['_amount'] = emp_te['hours'] * emp_te['_rate']

                        # ---- Hours by Project summary ----
                        st.markdown("#### Hours by Project")

                        # Group by project
                        billable_hrs = emp_te[emp_te['billable'].fillna(0) == 1].groupby(['project_id', 'project_name'])['hours'].sum()
                        nonbillable_hrs = emp_te[emp_te['billable'].fillna(0) != 1].groupby(['project_id', 'project_name'])['hours'].sum()
                        total_hrs = emp_te.groupby(['project_id', 'project_name'])['hours'].sum()
                        total_amount = emp_te.groupby(['project_id', 'project_name'])['_amount'].sum()

                        proj_summary = pd.DataFrame({
                            'Billable Hrs': billable_hrs,
                            'Non-billable Hrs': nonbillable_hrs,
                            'Total Hrs': total_hrs,
                            'Amount': total_amount,
                        }).fillna(0).reset_index()

                        proj_summary = proj_summary.rename(columns={
                            'project_id': 'Project Code',
                            'project_name': 'Project',
                        })

                        grand_total = proj_summary['Total Hrs'].sum()
                        proj_summary['% of Total'] = (
                            (proj_summary['Total Hrs'] / grand_total * 100).round(1) if grand_total > 0 else 0.0
                        )

                        proj_summary['Billable Hrs'] = proj_summary['Billable Hrs'].round(1)
                        proj_summary['Non-billable Hrs'] = proj_summary['Non-billable Hrs'].round(1)
                        proj_summary['Total Hrs'] = proj_summary['Total Hrs'].round(1)
                        proj_summary['Amount'] = proj_summary['Amount'].round(2)

                        proj_summary = proj_summary.sort_values('Total Hrs', ascending=False)

                        st.dataframe(
                            proj_summary[['Project Code', 'Project', 'Billable Hrs', 'Non-billable Hrs', 'Total Hrs', 'Amount', '% of Total']],
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                'Amount': st.column_config.NumberColumn(format='$%.2f'),
                                '% of Total': st.column_config.NumberColumn(format='%.1f%%'),
                            }
                        )

                        # ---- Timesheet Entries (raw) ----
                        st.markdown("#### Timesheet Entries")

                        # Sort by date ascending
                        emp_te = emp_te.sort_values('date', ascending=True)

                        # Build display columns
                        ts_display = pd.DataFrame()
                        ts_display['Date'] = emp_te['date'].values
                        ts_display['Project Code'] = emp_te['project_id'].values
                        ts_display['Project'] = emp_te['project_name'].values if 'project_name' in emp_te.columns else emp_te['project_id'].values
                        ts_display['Hours'] = emp_te['hours'].round(2).values
                        ts_display['Billable'] = emp_te['billable'].map({1: 'Yes', 0: 'No'}).values
                        ts_display['Bill Rate'] = emp_te['_rate'].values
                        ts_display['Amount'] = emp_te['_amount'].round(2).values
                        ts_display['Description'] = emp_te['description'].values if 'description' in emp_te.columns else ''

                        st.dataframe(ts_display, hide_index=True, use_container_width=True)

                st.markdown(f"### Utilization Report - {effective_time_frame} ({detail_period_label})")

                # Prepare display DataFrame
                display_df = util_df[[
                    'employee_id', 'name', 'possible_hours',
                    'actual_hours', 'actual_billable_hours',
                    'projected_missing_hours', 'effective_billable_hours',
                    'pto_hours', 'holiday_hours',
                    'other_nonbillable_hours', 'utilization_pct', 'status',
                    'ytd_possible_hours', 'ytd_actual_billable_hours', 'ytd_utilization_pct'
                ]].copy()

                display_df = display_df.rename(columns={
                    'name': 'Employee',
                    'possible_hours': 'Possible Billable Hrs',
                    'actual_hours': 'Actual Hrs',
                    'actual_billable_hours': 'Actual Billable Hrs',
                    'projected_missing_hours': 'Projected Missing Hrs',
                    'effective_billable_hours': 'Effective Billable Hrs',
                    'pto_hours': 'PTO Hrs',
                    'holiday_hours': 'Holiday Hrs',
                    'other_nonbillable_hours': 'Other Non-billable Hrs',
                    'utilization_pct': 'Billable Utilization %',
                    'status': 'Status',
                    'ytd_possible_hours': 'YTD Possible Billable Hrs',
                    'ytd_actual_billable_hours': 'YTD Actual Billable Hrs',
                    'ytd_utilization_pct': 'YTD Billable Utilization %'
                })

                # JsCode for conditional cell styling on Billable Utilization % column
                utilization_cell_style = JsCode("""
                function(params) {
                    if (params.value >= 111) {
                        return {'backgroundColor': '#f8bbd0'};
                    } else if (params.value >= 97) {
                        return {'backgroundColor': '#ccffcc'};
                    } else if (params.value >= 80) {
                        return {'backgroundColor': '#fff9cc'};
                    } else if (params.value >= 51) {
                        return {'backgroundColor': '#ffe0b2'};
                    } else {
                        return {'backgroundColor': '#ffcccc'};
                    }
                }
                """)

                # JsCode for YTD columns - light gray background
                ytd_cell_style = JsCode("""
                function(params) {
                    return {'backgroundColor': '#f0f0f0'};
                }
                """)

                # Value formatter for numeric columns (2 decimal places)
                numeric_formatter = JsCode("""
                function(params) {
                    if (params.value === null || params.value === undefined) {
                        return '';
                    }
                    return params.value.toFixed(2);
                }
                """)

                st.markdown("#### Utilization Report")

                col1, col2 = st.columns([1, 3])

                with col1:
                    with st.popover("Logic for Utilization Table"):
                        st.markdown("""For each employee in the utilization table:

  | Column                           | Source                                                  | Calculation                                                                          |
  |----------------------------------|---------------------------------------------------------|--------------------------------------------------------------------------------------|
  | Employee                         | employees_df['name']                                    | Direct from employees table                                                          |
  | Possible Billable Hrs            | metrics['possible'][month_key][emp_id]['hours']         | From employees table: (working_days - holidays) x (target_allocation - overhead_allocation) x 8 |
  | Actual Hrs                       | metrics['actuals'][month_key][emp_id]['hours']          | From time_entries table: sum of ALL hours logged (billable + non-billable)           |
  | Actual Billable Hrs              | metrics['actuals'][month_key][emp_id]['billable_hours'] | From time_entries table: sum of hours where billable=1                               |
  | Projected Missing Hrs            | Calculated (current month only)                         | projected_hours x (missing_working_days / available_working_days), where missing_working_days = weekdays from employee's last timesheet entry to end of month |
  | Effective Billable Hrs           | Calculated                                              | actual_billable_hours + projected_missing_hours                                      |
  | PTO Hrs                          | time_entries_df where project_id='FRINGE.PTO'           | Sum of hours from time_entries for PTO project                                       |
  | Holiday Hrs                      | time_entries_df where project_id='FRINGE.HOL'           | Sum of hours from time_entries for Holiday project (for reference; not in denominator)|
  | Other Non-billable Hrs           | Calculated                                              | (actual_hours - actual_billable_hours) - pto_hours                                   |
  | Billable Utilization %           | Calculated                                              | (effective_billable_hours / (possible_hours - pto_hours)) x 100                      |
  | Status                           | Calculated                                              | Based on Billable Utilization %: >=111% Over, 97-110% Good, 80-96% Fair, 51-79% Low, <=50% Under |
  | YTD Possible Billable Hrs        | ytd_metrics['possible']                                 | Sum of possible hours from Jan 1 to end of selected month                            |
  | YTD Actual Billable Hrs          | ytd_metrics['actuals']                                  | Sum of actual billable hours from Jan 1 to end of selected month                     |
  | YTD Billable Utilization %       | Calculated                                              | (ytd_actual_billable_hours / (ytd_possible_hours - ytd_pto_hours)) x 100             |

**Notes:**
- Possible hours use (working_days - holidays) from the months table as the authoritative holiday source.
- For the current month, missing billable hours are projected using allocation FTE data from the employee's last timesheet entry through end of month.
- Effective Billable Hrs = Actual Billable + Projected Missing.
- Use the "Include projected hours" toggle to switch between projected and actual-only views.
- Possible hours are adjusted for employees hired or terminated mid-month (employment proration).
- Billable Utilization % uses available hours (possible - PTO) as the denominator.
- Click on any row to view project-level breakdown.
- YTD columns show cumulative data from January 1st through the end of the selected month.
""")

                with col2:
                    st.info("Click on any row to view detailed project breakdown for that employee")

                # Build AgGrid options
                gb = GridOptionsBuilder.from_dataframe(display_df)

                # Configure single-row selection without checkbox
                gb.configure_selection(selection_mode='single', use_checkbox=False)

                # Hide the employee_id column
                gb.configure_column("employee_id", hide=True)

                # Make columns sortable but not filterable
                gb.configure_default_column(sortable=True, filterable=False)

                # Configure numeric columns with formatter
                numeric_columns = [
                    'Possible Billable Hrs',
                    'Actual Hrs',
                    'Actual Billable Hrs',
                    'Projected Missing Hrs',
                    'Effective Billable Hrs',
                    'PTO Hrs',
                    'Holiday Hrs',
                    'Other Non-billable Hrs'
                ]
                for col_name in numeric_columns:
                    gb.configure_column(col_name, valueFormatter=numeric_formatter)

                # Configure Billable Utilization % column with conditional styling and formatter
                gb.configure_column(
                    'Billable Utilization %',
                    cellStyle=utilization_cell_style,
                    valueFormatter=numeric_formatter
                )

                # Configure YTD columns with gray background and formatter
                ytd_columns = [
                    'YTD Possible Billable Hrs',
                    'YTD Actual Billable Hrs',
                    'YTD Billable Utilization %'
                ]
                for col_name in ytd_columns:
                    gb.configure_column(
                        col_name,
                        cellStyle=ytd_cell_style,
                        valueFormatter=numeric_formatter
                    )

                grid_options = gb.build()

                # Display AgGrid
                grid_response = AgGrid(
                    display_df,
                    gridOptions=grid_options,
                    columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW,
                    height=500,
                    update_mode=GridUpdateMode.SELECTION_CHANGED,
                    allow_unsafe_jscode=True,
                    theme='streamlit',
                    key=f"{widget_prefix}_cutil_aggrid_v{st.session_state[grid_version_key]}"
                )

                # Handle row selection - open dialog to show project breakdown
                selected_rows = grid_response['selected_rows']
                if selected_rows is not None and len(selected_rows) > 0:
                    selected_row = selected_rows.iloc[0] if hasattr(selected_rows, 'iloc') else selected_rows[0]
                    emp_id = selected_row['employee_id']
                    emp_name = selected_row['Employee']

                    show_combined_project_breakdown(emp_id, emp_name, detail_period_label, time_entries_df)

                # CSV Export (without employee_id column)
                csv_df = display_df.drop(columns=['employee_id'])
                csv = csv_df.to_csv(index=False)
                st.download_button(
                    label="Download Utilization Report",
                    data=csv,
                    file_name=f"utilization_{selected_year}_{effective_time_frame.replace(' ', '_').lower()}.csv",
                    mime="text/csv",
                    key=f"{widget_prefix}_cutil_csv_download"
                )

        # ==============================
        # SECTION 3: Utilization Timeline
        # ==============================
        st.markdown("---")
        st.markdown(f"### Utilization Timeline - {effective_time_frame} ({detail_period_label})")

        # Filter billable_df to only employees matching band filter
        filtered_billable_df = billable_df[billable_df['id'].isin(filtered_employee_ids)]

        if employee_id is not None:
            emp_name = filtered_billable_df['name'].iloc[0]
        else:
            st.markdown("#### Utilization Timeline: All")

        # Aggregate planned and actual hours per month across filtered employees
        planned_hours_list = []
        actual_hours_list = []

        for mk in months_in_range:
            month_planned = 0
            month_actual = 0

            projected_month = metrics['projected'].get(mk, {})
            actuals_month = metrics['actuals'].get(mk, {})

            for _, emp in filtered_billable_df.iterrows():
                emp_id_str = str(emp['id'])
                proj_emp = projected_month.get(emp_id_str, {})
                month_planned += proj_emp.get('hours', 0)

                act_emp = actuals_month.get(emp_id_str, {})
                month_actual += act_emp.get('billable_hours', 0)

            planned_hours_list.append(month_planned)
            actual_hours_list.append(month_actual)

        if any(h > 0 for h in planned_hours_list) or any(h > 0 for h in actual_hours_list):
            chart_title = "Planned vs Actual Billable Hours"
            if employee_id is None:
                chart_title += " - All Employees"

            fig_all = go.Figure()
            fig_all.add_trace(go.Bar(
                name='Planned Hours',
                x=months_in_range,
                y=planned_hours_list,
                marker_color='#28a745'
            ))
            fig_all.add_trace(go.Bar(
                name='Actual Billable Hours',
                x=months_in_range,
                y=actual_hours_list,
                marker_color='#ffc107'
            ))
            fig_all.update_layout(
                barmode='group',
                title=chart_title,
                xaxis_title="Month",
                yaxis_title="Hours",
                height=400
            )
            st.plotly_chart(fig_all, use_container_width=True)
        else:
            st.info("No planned or actual hours data available for the selected period.")

        # Individual employee timeline (only when not filtered to single employee)
        if employee_id is None and not filtered_billable_df.empty:
            st.markdown("#### Utilization Timeline: Individual Employee")

            sorted_filtered_df = filtered_billable_df.sort_values('name')

            selected_emp_id = st.selectbox(
                "Select Employee",
                options=sorted_filtered_df['id'].tolist(),
                format_func=lambda eid: filtered_billable_df[
                    filtered_billable_df['id'] == eid
                ]['name'].iloc[0],
                key=f"{widget_prefix}_cutil_timeline_employee"
            )

            selected_emp_name = filtered_billable_df[
                filtered_billable_df['id'] == selected_emp_id
            ]['name'].iloc[0]

            # Get individual employee metrics using constraint
            with st.spinner(f"Loading timeline for {selected_emp_name}..."):
                emp_metrics = processor.get_performance_metrics(
                    start_date=start_date,
                    end_date=end_date,
                    constraint={'employee_id': selected_emp_id}
                )

            # When using employee constraint, data is keyed by project_id.
            # Sum across all projects for each month.
            emp_planned_list = []
            emp_actual_list = []

            for mk in months_in_range:
                projected_month = emp_metrics['projected'].get(mk, {})
                month_planned = sum(
                    proj_data.get('hours', 0)
                    for proj_data in projected_month.values()
                )
                emp_planned_list.append(month_planned)

                actuals_month = emp_metrics['actuals'].get(mk, {})
                month_actual = sum(
                    act_data.get('billable_hours', 0)
                    for act_data in actuals_month.values()
                )
                emp_actual_list.append(month_actual)

            if any(h > 0 for h in emp_planned_list) or any(h > 0 for h in emp_actual_list):
                fig_emp = go.Figure()
                fig_emp.add_trace(go.Bar(
                    name='Planned Hours',
                    x=months_in_range,
                    y=emp_planned_list,
                    marker_color='#28a745'
                ))
                fig_emp.add_trace(go.Bar(
                    name='Actual Billable Hours',
                    x=months_in_range,
                    y=emp_actual_list,
                    marker_color='#ffc107'
                ))
                fig_emp.update_layout(
                    barmode='group',
                    title=f"Planned vs Actual Billable Hours - {selected_emp_name}",
                    xaxis_title="Month",
                    yaxis_title="Hours",
                    height=400
                )
                st.plotly_chart(fig_emp, use_container_width=True)
            else:
                st.info(f"No planned or actual hours data available for {selected_emp_name} in the selected period.")

        # ==============================
        # SECTION 4: Project Breakdown (Single Employee only)
        # ==============================
        if employee_id is not None and not util_df.empty:
            st.markdown("---")
            st.markdown(f"### Project Breakdown - {effective_time_frame} ({detail_period_label})")

            breakdown_df = get_employee_project_breakdown(employee_id, time_entries_df)

            if breakdown_df.empty:
                st.info("No time entries found for this employee in the selected period.")
            else:
                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    st.markdown("**Hours by Project**")
                    st.dataframe(breakdown_df.round(1), use_container_width=True, height=400, hide_index=True)
                with bcol2:
                    st.markdown("**Distribution**")
                    # Build pie chart data
                    chart_data = []
                    colors = []
                    for _, brow in breakdown_df.iterrows():
                        proj_name = brow.get('Project', brow.get('project_name', 'Unknown'))
                        billable_hrs = brow.get('Billable Hrs', 0)
                        nonbillable_hrs = brow.get('Non-billable Hrs', 0)
                        if billable_hrs > 0:
                            chart_data.append({'label': f"{proj_name} (Billable)", 'hours': billable_hrs})
                            colors.append('#2E7D32')
                        if nonbillable_hrs > 0:
                            chart_data.append({'label': f"{proj_name} (Non-billable)", 'hours': nonbillable_hrs})
                            colors.append('#FFA726')

                    if chart_data:
                        fig = go.Figure(data=[go.Pie(
                            labels=[d['label'] for d in chart_data],
                            values=[d['hours'] for d in chart_data],
                            marker_colors=colors,
                            hole=0.3
                        )])
                        fig.update_layout(
                            height=400,
                            showlegend=True,
                            margin=dict(t=20, b=20, l=20, r=20)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No chart data available.")

    except Exception as e:
        st.error(f"Error loading utilization data: {str(e)}")
        logger.error(f"Error in combined utilization view: {str(e)}", exc_info=True)
