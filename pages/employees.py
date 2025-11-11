import streamlit as st
from utils.logger import get_logger
from pages.employees_utilization import render_utilization_tab
from pages.employees_list import render_employee_list_tab
from pages.employees_detail import render_employee_detail_tab

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 👥 Employee Management")

tab1, tab2, tab3 = st.tabs(["Utilization", "Employee List", "Employee Detail (Edit)"])

with tab1:
    render_utilization_tab(db, processor)

with tab2:
    render_employee_list_tab(db, processor)

with tab3:
    render_employee_detail_tab(db, processor)
