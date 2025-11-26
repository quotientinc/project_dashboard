"""
Reports page - provides various analytical reports with lazy loading pattern.

Following the same UX pattern as projects.py:
- Radio button navigation for lazy loading
- Each report renders only when selected
- No "Generate Report" buttons needed
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor


# ============================================================================
# REPORT 1: Allocation Coverage Analysis
# ============================================================================

@st.dialog("Generate Allocation CSV Template", width="large")
def generate_allocation_csv_template(project_id, project_name, start_date, end_date):
    """Generate a CSV template for allocations covering the entire project period"""
    st.markdown(f"### {project_name}")
    st.caption(f"Period: {start_date} to {end_date}")

    # Generate month rows for the entire PoP
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    months = pd.date_range(
        start=start.replace(day=1),
        end=end + pd.DateOffset(months=1),
        freq='MS'
    )[:-1]  # Remove extra month

    month_keys = [m.strftime('%Y-%m') for m in months]

    st.info(f"📅 This template will cover **{len(month_keys)} months** from {month_keys[0]} to {month_keys[-1]}")

    # Get existing allocations for this project
    allocations_df = db.get_allocations(project_id=project_id)

    # Determine employee selection
    employees_df = db.get_employees()

    if not allocations_df.empty:
        # Project has some allocations - pre-select employees with existing allocations
        existing_employees = allocations_df['employee_id'].unique().tolist()
        existing_employee_names = employees_df[employees_df['id'].isin(existing_employees)]['name'].tolist()

        st.success(f"✅ Found {len(existing_employees)} employee(s) with existing allocations")
        st.write("**Pre-selected employees:**", ", ".join(existing_employee_names))

        # Allow adding more employees
        all_employee_options = employees_df['name'].tolist()
        selected_employee_names = st.multiselect(
            "Add or remove employees",
            options=all_employee_options,
            default=existing_employee_names,
            help="Modify the list of employees to include in the CSV template"
        )
    else:
        # No allocations yet - let user select from billable employees
        billable_employees = employees_df[employees_df['billable'] == 1]

        st.warning("⚠️ No existing allocations found for this project")

        selected_employee_names = st.multiselect(
            "Select employees to allocate",
            options=billable_employees['name'].tolist(),
            help="Select one or more billable employees to include in the allocation template"
        )

    if not selected_employee_names:
        st.info("👆 Please select at least one employee to generate the CSV template")
        return

    # Get employee IDs and details
    selected_employees = employees_df[employees_df['name'].isin(selected_employee_names)]

    # Build CSV template
    template_rows = []
    existing_count = 0
    new_count = 0

    for _, emp in selected_employees.iterrows():
        emp_id = emp['id']
        emp_name = emp['name']
        default_role = emp['role']

        for month_key in month_keys:
            # Check if allocation exists for this employee-month
            existing_alloc = allocations_df[
                (allocations_df['employee_id'] == emp_id) &
                (allocations_df['allocation_date'] == month_key)
            ]

            if not existing_alloc.empty:
                # Use existing allocation data
                alloc = existing_alloc.iloc[0]
                bill_rate = alloc['bill_rate'] if pd.notna(alloc.get('bill_rate')) and alloc.get('bill_rate') != 0 else ''

                template_rows.append({
                    'employee_id': emp_id,
                    'employee_name': emp_name,
                    'project_id': project_id,
                    'allocation_date': month_key,
                    'allocated_fte': alloc['allocated_fte'],
                    'bill_rate': bill_rate,
                    'role': alloc.get('role', default_role) if pd.notna(alloc.get('role')) else default_role,
                    'status': 'Existing'
                })
                existing_count += 1
            else:
                # Create placeholder row for missing allocation
                template_rows.append({
                    'employee_id': emp_id,
                    'employee_name': emp_name,
                    'project_id': project_id,
                    'allocation_date': month_key,
                    'allocated_fte': 0.0,
                    'bill_rate': '',
                    'role': default_role,
                    'status': 'New'
                })
                new_count += 1

    template_df = pd.DataFrame(template_rows)

    # Summary
    st.markdown("#### Template Summary")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Rows", len(template_df))
    with col2:
        st.metric("Existing Allocations", existing_count)
    with col3:
        st.metric("New Rows (Need FTE)", new_count)

    st.write(f"**Formula:** {len(selected_employees)} employees × {len(month_keys)} months = {len(template_df)} rows")

    # Preview
    st.markdown("#### Preview")
    st.caption("Rows marked 'New' have allocated_fte=0.0 and empty bill_rate - fill these in before import")

    st.dataframe(
        template_df,
        width='stretch',
        hide_index=True,
        height=400,
        column_config={
            "allocated_fte": st.column_config.NumberColumn(
                "Allocated FTE",
                format="%.2f",
                help="0.0 = No allocation (fill this in!)"
            ),
            "bill_rate": st.column_config.NumberColumn(
                "Bill Rate",
                format="$%.2f"
            ),
            "status": st.column_config.TextColumn(
                "Status",
                help="Existing = from database, New = needs FTE value"
            )
        }
    )

    # Export CSV
    export_df = template_df[['employee_id', 'employee_name', 'project_id', 'allocation_date', 'allocated_fte', 'bill_rate', 'role']].copy()
    csv = export_df.to_csv(index=False)

    st.markdown("#### Download")
    st.download_button(
        label="📥 Download CSV Template",
        data=csv,
        file_name=f"allocations_{project_id}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True
    )

    st.info(
        "💡 **Next Steps:**\n"
        "1. Download the CSV template\n"
        "2. Fill in `allocated_fte` values for rows marked 'New' (e.g., 0.5 for 50% allocation)\n"
        "3. Fill in `bill_rate` values if empty (hourly billing rate)\n"
        "4. Adjust `role` if needed\n"
        "5. Import via **Data Management → Import Data → Import Allocation CSV**"
    )


def render_allocation_coverage_report():
    """Report showing allocation coverage across all projects"""
    st.markdown("#### 📋 Allocation Coverage Analysis")
    st.caption("Analysis of allocation coverage across all projects")

    # Load data
    projects_df = db.get_projects()
    allocations_df = db.get_allocations()

    if projects_df.empty:
        st.info("No projects found.")
        return

    # Analyze each project
    project_details = []
    no_allocations = []
    partial_coverage = []
    fully_allocated = []
    skipped_projects = []

    for _, project in projects_df.iterrows():
        project_id = project['id']
        project_name = project['name']
        client = project['client']
        status = project['status']
        start_date_str = project['start_date']
        end_date_str = project['end_date']

        # Skip projects without dates
        if pd.isna(start_date_str) or start_date_str == '' or pd.isna(end_date_str) or end_date_str == '':
            reason = []
            if pd.isna(start_date_str) or start_date_str == '':
                reason.append("Missing start date")
            if pd.isna(end_date_str) or end_date_str == '':
                reason.append("Missing end date")

            skipped_projects.append({
                'Project ID': project_id,
                'Project Name': project_name,
                'Client': client,
                'Status': status,
                'Reason': ' & '.join(reason)
            })
            continue

        start_date = pd.to_datetime(start_date_str)
        end_date = pd.to_datetime(end_date_str)

        # Calculate project duration in months
        project_months = pd.date_range(start=start_date, end=end_date, freq='MS')
        total_months = len(project_months)

        # Get allocations for this project
        project_allocations = allocations_df[allocations_df['project_id'] == project_id]

        if project_allocations.empty:
            allocation_status = "❌ No Allocations"
            coverage_pct = 0
            months_covered = 0
            months_missing = total_months
            employee_count = 0
            total_fte = 0
            no_allocations.append(project_name)
        else:
            allocation_months = pd.to_datetime(project_allocations['allocation_date']).dt.to_period('M').unique()
            months_covered = len(allocation_months)
            coverage_pct = (months_covered / total_months * 100) if total_months > 0 else 0
            months_missing = total_months - months_covered
            employee_count = project_allocations['employee_id'].nunique()
            total_fte = project_allocations.groupby('allocation_date')['allocated_fte'].sum().mean()

            if coverage_pct >= 100:
                allocation_status = "✅ Fully Allocated"
                fully_allocated.append(project_name)
            else:
                allocation_status = "⚠️ Partial Coverage"
                partial_coverage.append(project_name)

        project_details.append({
            'Project ID': project_id,
            'Project Name': project_name,
            'Client': client,
            'Status': status,
            'Start Date': start_date.strftime('%Y-%m-%d'),
            'End Date': end_date.strftime('%Y-%m-%d'),
            'Total Months': total_months,
            'Months Covered': months_covered,
            'Months Missing': months_missing,
            'Coverage %': coverage_pct,
            'Allocation Status': allocation_status,
            'Employees': employee_count,
            'Avg FTE': round(total_fte, 2) if not project_allocations.empty else 0
        })

    details_df = pd.DataFrame(project_details)

    # Summary Cards
    st.markdown("##### Allocation Summary")
    col1, col2, col3, col4 = st.columns(4)

    analyzed_count = len(details_df)
    skipped_count = len(skipped_projects)

    with col1:
        st.metric(
            "Projects Analyzed",
            analyzed_count,
            help=f"Out of {len(projects_df)} total projects. {skipped_count} skipped (see below)."
        )

    with col2:
        no_alloc_pct = (len(no_allocations) / analyzed_count * 100) if analyzed_count > 0 else 0
        st.metric(
            "❌ No Allocations",
            len(no_allocations),
            delta=f"{no_alloc_pct:.1f}%",
            delta_color="inverse"
        )

    with col3:
        partial_pct = (len(partial_coverage) / analyzed_count * 100) if analyzed_count > 0 else 0
        st.metric(
            "⚠️ Partial Coverage",
            len(partial_coverage),
            delta=f"{partial_pct:.1f}%",
            delta_color="off"
        )

    with col4:
        full_pct = (len(fully_allocated) / analyzed_count * 100) if analyzed_count > 0 else 0
        st.metric(
            "✅ Fully Allocated",
            len(fully_allocated),
            delta=f"{full_pct:.1f}%",
            delta_color="normal"
        )

    st.markdown("---")

    # Filters
    st.markdown("##### Project Details")

    col1, col2 = st.columns(2)

    with col1:
        project_status_filter = st.selectbox(
            "Filter by Project Status",
            ["All", "Active", "Future", "Completed", "On Hold", "Cancelled"],
            index=1,  # Default to "Active"
            key="project_status_filter"
        )

    with col2:
        allocation_status_filter = st.selectbox(
            "Filter by Allocation Status",
            ["All", "❌ No Allocations", "⚠️ Partial Coverage", "✅ Fully Allocated"],
            key="alloc_status_filter"
        )

    # Apply filters
    filtered_df = details_df.copy()

    if project_status_filter != "All":
        filtered_df = filtered_df[filtered_df['Status'] == project_status_filter]

    if allocation_status_filter != "All":
        filtered_df = filtered_df[filtered_df['Allocation Status'] == allocation_status_filter]

    # Display table with row selection
    st.caption("💡 Click on a row to generate an allocation CSV template for that project")

    selection = st.dataframe(
        filtered_df,
        width='stretch',
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="allocation_gaps_table",
        column_config={
            "Coverage %": st.column_config.ProgressColumn(
                "Coverage %",
                format="%.1f%%",
                min_value=0,
                max_value=100
            ),
            "Avg FTE": st.column_config.NumberColumn(
                "Avg FTE",
                format="%.2f"
            )
        }
    )

    # Handle row selection
    if selection and selection.selection.rows:
        selected_idx = selection.selection.rows[0]
        selected_row = filtered_df.iloc[selected_idx]
        generate_allocation_csv_template(
            selected_row['Project ID'],
            selected_row['Project Name'],
            selected_row['Start Date'],
            selected_row['End Date']
        )

    # Summary Statistics
    st.markdown("##### Summary Statistics")
    summary_cols = st.columns(4)
    with summary_cols[0]:
        st.metric("Total Projects", len(filtered_df))
    with summary_cols[1]:
        avg_coverage = filtered_df['Coverage %'].mean()
        st.metric("Avg Coverage", f"{avg_coverage:.1f}%")
    with summary_cols[2]:
        total_missing = filtered_df['Months Missing'].sum()
        st.metric("Total Months Missing", int(total_missing))
    with summary_cols[3]:
        avg_fte = filtered_df['Avg FTE'].mean()
        st.metric("Avg FTE per Project", f"{avg_fte:.2f}")

    # CSV Export
    st.markdown("---")
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Report as CSV",
        data=csv,
        file_name=f"allocation_coverage_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

    # Skipped Projects Section
    if skipped_projects:
        st.markdown("---")
        st.markdown("#### ⚠️ Projects Skipped (No Period of Performance Defined)")
        st.info(
            f"**{len(skipped_projects)} project(s)** were excluded from the allocation analysis above "
            f"because they are missing a start date and/or end date."
        )

        skipped_df = pd.DataFrame(skipped_projects)
        st.dataframe(skipped_df, width='stretch', hide_index=True)
        st.caption("💡 To include these projects, add start and end dates in the Edit Project tab.")
    else:
        st.success("✅ All projects have defined periods of performance.")


# ============================================================================
# REPORT 2: Monthly Resource Allocation
# ============================================================================

def render_monthly_allocation_report():
    """Monthly resource allocation report with employee and project views"""
    st.markdown("#### 📊 Monthly Resource Allocation")
    st.caption("Visualize employee and project allocation status across the company")

    # Load allocations
    allocations_df = db.get_allocations()

    if allocations_df.empty or 'allocation_date' not in allocations_df.columns:
        st.warning("No allocation data available. Please import allocations first.")
        return

    # Get unique months
    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
    unique_months = allocations_df['allocation_date'].dt.to_period('M').unique()
    unique_months = sorted(unique_months, reverse=True)

    if len(unique_months) == 0:
        st.warning("No allocation data available.")
        return

    # Month selection
    col1, col2 = st.columns([2, 1])

    with col1:
        month_options = {str(m): m.strftime('%B %Y') for m in unique_months}
        selected_month_str = st.selectbox(
            "Select Month",
            options=list(month_options.keys()),
            format_func=lambda x: month_options[x],
            key="alloc_month_selector"
        )
        selected_month = pd.Period(selected_month_str)

    with col2:
        view_mode = st.radio(
            "View",
            ["Employee View", "Project View"],
            key="alloc_view_mode"
        )

    # Filter allocations for selected month
    month_allocations = allocations_df[
        allocations_df['allocation_date'].dt.to_period('M') == selected_month
    ].copy()

    if month_allocations.empty:
        st.warning(f"No allocations found for {selected_month.strftime('%B %Y')}")
        return

    # Load additional data
    employees_df = db.get_employees()
    projects_df = db.get_projects()
    months_df = db.get_months()

    # Get working days
    month_info = months_df[
        (months_df['year'] == selected_month.year) &
        (months_df['month'] == selected_month.month)
    ]
    working_days = month_info['working_days'].iloc[0] if not month_info.empty else 21

    st.divider()

    # EMPLOYEE VIEW
    if view_mode == "Employee View":
        employee_summary = []

        for _, emp in employees_df.iterrows():
            emp_id = emp['id']
            emp_name = emp['name']
            emp_role = emp['role']
            target_fte = emp.get('target_allocation', 1.0) if pd.notna(emp.get('target_allocation')) else 1.0
            billable = emp.get('billable', 1)

            emp_allocations = month_allocations[month_allocations['employee_id'] == emp_id]
            if emp_allocations.empty and billable == 0:
                continue

            total_allocated_fte = emp_allocations['allocated_fte'].sum() if not emp_allocations.empty else 0.0
            variance_fte = total_allocated_fte - target_fte
            variance_pct = (total_allocated_fte / target_fte * 100) if target_fte > 0 else 0

            if variance_pct > 100:
                status = "🔴 Over"
            elif variance_pct >= 80:
                status = "🟢 Healthy"
            else:
                status = "🟡 Under"

            project_count = emp_allocations['project_id'].nunique() if not emp_allocations.empty else 0
            project_names = emp_allocations['project_name'].unique().tolist() if not emp_allocations.empty else []
            projects_str = ", ".join(project_names[:3]) + (f" (+{len(project_names)-3} more)" if len(project_names) > 3 else "")

            employee_summary.append({
                'Employee ID': emp_id,
                'Employee': emp_name,
                'Role': emp_role,
                'Target FTE': target_fte,
                'Allocated FTE': total_allocated_fte,
                'Variance': variance_fte,
                'Variance %': variance_pct,
                'Project Count': project_count,
                'Projects': projects_str,
                'Status': status
            })

        summary_df = pd.DataFrame(employee_summary)

        if summary_df.empty:
            st.info("No employee allocation data for this month.")
            return

        # Summary metrics
        st.markdown("##### Summary Dashboard")

        total_employees = len(summary_df)
        over_allocated = len(summary_df[summary_df['Variance %'] > 100])
        under_allocated = len(summary_df[summary_df['Variance %'] < 80])
        healthy = len(summary_df[(summary_df['Variance %'] >= 80) & (summary_df['Variance %'] <= 100)])

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Active Employees", total_employees)
        with col2:
            over_pct = (over_allocated / total_employees * 100) if total_employees > 0 else 0
            st.metric("Over-Allocated", over_allocated, delta=f"{over_pct:.1f}%", delta_color="inverse")
        with col3:
            under_pct = (under_allocated / total_employees * 100) if total_employees > 0 else 0
            st.metric("Under-Allocated", under_allocated, delta=f"{under_pct:.1f}%", delta_color="off")
        with col4:
            healthy_pct = (healthy / total_employees * 100) if total_employees > 0 else 0
            st.metric("Healthy Allocation", healthy, delta=f"{healthy_pct:.1f}%", delta_color="normal")

        st.divider()

        # Alerts
        if over_allocated > 0:
            critical_over = summary_df[summary_df['Variance %'] > 120]
            if not critical_over.empty:
                st.warning(f"⚠️ **{len(critical_over)} employee(s) allocated >120%** - review workload: {', '.join(critical_over['Employee'].tolist()[:5])}")

        if under_allocated > total_employees * 0.3:
            st.info(f"📊 **{under_allocated} employees <80% allocated** - opportunities available for new projects")

        # Filter and sort
        st.markdown("##### Employee Allocation Details")

        col1, col2 = st.columns(2)

        with col1:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "🔴 Over", "🟢 Healthy", "🟡 Under"],
                key="emp_status_filter"
            )

        with col2:
            sort_by = st.selectbox(
                "Sort by",
                ["Variance % (High to Low)", "Variance % (Low to High)", "Employee Name", "Allocated FTE"],
                key="emp_sort_by"
            )

        # Apply filter
        filtered_df = summary_df.copy()
        if status_filter != "All":
            filtered_df = filtered_df[filtered_df['Status'] == status_filter]

        # Apply sorting
        if sort_by == "Variance % (High to Low)":
            filtered_df = filtered_df.sort_values('Variance %', ascending=False)
        elif sort_by == "Variance % (Low to High)":
            filtered_df = filtered_df.sort_values('Variance %', ascending=True)
        elif sort_by == "Employee Name":
            filtered_df = filtered_df.sort_values('Employee')
        elif sort_by == "Allocated FTE":
            filtered_df = filtered_df.sort_values('Allocated FTE', ascending=False)

        # Display table
        display_df = filtered_df[[
            'Employee', 'Role', 'Target FTE', 'Allocated FTE',
            'Variance', 'Variance %', 'Project Count', 'Projects', 'Status'
        ]].copy()

        st.dataframe(
            display_df,
            width='stretch',
            hide_index=True,
            column_config={
                "Target FTE": st.column_config.NumberColumn("Target FTE", format="%.2f"),
                "Allocated FTE": st.column_config.NumberColumn("Allocated FTE", format="%.2f"),
                "Variance": st.column_config.NumberColumn("Variance", format="%+.2f", help="Allocated - Target"),
                "Variance %": st.column_config.ProgressColumn(
                    "Utilization %",
                    format="%.1f%%",
                    min_value=0,
                    max_value=150
                )
            },
            height=500
        )

        # Visualization
        st.divider()
        st.markdown("##### Allocation by Employee")

        chart_data = []
        for _, emp in filtered_df.iterrows():
            emp_id = emp['Employee ID']
            emp_name = emp['Employee']
            target_fte = emp['Target FTE']

            emp_allocations = month_allocations[month_allocations['employee_id'] == emp_id]

            for _, alloc in emp_allocations.iterrows():
                chart_data.append({
                    'Employee': emp_name,
                    'Project': alloc['project_name'],
                    'FTE': alloc['allocated_fte'],
                    'Target': target_fte
                })

        if chart_data:
            chart_df = pd.DataFrame(chart_data)

            fig = go.Figure()

            for project in chart_df['Project'].unique():
                project_data = chart_df[chart_df['Project'] == project]
                fig.add_trace(go.Bar(
                    name=project,
                    x=project_data['Employee'],
                    y=project_data['FTE'],
                    text=project_data['FTE'].apply(lambda x: f"{x:.2f}"),
                    textposition='inside'
                ))

            employees_ordered = filtered_df.sort_values('Allocated FTE', ascending=False)['Employee'].tolist()
            target_values = [filtered_df[filtered_df['Employee'] == emp]['Target FTE'].values[0] for emp in employees_ordered]

            fig.add_trace(go.Scatter(
                x=employees_ordered,
                y=target_values,
                name='Target FTE',
                mode='lines+markers',
                line=dict(color='red', width=2, dash='dash'),
                marker=dict(size=8)
            ))

            fig.update_layout(
                title="Employee Allocation vs Target",
                xaxis_title="Employee",
                yaxis_title="FTE",
                barmode='stack',
                height=500,
                hovermode='x unified',
                showlegend=True
            )

            st.plotly_chart(fig, width='stretch')

        # Export
        st.divider()
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Employee Allocation Report",
            data=csv,
            file_name=f"employee_allocation_{selected_month.strftime('%Y_%m')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    # PROJECT VIEW
    else:
        project_summary = []

        for project_id in month_allocations['project_id'].unique():
            project_allocations = month_allocations[month_allocations['project_id'] == project_id]

            project = projects_df[projects_df['id'] == project_id]
            if project.empty:
                project_name = project_id
                project_status = "Unknown"
            else:
                project_name = project['name'].iloc[0]
                project_status = project['status'].iloc[0] if pd.notna(project['status'].iloc[0]) else "Active"

            total_fte = project_allocations['allocated_fte'].sum()
            employee_count = project_allocations['employee_id'].nunique()
            employees = project_allocations['employee_name'].unique().tolist()
            employees_str = ", ".join(employees[:3]) + (f" (+{len(employees)-3} more)" if len(employees) > 3 else "")

            projected_hours = total_fte * working_days * 8

            projected_revenue = 0
            for _, alloc in project_allocations.iterrows():
                bill_rate = alloc.get('bill_rate', 0) if pd.notna(alloc.get('bill_rate')) else 0
                alloc_hours = alloc['allocated_fte'] * working_days * 8
                projected_revenue += alloc_hours * bill_rate

            project_summary.append({
                'Project ID': project_id,
                'Project Name': project_name,
                'Status': project_status,
                'Total FTE': total_fte,
                'Employee Count': employee_count,
                'Employees': employees_str,
                'Projected Hours': projected_hours,
                'Projected Revenue': projected_revenue
            })

        project_summary_df = pd.DataFrame(project_summary)

        if project_summary_df.empty:
            st.info("No project allocation data for this month.")
            return

        # Summary metrics
        st.markdown("##### Project Summary Dashboard")

        total_projects = len(project_summary_df)
        total_fte_allocated = project_summary_df['Total FTE'].sum()
        total_hours = project_summary_df['Projected Hours'].sum()
        total_revenue = project_summary_df['Projected Revenue'].sum()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Projects", total_projects)
        with col2:
            st.metric("Total FTE Allocated", f"{total_fte_allocated:.1f}")
        with col3:
            st.metric("Projected Hours", f"{total_hours:,.0f}")
        with col4:
            st.metric("Projected Revenue", f"${total_revenue:,.0f}")

        st.divider()

        # Check for unallocated active projects
        active_projects = projects_df[projects_df['status'].isin(['Active', 'Future'])]
        allocated_project_ids = month_allocations['project_id'].unique()
        unallocated_projects = active_projects[~active_projects['id'].isin(allocated_project_ids)]

        if not unallocated_projects.empty:
            st.warning(f"🔴 **{len(unallocated_projects)} active/future project(s) have no team allocations** for {selected_month.strftime('%B %Y')}")

        # Filter and sort
        st.markdown("##### Project Allocation Details")

        col1, col2 = st.columns(2)

        with col1:
            project_status_filter = st.selectbox(
                "Filter by Status",
                ["All"] + sorted(project_summary_df['Status'].unique().tolist()),
                key="proj_status_filter"
            )

        with col2:
            proj_sort_by = st.selectbox(
                "Sort by",
                ["Total FTE (High to Low)", "Total FTE (Low to High)", "Project Name", "Projected Revenue"],
                key="proj_sort_by"
            )

        # Apply filter
        filtered_proj_df = project_summary_df.copy()
        if project_status_filter != "All":
            filtered_proj_df = filtered_proj_df[filtered_proj_df['Status'] == project_status_filter]

        # Apply sorting
        if proj_sort_by == "Total FTE (High to Low)":
            filtered_proj_df = filtered_proj_df.sort_values('Total FTE', ascending=False)
        elif proj_sort_by == "Total FTE (Low to High)":
            filtered_proj_df = filtered_proj_df.sort_values('Total FTE', ascending=True)
        elif proj_sort_by == "Project Name":
            filtered_proj_df = filtered_proj_df.sort_values('Project Name')
        elif proj_sort_by == "Projected Revenue":
            filtered_proj_df = filtered_proj_df.sort_values('Projected Revenue', ascending=False)

        # Display table
        display_proj_df = filtered_proj_df[[
            'Project Name', 'Status', 'Total FTE', 'Employee Count',
            'Employees', 'Projected Hours', 'Projected Revenue'
        ]].copy()

        st.dataframe(
            display_proj_df,
            width='stretch',
            hide_index=True,
            column_config={
                "Total FTE": st.column_config.NumberColumn("Total FTE", format="%.2f"),
                "Projected Hours": st.column_config.NumberColumn("Projected Hours", format="%.0f"),
                "Projected Revenue": st.column_config.NumberColumn("Projected Revenue", format="$%.0f")
            },
            height=500
        )

        # Visualization
        st.divider()
        st.markdown("##### FTE Allocation by Project")

        top_projects = filtered_proj_df.nlargest(20, 'Total FTE')

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=top_projects['Project Name'],
            y=top_projects['Total FTE'],
            text=top_projects['Total FTE'].apply(lambda x: f"{x:.1f}"),
            textposition='outside',
            marker_color='#007bff'
        ))

        fig.update_layout(
            title=f"Top {len(top_projects)} Projects by FTE Allocation",
            xaxis_title="Project",
            yaxis_title="Total FTE",
            height=500,
            showlegend=False
        )

        fig.update_xaxes(tickangle=-45)

        st.plotly_chart(fig, width='stretch')

        # Export
        st.divider()
        csv = display_proj_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Project Allocation Report",
            data=csv,
            file_name=f"project_allocation_{selected_month.strftime('%Y_%m')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )


# ============================================================================
# REPORT 3: Project Financial Summary (NEW - replaces Executive + Financial)
# ============================================================================

def render_financial_summary_report():
    """Financial summary report showing project budgets and burn rates"""
    st.markdown("#### 💰 Project Financial Summary")
    st.caption("Overview of project budgets, spending, and financial health")

    projects_df = db.get_projects()

    if projects_df.empty:
        st.info("No projects found.")
        return

    # Filter options
    col1, col2 = st.columns(2)

    with col1:
        status_filter = st.multiselect(
            "Filter by Status",
            options=["Active", "Future", "Completed", "On Hold", "Cancelled"],
            default=["Active"],
            key="financial_status_filter"
        )

    with col2:
        billable_filter = st.selectbox(
            "Filter by Type",
            ["All Projects", "Billable Only", "Non-Billable Only"],
            key="financial_billable_filter"
        )

    # Apply filters
    filtered_df = projects_df.copy()

    if status_filter:
        filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]

    if billable_filter == "Billable Only":
        filtered_df = filtered_df[filtered_df['billable'] == 1]
    elif billable_filter == "Non-Billable Only":
        filtered_df = filtered_df[filtered_df['billable'] == 0]

    if filtered_df.empty:
        st.warning("No projects match the selected filters.")
        return

    # Calculate totals
    total_quoted = filtered_df['quoted_value'].sum()
    total_awarded = filtered_df['awarded_value'].sum()
    total_accrued = filtered_df['budget_used'].sum()
    remaining = total_quoted - total_accrued
    burn_rate = (total_accrued / total_quoted * 100) if total_quoted > 0 else 0

    # Summary metrics
    st.markdown("##### Financial Overview")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Quoted Value", f"${total_quoted:,.0f}")
    with col2:
        st.metric("Total Awarded Value", f"${total_awarded:,.0f}")
    with col3:
        st.metric("Total Accrued", f"${total_accrued:,.0f}")
    with col4:
        st.metric("Budget Burn Rate", f"{burn_rate:.1f}%", f"${remaining:,.0f} remaining", delta_color="inverse")

    st.divider()

    # Project-level details
    st.markdown("##### Project Details")

    # Prepare display data
    display_df = filtered_df[['name', 'status', 'quoted_value', 'awarded_value', 'budget_used']].copy()

    # Calculate variances
    display_df['Budget %'] = ((display_df['budget_used'] / display_df['quoted_value']) * 100).round(1)
    display_df['Budget Variance'] = display_df['quoted_value'] - display_df['budget_used']
    display_df['Funding Gap'] = display_df['awarded_value'] - display_df['quoted_value']

    # Format for display
    from utils.project_helpers import safe_currency_display
    display_df['Quoted Value'] = display_df['quoted_value'].apply(safe_currency_display)
    display_df['Awarded Value'] = display_df['awarded_value'].apply(safe_currency_display)
    display_df['Budget Used'] = display_df['budget_used'].apply(safe_currency_display)
    display_df['Budget Variance'] = display_df['Budget Variance'].apply(lambda x: f"${x:+,.0f}" if pd.notna(x) else "-")
    display_df['Funding Gap'] = display_df['Funding Gap'].apply(lambda x: f"${x:+,.0f}" if pd.notna(x) else "-")

    # Select columns to show
    final_df = display_df[[
        'name', 'status', 'Quoted Value', 'Awarded Value', 'Budget Used', 'Budget %', 'Budget Variance', 'Funding Gap'
    ]].copy()
    final_df.rename(columns={'name': 'Project Name', 'status': 'Status'}, inplace=True)

    st.dataframe(
        final_df,
        width='stretch',
        hide_index=True,
        height=500
    )

    # Visualization
    st.divider()
    st.markdown("##### Budget Comparison")

    # Top 15 projects by quoted value
    top_projects = filtered_df.nlargest(15, 'quoted_value')

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name='Quoted Value',
        x=top_projects['name'],
        y=top_projects['quoted_value'],
        marker_color='#17a2b8'
    ))

    fig.add_trace(go.Bar(
        name='Awarded Value',
        x=top_projects['name'],
        y=top_projects['awarded_value'],
        marker_color='#28a745'
    ))

    fig.add_trace(go.Bar(
        name='Budget Used',
        x=top_projects['name'],
        y=top_projects['budget_used'],
        marker_color='#ffc107'
    ))

    fig.update_layout(
        title=f"Top {len(top_projects)} Projects - Financial Comparison",
        xaxis_title="Project",
        yaxis_title="Amount ($)",
        barmode='group',
        height=500,
        hovermode='x unified'
    )

    fig.update_xaxes(tickangle=-45)

    st.plotly_chart(fig, width='stretch')

    # Export
    st.divider()
    csv = final_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Financial Summary",
        data=csv,
        file_name=f"financial_summary_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )


# ============================================================================
# REPORT 4: Financial Analysis
# ============================================================================

def render_financial_analysis_report():
    """Render the Financial Analysis report with year selector and tabs."""

    # Get current year
    current_year = datetime.now().year

    # Year selector (default to current year)
    selected_year = st.selectbox(
        "Select Year",
        options=[current_year - 1, current_year, current_year + 1],
        index=1,  # Default to current year
        help="Financial analysis for the selected calendar year"
    )

    st.markdown(f"### 💰 Financial Analysis - {selected_year}")

    # Load data filtered to selected year
    projects_df = db.get_projects()

    # Filter projects active in selected year (start or end date within year)
    year_start = f"{selected_year}-01-01"
    year_end = f"{selected_year}-12-31"

    if not projects_df.empty:
        projects_df['start_date_dt'] = pd.to_datetime(projects_df['start_date'])
        projects_df['end_date_dt'] = pd.to_datetime(projects_df['end_date'])

        # Keep projects that overlap with selected year
        projects_df = projects_df[
            (projects_df['start_date_dt'] <= year_end) &
            (projects_df['end_date_dt'] >= year_start)
        ]

    # Get time entries for selected year
    time_entries_df = db.get_time_entries()
    if not time_entries_df.empty:
        time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
        time_entries_df = time_entries_df[time_entries_df['date'].dt.year == selected_year]

    # Get expenses for selected year
    expenses_df = db.get_expenses()
    if not expenses_df.empty:
        expenses_df['date'] = pd.to_datetime(expenses_df['date'])
        expenses_df = expenses_df[expenses_df['date'].dt.year == selected_year]

    # Get allocations for selected year
    allocations_df = db.get_allocations()
    if not allocations_df.empty:
        allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
        allocations_df = allocations_df[allocations_df['allocation_date'].dt.year == selected_year]

    # Calculate YTD actuals from time_entries
    ytd_revenue = 0
    ytd_labor_cost = 0

    if not time_entries_df.empty:
        # Revenue calculation
        def calculate_entry_revenue(row):
            if pd.notna(row.get('amount')) and row['amount'] != 0:
                return row['amount']
            elif pd.notna(row.get('hourly_rate')) and pd.notna(row.get('hours')):
                return row['hours'] * row['hourly_rate']
            return 0

        time_entries_df['revenue'] = time_entries_df.apply(calculate_entry_revenue, axis=1)
        ytd_revenue = time_entries_df['revenue'].sum()
        ytd_labor_cost = ytd_revenue  # Labor cost equals revenue for billable work

    # Expense costs
    ytd_expense_cost = expenses_df['amount'].sum() if not expenses_df.empty else 0
    ytd_total_cost = ytd_labor_cost + ytd_expense_cost

    # Metrics
    ytd_profit = ytd_revenue - ytd_total_cost
    ytd_margin = (ytd_profit / ytd_revenue * 100) if ytd_revenue > 0 else 0

    # Display key metrics
    st.markdown("#### Year-to-Date Performance")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("YTD Revenue", f"${ytd_revenue:,.0f}")
    with col2:
        st.metric("YTD Costs", f"${ytd_total_cost:,.0f}",
                  help=f"Labor: ${ytd_labor_cost:,.0f} | Expenses: ${ytd_expense_cost:,.0f}")
    with col3:
        st.metric("YTD Profit", f"${ytd_profit:,.0f}")
    with col4:
        st.metric("YTD Margin", f"{ytd_margin:.1f}%")

    st.markdown("---")

    # Tabs for focused analysis
    tab1, tab2, tab3 = st.tabs(["Monthly Trends", "Client Analysis", "Full Year Forecast"])

    with tab1:
        st.markdown("#### 📈 Monthly Trends")

        if not time_entries_df.empty:
            # Prepare monthly data
            monthly_df = time_entries_df.copy()
            monthly_df['month'] = monthly_df['date'].dt.to_period('M').astype(str)

            # Calculate monthly revenue
            monthly_revenue = monthly_df.groupby('month')['revenue'].sum().reset_index()
            monthly_revenue.columns = ['Month', 'Revenue']

            # Calculate monthly labor costs (same as revenue for billable)
            monthly_labor = monthly_df.groupby('month')['revenue'].sum().reset_index()
            monthly_labor.columns = ['Month', 'Labor Cost']

            # Calculate monthly expenses
            if not expenses_df.empty:
                exp_df = expenses_df.copy()
                exp_df['month'] = exp_df['date'].dt.to_period('M').astype(str)
                monthly_expenses = exp_df.groupby('month')['amount'].sum().reset_index()
                monthly_expenses.columns = ['Month', 'Expenses']
            else:
                monthly_expenses = pd.DataFrame(columns=['Month', 'Expenses'])

            # Merge all monthly data
            monthly_combined = monthly_revenue.merge(monthly_labor, on='Month', how='outer')
            monthly_combined = monthly_combined.merge(monthly_expenses, on='Month', how='outer').fillna(0)
            monthly_combined['Total Cost'] = monthly_combined['Labor Cost'] + monthly_combined['Expenses']
            monthly_combined['Profit'] = monthly_combined['Revenue'] - monthly_combined['Total Cost']
            monthly_combined['Margin %'] = (monthly_combined['Profit'] / monthly_combined['Revenue'] * 100).fillna(0)

            # Sort by month
            monthly_combined = monthly_combined.sort_values('Month')

            # Chart: Revenue, Cost, and Profit by Month
            fig = go.Figure()

            fig.add_trace(go.Bar(
                name='Revenue',
                x=monthly_combined['Month'],
                y=monthly_combined['Revenue'],
                marker_color='#2E86C1'
            ))

            fig.add_trace(go.Bar(
                name='Total Cost',
                x=monthly_combined['Month'],
                y=monthly_combined['Total Cost'],
                marker_color='#E74C3C'
            ))

            fig.add_trace(go.Scatter(
                name='Profit',
                x=monthly_combined['Month'],
                y=monthly_combined['Profit'],
                mode='lines+markers',
                line=dict(color='#27AE60', width=3),
                yaxis='y2'
            ))

            fig.update_layout(
                title=f"Monthly Revenue, Costs & Profit - {selected_year}",
                xaxis_title="Month",
                yaxis_title="Revenue & Costs ($)",
                yaxis2=dict(
                    title="Profit ($)",
                    overlaying='y',
                    side='right'
                ),
                barmode='group',
                height=400,
                hovermode='x unified'
            )

            st.plotly_chart(fig, width='stretch')

            # Display monthly breakdown table
            st.markdown("##### Monthly Breakdown")
            display_monthly = monthly_combined.copy()
            display_monthly['Revenue'] = display_monthly['Revenue'].apply(lambda x: f"${x:,.0f}")
            display_monthly['Total Cost'] = display_monthly['Total Cost'].apply(lambda x: f"${x:,.0f}")
            display_monthly['Profit'] = display_monthly['Profit'].apply(lambda x: f"${x:,.0f}")
            display_monthly['Margin %'] = display_monthly['Margin %'].apply(lambda x: f"{x:.1f}%")

            st.dataframe(display_monthly, width='stretch', hide_index=True)
        else:
            st.info(f"No time entry data found for {selected_year}")

    with tab2:
        st.markdown("#### 🏢 Client Analysis")

        if not time_entries_df.empty and not projects_df.empty:
            # Join time_entries with projects to get client info
            client_df = time_entries_df.merge(
                projects_df[['id', 'client']],
                left_on='project_id',
                right_on='id',
                how='left'
            )

            # Calculate revenue by client
            client_revenue = client_df.groupby('client')['revenue'].sum().reset_index()
            client_revenue.columns = ['Client', 'Revenue']

            # Get labor costs by client (same as revenue for billable)
            client_labor = client_df.groupby('client')['revenue'].sum().reset_index()
            client_labor.columns = ['Client', 'Labor Cost']

            # Get expenses by client (via project)
            if not expenses_df.empty:
                exp_client = expenses_df.merge(
                    projects_df[['id', 'client']],
                    left_on='project_id',
                    right_on='id',
                    how='left'
                )
                client_expenses = exp_client.groupby('client')['amount'].sum().reset_index()
                client_expenses.columns = ['Client', 'Expenses']
            else:
                client_expenses = pd.DataFrame(columns=['Client', 'Expenses'])

            # Combine client data
            client_summary = client_revenue.merge(client_labor, on='Client', how='outer')
            client_summary = client_summary.merge(client_expenses, on='Client', how='outer').fillna(0)
            client_summary['Total Cost'] = client_summary['Labor Cost'] + client_summary['Expenses']
            client_summary['Profit'] = client_summary['Revenue'] - client_summary['Total Cost']
            client_summary['Margin %'] = (client_summary['Profit'] / client_summary['Revenue'] * 100).fillna(0)

            # Sort by revenue descending
            client_summary = client_summary.sort_values('Revenue', ascending=False)

            # Chart 1: Revenue by Client (Pie)
            col1, col2 = st.columns(2)

            with col1:
                fig_pie = px.pie(
                    client_summary,
                    values='Revenue',
                    names='Client',
                    title=f"Revenue by Client - {selected_year}"
                )
                st.plotly_chart(fig_pie, width='stretch')

            with col2:
                # Chart 2: Profit Margin by Client (Bar)
                fig_margin = go.Figure()
                fig_margin.add_trace(go.Bar(
                    x=client_summary['Client'],
                    y=client_summary['Margin %'],
                    marker_color=client_summary['Margin %'].apply(
                        lambda x: '#27AE60' if x > 20 else '#F39C12' if x > 0 else '#E74C3C'
                    ),
                    text=client_summary['Margin %'].apply(lambda x: f"{x:.1f}%"),
                    textposition='outside'
                ))
                fig_margin.update_layout(
                    title=f"Profit Margin by Client - {selected_year}",
                    xaxis_title="Client",
                    yaxis_title="Margin %",
                    height=400
                )
                st.plotly_chart(fig_margin, width='stretch')

            # Client summary table
            st.markdown("##### Client Summary")
            display_client = client_summary.copy()
            display_client['Revenue'] = display_client['Revenue'].apply(lambda x: f"${x:,.0f}")
            display_client['Total Cost'] = display_client['Total Cost'].apply(lambda x: f"${x:,.0f}")
            display_client['Profit'] = display_client['Profit'].apply(lambda x: f"${x:,.0f}")
            display_client['Margin %'] = display_client['Margin %'].apply(lambda x: f"{x:.1f}%")

            st.dataframe(display_client, width='stretch', hide_index=True)
        else:
            st.info(f"No data found for {selected_year}")

    with tab3:
        st.markdown("#### 🔮 Full Year Forecast")

        # Projection method toggle
        projection_method = st.radio(
            "Projection Method",
            options=["Allocations-Based", "Simple Average"],
            horizontal=True,
            help="Allocations-Based uses planned allocations for future months. Simple Average uses YTD monthly average."
        )

        # Get current month
        current_month = datetime.now().month

        # Only show forecast for current year
        if selected_year == current_year:
            # Calculate YTD months and remaining months
            ytd_months = current_month
            remaining_months = 12 - current_month

            if not time_entries_df.empty:
                # YTD actuals by month
                ytd_df = time_entries_df.copy()
                ytd_df['month_num'] = ytd_df['date'].dt.month
                ytd_monthly = ytd_df.groupby('month_num')['revenue'].sum().to_dict()

                # Calculate projections
                forecast_data = []

                if projection_method == "Simple Average":
                    # Simple average of YTD months
                    ytd_avg = ytd_revenue / ytd_months if ytd_months > 0 else 0
                    projected_remaining = ytd_avg * remaining_months

                    # Build full year forecast
                    for month in range(1, 13):
                        if month <= current_month:
                            # Actual data
                            revenue = ytd_monthly.get(month, 0)
                            data_type = 'Actual'
                        else:
                            # Projected
                            revenue = ytd_avg
                            data_type = 'Projected (Avg)'

                        forecast_data.append({
                            'Month': month,
                            'Month Name': datetime(selected_year, month, 1).strftime('%B'),
                            'Revenue': revenue,
                            'Type': data_type
                        })

                else:  # Allocations-Based
                    # Use allocations for smart projections
                    if not allocations_df.empty:
                        # Get projected data from allocations
                        projected_monthly = {}

                        for month_num in range(current_month + 1, 13):
                            month_str = f"{selected_year}-{month_num:02d}"
                            month_allocs = allocations_df[
                                allocations_df['allocation_date'].dt.strftime('%Y-%m') == month_str
                            ]

                            if not month_allocs.empty:
                                # Calculate projected revenue from allocations
                                # allocated_fte × bill_rate × working_days × 8 hours/day
                                months_df = db.get_months()
                                month_info = months_df[
                                    (months_df['year'] == selected_year) &
                                    (months_df['month'] == month_num)
                                ]

                                if not month_info.empty:
                                    working_days = month_info['working_days'].iloc[0]

                                    month_revenue = 0
                                    for _, alloc in month_allocs.iterrows():
                                        if pd.notna(alloc.get('bill_rate')) and pd.notna(alloc.get('allocated_fte')):
                                            hours = working_days * alloc['allocated_fte'] * 8
                                            month_revenue += hours * alloc['bill_rate']

                                    projected_monthly[month_num] = month_revenue

                        # Build full year forecast
                        for month in range(1, 13):
                            if month <= current_month:
                                # Actual data
                                revenue = ytd_monthly.get(month, 0)
                                data_type = 'Actual'
                            else:
                                # Projected from allocations
                                revenue = projected_monthly.get(month, 0)
                                data_type = 'Projected (Alloc)'

                            forecast_data.append({
                                'Month': month,
                                'Month Name': datetime(selected_year, month, 1).strftime('%B'),
                                'Revenue': revenue,
                                'Type': data_type
                            })
                    else:
                        st.warning("No allocation data available for future months. Using Simple Average instead.")
                        # Fall back to simple average
                        ytd_avg = ytd_revenue / ytd_months if ytd_months > 0 else 0

                        for month in range(1, 13):
                            if month <= current_month:
                                revenue = ytd_monthly.get(month, 0)
                                data_type = 'Actual'
                            else:
                                revenue = ytd_avg
                                data_type = 'Projected (Avg)'

                            forecast_data.append({
                                'Month': month,
                                'Month Name': datetime(selected_year, month, 1).strftime('%B'),
                                'Revenue': revenue,
                                'Type': data_type
                            })

                forecast_df = pd.DataFrame(forecast_data)

                # Calculate full year projection
                full_year_projected = forecast_df['Revenue'].sum()
                projected_remaining_rev = forecast_df[forecast_df['Type'].str.contains('Projected')]['Revenue'].sum()

                # Display forecast metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("YTD Actual", f"${ytd_revenue:,.0f}")
                with col2:
                    st.metric("Projected Remaining", f"${projected_remaining_rev:,.0f}")
                with col3:
                    st.metric("Full Year Forecast", f"${full_year_projected:,.0f}")

                # Chart: Full year forecast
                fig = go.Figure()

                # Actual bars
                actual_data = forecast_df[forecast_df['Type'] == 'Actual']
                fig.add_trace(go.Bar(
                    name='Actual',
                    x=actual_data['Month Name'],
                    y=actual_data['Revenue'],
                    marker_color='#2E86C1'
                ))

                # Projected bars
                projected_data = forecast_df[forecast_df['Type'].str.contains('Projected')]
                fig.add_trace(go.Bar(
                    name='Projected',
                    x=projected_data['Month Name'],
                    y=projected_data['Revenue'],
                    marker_color='#85C1E2',
                    marker_pattern_shape="/"
                ))

                fig.update_layout(
                    title=f"Full Year Revenue Forecast - {selected_year}",
                    xaxis_title="Month",
                    yaxis_title="Revenue ($)",
                    height=400,
                    hovermode='x unified'
                )

                st.plotly_chart(fig, width='stretch')

                # Forecast table
                st.markdown("##### Monthly Forecast")
                display_forecast = forecast_df.copy()
                display_forecast['Revenue'] = display_forecast['Revenue'].apply(lambda x: f"${x:,.0f}")
                display_forecast = display_forecast[['Month Name', 'Revenue', 'Type']]
                display_forecast.columns = ['Month', 'Revenue', 'Data Type']

                st.dataframe(display_forecast, width='stretch', hide_index=True)
            else:
                st.info(f"No data found for {selected_year}")
        else:
            # For past/future years, just show actuals
            st.info(f"Forecast is only available for the current year ({current_year}). Showing actual data for {selected_year}.")

            if not time_entries_df.empty:
                # Show actual monthly revenue for selected year
                ytd_df = time_entries_df.copy()
                ytd_df['month_num'] = ytd_df['date'].dt.month
                monthly_actual = ytd_df.groupby('month_num')['revenue'].sum().reset_index()
                monthly_actual['Month Name'] = monthly_actual['month_num'].apply(
                    lambda x: datetime(selected_year, x, 1).strftime('%B')
                )
                monthly_actual = monthly_actual.rename(columns={'revenue': 'Revenue'})

                # Chart
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=monthly_actual['Month Name'],
                    y=monthly_actual['Revenue'],
                    marker_color='#2E86C1'
                ))

                fig.update_layout(
                    title=f"Actual Revenue by Month - {selected_year}",
                    xaxis_title="Month",
                    yaxis_title="Revenue ($)",
                    height=400
                )

                st.plotly_chart(fig, width='stretch')

                # Table
                display_actual = monthly_actual[['Month Name', 'Revenue']].copy()
                display_actual['Revenue'] = display_actual['Revenue'].apply(lambda x: f"${x:,.0f}")
                st.dataframe(display_actual, width='stretch', hide_index=True)


# ============================================================================
# MAIN PAGE LOGIC - Lazy Loading Pattern
# ============================================================================

st.markdown("### 📑 Reports")

# Lazy loading: Use radio buttons to select report and only render the active one
report_names = [
    "Allocation Coverage Analysis",
    "Monthly Resource Allocation",
    "Project Financial Summary",
    "Financial Analysis"
]

selected_report = st.radio(
    "Select Report",
    report_names,
    horizontal=True,
    key="report_selector",
    label_visibility="collapsed"
)

st.markdown("---")

# Lazy render: Only execute the selected report's function
if selected_report == "Allocation Coverage Analysis":
    render_allocation_coverage_report()
elif selected_report == "Monthly Resource Allocation":
    render_monthly_allocation_report()
elif selected_report == "Project Financial Summary":
    render_financial_summary_report()
elif selected_report == "Financial Analysis":
    render_financial_analysis_report()
