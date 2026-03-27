"""
Funding helper functions for project review and financial analysis.

Provides reusable calculations for average monthly invoicing, funding runway,
funding health status, and current month potential revenue. These functions
support the Project Review Meeting page and related financial views.
"""
import calendar

import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

logger = logging.getLogger(__name__)


def calculate_avg_monthly_invoices_batch(db, lookback_months=12):
    """Calculate avg monthly invoice for all projects in a single DB query.

    Instead of calling get_performance_metrics per project (N+1 pattern),
    this queries time_entries directly and groups by project_id and month.

    Revenue logic matches _build_actuals_data in data_processor.py:
        1) Use amount if non-null and non-zero
        2) Otherwise use hours * bill_rate from the time_entries row

    Args:
        db: DatabaseManager instance.
        lookback_months: Number of months to look back from today (default 12).

    Returns:
        dict: Mapping of project_id -> avg_monthly_invoice (float).
              Only projects with positive revenue in at least one month are included.
    """
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - relativedelta(months=lookback_months)).strftime('%Y-%m-%d')

    query = """
        SELECT t.project_id,
               strftime('%Y-%m', t.date) AS month,
               SUM(CASE
                   WHEN t.amount IS NOT NULL AND t.amount != 0 THEN t.amount
                   WHEN t.bill_rate IS NOT NULL THEN t.hours * t.bill_rate
                   ELSE 0.0
               END) AS revenue
        FROM time_entries t
        WHERE t.date >= ? AND t.date <= ?
            AND t.project_id NOT LIKE 'FRINGE.%'
        GROUP BY t.project_id, strftime('%Y-%m', t.date)
    """

    try:
        df = pd.read_sql_query(query, db.conn, params=[start_date, end_date])
    except Exception:
        logger.exception("Failed to query batch monthly invoices")
        return {}

    if df.empty:
        return {}

    # For each project, average over months that had positive revenue
    result = {}
    for project_id, group in df.groupby('project_id'):
        positive_months = group[group['revenue'] > 0]
        if not positive_months.empty:
            result[project_id] = positive_months['revenue'].sum() / len(positive_months)

    return result


def calculate_avg_monthly_invoice(project_id, db, processor, lookback_months=12):
    """
    Calculate the average monthly invoice for a project over the last N months.

    Uses actual revenue data from time entries (via get_performance_metrics)
    to compute the mean monthly invoice. Only months with positive revenue
    are included in the denominator, so months with zero activity do not
    dilute the average.

    Args:
        project_id: The project identifier (TEXT, e.g. "202800.Y2.000.00").
        db: DatabaseManager instance (unused directly but required by processor context).
        processor: DataProcessor class reference with get_performance_metrics static method.
        lookback_months: Number of months to look back from today (default 12).

    Returns:
        float: Average monthly revenue across months that had activity, or 0.0
               if no revenue data exists in the lookback window.
    """
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - relativedelta(months=lookback_months)).strftime('%Y-%m-%d')

    try:
        metrics = processor.get_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            constraint={'project_id': str(project_id)},
            db=db
        )
    except Exception as e:
        logger.exception("Failed to get performance metrics for project %s", project_id)
        return 0.0

    actuals = metrics.get('actuals', {})
    if not actuals:
        return 0.0

    monthly_revenues = []
    for month_name, employees in actuals.items():
        month_revenue = sum(
            emp_data.get('revenue', 0)
            for emp_data in employees.values()
        )
        if month_revenue > 0:
            monthly_revenues.append(month_revenue)

    if not monthly_revenues:
        return 0.0

    return sum(monthly_revenues) / len(monthly_revenues)


def calculate_funding_runway(remaining_funding, avg_monthly_invoice):
    """
    Calculate the number of months of funding remaining.

    Args:
        remaining_funding: Dollar amount of funding not yet consumed.
        avg_monthly_invoice: Average monthly spend/invoice amount.

    Returns:
        float: Estimated months of runway. Returns float('inf') if
               avg_monthly_invoice is zero or negative (i.e. no spend).
    """
    if avg_monthly_invoice <= 0:
        return float('inf')

    return remaining_funding / avg_monthly_invoice


def get_funding_health_status(funding_pct):
    """
    Determine funding health status based on the percentage of funding remaining.

    Thresholds:
        >= 50%  : Good (green)
        30%-50% : Minor Risk (yellow)
        10%-30% : Medium (orange)
        < 10%   : Risk (red)

    Args:
        funding_pct: Percentage of total funding remaining (0-100 scale).

    Returns:
        str: Health label classification (e.g. "Good", "Minor Risk", "Medium", "Risk").
    """
    if funding_pct >= 50:
        return "Good"
    elif funding_pct >= 30:
        return "Minor Risk"
    elif funding_pct >= 10:
        return "Medium"
    else:
        return "Risk"


def calculate_current_month_potential(project_id, db, allocations_df=None, months_df=None):
    """
    Calculate the potential invoice for the current month based on allocations.

    Looks up allocations for the given project in the current calendar month,
    then computes potential revenue as:
        allocated_fte * working_days * 8 hours/day * bill_rate

    Working days are sourced from the months table via db.get_months(). If no
    entry exists for the current month, a default of 21 working days is used.

    Args:
        project_id: The project identifier (TEXT).
        db: DatabaseManager instance with get_allocations() and get_months() methods.
        allocations_df: Optional pre-fetched allocations DataFrame. If provided,
            will be filtered to the given project_id in-memory instead of
            calling db.get_allocations(). Useful to avoid N+1 queries.
        months_df: Optional pre-fetched months DataFrame. If provided, used
            instead of calling db.get_months(). Useful to avoid N+1 queries.

    Returns:
        float: Total potential invoice amount for the current month across
               all allocated team members, or 0.0 if no allocations exist.
    """
    now = datetime.now()
    current_year = now.year
    current_month = now.month

    # First day of the current month in YYYY-MM-DD format (matches allocation_date storage)
    current_month_start = datetime(current_year, current_month, 1).strftime('%Y-%m-%d')

    # Retrieve allocations: use pre-fetched data if available, otherwise query
    if allocations_df is not None:
        # Filter pre-fetched allocations to this project in-memory
        project_allocations_df = allocations_df[
            allocations_df['project_id'].astype(str) == str(project_id)
        ].copy()
    else:
        try:
            project_allocations_df = db.get_allocations(project_id=str(project_id))
        except Exception as e:
            logger.exception("Failed to get allocations for project %s", project_id)
            return 0.0

    if project_allocations_df.empty:
        return 0.0

    # Filter to current month allocations
    # allocation_date is stored as TEXT in YYYY-MM-DD format (first of month)
    project_allocations_df['allocation_date_parsed'] = pd.to_datetime(
        project_allocations_df['allocation_date'], errors='coerce'
    )
    current_month_allocs = project_allocations_df[
        (project_allocations_df['allocation_date_parsed'].dt.year == current_year) &
        (project_allocations_df['allocation_date_parsed'].dt.month == current_month)
    ]

    if current_month_allocs.empty:
        return 0.0

    # Determine working days for the current month from the months table
    working_days = 21  # default fallback
    try:
        if months_df is None:
            months_df = db.get_months()
        if not months_df.empty:
            current_month_row = months_df[
                (months_df['year'] == current_year) &
                (months_df['month'] == current_month)
            ]
            if not current_month_row.empty:
                working_days = int(current_month_row['working_days'].iloc[0])
                holidays = current_month_row['holidays'].iloc[0] if 'holidays' in current_month_row.columns else 0
                holidays = holidays if pd.notna(holidays) else 0
                working_days = max(working_days - holidays, 0)
    except Exception:
        logger.exception(
            "Could not retrieve working days for %s-%02d, using default of 21",
            current_year, current_month,
        )

    hours_per_day = 8
    total_potential = 0.0

    for _, alloc in current_month_allocs.iterrows():
        fte = alloc.get('allocated_fte', 0) or 0
        bill_rate = alloc.get('bill_rate', 0) or 0

        potential = fte * working_days * hours_per_day * bill_rate
        total_potential += potential

    return total_potential


def calculate_project_utilization(project_id, db, processor, start_date, end_date):
    """
    Calculate project-level utilization by comparing allocated hours to actual billable hours.

    Uses get_performance_metrics to retrieve both projected (allocation-based) and
    actual (time-entry-based) data, then computes utilization as the ratio of
    actual billable hours to allocated hours. Also calculates the revenue gap
    representing lost revenue from underutilization.

    If end_date falls before the last day of its month (partial month), the
    allocated hours and projected revenue for that month are prorated by the
    ratio of elapsed weekdays to total weekdays in the month. This prevents
    misleadingly low utilization early in a month when actuals only cover
    days through end_date but allocations cover the full month.

    Args:
        project_id: The project identifier (TEXT, e.g. "220300.00.001.00").
        db: DatabaseManager instance (unused directly but required by processor context).
        processor: DataProcessor class reference with get_performance_metrics static method.
        start_date: Start date string 'YYYY-MM-DD'.
        end_date: End date string 'YYYY-MM-DD'.

    Returns:
        dict: {
            'allocated_hours': float,
            'actual_billable_hours': float,
            'utilization_pct': float or None,  # None if no allocations
            'revenue_gap': float,
            'weighted_avg_bill_rate': float,
        }
    """
    zero_result = {
        'allocated_hours': 0.0,
        'actual_billable_hours': 0.0,
        'utilization_pct': None,
        'revenue_gap': 0.0,
        'weighted_avg_bill_rate': 0.0,
    }

    try:
        metrics = processor.get_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            constraint={'project_id': str(project_id)},
            db=db
        )
    except Exception as e:
        logger.exception("Failed to get performance metrics for project %s", project_id)
        return zero_result

    # Prorate the end month's allocated hours if it is a partial month.
    # When end_date falls before the last day of its month (e.g., today is mid-month),
    # the projected allocation covers the full month but actuals only cover days up to
    # end_date. Without proration, utilization appears artificially low early in the month.
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    last_day_of_end_month = calendar.monthrange(end_dt.year, end_dt.month)[1]
    prorate_ratio = 1.0
    end_month_name = None

    if end_dt.day < last_day_of_end_month:
        # Count weekdays from day 1 through end_dt.day
        elapsed_weekdays = sum(
            1 for d in range(1, end_dt.day + 1)
            if calendar.weekday(end_dt.year, end_dt.month, d) < 5
        )
        # Count total weekdays in the full month
        full_month_weekdays = sum(
            1 for d in range(1, last_day_of_end_month + 1)
            if calendar.weekday(end_dt.year, end_dt.month, d) < 5
        )
        if full_month_weekdays > 0:
            prorate_ratio = elapsed_weekdays / full_month_weekdays
        # Build key matching the projected dict format, e.g. "February 2026"
        end_month_name = end_dt.strftime('%B %Y')

    # Sum allocated hours and projected revenue from the projected data,
    # applying prorate_ratio to the partial end month.
    projected = metrics.get('projected', {})
    allocated_hours = 0.0
    projected_revenue = 0.0
    for month_name, employees in projected.items():
        for emp_data in employees.values():
            hours = emp_data.get('hours', 0) or 0
            revenue = emp_data.get('revenue', 0) or 0
            if end_month_name and month_name == end_month_name:
                hours *= prorate_ratio
                revenue *= prorate_ratio
            allocated_hours += hours
            projected_revenue += revenue

    # Sum actual billable hours from the actuals data
    actuals = metrics.get('actuals', {})
    actual_billable_hours = 0.0
    for month_name, employees in actuals.items():
        for emp_data in employees.values():
            actual_billable_hours += emp_data.get('billable_hours', 0) or 0

    if allocated_hours > 0:
        utilization_pct = (actual_billable_hours / allocated_hours) * 100
        weighted_avg_bill_rate = projected_revenue / allocated_hours
        revenue_gap = (allocated_hours - actual_billable_hours) * weighted_avg_bill_rate
    else:
        utilization_pct = None
        revenue_gap = 0.0
        weighted_avg_bill_rate = 0.0

    return {
        'allocated_hours': allocated_hours,
        'actual_billable_hours': actual_billable_hours,
        'utilization_pct': utilization_pct,
        'revenue_gap': revenue_gap,
        'weighted_avg_bill_rate': weighted_avg_bill_rate,
    }


def get_utilization_health_status(utilization_pct):
    """
    Determine utilization health status based on percentage.

    Thresholds:
        >= 90%  : Good (green)
        70%-90% : Minor Risk (yellow)
        50%-70% : Medium (orange)
        < 50%   : Risk (red)

    Args:
        utilization_pct: Percentage of allocated hours actually used (0-100+ scale).
                         Can be None if no allocations exist.

    Returns:
        str: Health label classification (e.g. "Good", "Minor Risk", "Medium", "Risk",
             or "N/A" if utilization_pct is None).
    """
    if utilization_pct is None:
        return "N/A"
    # Round before comparing against thresholds so that the status matches
    # the displayed (rounded) value.  E.g. 89.5 rounds to 90 -> "Good".
    rounded = round(utilization_pct)
    if rounded >= 90:
        return "Good"
    elif rounded >= 70:
        return "Minor Risk"
    elif rounded >= 50:
        return "Medium"
    else:
        return "Risk"


def calculate_all_projects_utilization(db, processor, start_date, end_date):
    """
    Calculate utilization metrics for all billable projects.

    Iterates over all billable projects, computes per-project utilization via
    calculate_project_utilization, and assembles the results into a DataFrame
    with health status annotations.

    TODO: This function has an N+1 query pattern similar to the one fixed in
    get_funding_review(). Each call to calculate_project_utilization() invokes
    get_performance_metrics() per project. A batch approach querying all
    projects at once would be more efficient. The TTL cache on
    get_performance_metrics partially mitigates the cost for now.

    Args:
        db: DatabaseManager instance.
        processor: DataProcessor class reference.
        start_date: Start date string 'YYYY-MM-DD'.
        end_date: End date string 'YYYY-MM-DD'.

    Returns:
        pd.DataFrame with columns: project_id, project_name, allocated_hours,
        actual_billable_hours, utilization_pct, revenue_gap,
        health_label.
        Returns empty DataFrame with those columns if no billable projects.
    """
    columns = [
        'project_id', 'project_name', 'allocated_hours',
        'actual_billable_hours', 'utilization_pct', 'revenue_gap',
        'health_label',
    ]

    try:
        projects_df = db.get_projects()
    except Exception as e:
        logger.exception("Failed to get projects")
        return pd.DataFrame(columns=columns)

    if projects_df.empty:
        return pd.DataFrame(columns=columns)

    billable_projects = projects_df[projects_df['billable'] == 1]
    if billable_projects.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for _, project in billable_projects.iterrows():
        project_id = str(project['id'])
        project_name = project.get('name', project_id)

        util_data = calculate_project_utilization(
            project_id, db, processor, start_date, end_date
        )
        health_label = get_utilization_health_status(
            util_data['utilization_pct']
        )

        rows.append({
            'project_id': project_id,
            'project_name': project_name,
            'allocated_hours': util_data['allocated_hours'],
            'actual_billable_hours': util_data['actual_billable_hours'],
            'utilization_pct': util_data['utilization_pct'],
            'revenue_gap': util_data['revenue_gap'],
            'health_label': health_label,
        })

    return pd.DataFrame(rows, columns=columns)
