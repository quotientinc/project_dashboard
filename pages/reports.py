import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 📑 Reports")

# Function definitions
def generate_executive_summary(db, processor):
    st.markdown("#### Executive Summary Report")

    # Date range
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date")
    with col2:
        end_date = st.date_input("End Date")

    if st.button("Generate Report"):
        # Load data
        projects_df = db.get_projects()
        employees_df = db.get_employees()
        expenses_df = db.get_expenses()

        # Report header
        st.markdown(f"### Report Period: {start_date} to {end_date}")
        st.markdown(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Executive metrics
        st.markdown("#### Key Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Active Projects", len(projects_df[projects_df['status'] == 'Active']))
        with col2:
            st.metric("Total Revenue", f"${projects_df['revenue_actual'].sum():,.0f}")
        with col3:
            st.metric("Total Costs", f"${projects_df['budget_used'].sum():,.0f}")
        with col4:
            profit = projects_df['revenue_actual'].sum() - projects_df['budget_used'].sum()
            st.metric("Net Profit", f"${profit:,.0f}")

        # Project summary
        st.markdown("#### Project Summary")
        summary_df = projects_df[['name', 'status', 'budget_allocated', 'budget_used', 'revenue_actual']].copy()
        summary_df['Budget Variance'] = summary_df['budget_allocated'] - summary_df['budget_used']
        st.dataframe(summary_df, width='stretch', hide_index=True)

        # Download option
        if st.button("Download Report"):
            csv = summary_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"executive_summary_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

def generate_project_status_report(db, processor):
    st.markdown("#### Project Status Report")

    projects_df = db.get_projects()

    if not projects_df.empty:
        selected_project = st.selectbox("Select Project", projects_df['name'].tolist())

        if st.button("Generate Report"):
            project = projects_df[projects_df['name'] == selected_project].iloc[0]
            allocations_df = db.get_allocations(project_id=project['id'])
            expenses_df = db.get_expenses(project_id=project['id'])

            # Project header
            st.markdown(f"### {project['name']}")
            st.markdown(f"**Client:** {project['client']}")
            st.markdown(f"**Status:** {project['status']}")
            st.markdown(f"**Project Manager:** {project['project_manager']}")

            # Progress metrics
            col1, col2, col3 = st.columns(3)

            with col1:
                budget_progress = (project['budget_used'] / project['budget_allocated'] * 100) if project['budget_allocated'] > 0 else 0
                st.metric("Budget Progress", f"{budget_progress:.1f}%")
                st.progress(min(budget_progress / 100, 1.0))

            with col2:
                revenue_progress = (project['revenue_actual'] / project['revenue_projected'] * 100) if project['revenue_projected'] > 0 else 0
                st.metric("Revenue Progress", f"{revenue_progress:.1f}%")
                st.progress(min(revenue_progress / 100, 1.0))

            with col3:
                days_total = (pd.to_datetime(project['end_date']) - pd.to_datetime(project['start_date'])).days
                days_elapsed = (datetime.now() - pd.to_datetime(project['start_date'])).days
                time_progress = (days_elapsed / days_total * 100) if days_total > 0 else 0
                st.metric("Time Progress", f"{time_progress:.1f}%")
                st.progress(min(time_progress / 100, 1.0))

            # Team allocation
            if not allocations_df.empty:
                st.markdown("#### Team Allocation")
                st.dataframe(
                    allocations_df[['employee_name', 'role', 'allocated_fte']],
                    width='stretch',
                    hide_index=True
                )

def generate_resource_report(db, processor):
    st.markdown("#### Resource Utilization Report")

    period = st.selectbox("Select Period", ["Current Month", "Last Month", "Last Quarter", "Custom"])

    if st.button("Generate Report"):
        employees_df = db.get_employees()
        allocations_df = db.get_allocations()
        time_entries_df = db.get_time_entries()

        if not employees_df.empty:
            utilization_df = processor.calculate_employee_utilization(
                employees_df, allocations_df, time_entries_df
            )

            # Summary metrics
            st.markdown("#### Utilization Summary")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Average Utilization", f"{utilization_df['utilization_rate'].mean():.1f}%")
            with col2:
                st.metric("Total Billable Hours", f"{utilization_df['billable_hours'].sum():.0f}")
            with col3:
                st.metric("Revenue Generated", f"${utilization_df['revenue_generated'].sum():,.0f}")

            # Detailed table
            st.markdown("#### Employee Details")
            display_df = utilization_df[['name', 'utilization_rate', 'billable_hours', 'revenue_generated']]
            st.dataframe(display_df, width='stretch', hide_index=True)

            # Utilization chart
            # TODO: Resolve and come back to this
            """fig = px.bar(
                utilization_df,
                x='name',
                y='utilization_rate',
                color=title="Utilization by Employee"
            )
            st.plotly_chart(fig, width='stretch')"""

def generate_financial_report(db, processor):
    st.markdown("#### Financial Report")

    report_period = st.selectbox(
        "Report Period",
        ["Monthly", "Quarterly", "Annual", "Custom"]
    )

    if st.button("Generate Report"):
        projects_df = db.get_projects()
        expenses_df = db.get_expenses()

        # Financial summary
        st.markdown("#### Financial Summary")

        total_revenue = projects_df['revenue_actual'].sum()
        total_costs = projects_df['budget_used'].sum()
        gross_profit = total_revenue - total_costs
        profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Revenue", f"${total_revenue:,.0f}")
        with col2:
            st.metric("Total Costs", f"${total_costs:,.0f}")
        with col3:
            st.metric("Gross Profit", f"${gross_profit:,.0f}")
        with col4:
            st.metric("Profit Margin", f"{profit_margin:.1f}%")

        # Project financials
        st.markdown("#### Project Financials")
        financial_df = projects_df[['name', 'revenue_actual', 'budget_used']].copy()
        financial_df['Profit'] = financial_df['revenue_actual'] - financial_df['budget_used']
        financial_df['Margin %'] = (financial_df['Profit'] / financial_df['revenue_actual'] * 100).round(1)
        st.dataframe(financial_df, width='stretch', hide_index=True)

        # Expense breakdown
        if not expenses_df.empty:
            st.markdown("#### Expense Breakdown")
            expense_summary = expenses_df.groupby('category')['amount'].sum().reset_index()

            fig = px.pie(
                expense_summary,
                values='amount',
                names='category',
                title="Expenses by Category"
            )
            st.plotly_chart(fig, width='stretch')

def generate_custom_report(db, processor):
    st.markdown("#### Custom Report Builder")

    # Select data to include
    st.markdown("##### Select Data to Include")
    col1, col2, col3 = st.columns(3)

    with col1:
        include_projects = st.checkbox("Projects", value=True)
        include_employees = st.checkbox("Employees", value=True)
    with col2:
        include_financials = st.checkbox("Financials", value=True)
        include_allocations = st.checkbox("Allocations", value=True)
    with col3:
        include_expenses = st.checkbox("Expenses", value=True)
        include_time_entries = st.checkbox("Time Entries", value=False)

    # Filters
    st.markdown("##### Filters")
    projects_df = db.get_projects()

    selected_projects = st.multiselect(
        "Select Projects",
        projects_df['name'].tolist() if not projects_df.empty else []
    )

    date_range = st.date_input(
        "Date Range",
        value=(datetime.now() - pd.Timedelta(days=30), datetime.now()),
        key="custom_date_range"
    )

    if st.button("Generate Custom Report"):
        report_data = {}

        if include_projects:
            projects = db.get_projects()
            if selected_projects:
                projects = projects[projects['name'].isin(selected_projects)]
            report_data['Projects'] = projects

        if include_employees:
            report_data['Employees'] = db.get_employees()

        if include_allocations:
            report_data['Allocations'] = db.get_allocations()

        if include_expenses:
            report_data['Expenses'] = db.get_expenses()

        if include_time_entries and len(date_range) == 2:
            report_data['Time Entries'] = db.get_time_entries(
                start_date=date_range[0].strftime('%Y-%m-%d'),
                end_date=date_range[1].strftime('%Y-%m-%d')
            )

        # Display report
        for section, data in report_data.items():
            if not data.empty:
                st.markdown(f"#### {section}")
                st.dataframe(data, width='stretch', hide_index=True)

                # Download option for each section
                csv = data.to_csv(index=False)
                st.download_button(
                    label=f"Download {section} CSV",
                    data=csv,
                    file_name=f"{section.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key=f"download_{section}"
                )

# Report type selection
report_type = st.selectbox(
    "Select Report Type",
    ["Executive Summary", "Project Status Report", "Resource Utilization Report",
     "Financial Report", "Custom Report"]
)

# Call the appropriate function
if report_type == "Executive Summary":
    generate_executive_summary(db, processor)
elif report_type == "Project Status Report":
    generate_project_status_report(db, processor)
elif report_type == "Resource Utilization Report":
    generate_resource_report(db, processor)
elif report_type == "Financial Report":
    generate_financial_report(db, processor)
else:
    generate_custom_report(db, processor)