import streamlit as st
from pages.projects_details import render_project_details_tab
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Render the project details view
render_project_details_tab(db, processor)
