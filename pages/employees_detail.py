"""
Employee Detail (Edit) tab - manage employee data and project allocations with subtabs.

Exports three functions:
  - render_project_allocations_subtab(db, processor, employee_id)
  - render_employee_edit_tab(db, processor, employee_id)
  - render_employee_detail_tab(db, processor, employee_id, default_subtab)  [legacy wrapper]
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import calendar
from datetime import datetime


def render_project_allocations_subtab(db, processor, employee_id):
    """Render the Project Allocations subtab: FTE matrix editor + allocation overview.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        employee_id: The employee ID to show allocations for.
    """
    employees_df = db.get_employees()
    employee_match = employees_df[employees_df['id'] == employee_id]
    if employee_match.empty:
        st.error(f"Employee {employee_id} not found")
        return
    employee = employee_match.iloc[0]

    st.markdown("#### Project Allocation Management")

    # Get employee target FTE (accounting for overhead)
    target_fte = employee.get('target_allocation', 1.0) - employee.get('overhead_allocation', 0.0)

    # Current allocations
    allocations_df = db.get_allocations(employee_id=employee_id)

    # Parse allocation dates
    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
    allocations_df['year'] = allocations_df['allocation_date'].dt.year
    allocations_df['month'] = allocations_df['allocation_date'].dt.month

    # Get available years (or default to current year if no allocations)
    if not allocations_df.empty:
        available_years = sorted(allocations_df['year'].unique(), reverse=True)
    else:
        available_years = [pd.Timestamp.now().year]

    st.markdown("##### Project Allocations by Month")

    # Year selector
    selected_year = st.selectbox(
        "Select Year",
        options=available_years,
        key=f"alloc_year_select_{employee_id}"
    )

    # Filter to selected year
    if not allocations_df.empty:
        year_allocs = allocations_df[allocations_df['year'] == selected_year].copy()
        unique_projects = year_allocs[['project_id', 'project_name']].drop_duplicates()
    else:
        year_allocs = pd.DataFrame()
        unique_projects = pd.DataFrame()

    # Get all projects for dropdown
    projects_df = db.get_projects()

    # Build table with projects as rows, months as columns
    table_rows = []

    if not unique_projects.empty:
        for _, proj in unique_projects.iterrows():
            proj_allocs = year_allocs[year_allocs['project_id'] == proj['project_id']]

            # Get role from any allocation record
            role = proj_allocs['role'].iloc[0] if pd.notna(proj_allocs['role'].iloc[0]) else ''

            row = {
                'project_id': proj['project_id'],
                'project_name': proj['project_name'],
                'role': role
            }

            # Add columns for each month (Jan-Dec)
            for month_num in range(1, 13):
                month_data = proj_allocs[proj_allocs['month'] == month_num]

                if not month_data.empty:
                    row[f'fte_{month_num}'] = float(month_data['allocated_fte'].iloc[0])
                    row[f'rate_{month_num}'] = float(month_data['bill_rate'].iloc[0]) if pd.notna(month_data['bill_rate'].iloc[0]) else 0.0
                else:
                    row[f'fte_{month_num}'] = 0.0
                    row[f'rate_{month_num}'] = 0.0

            table_rows.append(row)

    # Create DataFrame (with correct columns even if empty)
    if table_rows:
        editor_df = pd.DataFrame(table_rows)
    else:
        columns = ['project_id', 'project_name', 'role']
        for month_num in range(1, 13):
            columns.extend([f'fte_{month_num}', f'rate_{month_num}'])
        editor_df = pd.DataFrame(columns=columns)

    # Store original for change detection
    if 'original_employee_allocations' not in st.session_state or st.session_state.get('current_employee_id') != employee_id or st.session_state.get('current_alloc_year') != selected_year:
        st.session_state.original_employee_allocations = editor_df.copy()
        st.session_state.current_employee_id = employee_id
        st.session_state.current_alloc_year = selected_year

    # Build column configuration
    column_config = {
        'project_id': None,  # Hide project_id (it's a TEXT field, not numeric)
        'project_name': st.column_config.SelectboxColumn(
            'Project',
            help='Select project to add',
            options=projects_df['name'].tolist(),
            required=True,
            width='medium'
        ),
        'role': st.column_config.TextColumn(
            'Role',
            help='Your role on this project',
            max_chars=50,
            width='medium'
        )
    }

    # Add month columns - alternating FTE and Rate
    for month_num in range(1, 13):
        month_abbr = pd.Timestamp(year=selected_year, month=month_num, day=1).strftime('%b')

        # FTE column
        column_config[f'fte_{month_num}'] = st.column_config.NumberColumn(
            f'{month_abbr} FTE',
            help=f'FTE allocation for {month_abbr} {selected_year} (0.0-2.0)',
            min_value=0.0,
            max_value=2.0,
            step=0.05,
            format='%.2f',
            width='small'
        )

        # Bill Rate column
        column_config[f'rate_{month_num}'] = st.column_config.NumberColumn(
            f'{month_abbr} Rate',
            help=f'Hourly bill rate for {month_abbr} {selected_year}',
            min_value=0.0,
            max_value=500.0,
            step=5.0,
            format='$%.2f',
            width='small'
        )

    # Display editable table
    edited_df = st.data_editor(
        editor_df,
        column_config=column_config,
        width='stretch',
        hide_index=True,
        num_rows="dynamic",  # Allow adding/deleting rows
        key=f'employee_allocation_editor_{employee_id}_{selected_year}',
        height=400
    )

    # Info helper
    st.caption("""
Tips:
- Click + to add a new project row
- Click the trash icon to remove a project
- Edit FTE values (0.0-2.0) and Bill Rates per month
- Only months with non-zero FTE or Rate will create allocation records
- Changes are saved when you click Save Changes
    """)

    # Calculate and display monthly totals
    st.markdown("##### Monthly Totals")
    total_cols = st.columns(12)

    for month_num in range(1, 13):
        month_abbr = pd.Timestamp(year=selected_year, month=month_num, day=1).strftime('%b')
        month_total = edited_df[f'fte_{month_num}'].sum()

        # Calculate allocation percentage
        allocation_pct = (month_total / target_fte * 100) if target_fte > 0 else 0

        # Determine color based on allocation
        if allocation_pct > 120:
            emoji = "🔴"
        elif allocation_pct >= 100:
            emoji = "🟡"
        elif allocation_pct >= 80:
            emoji = "🟢"
        else:
            emoji = "🔵"

        with total_cols[month_num - 1]:
            st.metric(
                label=month_abbr,
                value=f"{month_total:.2f}",
                delta=f"{allocation_pct:.0f}% {emoji}",
                help=f"Target: {target_fte:.2f} FTE"
            )

    # Detect changes
    changes = []
    new_projects = []
    deleted_projects = []

    # Check for new rows (project_id is empty/NaN for new)
    for idx, row in edited_df.iterrows():
        proj_id = row.get('project_id')
        # Check if project_id is empty, NaN, or empty string
        if pd.isna(proj_id) or proj_id == '' or proj_id == 0:
            # New project - need to create allocations
            project_name = row.get('project_name')
            if project_name:
                # Look up project_id from projects_df
                proj_match = projects_df[projects_df['name'] == project_name]
                if not proj_match.empty:
                    new_projects.append({
                        'idx': idx,
                        'project_id': proj_match.iloc[0]['id'],  # Keep as TEXT
                        'project_name': project_name,
                        'role': row.get('role', ''),
                        'row': row
                    })

    # Check for deleted rows (in original but not in edited)
    original_ids = set(st.session_state.original_employee_allocations['project_id'].dropna())
    edited_ids = set(edited_df['project_id'].dropna())
    deleted_ids = original_ids - edited_ids

    if deleted_ids:
        for proj_id in deleted_ids:
            proj_name = st.session_state.original_employee_allocations[
                st.session_state.original_employee_allocations['project_id'] == proj_id
            ]['project_name'].iloc[0]
            deleted_projects.append({'project_id': proj_id, 'project_name': proj_name})

    # Check for modified values (FTE or Rate changed)
    for idx, row in edited_df.iterrows():
        proj_id = row.get('project_id')

        # Skip if project_id is empty/NaN (new rows handled above)
        if pd.notna(proj_id) and proj_id != '' and proj_id != 0:
            # Find original row (project_id is TEXT, no conversion needed)
            orig_row = st.session_state.original_employee_allocations[
                st.session_state.original_employee_allocations['project_id'] == proj_id
            ]

            if not orig_row.empty:
                orig_row = orig_row.iloc[0]

                # Check each month for changes
                for month_num in range(1, 13):
                    # Check FTE change
                    orig_fte = orig_row.get(f'fte_{month_num}', 0.0)
                    new_fte = row.get(f'fte_{month_num}', 0.0)

                    # Check Rate change
                    orig_rate = orig_row.get(f'rate_{month_num}', 0.0)
                    new_rate = row.get(f'rate_{month_num}', 0.0)

                    if orig_fte != new_fte or orig_rate != new_rate:
                        month_abbr = pd.Timestamp(year=selected_year, month=month_num, day=1).strftime('%b')
                        changes.append({
                            'project_id': proj_id,
                            'project_name': row.get('project_name'),
                            'month_num': month_num,
                            'month_abbr': month_abbr,
                            'orig_fte': orig_fte,
                            'new_fte': new_fte,
                            'orig_rate': orig_rate,
                            'new_rate': new_rate,
                            'role': row.get('role', '')
                        })

    # Count total changes
    total_changes = len(changes) + len(new_projects) + len(deleted_projects)

    # Show save button if changes detected
    if total_changes > 0:
        col1, col2 = st.columns([4, 1])

        with col1:
            # Summary of changes
            change_summary = []
            if new_projects:
                change_summary.append(f"{len(new_projects)} project(s) added")
            if deleted_projects:
                change_summary.append(f"{len(deleted_projects)} project(s) removed")
            if changes:
                change_summary.append(f"{len(changes)} allocation(s) modified")

            st.info(f"Unsaved changes: {', '.join(change_summary)}")

        with col2:
            if st.button("Save Changes", type="primary", key=f"save_emp_alloc_{employee_id}"):
                try:
                    # Process deletions first
                    for deleted in deleted_projects:
                        # Delete all allocations for this project for this employee in this year
                        proj_allocs = allocations_df[
                            (allocations_df['project_id'] == deleted['project_id']) &
                            (allocations_df['year'] == selected_year)
                        ]
                        for _, alloc in proj_allocs.iterrows():
                            db.delete_allocation(alloc['id'])

                    # Process new projects
                    for new_proj in new_projects:
                        # Create allocation records for months with non-zero FTE or Rate
                        for month_num in range(1, 13):
                            fte_val = new_proj['row'].get(f'fte_{month_num}', 0.0)
                            rate_val = new_proj['row'].get(f'rate_{month_num}', 0.0)

                            # Only create if FTE or Rate is non-zero
                            if fte_val != 0.0 or rate_val != 0.0:
                                allocation_date = f"{selected_year}-{month_num:02d}"
                                db.add_allocation({
                                    'project_id': new_proj['project_id'],
                                    'employee_id': employee_id,
                                    'allocated_fte': float(fte_val),
                                    'allocation_date': allocation_date,
                                    'role': new_proj['role'],
                                    'bill_rate': float(rate_val)
                                })

                    # Process modifications
                    for change in changes:
                        allocation_date = f"{selected_year}-{change['month_num']:02d}"

                        # Find existing allocation record
                        existing = allocations_df[
                            (allocations_df['project_id'] == change['project_id']) &
                            (allocations_df['employee_id'] == employee_id) &
                            (allocations_df['month'] == change['month_num']) &
                            (allocations_df['year'] == selected_year)
                        ]

                        if not existing.empty:
                            # Update existing record
                            allocation_id = existing.iloc[0]['id']
                            db.update_allocation(allocation_id, {
                                'allocated_fte': float(change['new_fte']),
                                'bill_rate': float(change['new_rate']),
                                'role': change['role']
                            })
                        else:
                            # Create new record (project exists but no allocation for this month)
                            if change['new_fte'] != 0.0 or change['new_rate'] != 0.0:
                                db.add_allocation({
                                    'project_id': change['project_id'],
                                    'employee_id': employee_id,
                                    'allocated_fte': float(change['new_fte']),
                                    'allocation_date': allocation_date,
                                    'role': change['role'],
                                    'bill_rate': float(change['new_rate'])
                                })

                    # Clear session state and show success
                    if 'original_employee_allocations' in st.session_state:
                        del st.session_state.original_employee_allocations
                    if 'current_employee_id' in st.session_state:
                        del st.session_state.current_employee_id
                    if 'current_alloc_year' in st.session_state:
                        del st.session_state.current_alloc_year

                    st.success(f"Successfully saved {total_changes} change(s)!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error saving changes: {str(e)}")
    else:
        st.success("All allocations saved")

    # ===========================
    # Allocation Overview Section
    # ===========================
    st.markdown("---")
    st.markdown("#### Allocation Overview")
    st.caption("Allocated hours vs possible hours for this employee")

    # Month selector for allocation overview
    alloc_col1, alloc_col2 = st.columns([1, 1])

    with alloc_col1:
        # Use the same year as the FTE matrix above (selected_year variable)
        st.caption(f"Year: {selected_year}")

    with alloc_col2:
        current_month = datetime.now().month
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        alloc_month_name = st.selectbox(
            "Month",
            options=month_names,
            index=current_month - 1,
            key="emp_alloc_overview_month"
        )
        alloc_month = month_names.index(alloc_month_name) + 1

    # Build date range
    alloc_start = f"{selected_year}-{alloc_month:02d}-01"
    alloc_last_day = calendar.monthrange(selected_year, alloc_month)[1]
    alloc_end = f"{selected_year}-{alloc_month:02d}-{alloc_last_day}"

    # Get performance metrics
    alloc_metrics = processor.get_performance_metrics(
        start_date=alloc_start,
        end_date=alloc_end
    )

    # Get months data for working days
    months_df = db.get_months()

    emp_id_str = str(employee_id)
    month_key = f"{month_names[alloc_month - 1]} {selected_year}"

    # Calculate possible hours
    possible_month_data = alloc_metrics['possible'].get(month_key, {})
    emp_possible = possible_month_data.get(emp_id_str, {})
    possible_hours = emp_possible.get('hours', 0)

    # Calculate allocated hours (from projected/allocations)
    projected_month_data = alloc_metrics['projected'].get(month_key, {})
    emp_projected = projected_month_data.get(emp_id_str, {})
    allocated_hours = emp_projected.get('hours', 0)

    # Calculate allocation %
    allocation_pct = (allocated_hours / possible_hours * 100) if possible_hours > 0 else 0
    variance = allocated_hours - possible_hours

    # Determine status
    if allocation_pct > 120:
        status = "Over-Allocated"
        status_color = "#ff4444"
        status_icon = "🔴"
    elif allocation_pct > 100:
        status = "At Capacity"
        status_color = "#ffaa00"
        status_icon = "🟡"
    elif allocation_pct >= 80:
        status = "Healthy"
        status_color = "#2E7D32"
        status_icon = "🟢"
    else:
        status = "Under-Allocated"
        status_color = "#4488ff"
        status_icon = "🔵"

    # Display metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Possible Hours", f"{possible_hours:.1f}")
    with m2:
        st.metric("Allocated Hours", f"{allocated_hours:.1f}")
    with m3:
        st.metric("Allocation %", f"{allocation_pct:.1f}%")
    with m4:
        st.metric("Variance", f"{variance:+.1f} hrs")

    st.markdown(f"**Status:** {status_icon} {status}")

    # Project allocation breakdown
    all_allocations_df = db.get_allocations()
    if not all_allocations_df.empty:
        all_allocations_df['allocation_date'] = pd.to_datetime(all_allocations_df['allocation_date'])
        emp_allocs = all_allocations_df[
            (all_allocations_df['employee_id'] == employee_id) &
            (all_allocations_df['allocation_date'].dt.strftime('%Y-%m') == f"{selected_year}-{alloc_month:02d}")
        ]

        if not emp_allocs.empty:
            month_info = months_df[(months_df['year'] == selected_year) & (months_df['month'] == alloc_month)]
            working_days = int(month_info['working_days'].iloc[0]) if not month_info.empty else 21
            holidays = month_info['holidays'].iloc[0] if not month_info.empty and 'holidays' in month_info.columns else 0
            holidays = holidays if pd.notna(holidays) else 0
            available_days = max(working_days - holidays, 0)

            breakdown = []
            for _, alloc in emp_allocs.iterrows():
                allocated_fte = alloc.get('allocated_fte', 0)
                alloc_hours = allocated_fte * available_days * 8
                breakdown.append({
                    'Project': alloc.get('project_name', 'Unknown'),
                    'Allocated FTE': round(allocated_fte, 2),
                    'Allocated Hours': round(alloc_hours, 1),
                })

            breakdown_df = pd.DataFrame(breakdown)
            if not breakdown_df.empty:
                total_hours = breakdown_df['Allocated Hours'].sum()
                breakdown_df['% of Total'] = (breakdown_df['Allocated Hours'] / total_hours * 100).round(1)
                breakdown_df = breakdown_df.sort_values('Allocated Hours', ascending=False)

                st.markdown("##### Allocation by Project")
                st.dataframe(breakdown_df, hide_index=True, use_container_width=True)

                # Bar chart
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[employee['name']],
                    y=[allocation_pct],
                    marker_color=status_color,
                    text=[f"{allocation_pct:.1f}%"],
                    textposition='outside'
                ))
                fig.add_shape(
                    type="line", x0=-0.5, x1=0.5, y0=100, y1=100,
                    line=dict(color="black", dash="dash", width=2),
                )
                fig.add_shape(
                    type="line", x0=-0.5, x1=0.5, y0=80, y1=80,
                    line=dict(color="gray", dash="dot", width=1),
                )
                fig.update_layout(
                    height=300,
                    yaxis_title="Allocation %",
                    yaxis=dict(range=[0, max(150, allocation_pct + 20)]),
                    showlegend=False,
                    title="Allocation Status"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"No allocations found for {month_key}")
    else:
        st.info("No allocation data available")


def render_employee_edit_tab(db, processor, employee_id):
    """Render the Edit Employee Data subtab: form with basic info, compensation, benefits, allocation settings, skills.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        employee_id: The employee ID to edit.
    """
    employees_df = db.get_employees()
    employee_match = employees_df[employees_df['id'] == employee_id]
    if employee_match.empty:
        st.error(f"Employee {employee_id} not found")
        return
    employee = employee_match.iloc[0]

    st.markdown("#### Edit Employee Data")

    with st.form("edit_employee_form"):
        # === Basic Information ===
        st.markdown("**Basic Information**")
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Name*", value=employee['name'])
            role = st.text_input("Role*", value=employee['role'])

        with col2:
            hire_date = st.date_input(
                "Hire Date",
                value=pd.to_datetime(employee['hire_date']) if pd.notna(employee.get('hire_date')) else None
            )
            term_date = st.date_input(
                "Term Date (optional)",
                value=pd.to_datetime(employee['term_date']) if pd.notna(employee.get('term_date')) else None,
                help="Leave empty if employee is active"
            )

        st.markdown("---")

        # === Compensation ===
        st.markdown("**Compensation**")

        # Pay Type selection
        pay_type_options = ["Hourly", "Salary"]
        current_pay_type = employee.get('pay_type', 'Hourly')
        if current_pay_type not in pay_type_options:
            current_pay_type = "Hourly"

        pay_type = st.radio(
            "Pay Type*",
            options=pay_type_options,
            index=pay_type_options.index(current_pay_type),
            horizontal=True
        )

        col1, col2 = st.columns(2)

        # Conditional fields based on pay type
        if pay_type == "Hourly":
            with col1:
                cost_rate = st.number_input(
                    "Cost Rate ($/hour)*",
                    min_value=0.0,
                    value=float(employee.get('cost_rate', 0.0)) if pd.notna(employee.get('cost_rate')) else 0.0,
                    step=1.0,
                    format="%.2f",
                    help="Hourly rate for this employee"
                )
            with col2:
                st.info("Annual salary field is hidden for Hourly employees")

            # For form submission
            annual_salary = None

        else:  # Salary
            with col1:
                annual_salary = st.number_input(
                    "Annual Salary ($)*",
                    min_value=0.0,
                    value=float(employee.get('annual_salary', 0.0)) if pd.notna(employee.get('annual_salary')) else 0.0,
                    step=1000.0,
                    format="%.2f",
                    help="Annual salary for this employee"
                )

            # Auto-calculate cost rate from annual salary
            if annual_salary > 0:
                calculated_cost_rate = annual_salary / 2080
                with col2:
                    st.info(f"**Calculated Hourly Rate:** ${calculated_cost_rate:.2f}/hour  \n(Based on 2080 hours/year)")
                cost_rate = calculated_cost_rate
            else:
                cost_rate = 0.0
                with col2:
                    st.warning("Enter annual salary to calculate hourly rate")

        st.markdown("---")

        # === Benefits ===
        st.markdown("**Benefits**")
        col1, col2 = st.columns(2)

        with col1:
            pto_accrual = st.number_input(
                "PTO Accrual (hours/year)",
                min_value=0.0,
                value=float(employee.get('pto_accrual', 120.0)) if pd.notna(employee.get('pto_accrual')) else 120.0,
                step=8.0,
                format="%.1f",
                help="Annual PTO hours"
            )

        with col2:
            holidays = st.number_input(
                "Holidays (hours/year)",
                min_value=0.0,
                value=float(employee.get('holidays', 88.0 if pay_type == "Salary" else 0.0)) if pd.notna(employee.get('holidays')) else (88.0 if pay_type == "Salary" else 0.0),
                step=8.0,
                format="%.1f",
                help="Typically 88 for Salary, 0 for Hourly"
            )

        st.markdown("---")

        # === Allocation Settings ===
        st.markdown("**Allocation Settings**")
        col1, col2 = st.columns(2)

        with col1:
            billable = st.checkbox(
                "Billable Employee",
                value=bool(employee.get('billable', 0)),
                help="Check if this employee's time is billable to clients",
                key=f"billable_{employee_id}"
            )

            overhead_allocation = st.number_input(
                "Overhead Allocation",
                min_value=0.0,
                max_value=1.0,
                value=float(employee.get('overhead_allocation', 0.0)) if pd.notna(employee.get('overhead_allocation')) else 0.0,
                step=0.05,
                format="%.2f",
                help="Percentage of time allocated to overhead (0-1)",
                key=f"overhead_{employee_id}"
            )

        with col2:
            # Determine default target allocation based on pay type and billable status
            current_target = float(employee.get('target_allocation', 0.3)) if pd.notna(employee.get('target_allocation')) else 0.3

            target_allocation = st.number_input(
                "Target Allocation",
                min_value=0.0,
                max_value=1.0,
                value=current_target,
                step=0.05,
                format="%.2f",
                help="Target FTE allocation for this employee (0-1). Billable Salary: 1.0, Billable Hourly: 0.3",
                key=f"target_{employee_id}"
            )

        # Apply defaults for billable employees
        if billable:
            overhead_allocation = 0.0
            # Show info about defaults
            if pay_type == "Salary":
                st.info("Billable Salary employees: overhead set to 0, target typically 1.0")
            else:  # Hourly
                st.info("Billable Hourly employees: overhead set to 0, target typically 0.3")

        st.markdown("---")

        # === Skills ===
        st.markdown("**Skills**")

        # Skills options
        skills_options = [
            "jr. developer",
            "sr. developer",
            "sr. consultant",
            "technical SME",
            "project lead",
            "project manager",
            "scheduler"
        ]

        # Parse current skills from comma-separated string
        current_skills_str = employee.get('skills', '')
        if pd.notna(current_skills_str) and current_skills_str:
            current_skills = [s.strip() for s in current_skills_str.split(',')]
        else:
            current_skills = []

        selected_skills = st.multiselect(
            "Skills (select multiple)",
            options=skills_options,
            default=[s for s in current_skills if s in skills_options],
            help="Select one or more skills for this employee"
        )

        # Convert selected skills back to comma-separated string
        skills_str = ', '.join(selected_skills) if selected_skills else None

        st.markdown("---")

        # Submit button
        update_button = st.form_submit_button("Update Employee", type="primary")

        if update_button:
            # Validation
            if not name or not role:
                st.error("Please fill in all required fields marked with *")
            elif pay_type == "Hourly" and cost_rate <= 0:
                st.error("Cost Rate must be greater than 0 for Hourly employees")
            elif pay_type == "Salary" and annual_salary <= 0:
                st.error("Annual Salary must be greater than 0 for Salary employees")
            elif term_date and hire_date and term_date < hire_date:
                st.error("Term Date cannot be before Hire Date")
            else:
                # Prepare updates
                updates = {
                    'name': name,
                    'role': role,
                    'hire_date': hire_date.strftime('%Y-%m-%d') if hire_date else None,
                    'term_date': term_date.strftime('%Y-%m-%d') if term_date else None,
                    'pay_type': pay_type,
                    'cost_rate': cost_rate,
                    'annual_salary': annual_salary if pay_type == "Salary" else None,
                    'pto_accrual': pto_accrual,
                    'holidays': holidays,
                    'skills': skills_str,
                    'billable': 1 if billable else 0,
                    'overhead_allocation': overhead_allocation,
                    'target_allocation': target_allocation
                }

                try:
                    db.update_employee(employee_id, updates)
                    st.success(f"Employee '{name}' updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error updating employee: {str(e)}")


def render_employee_detail_tab(db, processor, employee_id=None, default_subtab=None):
    """Render the Employee Detail (Edit) tab with project allocations and employee data subtabs.

    Legacy wrapper that delegates to render_project_allocations_subtab and render_employee_edit_tab.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        employee_id: Optional employee ID. If provided, skips the selectbox and uses this employee directly.
        default_subtab: Optional subtab name to default to ("Project Allocations" or "Edit Employee Data").
    """
    st.markdown("#### Employee Detail (Edit)")

    employees_df = db.get_employees()

    if employees_df.empty:
        st.info("No employees available to edit")
        return

    if employee_id is not None:
        # Use provided employee ID directly
        employee_match = employees_df[employees_df['id'] == employee_id]
        if employee_match.empty:
            st.error(f"Employee {employee_id} not found")
            return
        employee = employee_match.iloc[0]
    else:
        # Original selectbox behavior
        selected_employee_name = st.selectbox(
            "Select Employee",
            options=employees_df['name'].tolist(),
            key="edit_employee_select"
        )

        if not selected_employee_name:
            return
        employee = employees_df[employees_df['name'] == selected_employee_name].iloc[0]

    employee_id = employee['id']  # Ensure employee_id is set for later use

    st.markdown(f"### {employee['name']}")

    # Create subtabs for Project Allocations and Employee Data
    valid_subtabs = ["Project Allocations", "Edit Employee Data"]
    if default_subtab and default_subtab not in valid_subtabs:
        default_subtab = None

    tab_alloc, tab_edit = st.tabs(
        ["Project Allocations", "Edit Employee Data"],
        default=default_subtab
    )

    with tab_alloc:
        render_project_allocations_subtab(db, processor, employee_id)

    with tab_edit:
        render_employee_edit_tab(db, processor, employee_id)
