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

# Lazy loading: Use radio buttons to select tab and only render the active one
# This prevents all 4 tabs from loading data simultaneously
tab_names = ["Project List", "Project Details", "Edit Project", "Project Analytics"]

# Track selected tab in session state
if 'project_active_tab' not in st.session_state:
    st.session_state.project_active_tab = tab_names[0]

# Tab selector with custom styling
selected_tab = st.radio(
    "Select View",
    tab_names,
    index=tab_names.index(st.session_state.project_active_tab),
    horizontal=True,
    key="project_tab_selector",
    label_visibility="collapsed"
)

# Update session state
st.session_state.project_active_tab = selected_tab

st.markdown("---")

# Lazy render: Only execute the selected tab's function
if selected_tab == "Project List":
    render_project_list_tab(db, processor)
elif selected_tab == "Project Details":
    render_project_details_tab(db, processor)
elif selected_tab == "Edit Project":
    render_project_edit_tab(db, processor)
elif selected_tab == "Project Analytics":
    render_project_analytics_tab(db, processor)
