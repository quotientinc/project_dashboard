import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import calendar
from datetime import datetime, timedelta
from utils.logger import get_logger
from utils.funding_helpers import calculate_all_projects_utilization
from utils.project_helpers import safe_currency_display

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

def _count_working_days(start_date, end_date):
    """Count weekdays (Mon-Fri) between start_date and end_date inclusive."""
    import numpy as np
    if end_date < start_date:
        return 0
    count = np.busday_count(start_date, end_date)
    if end_date.weekday() < 5:
        count += 1
    return int(count)

# Helper function to calculate working days in a month range
def get_working_days_in_range(start_date, end_date, months_df, year, month):
    """Calculate working days between start and end date for a specific month.

    Working days are adjusted for holidays (subtracted from the months table count)
    to match the denominator used by _build_possible_data().
    """
    import calendar

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
    actual_start = max(start_date, month_start)
    actual_end = min(end_date, month_end)

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

# Date Range Filter
st.markdown("### 📊 Dashboard Overview")
col1, col2 = st.columns([4, 1])

with col1:
    st.write("")  # Spacer

with col2:
    date_range_option = st.selectbox(
        "Time Range",
        ["Last 30 Days", "Last Quarter", "YTD", "This Year", "All Time"],
        index=2,  # Default to "YTD"
        key="overview_date_range"
    )

# Calculate date range
current_date = datetime.now()
if date_range_option == "Last 30 Days":
    start_date = current_date - timedelta(days=30)
    end_date = current_date
elif date_range_option == "Last Quarter":
    start_date = current_date - timedelta(days=90)
    end_date = current_date
elif date_range_option == "YTD":
    start_date = datetime(current_date.year, 1, 1)
    end_date = current_date
elif date_range_option == "This Year":
    start_date = datetime(current_date.year, 1, 1)
    end_date = datetime(current_date.year, 12, 31)
else:  # All Time
    start_date = None
    end_date = None

# Load data
all_projects_df = db.get_projects()
employees_df = db.get_employees()
allocations_df = db.get_allocations()
months_df = db.get_months()

# Filter to only billable projects
if not all_projects_df.empty:
    projects_df = all_projects_df[all_projects_df['billable'] == 1].copy()
    billable_project_ids = projects_df['id'].tolist()
else:
    projects_df = all_projects_df
    billable_project_ids = []

# Apply date filtering to time entries and expenses
if start_date and end_date:
    time_entries_df = db.get_time_entries(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )
    # Filter expenses by date
    all_expenses_df = db.get_expenses()
    if not all_expenses_df.empty:
        all_expenses_df['date'] = pd.to_datetime(all_expenses_df['date'])
        expenses_df = all_expenses_df[
            (all_expenses_df['date'] >= start_date) &
            (all_expenses_df['date'] <= end_date)
        ]
    else:
        expenses_df = all_expenses_df
else:
    time_entries_df = db.get_time_entries()
    expenses_df = db.get_expenses()

# Filter time entries, expenses, and allocations to only billable projects
if billable_project_ids:
    if not time_entries_df.empty:
        time_entries_df = time_entries_df[time_entries_df['project_id'].isin(billable_project_ids)].copy()
    if not expenses_df.empty:
        expenses_df = expenses_df[expenses_df['project_id'].isin(billable_project_ids)].copy()
    if not allocations_df.empty:
        allocations_df = allocations_df[allocations_df['project_id'].isin(billable_project_ids)].copy()

# Calculate monthly utilization trend (for the current year)
# Filter to billable employees only (billable=1, active)
billable_employees_df = employees_df[
    (employees_df['billable'] == 1) &
    (
        (pd.isna(employees_df['term_date'])) |
        (pd.to_datetime(employees_df['term_date']) >= pd.Timestamp(current_date))
    )
].copy()

# Get performance metrics for full year (for trend chart with projections)
full_year_start = datetime(current_date.year, 1, 1).strftime('%Y-%m-%d')
full_year_end = datetime(current_date.year, 12, 31).strftime('%Y-%m-%d')

# Get performance metrics for YTD only (for KPI calculations)
ytd_start = datetime(current_date.year, 1, 1).strftime('%Y-%m-%d')
ytd_end = current_date.strftime('%Y-%m-%d')

# Get full year time entries for PTO/Holiday calculations (optimization: fetch once)
full_year_time_entries_all = db.get_time_entries(
    start_date=full_year_start,
    end_date=full_year_end
)

if not billable_employees_df.empty:
    performance_data = processor.get_performance_metrics(
        start_date=full_year_start,
        end_date=full_year_end,
        constraint=None
    )

    # Transform performance metrics to utilization trend DataFrame
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    utilization_data = []
    current_month = current_date.month

    for month_num in range(1, 13):
        month_name = f"{month_names[month_num - 1]} {current_date.year}"

        # Determine if this is actual or projected
        if month_num < current_month:
            data_type = 'Actual'
            # Use actuals only for past months
            month_data = performance_data['actuals'].get(month_name, {})
            possible_data = performance_data['possible'].get(month_name, {})

            total_billable_hours = sum(emp_data.get('billable_hours', 0) for emp_data in month_data.values())
            total_possible_hours = sum(emp_data.get('hours', 0) for emp_data in possible_data.values())

        elif month_num == current_month:
            # Use gold standard formula for current month:
            # For each employee, project missing hours from their last timesheet entry
            month_info = months_df[
                (months_df['year'] == current_date.year) &
                (months_df['month'] == current_month)
            ]

            if not month_info.empty:
                working_days = int(month_info['working_days'].iloc[0])
                month_holidays = int(month_info['holidays'].iloc[0]) if pd.notna(month_info['holidays'].iloc[0]) else 0
                available_working_days = max(working_days - month_holidays, 1)

                # Get actual and projected data for this month
                actual_month_data = performance_data['actuals'].get(month_name, {})
                projected_month_data = performance_data['projected'].get(month_name, {})
                possible_month_data = performance_data['possible'].get(month_name, {})

                # Calculate actual billable hours
                actual_billable = sum(emp_data.get('billable_hours', 0) for emp_data in actual_month_data.values())

                # Get time entries for this month to find per-employee last entry dates
                month_start_str = f"{current_date.year}-{current_month:02d}-01"
                month_end_day = calendar.monthrange(current_date.year, current_month)[1]
                month_end_str = f"{current_date.year}-{current_month:02d}-{month_end_day}"
                month_start_date = datetime(current_date.year, current_month, 1).date()
                month_end_date = datetime(current_date.year, current_month, month_end_day).date()

                month_time_entries = full_year_time_entries_all[
                    (full_year_time_entries_all['date'] >= month_start_str) &
                    (full_year_time_entries_all['date'] <= month_end_str)
                ] if not full_year_time_entries_all.empty else pd.DataFrame()

                last_entry_dates = {}
                if not month_time_entries.empty:
                    billable_te = month_time_entries[month_time_entries['billable'] == 1]
                    if not billable_te.empty:
                        last_entry_dates = billable_te.groupby('employee_id')['date'].max().to_dict()

                # For each employee with projected data, calculate missing hours
                total_projected_missing = 0
                for emp_id_str, proj_data in projected_month_data.items():
                    proj_hours = proj_data.get('hours', 0)
                    if proj_hours <= 0:
                        continue

                    # Try to convert emp_id to int for matching with last_entry_dates
                    try:
                        emp_id_int = int(emp_id_str)
                    except (ValueError, TypeError):
                        emp_id_int = emp_id_str

                    last_entry_str = last_entry_dates.get(emp_id_int)
                    if last_entry_str:
                        last_entry = pd.to_datetime(last_entry_str).date()
                        missing_start = last_entry + timedelta(days=1)
                    else:
                        missing_start = month_start_date  # No entries yet, project entire month

                    if missing_start <= month_end_date:
                        missing_days = _count_working_days(missing_start, month_end_date)
                    else:
                        missing_days = 0

                    if missing_days > 0 and available_working_days > 0:
                        total_projected_missing += proj_hours * (missing_days / available_working_days)

                total_billable_hours = actual_billable + total_projected_missing
                total_possible_hours = sum(emp_data.get('hours', 0) for emp_data in possible_month_data.values())

                # Determine type based on whether we have significant actuals
                data_type = 'Actual' if actual_billable > 0 else 'Projected'
            else:
                # Fallback if no month info available
                actual_month_data = performance_data['actuals'].get(month_name, {})
                possible_month_data = performance_data['possible'].get(month_name, {})
                total_billable_hours = sum(emp_data.get('billable_hours', 0) for emp_data in actual_month_data.values())
                total_possible_hours = sum(emp_data.get('hours', 0) for emp_data in possible_month_data.values())
                data_type = 'Actual'

        else:
            data_type = 'Projected'
            # Use projected only for future months
            month_data = performance_data['projected'].get(month_name, {})
            possible_data = performance_data['possible'].get(month_name, {})

            total_billable_hours = sum(emp_data.get('hours', 0) for emp_data in month_data.values())
            total_possible_hours = sum(emp_data.get('hours', 0) for emp_data in possible_data.values())

        # Get PTO hours for this month from billable employees
        total_pto_hours = 0
        if not full_year_time_entries_all.empty:
            # Calculate month date range
            month_start_str = f"{current_date.year}-{month_num:02d}-01"
            month_end_day = calendar.monthrange(current_date.year, month_num)[1]
            month_end_str = f"{current_date.year}-{month_num:02d}-{month_end_day}"

            # Filter time entries for this month
            month_entries = full_year_time_entries_all[
                (full_year_time_entries_all['date'] >= month_start_str) &
                (full_year_time_entries_all['date'] <= month_end_str)
            ]

            if not month_entries.empty:
                # Filter to billable employees only
                billable_emp_ids = billable_employees_df['id'].tolist()
                billable_entries = month_entries[month_entries['employee_id'].isin(billable_emp_ids)]

                # Get PTO hours (FRINGE.PTO)
                pto_entries = billable_entries[billable_entries['project_id'] == 'FRINGE.PTO']
                total_pto_hours = pto_entries['hours'].sum() if not pto_entries.empty else 0

        # Calculate available hours (exclude PTO; holidays already subtracted in _build_possible_data)
        available_hours = max(total_possible_hours - total_pto_hours, 0)

        # Calculate utilization percentage using available hours
        if available_hours > 0:
            avg_utilization = (total_billable_hours / available_hours) * 100
        else:
            avg_utilization = 0

        utilization_data.append({
            'month': month_num,
            'month_name': month_names[month_num - 1],
            'avg_utilization': avg_utilization,
            'type': data_type
        })

    utilization_trend_df = pd.DataFrame(utilization_data)
else:
    utilization_trend_df = pd.DataFrame()

# Calculate YTD average utilization using aggregate formula (total billable / total available)
if not utilization_trend_df.empty:
    # Sum up all billable, possible, and PTO hours from actual months only
    ytd_total_billable = 0
    ytd_total_possible = 0
    ytd_total_pto = 0

    for month_num in range(1, current_date.month + 1):
        month_name = f"{utilization_trend_df.iloc[month_num-1]['month_name']} {current_date.year}"

        # Get actual billable hours from actuals
        actual_month_data = performance_data['actuals'].get(month_name, {})
        ytd_total_billable += sum(emp_data.get('billable_hours', 0) for emp_data in actual_month_data.values())

        # Get possible hours
        possible_month_data = performance_data['possible'].get(month_name, {})
        ytd_total_possible += sum(emp_data.get('hours', 0) for emp_data in possible_month_data.values())

        # Get PTO hours for this month
        if not full_year_time_entries_all.empty:
            month_start_str = f"{current_date.year}-{month_num:02d}-01"
            month_end_day = calendar.monthrange(current_date.year, month_num)[1]
            month_end_str = f"{current_date.year}-{month_num:02d}-{month_end_day}"

            month_entries = full_year_time_entries_all[
                (full_year_time_entries_all['date'] >= month_start_str) &
                (full_year_time_entries_all['date'] <= month_end_str)
            ]

            if not month_entries.empty:
                billable_emp_ids = billable_employees_df['id'].tolist()
                billable_entries = month_entries[month_entries['employee_id'].isin(billable_emp_ids)]

                pto_entries = billable_entries[billable_entries['project_id'] == 'FRINGE.PTO']
                ytd_total_pto += pto_entries['hours'].sum() if not pto_entries.empty else 0

    # Calculate aggregate utilization percentage using available hours
    # (holidays already subtracted in _build_possible_data)
    ytd_available = max(ytd_total_possible - ytd_total_pto, 0)
    avg_employee_utilization = (ytd_total_billable / ytd_available * 100) if ytd_available > 0 else 0
else:
    avg_employee_utilization = 0

# Key Metrics Row
st.markdown("#### Key Performance Indicators")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Avg Employee Utilization", f"{avg_employee_utilization:.1f}%")

with col2:
    total_quoted_value = projects_df['quoted_value'].sum() if not projects_df.empty else 0
    st.metric("Total Quoted Value", f"${total_quoted_value:,.0f}")

with col3:
    total_accrued = projects_df['budget_used'].sum() if not projects_df.empty else 0
    st.metric("Total Accrued", f"${total_accrued:,.0f}")

with col4:
    remaining = total_quoted_value - total_accrued
    burn_rate = (total_accrued / total_quoted_value * 100) if total_quoted_value > 0 else 0
    st.metric("Budget Burn Rate", f"{burn_rate:.1f}%", f"${remaining:,.0f} remaining", delta_color="inverse")

# --- Under-Utilized Projects Alert ---
st.markdown("---")

# Header row with title and help popover
alert_header_col1, alert_header_col2 = st.columns([4, 1])
with alert_header_col1:
    st.markdown("#### Under-Utilized Projects")
with alert_header_col2:
    with st.popover("What does this mean?"):
        st.markdown("""
**Under-utilized projects** have allocated staff capacity (FTE allocations with bill rates)
but aren't billing enough hours against that capacity. This represents potential revenue
that could be captured.

**How it's calculated:**

**Utilization %** = (Actual Billable Hours / Allocated Hours) x 100

- **Allocated Hours**: From FTE allocations -- `allocated_fte x working_days x 8 hrs/day` summed across all team members. For the current (partial) month, allocated hours are prorated to elapsed working days.
- **Actual Billable Hours**: From time entries marked as billable
- **Revenue Gap**: Dollar value of unused capacity -- `(Allocated Hours - Actual Billable Hours) x avg bill rate`. The avg bill rate is the blended rate across all team members on the project, weighted by their allocated hours.

**Color Key:**
- Green (>=90%): Well utilized
- Yellow (70-89%): Minor risk -- some unused capacity
- Orange (50-69%): Medium risk -- significant money on the table
- Red (<50%): Severely under-utilized

**N/A** means the project has no FTE allocations, so utilization cannot be calculated.

*Based on YTD (Year-to-Date) data.*
        """)

with st.spinner("Checking project utilization..."):
    try:
        util_df = calculate_all_projects_utilization(db, processor, ytd_start, ytd_end)
    except Exception as e:
        logger.error(f"Failed to calculate project utilization: {e}")
        util_df = pd.DataFrame()
        st.error("Could not load project utilization data. Check logs for details.")

if not util_df.empty:
    # Filter to under-utilized projects (< 70% utilization and has allocations)
    underutilized = util_df[
        (util_df['utilization_pct'].notna()) &
        (util_df['utilization_pct'] < 70) &
        (util_df['allocated_hours'] > 0)
    ].sort_values('revenue_gap', ascending=False)

    if not underutilized.empty:
        total_revenue_gap = underutilized['revenue_gap'].sum()

        st.warning(
            f"**{len(underutilized)} project(s) are under-utilized** — "
            f"estimated **{safe_currency_display(total_revenue_gap)}** in potential revenue "
            f"is not being captured (YTD)."
        )

        # Show compact table
        alert_display = underutilized[['project_name', 'utilization_pct', 'revenue_gap', 'health_icon']].copy()
        alert_display.columns = ['Project', 'Utilization %', 'Revenue Gap', '_icon']
        alert_display['Utilization %'] = alert_display.apply(
            lambda row: f"{row['_icon']} {row['Utilization %']:.1f}%", axis=1
        )
        alert_display['Revenue Gap'] = alert_display['Revenue Gap'].apply(lambda x: f"${x:,.0f}")
        alert_display = alert_display.drop(columns=['_icon'])
        st.dataframe(alert_display, hide_index=True, use_container_width=True)
    else:
        st.success("All billable projects are well-utilized (>=70% of allocated capacity).")
else:
    st.info("No billable projects with allocations found for utilization analysis.")

# Charts Row 1
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📈 Monthly Utilization Trend (Actual & Projected)")
    if not utilization_trend_df.empty:
        # Separate actual and projected data
        actual_data = utilization_trend_df[utilization_trend_df['type'] == 'Actual']
        projected_data = utilization_trend_df[utilization_trend_df['type'] == 'Projected']

        fig = go.Figure()

        # Actual line (solid)
        if not actual_data.empty:
            fig.add_trace(go.Scatter(
                x=actual_data['month_name'],
                y=actual_data['avg_utilization'],
                mode='lines+markers',
                name='Actual',
                line=dict(color='#1f77b4', width=3),
                marker=dict(size=8)
            ))

        # Projected line (dashed)
        if not projected_data.empty:
            fig.add_trace(go.Scatter(
                x=projected_data['month_name'],
                y=projected_data['avg_utilization'],
                mode='lines+markers',
                name='Projected',
                line=dict(color='#ff7f0e', width=3, dash='dash'),
                marker=dict(size=8, symbol='diamond')
            ))

        # 80% target line
        fig.add_shape(
            type="line",
            x0=0,
            x1=11,
            y0=80,
            y1=80,
            line=dict(color="red", dash="dash", width=2),
        )

        # Add colored zones
        fig.add_hrect(y0=80, y1=100, fillcolor="green", opacity=0.1, line_width=0)
        fig.add_hrect(y0=60, y1=80, fillcolor="yellow", opacity=0.1, line_width=0)
        fig.add_hrect(y0=0, y1=60, fillcolor="red", opacity=0.1, line_width=0)

        fig.update_layout(
            height=400,
            yaxis_title="Average Utilization %",
            yaxis=dict(range=[0, 100]),
            showlegend=True,
            legend=dict(x=0.02, y=0.98),
            hovermode='x unified'
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No utilization data available")

with col2:
    st.markdown("#### 🎯 Project Status Distribution")
    if not projects_df.empty:
        status_counts = projects_df['status'].value_counts()

        # Add active/total info
        active_count = projects_df[projects_df['status'] == 'Active'].shape[0]
        total_count = len(projects_df)

        fig = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            color_discrete_map={
                'Active': '#2E7D32',
                'Completed': '#1976D2',
                'On Hold': '#FFA726',
                'Cancelled': '#E53935'
            }
        )
        fig.update_layout(
            height=400,
            annotations=[dict(
                text=f'{active_count} Active<br>of {total_count} Total',
                x=0.5, y=0.5,
                font_size=14,
                showarrow=False
            )]
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No project data available")

# Charts Row 2
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 👥 Employee Billable Utilization (Individual)")
    if not billable_employees_df.empty and not utilization_trend_df.empty:
        # Calculate billable utilization for each employee using YTD data
        employee_util_data = []

        # Pre-compute current month constants (invariant across employees)
        cm_month_name = f"{month_names[current_date.month - 1]} {current_date.year}"
        cm_month_info = months_df[
            (months_df['year'] == current_date.year) &
            (months_df['month'] == current_date.month)
        ]
        cm_start_str = f"{current_date.year}-{current_date.month:02d}-01"
        cm_end_day = calendar.monthrange(current_date.year, current_date.month)[1]
        cm_end_str = f"{current_date.year}-{current_date.month:02d}-{cm_end_day}"
        cm_start_date = datetime(current_date.year, current_date.month, 1).date()
        cm_end_date = datetime(current_date.year, current_date.month, cm_end_day).date()
        if not cm_month_info.empty:
            cm_working_days = int(cm_month_info['working_days'].iloc[0])
            cm_holidays = int(cm_month_info['holidays'].iloc[0]) if pd.notna(cm_month_info['holidays'].iloc[0]) else 0
            cm_available_working_days = max(cm_working_days - cm_holidays, 1)
        else:
            cm_available_working_days = 0

        # Pre-filter current month billable time entries for last-entry lookup
        if not full_year_time_entries_all.empty:
            cm_billable_entries = full_year_time_entries_all[
                (full_year_time_entries_all['date'] >= cm_start_str) &
                (full_year_time_entries_all['date'] <= cm_end_str) &
                (full_year_time_entries_all['billable'] == 1)
            ]
        else:
            cm_billable_entries = pd.DataFrame()

        # Current month projected data
        cm_projected_data = performance_data['projected'].get(cm_month_name, {})

        for _, emp in billable_employees_df.iterrows():
            emp_id_str = str(emp['id'])

            # Sum billable, possible, and PTO hours across all YTD months
            ytd_billable = 0
            ytd_possible = 0
            emp_ytd_pto = 0

            for month_num in range(1, current_date.month + 1):
                month_name = f"{month_names[month_num - 1]} {current_date.year}"

                # Get actual billable hours from actuals
                actual_month_data = performance_data['actuals'].get(month_name, {})
                emp_actual = actual_month_data.get(emp_id_str, {})
                emp_actual_billable = emp_actual.get('billable_hours', 0)

                # For current month, add projected missing hours (gold standard formula)
                if month_num == current_date.month and cm_available_working_days > 0:
                    emp_projected = cm_projected_data.get(emp_id_str, {})
                    emp_proj_hours = emp_projected.get('hours', 0)

                    if emp_proj_hours > 0:
                        # Find this employee's last billable entry date
                        if not cm_billable_entries.empty:
                            emp_cm_entries = cm_billable_entries[
                                cm_billable_entries['employee_id'] == emp['id']
                            ]
                            if not emp_cm_entries.empty:
                                last_entry = pd.to_datetime(emp_cm_entries['date'].max()).date()
                                missing_start = last_entry + timedelta(days=1)
                            else:
                                missing_start = cm_start_date
                        else:
                            missing_start = cm_start_date

                        if missing_start <= cm_end_date:
                            missing_days = _count_working_days(missing_start, cm_end_date)
                        else:
                            missing_days = 0

                        if missing_days > 0:
                            emp_projected_missing = emp_proj_hours * (missing_days / cm_available_working_days)
                            ytd_billable += emp_actual_billable + emp_projected_missing
                        else:
                            ytd_billable += emp_actual_billable
                    else:
                        ytd_billable += emp_actual_billable
                else:
                    ytd_billable += emp_actual_billable

                # Get possible hours and adjust for hire/term dates
                possible_month_data = performance_data['possible'].get(month_name, {})
                emp_possible = possible_month_data.get(emp_id_str, {})
                possible_hours = emp_possible.get('hours', 0)

                # Adjust for hire/term dates
                if pd.notna(emp.get('hire_date')):
                    hire_date = pd.to_datetime(emp['hire_date']).date()
                else:
                    hire_date = datetime(current_date.year, 1, 1).date()

                if pd.notna(emp.get('term_date')):
                    term_date = pd.to_datetime(emp['term_date']).date()
                else:
                    term_date = datetime(current_date.year, 12, 31).date()

                # Get working days for adjustment
                working_days = get_working_days_in_range(hire_date, term_date, months_df, current_date.year, month_num)
                possible_worked_days = emp_possible.get('worked_days', 21)

                # Adjust possible hours if needed
                if possible_worked_days > 0 and working_days != possible_worked_days:
                    daily_rate = possible_hours / possible_worked_days
                    adjusted_possible = daily_rate * working_days
                else:
                    adjusted_possible = possible_hours

                ytd_possible += adjusted_possible

                # Get PTO hours for this employee for this month
                if not full_year_time_entries_all.empty:
                    month_start_str = f"{current_date.year}-{month_num:02d}-01"
                    month_end_day = calendar.monthrange(current_date.year, month_num)[1]
                    month_end_str = f"{current_date.year}-{month_num:02d}-{month_end_day}"

                    month_entries = full_year_time_entries_all[
                        (full_year_time_entries_all['date'] >= month_start_str) &
                        (full_year_time_entries_all['date'] <= month_end_str)
                    ]

                    if not month_entries.empty:
                        emp_entries = month_entries[month_entries['employee_id'] == emp['id']]

                        pto_entries = emp_entries[emp_entries['project_id'] == 'FRINGE.PTO']
                        emp_ytd_pto += pto_entries['hours'].sum() if not pto_entries.empty else 0

            # Calculate available hours for this employee (exclude PTO; holidays already subtracted in _build_possible_data)
            emp_available = max(ytd_possible - emp_ytd_pto, 0)

            # Calculate utilization percentage using available hours
            utilization_pct = (ytd_billable / emp_available * 100) if emp_available > 0 else 0

            employee_util_data.append({
                'name': emp['name'],
                'utilization_rate': utilization_pct
            })

        utilization_df = pd.DataFrame(employee_util_data)

        # Sort by utilization rate descending
        utilization_df = utilization_df.sort_values('utilization_rate', ascending=False)

        # Assign colors based on utilization rate (matching employees.py thresholds)
        colors = utilization_df['utilization_rate'].apply(
            lambda x: '#ffcccc' if x > 120 else ('#fff9cc' if x >= 100 else ('#2E7D32' if x >= 80 else '#cce5ff'))
        )

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=utilization_df['name'],
            y=utilization_df['utilization_rate'],
            marker_color=colors,
            name='Billable Utilization %',
            text=utilization_df['utilization_rate'].apply(lambda x: f"{x:.1f}%"),
            textposition='outside'
        ))
        fig.add_shape(
            type="line",
            x0=-0.5,
            x1=len(utilization_df)-0.5,
            y0=80,
            y1=80,
            line=dict(color="red", dash="dash", width=2),
        )
        fig.update_layout(
            height=400,
            xaxis_tickangle=-45,
            yaxis_title="Billable Utilization %",
            yaxis=dict(range=[0, 150]),
            showlegend=False
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No billable employee data available")

with col2:
    st.markdown("#### 💰 Monthly Burn Rate (Labor + Expenses)")
    if not time_entries_df.empty or not expenses_df.empty:
        # Calculate labor costs by month
        labor_by_month = {}
        if not time_entries_df.empty:
            time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
            time_entries_df['month'] = time_entries_df['date'].dt.to_period('M')

            for month, group in time_entries_df.groupby('month'):
                labor_cost = (group['hours'] * group['hourly_rate']).sum()
                labor_by_month[str(month)] = labor_cost

        # Calculate expense costs by month
        expense_by_month = {}
        if not expenses_df.empty:
            expenses_df['date'] = pd.to_datetime(expenses_df['date'])
            expenses_df['month'] = expenses_df['date'].dt.to_period('M')

            for month, group in expenses_df.groupby('month'):
                expense_cost = group['amount'].sum()
                expense_by_month[str(month)] = expense_cost

        # Combine data
        all_months = sorted(set(list(labor_by_month.keys()) + list(expense_by_month.keys())))

        burn_data = []
        for month in all_months:
            labor = labor_by_month.get(month, 0)
            expense = expense_by_month.get(month, 0)
            burn_data.append({
                'month': month,
                'labor_cost': labor,
                'expense_cost': expense,
                'total_burn': labor + expense
            })

        burn_df = pd.DataFrame(burn_data)

        if not burn_df.empty:
            fig = go.Figure()

            # Stacked area chart
            fig.add_trace(go.Scatter(
                x=burn_df['month'],
                y=burn_df['labor_cost'],
                mode='lines',
                name='Labor Cost',
                line=dict(width=0.5, color='#1f77b4'),
                stackgroup='one',
                fillcolor='rgba(31, 119, 180, 0.5)'
            ))
            fig.add_trace(go.Scatter(
                x=burn_df['month'],
                y=burn_df['expense_cost'],
                mode='lines',
                name='Expenses',
                line=dict(width=0.5, color='#ff7f0e'),
                stackgroup='one',
                fillcolor='rgba(255, 127, 14, 0.5)'
            ))

            # Total burn line
            fig.add_trace(go.Scatter(
                x=burn_df['month'],
                y=burn_df['total_burn'],
                mode='lines+markers',
                name='Total Burn',
                line=dict(color='red', width=2),
                marker=dict(size=6)
            ))

            fig.update_layout(
                height=400,
                xaxis_title="Month",
                yaxis_title="Amount ($)",
                showlegend=True,
                hovermode='x unified'
            )
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No burn rate data available")
    else:
        st.info("No time entry or expense data available")

# Recent Activity
st.markdown("---")
st.markdown("### 📋 Recent Activity")

if not time_entries_df.empty:
    # Convert date to datetime for proper sorting
    time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
    recent_entries = time_entries_df.nlargest(10, 'date')[
        ['date', 'employee_name', 'project_id', 'project_name', 'hours', 'billable', 'description']
    ].copy()
    recent_entries = recent_entries.rename(columns={'project_id': 'Project Code'})
    # Format date back to string for display
    recent_entries['date'] = recent_entries['date'].dt.strftime('%Y-%m-%d')
    # Add visual indicator for billable status
    recent_entries['billable'] = recent_entries['billable'].apply(lambda x: '✓ Billable' if x == 1 else '✗ Non-billable')
    st.dataframe(recent_entries, width='stretch', hide_index=True)
else:
    st.info("No recent time entries")
