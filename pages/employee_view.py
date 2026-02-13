"""
Unified Employee View page - displays a single employee with tabbed interface.
"""
import streamlit as st
import pandas as pd
from utils.logger import get_logger
from pages.employees_detail import render_project_allocations_subtab, render_employee_edit_tab
from pages.employees_utilization import render_combined_utilization_view

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Get employees for the switcher
employees_df = db.get_employees()

if employees_df.empty:
    st.warning("No employees available.")
    if st.button("← Back to Employees"):
        st.query_params.clear()
        st.switch_page("pages/employees.py")
    st.stop()

# Resolve employee ID: query params first, session state fallback
employee_id = None

if "employee_id" in st.query_params:
    try:
        employee_id = int(st.query_params["employee_id"])
    except (ValueError, TypeError):
        st.error("Invalid employee_id in URL.")
        if st.button("← Go to Employees List"):
            st.query_params.clear()
            st.switch_page("pages/employees.py")
        st.stop()

if employee_id is None and 'selected_employee_id' in st.session_state:
    employee_id = st.session_state.selected_employee_id

if employee_id is None:
    st.warning("No employee selected. Please select an employee from the list.")
    if st.button("← Go to Employees List"):
        st.query_params.clear()
        st.switch_page("pages/employees.py")
    st.stop()

# Keep session state in sync for downstream tab code
st.session_state.selected_employee_id = employee_id

# Update URL if arrived via session state only
if st.query_params.get("employee_id") != str(employee_id):
    st.query_params["employee_id"] = str(employee_id)
employee_match = employees_df[employees_df['id'] == employee_id]

if employee_match.empty:
    st.error(f"Employee ID '{employee_id}' not found.")
    if st.button("← Back to Employees"):
        st.query_params.clear()
        st.switch_page("pages/employees.py")
    st.stop()

employee = employee_match.iloc[0]

# Header with back button, title, and employee switcher
col1, col2, col3 = st.columns([1, 3, 2])

with col1:
    if st.button("← Back to Employees"):
        st.query_params.clear()
        st.switch_page("pages/employees.py")

with col2:
    st.markdown(f"## {employee['name']}")
    role = employee['role'] if pd.notna(employee['role']) else 'N/A'
    pay_type = employee.get('pay_type', 'N/A')
    billable = 'Billable' if employee.get('billable', 0) == 1 else 'Non-billable'
    st.caption(f"Role: {role} | Pay Type: {pay_type} | {billable}")

with col3:
    # Employee switcher dropdown
    employee_names = employees_df['name'].tolist()
    current_index = employee_names.index(employee['name']) if employee['name'] in employee_names else 0

    selected_name = st.selectbox(
        "Switch Employee",
        options=employee_names,
        index=current_index,
        key="employee_switcher",
        label_visibility="collapsed"
    )

    # If selection changed, update session state and rerun
    if selected_name != employee['name']:
        new_employee = employees_df[employees_df['name'] == selected_name].iloc[0]
        st.session_state.selected_employee_id = new_employee['id']
        st.session_state.selected_employee_name = new_employee['name']
        st.query_params.from_dict({"employee_id": str(new_employee['id'])})
        st.rerun()

st.markdown("---")

# Read subtab from query params for deep-linking
default_subtab = st.query_params.get("subtab")
valid_subtabs = ["Project Allocations", "Utilization", "Edit Employee Data"]
if default_subtab and default_subtab not in valid_subtabs:
    default_subtab = None

# Create subtabs
subtab_alloc, subtab_util, subtab_edit = st.tabs(
    ["Project Allocations", "Utilization", "Edit Employee Data"],
    default=default_subtab
)

with subtab_alloc:
    try:
        render_project_allocations_subtab(db, processor, employee_id=employee_id)
    except Exception as e:
        st.error(f"Error loading project allocations: {str(e)}")
        logger.error(f"Error in Project Allocations subtab: {str(e)}", exc_info=True)

with subtab_util:
    try:
        render_combined_utilization_view(db, processor, employee_id=employee_id, widget_prefix="emp")
    except Exception as e:
        st.error(f"Error loading utilization data: {str(e)}")
        logger.error(f"Error in Utilization subtab: {str(e)}", exc_info=True)

with subtab_edit:
    try:
        render_employee_edit_tab(db, processor, employee_id=employee_id)
    except Exception as e:
        st.error(f"Error loading employee edit form: {str(e)}")
        logger.error(f"Error in Edit Employee Data subtab: {str(e)}", exc_info=True)
