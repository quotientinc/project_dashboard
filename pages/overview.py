import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Helper function to calculate working days in a month range
def get_working_days_in_range(start_date, end_date, months_df, year, month):
    """Calculate working days between start and end date for a specific month"""
    import calendar

    # Get month info
    month_info = months_df[
        (months_df['year'] == year) &
        (months_df['month'] == month)
    ]

    if month_info.empty:
        return 21  # Default fallback

    working_days_in_month = int(month_info['working_days'].iloc[0])

    # Calculate the actual working days the employee was active
    month_start = datetime(year, month, 1).date()
    month_end = datetime(year, month, calendar.monthrange(year, month)[1]).date()

    # Determine actual start and end dates for this employee in this month
    actual_start = max(start_date, month_start)
    actual_end = min(end_date, month_end)

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
st.markdown("### 📊 Dashboard Overview (🚨data is in progress)")
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
        (pd.to_datetime(employees_df['term_date']).dt.date >= current_date.date())
    )
].copy()

# Get performance metrics for full year (for trend chart with projections)
full_year_start = datetime(current_date.year, 1, 1).strftime('%Y-%m-%d')
full_year_end = datetime(current_date.year, 12, 31).strftime('%Y-%m-%d')

# Get performance metrics for YTD only (for KPI calculations)
ytd_start = datetime(current_date.year, 1, 1).strftime('%Y-%m-%d')
ytd_end = current_date.strftime('%Y-%m-%d')

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
            # Use smart blending for current month
            # Get month info for working days calculation
            month_info = months_df[
                (months_df['year'] == current_date.year) &
                (months_df['month'] == current_month)
            ]

            if not month_info.empty:
                working_days = int(month_info['working_days'].iloc[0])
                days_so_far = current_date.day
                days_remaining = working_days - days_so_far

                # Get actual and projected data for this month
                actual_month_data = performance_data['actuals'].get(month_name, {})
                projected_month_data = performance_data['projected'].get(month_name, {})
                possible_month_data = performance_data['possible'].get(month_name, {})

                # Calculate blended billable hours
                actual_billable = sum(emp_data.get('billable_hours', 0) for emp_data in actual_month_data.values())

                # For remaining days, estimate from projected
                if working_days > 0 and days_remaining > 0:
                    projected_total = sum(emp_data.get('hours', 0) for emp_data in projected_month_data.values())
                    projected_remaining = (projected_total / working_days) * days_remaining
                    total_billable_hours = actual_billable + projected_remaining
                else:
                    total_billable_hours = actual_billable

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

        # Calculate utilization percentage
        if total_possible_hours > 0:
            avg_utilization = (total_billable_hours / total_possible_hours) * 100
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

# Calculate YTD average utilization using aggregate formula (total billable / total possible)
if not utilization_trend_df.empty:
    # Sum up all billable and possible hours from actual months only
    ytd_total_billable = 0
    ytd_total_possible = 0

    for month_num in range(1, current_date.month + 1):
        month_name = f"{utilization_trend_df.iloc[month_num-1]['month_name']} {current_date.year}"

        # Get actual billable hours from actuals
        actual_month_data = performance_data['actuals'].get(month_name, {})
        ytd_total_billable += sum(emp_data.get('billable_hours', 0) for emp_data in actual_month_data.values())

        # Get possible hours
        possible_month_data = performance_data['possible'].get(month_name, {})
        ytd_total_possible += sum(emp_data.get('hours', 0) for emp_data in possible_month_data.values())

    # Calculate aggregate utilization percentage
    avg_employee_utilization = (ytd_total_billable / ytd_total_possible * 100) if ytd_total_possible > 0 else 0
else:
    avg_employee_utilization = 0

# Key Metrics Row
st.markdown("#### Key Performance Indicators")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Avg Employee Utilization", f"{avg_employee_utilization:.1f}%")

with col2:
    # Sum only leaf projects to prevent double-counting parent + children
    leaf_projects = projects_df[projects_df['is_parent'] == 0] if not projects_df.empty else projects_df
    total_contract_value = leaf_projects['contract_value'].sum() if not leaf_projects.empty else 0
    st.metric("Total Contract Value", f"${total_contract_value:,.0f}")

with col3:
    total_accrued = leaf_projects['budget_used'].sum() if not leaf_projects.empty else 0
    st.metric("Total Accrued", f"${total_accrued:,.0f}")

with col4:
    remaining = total_contract_value - total_accrued
    burn_rate = (total_accrued / total_contract_value * 100) if total_contract_value > 0 else 0
    st.metric("Budget Burn Rate", f"{burn_rate:.1f}%", f"${remaining:,.0f} remaining", delta_color="inverse")

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
        st.plotly_chart(fig, use_container_width=True)
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
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No project data available")

# Charts Row 2
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 👥 Employee Billable Utilization (Individual)")
    if not billable_employees_df.empty and not utilization_trend_df.empty:
        # Calculate billable utilization for each employee using YTD data
        employee_util_data = []

        for _, emp in billable_employees_df.iterrows():
            emp_id_str = str(emp['id'])

            # Sum billable and possible hours across all YTD months
            ytd_billable = 0
            ytd_possible = 0

            for month_num in range(1, current_date.month + 1):
                month_name = f"{utilization_trend_df.iloc[month_num-1]['month_name']} {current_date.year}"

                # Get actual billable hours from actuals
                actual_month_data = performance_data['actuals'].get(month_name, {})
                emp_actual = actual_month_data.get(emp_id_str, {})
                ytd_billable += emp_actual.get('billable_hours', 0)

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

            # Calculate utilization percentage
            utilization_pct = (ytd_billable / ytd_possible * 100) if ytd_possible > 0 else 0

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
        st.plotly_chart(fig, use_container_width=True)
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
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No burn rate data available")
    else:
        st.info("No time entry or expense data available")

# Project Health Dashboard
st.markdown("---")
st.markdown("### 🏥 Project Health Dashboard")

if not projects_df.empty:
    health_df = processor.calculate_project_health(projects_df, allocations_df)

    # Add filter option
    col1, col2 = st.columns([3, 1])
    with col2:
        show_at_risk_only = st.checkbox("Show only at-risk projects (< 75%)", value=False)

    # Filter if requested
    if show_at_risk_only:
        health_df = health_df[health_df['health_score'] < 75]

    # Sort by health score (worst first)
    health_df = health_df.sort_values('health_score', ascending=True)

    if not health_df.empty:
        # Display in 4-column grid
        projects_per_row = 4
        for i in range(0, len(health_df), projects_per_row):
            cols = st.columns(projects_per_row)
            batch = health_df.iloc[i:i+projects_per_row]

            for idx, (_, project) in enumerate(batch.iterrows()):
                with cols[idx]:
                    # Handle NaN values
                    health_score = project['health_score'] if not pd.isna(project['health_score']) else 0
                    budget_health = project['budget_health'] if not pd.isna(project['budget_health']) else 0
                    schedule_progress = project['schedule_progress'] if not pd.isna(project['schedule_progress']) else 0
                    profit_margin = project['profit_margin'] if not pd.isna(project['profit_margin']) else 0

                    # Determine color based on health score
                    if health_score >= 75:
                        color = "🟢"
                    elif health_score >= 50:
                        color = "🟡"
                    else:
                        color = "🔴"

                    st.markdown(f"**{project['name']}** {color}")
                    st.metric("Health Score", f"{health_score:.1f}%")
                    st.progress(max(0.0, min(1.0, health_score / 100)))

                    with st.expander("Details"):
                        st.write(f"Budget Health: {budget_health:.1f}%")
                        st.write(f"Schedule Progress: {schedule_progress:.1f}%")
                        st.write(f"Profit Margin: {profit_margin:.1f}%")
    else:
        st.info("No at-risk projects found")
else:
    st.info("No project data available")

# Forecast Section
st.markdown("---")
st.markdown("### 🔮 Project Completion Forecast")

if not projects_df.empty and not time_entries_df.empty:
    forecast_df = processor.forecast_project_completion(projects_df, time_entries_df)

    if not forecast_df.empty:
        for _, forecast in forecast_df.iterrows():
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.write(f"**{forecast['project_name']}**")

            with col2:
                st.write(f"Progress: {forecast['current_progress']:.1f}%")
                st.progress(min(max(forecast['current_progress'] / 100, 0.0), 1.0))

            with col3:
                st.write(f"Est. Completion: {forecast['forecast_completion'].strftime('%Y-%m-%d')}")

            with col4:
                if forecast['on_track']:
                    st.success("On Track")
                else:
                    days_late = (forecast['forecast_completion'] - forecast['scheduled_end']).days
                    st.error(f"Delayed by {days_late} days")
    else:
        st.info("Insufficient data for forecasting")
else:
    st.info("No project or time entry data available for forecasting")

# Recent Activity
st.markdown("---")
st.markdown("### 📋 Recent Activity")

if not time_entries_df.empty:
    # Convert date to datetime for proper sorting
    time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
    recent_entries = time_entries_df.nlargest(10, 'date')[
        ['date', 'employee_name', 'project_name', 'hours', 'billable', 'description']
    ].copy()
    # Format date back to string for display
    recent_entries['date'] = recent_entries['date'].dt.strftime('%Y-%m-%d')
    # Add visual indicator for billable status
    recent_entries['billable'] = recent_entries['billable'].apply(lambda x: '✓ Billable' if x == 1 else '✗ Non-billable')
    st.dataframe(recent_entries, use_container_width=True, hide_index=True)
else:
    st.info("No recent time entries")
