import logging
from datetime import datetime, timedelta

# Setup logging FIRST, before any Streamlit imports
from utils.logger import setup_logging, get_logger
setup_logging(log_level=logging.INFO)
logger = get_logger(__name__)

# Now import Streamlit and other dependencies
import streamlit as st
import pandas as pd

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="Project Management Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Import database utilities
from utils.database import DatabaseManager
from utils.data_processor import DataProcessor

# Initialize session state BEFORE defining pages
# This ensures session state exists when page modules are imported
if 'db_manager' not in st.session_state:
    logger.info("Initializing database manager and data processor")
    st.session_state.db_manager = DatabaseManager()
    st.session_state.data_processor = DataProcessor()

    # Initialize with sample data if database is empty
    if st.session_state.db_manager.is_empty():
        logger.info("Database is empty, generating sample data")
        from utils.sample_data import generate_sample_data
        generate_sample_data(st.session_state.db_manager)
        logger.info("Sample data generation completed")
    else:
        logger.info("Database already populated, skipping sample data generation")

# Initialize filters in session state if not present
if 'filters' not in st.session_state:
    st.session_state.filters = {
        'start_date': datetime.now() - timedelta(days=180),
        'end_date': datetime.now() + timedelta(days=180),
        'projects': [],
        'employees': [],
        'departments': [],
        'status': ['Active']
    }

# Define pages using st.Page
overview_page = st.Page(
    "pages/overview.py",
    title="Overview Dashboard",
    icon="📊",
    default=True
)
projects_page = st.Page(
    "pages/projects.py",
    title="Projects",
    icon="🚀"
)
employees_page = st.Page(
    "pages/employees.py",
    title="Employees",
    icon="👥"
)
financial_page = st.Page(
    "pages/financial.py",
    title="Financial Analysis",
    icon="💰"
)
reports_page = st.Page(
    "pages/reports.py",
    title="Reports",
    icon="📈"
)
whatif_page = st.Page(
    "pages/what_if.py",
    title="What-If Scenarios",
    icon="🔮"
)
data_page = st.Page(
    "pages/data_management.py",
    title="Data Management",
    icon="💾"
)

# Create navigation
pg = st.navigation([
    overview_page,
    projects_page,
    employees_page,
    financial_page,
    reports_page,
    whatif_page,
    data_page
])

# Global filters in sidebar
with st.sidebar:
    st.markdown("### 🔍 Global Filters")

    # Load filter options
    db = st.session_state.db_manager
    projects_df = db.get_projects()
    employees_df = db.get_employees()

    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now() - timedelta(days=180),
            key="global_start_date"
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now() + timedelta(days=180),
            key="global_end_date"
        )

    # Project filter
    selected_projects = st.multiselect(
        "Filter by Project",
        options=projects_df['name'].tolist() if not projects_df.empty else [],
        default=None,
        key="global_project_filter"
    )

    # Employee filter
    selected_employees = st.multiselect(
        "Filter by Employee",
        options=employees_df['name'].tolist() if not employees_df.empty else [],
        default=None,
        key="global_employee_filter"
    )

    # Department filter
    departments = employees_df['department'].unique().tolist() if not employees_df.empty else []
    selected_departments = st.multiselect(
        "Filter by Department",
        options=departments,
        default=None,
        key="global_department_filter"
    )

    # Status filter
    status_options = ["Active", "Completed", "On Hold", "Cancelled"]
    selected_status = st.multiselect(
        "Project Status",
        options=status_options,
        default=["Active"],
        key="global_status_filter"
    )

    st.markdown("---")

    # Quick stats
    st.markdown("### 📈 Quick Stats")
    if not projects_df.empty:
        st.metric("Total Projects", len(projects_df))
        st.metric("Active Projects", len(projects_df[projects_df['status'] == 'Active']))
    if not employees_df.empty:
        st.metric("Total Employees", len(employees_df))
        st.metric("Avg Utilization", f"{employees_df['utilization'].mean():.1f}%")

# Store filters in session state for access by pages
st.session_state.filters = {
    'start_date': start_date,
    'end_date': end_date,
    'projects': selected_projects,
    'employees': selected_employees,
    'departments': selected_departments,
    'status': selected_status
}

# Run the selected page
pg.run()

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Project Management Dashboard v1.0 | Last updated: {0}
    </div>
    """.format(datetime.now().strftime("%Y-%m-%d %H:%M")),
    unsafe_allow_html=True
)