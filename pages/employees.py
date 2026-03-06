"""
Employees List page - displays all employees in AgGrid with click-to-navigate.
"""
import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, ColumnsAutoSizeMode
from utils.logger import get_logger
from pages.employees_allocation import render_allocation_tab
from pages.employees_utilization import render_combined_utilization_view

logger = get_logger(__name__)


def _format_date_for_export(date_str):
    """Convert YYYY-MM-DD to M/D/YY for CSV export."""
    if not date_str or pd.isna(date_str):
        return ''
    try:
        dt = pd.to_datetime(date_str)
        return f"{dt.month}/{dt.day}/{dt.strftime('%y')}"
    except Exception:
        return ''


def _build_export_df(filtered_df):
    """Build a CSV-export DataFrame matching the Employee Reference CSV import format."""
    export = pd.DataFrame()
    export['Employee Id'] = filtered_df['id']
    export['Last Name'] = filtered_df['name'].apply(lambda n: n.strip().split()[-1] if n and n.strip() else '')
    export['Preferred/First Name'] = filtered_df['name'].apply(
        lambda n: ' '.join(n.strip().split()[:-1]) if n and n.strip() and len(n.strip().split()) > 1 else ''
    )
    export['Billable'] = filtered_df['billable'].apply(lambda x: 'YES' if x == 1 else 'NO')
    export['Hire Date'] = filtered_df['hire_date'].apply(_format_date_for_export)
    export['Term Date'] = filtered_df['term_date'].apply(_format_date_for_export)
    export['Job Title'] = filtered_df['role']
    export['Pay Type Code'] = filtered_df['pay_type'].apply(
        lambda x: 'S' if x == 'Salary' else ('H' if x == 'Hourly' else '')
    )
    export['Base Rate'] = filtered_df['cost_rate']
    export['Annual Salary'] = filtered_df['annual_salary']
    export['PTO Accrual'] = filtered_df['pto_accrual'].apply(
        lambda x: x / 8 if pd.notna(x) and x else ''
    )
    export['Holidays'] = filtered_df['holidays']
    return export

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Initialize grid selection version for clearing selection after navigation
if "employees_grid_selection_version" not in st.session_state:
    st.session_state.employees_grid_selection_version = 0

st.markdown("### Employees")

# Load employees
employees_df = db.get_employees()

if employees_df.empty:
    st.info("No employees found. Import employee data to get started.")
    st.stop()

# Read tab from query params for deep-linking
default_tab = st.query_params.get("tab")
valid_tabs = ["Employees List", "Allocation Overview", "Utilization Overview"]
if default_tab and default_tab not in valid_tabs:
    default_tab = None

tab_list, tab_alloc, tab_util = st.tabs(
    ["Employees List", "Allocation Overview", "Utilization Overview"],
    default=default_tab
)

with tab_list:
    # --- Filters Section ---
    col1, col2, col3, col4 = st.columns([1.5, 1.5, 2, 1])

    with col1:
        billable_filter = st.selectbox(
            "Billable Status",
            options=["All", "Billable", "Non-billable"],
            index=0
        )

    with col2:
        pay_type_filter = st.selectbox(
            "Pay Type",
            options=["All", "Hourly", "Salary"],
            index=0
        )

    with col3:
        search_term = st.text_input(
            "Search",
            placeholder="Search by name or role...",
            label_visibility="collapsed"
        )

    with col4:
        if st.button("+ Add Employee", type="primary", use_container_width=True):
            st.info("Employee creation dialog coming soon!")

    st.markdown("---")

    # --- Apply Filters ---
    filtered_df = employees_df.copy()

    # Billable filter
    if billable_filter == "Billable":
        filtered_df = filtered_df[filtered_df['billable'] == 1]
    elif billable_filter == "Non-billable":
        filtered_df = filtered_df[filtered_df['billable'] != 1]

    # Pay type filter
    if pay_type_filter != "All":
        filtered_df = filtered_df[filtered_df['pay_type'] == pay_type_filter]

    # Search filter
    if search_term:
        search_mask = (
            filtered_df['name'].str.contains(search_term, case=False, na=False) |
            filtered_df['role'].str.contains(search_term, case=False, na=False)
        )
        filtered_df = filtered_df[search_mask]

    if filtered_df.empty:
        st.info("No employees match the current filters.")
        st.stop()

    # --- Build Display DataFrame ---
    display_df = pd.DataFrame()
    display_df['id'] = filtered_df['id']
    display_df['Name'] = filtered_df['name']
    display_df['Role'] = filtered_df['role']
    display_df['Pay Type'] = filtered_df['pay_type']
    display_df['Billable'] = filtered_df['billable'].apply(lambda x: 'Yes' if x == 1 else 'No')
    display_df['Hire Date'] = filtered_df['hire_date']
    display_df['Term Date'] = filtered_df['term_date']
    display_df['Cost Rate'] = filtered_df['cost_rate']
    display_df['Target Allocation'] = filtered_df['target_allocation'].fillna(1.0) * 100  # Convert to percentage

    # Sort by name
    display_df = display_df.sort_values('Name')

    # --- Summary Metrics ---
    st.caption(f"Showing {len(display_df)} of {len(employees_df)} employees")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", len(display_df))
    with col2:
        billable_count = len(filtered_df[filtered_df['billable'] == 1])
        st.metric("Billable", billable_count)
    with col3:
        salary_count = len(filtered_df[filtered_df['pay_type'] == 'Salary'])
        st.metric("Salary", salary_count)
    with col4:
        hourly_count = len(filtered_df[filtered_df['pay_type'] == 'Hourly'])
        st.metric("Hourly", hourly_count)

    st.markdown("---")

    # --- AgGrid Configuration ---
    currency_formatter = JsCode("""
    function(params) {
        if (params.value === null || params.value === undefined) return '-';
        return '$' + params.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    """)

    pct_formatter = JsCode("""
    function(params) {
        if (params.value === null || params.value === undefined) return '-';
        return params.value.toFixed(0) + '%';
    }
    """)

    billable_cell_style = JsCode("""
    function(params) {
        if (params.value === 'Yes') {
            return {'backgroundColor': '#ccffcc', 'fontWeight': 'bold'};
        } else {
            return {'backgroundColor': '#f0f0f0'};
        }
    }
    """)

    gb = GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_selection(selection_mode='single', use_checkbox=False)
    gb.configure_default_column(sortable=True, filterable=False)

    # Hide the id column
    gb.configure_column("id", hide=True)

    # Configure currency column
    gb.configure_column('Cost Rate', valueFormatter=currency_formatter)

    # Configure percentage column
    gb.configure_column('Target Allocation', valueFormatter=pct_formatter)

    # Configure billable column with styling
    gb.configure_column('Billable', cellStyle=billable_cell_style)

    grid_options = gb.build()

    # Display AgGrid
    st.info("Click on any employee row to view details")

    grid_response = AgGrid(
        display_df,
        gridOptions=grid_options,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW,
        height=500,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=True,
        theme='streamlit',
        key=f"employees_aggrid_v{st.session_state.employees_grid_selection_version}"
    )

    # --- Handle Row Selection ---
    selected_rows = grid_response['selected_rows']
    if selected_rows is not None and len(selected_rows) > 0:
        selected_row = selected_rows.iloc[0] if hasattr(selected_rows, 'iloc') else selected_rows[0]

        # Set session state for the selected employee
        st.session_state.selected_employee_id = selected_row['id']
        st.session_state.selected_employee_name = selected_row['Name']

        # Clear selection version to prevent re-selection on return
        st.session_state.employees_grid_selection_version += 1

        # Navigate to employee view
        st.switch_page("pages/employee_view.py")

    # --- CSV Export ---
    export_df = _build_export_df(filtered_df)
    csv_data = export_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Employee CSV",
        data=csv_data,
        file_name="employees.csv",
        mime="text/csv",
    )

with tab_alloc:
    try:
        render_allocation_tab(db, processor, employee_id=None)
    except Exception as e:
        st.error(f"Error loading allocation data: {str(e)}")

with tab_util:
    try:
        render_combined_utilization_view(db, processor, employee_id=None)
    except Exception as e:
        st.error(f"Error loading utilization data: {str(e)}")
