"""
Budget Allocation Planner Component

Interactive tool for project managers to optimize team allocations
to achieve target budget utilization (±10%) for Time & Materials projects.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from typing import Dict, List, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)


def show_allocation_planner(project, db_manager, processor):
    """Display the Budget Allocation Planner for optimizing team allocations"""

    st.markdown("### 📊 Budget Allocation Planner")
    st.markdown("*Interactive tool to optimize allocations and achieve target budget utilization*")

    # Check if project has required data
    if pd.isna(project['start_date']) or pd.isna(project['end_date']):
        st.warning("⚠️ **Project dates required** - Please set start and end dates in the Edit Project tab.")
        return

    if pd.isna(project['contract_value']) or project['contract_value'] == 0:
        st.warning("⚠️ **Contract value required** - Please set a contract value in the Edit Project tab.")
        return

    # Load data
    allocations_df = db_manager.get_allocations(project_id=project['id'])
    time_entries_df = db_manager.get_time_entries(project_id=project['id'])

    if allocations_df.empty:
        st.warning("⚠️ **No allocations found** - Please add team allocations in the Team tab first.")
        return

    # Initialize session state for allocation adjustments
    if 'allocation_planner_adjustments' not in st.session_state:
        st.session_state.allocation_planner_adjustments = {}

    if 'allocation_planner_project_id' not in st.session_state or \
       st.session_state.allocation_planner_project_id != project['id']:
        st.session_state.allocation_planner_adjustments = {}
        st.session_state.allocation_planner_project_id = project['id']

    # Calculate current status and projections
    budget_analysis = analyze_budget_status(
        project,
        allocations_df,
        time_entries_df,
        processor,
        db_manager
    )

    # 1. Budget Health Dashboard
    display_budget_health_dashboard(budget_analysis, project)

    st.divider()

    # 2. Trajectory Visualization
    display_trajectory_visualization(budget_analysis, project)

    st.divider()

    # 3. Interactive Allocation Planner
    display_interactive_allocation_table(budget_analysis, project, allocations_df, processor, db_manager)

    st.divider()

    # 4. Scenario Analysis
    display_scenario_analysis(budget_analysis, project, allocations_df, processor, db_manager)

    st.divider()

    # 5. Smart Recommendations
    display_smart_recommendations(budget_analysis, project)


def analyze_budget_status(project, allocations_df, time_entries_df, processor, db_manager):
    """
    Analyze current budget status and calculate projections.

    Returns dict with:
    - budget_total: Total contract value
    - budget_spent: Actual cost to date
    - budget_projected: Projected total cost (actuals + remaining based on current allocations)
    - timeline_elapsed_pct: % of timeline that has elapsed
    - budget_utilized_pct: % of budget currently spent
    - projected_final_pct: Projected final % of budget utilization
    - monthly_data: List of dicts with monthly breakdown
    - target_threshold: Custom threshold for large projects
    - health_status: 'healthy', 'warning', 'critical'
    """

    budget_total = project['contract_value'] if pd.notna(project['contract_value']) else 0

    # Calculate timeline metrics
    start_date = pd.to_datetime(project['start_date'])
    end_date = pd.to_datetime(project['end_date'])
    today = pd.Timestamp.now()

    total_days = (end_date - start_date).days
    elapsed_days = (today - start_date).days if today >= start_date else 0
    timeline_elapsed_pct = (elapsed_days / total_days * 100) if total_days > 0 else 0
    timeline_elapsed_pct = min(max(timeline_elapsed_pct, 0), 100)  # Clamp to 0-100%

    # Get performance metrics for actual costs
    try:
        metrics = processor.get_performance_metrics(
            start_date=project['start_date'],
            end_date=project['end_date'],
            constraint={'project_id': str(project['id'])}
        )

        # Sum actual revenue (which is cost for T&M projects)
        budget_spent = 0
        for month_data in metrics.get('actuals', {}).values():
            for entity_data in month_data.values():
                budget_spent += entity_data.get('revenue', 0)

        # Sum projected revenue
        budget_projected_remaining = 0
        for month_data in metrics.get('projected', {}).values():
            for entity_data in month_data.values():
                budget_projected_remaining += entity_data.get('revenue', 0)

        budget_projected = budget_spent + budget_projected_remaining

    except Exception as e:
        logger.error(f"Error calculating budget metrics: {e}")
        budget_spent = project.get('budget_used', 0)
        budget_projected = budget_spent

    # Calculate percentages
    budget_utilized_pct = (budget_spent / budget_total * 100) if budget_total > 0 else 0
    projected_final_pct = (budget_projected / budget_total * 100) if budget_total > 0 else 0

    # Determine target threshold based on project size
    if budget_total >= 1000000:
        # Large projects (>=$1M): use 5% threshold
        target_threshold = 5.0
    elif budget_total >= 500000:
        # Medium-large projects ($500K-$1M): use 7.5% threshold
        target_threshold = 7.5
    else:
        # Standard projects: use 10% threshold
        target_threshold = 10.0

    # Determine health status
    if 90 - target_threshold <= projected_final_pct <= 100 + target_threshold:
        health_status = 'healthy'
    elif 80 - target_threshold <= projected_final_pct <= 100 + target_threshold * 1.5:
        health_status = 'warning'
    else:
        health_status = 'critical'

    # Build monthly data for visualization
    months = pd.date_range(
        start=start_date.replace(day=1),
        end=end_date + pd.DateOffset(months=1),
        freq='MS'
    )[:-1]

    monthly_data = []
    cumulative_actual = 0
    cumulative_projected = 0

    for month_date in months:
        month_key = month_date.strftime('%B %Y')
        is_past = month_date < pd.Timestamp(today.year, today.month, 1)
        is_current = month_date == pd.Timestamp(today.year, today.month, 1)

        # Get actuals and projected for this month
        month_actual = 0
        month_projected = 0

        try:
            if month_key in metrics.get('actuals', {}):
                for entity_data in metrics['actuals'][month_key].values():
                    month_actual += entity_data.get('revenue', 0)

            if month_key in metrics.get('projected', {}):
                for entity_data in metrics['projected'][month_key].values():
                    month_projected += entity_data.get('revenue', 0)
        except:
            pass

        cumulative_actual += month_actual
        cumulative_projected += month_projected

        monthly_data.append({
            'month': month_date,
            'month_label': month_date.strftime('%b %Y'),
            'is_past': is_past,
            'is_current': is_current,
            'is_future': not is_past and not is_current,
            'actual_cost': month_actual,
            'projected_cost': month_projected,
            'cumulative_actual': cumulative_actual,
            'cumulative_projected': cumulative_actual + month_projected,
            'cumulative_pct_actual': (cumulative_actual / budget_total * 100) if budget_total > 0 else 0,
            'cumulative_pct_projected': ((cumulative_actual + month_projected) / budget_total * 100) if budget_total > 0 else 0
        })

    return {
        'budget_total': budget_total,
        'budget_spent': budget_spent,
        'budget_projected': budget_projected,
        'timeline_elapsed_pct': timeline_elapsed_pct,
        'budget_utilized_pct': budget_utilized_pct,
        'projected_final_pct': projected_final_pct,
        'monthly_data': monthly_data,
        'target_threshold': target_threshold,
        'health_status': health_status,
        'start_date': start_date,
        'end_date': end_date,
        'today': today
    }


def display_budget_health_dashboard(budget_analysis, project):
    """Display the budget health dashboard with current status and projections"""

    st.markdown("#### 🎯 Budget Health Dashboard")

    col1, col2, col3, col4 = st.columns(4)

    # Current Status Card
    with col1:
        timeline_pct = budget_analysis['timeline_elapsed_pct']
        budget_pct = budget_analysis['budget_utilized_pct']

        delta_vs_timeline = budget_pct - timeline_pct
        delta_label = f"{delta_vs_timeline:+.1f}% vs timeline"

        st.metric(
            "Current Status",
            f"{budget_pct:.1f}% spent",
            delta=delta_label,
            delta_color="inverse" if delta_vs_timeline > 5 else ("normal" if delta_vs_timeline < -5 else "off"),
            help=f"{timeline_pct:.1f}% of timeline elapsed"
        )

        # Progress bar
        st.progress(min(budget_pct / 100, 1.0))
        st.caption(f"Timeline: {timeline_pct:.1f}% elapsed")

    # Projected Outcome Card
    with col2:
        projected_pct = budget_analysis['projected_final_pct']
        variance_from_100 = projected_pct - 100

        st.metric(
            "Projected Outcome",
            f"{projected_pct:.1f}%",
            delta=f"{variance_from_100:+.1f}% vs budget",
            delta_color="inverse" if variance_from_100 > 0 else "normal",
            help="Projected final budget utilization at current trajectory"
        )

        # Show actual and projected costs
        st.caption(f"${budget_analysis['budget_spent']:,.0f} spent + ${budget_analysis['budget_projected'] - budget_analysis['budget_spent']:,.0f} projected")

    # Target Zone Indicator
    with col3:
        threshold = budget_analysis['target_threshold']
        target_min = 100 - threshold
        target_max = 100 + threshold

        st.markdown(f"**Target Zone**")
        st.markdown(f"<div style='text-align: center; font-size: 24px; font-weight: bold;'>{target_min:.0f}% - {target_max:.0f}%</div>", unsafe_allow_html=True)

        # Gauge visualization
        projected_pct = budget_analysis['projected_final_pct']
        if target_min <= projected_pct <= target_max:
            gauge_color = "#28a745"  # Green
            gauge_emoji = "✅"
        elif target_min - threshold <= projected_pct <= target_max + threshold:
            gauge_color = "#ffc107"  # Yellow
            gauge_emoji = "⚠️"
        else:
            gauge_color = "#dc3545"  # Red
            gauge_emoji = "🔴"

        st.markdown(
            f"<div style='text-align: center; font-size: 32px;'>{gauge_emoji}</div>",
            unsafe_allow_html=True
        )

        st.caption(f"Threshold: ±{threshold:.1f}% for ${budget_analysis['budget_total']:,.0f} project")

    # Health Score
    with col4:
        health_status = budget_analysis['health_status']
        projected_pct = budget_analysis['projected_final_pct']

        if health_status == 'healthy':
            status_emoji = "🟢"
            status_text = "On Target"
            status_color = "#28a745"
            status_message = "Project is tracking within target zone"
        elif health_status == 'warning':
            status_emoji = "🟡"
            status_text = "Needs Attention"
            status_color = "#ffc107"
            if projected_pct < 90:
                status_message = "Risk of under-burning budget"
            else:
                status_message = "Risk of exceeding budget"
        else:
            status_emoji = "🔴"
            status_text = "Critical"
            status_color = "#dc3545"
            if projected_pct < 80:
                status_message = "Significant under-burn expected"
            else:
                status_message = "Budget overrun expected"

        st.markdown(f"**Health Score**")
        st.markdown(
            f"<div style='text-align: center; background-color: {status_color}22; padding: 15px; border-radius: 10px; border: 2px solid {status_color};'>"
            f"<div style='font-size: 32px;'>{status_emoji}</div>"
            f"<div style='font-size: 18px; font-weight: bold; color: {status_color};'>{status_text}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
        st.caption(status_message)


def display_trajectory_visualization(budget_analysis, project):
    """Display trajectory chart showing budget baseline, target zone, and projections"""

    st.markdown("#### 📈 Budget Trajectory")

    monthly_data = budget_analysis['monthly_data']
    budget_total = budget_analysis['budget_total']
    threshold = budget_analysis['target_threshold']

    # Create figure
    fig = go.Figure()

    # Extract data for plotting
    months = [m['month_label'] for m in monthly_data]
    cumulative_pct = [m['cumulative_pct_projected'] for m in monthly_data]
    cumulative_actual_pct = [m['cumulative_pct_actual'] if m['is_past'] or m['is_current'] else None for m in monthly_data]

    # Budget baseline (100%)
    fig.add_trace(go.Scatter(
        x=months,
        y=[100] * len(months),
        name='Budget Baseline (100%)',
        line=dict(color='#6c757d', width=2, dash='dash'),
        hovertemplate='%{x}<br>Budget: 100%<extra></extra>'
    ))

    # Target zone (shaded area)
    fig.add_trace(go.Scatter(
        x=months + months[::-1],
        y=[100 + threshold] * len(months) + [100 - threshold] * len(months),
        fill='toself',
        fillcolor='rgba(40, 167, 69, 0.2)',
        line=dict(width=0),
        name=f'Target Zone (±{threshold:.0f}%)',
        hoverinfo='skip'
    ))

    # Target zone boundaries
    fig.add_trace(go.Scatter(
        x=months,
        y=[100 + threshold] * len(months),
        name=f'Upper Target ({100 + threshold:.0f}%)',
        line=dict(color='#28a745', width=1, dash='dot'),
        hovertemplate='%{x}<br>Upper: ' + f'{100 + threshold:.1f}%<extra></extra>'
    ))

    fig.add_trace(go.Scatter(
        x=months,
        y=[100 - threshold] * len(months),
        name=f'Lower Target ({100 - threshold:.0f}%)',
        line=dict(color='#28a745', width=1, dash='dot'),
        hovertemplate='%{x}<br>Lower: ' + f'{100 - threshold:.1f}%<extra></extra>'
    ))

    # Actual cumulative (past months only)
    fig.add_trace(go.Scatter(
        x=months,
        y=cumulative_actual_pct,
        name='Actual (Past)',
        line=dict(color='#007bff', width=3),
        mode='lines+markers',
        marker=dict(size=8),
        hovertemplate='%{x}<br>Actual: %{y:.1f}%<extra></extra>'
    ))

    # Projected trajectory (current trajectory based on current allocations)
    fig.add_trace(go.Scatter(
        x=months,
        y=cumulative_pct,
        name='Current Trajectory',
        line=dict(color='#fd7e14', width=3),
        mode='lines',
        hovertemplate='%{x}<br>Projected: %{y:.1f}%<extra></extra>'
    ))

    # Layout
    fig.update_layout(
        title="Budget Utilization Over Time",
        xaxis_title="Month",
        yaxis_title="Cumulative Budget Utilization (%)",
        hovermode='x unified',
        height=450,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    # Add markers for past vs future
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')

    st.plotly_chart(fig, use_container_width=True)

    # Legend explanation
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("📊 **Past months**: Solid blue line (actuals) | **Future months**: Orange line (projected based on current allocations)")
    with col2:
        if budget_analysis['health_status'] == 'healthy':
            st.success("✅ On track")
        elif budget_analysis['health_status'] == 'warning':
            st.warning("⚠️ Attention needed")
        else:
            st.error("🔴 Critical")


def display_interactive_allocation_table(budget_analysis, project, allocations_df, processor, db_manager):
    """Display interactive table for adjusting future allocations"""

    st.markdown("#### ✏️ Allocation Adjustments (Future Months Only)")
    st.caption("*Adjust FTE allocations for upcoming months to optimize budget utilization. Past months are locked.*")

    # Filter to future months only
    future_months = [m for m in budget_analysis['monthly_data'] if m['is_future']]

    if not future_months:
        st.info("No future months to plan. Project timeline has ended or only current month remains.")
        return

    st.markdown(f"**{len(future_months)} month(s) remaining** in project timeline")

    # Build table data (placeholder for now - will implement full functionality)
    table_data = []

    for month_data in future_months:
        month_key = month_data['month'].strftime('%Y-%m-%d')
        month_label = month_data['month_label']

        # Get current allocations for this month
        month_allocs = allocations_df[
            pd.to_datetime(allocations_df['allocation_date']) == month_data['month']
        ]

        if not month_allocs.empty:
            current_fte = month_allocs['allocated_fte'].sum()
            projected_hours = month_data['projected_cost'] / 150 if month_data['projected_cost'] > 0 else 0  # Rough estimate
        else:
            current_fte = 0
            projected_hours = 0

        table_data.append({
            'Month': month_label,
            'Current FTE': current_fte,
            'Projected Hours': projected_hours,
            'Projected Cost': month_data['projected_cost'],
            'Status': '⏳ Future'
        })

    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(
            df,
            column_config={
                'Month': st.column_config.TextColumn('Month', width='medium'),
                'Current FTE': st.column_config.NumberColumn('Current FTE', format='%.2f', width='small'),
                'Projected Hours': st.column_config.NumberColumn('Projected Hours', format='%.0f', width='small'),
                'Projected Cost': st.column_config.NumberColumn('Projected Cost', format='$%.0f', width='medium'),
                'Status': st.column_config.TextColumn('Status', width='small')
            },
            use_container_width=True,
            hide_index=True
        )

    st.info("🚧 **Coming in next update**: Interactive sliders to adjust FTE allocations with real-time impact calculations")


def display_scenario_analysis(budget_analysis, project, allocations_df, processor, db_manager):
    """Display scenario comparison and quick actions"""

    st.markdown("#### 🎭 Scenario Analysis")
    st.caption("*Compare different allocation strategies to find the optimal approach*")

    projected_final = budget_analysis['projected_final_pct']
    threshold = budget_analysis['target_threshold']

    scenarios = [
        {
            'name': 'Current Plan',
            'description': 'Continue with existing allocations',
            'final_pct': projected_final,
            'status': '📍 Current'
        },
        {
            'name': 'Conservative',
            'description': f'Target {100 - threshold:.0f}% utilization (avoid overrun)',
            'final_pct': 100 - threshold,
            'status': '🛡️ Safe'
        },
        {
            'name': 'Optimal',
            'description': 'Target 97-100% utilization (maximize value)',
            'final_pct': 98.5,
            'status': '🎯 Recommended'
        },
        {
            'name': 'Aggressive',
            'description': f'Target {100 + threshold:.0f}% utilization (full budget)',
            'final_pct': 100 + threshold,
            'status': '⚡ Risky'
        }
    ]

    scenario_df = pd.DataFrame(scenarios)

    st.dataframe(
        scenario_df,
        column_config={
            'name': st.column_config.TextColumn('Scenario', width='medium'),
            'description': st.column_config.TextColumn('Description', width='large'),
            'final_pct': st.column_config.NumberColumn('Target %', format='%.1f%%', width='small'),
            'status': st.column_config.TextColumn('Status', width='small')
        },
        use_container_width=True,
        hide_index=True
    )

    st.info("🚧 **Coming in next update**: Calculate specific allocation adjustments needed for each scenario")


def display_smart_recommendations(budget_analysis, project):
    """Display smart recommendations based on current trajectory"""

    st.markdown("#### 💡 Smart Recommendations")

    projected_pct = budget_analysis['projected_final_pct']
    threshold = budget_analysis['target_threshold']
    health_status = budget_analysis['health_status']
    budget_total = budget_analysis['budget_total']

    if health_status == 'healthy':
        st.success(
            f"✅ **On Track** - Current trajectory ({projected_pct:.1f}%) is within target zone "
            f"({100 - threshold:.0f}%-{100 + threshold:.0f}%). Continue monitoring monthly progress."
        )
    elif projected_pct < 100 - threshold:
        # Under-burning
        variance = 100 - projected_pct
        money_left = budget_total * (variance / 100)

        st.warning(
            f"⚠️ **Under-Burning Risk** - Projected to finish at {projected_pct:.1f}% of budget. "
            f"This leaves approximately **${money_left:,.0f}** unspent.\n\n"
            f"**Recommendations:**\n"
            f"- Consider increasing team allocation by 0.2-0.5 FTE for remaining months\n"
            f"- Add scope or extend deliverables to utilize full budget\n"
            f"- Review if all planned work is allocated correctly"
        )
    elif projected_pct > 100 + threshold:
        # Over-burning
        variance = projected_pct - 100
        money_over = budget_total * (variance / 100)

        st.error(
            f"🔴 **Budget Overrun Risk** - Projected to exceed budget by {variance:.1f}% "
            f"(approximately **${money_over:,.0f}**).\n\n"
            f"**Recommendations:**\n"
            f"- Reduce team allocation by 0.2-0.5 FTE for remaining months\n"
            f"- Identify tasks that can be descoped or delayed\n"
            f"- Consider requesting budget increase if scope is fixed\n"
            f"- Review if there are efficiency gains to be made"
        )

    # Large project specific guidance
    if budget_total >= 1000000:
        variance_amount = budget_total * (threshold / 100)
        st.info(
            f"💼 **Large Project Alert** - This ${budget_total:,.0f} project uses ±{threshold:.1f}% threshold. "
            f"Even at this threshold, variance can be ±${variance_amount:,.0f}. "
            f"Consider tighter controls and more frequent reviews."
        )
