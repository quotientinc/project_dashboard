import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Date Range Filter
st.markdown("### 📊 Dashboard Overview")
col1, col2 = st.columns([4, 1])

with col1:
    st.write("")  # Spacer

with col2:
    date_range_option = st.selectbox(
        "Time Range",
        ["Last 30 Days", "Last Quarter", "YTD", "This Year", "All Time"],
        index=3,  # Default to "This Year"
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
utilization_trend_df = processor.calculate_monthly_utilization_trend(
    employees_df, allocations_df, time_entries_df, months_df
)

# Calculate YTD average utilization
if not utilization_trend_df.empty:
    ytd_data = utilization_trend_df[utilization_trend_df['type'] == 'Actual']
    avg_employee_utilization = ytd_data['avg_utilization'].mean() if not ytd_data.empty else 0
else:
    avg_employee_utilization = 0

# Key Metrics Row
st.markdown("#### Key Performance Indicators")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Avg Employee Utilization", f"{avg_employee_utilization:.1f}%")

with col2:
    total_contract_value = projects_df['contract_value'].sum() if not projects_df.empty else 0
    st.metric("Total Contract Value", f"${total_contract_value:,.0f}")

with col3:
    total_accrued = projects_df['budget_used'].sum() if not projects_df.empty else 0
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
    st.markdown("#### 👥 Employee Utilization (Individual)")
    if not employees_df.empty:
        utilization_df = processor.calculate_employee_utilization(
            employees_df, allocations_df, time_entries_df
        )

        # Sort by utilization rate descending
        utilization_df = utilization_df.sort_values('utilization_rate', ascending=False)

        # Assign colors based on utilization rate
        colors = utilization_df['utilization_rate'].apply(
            lambda x: '#2E7D32' if x >= 80 else ('#FFA726' if x >= 60 else '#E53935')
        )

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=utilization_df['name'],
            y=utilization_df['utilization_rate'],
            marker_color=colors,
            name='Utilization %',
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
            yaxis_title="Utilization %",
            yaxis=dict(range=[0, 110]),
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No employee data available")

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
