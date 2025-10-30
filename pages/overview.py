import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor
filters = st.session_state.filters

# Load data with filters
projects_df = db.get_projects()
employees_df = db.get_employees()
allocations_df = db.get_allocations()
time_entries_df = db.get_time_entries(
    start_date=filters['start_date'].strftime('%Y-%m-%d'),
    end_date=filters['end_date'].strftime('%Y-%m-%d')
)
expenses_df = db.get_expenses()

# Apply filters
if filters['projects']:
    projects_df = projects_df[projects_df['name'].isin(filters['projects'])]
if filters['status']:
    projects_df = projects_df[projects_df['status'].isin(filters['status'])]

# Key Metrics Row
st.markdown("### 📊 Key Performance Indicators")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    total_revenue = projects_df['revenue_actual'].sum() if not projects_df.empty else 0
    st.metric("Total Revenue", f"${total_revenue:,.0f}")

with col2:
    total_cost = projects_df['budget_used'].sum() if not projects_df.empty else 0
    st.metric("Total Cost", f"${total_cost:,.0f}")

with col3:
    profit = total_revenue - total_cost
    profit_margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
    st.metric("Profit Margin", f"{profit_margin:.1f}%", f"${profit:,.0f}")

with col4:
    avg_utilization = employees_df['utilization'].mean() if not employees_df.empty else 0
    st.metric("Avg Utilization", f"{avg_utilization:.1f}%")

with col5:
    active_projects = len(projects_df[projects_df['status'] == 'Active']) if not projects_df.empty else 0
    total_projects = len(projects_df) if not projects_df.empty else 0
    st.metric("Active Projects", active_projects, f"of {total_projects}")

# Charts Row 1
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📈 Revenue vs Cost by Project")
    if not projects_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Revenue',
            x=projects_df['name'],
            y=projects_df['revenue_actual'],
            marker_color='green'
        ))
        fig.add_trace(go.Bar(
            name='Cost',
            x=projects_df['name'],
            y=projects_df['budget_used'],
            marker_color='red'
        ))
        fig.update_layout(
            barmode='group',
            height=400,
            xaxis_tickangle=-45,
            showlegend=True
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No project data available")

with col2:
    st.markdown("#### 🎯 Project Status Distribution")
    if not projects_df.empty:
        status_counts = projects_df['status'].value_counts()
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
        fig.update_layout(height=400)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No project data available")

# Charts Row 2
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 👥 Employee Utilization")
    if not employees_df.empty:
        utilization_df = processor.calculate_employee_utilization(
            employees_df, allocations_df, time_entries_df
        )
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=utilization_df['name'],
            y=utilization_df['utilization_rate'],
            marker_color='lightblue',
            name='Utilization %'
        ))
        fig.add_shape(
            type="line",
            x0=-0.5,
            x1=len(utilization_df)-0.5,
            y0=80,
            y1=80,
            line=dict(color="red", dash="dash"),
        )
        fig.update_layout(
            height=400,
            xaxis_tickangle=-45,
            yaxis_title="Utilization %",
            showlegend=False
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No employee data available")

with col2:
    st.markdown("#### 💰 Monthly Burn Rate")
    if not expenses_df.empty:
        burn_rate_df = processor.calculate_burn_rate(expenses_df, 'monthly')
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=burn_rate_df['period'].astype(str),
            y=burn_rate_df['burn_rate'],
            mode='lines+markers',
            name='Monthly Burn',
            line=dict(color='orange', width=2)
        ))
        fig.add_trace(go.Scatter(
            x=burn_rate_df['period'].astype(str),
            y=burn_rate_df['cumulative_burn'],
            mode='lines',
            name='Cumulative',
            line=dict(color='red', width=2, dash='dash')
        ))
        fig.update_layout(
            height=400,
            xaxis_title="Month",
            yaxis_title="Amount ($)",
            showlegend=True
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No expense data available")

# Project Health Dashboard
st.markdown("---")
st.markdown("### 🏥 Project Health Dashboard")

if not projects_df.empty:
    health_df = processor.calculate_project_health(projects_df, allocations_df)
    
    # Create columns for health metrics
    cols = st.columns(len(health_df))
    
    for idx, (_, project) in enumerate(health_df.iterrows()):
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
        ['date', 'employee_name', 'project_name', 'hours', 'description']
    ].copy()
    # Format date back to string for display
    recent_entries['date'] = recent_entries['date'].dt.strftime('%Y-%m-%d')
    st.dataframe(recent_entries, width='stretch', hide_index=True)
else:
    st.info("No recent time entries")
