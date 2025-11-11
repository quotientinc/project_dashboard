import streamlit as st
from utils.logger import get_logger
from pages.projects_list import render_project_list_tab
from pages.projects_details import render_project_details_tab
from pages.projects_edit import render_project_edit_tab
from pages.projects_analytics import render_project_analytics_tab

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 🚀 Project Management (🚨data is in progress)")

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["Project List", "Project Details", "Edit Project", "Project Analytics"])

with tab1:
    render_project_list_tab(db, processor)

with tab2:
    render_project_details_tab(db, processor)

with tab3:
    render_project_edit_tab(db, processor)

with tab4:
    render_project_analytics_tab(db, processor)
