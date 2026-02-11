"""
Unified Employee View page - displays a single employee with tabbed interface.
"""
import streamlit as st
import pandas as pd
from utils.logger import get_logger
from pages.employees_detail import render_employee_detail_tab
from pages.employees_allocation import render_allocation_tab
from pages.employees_utilization import render_utilization_tab

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Get employees for the switcher
employees_df = db.get_employees()

if employees_df.empty:
    st.warning("No employees available.")
    if st.button("← Back to Employees"):
        st.switch_page("pages/employees.py")
    st.stop()

# Check if an employee is selected
if 'selected_employee_id' not in st.session_state or st.session_state.selected_employee_id is None:
    st.warning("No employee selected. Please select an employee from the list.")
    if st.button("← Go to Employees List"):
        st.switch_page("pages/employees.py")
    st.stop()

employee_id = st.session_state.selected_employee_id
employee_match = employees_df[employees_df['id'] == employee_id]

if employee_match.empty:
    st.error(f"Employee ID '{employee_id}' not found.")
    if st.button("← Back to Employees"):
        st.switch_page("pages/employees.py")
    st.stop()

employee = employee_match.iloc[0]

# Header with back button, title, and employee switcher
col1, col2, col3 = st.columns([1, 3, 2])

with col1:
    if st.button("← Back to Employees"):
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
        st.rerun()

st.markdown("---")

# Create tabs
tab_details, tab_allocation, tab_utilization = st.tabs([
    "Details", "Allocation", "Utilization"
])

with tab_details:
    render_employee_detail_tab(db, processor, employee_id=employee_id)

with tab_allocation:
    render_allocation_tab(db, processor, employee_id=employee_id)

with tab_utilization:
    render_utilization_tab(db, processor, employee_id=employee_id)
