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
                    # Group allocations by month
                    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
                    allocations_df['month_key'] = allocations_df['allocation_date'].dt.strftime('%B %Y')
                    allocations_df['sort_key'] = allocations_df['allocation_date'].dt.to_period('M')

                    # Group by month
                    grouped = allocations_df.groupby('month_key')

                    # Sort months chronologically
                    month_order = allocations_df.sort_values('sort_key')['month_key'].unique()

                    st.markdown("##### Current Allocations by Month")

                    for month in month_order:
                        month_allocs = allocations_df[allocations_df['month_key'] == month]

                        # Calculate total FTE for this month
                        total_fte = month_allocs['allocated_fte'].sum()

                        # Calculate allocation percentage
                        allocation_pct = (total_fte / target_fte * 100) if target_fte > 0 else 0

                        # Determine color and emoji based on allocation
                        if allocation_pct > 120:
                            emoji = "🔴"
                            bg_color = "#ffcccc"
                        elif allocation_pct >= 100:
                            emoji = "🟡"
                            bg_color = "#fff9cc"
                        elif allocation_pct >= 80:
                            emoji = "🟢"
                            bg_color = "#ccffcc"
                        else:
                            emoji = "🔵"
                            bg_color = "#cce5ff"

                        # Display month header with color coding
                        st.markdown(
                            f"<div style='background-color: {bg_color}; padding: 10px; border-radius: 5px; margin: 10px 0;'>"
                            f"<b>📅 {month} ({total_fte:.1f} FTE of {target_fte:.1f} Target FTE) {emoji}</b>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        # Display allocations for this month
                        for _, alloc in month_allocs.iterrows():
                            col1, col2, col3 = st.columns([4, 2, 1])

                            with col1:
                                st.write(f"  • **{alloc['project_name']}**")

                            with col2:
                                fte = alloc.get('allocated_fte', 0)
                                st.write(f"{fte:.2f} FTE")

                            with col3:
                                if st.button("Remove", key=f"remove_emp_alloc_{alloc['id']}"):
                                    try:
                                        db.delete_allocation(alloc['id'])
                                        st.success(f"Removed from {alloc['project_name']}")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error removing allocation: {str(e)}")

                        st.markdown("")  # Add spacing between months
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

                                allocation_data = {
                                    'project_id': selected_proj['id'],
                                    'employee_id': employee_id,
                                    'allocated_fte': allocated_fte,
                                    'start_date': alloc_start.strftime('%Y-%m-%d'),
                                    'end_date': alloc_end.strftime('%Y-%m-%d'),
                                    'role': role_in_project,
                                    'bill_rate': bill_rate
                                }

                                db.add_allocation(allocation_data)
                                st.success(f"Added {employee['name']} to {project_name}!")
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
