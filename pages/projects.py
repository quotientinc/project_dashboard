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
filters = st.session_state.filters

st.markdown("### 🚀 Project Management")

# Tabs for different views
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Project List", "Project Details", "Add Project", "Edit Project", "Project Analytics"])

with tab1:
    # Load projects
    projects_df = db.get_projects()

    # Apply filters
    if filters['projects']:
        projects_df = projects_df[projects_df['name'].isin(filters['projects'])]
    if filters['status']:
        projects_df = projects_df[projects_df['status'].isin(filters['status'])]

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

            # Project header
            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                st.markdown(f"## {project['name']}")
                st.write(project['description'])

            with col2:
                st.metric("Status", project['status'])
                st.metric("Client", project['client'])

            with col3:
                st.metric("Project Manager", project['project_manager'])
                profit = project['revenue_actual'] - project['budget_used']
                st.metric("Profit/Loss", f"${profit:,.0f}")

            # Tabs for project details
            detail_tab1, detail_tab2, detail_tab3, detail_tab4, detail_tab5 = st.tabs(
                ["Financial", "Team", "Timeline", "Expenses", "Burn Rate"]
            )

            with detail_tab1:
                # Financial metrics
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### Budget")
                    st.metric("Allocated", f"${project['budget_allocated']:,.0f}")
                    st.metric("Used", f"${project['budget_used']:,.0f}")
                    remaining = project['budget_allocated'] - project['budget_used']
                    st.metric("Remaining", f"${remaining:,.0f}")

                    if project['budget_allocated'] > 0:
                        budget_pct = project['budget_used'] / project['budget_allocated'] * 100
                        st.progress(min(budget_pct / 100, 1.0))
                        st.caption(f"Budget Utilization: {budget_pct:.1f}%")

                with col2:
                    st.markdown("#### Revenue")
                    st.metric("Projected", f"${project['revenue_projected']:,.0f}")
                    st.metric("Actual", f"${project['revenue_actual']:,.0f}")
                    variance = project['revenue_actual'] - project['revenue_projected']
                    st.metric("Variance", f"${variance:,.0f}")

                    if project['revenue_projected'] > 0:
                        revenue_pct = project['revenue_actual'] / project['revenue_projected'] * 100
                        st.progress(min(revenue_pct / 100, 1.0))
                        st.caption(f"Revenue Achievement: {revenue_pct:.1f}%")

                # Cost breakdown
                costs = processor.calculate_project_costs(
                    project_id,
                    db.get_allocations(project_id=project_id),
                    db.get_expenses(project_id=project_id),
                    db.get_time_entries(project_id=project_id)
                )

                st.markdown("#### Cost Breakdown")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Labor Cost", f"${costs['labor_cost']:,.0f}")
                with col2:
                    st.metric("Expense Cost", f"${costs['expense_cost']:,.0f}")
                with col3:
                    st.metric("Total Cost", f"${costs['total_cost']:,.0f}")

                # Cost charts
                if costs['cost_breakdown']:
                    col1, col2 = st.columns(2)

                    with col1:
                        if 'by_employee' in costs['cost_breakdown'] and costs['cost_breakdown']['by_employee']:
                            fig = px.pie(
                                values=list(costs['cost_breakdown']['by_employee'].values()),
                                names=list(costs['cost_breakdown']['by_employee'].keys()),
                                title="Cost by Employee"
                            )
                            st.plotly_chart(fig, width='stretch')

                    with col2:
                        if 'by_category' in costs['cost_breakdown'] and costs['cost_breakdown']['by_category']:
                            fig = px.pie(
                                values=list(costs['cost_breakdown']['by_category'].values()),
                                names=list(costs['cost_breakdown']['by_category'].keys()),
                                title="Cost by Category"
                            )
                            st.plotly_chart(fig, width='stretch')

            with detail_tab2:
                # Team allocation
                allocations_df = db.get_allocations(project_id=project_id)

                if not allocations_df.empty:
                    st.markdown("#### Team Members")

                    for _, allocation in allocations_df.iterrows():
                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            st.write(f"**{allocation['employee_name']}**")
                            st.caption(allocation['department'])

                        with col2:
                            st.write(f"Role: {allocation['role']}")
                            st.write(f"Allocation: {allocation['allocation_percent']:.0f}%")

                        with col3:
                            st.write(f"Hours Projected: {allocation['hours_projected']:.0f}")
                            st.write(f"Hours Actual: {allocation['hours_actual']:.0f}")

                        with col4:
                            variance = allocation['hours_actual'] - allocation['hours_projected']
                            if variance > 0:
                                st.error(f"Over by {variance:.0f} hours")
                            else:
                                st.success(f"Under by {abs(variance):.0f} hours")

                        st.markdown("---")

                    # Team utilization chart
                    fig = go.Figure(data=[
                        go.Bar(
                            name='Projected',
                            x=allocations_df['employee_name'],
                            y=allocations_df['hours_projected']
                        ),
                        go.Bar(
                            name='Actual',
                            x=allocations_df['employee_name'],
                            y=allocations_df['hours_actual']
                        )
                    ])
                    fig.update_layout(
                        title="Hours: Projected vs Actual",
                        barmode='group',
                        height=400
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info("No team members allocated to this project")

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

            with detail_tab5:
                # Burn Rate Analysis
                show_burn_rate_editor(project, db, processor)
    else:
        st.info("No projects available")

with tab3:
    # Add new project
    st.markdown("#### Add New Project")

    with st.form("add_project_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Project Name*")
            description = st.text_area("Description")
            client = st.text_input("Client*")
            project_manager = st.text_input("Project Manager*")

        with col2:
            status = st.selectbox("Status", ["Active", "On Hold", "Completed", "Cancelled"])
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")
            budget_allocated = st.number_input("Budget Allocated", min_value=0.0, step=1000.0)

        col1, col2 = st.columns(2)

        with col1:
            revenue_projected = st.number_input("Revenue Projected", min_value=0.0, step=1000.0)

        with col2:
            budget_used = st.number_input("Budget Used", min_value=0.0, step=1000.0, value=0.0)
            revenue_actual = st.number_input("Revenue Actual", min_value=0.0, step=1000.0, value=0.0)

        submitted = st.form_submit_button("Add Project")

        if submitted:
            if name and client and project_manager:
                project_data = {
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
                    'revenue_actual': revenue_actual
                }

                try:
                    db.add_project(project_data)
                    st.success(f"Project '{name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding project: {str(e)}")
            else:
                st.error("Please fill in all required fields marked with *")

with tab4:
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

                col1, col2 = st.columns(2)
                with col1:
                    update_button = st.form_submit_button("Update Project", type="primary")
                with col2:
                    delete_button = st.form_submit_button("Delete Project", type="secondary")

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
                            'revenue_actual': revenue_actual
                        }

                        try:
                            db.update_project(project_id, updates)
                            st.success(f"Project '{name}' updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating project: {str(e)}")
                    else:
                        st.error("Please fill in all required fields marked with *")

                if delete_button:
                    st.warning("⚠️ Delete functionality requires confirmation. Please implement a confirmation dialog.")

            # Team allocation management (outside the form)
            st.markdown("---")
            st.markdown("#### Team Allocation Management")

            # Current allocations
            allocations_df = db.get_allocations(project_id=project_id)

            if not allocations_df.empty:
                st.markdown("##### Current Team Members")

                for _, alloc in allocations_df.iterrows():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

                    with col1:
                        st.write(f"**{alloc['employee_name']}** ({alloc['department']})")

                    with col2:
                        st.write(f"Allocation: {alloc['allocation_percent']:.0f}%")

                    with col3:
                        st.write(f"Hours: {alloc['hours_projected']:.0f} proj / {alloc['hours_actual']:.0f} actual")

                    with col4:
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
                        allocation_percent = st.number_input("Allocation %", min_value=0.0, max_value=100.0, step=5.0, value=50.0)

                    with col2:
                        role_in_project = st.text_input("Role in Project")
                        hours_projected = st.number_input("Hours Projected", min_value=0.0, step=10.0, value=80.0)

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

                            allocation_data = {
                                'project_id': project_id,
                                'employee_id': selected_emp['id'],
                                'allocation_percent': allocation_percent,
                                'hours_projected': hours_projected,
                                'hours_actual': 0.0,
                                'start_date': alloc_start.strftime('%Y-%m-%d'),
                                'end_date': alloc_end.strftime('%Y-%m-%d'),
                                'role': role_in_project
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

with tab5:
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
