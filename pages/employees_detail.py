"""
Employee Detail (Edit) tab - manage employee data and project allocations with subtabs.
"""
import streamlit as st
import pandas as pd


def render_employee_detail_tab(db, processor):
    """Render the Employee Detail (Edit) tab with project allocations and employee data subtabs."""
    st.markdown("#### Employee Detail (Edit)")

    employees_df = db.get_employees()

    if not employees_df.empty:
        # Select employee to edit
        selected_employee_name = st.selectbox(
            "Select Employee",
            options=employees_df['name'].tolist(),
            key="edit_employee_select"
        )

        if selected_employee_name:
            employee = employees_df[employees_df['name'] == selected_employee_name].iloc[0]
            employee_id = employee['id']

            st.markdown(f"### {employee['name']}")

            # Create subtabs for Project Allocations and Employee Data
            detail_tab1, detail_tab2 = st.tabs(["Project Allocations", "Edit Employee Data"])

            # Subtab 1: Project Allocation Management
            with detail_tab1:
                st.markdown("#### Project Allocation Management")

                # Get employee target FTE (accounting for overhead)
                target_fte = employee.get('target_allocation', 1.0) - employee.get('overhead_allocation', 0.0)

                # Current allocations
                allocations_df = db.get_allocations(employee_id=employee_id)

                if not allocations_df.empty:
                    # Parse allocation dates
                    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
                    allocations_df['year'] = allocations_df['allocation_date'].dt.year
                    allocations_df['month'] = allocations_df['allocation_date'].dt.month

                    # Get available years
                    available_years = sorted(allocations_df['year'].unique(), reverse=True)

                    st.markdown("##### Current Allocations by Month")

                    # Year selector
                    selected_year = st.selectbox(
                        "Select Year",
                        options=available_years,
                        key=f"alloc_year_select_{employee_id}"
                    )

                    # Filter to selected year
                    year_allocs = allocations_df[allocations_df['year'] == selected_year].copy()

                    # Get unique projects for this year
                    unique_projects = year_allocs[['project_id', 'project_name']].drop_duplicates()

                    # Build table with projects as rows, months as columns
                    table_rows = []

                    for _, proj in unique_projects.iterrows():
                        proj_allocs = year_allocs[year_allocs['project_id'] == proj['project_id']]

                        row = {
                            'project_id': proj['project_id'],
                            'Project': proj['project_name']
                        }

                        # Add columns for each month (Jan-Dec)
                        for month_num in range(1, 13):
                            month_data = proj_allocs[proj_allocs['month'] == month_num]

                            month_abbr = pd.Timestamp(year=selected_year, month=month_num, day=1).strftime('%b')

                            if not month_data.empty:
                                row[f'{month_abbr} FTE'] = float(month_data['allocated_fte'].iloc[0])
                                row[f'{month_abbr} Rate'] = float(month_data['bill_rate'].iloc[0]) if pd.notna(month_data['bill_rate'].iloc[0]) else 0.0
                            else:
                                row[f'{month_abbr} FTE'] = 0.0
                                row[f'{month_abbr} Rate'] = 0.0

                        table_rows.append(row)

                    # Create DataFrame
                    display_df = pd.DataFrame(table_rows)

                    # Build column configuration
                    column_config = {
                        'project_id': None,  # Hide project_id
                        'Project': st.column_config.TextColumn(
                            'Project',
                            width='medium',
                            disabled=True
                        )
                    }

                    # Add month columns
                    for month_num in range(1, 13):
                        month_abbr = pd.Timestamp(year=selected_year, month=month_num, day=1).strftime('%b')

                        column_config[f'{month_abbr} FTE'] = st.column_config.NumberColumn(
                            f'{month_abbr} FTE',
                            help=f'FTE allocation for {month_abbr} {selected_year}',
                            format='%.2f',
                            width='small',
                            disabled=True
                        )

                        column_config[f'{month_abbr} Rate'] = st.column_config.NumberColumn(
                            f'{month_abbr} Rate',
                            help=f'Bill rate for {month_abbr} {selected_year}',
                            format='$%.2f',
                            width='small',
                            disabled=True
                        )

                    # Display table
                    st.dataframe(
                        display_df,
                        column_config=column_config,
                        hide_index=True,
                        use_container_width=True,
                        height=400
                    )

                    # Calculate and display monthly totals
                    st.markdown("##### Monthly Totals")
                    total_cols = st.columns(12)

                    for month_num in range(1, 13):
                        month_abbr = pd.Timestamp(year=selected_year, month=month_num, day=1).strftime('%b')
                        month_total = display_df[f'{month_abbr} FTE'].sum()

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

                else:
                    st.info("Not allocated to any projects")

                # Add new allocation
                st.markdown("##### Add to Project")

                projects_df = db.get_projects()

                # Filter out projects already allocated
                if not allocations_df.empty:
                    allocated_proj_ids = allocations_df['project_id'].tolist()
                    available_projects = projects_df[~projects_df['id'].isin(allocated_proj_ids)]
                else:
                    available_projects = projects_df

                if not available_projects.empty:
                    with st.form(key=f"add_alloc_employee_{employee_id}"):
                        col1, col2 = st.columns(2)

                        with col1:
                            project_name = st.selectbox(
                                "Select Project",
                                options=available_projects['name'].tolist(),
                                key=f"new_proj_select_{employee_id}"
                            )
                            allocated_fte = st.number_input("Allocation (FTE)", min_value=0.0, max_value=1.0, step=0.05, value=0.5, key=f"emp_alloc_{employee_id}", help="0.5 = 50% of full-time, 1.0 = 100% full-time")

                        with col2:
                            role_in_project = st.text_input("Role in Project", key=f"emp_role_{employee_id}")

                        selected_proj = available_projects[available_projects['name'] == project_name].iloc[0]

                        col1, col2 = st.columns(2)
                        with col1:
                            alloc_start = st.date_input("Start Date", value=pd.to_datetime(selected_proj['start_date']), key=f"emp_alloc_start_{employee_id}")
                        with col2:
                            alloc_end = st.date_input("End Date", value=pd.to_datetime(selected_proj['end_date']), key=f"emp_alloc_end_{employee_id}")

                        if st.form_submit_button("Add to Project"):
                            try:
                                # Get employee's cost_rate to use as bill_rate
                                bill_rate = employee.get('cost_rate', None)

                                # Generate monthly allocation records (matching Project Edit logic)
                                # Create list of first-of-month dates between start and end
                                months = pd.date_range(
                                    start=pd.to_datetime(alloc_start).replace(day=1),
                                    end=pd.to_datetime(alloc_end) + pd.DateOffset(months=1),
                                    freq='MS'  # Month Start
                                )[:-1]  # Remove extra month

                                # Create one allocation record per month
                                records_created = 0
                                for month_date in months:
                                    allocation_data = {
                                        'project_id': selected_proj['id'],
                                        'employee_id': employee_id,
                                        'allocated_fte': allocated_fte,
                                        'allocation_date': month_date.strftime('%Y-%m'),  # Monthly allocation_date (source of truth)
                                        'role': role_in_project,
                                        'bill_rate': bill_rate
                                    }

                                    db.add_allocation(allocation_data)
                                    records_created += 1

                                st.success(f"Added {employee['name']} to {project_name}! Created {records_created} monthly allocation record(s).")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error adding to project: {str(e)}")
                else:
                    st.info("Employee is already allocated to all available projects")

            # Subtab 2: Edit Employee Data
            with detail_tab2:
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
                        calculated_rate_display = None

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
                            st.info("💡 Billable Salary employees: overhead set to 0, target typically 1.0")
                        else:  # Hourly
                            st.info("💡 Billable Hourly employees: overhead set to 0, target typically 0.3")

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

    else:
        st.info("No employees available to edit")
