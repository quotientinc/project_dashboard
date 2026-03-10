"""
Budget Trajectory Mockup - Multi-Modification Project Visualization

This page demonstrates how the Budget Trajectory chart can visualize projects
with multiple contract modifications, showing incremental funding increases over time.

Uses real data from project '220306.00.009.01' with a hard-coded modifications dataframe
to show stepped budget ceiling and target zones.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


def get_budget_at_date(date, modifications_df):
    """
    Get the applicable budget ceiling for a given date.

    Args:
        date: datetime or pd.Timestamp
        modifications_df: DataFrame with 'mod_date' and 'ceiling' columns

    Returns:
        float: Budget ceiling applicable at that date
    """
    date = pd.to_datetime(date)

    # Filter to modifications that occurred on or before this date
    applicable_mods = modifications_df[pd.to_datetime(modifications_df['mod_date']) <= date]

    if applicable_mods.empty:
        # No modification yet - use the first one (base contract)
        return modifications_df.iloc[0]['ceiling']

    # Return the most recent modification ceiling
    return applicable_mods.iloc[-1]['ceiling']


def create_stepped_budget_line(months, modifications_df):
    """
    Create a stepped line showing budget ceiling over time.

    Args:
        months: List of month labels
        modifications_df: DataFrame with 'mod_date' and 'ceiling' columns

    Returns:
        list: Budget ceiling value for each month
    """
    budget_values = []

    for month_label in months:
        # Convert month label to a date (first day of month)
        month_date = pd.to_datetime(month_label, format='%b %Y')
        budget = get_budget_at_date(month_date, modifications_df)
        budget_values.append(budget)

    return budget_values


def create_stepped_target_boundaries(months, modifications_df, threshold_pct):
    """
    Create stepped upper and lower target boundaries that adjust with budget modifications.

    Args:
        months: List of month labels
        modifications_df: DataFrame with 'mod_date' and 'ceiling' columns
        threshold_pct: Percentage threshold (e.g., 5.0 for ±5%)

    Returns:
        tuple: (upper_bounds, lower_bounds) as lists
    """
    upper_bounds = []
    lower_bounds = []

    for month_label in months:
        month_date = pd.to_datetime(month_label, format='%b %Y')
        budget = get_budget_at_date(month_date, modifications_df)

        upper_bounds.append(budget * (1 + threshold_pct / 100))
        lower_bounds.append(budget * (1 - threshold_pct / 100))

    return upper_bounds, lower_bounds


def calculate_cumulative_costs_as_percentages(monthly_data, modifications_df):
    """
    Calculate cumulative costs as percentages of the applicable budget ceiling.

    Args:
        monthly_data: List of dicts with 'month_label' and cost data
        modifications_df: DataFrame with 'mod_date' and 'ceiling' columns

    Returns:
        tuple: (actual_pcts, projected_pcts) as lists
    """
    actual_pcts = []
    projected_pcts = []
    cumulative_actual = 0
    cumulative_projected = 0

    for month in monthly_data:
        month_date = pd.to_datetime(month['month_label'], format='%b %Y')
        budget = get_budget_at_date(month_date, modifications_df)

        cumulative_actual += month.get('actual_cost', 0)
        cumulative_projected += month.get('projected_cost', 0)

        # Calculate percentages based on applicable budget at this point in time
        actual_pct = (cumulative_actual / budget * 100) if budget > 0 else 0
        projected_pct = (cumulative_projected / budget * 100) if budget > 0 else 0

        actual_pcts.append(actual_pct if month.get('is_past', False) or month.get('is_current', False) else None)
        projected_pcts.append(projected_pct)

    return actual_pcts, projected_pcts


def render_budget_mockup():
    """Main function to render the budget mockup page"""

    st.title("📊 Budget Trajectory Mockup")
    st.markdown("### Multi-Modification Project Visualization")

    st.info(
        "This page demonstrates how contract modifications with incremental funding "
        "can be visualized in the Budget Trajectory chart. The budget ceiling (green area) "
        "shows as a 'stair-step' pattern as modifications are awarded over time."
    )

    # Hard-coded modifications for the demonstration
    # These represent a long-running project that received funding in phases
    modifications_df = pd.DataFrame([
        {'mod_number': 'Base', 'mod_date': '2023-01-01', 'ceiling': 300000},
        {'mod_number': 'Mod 1', 'mod_date': '2023-06-01', 'ceiling': 500000},
        {'mod_number': 'Mod 2', 'mod_date': '2024-01-01', 'ceiling': 750000},
        {'mod_number': 'Mod 3', 'mod_date': '2024-06-01', 'ceiling': 1000000},
        {'mod_number': 'Mod 4', 'mod_date': '2025-01-01', 'ceiling': 1250000},
    ])

    modifications_df['mod_date'] = pd.to_datetime(modifications_df['mod_date'])

    # Project info
    PROJECT_ID = '220306.00.009.01'

    st.markdown(f"**Project ID:** `{PROJECT_ID}`")
    st.markdown(f"**Contract Period:** {modifications_df['mod_date'].min().strftime('%b %Y')} - Present")
    st.markdown(f"**Total Modifications:** {len(modifications_df) - 1}")  # Exclude base
    st.markdown(f"**Current Contract Ceiling:** ${modifications_df['ceiling'].iloc[-1]:,.0f}")

    st.divider()

    # Check for required session state
    if 'db_manager' not in st.session_state or 'data_processor' not in st.session_state:
        st.error("Database manager or data processor not initialized. Please return to the main page.")
        return

    db = st.session_state.db_manager
    processor = st.session_state.data_processor

    # Load data for the project
    try:
        with st.spinner("Loading project data..."):
            # Get project info
            projects_df = db.get_projects()
            project = projects_df[projects_df['id'] == PROJECT_ID]

            if project.empty:
                st.error(f"Project {PROJECT_ID} not found in database.")
                return

            project = project.iloc[0]

            # Get time entries and performance metrics
            time_entries = db.get_time_entries(project_id=PROJECT_ID)

            if time_entries.empty:
                st.warning(f"No time entries found for project {PROJECT_ID}. Chart will show projected data only.")

            # Get performance metrics
            # Use earliest mod date as start and add some buffer for end
            start_date = modifications_df['mod_date'].min().strftime('%Y-%m-%d')
            end_date = '2025-12-31'  # Extended end date to show future projections

            metrics = processor.get_performance_metrics(
                start_date=start_date,
                end_date=end_date,
                constraint={'project_id': PROJECT_ID}
            )

            # Get months data
            months_df = db.get_months()

            # Build monthly data
            months = pd.date_range(
                start=pd.to_datetime(start_date).replace(day=1),
                end=pd.to_datetime(end_date) + pd.DateOffset(months=1),
                freq='MS'
            )[:-1]

            monthly_data = []
            today = pd.Timestamp.now()

            for month_date in months:
                month_key = month_date.strftime('%B %Y')
                is_past = month_date < pd.Timestamp(today.year, today.month, 1)
                is_current = month_date == pd.Timestamp(today.year, today.month, 1)

                # Get actuals and projected for this month
                month_actual = 0
                month_projected = 0

                if month_key in metrics.get('actuals', {}):
                    for entity_data in metrics['actuals'][month_key].values():
                        month_actual += entity_data.get('revenue', 0)

                if month_key in metrics.get('projected', {}):
                    for entity_data in metrics['projected'][month_key].values():
                        month_projected += entity_data.get('revenue', 0)

                monthly_data.append({
                    'month_date': month_date,
                    'month_label': month_date.strftime('%b %Y'),
                    'is_past': is_past,
                    'is_current': is_current,
                    'is_future': not is_past and not is_current,
                    'actual_cost': month_actual,
                    'projected_cost': month_projected
                })

            # Display modification history table
            st.markdown("#### 📋 Contract Modification History")

            mod_display = modifications_df.copy()
            mod_display['mod_date'] = mod_display['mod_date'].dt.strftime('%Y-%m-%d')
            mod_display['ceiling'] = mod_display['ceiling'].apply(lambda x: f"${x:,.0f}")
            mod_display['increase'] = modifications_df['ceiling'].diff().fillna(modifications_df['ceiling'].iloc[0])
            mod_display['increase'] = mod_display['increase'].apply(lambda x: f"+${x:,.0f}" if x > 0 else f"${x:,.0f}")

            st.dataframe(
                mod_display[['mod_number', 'mod_date', 'ceiling', 'increase']],
                column_config={
                    'mod_number': 'Modification',
                    'mod_date': 'Effective Date',
                    'ceiling': 'Contract Ceiling',
                    'increase': 'Funding Added'
                },
                hide_index=True,
                width='content'
            )

            st.divider()

            # Create the enhanced Budget Trajectory chart
            st.markdown("#### 📈 Budget Trajectory with Stepped Modifications")

            months_labels = [m['month_label'] for m in monthly_data]

            # Calculate stepped budget and target zones
            budget_stepped = create_stepped_budget_line(months_labels, modifications_df)
            threshold = 10.0  # 10% threshold for demo
            upper_bounds, lower_bounds = create_stepped_target_boundaries(months_labels, modifications_df, threshold)

            # Calculate cumulative costs as percentages
            actual_pcts, projected_pcts = calculate_cumulative_costs_as_percentages(monthly_data, modifications_df)

            # Convert budget values to percentages (100% of applicable budget)
            budget_pcts = [100] * len(months_labels)
            upper_pcts = [100 + threshold] * len(months_labels)
            lower_pcts = [100 - threshold] * len(months_labels)

            # Create figure
            fig = go.Figure()

            # Target zone (shaded area) - now stepped
            fig.add_trace(go.Scatter(
                x=months_labels + months_labels[::-1],
                y=upper_pcts + lower_pcts[::-1],
                fill='toself',
                fillcolor='rgba(40, 167, 69, 0.2)',
                line=dict(width=0),
                name=f'Target Zone (±{threshold:.0f}%)',
                hoverinfo='skip'
            ))

            # Budget baseline (100%)
            fig.add_trace(go.Scatter(
                x=months_labels,
                y=budget_pcts,
                name='Budget Baseline (100%)',
                line=dict(color='#28a745', width=3, shape='hv'),  # shape='hv' creates steps
                hovertemplate='%{x}<br>Budget: 100%<br>($%{customdata:,.0f})<extra></extra>',
                customdata=budget_stepped
            ))

            # Upper target boundary
            fig.add_trace(go.Scatter(
                x=months_labels,
                y=upper_pcts,
                name=f'Upper Target ({100 + threshold:.0f}%)',
                line=dict(color='#28a745', width=1, dash='dot', shape='hv'),
                hovertemplate='%{x}<br>Upper: ' + f'{100 + threshold:.0f}%<br>($%{{customdata:,.0f}})<extra></extra>',
                customdata=upper_bounds
            ))

            # Lower target boundary
            fig.add_trace(go.Scatter(
                x=months_labels,
                y=lower_pcts,
                name=f'Lower Target ({100 - threshold:.0f}%)',
                line=dict(color='#28a745', width=1, dash='dot', shape='hv'),
                hovertemplate='%{x}<br>Lower: ' + f'{100 - threshold:.0f}%<br>($%{{customdata:,.0f}})<extra></extra>',
                customdata=lower_bounds
            ))

            # Actual cumulative (past months only)
            fig.add_trace(go.Scatter(
                x=months_labels,
                y=actual_pcts,
                name='Actual (Past)',
                line=dict(color='#007bff', width=3),
                mode='lines+markers',
                marker=dict(size=6),
                hovertemplate='%{x}<br>Actual: %{y:.1f}%<extra></extra>'
            ))

            # Projected trajectory
            fig.add_trace(go.Scatter(
                x=months_labels,
                y=projected_pcts,
                name='Projected Trajectory',
                line=dict(color='#fd7e14', width=3),
                mode='lines',
                hovertemplate='%{x}<br>Projected: %{y:.1f}%<extra></extra>'
            ))

            # Add vertical lines at modification dates
            for _, mod in modifications_df.iterrows():
                mod_label = mod['mod_date'].strftime('%b %Y')
                if mod_label in months_labels:
                    # Find the index position of this month
                    x_position = months_labels.index(mod_label)
                    fig.add_vline(
                        x=x_position,
                        line=dict(color='gray', width=1, dash='dash'),
                        annotation_text=mod['mod_number'],
                        annotation_position='top'
                    )

            # Layout
            fig.update_layout(
                title="Budget Utilization Over Time (with Stepped Modifications)",
                xaxis_title="Month",
                yaxis_title="Cumulative Budget Utilization (%)",
                hovermode='x unified',
                height=600,
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )

            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')

            st.plotly_chart(fig, use_container_width=True)

            # Explanation
            st.markdown("#### 🔍 Chart Explanation")
            st.markdown("""
            **Key Features:**
            - **Green Stepped Line (100%)**: Shows the budget baseline as it increases with each modification
            - **Green Shaded Area**: Target zone (±10%) that steps up as budget increases
            - **Blue Line**: Actual costs from time entries (past months only)
            - **Orange Line**: Projected costs based on current team allocations
            - **Vertical Dashed Lines**: Mark the effective dates of contract modifications

            **Why This Matters:**
            For long-running projects with incremental funding, this visualization shows:
            1. How budget utilization percentage resets/adjusts when new funding is added
            2. Whether the project is staying within the target zone relative to the applicable budget
            3. The cumulative effect of actual spending vs. the growing budget ceiling
            """)

            # Summary metrics
            st.divider()
            st.markdown("#### 📊 Summary Metrics")

            col1, col2, col3, col4 = st.columns(4)

            # Calculate totals
            total_actual = sum([m.get('actual_cost', 0) for m in monthly_data if m['is_past'] or m['is_current']])
            total_projected = sum([m.get('projected_cost', 0) for m in monthly_data])
            current_ceiling = modifications_df['ceiling'].iloc[-1]
            total_funding_added = modifications_df['ceiling'].iloc[-1] - modifications_df['ceiling'].iloc[0]

            with col1:
                st.metric("Total Actual Costs", f"${total_actual:,.0f}")

            with col2:
                st.metric("Total Projected Costs", f"${total_projected:,.0f}")

            with col3:
                st.metric("Current Budget Ceiling", f"${current_ceiling:,.0f}")

            with col4:
                st.metric("Total Funding Added", f"${total_funding_added:,.0f}")

    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        logger.error(f"Error in budget mockup: {str(e)}", exc_info=True)
        st.info("Please check the logs for details.")


if __name__ == "__main__":
    render_budget_mockup()
else:
    render_budget_mockup()
