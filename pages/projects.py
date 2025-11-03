import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime
from components.burn_rate_editor import show_burn_rate_editor
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 🚀 Project Management")

# Tabs for different views
tab1, tab2, tab3, tab4 = st.tabs(["Project List", "Project Details", "Edit Project", "Project Analytics"])

with tab1:
    # Load projects
    projects_df = db.get_projects()

    if not projects_df.empty:
        # Display options
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("#### All Projects")
        with col2:
            view_mode = st.selectbox("View", ["Table", "Cards"], label_visibility="collapsed")

        if view_mode == "Table":
            # Table view
            display_df = projects_df[[
                'name', 'client', 'status', 'project_manager',
                'start_date', 'end_date', 'budget_allocated', 'budget_used',
                'revenue_projected', 'revenue_actual'
            ]].copy()

            # Format currency columns
            for col in ['budget_allocated', 'budget_used', 'revenue_projected', 'revenue_actual']:
                display_df[col] = display_df[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "-")

            st.dataframe(display_df, width='stretch', hide_index=True)

        else:
            # Card view
            cols = st.columns(3)
            for idx, (_, project) in enumerate(projects_df.iterrows()):
                with cols[idx % 3]:
                    with st.container():
                        # Status color
                        status_color = {
                            'Active': '🟢',
                            'Completed': '🔵',
                            'On Hold': '🟡',
                            'Cancelled': '🔴'
                        }.get(project['status'], '⚪')

                        st.markdown(f"### {status_color} {project['name']}")
                        st.write(f"**Client:** {project['client']}")
                        st.write(f"**PM:** {project['project_manager']}")
                        st.write(f"**Status:** {project['status']}")

                        # Progress bars
                        if project['budget_allocated']:
                            budget_used_pct = (project['budget_used'] / project['budget_allocated'] * 100)
                            st.progress(min(budget_used_pct / 100, 1.0))
                            st.caption(f"Budget: ${project['budget_used']:,.0f} / ${project['budget_allocated']:,.0f}")

                        if project['revenue_projected']:
                            revenue_pct = (project['revenue_actual'] / project['revenue_projected'] * 100)
                            st.progress(min(revenue_pct / 100, 1.0))
                            st.caption(f"Revenue: ${project['revenue_actual']:,.0f} / ${project['revenue_projected']:,.0f}")

                        st.write(f"**Duration:** {project['start_date']} to {project['end_date']}")
                        st.markdown("---")
    else:
        st.info("No projects found with current filters")

with tab2:
    # Project details view
    projects_df = db.get_projects()

    if not projects_df.empty:
        selected_project = st.selectbox(
            "Select Project",
            options=projects_df['name'].tolist(),
            index=5,
        )

        if selected_project:
            project = projects_df[projects_df['name'] == selected_project].iloc[0]
            project_id = project['id']

            # Check allocation coverage
            allocations_df = db.get_allocations(project_id=project_id)
            if not allocations_df.empty and 'allocation_date' in allocations_df.columns:
                try:
                    project_start = pd.to_datetime(project['start_date'])
                    project_end = pd.to_datetime(project['end_date'])
                    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
                    first_allocation = allocations_df['allocation_date'].min()
                    last_allocation = allocations_df['allocation_date'].max()

                    # Calculate gaps in days
                    gap_before = (first_allocation - project_start).days if first_allocation > project_start else 0
                    gap_after = (project_end - last_allocation).days if last_allocation < project_end else 0

                    if gap_before > 0 or gap_after > 0:
                        # Calculate approximate months (30 days = 1 month)
                        months_before = gap_before // 30
                        months_after = gap_after // 30

                        # Build warning message
                        warning_msg = f"⚠️ **Incomplete Allocation Coverage** — "
                        warning_msg += f"Project runs **{project_start.strftime('%b %Y')}** to **{project_end.strftime('%b %Y')}**, "
                        warning_msg += f"but allocation data only exists for **{first_allocation.strftime('%b %Y')}** to **{last_allocation.strftime('%b %Y')}**. "

                        gaps = []
                        if months_before > 0:
                            gaps.append(f"{months_before} month(s) at start")
                        if months_after > 0:
                            gaps.append(f"{months_after} month(s) at end")

                        warning_msg += f"Missing: {' and '.join(gaps)}. "
                        warning_msg += "This will affect Monthly Breakdown table and projected revenue calculations."

                        st.warning(warning_msg)
                except (ValueError, TypeError):
                    # Skip if dates can't be parsed
                    pass
            elif allocations_df.empty:
                st.warning("⚠️ **No allocations found** for this project. Add team allocations to enable projected revenue calculations.")

            # Project header
            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                st.markdown(f"## {project['name']}")
                st.write(project['description'])

                project_deets = {
                    "Status": project['status'],
                    "Project ID": project['id'],
                    "Client": project['client'],
                    "Project Manager": project['project_manager'],
                    "Project Start": project['start_date'],
                    "Project End": project['end_date']
                }
                st.table(project_deets, border="horizontal")

            with col2:
                # Calculate Revenue Projected vs. Actual
                budget = project['budget_allocated']

                # Get actual accrued revenue from time_entries
                time_entries = db.get_time_entries(project_id=project_id)
                if not time_entries.empty:
                    # Calculate revenue using amount if available, otherwise hours × bill_rate
                    def calculate_entry_revenue(row):
                        if pd.notna(row.get('amount')) and row['amount'] != 0:
                            return row['amount']
                        elif pd.notna(row.get('bill_rate')):
                            return row['hours'] * row['bill_rate']
                        else:
                            return 0

                    time_entries['revenue'] = time_entries.apply(calculate_entry_revenue, axis=1)
                    total_accrued = time_entries['revenue'].sum()
                else:
                    total_accrued = 0

                budget_remaining = budget - total_accrued
                st.metric("Budget Allocated", f"${budget:,.0f}")
                st.metric("Total Accrued to Date", f"${total_accrued:,.0f}")
                st.metric("Budget Remaining", f"${budget_remaining:,.0f}")

            # Tabs for project details
            detail_tab1, detail_tab2, detail_tab3, detail_tab4, detail_tab5 = st.tabs(
                ["Performance", "Team", "Timeline", "Expenses", "Burn Rate"]
            )

            # Performance
            with detail_tab1:
                st.markdown("#### Project Performance Analysis")

                # Get performance metrics for project date range
                try:
                    with st.spinner("Loading project performance data..."):
                        metrics = processor.get_performance_metrics(
                            start_date=project['start_date'],
                            end_date=project['end_date'],
                            constraint={'project_id': str(project_id)}
                        )

                    # Helper function to aggregate metrics across all months and employees
                    def aggregate_monthly_data(metrics_dict):
                        """Aggregate metrics by month across all employees"""
                        monthly_totals = {}
                        for month, employees in metrics_dict.items():
                            total_hours = sum(emp_data['hours'] for emp_data in employees.values())
                            total_revenue = sum(emp_data['revenue'] for emp_data in employees.values())
                            monthly_totals[month] = {
                                'hours': total_hours,
                                'revenue': total_revenue
                            }
                        return monthly_totals

                    # Get months data for smart combination
                    months_df = db.get_months()

                    # Use smart combination logic
                    combined_data = processor.combine_actual_projected_smartly(
                        actuals_dict=metrics['actuals'],
                        projected_dict=metrics['projected'],
                        months_df=months_df
                    )

                    # Aggregate combined data
                    combined_monthly = aggregate_monthly_data(combined_data)

                    # Also keep separate aggregates for display purposes
                    actuals_monthly = aggregate_monthly_data(metrics['actuals'])
                    projected_monthly = aggregate_monthly_data(metrics['projected'])

                    # Calculate totals from smart combined data
                    total_combined_hours = sum(m['hours'] for m in combined_monthly.values())
                    total_combined_revenue = sum(m['revenue'] for m in combined_monthly.values())

                    # Calculate separate totals for display (actual from past, projected from future)
                    total_actual_hours = sum(m['hours'] for m in actuals_monthly.values())
                    total_actual_revenue = sum(m['revenue'] for m in actuals_monthly.values())

                    # Get budget from project
                    budget_revenue = project['budget_allocated'] if pd.notna(project['budget_allocated']) else 0

                    # Calculate burn percentages
                    revenue_burn_pct = (total_combined_revenue / budget_revenue * 100) if budget_revenue > 0 else 0
                    revenue_variance = total_combined_revenue - budget_revenue

                    # Determine status
                    if revenue_burn_pct > 100:
                        status = "🔴 Over Budget"
                        status_color = "#ffcccc"
                    elif revenue_burn_pct >= 90:
                        status = "🟡 Near Budget"
                        status_color = "#fff9cc"
                    elif revenue_burn_pct >= 80:
                        status = "🟢 On Track"
                        status_color = "#ccffcc"
                    else:
                        status = "🔵 Under Budget"
                        status_color = "#cce5ff"

                    # Display summary cards
                    st.markdown("##### Summary")
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric(
                            "Total Hours (Smart Combined)",
                            f"{total_combined_hours:,.0f} hrs",
                            delta=f"Actual: {total_actual_hours:,.0f}",
                            help="Intelligently combined hours: Past = actual only, Current = blended, Future = projected only"
                        )

                    with col2:
                        st.metric(
                            f"Total Accrued (Smart Combined)",
                            f"${total_combined_revenue:,.0f}",
                            delta=f"${revenue_variance:+,.0f} vs budget",
                            delta_color="inverse" if revenue_variance > 0 else "normal",
                            help="Intelligently combined revenue: Past = actual only, Current = blended, Future = projected only"
                        )

                    with col3:
                        st.markdown(
                            f"<div style='background-color: {status_color}; padding: 20px; border-radius: 5px; text-align: center;'>"
                            f"<h4>Budget Status</h4>"
                            f"<h2>{status}</h2>"
                            f"<p>{revenue_burn_pct:.1f}% of ${budget_revenue:,.0f}</p>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                    st.divider()

                    # Monthly breakdown table
                    st.markdown("##### Monthly Breakdown (Smart Combined)")

                    # Get all unique months from actuals, projected, and combined to include future months
                    all_months = sorted(
                        set(list(actuals_monthly.keys()) + list(projected_monthly.keys()) + list(combined_monthly.keys())),
                        key=lambda x: pd.to_datetime(x, format='%B %Y')
                    )

                    # Build monthly breakdown
                    monthly_data = []
                    cumulative_revenue = 0

                    # Month type icons
                    month_type_icons = {
                        'past': '📊',  # Past month - actual only
                        'active': '⚡',  # Active month - blended
                        'future': '📈'  # Future month - projected only
                    }

                    for month in all_months:
                        # Get smart combined data
                        combined_month = combined_monthly.get(month, {})
                        combined_hrs = combined_month.get('hours', 0)
                        combined_rev = combined_month.get('revenue', 0)

                        # Get month type from the combined data (check first entity)
                        month_type = 'past'  # default
                        if month in combined_data:
                            first_entity = list(combined_data[month].values())[0] if combined_data[month] else {}
                            month_type = first_entity.get('month_type', 'past')

                        # Get actual and projected for reference
                        actual_hrs = actuals_monthly.get(month, {}).get('hours', 0)
                        actual_rev = actuals_monthly.get(month, {}).get('revenue', 0)
                        proj_hrs = projected_monthly.get(month, {}).get('hours', 0)
                        proj_rev = projected_monthly.get(month, {}).get('revenue', 0)

                        cumulative_revenue += combined_rev

                        budget_pct = (cumulative_revenue / budget_revenue * 100) if budget_revenue > 0 else 0

                        # Determine budget status
                        if budget_pct > 100:
                            budget_status = "🔴"
                        elif budget_pct >= 90:
                            budget_status = "🟡"
                        elif budget_pct >= 80:
                            budget_status = "🟢"
                        else:
                            budget_status = "🔵"

                        # Get month type icon
                        type_icon = month_type_icons.get(month_type, '')

                        monthly_data.append({
                            'Type': type_icon,
                            'Month': month,
                            'Combined Hours': combined_hrs,
                            'Combined Revenue': combined_rev,
                            'Actual Hours': actual_hrs,
                            'Actual Revenue': actual_rev,
                            'Projected Hours': proj_hrs,
                            'Projected Revenue': proj_rev,
                            'Cumulative Revenue': cumulative_revenue,
                            'Budget %': budget_pct,
                            'Status': budget_status
                        })

                    monthly_df = pd.DataFrame(monthly_data)

                    # Format display
                    display_df = monthly_df.copy()
                    display_df['Combined Hours'] = display_df['Combined Hours'].apply(lambda x: f"{x:,.0f}")
                    display_df['Combined Revenue'] = display_df['Combined Revenue'].apply(lambda x: f"${x:,.0f}")
                    display_df['Actual Hours'] = display_df['Actual Hours'].apply(lambda x: f"{x:,.0f}")
                    display_df['Actual Revenue'] = display_df['Actual Revenue'].apply(lambda x: f"${x:,.0f}")
                    display_df['Projected Hours'] = display_df['Projected Hours'].apply(lambda x: f"{x:,.0f}")
                    display_df['Projected Revenue'] = display_df['Projected Revenue'].apply(lambda x: f"${x:,.0f}")
                    display_df['Cumulative Revenue'] = display_df['Cumulative Revenue'].apply(lambda x: f"${x:,.0f}")
                    display_df['Budget %'] = display_df['Budget %'].apply(lambda x: f"{x:.1f}%")

                    # Add legend for icons
                    st.info("📊 = Past (Actual only) | ⚡ = Active/Current (Blended) | 📈 = Future (Projected only)")

                    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

                    # Burn rate visualization
                    st.divider()
                    st.markdown("##### Burn Rate Visualization")

                    col1, col2 = st.columns(2)

                    with col1:
                        # Cumulative revenue vs budget chart
                        fig = go.Figure()

                        fig.add_trace(go.Scatter(
                            x=monthly_df['Month'],
                            y=monthly_df['Cumulative Revenue'],
                            name='Cumulative Revenue',
                            mode='lines+markers',
                            line=dict(color='#2E86C1', width=3),
                            fill='tozeroy'
                        ))

                        fig.add_trace(go.Scatter(
                            x=monthly_df['Month'],
                            y=[budget_revenue] * len(monthly_df),
                            name='Budget',
                            mode='lines',
                            line=dict(color='red', width=2, dash='dash')
                        ))

                        fig.update_layout(
                            title="Cumulative Revenue vs Budget (Smart Combined)",
                            xaxis_title="Month",
                            yaxis_title="Revenue ($)",
                            height=400,
                            hovermode='x unified'
                        )

                        st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        # Monthly hours breakdown with color coding by month type
                        fig = go.Figure()

                        # Color code bars by month type
                        colors = []
                        for month in monthly_df['Month']:
                            month_type = 'past'
                            if month in combined_data:
                                first_entity = list(combined_data[month].values())[0] if combined_data[month] else {}
                                month_type = first_entity.get('month_type', 'past')

                            # Assign colors based on type
                            if month_type == 'past':
                                colors.append('#27AE60')  # Green for actual
                            elif month_type == 'active':
                                colors.append('#F39C12')  # Orange for blended
                            else:  # future
                                colors.append('#85C1E2')  # Blue for projected

                        fig.add_trace(go.Bar(
                            x=monthly_df['Month'],
                            y=monthly_df['Combined Hours'],
                            name='Combined Hours',
                            marker_color=colors,
                            text=monthly_df['Type'],
                            textposition='outside'
                        ))

                        fig.update_layout(
                            title="Hours by Month (Smart Combined)<br><sub>📊 Past | ⚡ Active | 📈 Future</sub>",
                            xaxis_title="Month",
                            yaxis_title="Hours",
                            height=400,
                            hovermode='x unified'
                        )

                        st.plotly_chart(fig, use_container_width=True)

                    # CSV Export
                    csv = monthly_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Monthly Breakdown",
                        data=csv,
                        file_name=f"project_performance_{project_id}_{project['start_date']}_{project['end_date']}.csv",
                        mime="text/csv"
                    )

                except Exception as e:
                    st.error(f"Error loading performance data: {str(e)}")
                    logger.error(f"Error in performance tab: {str(e)}", exc_info=True)
                    st.info("Unable to load performance metrics. Please check the logs for details.")

            # Team
            with detail_tab2:
                # Team allocation
                allocations_df = db.get_allocations(project_id=project_id)

                if not allocations_df.empty:
                    st.markdown("#### Team Members")

                    # Get time entries for this project to show actual hours
                    time_entries = db.get_time_entries(project_id=project_id)

                    # Process time entries to get monthly hours by employee
                    actual_hours_by_employee = {}
                    if not time_entries.empty:
                        time_entries['date'] = pd.to_datetime(time_entries['date'])
                        time_entries['month'] = time_entries['date'].dt.strftime('%Y-%m')

                        # Group by employee and month
                        for emp_id in time_entries['employee_id'].unique():
                            emp_time = time_entries[time_entries['employee_id'] == emp_id]
                            monthly_hours = emp_time.groupby('month')['hours'].sum().to_dict()
                            actual_hours_by_employee[emp_id] = monthly_hours

                    # Group by employee
                    for employee_name in allocations_df['employee_name'].unique():
                        emp_allocs = allocations_df[allocations_df['employee_name'] == employee_name]

                        st.markdown(f"**{employee_name}**")

                        # Get role (assuming it's consistent for the employee)
                        role = emp_allocs['role'].iloc[0] if pd.notna(emp_allocs['role'].iloc[0]) else 'N/A'
                        st.write(f"*Role: {role}*")

                        # Get employee_id for this employee
                        employee_id = emp_allocs['employee_id'].iloc[0]

                        # Check if we have allocation_date for monthly breakdown
                        if 'allocation_date' in emp_allocs.columns and emp_allocs['allocation_date'].notna().any():
                            # Create monthly allocation display with actual hours
                            monthly_data = []
                            for _, alloc in emp_allocs.iterrows():
                                if pd.notna(alloc.get('allocation_date')):
                                    month = pd.to_datetime(alloc['allocation_date']).strftime('%Y-%m')
                                    fte = alloc.get('allocated_fte', 0)

                                    # Get working days from months table
                                    alloc_date = pd.to_datetime(alloc['allocation_date'])
                                    months_df = db.get_months()
                                    month_info = months_df[
                                        (months_df['year'] == alloc_date.year) &
                                        (months_df['month'] == alloc_date.month)
                                    ]

                                    if not month_info.empty:
                                        working_days = month_info['working_days'].iloc[0]
                                        holidays = month_info['holidays'].iloc[0]
                                        allocated_hours = (working_days - holidays) * fte * 8
                                    else:
                                        # Fallback to 21 working days
                                        allocated_hours = 21 * fte * 8

                                    # Get actual hours for this month
                                    actual_hours = 0
                                    if employee_id in actual_hours_by_employee:
                                        actual_hours = actual_hours_by_employee[employee_id].get(month, 0)

                                    monthly_data.append({
                                        'Month': month,
                                        'FTE': f"{fte * 100:.0f}%",
                                        'Allocated Hours': f"{allocated_hours:,.0f}",
                                        'Actual Hours': f"{actual_hours:,.0f}" if actual_hours > 0 else "-",
                                        'Variance': f"{actual_hours - allocated_hours:+,.0f}" if actual_hours > 0 else "-"
                                    })

                            if monthly_data:
                                monthly_df = pd.DataFrame(monthly_data)
                                st.dataframe(monthly_df, hide_index=True, use_container_width=True)
                        else:
                            # Fallback to simple FTE display if no allocation_date
                            total_fte = emp_allocs['allocated_fte'].sum()
                            st.write(f"Total Allocation: {total_fte * 100:.0f}%")

                        st.markdown("---")

                    # Team allocation chart - show allocated vs actual hours
                    if 'allocation_date' in allocations_df.columns and allocations_df['allocation_date'].notna().any():
                        st.markdown("#### Allocated vs Actual Hours by Employee")

                        # Prepare data for comparison chart
                        chart_df = allocations_df.copy()
                        chart_df['month'] = pd.to_datetime(chart_df['allocation_date']).dt.strftime('%Y-%m')

                        # Calculate allocated hours for each row
                        months_df = db.get_months()
                        allocated_hours_list = []

                        for _, row in chart_df.iterrows():
                            alloc_date = pd.to_datetime(row['allocation_date'])
                            month_info = months_df[
                                (months_df['year'] == alloc_date.year) &
                                (months_df['month'] == alloc_date.month)
                            ]

                            if not month_info.empty:
                                working_days = month_info['working_days'].iloc[0]
                                holidays = month_info['holidays'].iloc[0]
                                allocated_hours = (working_days - holidays) * row['allocated_fte'] * 8
                            else:
                                allocated_hours = 21 * row['allocated_fte'] * 8

                            allocated_hours_list.append(allocated_hours)

                        chart_df['allocated_hours'] = allocated_hours_list

                        # Create comparison chart with two columns
                        col1, col2 = st.columns(2)

                        with col1:
                            # Bar chart: Allocated vs Actual by Employee-Month
                            fig = go.Figure()

                            # Get all unique months
                            all_months = sorted(chart_df['month'].unique())

                            for employee in chart_df['employee_name'].unique():
                                emp_chart_data = chart_df[chart_df['employee_name'] == employee]
                                employee_id = emp_chart_data['employee_id'].iloc[0]

                                # Get allocated hours
                                allocated_by_month = dict(zip(emp_chart_data['month'], emp_chart_data['allocated_hours']))

                                # Get actual hours
                                actual_by_month = {}
                                if employee_id in actual_hours_by_employee:
                                    actual_by_month = actual_hours_by_employee[employee_id]

                                # Create trace for allocated hours
                                fig.add_trace(go.Bar(
                                    name=f"{employee} - Allocated",
                                    x=list(allocated_by_month.keys()),
                                    y=list(allocated_by_month.values()),
                                    marker=dict(pattern=dict(shape="/")),
                                    legendgroup=employee,
                                    showlegend=True
                                ))

                                # Create trace for actual hours
                                actual_hours_values = [actual_by_month.get(m, 0) for m in allocated_by_month.keys()]
                                fig.add_trace(go.Bar(
                                    name=f"{employee} - Actual",
                                    x=list(allocated_by_month.keys()),
                                    y=actual_hours_values,
                                    legendgroup=employee,
                                    showlegend=True
                                ))

                            fig.update_layout(
                                title="Allocated vs Actual Hours by Month",
                                xaxis_title="Month",
                                yaxis_title="Hours",
                                barmode='group',
                                height=400
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        with col2:
                            # Line chart: Allocation % over time
                            fig2 = go.Figure()
                            for employee in chart_df['employee_name'].unique():
                                emp_data = chart_df[chart_df['employee_name'] == employee]
                                fig2.add_trace(go.Scatter(
                                    name=employee,
                                    x=emp_data['month'],
                                    y=emp_data['allocated_fte'] * 100,
                                    mode='lines+markers',
                                    line=dict(width=2),
                                    marker=dict(size=8)
                                ))

                            fig2.update_layout(
                                title="Team Allocation by Month (% FTE)",
                                xaxis_title="Month",
                                yaxis_title="Allocation %",
                                height=400
                            )
                            st.plotly_chart(fig2, use_container_width=True)
                    else:
                        # Fallback to simple bar chart
                        fig = go.Figure(data=[
                            go.Bar(
                                name='Allocated FTE',
                                x=allocations_df['employee_name'],
                                y=allocations_df['allocated_fte'] * 100
                            )
                        ])
                        fig.update_layout(
                            title="Team Allocation (% of Full-Time)",
                            yaxis_title="Allocation %",
                            height=400
                        )
                        st.plotly_chart(fig, width='stretch')
                else:
                    st.info("No team members allocated to this project")

            # Timeline
            with detail_tab3:
                # Timeline
                st.markdown("#### Project Timeline")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Start Date:** {project['start_date']}")
                with col2:
                    st.write(f"**End Date:** {project['end_date']}")
                with col3:
                    days_total = (pd.to_datetime(project['end_date']) - pd.to_datetime(project['start_date'])).days
                    st.write(f"**Duration:** {days_total} days")

                # Progress
                if project['status'] == 'Active':
                    today = pd.Timestamp.now()
                    start = pd.to_datetime(project['start_date'])
                    end = pd.to_datetime(project['end_date'])

                    # TODO: Fix this
                    if today >= start and today <= end:
                        days_elapsed = (today - start).days
                        progress = days_elapsed / days_total * 100
                        st.progress(min(progress / 100, 1.0))
                        st.caption(f"Timeline Progress: {progress:.1f}% ({days_elapsed}/{days_total} days)")
                    elif today < start:
                        st.info("Project not started yet")
                    else:
                        st.warning("Project past scheduled end date")

                # Time entries over time
                time_entries = db.get_time_entries(project_id=project_id)
                if not time_entries.empty:
                    time_entries['date'] = pd.to_datetime(time_entries['date'])
                    daily_hours = time_entries.groupby('date')['hours'].sum().reset_index()

                    fig = px.line(
                        daily_hours,
                        x='date',
                        y='hours',
                        title="Daily Hours Logged",
                        markers=True
                    )
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, width='stretch')

            # Expenses
            with detail_tab4:
                # Expenses
                expenses_df = db.get_expenses(project_id=project_id)

                if not expenses_df.empty:
                    st.markdown("#### Project Expenses")

                    # Summary by category
                    category_summary = expenses_df.groupby('category')['amount'].sum().reset_index()

                    col1, col2 = st.columns(2)

                    with col1:
                        st.dataframe(
                            category_summary.rename(columns={'amount': 'Total Amount'}),
                            width='stretch',
                            hide_index=True
                        )

                    with col2:
                        fig = px.pie(
                            category_summary,
                            values='amount',
                            names='category',
                            title="Expenses by Category"
                        )
                        st.plotly_chart(fig, width='stretch')

                    # Detailed expense list
                    st.markdown("##### Expense Details")
                    expense_display = expenses_df[[
                        'date', 'category', 'description', 'amount', 'approved'
                    ]].copy()
                    expense_display['approved'] = expense_display['approved'].map({0: '❌', 1: '✅'})
                    expense_display['amount'] = expense_display['amount'].apply(lambda x: f"${x:,.2f}")

                    st.dataframe(expense_display, width='stretch', hide_index=True)
                else:
                    st.info("No expenses recorded for this project")

            # Burn Rate
            with detail_tab5:
                # Burn Rate Analysis
                show_burn_rate_editor(project, db, processor)
    else:
        st.info("No projects available")

with tab3:
    # Edit project
    st.markdown("#### Edit Project")

    projects_df = db.get_projects()

    if not projects_df.empty:
        # Select project to edit
        selected_project_name = st.selectbox(
            "Select Project to Edit",
            options=projects_df['name'].tolist(),
            key="edit_project_select"
        )

        if selected_project_name:
            project = projects_df[projects_df['name'] == selected_project_name].iloc[0]
            project_id = project['id']

            st.markdown(f"##### Editing: {project['name']}")

            with st.form("edit_project_form"):
                col1, col2 = st.columns(2)

                with col1:
                    name = st.text_input("Project Name*", value=project['name'])
                    description = st.text_area("Description", value=project['description'] if pd.notna(project['description']) else "")
                    client = st.text_input("Client*", value=project['client'])
                    project_manager = st.text_input("Project Manager*", value=project['project_manager'])

                with col2:
                    status = st.selectbox("Status", ["Active", "On Hold", "Completed", "Cancelled"],
                                        index=["Active", "On Hold", "Completed", "Cancelled"].index(project['status']))
                    start_date = st.date_input("Start Date", value=pd.to_datetime(project['start_date']))
                    end_date = st.date_input("End Date", value=pd.to_datetime(project['end_date']))
                    budget_allocated = st.number_input("Budget Allocated", min_value=0.0, step=1000.0, value=float(project['budget_allocated']))

                col1, col2 = st.columns(2)

                with col1:
                    revenue_projected = st.number_input("Revenue Projected", min_value=0.0, step=1000.0, value=float(project['revenue_projected']))
                    budget_used = st.number_input("Budget Used", min_value=0.0, step=1000.0, value=float(project['budget_used']))

                with col2:
                    revenue_actual = st.number_input("Revenue Actual", min_value=0.0, step=1000.0, value=float(project['revenue_actual']))

                billable = st.checkbox("Billable Project", value=bool(project.get('billable', 0)), help="Check if this is a billable client project")

                update_button = st.form_submit_button("Update Project", type="primary")

                if update_button:
                    if name and client and project_manager:
                        updates = {
                            'name': name,
                            'description': description,
                            'client': client,
                            'project_manager': project_manager,
                            'status': status,
                            'start_date': start_date.strftime('%Y-%m-%d'),
                            'end_date': end_date.strftime('%Y-%m-%d'),
                            'budget_allocated': budget_allocated,
                            'budget_used': budget_used,
                            'revenue_projected': revenue_projected,
                            'revenue_actual': revenue_actual,
                            'billable': 1 if billable else 0
                        }

                        try:
                            db.update_project(project_id, updates)
                            st.success(f"Project '{name}' updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating project: {str(e)}")
                    else:
                        st.error("Please fill in all required fields marked with *")

            # Team allocation management (outside the form)
            st.markdown("---")
            st.markdown("#### Team Allocation Management")

            # Current allocations
            allocations_df = db.get_allocations(project_id=project_id)

            if not allocations_df.empty:
                st.markdown("##### Current Team Members")

                for _, alloc in allocations_df.iterrows():
                    col1, col2, col3 = st.columns([4, 2, 1])

                    with col1:
                        st.write(f"**{alloc['employee_name']}**")

                    with col2:
                        fte = alloc.get('allocated_fte', 0)
                        st.write(f"Allocation: {fte * 100:.0f}%")

                    with col3:
                        if st.button("Remove", key=f"remove_alloc_{alloc['id']}"):
                            try:
                                db.delete_allocation(alloc['id'])
                                st.success(f"Removed {alloc['employee_name']} from project")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error removing allocation: {str(e)}")
            else:
                st.info("No team members allocated to this project")

            # Add new allocation
            st.markdown("##### Add Team Member")
            logger.info(f"Page loaded, project_id={project_id}")

            employees_df = db.get_employees()

            # Filter out employees already allocated
            if not allocations_df.empty:
                allocated_ids = allocations_df['employee_id'].tolist()
                available_employees = employees_df[~employees_df['id'].isin(allocated_ids)]
            else:
                available_employees = employees_df

            if not available_employees.empty:
                with st.form(key=f"add_alloc_project_{project_id}"):
                    col1, col2 = st.columns(2)

                    with col1:
                        employee_name = st.selectbox(
                            "Select Employee",
                            options=available_employees['name'].tolist()
                        )
                        allocated_fte = st.number_input("Allocation (FTE)", min_value=0.0, max_value=1.0, step=0.05, value=0.5, help="0.5 = 50% of full-time, 1.0 = 100% full-time")

                    with col2:
                        role_in_project = st.text_input("Role in Project")

                    col1, col2 = st.columns(2)
                    with col1:
                        alloc_start = st.date_input("Start Date", value=pd.to_datetime(project['start_date']))
                    with col2:
                        alloc_end = st.date_input("End Date", value=pd.to_datetime(project['end_date']))

                    if st.form_submit_button("Add Team Member"):
                        try:
                            logger.info(f"Form submitted for project_id={project_id}, employee_name={employee_name}")
                            selected_emp = available_employees[available_employees['name'] == employee_name].iloc[0]
                            logger.info(f"Selected employee: {selected_emp['id']}, {selected_emp['name']}")

                            # Get employee's cost_rate to use as bill_rate
                            bill_rate = selected_emp.get('cost_rate', None)

                            allocation_data = {
                                'project_id': project_id,
                                'employee_id': selected_emp['id'],
                                'allocated_fte': allocated_fte,
                                'start_date': alloc_start.strftime('%Y-%m-%d'),
                                'end_date': alloc_end.strftime('%Y-%m-%d'),
                                'role': role_in_project,
                                'bill_rate': bill_rate
                            }
                            logger.info(f"Allocation data: {allocation_data}")

                            result = db.add_allocation(allocation_data)
                            logger.info(f"add_allocation returned: {result}")
                            st.success(f"Added {employee_name} to project!")
                            st.rerun()
                        except Exception as e:
                            logger.error(f"Exception occurred while adding team member: {str(e)}", exc_info=True)
                            st.error(f"Error adding team member: {str(e)}")
            else:
                st.info("All employees are already allocated to this project")

    else:
        st.info("No projects available to edit")

with tab4:
    # Project analytics
    projects_df = db.get_projects()

    if not projects_df.empty:
        # Project comparison
        st.markdown("#### Project Comparison")

        selected_projects = st.multiselect(
            "Select projects to compare",
            options=projects_df['name'].tolist(),
            default=projects_df['name'].tolist()[:5]
        )

        if selected_projects:
            comparison_df = projects_df[projects_df['name'].isin(selected_projects)].copy()

            # Comparison charts
            col1, col2 = st.columns(2)

            with col1:
                # Budget comparison
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name='Allocated',
                    x=comparison_df['name'],
                    y=comparison_df['budget_allocated']
                ))
                fig.add_trace(go.Bar(
                    name='Used',
                    x=comparison_df['name'],
                    y=comparison_df['budget_used']
                ))
                fig.update_layout(
                    title="Budget Comparison",
                    barmode='group',
                    height=400
                )
                st.plotly_chart(fig, width='stretch')

            with col2:
                # Revenue comparison
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name='Projected',
                    x=comparison_df['name'],
                    y=comparison_df['revenue_projected']
                ))
                fig.add_trace(go.Bar(
                    name='Actual',
                    x=comparison_df['name'],
                    y=comparison_df['revenue_actual']
                ))
                fig.update_layout(
                    title="Revenue Comparison",
                    barmode='group',
                    height=400
                )
                st.plotly_chart(fig, width='stretch')

            # Profitability analysis
            st.markdown("#### Profitability Analysis")

            comparison_df['profit'] = comparison_df['revenue_actual'] - comparison_df['budget_used']
            comparison_df['profit_margin'] = (comparison_df['profit'] / comparison_df['revenue_actual'] * 100).fillna(0)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=comparison_df['revenue_actual'],
                y=comparison_df['profit'],
                mode='markers+text',
                text=comparison_df['name'],
                textposition="top center",
                marker=dict(
                    size=comparison_df['budget_used'] / 5000,
                    color=comparison_df['profit_margin'],
                    colorscale='RdYlGn',
                    showscale=True,
                    colorbar=dict(title="Profit Margin %")
                )
            ))
            fig.update_layout(
                title="Revenue vs Profit (Bubble size = Budget Used)",
                xaxis_title="Revenue Actual",
                yaxis_title="Profit",
                height=500
            )
            st.plotly_chart(fig, width='stretch')
    else:
        st.info("No projects available for analysis")
