import streamlit as st
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 👥 Employee Management")

tab1, tab2, tab3 = st.tabs(["Employee List", "Utilization", "Edit Employee"])

with tab1:
    employees_df = db.get_employees()

    if not employees_df.empty:
        # Display options
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("#### All Employees")
        with col2:
            view_mode = st.selectbox("View", ["Table", "Cards"], label_visibility="collapsed")

        if view_mode == "Table":
            # Table view - no filters, just display all data
            # The dataframe itself has built-in sorting and filtering
            display_df = employees_df.copy()

            st.dataframe(display_df, width='stretch', hide_index=True)

        else:
            # Card view with role filter only
            role_filter = st.selectbox("Filter by Role", ["All"] + sorted(employees_df['role'].dropna().unique().tolist()), key="card_role_filter")

            # Apply filter
            filtered_df = employees_df.copy()
            if role_filter != "All":
                filtered_df = filtered_df[filtered_df['role'] == role_filter]

            # Sort by name
            filtered_df = filtered_df.sort_values('name')

            # Display cards
            cols = st.columns(3)
            for idx, (_, emp) in enumerate(filtered_df.iterrows()):
                with cols[idx % 3]:
                    with st.container():
                        st.markdown(f"### 👤 {emp['name']}")
                        st.write(f"**Role:** {emp['role'] if pd.notna(emp['role']) else 'N/A'}")
                        st.write(f"**Hire Date:** {emp['hire_date'] if pd.notna(emp['hire_date']) else 'N/A'}")

                        if pd.notna(emp.get('skills')) and emp['skills']:
                            st.write(f"**Skills:** {emp['skills']}")

                        # Show current allocations with FTE
                        allocations = db.get_allocations(employee_id=emp['id'])
                        if not allocations.empty:
                            total_fte = allocations['allocated_fte'].sum() if 'allocated_fte' in allocations.columns else 0
                            st.write(f"**Total FTE:** {total_fte:.2f}")

                            with st.expander("Current Projects"):
                                for _, alloc in allocations.iterrows():
                                    fte = alloc.get('allocated_fte', 0)
                                    st.write(f"• {alloc['project_name']} ({fte * 100:.0f}%)")

                        st.markdown("---")
    else:
        st.info("No employees found")

with tab2:
    st.markdown("#### Employee Utilization Analysis")

    employees_df = db.get_employees()
    allocations_df = db.get_allocations()
    time_entries_df = db.get_time_entries()

    if not employees_df.empty:
        from datetime import datetime
        import calendar

        # Month filter
        col1, col2 = st.columns([1, 1])

        with col1:
            # Year selector
            current_year = datetime.now().year
            year_options = list(range(current_year - 2, current_year + 2))  # 2 years back, 1 year forward
            selected_year = st.selectbox(
                "Year",
                options=year_options,
                index=year_options.index(current_year),
                key="util_year_filter"
            )

        with col2:
            # Month selector
            current_month = datetime.now().month
            month_names = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]
            selected_month_name = st.selectbox(
                "Month",
                options=month_names,
                index=current_month - 1,  # Default to current month
                key="util_month_filter"
            )
            selected_month = month_names.index(selected_month_name) + 1

        # Get month data from database
        months_df = db.get_months(year=selected_year)
        month_data = months_df[months_df['month'] == selected_month]

        if not month_data.empty:
            month_row = month_data.iloc[0]
            working_days = int(month_row['working_days'])
            holidays = int(month_row['holidays']) if pd.notna(month_row['holidays']) else 0
            actual_working_days = working_days - holidays
        else:
            # Fallback to calculation if month not in database
            days_in_month = calendar.monthrange(selected_year, selected_month)[1]
            working_days = sum(1 for day in range(1, days_in_month + 1)
                              if datetime(selected_year, selected_month, day).weekday() < 5)
            holidays = 0
            actual_working_days = working_days
            st.warning(f"⚠️ Month data not found in database for {month_names[selected_month - 1]} {selected_year}. Using calculated values.")

        utilization_df = processor.calculate_employee_utilization(
            employees_df,
            allocations_df,
            time_entries_df,
            current_month_working_days=actual_working_days,
            target_year=selected_year,
            target_month=selected_month
        )

        # Display key info with selected month
        is_current_month = (selected_year == current_year and selected_month == current_month)
        month_label = f"{month_names[selected_month - 1]} {selected_year}"
        if is_current_month:
            st.info(f"📅 **{month_label}** (Current Month) • Working Days: {working_days} • Holidays: {holidays} • Actual Working Days: {actual_working_days}")
        else:
            st.info(f"📅 **{month_label}** • Working Days: {working_days} • Holidays: {holidays} • Actual Working Days: {actual_working_days}")

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            avg_util = utilization_df['utilization_rate'].mean()
            st.metric("Average Utilization", f"{avg_util:.1f}%")
        with col2:
            if 'billable_utilization' in utilization_df.columns:
                avg_billable = utilization_df['billable_utilization'].mean()
                st.metric("Average Billable Util.", f"{avg_billable:.1f}%")
        with col3:
            if 'expected_hours' in utilization_df.columns:
                total_expected = utilization_df['expected_hours'].sum()
                total_actual = utilization_df['total_hours'].sum()
                st.metric("Total Hours", f"{total_actual:.0f} / {total_expected:.0f}")

        st.markdown("---")
        st.markdown("#### Detailed Utilization Table")

        # Prepare comprehensive table with all calculation values
        table_df = utilization_df.copy()

        # Calculate derived fields
        table_df['non_billable_hours'] = table_df['total_hours'] - table_df['billable_hours']
        table_df['hours_variance'] = table_df['total_hours'] - table_df['expected_hours']
        table_df['capacity_remaining'] = table_df['expected_hours'] - table_df['total_hours']

        # Add working days column (same for all)
        table_df['working_days'] = working_days

        # Select and order columns for display
        display_columns = [
            'name',
            'role',
            'target_allocation',
            'overhead_allocation',
            'working_days',
            'expected_hours',
            'total_hours',
            'billable_hours',
            'non_billable_hours',
            'utilization_rate',
            'billable_utilization',
            'billable_rate',
            'hours_variance',
            'capacity_remaining'
        ]

        # Filter to only existing columns
        display_columns = [col for col in display_columns if col in table_df.columns]
        display_df = table_df[display_columns].copy()

        # Rename columns for better display
        display_df = display_df.rename(columns={
            'name': 'Employee',
            'role': 'Role',
            'target_allocation': 'Target FTE',
            'overhead_allocation': 'Overhead %',
            'working_days': 'Working Days',
            'expected_hours': 'Expected Hrs',
            'total_hours': 'Actual Hrs',
            'billable_hours': 'Billable Hrs',
            'non_billable_hours': 'Non-bill Hrs',
            'utilization_rate': 'Total Util %',
            'billable_utilization': 'Billable Util %',
            'billable_rate': 'Billable Rate %',
            'hours_variance': 'Variance (+/-)',
            'capacity_remaining': 'Capacity Rem.'
        })

        # Format numeric columns
        if 'Target FTE' in display_df.columns:
            display_df['Target FTE'] = (display_df['Target FTE'] * 100).round(0).astype(int)
        if 'Overhead %' in display_df.columns:
            display_df['Overhead %'] = (display_df['Overhead %'] * 100).round(0).astype(int)
        if 'Expected Hrs' in display_df.columns:
            display_df['Expected Hrs'] = display_df['Expected Hrs'].round(1)
        if 'Actual Hrs' in display_df.columns:
            display_df['Actual Hrs'] = display_df['Actual Hrs'].round(1)
        if 'Billable Hrs' in display_df.columns:
            display_df['Billable Hrs'] = display_df['Billable Hrs'].round(1)
        if 'Non-bill Hrs' in display_df.columns:
            display_df['Non-bill Hrs'] = display_df['Non-bill Hrs'].round(1)
        if 'Total Util %' in display_df.columns:
            display_df['Total Util %'] = display_df['Total Util %'].round(1)
        if 'Billable Util %' in display_df.columns:
            display_df['Billable Util %'] = display_df['Billable Util %'].round(1)
        if 'Billable Rate %' in display_df.columns:
            display_df['Billable Rate %'] = display_df['Billable Rate %'].round(1)
        if 'Variance (+/-)' in display_df.columns:
            display_df['Variance (+/-)'] = display_df['Variance (+/-)'].round(1)
        if 'Capacity Rem.' in display_df.columns:
            display_df['Capacity Rem.'] = display_df['Capacity Rem.'].round(1)

        # Define color function for utilization columns
        def color_utilization(val):
            """Color code utilization percentages"""
            try:
                val_float = float(val)
                if val_float < 80:
                    return 'background-color: #ffcccb'  # Light red
                elif val_float < 100:
                    return 'background-color: #ffffcc'  # Light yellow
                elif val_float <= 120:
                    return 'background-color: #ccffcc'  # Light green
                else:
                    return 'background-color: #ffd9b3'  # Light orange
            except:
                return ''

        def color_variance(val):
            """Color code variance (positive = over, negative = under)"""
            try:
                val_float = float(val)
                if val_float < -10:
                    return 'background-color: #ffcccb; color: #cc0000'  # Red for significantly under
                elif val_float < 0:
                    return 'background-color: #ffffcc'  # Yellow for slightly under
                elif val_float <= 10:
                    return 'background-color: #ccffcc'  # Green for on target
                else:
                    return 'background-color: #ffd9b3; color: #cc6600'  # Orange for over
            except:
                return ''

        # Apply conditional formatting
        styled_df = display_df.style
        if 'Total Util %' in display_df.columns:
            styled_df = styled_df.applymap(color_utilization, subset=['Total Util %'])
        if 'Billable Util %' in display_df.columns:
            styled_df = styled_df.applymap(color_utilization, subset=['Billable Util %'])
        if 'Variance (+/-)' in display_df.columns:
            styled_df = styled_df.applymap(color_variance, subset=['Variance (+/-)'])

        # Format as strings with proper signs for variance
        if 'Variance (+/-)' in display_df.columns:
            display_df['Variance (+/-)'] = display_df['Variance (+/-)'].apply(
                lambda x: f"+{x:.1f}" if x > 0 else f"{x:.1f}"
            )

        # Display the table
        st.dataframe(styled_df, use_container_width=True, hide_index=True, height=600)

        # Add summary row
        st.markdown("##### Summary Totals")
        summary_cols = st.columns(5)
        with summary_cols[0]:
            st.metric("Total Employees", len(table_df))
        with summary_cols[1]:
            st.metric("Total Expected Hrs", f"{table_df['expected_hours'].sum():.0f}")
        with summary_cols[2]:
            st.metric("Total Actual Hrs", f"{table_df['total_hours'].sum():.0f}")
        with summary_cols[3]:
            st.metric("Total Billable Hrs", f"{table_df['billable_hours'].sum():.0f}")
        with summary_cols[4]:
            total_variance = table_df['hours_variance'].sum()
            st.metric("Total Variance", f"{'+' if total_variance > 0 else ''}{total_variance:.0f} hrs")

with tab3:
    st.markdown("#### Edit Employee")

    employees_df = db.get_employees()

    if not employees_df.empty:
        # Select employee to edit
        selected_employee_name = st.selectbox(
            "Select Employee to Edit",
            options=employees_df['name'].tolist(),
            key="edit_employee_select"
        )

        if selected_employee_name:
            employee = employees_df[employees_df['name'] == selected_employee_name].iloc[0]
            employee_id = employee['id']

            st.markdown(f"##### Editing: {employee['name']}")

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

            # Project allocation management (outside the form)
            st.markdown("---")
            st.markdown("#### Project Allocation Management")

            # Current allocations
            allocations_df = db.get_allocations(employee_id=employee_id)

            if not allocations_df.empty:
                st.markdown("##### Current Projects")

                for _, alloc in allocations_df.iterrows():
                    col1, col2, col3 = st.columns([4, 2, 1])

                    with col1:
                        st.write(f"**{alloc['project_name']}**")

                    with col2:
                        fte = alloc.get('allocated_fte', 0)
                        st.write(f"Allocation: {fte * 100:.0f}%")

                    with col3:
                        if st.button("Remove", key=f"remove_emp_alloc_{alloc['id']}"):
                            try:
                                db.delete_allocation(alloc['id'])
                                st.success(f"Removed from {alloc['project_name']}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error removing allocation: {str(e)}")
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

    else:
        st.info("No employees available to edit")
