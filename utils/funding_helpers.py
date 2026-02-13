"""
Funding helper functions for project review and financial analysis.

Provides reusable calculations for average monthly invoicing, funding runway,
funding health status, and current month potential revenue. These functions
support the Project Review Meeting page and related financial views.
"""
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils.logger import get_logger

logger = get_logger(__name__)


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
            constraint={'project_id': str(project_id)}
        )
    except Exception as e:
        logger.error(f"Failed to get performance metrics for project {project_id}: {e}")
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
        tuple: (label: str, color: str, icon: str) suitable for display in
               Streamlit UI elements.
    """
    if funding_pct >= 50:
        return ("Good", "#28a745", "\U0001f7e2")
    elif funding_pct >= 30:
        return ("Minor Risk", "#ffc107", "\U0001f7e1")
    elif funding_pct >= 10:
        return ("Medium", "#fd7e14", "\U0001f7e0")
    else:
        return ("Risk", "#dc3545", "\U0001f534")


def calculate_current_month_potential(project_id, db):
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

    Returns:
        float: Total potential invoice amount for the current month across
               all allocated team members, or 0.0 if no allocations exist.
    """
    now = datetime.now()
    current_year = now.year
    current_month = now.month

    # First day of the current month in YYYY-MM-DD format (matches allocation_date storage)
    current_month_start = datetime(current_year, current_month, 1).strftime('%Y-%m-%d')

    # Retrieve all allocations for this project
    try:
        allocations_df = db.get_allocations(project_id=str(project_id))
    except Exception as e:
        logger.error(f"Failed to get allocations for project {project_id}: {e}")
        return 0.0

    if allocations_df.empty:
        return 0.0

    # Filter to current month allocations
    # allocation_date is stored as TEXT in YYYY-MM-DD format (first of month)
    allocations_df['allocation_date_parsed'] = pd.to_datetime(
        allocations_df['allocation_date'], errors='coerce'
    )
    current_month_allocs = allocations_df[
        (allocations_df['allocation_date_parsed'].dt.year == current_year) &
        (allocations_df['allocation_date_parsed'].dt.month == current_month)
    ]

    if current_month_allocs.empty:
        return 0.0

    # Determine working days for the current month from the months table
    working_days = 21  # default fallback
    try:
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
    except Exception as e:
        logger.warning(
            f"Could not retrieve working days for {current_year}-{current_month:02d}, "
            f"using default of 21: {e}"
        )

    hours_per_day = 8
    total_potential = 0.0

    for _, alloc in current_month_allocs.iterrows():
        fte = alloc.get('allocated_fte', 0) or 0
        bill_rate = alloc.get('bill_rate', 0) or 0

        potential = fte * working_days * hours_per_day * bill_rate
        total_potential += potential

    return total_potential
