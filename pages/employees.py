import streamlit as st
from utils.logger import get_logger
from pages.employees_utilization import render_utilization_tab
from pages.employees_list import render_employee_list_tab
from pages.employees_detail import render_employee_detail_tab

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 👥 Employee Management")

# Lazy loading: Use radio buttons to select tab and only render the active one
# This prevents all 3 tabs from loading data simultaneously
tab_names = ["Utilization", "Employee List", "Employee Detail (Edit)"]

# Track selected tab in session state
if 'employee_active_tab' not in st.session_state:
    st.session_state.employee_active_tab = tab_names[0]

# Tab selector with custom styling
selected_tab = st.radio(
    "Select View",
    tab_names,
    index=tab_names.index(st.session_state.employee_active_tab),
    horizontal=True,
    key="employee_tab_selector",
    label_visibility="collapsed"
)

# Update session state
st.session_state.employee_active_tab = selected_tab

st.markdown("---")

# Lazy render: Only execute the selected tab's function
if selected_tab == "Utilization":
    render_utilization_tab(db, processor)
elif selected_tab == "Employee List":
    render_employee_list_tab(db, processor)
elif selected_tab == "Employee Detail (Edit)":
    render_employee_detail_tab(db, processor)
