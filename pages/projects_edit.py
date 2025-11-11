"""
Project Edit tab - edit project details and manage team allocations with dynamic monthly data editor.
"""
import streamlit as st
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)


def render_project_edit_tab(db, processor):
    """Render the Project Edit tab with project form and team allocation management."""
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
                    status_options_edit = ["Active", "Future", "On Hold", "Completed", "Cancelled"]
                    current_status_index = status_options_edit.index(project['status']) if project['status'] in status_options_edit else 0
                    status = st.selectbox("Status", status_options_edit, index=current_status_index)
                    start_date = st.date_input("Start Date", value=pd.to_datetime(project['start_date']) if pd.notna(project['start_date']) else None)
                    end_date = st.date_input("End Date", value=pd.to_datetime(project['end_date']) if pd.notna(project['end_date']) else None)
                    contract_value = st.number_input("Contract Value", min_value=0.0, step=1000.0, value=float(project['contract_value']) if pd.notna(project['contract_value']) else 0.0, help="Total contract value - what the customer pays")

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
                            'contract_value': contract_value,
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

            # Check if project has dates defined
            if pd.isna(project['start_date']) or pd.isna(project['end_date']):
                st.warning("⚠️ **Project dates required** - Please set start and end dates above to enable team allocation management.")
            else:
                st.markdown("Edit monthly FTE allocations and bill rates for team members. Add or remove employees using the table.")

                # Generate month columns based on project dates
                start_date = pd.to_datetime(project['start_date'])
                end_date = pd.to_datetime(project['end_date'])

                # Create list of first-of-month dates
                months = pd.date_range(
                    start=start_date.replace(day=1),
                    end=end_date + pd.DateOffset(months=1),
                    freq='MS'  # Month Start
                )[:-1]  # Remove extra month

                # Create mapping for display
                month_labels = [m.strftime('%b %Y') for m in months]  # ['Jan 2025', 'Feb 2025', ...]
                month_keys = [m.strftime('%Y-%m') for m in months]     # ['2025-01', '2025-02', ...]

                # Get all allocations for this project
                allocations_df = db.get_allocations(project_id=project_id)

                # Get all employees for dropdown
                employees_df = db.get_employees()

                if not allocations_df.empty:
                    # Get unique employees already on project
                    existing_employees = allocations_df['employee_id'].unique()

                    # Build display dataframe - one row per employee
                    display_rows = []

                    for emp_id in existing_employees:
                        emp_allocs = allocations_df[allocations_df['employee_id'] == emp_id]
                        emp_name = emp_allocs['employee_name'].iloc[0]

                        # Get employee's role from any allocation record
                        role = emp_allocs['role'].iloc[0] if pd.notna(emp_allocs['role'].iloc[0]) else ''

                        # Build row with employee info and month columns
                        row = {
                            'employee_id': int(emp_id),
                            'employee_name': emp_name,
                            'role': role
                        }

                        # Add FTE and Rate columns for each month
                        for i, month_date in enumerate(months):
                            month_key = month_date.strftime('%Y-%m')
                            month_label = month_labels[i]

                            # Find allocation for this month
                            month_alloc = emp_allocs[
                                pd.to_datetime(emp_allocs['allocation_date']).dt.strftime('%Y-%m') == month_key
                            ]

                            if not month_alloc.empty:
                                # Use existing allocation
                                row[f'fte_{month_key}'] = float(month_alloc['allocated_fte'].iloc[0])
                                row[f'rate_{month_key}'] = float(month_alloc['bill_rate'].iloc[0]) if pd.notna(month_alloc['bill_rate'].iloc[0]) else 0.0
                            else:
                                # No allocation for this month - default to 0.0
                                row[f'fte_{month_key}'] = 0.0
                                row[f'rate_{month_key}'] = 0.0

                        display_rows.append(row)

                    # Create DataFrame
                    editor_df = pd.DataFrame(display_rows)
                else:
                    # No allocations yet - create empty dataframe with correct columns
                    columns = ['employee_id', 'employee_name', 'role']
                    for month_key in month_keys:
                        columns.extend([f'fte_{month_key}', f'rate_{month_key}'])

                    editor_df = pd.DataFrame(columns=columns)

                # Store original for change detection
                if 'original_allocations' not in st.session_state or st.session_state.get('current_project_id') != project_id:
                    st.session_state.original_allocations = editor_df.copy()
                    st.session_state.current_project_id = project_id

                # Build column configuration
                column_config = {
                    'employee_id': st.column_config.NumberColumn(
                        'Employee ID',
                        help='Database employee ID',
                        disabled=True,
                        width='small'
                    ),
                    'employee_name': st.column_config.SelectboxColumn(
                        'Employee',
                        help='Select employee to add to project',
                        options=employees_df['name'].tolist(),
                        required=True,
                        width='medium'
                    ),
                    'role': st.column_config.TextColumn(
                        'Role',
                        help='Employee role on this project',
                        max_chars=50,
                        width='medium'
                    )
                }

                # Add month columns - alternating FTE and Rate
                for i, month_date in enumerate(months):
                    month_key = month_keys[i]
                    month_label = month_labels[i]

                    # FTE column
                    column_config[f'fte_{month_key}'] = st.column_config.NumberColumn(
                        f'{month_label} FTE',
                        help=f'FTE allocation for {month_label} (0.0-2.0, where 1.0=100%)',
                        min_value=0.0,
                        max_value=2.0,
                        step=0.05,
                        format='%.2f',
                        width='small'
                    )

                    # Bill Rate column
                    column_config[f'rate_{month_key}'] = st.column_config.NumberColumn(
                        f'{month_label} Rate',
                        help=f'Hourly bill rate for {month_label}',
                        min_value=0.0,
                        max_value=500.0,
                        step=5.0,
                        format='$%.2f',
                        width='small'
                    )

                # Display the editable table
                edited_df = st.data_editor(
                    editor_df,
                    column_config=column_config,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",  # Allow adding/deleting rows
                    key='team_allocation_editor',
                    height=400  # Fixed height with scrolling
                )

                # Info helper
                st.caption("""
💡 **Tips:**
- Click **+** to add a new employee row
- Click **🗑️** on row to remove employee from project
- Edit FTE values (0.0-2.0, where 1.0 = 100% full-time)
- Edit Bill Rates per month if they change during the project
- Changes are saved when you click **Save Changes**
                """)

                # Detect changes
                changes = []
                new_employees = []
                deleted_employees = []

                # Check for new rows (employee_id is 0 or NaN for new)
                for idx, row in edited_df.iterrows():
                    if pd.isna(row.get('employee_id')) or row.get('employee_id') == 0:
                        # New employee - need to create allocations
                        employee_name = row.get('employee_name')
                        if employee_name:
                            # Look up employee_id from employees_df
                            emp_match = employees_df[employees_df['name'] == employee_name]
                            if not emp_match.empty:
                                new_employees.append({
                                    'idx': idx,
                                    'employee_id': int(emp_match.iloc[0]['id']),
                                    'employee_name': employee_name,
                                    'role': row.get('role', ''),
                                    'row': row
                                })

                # Check for deleted rows (in original but not in edited)
                original_ids = set(st.session_state.original_allocations['employee_id'].dropna().astype(int))
                edited_ids = set(edited_df['employee_id'].dropna().astype(int))
                deleted_ids = original_ids - edited_ids

                if deleted_ids:
                    for emp_id in deleted_ids:
                        emp_name = st.session_state.original_allocations[
                            st.session_state.original_allocations['employee_id'] == emp_id
                        ]['employee_name'].iloc[0]
                        deleted_employees.append({'employee_id': emp_id, 'employee_name': emp_name})

                # Check for modified values (FTE or Rate changed)
                for idx, row in edited_df.iterrows():
                    emp_id = row.get('employee_id')

                    if pd.notna(emp_id) and emp_id != 0:
                        emp_id = int(emp_id)

                        # Find original row
                        orig_row = st.session_state.original_allocations[
                            st.session_state.original_allocations['employee_id'] == emp_id
                        ]

                        if not orig_row.empty:
                            orig_row = orig_row.iloc[0]

                            # Check each month for changes
                            for i, month_date in enumerate(months):
                                month_key = month_keys[i]
                                month_label = month_labels[i]

                                # Check FTE change
                                orig_fte = orig_row.get(f'fte_{month_key}', 0.0)
                                new_fte = row.get(f'fte_{month_key}', 0.0)

                                # Check Rate change
                                orig_rate = orig_row.get(f'rate_{month_key}', 0.0)
                                new_rate = row.get(f'rate_{month_key}', 0.0)

                                if orig_fte != new_fte or orig_rate != new_rate:
                                    changes.append({
                                        'employee_id': emp_id,
                                        'employee_name': row.get('employee_name'),
                                        'month_date': month_date,
                                        'month_key': month_key,
                                        'month_label': month_label,
                                        'orig_fte': orig_fte,
                                        'new_fte': new_fte,
                                        'orig_rate': orig_rate,
                                        'new_rate': new_rate,
                                        'role': row.get('role', '')
                                    })

                # Count total changes
                total_changes = len(changes) + len(new_employees) + len(deleted_employees)

                # Show save button if changes detected
                if total_changes > 0:
                    col1, col2 = st.columns([4, 1])

                    with col1:
                        # Summary of changes
                        change_summary = []
                        if new_employees:
                            change_summary.append(f"{len(new_employees)} employee(s) added")
                        if deleted_employees:
                            change_summary.append(f"{len(deleted_employees)} employee(s) removed")
                        if changes:
                            change_summary.append(f"{len(changes)} allocation(s) modified")

                        st.info(f"ℹ️ Unsaved changes: {', '.join(change_summary)}")

                    with col2:
                        if st.button("💾 Save Changes", type="primary"):
                            try:
                                # Process deletions first
                                for deleted in deleted_employees:
                                    # Delete all allocations for this employee on this project
                                    emp_allocs = allocations_df[allocations_df['employee_id'] == deleted['employee_id']]
                                    for _, alloc in emp_allocs.iterrows():
                                        db.delete_allocation(alloc['id'])

                                # Process new employees
                                for new_emp in new_employees:
                                    # Create allocation records for all months
                                    for i, month_date in enumerate(months):
                                        month_key = month_keys[i]
                                        fte_val = new_emp['row'].get(f'fte_{month_key}', 0.0)
                                        rate_val = new_emp['row'].get(f'rate_{month_key}', 0.0)

                                        # Only create if FTE or Rate is non-zero
                                        if fte_val != 0.0 or rate_val != 0.0:
                                            db.add_allocation({
                                                'project_id': project_id,
                                                'employee_id': new_emp['employee_id'],
                                                'allocated_fte': float(fte_val),
                                                'allocation_date': month_date.strftime('%Y-%m'),
                                                'role': new_emp['role'],
                                                'bill_rate': float(rate_val),
                                                'start_date': project['start_date'],
                                                'end_date': project['end_date']
                                            })

                                # Process modifications
                                for change in changes:
                                    month_allocation_date = change['month_date'].strftime('%Y-%m')

                                    # Find existing allocation record
                                    existing = allocations_df[
                                        (allocations_df['employee_id'] == change['employee_id']) &
                                        (pd.to_datetime(allocations_df['allocation_date']).dt.strftime('%Y-%m') == month_allocation_date)
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
                                        # Create new record (employee exists but no allocation for this month)
                                        db.add_allocation({
                                            'project_id': project_id,
                                            'employee_id': change['employee_id'],
                                            'allocated_fte': float(change['new_fte']),
                                            'allocation_date': month_allocation_date,
                                            'role': change['role'],
                                            'bill_rate': float(change['new_rate']),
                                            'start_date': project['start_date'],
                                            'end_date': project['end_date']
                                        })

                                # Clear session state and show success
                                if 'original_allocations' in st.session_state:
                                    del st.session_state.original_allocations
                                if 'current_project_id' in st.session_state:
                                    del st.session_state.current_project_id

                                st.success(f"✅ Successfully saved {total_changes} change(s)!")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ Error saving changes: {str(e)}")
                                logger.error(f"Allocation save error: {str(e)}", exc_info=True)
                else:
                    st.success("✅ All allocations saved")

    else:
        st.info("No projects available to edit")
