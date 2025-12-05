import streamlit as st
from pages.employees_utilization import render_utilization_tab
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Render the employee utilization view
render_utilization_tab(db, processor)
