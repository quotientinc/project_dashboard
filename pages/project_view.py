"""
Unified Project View page - displays a single project with tabbed interface.

Provides a unified view of a project with tabs for Details, Edit, Review, Timeline, and Analytics.
Uses session state to track the selected project and allows switching between projects via dropdown.
"""
import streamlit as st
import pandas as pd
from utils.logger import get_logger
from pages.projects_details import render_project_details_tab
from pages.projects_edit import render_project_edit_tab
from pages.project_review_details import render_project_review_tab
from pages.project_timeline_details import render_project_timeline_tab
from pages.projects_analytics import render_project_analytics_tab

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Get projects for the switcher
projects_df = db.get_projects()

if projects_df.empty:
    st.warning("No projects available.")
    if st.button("Back to Projects"):
        st.switch_page("pages/projects.py")
    st.stop()

# Check if a project is selected
if 'selected_project_id' not in st.session_state or st.session_state.selected_project_id is None:
    st.warning("No project selected. Please select a project from the list.")
    if st.button("Go to Projects List"):
        st.switch_page("pages/projects.py")
    st.stop()

project_id = st.session_state.selected_project_id
project_match = projects_df[projects_df['id'] == project_id]

if project_match.empty:
    st.error(f"Project '{project_id}' not found.")
    if st.button("Back to Projects"):
        st.switch_page("pages/projects.py")
    st.stop()

project = project_match.iloc[0]

# Header with back button, title, and project switcher
col1, col2, col3 = st.columns([1, 3, 2])

with col1:
    if st.button("Back to Projects", key="back_to_projects_btn"):
        st.switch_page("pages/projects.py")

with col2:
    st.markdown(f"## {project['name']}")
    client_display = project['client'] if pd.notna(project['client']) else 'N/A'
    pm_display = project['project_manager'] if pd.notna(project['project_manager']) else 'N/A'
    status_display = project['status'] if pd.notna(project['status']) else 'N/A'
    st.caption(f"Client: {client_display} | PM: {pm_display} | Status: {status_display}")

with col3:
    # Project switcher dropdown
    project_names = projects_df['name'].tolist()
    current_index = project_names.index(project['name']) if project['name'] in project_names else 0

    selected_name = st.selectbox(
        "Switch Project",
        options=project_names,
        index=current_index,
        key="project_switcher",
        label_visibility="collapsed"
    )

    # If selection changed, update session state and rerun
    if selected_name != project['name']:
        new_project = projects_df[projects_df['name'] == selected_name].iloc[0]
        st.session_state.selected_project_id = new_project['id']
        st.session_state.selected_project_name = new_project['name']
        st.rerun()

st.markdown("---")

# Create tabs
tab_details, tab_edit, tab_review, tab_timeline, tab_analytics = st.tabs([
    "Details", "Edit", "Review", "Timeline", "Analytics"
])

with tab_details:
    try:
        render_project_details_tab(db, processor, project_id=project_id)
    except Exception as e:
        st.error(f"Error loading project details: {str(e)}")
        logger.error(f"Error in Details tab: {str(e)}", exc_info=True)

with tab_edit:
    try:
        render_project_edit_tab(db, processor, project_id=project_id)
    except Exception as e:
        st.error(f"Error loading project edit form: {str(e)}")
        logger.error(f"Error in Edit tab: {str(e)}", exc_info=True)

with tab_review:
    try:
        # Review tab shows funding-focused project review
        # Note: render_project_review_tab shows all projects with filtering capability
        # The user can filter to the current project if desired
        render_project_review_tab(db, processor)
    except Exception as e:
        st.error(f"Error loading project review: {str(e)}")
        logger.error(f"Error in Review tab: {str(e)}", exc_info=True)

with tab_timeline:
    try:
        render_project_timeline_tab(db, processor, project_id=project_id)
    except Exception as e:
        st.error(f"Error loading project timeline: {str(e)}")
        logger.error(f"Error in Timeline tab: {str(e)}", exc_info=True)

with tab_analytics:
    try:
        # Analytics tab shows multi-project comparison
        # The user can select projects to compare, including the current one
        render_project_analytics_tab(db, processor)
    except Exception as e:
        st.error(f"Error loading project analytics: {str(e)}")
        logger.error(f"Error in Analytics tab: {str(e)}", exc_info=True)
