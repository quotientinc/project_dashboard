import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
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
        utilization_df = processor.calculate_employee_utilization(
            employees_df, allocations_df, time_entries_df
        )
        
        # Utilization chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=utilization_df['name'],
            y=utilization_df['utilization_rate'],
            name='Utilization %',
            marker_color=utilization_df['utilization_rate'].apply(
                lambda x: 'green' if x >= 80 else ('yellow' if x >= 60 else 'red')
            )
        ))
        fig.add_shape(
            type="line", x0=-0.5, x1=len(utilization_df)-0.5,
            y0=80, y1=80, line=dict(color="red", dash="dash")
        )
        fig.update_layout(
            title="Employee Utilization Rates",
            yaxis_title="Utilization %",
            height=400
        )
        st.plotly_chart(fig, width='stretch')
        
        # Detailed metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### Top Utilized Employees")
            top_utilized = utilization_df.nlargest(5, 'utilization_rate')[
                ['name', 'utilization_rate', 'billable_hours']
            ]
            st.dataframe(top_utilized, hide_index=True)
        
        with col2:
            st.markdown("##### Under-utilized Employees")
            # Select columns that exist in the utilization_df
            display_cols = ['name', 'utilization_rate']
            if 'allocated_fte' in utilization_df.columns:
                display_cols.append('allocated_fte')
            under_utilized = utilization_df.nsmallest(5, 'utilization_rate')[display_cols]
            st.dataframe(under_utilized, hide_index=True)

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
                            'skills': skills_str
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
                            # Get employee's cost_rate to use as employee_rate
                            employee_rate = employee.get('cost_rate', None)

                            allocation_data = {
                                'project_id': selected_proj['id'],
                                'employee_id': employee_id,
                                'allocated_fte': allocated_fte,
                                'start_date': alloc_start.strftime('%Y-%m-%d'),
                                'end_date': alloc_end.strftime('%Y-%m-%d'),
                                'role': role_in_project,
                                'employee_rate': employee_rate
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
