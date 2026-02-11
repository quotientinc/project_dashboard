"""
Employee Utilization Analysis tab - detailed monthly and YTD utilization tracking.
"""
import html

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import calendar
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

from utils.logger import get_logger

logger = get_logger(__name__)


def render_utilization_tab(db, processor, employee_id=None):
    """Render the Employee Utilization Analysis tab with monthly and YTD metrics.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        employee_id: Optional employee ID. If provided, filters the view to show only that employee's utilization.
    """
    st.markdown("#### Employee Utilization Analysis")

    # Tab selector
    tab_selection = st.radio(
        "View",
        ["Monthly Detail", "Utilization Summary", "Utilization Timeline"],
        horizontal=True,
        key="util_tab_selection"
    )

    # Initialize session state for grid selection versioning
    if "grid_selection_version" not in st.session_state:
        st.session_state.grid_selection_version = 0

    # Shared year selector
    current_year = datetime.now().year
    year_options = list(range(current_year - 2, current_year + 2))

    if tab_selection == "Monthly Detail":
        _render_monthly_detail_tab(db, processor, year_options, current_year, employee_id=employee_id)
    elif tab_selection == "Utilization Summary":
        _render_utilization_summary_tab(db, processor, year_options, current_year, employee_id=employee_id)
    elif tab_selection == "Utilization Timeline":
        _render_utilization_timeline_tab(db, processor, year_options, current_year, employee_id=employee_id)


def _render_monthly_detail_tab(db, processor, year_options, current_year, employee_id=None):
    """Render the Monthly Detail tab (original utilization table).

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        year_options: List of years for the year selector
        current_year: Current year for default selection
        employee_id: Optional employee ID to filter results to a single employee
    """
    # Date range selection
    col1, col2 = st.columns([1, 1])

    with col1:
        # Year selector
        selected_year = st.selectbox(
            "Year",
            options=year_options,
            index=year_options.index(current_year),
            key="util_year_filter"
        )

    with col2:
        # Month selector
        current_month = datetime.now().month
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        selected_month_name = st.selectbox(
            "Month",
            options=month_names,
            index=current_month - 1,
            key="util_month_filter"
        )
        selected_month = month_names.index(selected_month_name) + 1

    # Build date range for get_performance_metrics
    start_date = f"{selected_year}-{selected_month:02d}-01"
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    end_date = f"{selected_year}-{selected_month:02d}-{last_day}"

    # Get performance metrics
    try:
        with st.spinner("Loading utilization data..."):
            # Get monthly metrics for selected month
            metrics = processor.get_performance_metrics(
                start_date=start_date,
                end_date=end_date
            )

            # Get YTD metrics (January 1st through end of selected month)
            ytd_start_date = f"{selected_year}-01-01"
            ytd_metrics = processor.get_performance_metrics(
                start_date=ytd_start_date,
                end_date=end_date
            )

        # Helper function to calculate working days in a month range
        def get_working_days_in_range(start_date, end_date, months_df, year, month):
            """Calculate working days between start and end date for a specific month"""
            # Get month info
            month_info = months_df[
                (months_df['year'] == year) &
                (months_df['month'] == month)
            ]

            if month_info.empty:
                return 21  # Default fallback

            working_days_in_month = int(month_info['working_days'].iloc[0])

            # Calculate the actual working days the employee was active
            month_start = datetime(year, month, 1).date()
            month_end = datetime(year, month, calendar.monthrange(year, month)[1]).date()

            # Determine actual start and end dates for this employee in this month
            actual_start = max(start_date, month_start)
            actual_end = min(end_date, month_end)

            # If they worked the entire month, return full working days
            if actual_start == month_start and actual_end == month_end:
                return working_days_in_month

            # Calculate proportion of month worked
            days_in_month = (month_end - month_start).days + 1
            days_worked = (actual_end - actual_start).days + 1
            proportion = days_worked / days_in_month

            # Return prorated working days
            return int(working_days_in_month * proportion)

        # Extract month key (should only be one month)
        month_names_list = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_key = f"{month_names_list[selected_month - 1]} {selected_year}"

        # Calculate first and last day of report month for filtering
        first_day_of_month = datetime(selected_year, selected_month, 1).date()
        last_day_of_month = datetime(selected_year, selected_month, last_day).date()

        # Get months data for working days calculation
        months_df = db.get_months()

        # Get time entries for PTO calculation
        time_entries_df = db.get_time_entries(start_date=start_date, end_date=end_date)

        # Calculate PTO hours by employee for this month
        pto_by_employee = {}
        holiday_by_employee = {}
        if not time_entries_df.empty:
            pto_entries = time_entries_df[time_entries_df['project_id'] == 'FRINGE.PTO']
            if not pto_entries.empty:
                pto_by_employee = pto_entries.groupby('employee_id')['hours'].sum().to_dict()

            # Extract holiday hours (FRINGE.HOL)
            holiday_entries = time_entries_df[time_entries_df['project_id'] == 'FRINGE.HOL']
            if not holiday_entries.empty:
                holiday_by_employee = holiday_entries.groupby('employee_id')['hours'].sum().to_dict()

        # Helper function to get project breakdown for an employee
        def get_employee_project_breakdown(employee_id, time_entries_df):
            """Generate project-level breakdown for a specific employee"""
            # Filter time entries for this employee
            emp_entries = time_entries_df[time_entries_df['employee_id'] == employee_id]

            if emp_entries.empty:
                return pd.DataFrame(columns=['Project', 'Billable Hrs', 'Non-billable Hrs', 'Total Hrs', '% of Total'])

            # Group by project and billable status
            breakdown = emp_entries.groupby(['project_name', 'billable'])['hours'].sum().reset_index()

            # Pivot to get billable and non-billable columns
            breakdown_pivot = breakdown.pivot(index='project_name', columns='billable', values='hours').reset_index()
            breakdown_pivot.columns.name = None

            # Rename columns - billable=0 is non-billable, billable=1 is billable
            column_map = {'project_name': 'Project'}
            if 0 in breakdown_pivot.columns:
                column_map[0] = 'Non-billable Hrs'
            if 1 in breakdown_pivot.columns:
                column_map[1] = 'Billable Hrs'

            breakdown_pivot = breakdown_pivot.rename(columns=column_map)

            # Fill NaN values with 0
            if 'Billable Hrs' not in breakdown_pivot.columns:
                breakdown_pivot['Billable Hrs'] = 0
            if 'Non-billable Hrs' not in breakdown_pivot.columns:
                breakdown_pivot['Non-billable Hrs'] = 0

            # Calculate total and percentage
            breakdown_pivot['Total Hrs'] = breakdown_pivot['Billable Hrs'] + breakdown_pivot['Non-billable Hrs']
            total_hours = breakdown_pivot['Total Hrs'].sum()
            breakdown_pivot['% of Total'] = (breakdown_pivot['Total Hrs'] / total_hours * 100).round(1)

            # Sort by total hours descending
            breakdown_pivot = breakdown_pivot.sort_values('Total Hrs', ascending=False)

            return breakdown_pivot

        def clear_grid_selection():
            """Callback to clear grid selection when dialog is dismissed"""
            st.session_state.grid_selection_version += 1

        # Dialog function for showing employee project breakdown
        @st.dialog("Employee Project Breakdown", width="large", on_dismiss=clear_grid_selection)
        def show_project_breakdown(emp_id, emp_name, month_key, time_entries_df):
            """Display project-level breakdown for a selected employee in a modal dialog"""
            st.markdown(f"### {emp_name}")
            st.caption(f"{month_key}")

            # Get project breakdown
            breakdown_df = get_employee_project_breakdown(emp_id, time_entries_df)

            if not breakdown_df.empty:
                col1, col2 = st.columns([1, 1])

                with col1:
                    # Display breakdown table
                    st.markdown("#### Hours by Project")

                    # Format the breakdown table for display
                    breakdown_display = breakdown_df.copy()
                    breakdown_display['Billable Hrs'] = breakdown_display['Billable Hrs'].round(1)
                    breakdown_display['Non-billable Hrs'] = breakdown_display['Non-billable Hrs'].round(1)
                    breakdown_display['Total Hrs'] = breakdown_display['Total Hrs'].round(1)

                    st.dataframe(
                        breakdown_display,
                        width='stretch',
                        hide_index=True,
                        height=400
                    )

                with col2:
                    # Create pie chart
                    st.markdown("#### Distribution")

                    # Prepare data for pie chart - separate billable and non-billable
                    chart_data = []
                    for _, proj_row in breakdown_df.iterrows():
                        if proj_row['Billable Hrs'] > 0:
                            chart_data.append({
                                'Category': f"{proj_row['Project']} (Billable)",
                                'Hours': proj_row['Billable Hrs'],
                                'Type': 'Billable'
                            })
                        if proj_row['Non-billable Hrs'] > 0:
                            chart_data.append({
                                'Category': f"{proj_row['Project']} (Non-billable)",
                                'Hours': proj_row['Non-billable Hrs'],
                                'Type': 'Non-billable'
                            })

                    chart_df = pd.DataFrame(chart_data)

                    if not chart_df.empty:
                        fig = px.pie(
                            chart_df,
                            values='Hours',
                            names='Category',
                            color='Type',
                            color_discrete_map={
                                'Billable': '#2E7D32',
                                'Non-billable': '#FFA726'
                            }
                        )
                        fig.update_layout(height=400, showlegend=True)
                        st.plotly_chart(fig, width='stretch')
            else:
                st.info(f"No time entries found for {emp_name} in {month_key}")

        # Get employees dataframe for utilization calculations
        employees_df = db.get_employees()

        # Filter to specific employee if employee_id is provided
        if employee_id is not None:
            employees_df = employees_df[employees_df['id'] == employee_id]
            if employees_df.empty:
                st.error(f"Employee {employee_id} not found")
                return

        # Build utilization DataFrame
        util_data = []

        for _, emp in employees_df.iterrows():
            emp_id_str = str(emp['id'])

            # Skip non-billable employees
            if emp.get('billable', 0) != 1:
                continue

            # Determine employee's active date range
            if pd.notna(emp.get('hire_date')):
                hire_date = pd.to_datetime(emp['hire_date']).date()
                if hire_date > last_day_of_month:
                    continue  # Skip - hired after this month
            else:
                hire_date = first_day_of_month  # Assume active from start of month

            if pd.notna(emp.get('term_date')):
                term_date = pd.to_datetime(emp['term_date']).date()
                if term_date < first_day_of_month:
                    continue  # Skip - terminated before this month
            else:
                term_date = last_day_of_month  # Assume active through end of month

            # Get data from metrics
            actuals = metrics['actuals'].get(month_key, {}).get(emp_id_str, {'hours': 0, 'billable_hours': 0, 'revenue': 0, 'worked_days': 0})
            projected = metrics['projected'].get(month_key, {}).get(emp_id_str, {'hours': 0, 'revenue': 0, 'worked_days': 0})
            possible = metrics['possible'].get(month_key, {}).get(emp_id_str, {'hours': 0, 'revenue': 0, 'worked_days': 0})

            # Adjust possible hours based on hire/term dates (not time entry days)
            possible_hours = possible['hours']
            possible_worked_days = possible['worked_days']

            # Calculate actual working days based on hire/term dates
            actual_working_days_in_month = get_working_days_in_range(
                hire_date, term_date, months_df, selected_year, selected_month
            )

            # Adjust possible hours if employee worked partial month
            if actual_working_days_in_month != possible_worked_days and possible_worked_days > 0:
                daily_rate = possible_hours / possible_worked_days
                adjusted_possible_hours = daily_rate * actual_working_days_in_month
            else:
                adjusted_possible_hours = possible_hours

            # Calculate utilization metrics
            actual_hours = actuals['hours']
            actual_billable_hours = actuals['billable_hours']
            projected_hours = projected['hours']
            actual_worked_days = actuals['worked_days']  # Days with time entries (for display only)

            # Get PTO hours for this employee
            pto_hours = pto_by_employee.get(emp['id'], 0)

            # Get Holiday hours for this employee
            holiday_hours = holiday_by_employee.get(emp['id'], 0)

            # Calculate available hours (exclude PTO and Holiday from denominator)
            available_hours = max(adjusted_possible_hours - pto_hours - holiday_hours, 0)

            # Calculate other non-billable hours (excluding PTO and Holiday)
            total_nonbillable_hours = actual_hours - actual_billable_hours
            other_nonbillable_hours = max(total_nonbillable_hours - pto_hours - holiday_hours, 0)

            # Calculate utilization using available hours as denominator
            utilization_pct = (actual_billable_hours / available_hours * 100) if available_hours > 0 else 0
            variance = actual_hours - projected_hours

            # Calculate YTD metrics (sum across all months from Jan to selected month)
            # Account for hire_date and term_date when calculating possible hours
            ytd_possible_hours = 0
            ytd_actual_billable_hours = 0
            ytd_pto_hours = 0
            ytd_holiday_hours = 0

            # Get YTD time entries for PTO and Holiday calculation
            ytd_time_entries_df = db.get_time_entries(start_date=ytd_start_date, end_date=end_date)

            for month_num in range(1, selected_month + 1):
                ytd_month_date = datetime(selected_year, month_num, 1)
                ytd_month_key = ytd_month_date.strftime('%B %Y')

                # Get YTD possible hours for this month
                ytd_possible_emp = ytd_metrics['possible'].get(ytd_month_key, {}).get(emp_id_str, {})
                ytd_possible_hours_raw = ytd_possible_emp.get('hours', 0)
                ytd_possible_worked_days = ytd_possible_emp.get('worked_days', 0)

                # Adjust possible hours based on hire/term dates (same logic as monthly calculation)
                if ytd_possible_hours_raw > 0 and ytd_possible_worked_days > 0:
                    # Calculate actual working days based on hire/term dates for this YTD month
                    ytd_actual_working_days = get_working_days_in_range(
                        hire_date, term_date, months_df, selected_year, month_num
                    )

                    # Prorate possible hours if employee worked partial month
                    if ytd_actual_working_days != ytd_possible_worked_days:
                        daily_rate = ytd_possible_hours_raw / ytd_possible_worked_days
                        ytd_adjusted_possible_hours = daily_rate * ytd_actual_working_days
                    else:
                        ytd_adjusted_possible_hours = ytd_possible_hours_raw
                else:
                    ytd_adjusted_possible_hours = ytd_possible_hours_raw

                ytd_possible_hours += ytd_adjusted_possible_hours

                # Get YTD actual billable hours for this month
                ytd_actuals_emp = ytd_metrics['actuals'].get(ytd_month_key, {}).get(emp_id_str, {})
                ytd_actual_billable_hours += ytd_actuals_emp.get('billable_hours', 0)

                # Calculate PTO and Holiday hours for this month from YTD time entries
                if not ytd_time_entries_df.empty:
                    # Filter for this specific month
                    ytd_month_last_day = calendar.monthrange(selected_year, month_num)[1]
                    month_start_str = f"{selected_year}-{month_num:02d}-01"
                    month_end_str = f"{selected_year}-{month_num:02d}-{ytd_month_last_day}"

                    month_entries = ytd_time_entries_df[
                        (ytd_time_entries_df['date'] >= month_start_str) &
                        (ytd_time_entries_df['date'] <= month_end_str) &
                        (ytd_time_entries_df['employee_id'] == emp['id'])
                    ]

                    if not month_entries.empty:
                        # PTO hours for this month
                        month_pto = month_entries[month_entries['project_id'] == 'FRINGE.PTO']['hours'].sum()
                        ytd_pto_hours += month_pto

                        # Holiday hours for this month
                        month_holiday = month_entries[month_entries['project_id'] == 'FRINGE.HOL']['hours'].sum()
                        ytd_holiday_hours += month_holiday

            # Calculate YTD available hours (exclude PTO and Holiday from denominator)
            ytd_available_hours = max(ytd_possible_hours - ytd_pto_hours - ytd_holiday_hours, 0)

            # Calculate YTD utilization percentage using available hours
            ytd_utilization_pct = (ytd_actual_billable_hours / ytd_available_hours * 100) if ytd_available_hours > 0 else 0

            # Determine status
            if utilization_pct > 120:
                status = "🔴 Over"
                status_num = 4
            elif utilization_pct >= 100:
                status = "🟡 High"
                status_num = 3
            elif utilization_pct >= 80:
                status = "🟢 Good"
                status_num = 2
            else:
                status = "🔵 Under"
                status_num = 1

            util_data.append({
                'employee_id': emp['id'],
                'name': emp['name'],
                'role': emp['role'],
                'pay_type': emp.get('pay_type', 'Hourly'),
                'possible_hours': adjusted_possible_hours,
                'projected_hours': projected_hours,
                'actual_hours': actual_hours,
                'actual_billable_hours': actual_billable_hours,
                'pto_hours': pto_hours,
                'holiday_hours': holiday_hours,
                'other_nonbillable_hours': other_nonbillable_hours,
                'utilization_pct': utilization_pct,
                'variance': variance,
                'status': status,
                'ytd_possible_hours': ytd_possible_hours,
                'ytd_actual_billable_hours': ytd_actual_billable_hours,
                'ytd_utilization_pct': ytd_utilization_pct,
                'status_num': status_num,
                'worked_days': actual_worked_days
            })

        util_df = pd.DataFrame(util_data)

        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            pay_type_filter = st.selectbox(
                "Filter by Pay Type",
                ["All", "Hourly", "Salary"],
                index=2,  # Default to "Salary"
                key="util_pay_type_filter"
            )

        with col2:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "🔴 Over", "🟡 High", "🟢 Good", "🔵 Under"],
                key="util_status_filter"
            )

        with col3:
            sort_by = st.selectbox(
                "Sort by",
                ["Name", "Utilization % (High to Low)", "Utilization % (Low to High)", "Variance"],
                key="util_sort_by"
            )

        # Apply filters
        filtered_df = util_df.copy()

        # Only apply filters if DataFrame is not empty
        if not util_df.empty:
            if pay_type_filter != "All":
                filtered_df = filtered_df[filtered_df['pay_type'] == pay_type_filter]

            if status_filter != "All":
                filtered_df = filtered_df[filtered_df['status'] == status_filter]

            # Apply sorting
            if sort_by == "Name":
                filtered_df = filtered_df.sort_values('name')
            elif sort_by == "Utilization % (High to Low)":
                filtered_df = filtered_df.sort_values('utilization_pct', ascending=False)
            elif sort_by == "Utilization % (Low to High)":
                filtered_df = filtered_df.sort_values('utilization_pct', ascending=True)
            elif sort_by == "Variance":
                filtered_df = filtered_df.sort_values('variance', ascending=False)

        st.markdown(f"### Detailed Utilization - {month_key}")

        # Check if there are any billable employees
        if util_df.empty:
            st.info("No billable employees found for the selected period. Make sure employees are marked as billable in the employee settings.")
        else:
            # Summary cards
            st.markdown("#### Utilization Summary")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                over_util = len(util_df[util_df['utilization_pct'] > 120])
                st.metric("Over-Utilized (>120%)", over_util)

            with col2:
                high_util = len(util_df[(util_df['utilization_pct'] >= 100) & (util_df['utilization_pct'] <= 120)])
                st.metric("High Utilization (100-120%)", high_util)

            with col3:
                good_util = len(util_df[(util_df['utilization_pct'] >= 80) & (util_df['utilization_pct'] < 100)])
                st.metric("Well-Utilized (80-100%)", good_util)

            with col4:
                under_util = len(util_df[util_df['utilization_pct'] < 80])
                st.metric("Under-Utilized (<80%)", under_util)

            # Display table
            display_df = filtered_df[[
                'employee_id', 'name', 'possible_hours',
                'actual_hours', 'actual_billable_hours', 'pto_hours', 'holiday_hours', 'other_nonbillable_hours', 'utilization_pct', 'status',
                'ytd_possible_hours', 'ytd_actual_billable_hours', 'ytd_utilization_pct'
            ]].copy()

            display_df = display_df.rename(columns={
                'name': 'Employee',
                'possible_hours': 'Possible Billable Hrs',
                'actual_hours': 'Actual Hrs',
                'actual_billable_hours': 'Actual Billable Hrs',
                'pto_hours': 'PTO Hrs',
                'holiday_hours': 'Holiday Hrs',
                'other_nonbillable_hours': 'Other Non-billable Hrs',
                'utilization_pct': 'Billable Utilization %',
                'status': 'Status',
                'ytd_possible_hours': 'YTD Possible Billable Hrs',
                'ytd_actual_billable_hours': 'YTD Actual Billable Hrs',
                'ytd_utilization_pct': 'YTD Billable Utilization %'
            })

            # JsCode for conditional cell styling on Billable Utilization % column
            utilization_cell_style = JsCode("""
            function(params) {
                if (params.value > 120) {
                    return {'backgroundColor': '#ffcccc'};
                } else if (params.value >= 100) {
                    return {'backgroundColor': '#fff9cc'};
                } else if (params.value >= 80) {
                    return {'backgroundColor': '#ccffcc'};
                } else {
                    return {'backgroundColor': '#cce5ff'};
                }
            }
            """)

            # JsCode for YTD columns - light gray background
            ytd_cell_style = JsCode("""
            function(params) {
                return {'backgroundColor': '#f0f0f0'};
            }
            """)

            # Value formatter for numeric columns (2 decimal places)
            numeric_formatter = JsCode("""
            function(params) {
                if (params.value === null || params.value === undefined) {
                    return '';
                }
                return params.value.toFixed(2);
            }
            """)

            st.markdown("#### Utilization Report")

            col1, col2 = st.columns([1, 3])

            # Show the logic behind the table for reference
            with col1:
                with st.popover("Logic for Utilization Table"):
                    st.markdown("""For each employee in the utilization table:

  | Column                           | Source                                                  | Calculation                                                                          |
  |----------------------------------|---------------------------------------------------------|--------------------------------------------------------------------------------------|
  | Employee                         | employees_df['name']                                    | Direct from employees table                                                          |
  | Possible Billable Hrs            | metrics['possible'][month_key][emp_id]['hours']         | From employees table: (working_days) x (target_allocation - overhead_allocation) x 8 |
  | Actual Hrs                       | metrics['actuals'][month_key][emp_id]['hours']          | From time_entries table: sum of ALL hours logged (billable + non-billable)           |
  | Actual Billable Hrs              | metrics['actuals'][month_key][emp_id]['billable_hours'] | From time_entries table: sum of hours where billable=1                               |
  | PTO Hrs                          | time_entries_df where project_id='FRINGE.PTO'           | Sum of hours from time_entries for PTO project                                       |
  | Holiday Hrs                      | time_entries_df where project_id='FRINGE.HOL'           | Sum of hours from time_entries for Holiday project                                   |
  | Other Non-billable Hrs           | Calculated                                              | (actual_hours - actual_billable_hours) - pto_hours - holiday_hours                   |
  | Billable Utilization %           | Calculated                                              | (actual_billable_hours / (possible_hours - pto_hours - holiday_hours)) x 100         |
  | Status                           | Calculated                                              | Based on Billable Utilization %: >120%, 100-120%, 80-100%, <80%                      |
  | YTD Possible Billable Hrs        | ytd_metrics['possible']                                 | Sum of possible hours from Jan 1 to end of selected month                            |
  | YTD Actual Billable Hrs          | ytd_metrics['actuals']                                  | Sum of actual billable hours from Jan 1 to end of selected month                     |
  | YTD Billable Utilization %       | Calculated                                              | (ytd_actual_billable_hours / (ytd_possible_hours - ytd_pto_hours - ytd_holiday_hours)) x 100 |

**Notes:**
- Possible hours are adjusted only for employees hired or terminated mid-month, not based on which days they logged time entries.
- Actual Billable Hrs shows only time entries marked as billable=1 in the database.
- Billable Utilization % uses available hours (possible - PTO - Holiday) as the denominator to reflect actual time available for billable work.
- Click on any row to view project-level breakdown.
- YTD columns show cumulative data from January 1st through the end of the selected month.
""")

            # Display table with row selection
            with col2:
                st.info("Click on any row to view detailed project breakdown for that employee")

            # Build AgGrid options
            gb = GridOptionsBuilder.from_dataframe(display_df)

            # Configure single-row selection without checkbox
            gb.configure_selection(selection_mode='single', use_checkbox=False)

            # Hide the employee_id column
            gb.configure_column("employee_id", hide=True)

            # Make columns sortable but not filterable
            gb.configure_default_column(sortable=True, filterable=False)

            # Configure numeric columns with formatter
            numeric_columns = [
                'Possible Billable Hrs',
                'Actual Hrs',
                'Actual Billable Hrs',
                'PTO Hrs',
                'Holiday Hrs',
                'Other Non-billable Hrs'
            ]
            for col in numeric_columns:
                gb.configure_column(col, valueFormatter=numeric_formatter)

            # Configure Billable Utilization % column with conditional styling and formatter
            gb.configure_column(
                'Billable Utilization %',
                cellStyle=utilization_cell_style,
                valueFormatter=numeric_formatter
            )

            # Configure YTD columns with gray background and formatter
            ytd_columns = [
                'YTD Possible Billable Hrs',
                'YTD Actual Billable Hrs',
                'YTD Billable Utilization %'
            ]
            for col in ytd_columns:
                gb.configure_column(
                    col,
                    cellStyle=ytd_cell_style,
                    valueFormatter=numeric_formatter
                )

            grid_options = gb.build()

            # Display AgGrid
            grid_response = AgGrid(
                display_df,
                gridOptions=grid_options,
                height=500,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                allow_unsafe_jscode=True,  # Required for JsCode cell styling
                theme='streamlit',
                key=f"employee_utilization_aggrid_v{st.session_state.grid_selection_version}"
            )

            # Handle row selection - open dialog to show project breakdown
            selected_rows = grid_response['selected_rows']
            if selected_rows is not None and len(selected_rows) > 0:
                selected_row = selected_rows.iloc[0] if hasattr(selected_rows, 'iloc') else selected_rows[0]
                emp_id = selected_row['employee_id']
                emp_name = selected_row['Employee']

                # Open modal dialog with employee project breakdown
                show_project_breakdown(emp_id, emp_name, month_key, time_entries_df)

            # Summary totals
            st.markdown("##### Summary Totals")
            summary_cols = st.columns(7)
            with summary_cols[0]:
                st.metric("Employees", len(filtered_df))
            with summary_cols[1]:
                st.metric("Total Possible Hrs", f"{filtered_df['possible_hours'].sum():.0f}")
            with summary_cols[2]:
                st.metric("Total Actual Hrs", f"{filtered_df['actual_hours'].sum():.0f}")
            with summary_cols[3]:
                st.metric("Total Actual Billable Hrs", f"{filtered_df['actual_billable_hours'].sum():.0f}")
            with summary_cols[4]:
                st.metric("Total PTO Hrs", f"{filtered_df['pto_hours'].sum():.0f}")
            with summary_cols[5]:
                st.metric("Total Holiday Hrs", f"{filtered_df['holiday_hours'].sum():.0f}")
            with summary_cols[6]:
                avg_util = filtered_df['utilization_pct'].mean()
                st.metric("Avg Utilization", f"{avg_util:.1f}%")

            # CSV Export (without employee_id column)
            csv_df = display_df.drop(columns=['employee_id'])
            csv = csv_df.to_csv(index=False)
            st.download_button(
                label="Download Utilization Report",
                data=csv,
                file_name=f"utilization_{selected_year}_{selected_month:02d}.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error loading utilization data: {str(e)}")
        logger.error(f"Error in utilization tab: {str(e)}", exc_info=True)


def _get_billable_employees(db, period_start, period_end):
    """Get billable employees active during the given period.

    Returns a DataFrame of employees where billable=1 and who have not been
    terminated before the period start date.
    """
    employees_df = db.get_employees()
    if employees_df.empty:
        return employees_df

    # Filter to billable employees only
    billable_df = employees_df[employees_df['billable'] == 1].copy()

    # Exclude employees terminated before the period start
    period_start_date = pd.to_datetime(period_start).date()
    period_end_date = pd.to_datetime(period_end).date()

    def is_active_in_period(row):
        # Check termination date
        if pd.notna(row.get('term_date')):
            term_date = pd.to_datetime(row['term_date']).date()
            if term_date < period_start_date:
                return False
        # Check hire date
        if pd.notna(row.get('hire_date')):
            hire_date = pd.to_datetime(row['hire_date']).date()
            if hire_date > period_end_date:
                return False
        return True

    billable_df = billable_df[billable_df.apply(is_active_in_period, axis=1)]
    return billable_df


def _get_period_date_range(time_frame, year):
    """Calculate start and end dates for the selected time frame.

    Returns (start_date, end_date) as strings in YYYY-MM-DD format.
    """
    quarter_ranges = {
        "Quarter 1": (f"{year}-01-01", f"{year}-03-31"),
        "Quarter 2": (f"{year}-04-01", f"{year}-06-30"),
        "Quarter 3": (f"{year}-07-01", f"{year}-09-30"),
        "Quarter 4": (f"{year}-10-01", f"{year}-12-31"),
    }

    if time_frame == "Current Month":
        now = datetime.now()
        if year == now.year:
            month = now.month
        else:
            month = 1  # Default to January for non-current years
        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
    else:
        start_date, end_date = quarter_ranges[time_frame]

    return start_date, end_date


def _get_months_in_range(start_date, end_date):
    """Return a list of month keys (e.g. 'January 2025') for all months in the date range."""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current.strftime('%B %Y'))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def _render_utilization_summary_tab(db, processor, year_options, current_year, employee_id=None):
    """Render the Utilization Summary tab with category cards.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        year_options: List of years for the year selector
        current_year: Current year for default selection
        employee_id: Optional employee ID to filter results to a single employee
    """
    col1, col2 = st.columns([1, 1])

    with col1:
        selected_year = st.selectbox(
            "Year",
            options=year_options,
            index=year_options.index(current_year),
            key="util_summary_year"
        )

    with col2:
        time_frame = st.selectbox(
            "Time Frame",
            ["Current Month", "Quarter 1", "Quarter 2", "Quarter 3", "Quarter 4"],
            key="util_summary_timeframe"
        )

    start_date, end_date = _get_period_date_range(time_frame, selected_year)
    months_in_range = _get_months_in_range(start_date, end_date)

    try:
        with st.spinner("Loading utilization summary..."):
            metrics = processor.get_performance_metrics(
                start_date=start_date,
                end_date=end_date
            )

        billable_df = _get_billable_employees(db, start_date, end_date)

        # Filter to specific employee if employee_id is provided
        if employee_id is not None:
            billable_df = billable_df[billable_df['id'] == employee_id]
            if billable_df.empty:
                st.error(f"Employee {employee_id} not found or is not billable")
                return

        if billable_df.empty:
            st.info("No billable employees found for the selected period.")
            return

        # Calculate utilization for each employee across the period
        employee_utilizations = []

        for _, emp in billable_df.iterrows():
            emp_id_str = str(emp['id'])
            total_billable_hours = 0
            total_possible_hours = 0

            for month_key in months_in_range:
                # Get actual billable hours for this month
                actuals_emp = metrics['actuals'].get(month_key, {}).get(emp_id_str, {})
                total_billable_hours += actuals_emp.get('billable_hours', 0)

                # Get possible hours for this month
                possible_emp = metrics['possible'].get(month_key, {}).get(emp_id_str, {})
                total_possible_hours += possible_emp.get('hours', 0)

            utilization_pct = (total_billable_hours / total_possible_hours * 100) if total_possible_hours > 0 else 0

            employee_utilizations.append({
                'name': emp['name'],
                'utilization_pct': utilization_pct,
                'billable_hours': total_billable_hours,
                'possible_hours': total_possible_hours,
            })

        # Categorize employees
        categories = [
            {
                'label': '100%+',
                'icon': '\U0001f7e2',
                'bg_color': '#e8f5e9',
                'border_color': '#28a745',
                'filter': lambda pct: pct >= 100,
            },
            {
                'label': '90% - 99%',
                'icon': '\U0001f7e1',
                'bg_color': '#fff8e1',
                'border_color': '#ffc107',
                'filter': lambda pct: 90 <= pct < 100,
            },
            {
                'label': '75% - 89%',
                'icon': '\U0001f7e0',
                'bg_color': '#fff3e0',
                'border_color': '#fd7e14',
                'filter': lambda pct: 75 <= pct < 90,
            },
            {
                'label': '< 75%',
                'icon': '\U0001f534',
                'bg_color': '#ffebee',
                'border_color': '#dc3545',
                'filter': lambda pct: pct < 75,
            },
        ]

        if time_frame == "Current Month":
            # Derive the month name from the resolved start_date to stay consistent
            period_month = pd.to_datetime(start_date).strftime('%B')
            period_label = f"{period_month} {selected_year}"
        else:
            period_label = time_frame
        st.markdown(f"### Utilization Summary - {period_label}")

        cols = st.columns(4)

        for idx, cat in enumerate(categories):
            matching = [e for e in employee_utilizations if cat['filter'](e['utilization_pct'])]
            count = len(matching)

            # Build names list with utilization percentage
            if matching:
                names_lines = [
                    f"{html.escape(e['name'])} ({e['utilization_pct']:.0f}%)"
                    for e in sorted(matching, key=lambda x: x['utilization_pct'], reverse=True)
                ]
                names_html = "<br>".join(names_lines)
            else:
                names_html = "<em>None</em>"

            with cols[idx]:
                st.markdown(f'''
<div style="background-color: {cat['bg_color']}; padding: 15px; border-radius: 10px; border-left: 5px solid {cat['border_color']}; margin-bottom: 10px;">
    <div style="display: flex; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 24px; margin-right: 8px;">{cat['icon']}</span>
        <span style="font-size: 18px; font-weight: bold;">{cat['label']}</span>
    </div>
    <div style="font-size: 28px; font-weight: bold; margin-bottom: 5px;">{count} Employees</div>
    <div style="font-size: 13px; color: #555;">{names_html}</div>
</div>
''', unsafe_allow_html=True)

        # Overall summary metrics
        st.markdown("---")
        total_billable = sum(e['billable_hours'] for e in employee_utilizations)
        total_possible = sum(e['possible_hours'] for e in employee_utilizations)
        overall_util = (total_billable / total_possible * 100) if total_possible > 0 else 0

        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("Total Billable Employees", len(employee_utilizations))
        with summary_cols[1]:
            st.metric("Total Billable Hours", f"{total_billable:,.0f}")
        with summary_cols[2]:
            st.metric("Total Possible Hours", f"{total_possible:,.0f}")
        with summary_cols[3]:
            st.metric("Overall Utilization", f"{overall_util:.1f}%")

    except Exception as e:
        st.error(f"Error loading utilization summary: {str(e)}")
        logger.error(f"Error in utilization summary tab: {str(e)}", exc_info=True)


def _render_utilization_timeline_tab(db, processor, year_options, current_year, employee_id=None):
    """Render the Utilization Timeline tab with planned vs actual charts.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        year_options: List of years for the year selector
        current_year: Current year for default selection
        employee_id: Optional employee ID to filter results to a single employee
    """
    col1, col2 = st.columns([1, 1])

    with col1:
        selected_year = st.selectbox(
            "Year",
            options=year_options,
            index=year_options.index(current_year),
            key="util_timeline_year"
        )

    with col2:
        time_frame = st.selectbox(
            "Time Frame",
            ["Current Month", "Quarter 1", "Quarter 2", "Quarter 3", "Quarter 4"],
            key="util_timeline_timeframe"
        )

    start_date, end_date = _get_period_date_range(time_frame, selected_year)
    months_in_range = _get_months_in_range(start_date, end_date)

    try:
        with st.spinner("Loading timeline data..."):
            metrics = processor.get_performance_metrics(
                start_date=start_date,
                end_date=end_date
            )

        billable_df = _get_billable_employees(db, start_date, end_date)

        # Filter to specific employee if employee_id is provided
        if employee_id is not None:
            billable_df = billable_df[billable_df['id'] == employee_id]
            if billable_df.empty:
                st.error(f"Employee {employee_id} not found or is not billable")
                return

        if billable_df.empty:
            st.info("No billable employees found for the selected period.")
            return

        # ---------------------------------------------------------------
        # Section 1: Utilization Timeline - All Employees (or single employee if filtered)
        # ---------------------------------------------------------------
        if employee_id is not None:
            emp_name = billable_df['name'].iloc[0]
            st.markdown(f"### Utilization Timeline: {emp_name}")
        else:
            st.markdown("### Utilization Timeline: All")

        # Aggregate planned and actual hours per month across all employees
        planned_hours_list = []
        actual_hours_list = []

        for month_key in months_in_range:
            month_planned = 0
            month_actual = 0

            projected_month = metrics['projected'].get(month_key, {})
            actuals_month = metrics['actuals'].get(month_key, {})

            for _, emp in billable_df.iterrows():
                emp_id_str = str(emp['id'])
                # Planned (projected) hours
                proj_emp = projected_month.get(emp_id_str, {})
                month_planned += proj_emp.get('hours', 0)

                # Actual billable hours
                act_emp = actuals_month.get(emp_id_str, {})
                month_actual += act_emp.get('billable_hours', 0)

            planned_hours_list.append(month_planned)
            actual_hours_list.append(month_actual)

        if any(h > 0 for h in planned_hours_list) or any(h > 0 for h in actual_hours_list):
            fig_all = go.Figure()
            fig_all.add_trace(go.Bar(
                name='Planned Hours',
                x=months_in_range,
                y=planned_hours_list,
                marker_color='#28a745'
            ))
            fig_all.add_trace(go.Bar(
                name='Actual Billable Hours',
                x=months_in_range,
                y=actual_hours_list,
                marker_color='#ffc107'
            ))
            fig_all.update_layout(
                barmode='group',
                title="Planned vs Actual Billable Hours - All Employees",
                xaxis_title="Month",
                yaxis_title="Hours",
                height=400
            )
            st.plotly_chart(fig_all, use_container_width=True)
        else:
            st.info("No planned or actual hours data available for the selected period.")

        # ---------------------------------------------------------------
        # Section 2: Utilization Timeline - Individual Employee
        # ---------------------------------------------------------------
        # Skip this section if already filtered to a specific employee
        if employee_id is not None:
            # Already showing single employee data in section 1
            return

        st.markdown("### Utilization Timeline: Individual Employee")

        sorted_billable_df = billable_df.sort_values('name')

        if sorted_billable_df.empty:
            st.info("No billable employees available for individual timeline.")
            return

        selected_emp_id = st.selectbox(
            "Select Employee",
            options=sorted_billable_df['id'].tolist(),
            format_func=lambda eid: billable_df[billable_df['id'] == eid]['name'].iloc[0],
            key="util_timeline_employee"
        )

        selected_emp_name = billable_df[billable_df['id'] == selected_emp_id]['name'].iloc[0]

        # Get individual employee metrics using constraint
        with st.spinner(f"Loading timeline for {selected_emp_name}..."):
            emp_metrics = processor.get_performance_metrics(
                start_date=start_date,
                end_date=end_date,
                constraint={'employee_id': selected_emp_id}
            )

        # When using employee constraint, data is keyed by project_id.
        # We need to sum across all projects for each month.
        emp_planned_list = []
        emp_actual_list = []

        for month_key in months_in_range:
            # Sum projected hours across all projects for this month
            projected_month = emp_metrics['projected'].get(month_key, {})
            month_planned = sum(
                proj_data.get('hours', 0)
                for proj_data in projected_month.values()
            )
            emp_planned_list.append(month_planned)

            # Sum actual billable hours across all projects for this month
            actuals_month = emp_metrics['actuals'].get(month_key, {})
            month_actual = sum(
                act_data.get('billable_hours', 0)
                for act_data in actuals_month.values()
            )
            emp_actual_list.append(month_actual)

        if any(h > 0 for h in emp_planned_list) or any(h > 0 for h in emp_actual_list):
            fig_emp = go.Figure()
            fig_emp.add_trace(go.Bar(
                name='Planned Hours',
                x=months_in_range,
                y=emp_planned_list,
                marker_color='#28a745'
            ))
            fig_emp.add_trace(go.Bar(
                name='Actual Billable Hours',
                x=months_in_range,
                y=emp_actual_list,
                marker_color='#ffc107'
            ))
            fig_emp.update_layout(
                barmode='group',
                title=f"Planned vs Actual Billable Hours - {selected_emp_name}",
                xaxis_title="Month",
                yaxis_title="Hours",
                height=400
            )
            st.plotly_chart(fig_emp, use_container_width=True)
        else:
            st.info(f"No planned or actual hours data available for {selected_emp_name} in the selected period.")

    except Exception as e:
        st.error(f"Error loading utilization timeline: {str(e)}")
        logger.error(f"Error in utilization timeline tab: {str(e)}", exc_info=True)
