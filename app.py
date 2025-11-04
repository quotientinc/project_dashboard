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
    # if st.session_state.db_manager.is_empty():
    #     logger.info("Database is empty, generating sample data")
    #     from utils.sample_data import generate_sample_data
    #     generate_sample_data(st.session_state.db_manager)
    #     logger.info("Sample data generation completed")
    # else:
    #     logger.info("Database already populated, skipping sample data generation")

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
performance_data_page = st.Page(
    "pages/performance_data.py",
    title="Performance Data",
    icon="📊"
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
months_page = st.Page(
    "pages/months.py",
    title="Months",
    icon="📅"
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
    performance_data_page,
    financial_page,
    reports_page,
    whatif_page,
    months_page,
    data_page
])

# Quick stats in sidebar
with st.sidebar:
    st.markdown("### 📈 Quick Stats")

    # Load data for stats
    db = st.session_state.db_manager
    projects_df = db.get_projects()
    employees_df = db.get_employees()

    if not projects_df.empty:
        st.metric("Total Projects", len(projects_df))
        st.metric("Active Projects", len(projects_df[projects_df['status'] == 'Active']))
    if not employees_df.empty:
        # Filter for active, billable, salary employees
        current_date = datetime.now().date()
        billable_employees = employees_df[
            (employees_df['billable'] == 1) &
            (employees_df['pay_type'] == 'Salary') &
            (
                (pd.isna(employees_df['term_date'])) |
                (pd.to_datetime(employees_df['term_date']).dt.date >= current_date)
            )
        ]
        st.metric("Total Billable Employees", len(billable_employees))

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