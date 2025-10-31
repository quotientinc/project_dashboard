import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 👥 Employee Management")

tab1, tab2, tab3, tab4 = st.tabs(["Employee List", "Utilization", "Add Employee", "Edit Employee"])

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
            # Card view with filters
            col1, col2 = st.columns(2)
            with col1:
                dept_filter = st.selectbox("Department", ["All"] + sorted(employees_df['department'].unique().tolist()), key="card_dept_filter")
            with col2:
                role_filter = st.selectbox("Role", ["All"] + sorted(employees_df['role'].unique().tolist()), key="card_role_filter")

            # Apply filters
            filtered_df = employees_df.copy()
            if role_filter != "All":
                filtered_df = filtered_df[filtered_df['role'] == role_filter]

            # Sort
            sort_map = {
                "Name": "name",
                "Role": "role",
                "Utilization": "utilization",
            }
            filtered_df = filtered_df.sort_values(sort_map[sort_by])

            # Display cards
            cols = st.columns(3)
            for idx, (_, emp) in enumerate(filtered_df.iterrows()):
                with cols[idx % 3]:
                    with st.container():
                        # Utilization color indicator
                        util_indicator = '🟢' if emp['utilization'] >= 80 else ('🟡' if emp['utilization'] >= 60 else '🔴')

                        st.markdown(f"### {util_indicator} {emp['name']}")
                        st.write(f"**Role:** {emp['role']}")
                        st.write(f"**Department:** {emp['department']}")
                        st.write(f"**Email:** {emp['email']}")

                        # Utilization bar

                        st.write(f"**Hire Date:** {emp['hire_date']}")
                        st.write(f"**Skills:** {emp['skills']}")

                        # Show current allocations
                        allocations = db.get_allocations(employee_id=emp['id'])
                        if not allocations.empty:
                            with st.expander("Current Projects"):
                                for _, alloc in allocations.iterrows():
                                    st.write(f"• {alloc['project_name']} ({alloc['allocation_percent']:.0f}%)")

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
            under_utilized = utilization_df.nsmallest(5, 'utilization_rate')[
                ['name', 'utilization_rate', 'allocation_percent']
            ]
            st.dataframe(under_utilized, hide_index=True)

with tab3:
    st.markdown("#### Add New Employee")
    
    with st.form("add_employee_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Name*")
            role = st.text_input("Role*")
        
        with col2:
            hire_date = st.date_input("Hire Date")
        
        skills = st.text_area("Skills (comma-separated)")
        
        submitted = st.form_submit_button("Add Employee")
        
        if submitted:
            if name and email and department and role:
                employee_data = {
                    'name': name,
                    'role': role,
                    'skills': skills,
                    'hire_date': hire_date.strftime('%Y-%m-%d')
                }
                
                try:
                    db.add_employee(employee_data)
                    st.success(f"Employee '{name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding employee: {str(e)}")
            else:
                st.error("Please fill in all required fields marked with *")

with tab4:
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
                col1, col2 = st.columns(2)

                with col1:
                    name = st.text_input("Name*", value=employee['name'])
                    role = st.text_input("Role*", value=employee['role'])

                with col2:
                    hire_date = st.date_input("Hire Date", value=pd.to_datetime(employee['hire_date']))

                skills = st.text_area("Skills (comma-separated)", value=employee['skills'])

                col1, col2 = st.columns(2)
                with col1:
                    update_button = st.form_submit_button("Update Employee", type="primary")
                with col2:
                    delete_button = st.form_submit_button("Delete Employee", type="secondary")

                if update_button:
                    if name and email and department and role:
                        updates = {
                            'name': name,
                            'role': role,
                            'skills': skills,
                            'hire_date': hire_date.strftime('%Y-%m-%d')
                        }

                        try:
                            db.update_employee(employee_id, updates)
                            st.success(f"Employee '{name}' updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating employee: {str(e)}")
                    else:
                        st.error("Please fill in all required fields marked with *")

                if delete_button:
                    st.warning("⚠️ Delete functionality requires confirmation. Please implement a confirmation dialog.")

            # Project allocation management (outside the form)
            st.markdown("---")
            st.markdown("#### Project Allocation Management")

            # Current allocations
            allocations_df = db.get_allocations(employee_id=employee_id)

            if not allocations_df.empty:
                st.markdown("##### Current Projects")

                for _, alloc in allocations_df.iterrows():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

                    with col1:
                        st.write(f"**{alloc['project_name']}**")

                    with col2:
                        st.write(f"Allocation: {alloc['allocation_percent']:.0f}%")

                    with col3:
                        st.write(f"Hours: {alloc['hours_projected']:.0f} proj / {alloc['hours_actual']:.0f} actual")

                    with col4:
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
                        allocation_percent = st.number_input("Allocation %", min_value=0.0, max_value=100.0, step=5.0, value=50.0, key=f"emp_alloc_{employee_id}")

                    with col2:
                        role_in_project = st.text_input("Role in Project", key=f"emp_role_{employee_id}")
                        hours_projected = st.number_input("Hours Projected", min_value=0.0, step=10.0, value=80.0, key=f"emp_hours_{employee_id}")

                    selected_proj = available_projects[available_projects['name'] == project_name].iloc[0]

                    col1, col2 = st.columns(2)
                    with col1:
                        alloc_start = st.date_input("Start Date", value=pd.to_datetime(selected_proj['start_date']), key=f"emp_alloc_start_{employee_id}")
                    with col2:
                        alloc_end = st.date_input("End Date", value=pd.to_datetime(selected_proj['end_date']), key=f"emp_alloc_end_{employee_id}")

                    if st.form_submit_button("Add to Project"):
                        try:
                            allocation_data = {
                                'project_id': selected_proj['id'],
                                'employee_id': employee_id,
                                'allocation_percent': allocation_percent,
                                'hours_projected': hours_projected,
                                'hours_actual': 0.0,
                                'start_date': alloc_start.strftime('%Y-%m-%d'),
                                'end_date': alloc_end.strftime('%Y-%m-%d'),
                                'role': role_in_project
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
