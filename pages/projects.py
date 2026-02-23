"""
Projects List page - displays all projects in AgGrid with click-to-navigate.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, ColumnsAutoSizeMode
from utils.project_helpers import safe_budget_percentage
from utils.funding_helpers import calculate_project_utilization
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Initialize grid selection version for clearing selection after navigation
if "projects_grid_selection_version" not in st.session_state:
    st.session_state.projects_grid_selection_version = 0

st.markdown("### Projects")

# YTD date range for utilization calculations
current_date = datetime.now()
ytd_start = datetime(current_date.year, 1, 1).strftime('%Y-%m-%d')
ytd_end = current_date.strftime('%Y-%m-%d')

# Load projects
projects_df = db.get_projects()

if projects_df.empty:
    st.info("No projects found. Import project data to get started.")
    st.stop()

# --- Filters Section ---
col1, col2, col3, col4 = st.columns([2, 1.5, 1, 1])

with col1:
    status_options = ['Active', 'Future', 'Completed', 'On Hold', 'Cancelled']
    selected_statuses = st.multiselect(
        "Filter by Status",
        options=status_options,
        default=['Active', 'Future', 'Completed'],
        help="Select one or more statuses to display"
    )

with col2:
    current_year = current_date.year
    date_filter_options = [
        f"Active in {current_year}",
        "All Projects",
        "Custom Date Range"
    ]
    date_filter = st.selectbox(
        "Date Range",
        options=date_filter_options,
        index=0
    )

with col3:
    util_filter = st.selectbox(
        "Utilization",
        options=["All", "Under-Utilized (<70%)", "Severely (<50%)", "Well Utilized (>=90%)"],
        index=0,
        key="projects_util_filter"
    )

with col4:
    if st.button("+ Add Project", type="primary", use_container_width=True):
        st.info("Project creation dialog coming soon!")

# Custom date range inputs
if date_filter == "Custom Date Range":
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        custom_start = st.date_input("Start Date", value=datetime(current_year, 1, 1))
    with date_col2:
        custom_end = st.date_input("End Date", value=datetime(current_year, 12, 31))

# Search
search_term = st.text_input(
    "Search",
    placeholder="Search by project code, name, client, or PM...",
    label_visibility="collapsed"
)

st.markdown("---")

# --- Apply Filters ---
filtered_df = projects_df.copy()

# Status filter
if selected_statuses:
    filtered_df = filtered_df[filtered_df['status'].isin(selected_statuses)]
else:
    filtered_df = pd.DataFrame()

# Date filter logic
if date_filter == f"Active in {current_year}":
    year_start = pd.Timestamp(datetime(current_year, 1, 1))
    year_end = pd.Timestamp(datetime(current_year, 12, 31))
    filtered_df = filtered_df[
        pd.notna(filtered_df['start_date']) &
        pd.notna(filtered_df['end_date']) &
        (pd.to_datetime(filtered_df['start_date']) <= year_end) &
        (pd.to_datetime(filtered_df['end_date']) >= year_start)
    ]
elif date_filter == "Custom Date Range":
    range_start = pd.Timestamp(custom_start)
    range_end = pd.Timestamp(custom_end)
    filtered_df = filtered_df[
        pd.notna(filtered_df['start_date']) &
        pd.notna(filtered_df['end_date']) &
        (pd.to_datetime(filtered_df['start_date']) <= range_end) &
        (pd.to_datetime(filtered_df['end_date']) >= range_start)
    ]

# Search filter
if search_term:
    search_mask = (
        filtered_df['id'].astype(str).str.contains(search_term, case=False, na=False) |
        filtered_df['name'].str.contains(search_term, case=False, na=False) |
        filtered_df['client'].str.contains(search_term, case=False, na=False) |
        filtered_df['project_manager'].str.contains(search_term, case=False, na=False)
    )
    filtered_df = filtered_df[search_mask]

if filtered_df.empty:
    st.info("No projects match the current filters.")
    st.stop()

# --- Build Display DataFrame ---
display_df = pd.DataFrame()
display_df['id'] = filtered_df['id']
display_df['Project Code'] = filtered_df['id'].astype(str)
display_df['Project Name'] = filtered_df['name']
display_df['Client'] = filtered_df['client']
display_df['PM'] = filtered_df['project_manager']
display_df['Status'] = filtered_df['status']
display_df['Start Date'] = filtered_df['start_date']
display_df['End Date'] = filtered_df['end_date']
display_df['Quoted Value'] = filtered_df['quoted_value']
display_df['Awarded Value'] = filtered_df['awarded_value']
display_df['Budget Used'] = filtered_df['budget_used']

# Calculate Budget % Used
display_df['Budget % Used'] = filtered_df.apply(
    lambda row: safe_budget_percentage(row['budget_used'], row['quoted_value'])[0],
    axis=1
)

# Calculate project utilization (YTD)
with st.spinner("Computing utilization metrics..."):
    util_data_list = []
    for proj_id in filtered_df['id']:
        util_data = calculate_project_utilization(str(proj_id), db, processor, ytd_start, ytd_end)
        util_data_list.append({
            'id': proj_id,
            'Utilization %': util_data['utilization_pct'],
            'Revenue Gap ($)': max(util_data['revenue_gap'], 0) if util_data['revenue_gap'] is not None else None,
        })

    util_df = pd.DataFrame(util_data_list)
    display_df = display_df.merge(util_df, on='id', how='left')

# Apply utilization filter
if util_filter == "Under-Utilized (<70%)":
    display_df = display_df[display_df['Utilization %'].notna() & (display_df['Utilization %'] < 70)]
elif util_filter == "Severely (<50%)":
    display_df = display_df[display_df['Utilization %'].notna() & (display_df['Utilization %'] < 50)]
elif util_filter == "Well Utilized (>=90%)":
    display_df = display_df[display_df['Utilization %'].notna() & (display_df['Utilization %'] >= 90)]

if display_df.empty:
    st.info("No projects match the current filters.")
    st.stop()

# Sort by status, then name
display_df = display_df.sort_values(['Status', 'Project Name'])

# --- Summary Metrics ---
st.caption(f"Showing {len(display_df)} of {len(projects_df)} projects")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Active", len(display_df[display_df['Status'] == 'Active']))
with col2:
    st.metric("Future", len(display_df[display_df['Status'] == 'Future']))
with col3:
    st.metric("Completed", len(display_df[display_df['Status'] == 'Completed']))
with col4:
    total_quoted = display_df['Quoted Value'].sum()
    st.metric("Total Quoted", f"${total_quoted/1e6:.1f}M")
with col5:
    underutilized_count = len(display_df[
        display_df['Utilization %'].notna() & (display_df['Utilization %'] < 70)
    ])
    st.metric("Under-Utilized", underutilized_count,
              help="Projects with <70% utilization of allocated capacity")

st.markdown("---")

# --- AgGrid Configuration ---
currency_formatter = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return '-';
    return '$' + params.value.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
""")

budget_pct_cell_style = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return {};
    if (params.value > 100) {
        return {'backgroundColor': '#ffcccc', 'fontWeight': 'bold'};
    } else if (params.value >= 80) {
        return {'backgroundColor': '#fff9cc'};
    } else {
        return {'backgroundColor': '#ccffcc'};
    }
}
""")

util_pct_cell_style = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return {};
    if (params.value >= 90) {
        return {'backgroundColor': '#ccffcc'};
    } else if (params.value >= 70) {
        return {'backgroundColor': '#fff9cc'};
    } else if (params.value >= 50) {
        return {'backgroundColor': '#ffe0b2'};
    } else {
        return {'backgroundColor': '#ffcccc', 'fontWeight': 'bold'};
    }
}
""")

pct_formatter = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return 'N/A';
    return params.value.toFixed(1) + '%';
}
""")

gb = GridOptionsBuilder.from_dataframe(display_df)
gb.configure_selection(selection_mode='single', use_checkbox=False)
gb.configure_default_column(sortable=True, filterable=False)

# Hide the id column
gb.configure_column("id", hide=True)

# Configure currency columns
for col in ['Quoted Value', 'Awarded Value', 'Budget Used']:
    gb.configure_column(col, valueFormatter=currency_formatter)

# Configure Budget % Used with conditional styling
gb.configure_column(
    'Budget % Used',
    cellStyle=budget_pct_cell_style,
    valueFormatter=pct_formatter
)

# Configure Utilization % with conditional styling
gb.configure_column(
    'Utilization %',
    cellStyle=util_pct_cell_style,
    valueFormatter=pct_formatter
)

# Configure Revenue Gap with currency formatting
gb.configure_column('Revenue Gap ($)', valueFormatter=currency_formatter)

grid_options = gb.build()

# Display AgGrid
with st.popover("How is utilization calculated?"):
    st.markdown("""
**Utilization %** = (Actual Billable Hours / Allocated Hours) x 100

- **Allocated Hours**: From FTE allocations -- `allocated_fte x working_days x 8 hrs/day` summed across all team members. For the current (partial) month, allocated hours are prorated to elapsed working days so utilization reflects actual billing pace.
- **Actual Billable Hours**: From time entries marked as billable
- **Revenue Gap**: Dollar value of unused capacity -- `(Allocated Hours - Actual Billable Hours) x avg bill rate`. The avg bill rate is the blended rate across all team members on the project, weighted by their allocated hours.

**Color Key:**
- Green (>=90%): Well utilized
- Yellow (70-89%): Minor risk -- some unused capacity
- Orange (50-69%): Medium risk -- significant money on the table
- Red (<50%): Severely under-utilized

**N/A** means the project has no FTE allocations, so utilization cannot be calculated.

*Based on YTD (Year-to-Date) data. Current month prorated to elapsed working days.*
    """)

st.info("Click on any project row to view details")

grid_response = AgGrid(
    display_df,
    gridOptions=grid_options,
    columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW,
    height=500,
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    allow_unsafe_jscode=True,
    theme='streamlit',
    key=f"projects_aggrid_v{st.session_state.projects_grid_selection_version}"
)

# --- Handle Row Selection ---
selected_rows = grid_response['selected_rows']
if selected_rows is not None and len(selected_rows) > 0:
    selected_row = selected_rows.iloc[0] if hasattr(selected_rows, 'iloc') else selected_rows[0]

    # Set session state for the selected project
    st.session_state.selected_project_id = selected_row['id']
    st.session_state.selected_project_name = selected_row['Project Name']

    # Clear selection version to prevent re-selection on return
    st.session_state.projects_grid_selection_version += 1

    # Navigate to project view
    st.switch_page("pages/project_view.py")
