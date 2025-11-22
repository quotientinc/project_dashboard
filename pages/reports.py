import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 📑 Reports (🚨not ready yet)")

# Function definitions
def generate_executive_summary(db, processor):
    st.markdown("#### Executive Summary Report")

    # Date range
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date")
    with col2:
        end_date = st.date_input("End Date")

    if st.button("Generate Report"):
        # Load data
        projects_df = db.get_projects()
        employees_df = db.get_employees()
        expenses_df = db.get_expenses()

        # Report header
        st.markdown(f"### Report Period: {start_date} to {end_date}")
        st.markdown(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Executive metrics
        st.markdown("#### Key Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Active Projects", len(projects_df[projects_df['status'] == 'Active']))
        with col2:
            st.metric("Total Revenue", f"${projects_df['revenue_actual'].sum():,.0f}")
        with col3:
            st.metric("Total Costs", f"${projects_df['budget_used'].sum():,.0f}")
        with col4:
            profit = projects_df['revenue_actual'].sum() - projects_df['budget_used'].sum()
            st.metric("Net Profit", f"${profit:,.0f}")

        # Project summary
        st.markdown("#### Project Summary")
        summary_df = projects_df[['name', 'status', 'contract_value', 'budget_used', 'revenue_actual']].copy()
        summary_df['Budget Variance'] = summary_df['contract_value'] - summary_df['budget_used']
        st.dataframe(summary_df, width='stretch', hide_index=True)

        # Download option
        if st.button("Download Report"):
            csv = summary_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"executive_summary_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

def generate_project_status_report(db, processor):
    st.markdown("#### Project Status Report")

    projects_df = db.get_projects()

    if not projects_df.empty:
        selected_project = st.selectbox("Select Project", projects_df['name'].tolist())

        if st.button("Generate Report"):
            project = projects_df[projects_df['name'] == selected_project].iloc[0]
            allocations_df = db.get_allocations(project_id=project['id'])
            expenses_df = db.get_expenses(project_id=project['id'])

            # Project header
            st.markdown(f"### {project['name']}")
            st.markdown(f"**Client:** {project['client']}")
            st.markdown(f"**Status:** {project['status']}")
            st.markdown(f"**Project Manager:** {project['project_manager']}")

            # Progress metrics
            col1, col2, col3 = st.columns(3)

            with col1:
                budget_progress = (project['budget_used'] / project['contract_value'] * 100) if project['contract_value'] > 0 else 0
                st.metric("Budget Progress", f"{budget_progress:.1f}%")
                st.progress(min(budget_progress / 100, 1.0))

            with col2:
                revenue_progress = (project['revenue_actual'] / project['revenue_projected'] * 100) if project['revenue_projected'] > 0 else 0
                st.metric("Revenue Progress", f"{revenue_progress:.1f}%")
                st.progress(min(revenue_progress / 100, 1.0))

            with col3:
                if pd.notna(project['start_date']) and pd.notna(project['end_date']):
                    days_total = (pd.to_datetime(project['end_date']) - pd.to_datetime(project['start_date'])).days
                    days_elapsed = (datetime.now() - pd.to_datetime(project['start_date'])).days
                    time_progress = (days_elapsed / days_total * 100) if days_total > 0 else 0
                    st.metric("Time Progress", f"{time_progress:.1f}%")
                    st.progress(min(time_progress / 100, 1.0))
                else:
                    st.metric("Time Progress", "N/A")
                    st.caption("Project dates not defined")

            # Team allocation
            if not allocations_df.empty:
                st.markdown("#### Team Allocation")
                st.dataframe(
                    allocations_df[['employee_name', 'role', 'allocated_fte']],
                    width='stretch',
                    hide_index=True
                )

def generate_resource_report(db, processor):
    st.markdown("#### Resource Utilization Report")

    period = st.selectbox("Select Period", ["Current Month", "Last Month", "Past 90 Days", "Custom"])

    # Set date range based on period selection
    today = datetime.now()

    # Initialize dates
    start_date = None
    end_date = None

    if period == "Current Month":
        start_date = datetime(today.year, today.month, 1)
        end_date = today
    elif period == "Last Month":
        # Get first day of last month
        first_day_this_month = datetime(today.year, today.month, 1)
        last_day_last_month = first_day_this_month - pd.Timedelta(days=1)
        start_date = datetime(last_day_last_month.year, last_day_last_month.month, 1)
        end_date = last_day_last_month
    elif period == "Past 90 Days":
        # Get quarter start (simplified to last 90 days)
        end_date = today
        start_date = today - pd.Timedelta(days=90)

    # Show custom date inputs if Custom period is selected
    if period == "Custom":
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=today - pd.Timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", value=today)
    else:
        # Show selected period range for non-custom periods
        st.info(f"Report Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    if st.button("Generate Report"):
        employees_df = db.get_employees()
        allocations_df = db.get_allocations()

        # Filter time entries by the selected period
        time_entries_df = db.get_time_entries(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )

        if not employees_df.empty:
            # TODO: This is not accurate
            utilization_df = processor.calculate_employee_utilization(
                employees_df, allocations_df, time_entries_df
            )

            # Summary metrics
            st.markdown("#### Utilization Summary")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Average Utilization", f"{utilization_df['utilization_rate'].mean():.1f}%")
            with col2:
                st.metric("Total Billable Hours", f"{utilization_df['billable_hours'].sum():.0f}")
            with col3:
                st.metric("Revenue Generated", f"${utilization_df['revenue_generated'].sum():,.0f}")

            # Detailed table
            st.markdown("#### Employee Details")
            display_df = utilization_df[['name', 'utilization_rate', 'billable_hours', 'revenue_generated']]
            st.dataframe(display_df, width='stretch', hide_index=True)

            # Utilization chart
            fig = px.bar(
                utilization_df,
                x='name',
                y='utilization_rate',
                title="Utilization by Employee"
            )
            st.plotly_chart(fig, width='stretch')

def generate_financial_report(db, processor):
    st.markdown("#### Financial Report")

    report_period = st.selectbox(
        "Report Period",
        ["Monthly", "Quarterly", "Annual", "Custom"]
    )

    if st.button("Generate Report"):
        projects_df = db.get_projects()
        expenses_df = db.get_expenses()

        # Financial summary
        st.markdown("#### Financial Summary")

        total_revenue = projects_df['revenue_actual'].sum()
        total_costs = projects_df['budget_used'].sum()
        gross_profit = total_revenue - total_costs
        profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Revenue", f"${total_revenue:,.0f}")
        with col2:
            st.metric("Total Costs", f"${total_costs:,.0f}")
        with col3:
            st.metric("Gross Profit", f"${gross_profit:,.0f}")
        with col4:
            st.metric("Profit Margin", f"{profit_margin:.1f}%")

        # Project financials
        st.markdown("#### Project Financials")
        financial_df = projects_df[['name', 'revenue_actual', 'budget_used']].copy()
        financial_df['Profit'] = financial_df['revenue_actual'] - financial_df['budget_used']
        financial_df['Margin %'] = (financial_df['Profit'] / financial_df['revenue_actual'] * 100).round(1)
        st.dataframe(financial_df, width='stretch', hide_index=True)

        # Expense breakdown
        if not expenses_df.empty:
            st.markdown("#### Expense Breakdown")
            expense_summary = expenses_df.groupby('category')['amount'].sum().reset_index()

            fig = px.pie(
                expense_summary,
                values='amount',
                names='category',
                title="Expenses by Category"
            )
            st.plotly_chart(fig, width='stretch')

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
                # Only use bill_rate if it exists in the allocation record
                bill_rate = alloc['bill_rate'] if pd.notna(alloc.get('bill_rate')) and alloc.get('bill_rate') != 0 else ''

                template_rows.append({
                    'employee_id': emp_id,
                    'employee_name': emp_name,  # For preview only, not in export
                    'project_id': project_id,
                    'allocation_date': month_key,
                    'allocated_fte': alloc['allocated_fte'],
                    'bill_rate': bill_rate,
                    'role': alloc.get('role', default_role) if pd.notna(alloc.get('role')) else default_role,
                    'status': 'Existing'  # For preview only
                })
                existing_count += 1
            else:
                # Create placeholder row for missing allocation
                # Leave bill_rate empty - user should set appropriate rate
                template_rows.append({
                    'employee_id': emp_id,
                    'employee_name': emp_name,  # For preview only
                    'project_id': project_id,
                    'allocation_date': month_key,
                    'allocated_fte': 0.0,  # User needs to fill this in
                    'bill_rate': '',  # Empty - user should set appropriate billing rate
                    'role': default_role,
                    'status': 'New'  # For preview only
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

    # Display preview with status column
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

    # Export CSV (remove preview-only columns)
    export_df = template_df[['employee_id', 'employee_name', 'project_id', 'allocation_date', 'allocated_fte', 'bill_rate', 'role']].copy()
    csv = export_df.to_csv(index=False)

    st.markdown("#### Download")
    st.download_button(
        label="📥 Download CSV Template",
        data=csv,
        file_name=f"allocations_{project_id}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        type="primary",
        width='stretch'
    )

    st.info(
        "💡 **Next Steps:**\n"
        "1. Download the CSV template\n"
        "2. Fill in `allocated_fte` values for rows marked 'New' (e.g., 0.5 for 50% allocation)\n"
        "3. Fill in `bill_rate` values if empty (hourly billing rate)\n"
        "4. Adjust `role` if needed\n"
        "5. Import via **Data Management → Import Data → Import Allocation CSV**"
    )

def generate_allocation_gaps_report(db, processor):
    st.markdown("#### Projects Lacking Allocations Report")
    st.caption("Analysis of allocation coverage across all projects")

    # Load data
    projects_df = db.get_projects()
    allocations_df = db.get_allocations()

    # Get all projects (will be filtered by user selection below)
    all_projects = projects_df.copy()

    if all_projects.empty:
        st.info("No projects found.")
        return

    # Initialize lists to categorize projects
    no_allocations = []
    partial_coverage = []
    fully_allocated = []
    skipped_projects = []

    # Analyze each project
    project_details = []

    for _, project in all_projects.iterrows():
        project_id = project['id']
        project_name = project['name']
        client = project['client']
        status = project['status']

        # Check for missing dates
        start_date_str = project['start_date']
        end_date_str = project['end_date']

        # Skip projects without start_date or end_date
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
            # No allocations at all
            allocation_status = "❌ No Allocations"
            coverage_pct = 0
            months_covered = 0
            months_missing = total_months
            employee_count = 0
            total_fte = 0
            no_allocations.append(project_name)
        else:
            # Get unique allocation months
            allocation_months = pd.to_datetime(project_allocations['allocation_date']).dt.to_period('M').unique()
            months_covered = len(allocation_months)

            # Calculate coverage percentage
            coverage_pct = (months_covered / total_months * 100) if total_months > 0 else 0
            months_missing = total_months - months_covered

            # Get employee count and total FTE
            employee_count = project_allocations['employee_id'].nunique()
            total_fte = project_allocations.groupby('allocation_date')['allocated_fte'].sum().mean()

            # Classify allocation status
            if coverage_pct >= 100:
                allocation_status = "✅ Fully Allocated"
                fully_allocated.append(project_name)
            else:
                allocation_status = "⚠️ Partial Coverage"
                partial_coverage.append(project_name)

        # Add to project details
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

    # Create DataFrame
    details_df = pd.DataFrame(project_details)

    # Summary Cards
    st.markdown("#### Allocation Summary")
    col1, col2, col3, col4 = st.columns(4)

    analyzed_count = len(details_df)
    skipped_count = len(skipped_projects)

    with col1:
        st.metric(
            "Projects Analyzed",
            analyzed_count,
            help=f"Out of {len(all_projects)} total projects. {skipped_count} skipped (see below)."
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
    st.markdown("#### Project Details")

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

    # Filter by project status
    if project_status_filter != "All":
        filtered_df = filtered_df[filtered_df['Status'] == project_status_filter]

    # Filter by allocation status
    if allocation_status_filter != "All":
        filtered_df = filtered_df[filtered_df['Allocation Status'] == allocation_status_filter]

    # Display table with row selection for CSV template generation
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

    # Handle row selection - open dialog to generate CSV template
    if selection and selection.selection.rows:
        selected_idx = selection.selection.rows[0]
        selected_row = filtered_df.iloc[selected_idx]
        project_id = selected_row['Project ID']
        project_name = selected_row['Project Name']
        start_date = selected_row['Start Date']
        end_date = selected_row['End Date']

        # Open modal dialog for CSV template generation
        generate_allocation_csv_template(project_id, project_name, start_date, end_date)

    # Show totals
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
        file_name=f"allocation_gaps_report_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

    # Skipped Projects Section
    if skipped_projects:
        st.markdown("---")
        st.markdown("#### ⚠️ Projects Skipped (No Period of Performance Defined)")
        st.info(
            f"**{len(skipped_projects)} project(s)** were excluded from the allocation analysis above "
            f"because they are missing a start date and/or end date. Projects must have both dates "
            f"defined to calculate allocation coverage."
        )

        skipped_df = pd.DataFrame(skipped_projects)
        st.dataframe(
            skipped_df,
            width='stretch',
            hide_index=True
        )

        st.caption("💡 To include these projects in the analysis, please add start and end dates in the Projects page.")
    else:
        st.success("✅ All projects have defined periods of performance.")

def generate_custom_report(db, processor):
    st.markdown("#### Custom Report Builder")

    # Select data to include
    st.markdown("##### Select Data to Include")
    col1, col2, col3 = st.columns(3)

    with col1:
        include_projects = st.checkbox("Projects", value=True)
        include_employees = st.checkbox("Employees", value=True)
    with col2:
        include_financials = st.checkbox("Financials", value=True)
        include_allocations = st.checkbox("Allocations", value=True)
    with col3:
        include_expenses = st.checkbox("Expenses", value=True)
        include_time_entries = st.checkbox("Time Entries", value=False)

    # Filters
    st.markdown("##### Filters")
    projects_df = db.get_projects()

    selected_projects = st.multiselect(
        "Select Projects",
        projects_df['name'].tolist() if not projects_df.empty else []
    )

    date_range = st.date_input(
        "Date Range",
        value=(datetime.now() - pd.Timedelta(days=30), datetime.now()),
        key="custom_date_range"
    )

    if st.button("Generate Custom Report"):
        report_data = {}

        if include_projects:
            projects = db.get_projects()
            if selected_projects:
                projects = projects[projects['name'].isin(selected_projects)]
            report_data['Projects'] = projects

        if include_employees:
            report_data['Employees'] = db.get_employees()

        if include_allocations:
            report_data['Allocations'] = db.get_allocations()

        if include_expenses:
            report_data['Expenses'] = db.get_expenses()

        if include_time_entries and len(date_range) == 2:
            report_data['Time Entries'] = db.get_time_entries(
                start_date=date_range[0].strftime('%Y-%m-%d'),
                end_date=date_range[1].strftime('%Y-%m-%d')
            )

        # Display report
        for section, data in report_data.items():
            if not data.empty:
                st.markdown(f"#### {section}")
                st.dataframe(data, width='stretch', hide_index=True)

                # Download option for each section
                csv = data.to_csv(index=False)
                st.download_button(
                    label=f"Download {section} CSV",
                    data=csv,
                    file_name=f"{section.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key=f"download_{section}"
                )

def generate_resource_allocation_report(db, processor):
    """Generate monthly resource allocation report showing employee and project allocation status"""
    st.markdown("#### Resource Allocation by Month")
    st.caption("Visualize employee and project allocation status across the company")

    # Month selection
    col1, col2 = st.columns([2, 1])

    with col1:
        # Get available months from allocations
        allocations_df = db.get_allocations()

        if allocations_df.empty or 'allocation_date' not in allocations_df.columns:
            st.warning("No allocation data available. Please import allocations first.")
            return

        # Get unique months from allocations
        allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
        unique_months = allocations_df['allocation_date'].dt.to_period('M').unique()
        unique_months = sorted(unique_months, reverse=True)

        if len(unique_months) == 0:
            st.warning("No allocation data available.")
            return

        # Format month options for display
        month_options = {str(m): m.strftime('%B %Y') for m in unique_months}

        # Default to most recent month
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

    # Get working days for the selected month
    month_info = months_df[
        (months_df['year'] == selected_month.year) &
        (months_df['month'] == selected_month.month)
    ]
    working_days = month_info['working_days'].iloc[0] if not month_info.empty else 21

    st.divider()

    # === EMPLOYEE VIEW ===
    if view_mode == "Employee View":
        # Calculate employee allocation summary
        employee_summary = []

        for _, emp in employees_df.iterrows():
            emp_id = emp['id']
            emp_name = emp['name']
            emp_role = emp['role']
            target_fte = emp.get('target_allocation', 1.0) if pd.notna(emp.get('target_allocation')) else 1.0
            billable = emp.get('billable', 1)

            # Skip non-billable employees unless they have allocations
            emp_allocations = month_allocations[month_allocations['employee_id'] == emp_id]
            if emp_allocations.empty and billable == 0:
                continue

            # Calculate total allocated FTE
            total_allocated_fte = emp_allocations['allocated_fte'].sum() if not emp_allocations.empty else 0.0

            # Calculate variance
            variance_fte = total_allocated_fte - target_fte
            variance_pct = (total_allocated_fte / target_fte * 100) if target_fte > 0 else 0

            # Determine status
            if variance_pct > 100:
                status = "🔴 Over"
                status_color = "#ffcccc"
            elif variance_pct >= 80:
                status = "🟢 Healthy"
                status_color = "#ccffcc"
            else:
                status = "🟡 Under"
                status_color = "#fff9cc"

            # Get project list
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
                'Status': status,
                'Status Color': status_color
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
            st.metric(
                "Over-Allocated",
                over_allocated,
                delta=f"{over_pct:.1f}%",
                delta_color="inverse"
            )

        with col3:
            under_pct = (under_allocated / total_employees * 100) if total_employees > 0 else 0
            st.metric(
                "Under-Allocated",
                under_allocated,
                delta=f"{under_pct:.1f}%",
                delta_color="off"
            )

        with col4:
            healthy_pct = (healthy / total_employees * 100) if total_employees > 0 else 0
            st.metric(
                "Healthy Allocation",
                healthy,
                delta=f"{healthy_pct:.1f}%",
                delta_color="normal"
            )

        st.divider()

        # Alerts
        if over_allocated > 0:
            critical_over = summary_df[summary_df['Variance %'] > 120]
            if not critical_over.empty:
                st.warning(f"⚠️ **{len(critical_over)} employee(s) allocated >120%** - review workload: {', '.join(critical_over['Employee'].tolist()[:5])}")

        if under_allocated > total_employees * 0.3:
            st.info(f"📊 **{under_allocated} employees <80% allocated** - opportunities available for new projects")

        # Filter and sort options
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
                "Target FTE": st.column_config.NumberColumn(
                    "Target FTE",
                    format="%.2f"
                ),
                "Allocated FTE": st.column_config.NumberColumn(
                    "Allocated FTE",
                    format="%.2f"
                ),
                "Variance": st.column_config.NumberColumn(
                    "Variance",
                    format="%+.2f",
                    help="Allocated - Target"
                ),
                "Variance %": st.column_config.ProgressColumn(
                    "Utilization %",
                    format="%.1f%%",
                    min_value=0,
                    max_value=150
                )
            },
            height=500
        )

        # Visualization: Stacked bar chart
        st.divider()
        st.markdown("##### Allocation by Employee")

        # Prepare data for stacked bar chart
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

            # Create stacked bar chart
            fig = go.Figure()

            # Add bars for each project
            for project in chart_df['Project'].unique():
                project_data = chart_df[chart_df['Project'] == project]
                fig.add_trace(go.Bar(
                    name=project,
                    x=project_data['Employee'],
                    y=project_data['FTE'],
                    text=project_data['FTE'].apply(lambda x: f"{x:.2f}"),
                    textposition='inside'
                ))

            # Add target line
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

    # === PROJECT VIEW ===
    else:  # Project View
        # Calculate project allocation summary
        project_summary = []

        # Group allocations by project
        for project_id in month_allocations['project_id'].unique():
            project_allocations = month_allocations[month_allocations['project_id'] == project_id]

            # Get project details
            project = projects_df[projects_df['id'] == project_id]
            if project.empty:
                project_name = project_id
                project_status = "Unknown"
            else:
                project_name = project['name'].iloc[0]
                project_status = project['status'].iloc[0] if pd.notna(project['status'].iloc[0]) else "Active"

            # Calculate metrics
            total_fte = project_allocations['allocated_fte'].sum()
            employee_count = project_allocations['employee_id'].nunique()
            employees = project_allocations['employee_name'].unique().tolist()
            employees_str = ", ".join(employees[:3]) + (f" (+{len(employees)-3} more)" if len(employees) > 3 else "")

            # Calculate projected hours and revenue
            projected_hours = total_fte * working_days * 8

            # Calculate projected revenue (use bill_rate if available)
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

        # Check for active projects without allocations
        active_projects = projects_df[projects_df['status'].isin(['Active', 'Future'])]
        allocated_project_ids = month_allocations['project_id'].unique()
        unallocated_projects = active_projects[~active_projects['id'].isin(allocated_project_ids)]

        if not unallocated_projects.empty:
            st.warning(f"🔴 **{len(unallocated_projects)} active/future project(s) have no team allocations** for {selected_month.strftime('%B %Y')}")

        # Filter and sort options
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
                "Total FTE": st.column_config.NumberColumn(
                    "Total FTE",
                    format="%.2f"
                ),
                "Projected Hours": st.column_config.NumberColumn(
                    "Projected Hours",
                    format="%.0f"
                ),
                "Projected Revenue": st.column_config.NumberColumn(
                    "Projected Revenue",
                    format="$%.0f"
                )
            },
            height=500
        )

        # Visualization: Bar chart of FTE by project
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

# Report type selection
report_type = st.selectbox(
    "Select Report Type",
    ["Executive Summary", "Project Status Report", "Resource Utilization Report",
     "Financial Report", "Projects Lacking Allocations", "Resource Allocation by Month", "Custom Report"]
)

# Call the appropriate function
if report_type == "Executive Summary":
    generate_executive_summary(db, processor)
elif report_type == "Project Status Report":
    generate_project_status_report(db, processor)
elif report_type == "Resource Utilization Report":
    generate_resource_report(db, processor)
elif report_type == "Financial Report":
    generate_financial_report(db, processor)
elif report_type == "Projects Lacking Allocations":
    generate_allocation_gaps_report(db, processor)
elif report_type == "Resource Allocation by Month":
    generate_resource_allocation_report(db, processor)
else:
    generate_custom_report(db, processor)