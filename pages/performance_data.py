"""
Performance Data Page

Displays performance metrics data using the get_performance_metrics() data processor.
Shows actuals, projected, and possible data in separate tabs with configurable filters.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
from utils.logger import get_logger

logger = get_logger(__name__)

# Access shared database and processor from session state
db = st.session_state.db_manager
processor = st.session_state.data_processor

# Page title
st.markdown("### 📊 Performance Data")
st.markdown("View performance metrics across actuals, projected, and possible capacity.")

# Filters section
st.markdown("#### Filters")

# Create columns for date pickers and entity filters
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

# Get current year and month for defaults
current_year = datetime.now().year
current_month = datetime.now().month

# Month names
month_names = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

with col1:
    # Start Year selector
    year_options = list(range(current_year - 2, current_year + 2))
    start_year = st.selectbox(
        "Start Year",
        options=year_options,
        index=year_options.index(current_year),
        key="perf_start_year"
    )

with col2:
    # Start Month selector
    start_month_name = st.selectbox(
        "Start Month",
        options=month_names,
        index=0,  # Default to January
        key="perf_start_month"
    )
    start_month = month_names.index(start_month_name) + 1

with col3:
    # End Year selector
    end_year = st.selectbox(
        "End Year",
        options=year_options,
        index=year_options.index(current_year),
        key="perf_end_year"
    )

with col4:
    # End Month selector
    end_month_name = st.selectbox(
        "End Month",
        options=month_names,
        index=11,  # Default to December
        key="perf_end_month"
    )
    end_month = month_names.index(end_month_name) + 1

# Create start and end date strings
start_date = f"{start_year}-{start_month:02d}-01"
# Get last day of end month
last_day = calendar.monthrange(end_year, end_month)[1]
end_date = f"{end_year}-{end_month:02d}-{last_day}"

# Optional entity filters (mutually exclusive)
st.markdown("#### Optional Filters (Choose one or none)")
col5, col6 = st.columns([1, 1])

# Get employees and projects for dropdowns
employees_df = db.get_employees()
projects_df = db.get_projects()

# Create options lists
employee_options = ["All"] + sorted([f"{row['id']} - {row['name']}" for _, row in employees_df.iterrows()])
project_options = ["All"] + sorted(projects_df['id'].tolist())

# Track if a filter is selected to make them mutually exclusive
employee_selected = st.session_state.get('perf_employee_filter', "All") != "All"
project_selected = st.session_state.get('perf_project_filter', "All") != "All"

with col5:
    employee_filter = st.selectbox(
        "Filter by Employee",
        options=employee_options,
        index=0,
        key="perf_employee_filter",
        disabled=project_selected
    )

with col6:
    project_filter = st.selectbox(
        "Filter by Project",
        options=project_options,
        index=0,
        key="perf_project_filter",
        disabled=employee_selected
    )

# Build constraint parameter
constraint = None
if employee_filter != "All":
    # Extract employee ID from "ID - Name" format
    employee_id = employee_filter.split(" - ")[0]
    constraint = {"employee_id": employee_id}
    st.info(f"Filtering by Employee: {employee_filter} (data grouped by project)")
elif project_filter != "All":
    constraint = {"project_id": project_filter}
    st.info(f"Filtering by Project: {project_filter} (data grouped by employee)")

# Add a refresh button
if st.button("🔄 Refresh Data", key="perf_refresh"):
    st.rerun()

st.divider()

# Fetch performance metrics
try:
    with st.spinner("Loading performance metrics..."):
        metrics = processor.get_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            constraint=constraint
        )

        logger.info(f"Loaded performance metrics from {start_date} to {end_date}")

except Exception as e:
    st.error(f"Error loading performance metrics: {str(e)}")
    logger.error(f"Error loading performance metrics: {str(e)}", exc_info=True)
    st.stop()

# Helper function to sort months chronologically
def sort_months_chronologically(month_names):
    """
    Sort month names chronologically (e.g., "January 2024", "February 2024", ..., "January 2025")

    Args:
        month_names: List of month names in format "Month Year"

    Returns:
        Sorted list of month names
    """
    from datetime import datetime

    # Parse month names to datetime objects for sorting
    month_dates = []
    for month_name in month_names:
        try:
            # Parse "January 2025" format
            dt = datetime.strptime(month_name, "%B %Y")
            month_dates.append((month_name, dt))
        except:
            # If parsing fails, keep original
            month_dates.append((month_name, datetime.min))

    # Sort by datetime
    sorted_months = sorted(month_dates, key=lambda x: x[1])

    # Return just the month names
    return [m[0] for m in sorted_months]

# Helper function to convert nested dict to DataFrame
def metrics_to_dataframe(metrics_dict, employees_df, constraint, data_type="actuals"):
    """
    Convert nested metrics dictionary to a pandas DataFrame with months as columns.

    Args:
        metrics_dict: Nested dict with structure {month: {id: {hours, revenue, worked_days}}}
        employees_df: DataFrame of employees for name lookup
        constraint: Filter constraint (employee_id or project_id)
        data_type: Name of the data type for logging

    Returns:
        Tuple of (DataFrame with entities as rows and months as columns, list of entities, list of months)
    """
    if not metrics_dict:
        return pd.DataFrame(), [], []

    # Collect all unique entity IDs (employees or projects)
    all_entities = set()
    for month_data in metrics_dict.values():
        all_entities.update(month_data.keys())

    all_entities = sorted(all_entities)

    # Get all months and sort them chronologically
    all_months = sort_months_chronologically(list(metrics_dict.keys()))

    # Build data structure with entities as rows, months as columns
    data_rows = []
    for entity_id in all_entities:
        # Get entity name
        if constraint and 'employee_id' in constraint:
            # Grouped by project
            entity_name = entity_id
        else:
            # Grouped by employee
            try:
                emp_row = employees_df[employees_df['id'] == int(entity_id)]
                entity_name = emp_row.iloc[0]['name'] if not emp_row.empty else entity_id
            except:
                entity_name = entity_id

        # Create rows for hours, revenue, and days
        hours_row = {'Entity': f'{entity_name}', 'Metric': 'Hours'}
        revenue_row = {'Entity': f'{entity_name}', 'Metric': 'Revenue'}
        days_row = {'Entity': f'{entity_name}', 'Metric': 'Worked Days'}

        for month in all_months:
            if month in metrics_dict and entity_id in metrics_dict[month]:
                hours_row[month] = metrics_dict[month][entity_id]['hours']
                revenue_row[month] = metrics_dict[month][entity_id]['revenue']
                days_row[month] = metrics_dict[month][entity_id]['worked_days']
            else:
                hours_row[month] = 0
                revenue_row[month] = 0
                days_row[month] = 0

        data_rows.extend([hours_row, revenue_row, days_row])

    if not data_rows:
        return pd.DataFrame(), [], []

    df = pd.DataFrame(data_rows)

    return df, all_entities, all_months

# Convert metrics to DataFrames
actuals_df, actuals_entities, actuals_months = metrics_to_dataframe(metrics['actuals'], employees_df, constraint, 'actuals') if metrics['actuals'] else (pd.DataFrame(), [], [])
projected_df, projected_entities, projected_months = metrics_to_dataframe(metrics['projected'], employees_df, constraint, 'projected') if metrics['projected'] else (pd.DataFrame(), [], [])
possible_df, possible_entities, possible_months = metrics_to_dataframe(metrics['possible'], employees_df, constraint, 'possible') if metrics['possible'] else (pd.DataFrame(), [], [])

# Create tabs for each metric type
tab1, tab2, tab3 = st.tabs(["📈 Actuals", "📊 Projected", "💡 Possible"])

# Tab 1: Actuals
with tab1:
    st.markdown("#### Actual Performance (from Time Entries)")
    st.markdown("Based on actual time entries logged in the system (excludes FRINGE.HOL).")

    if actuals_df.empty:
        st.warning("No actual data available for the selected date range and filters.")
    else:
        # Calculate summary metrics from the pivoted data
        # Sum all month columns for hours rows
        hours_rows = actuals_df[actuals_df['Metric'] == 'Hours']
        revenue_rows = actuals_df[actuals_df['Metric'] == 'Revenue']

        total_hours = hours_rows[actuals_months].sum().sum() if actuals_months else 0
        total_revenue = revenue_rows[actuals_months].sum().sum() if actuals_months else 0

        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Hours", f"{total_hours:,.1f}")
        with col2:
            st.metric("Total Revenue", f"${total_revenue:,.2f}")
        with col3:
            avg_hours_per_month = total_hours / len(actuals_months) if len(actuals_months) > 0 else 0
            st.metric("Avg Hours/Month", f"{avg_hours_per_month:,.1f}")

        st.divider()

        # Display the pivoted table (entities as rows, months as columns)
        display_df = actuals_df.copy()

        # Format revenue columns with dollar signs
        for month in actuals_months:
            # Apply formatting to revenue rows
            revenue_mask = display_df['Metric'] == 'Revenue'
            display_df.loc[revenue_mask, month] = display_df.loc[revenue_mask, month].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00")

            # Format hours to 1 decimal
            hours_mask = display_df['Metric'] == 'Hours'
            display_df.loc[hours_mask, month] = display_df.loc[hours_mask, month].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "0.0")

            # Format days as integers
            days_mask = display_df['Metric'] == 'Worked Days'
            display_df.loc[days_mask, month] = display_df.loc[days_mask, month].apply(lambda x: f"{int(x)}" if pd.notna(x) else "0")

        # Display the table
        st.dataframe(display_df, use_container_width=True, height=600)

        # Download button (with original numeric values)
        csv = actuals_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Actuals as CSV",
            data=csv,
            file_name=f"actuals_{start_date}_{end_date}.csv",
            mime="text/csv"
        )

# Tab 2: Projected
with tab2:
    st.markdown("#### Projected Performance (from Allocations)")
    st.markdown("Based on employee allocations and bill rates.")

    if projected_df.empty:
        st.warning("No projected data available for the selected date range and filters.")
    else:
        # Calculate summary metrics from the pivoted data
        hours_rows = projected_df[projected_df['Metric'] == 'Hours']
        revenue_rows = projected_df[projected_df['Metric'] == 'Revenue']

        total_hours = hours_rows[projected_months].sum().sum() if projected_months else 0
        total_revenue = revenue_rows[projected_months].sum().sum() if projected_months else 0

        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Hours", f"{total_hours:,.1f}")
        with col2:
            st.metric("Total Revenue", f"${total_revenue:,.2f}")
        with col3:
            avg_hours_per_month = total_hours / len(projected_months) if len(projected_months) > 0 else 0
            st.metric("Avg Hours/Month", f"{avg_hours_per_month:,.1f}")

        st.divider()

        # Display the pivoted table (entities as rows, months as columns)
        display_df = projected_df.copy()

        # Format revenue columns with dollar signs
        for month in projected_months:
            # Apply formatting to revenue rows
            revenue_mask = display_df['Metric'] == 'Revenue'
            display_df.loc[revenue_mask, month] = display_df.loc[revenue_mask, month].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00")

            # Format hours to 1 decimal
            hours_mask = display_df['Metric'] == 'Hours'
            display_df.loc[hours_mask, month] = display_df.loc[hours_mask, month].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "0.0")

            # Format days as integers
            days_mask = display_df['Metric'] == 'Worked Days'
            display_df.loc[days_mask, month] = display_df.loc[days_mask, month].apply(lambda x: f"{int(x)}" if pd.notna(x) else "0")

        # Display the table
        st.dataframe(display_df, use_container_width=True, height=600)

        # Download button (with original numeric values)
        csv = projected_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Projected as CSV",
            data=csv,
            file_name=f"projected_{start_date}_{end_date}.csv",
            mime="text/csv"
        )

# Tab 3: Possible
with tab3:
    st.markdown("#### Possible Capacity (from Employee Targets)")
    st.markdown("Based on employee target allocations and overhead (revenue set to 0 for future use).")

    if possible_df.empty:
        st.warning("No possible capacity data available for the selected date range and filters.")
    else:
        # Calculate summary metrics from the pivoted data
        hours_rows = possible_df[possible_df['Metric'] == 'Hours']
        revenue_rows = possible_df[possible_df['Metric'] == 'Revenue']

        total_hours = hours_rows[possible_months].sum().sum() if possible_months else 0
        total_revenue = revenue_rows[possible_months].sum().sum() if possible_months else 0

        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Possible Hours", f"{total_hours:,.1f}")
        with col2:
            st.metric("Total Revenue (Reserved)", f"${total_revenue:,.2f}")
        with col3:
            avg_hours_per_month = total_hours / len(possible_months) if len(possible_months) > 0 else 0
            st.metric("Avg Hours/Month", f"{avg_hours_per_month:,.1f}")

        st.divider()

        # Display the pivoted table (entities as rows, months as columns)
        display_df = possible_df.copy()

        # Format revenue columns with dollar signs
        for month in possible_months:
            # Apply formatting to revenue rows
            revenue_mask = display_df['Metric'] == 'Revenue'
            display_df.loc[revenue_mask, month] = display_df.loc[revenue_mask, month].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00")

            # Format hours to 1 decimal
            hours_mask = display_df['Metric'] == 'Hours'
            display_df.loc[hours_mask, month] = display_df.loc[hours_mask, month].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "0.0")

            # Format days as integers
            days_mask = display_df['Metric'] == 'Worked Days'
            display_df.loc[days_mask, month] = display_df.loc[days_mask, month].apply(lambda x: f"{int(x)}" if pd.notna(x) else "0")

        # Display the table
        st.dataframe(display_df, use_container_width=True, height=600)

        # Download button (with original numeric values)
        csv = possible_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Possible as CSV",
            data=csv,
            file_name=f"possible_{start_date}_{end_date}.csv",
            mime="text/csv"
        )

st.divider()
st.markdown("**Note:** Actuals exclude time entries with project_id='FRINGE.HOL'. Revenue is calculated using bill rates from allocations.")
