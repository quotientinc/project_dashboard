"""
Employee Utilization Analysis tab - detailed monthly and YTD utilization tracking.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import calendar


def render_utilization_tab(db, processor):
    """Render the Employee Utilization Analysis tab with monthly and YTD metrics."""
    st.markdown("#### Employee Utilization Analysis")

    # Date range selection
    col1, col2 = st.columns([1, 1])

    with col1:
        # Year selector
        current_year = datetime.now().year
        year_options = list(range(current_year - 2, current_year + 2))
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
        month_key = f"{month_names[selected_month - 1]} {selected_year}"

        # Calculate first and last day of report month for filtering
        first_day_of_month = datetime(selected_year, selected_month, 1).date()
        last_day_of_month = datetime(selected_year, selected_month, last_day).date()

        # Get months data for working days calculation
        months_df = db.get_months()

        # Get time entries for PTO calculation
        time_entries_df = db.get_time_entries(start_date=start_date, end_date=end_date)

        # Calculate PTO hours by employee for this month
        pto_by_employee = {}
        if not time_entries_df.empty:
            pto_entries = time_entries_df[time_entries_df['project_id'] == 'FRINGE.PTO']
            if not pto_entries.empty:
                pto_by_employee = pto_entries.groupby('employee_id')['hours'].sum().to_dict()

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

        # Dialog function for showing employee project breakdown
        @st.dialog("Employee Project Breakdown", width="large")
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
                        use_container_width=True,
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
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No time entries found for {emp_name} in {month_key}")

        # Get employees dataframe for utilization calculations
        employees_df = db.get_employees()

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

            # Calculate other non-billable hours (excluding PTO)
            total_nonbillable_hours = actual_hours - actual_billable_hours
            other_nonbillable_hours = total_nonbillable_hours - pto_hours

            utilization_pct = (actual_billable_hours / adjusted_possible_hours * 100) if adjusted_possible_hours > 0 else 0
            variance = actual_hours - projected_hours

            # Calculate YTD metrics (sum across all months from Jan to selected month)
            # Account for hire_date and term_date when calculating possible hours
            ytd_possible_hours = 0
            ytd_actual_billable_hours = 0

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

            # Calculate YTD utilization percentage
            ytd_utilization_pct = (ytd_actual_billable_hours / ytd_possible_hours * 100) if ytd_possible_hours > 0 else 0

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

        st.markdown(f"### 📋 Detailed Utilization - {month_key}")

        # Check if there are any billable employees
        if util_df.empty:
            st.info("No billable employees found for the selected period. Make sure employees are marked as billable in the employee settings.")
        else:
            # Summary cards
            st.markdown("#### Utilization Summary")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                over_util = len(util_df[util_df['utilization_pct'] > 120])
                st.metric("🔴 Over-Utilized (>120%)", over_util)

            with col2:
                high_util = len(util_df[(util_df['utilization_pct'] >= 100) & (util_df['utilization_pct'] <= 120)])
                st.metric("🟡 High Utilization (100-120%)", high_util)

            with col3:
                good_util = len(util_df[(util_df['utilization_pct'] >= 80) & (util_df['utilization_pct'] < 100)])
                st.metric("🟢 Well-Utilized (80-100%)", good_util)

            with col4:
                under_util = len(util_df[util_df['utilization_pct'] < 80])
                st.metric("🔵 Under-Utilized (<80%)", under_util)

            # Display table
            display_df = filtered_df[[
                'employee_id', 'name', 'possible_hours',
                'actual_hours', 'actual_billable_hours', 'pto_hours', 'other_nonbillable_hours', 'utilization_pct', 'status',
                'ytd_possible_hours', 'ytd_actual_billable_hours', 'ytd_utilization_pct'
            ]].copy()

            display_df = display_df.rename(columns={
                'name': 'Employee',
                'possible_hours': 'Possible Billable Hrs',
                'actual_hours': 'Actual Hrs',
                'actual_billable_hours': 'Actual Billable Hrs',
                'pto_hours': 'PTO Hrs',
                'other_nonbillable_hours': 'Other Non-billable Hrs',
                'utilization_pct': 'Billable Utilization %',
                'status': 'Status',
                'ytd_possible_hours': '📅 YTD Possible Billable Hrs',
                'ytd_actual_billable_hours': '📅 YTD Actual Billable Hrs',
                'ytd_utilization_pct': '📅 YTD Billable Utilization %'
            })

            # Conditional formatting
            def color_utilization_status(val):
                if val > 120:
                    return 'background-color: #ffcccc'  # Red
                elif val >= 100:
                    return 'background-color: #fff9cc'  # Yellow
                elif val >= 80:
                    return 'background-color: #ccffcc'  # Green
                else:
                    return 'background-color: #cce5ff'  # Blue

            def ytd_background(val):
                return 'background-color: #f0f0f0'  # Light gray for YTD columns

            # Apply styling and formatting to display_df
            styled_df = display_df.style.applymap(color_utilization_status, subset=['Billable Utilization %'])
            styled_df = styled_df.applymap(ytd_background, subset=[
                '📅 YTD Possible Billable Hrs',
                '📅 YTD Actual Billable Hrs',
                '📅 YTD Billable Utilization %'
            ])

            # Format numeric columns to 2 decimal places
            styled_df = styled_df.format({
                'Possible Billable Hrs': '{:.2f}',
                'Actual Hrs': '{:.2f}',
                'Actual Billable Hrs': '{:.2f}',
                'PTO Hrs': '{:.2f}',
                'Other Non-billable Hrs': '{:.2f}',
                'Billable Utilization %': '{:.2f}',
                '📅 YTD Possible Billable Hrs': '{:.2f}',
                '📅 YTD Actual Billable Hrs': '{:.2f}',
                '📅 YTD Billable Utilization %': '{:.2f}'
            })

            st.markdown("#### Utilization Report")

            col1, col2 = st.columns([1, 3])

            # Show the logic behind the table for reference
            with col1:
                with st.popover("💡Logic for Utilization Table"):
                    st.markdown("""For each employee in the utilization table:

  | Column                           | Source                                                  | Calculation                                                                          |
  |----------------------------------|---------------------------------------------------------|--------------------------------------------------------------------------------------|
  | Employee                         | employees_df['name']                                    | Direct from employees table                                                          |
  | Possible Billable Hrs            | metrics['possible'][month_key][emp_id]['hours']         | From employees table: (working_days) × (target_allocation - overhead_allocation) × 8 |
  | Actual Hrs                       | metrics['actuals'][month_key][emp_id]['hours']          | From time_entries table: sum of ALL hours logged (billable + non-billable)           |
  | Actual Billable Hrs              | metrics['actuals'][month_key][emp_id]['billable_hours'] | From time_entries table: sum of hours where billable=1                               |
  | PTO Hrs                          | time_entries_df where project_id='FRINGE.PTO'           | Sum of hours from time_entries for PTO project                                       |
  | Other Non-billable Hrs           | Calculated                                              | (actual_hours - actual_billable_hours) - pto_hours                                   |
  | Billable Utilization %           | Calculated                                              | (actual_billable_hours / adjusted_possible_hours) × 100                              |
  | Status                           | Calculated                                              | Based on Billable Utilization %: 🔴 >120%, 🟡 100-120%, 🟢 80-100%, 🔵 <80%         |
  | 📅 YTD Possible Billable Hrs    | ytd_metrics['possible']                                 | Sum of possible hours from Jan 1 to end of selected month                            |
  | 📅 YTD Actual Billable Hrs      | ytd_metrics['actuals']                                  | Sum of actual billable hours from Jan 1 to end of selected month                     |
  | 📅 YTD Billable Utilization %   | Calculated                                              | (ytd_actual_billable_hours / ytd_possible_hours) × 100                               |

**Notes:**
- Possible hours are adjusted only for employees hired or terminated mid-month, not based on which days they logged time entries.
- Actual Billable Hrs shows only time entries marked as billable=1 in the database.
- Click on any row to view project-level breakdown.
- YTD columns show cumulative data from January 1st through the end of the selected month.
""")

            # Display table with row selection
            with col2:
                st.info("👆 Click on any row to view detailed project breakdown for that employee")

            selection = st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                height=500,
                on_select="rerun",
                selection_mode="single-row",
                key="employee_utilization_table",
                column_config={
                    "employee_id": None  # Hide employee_id column
                }
            )

            # Handle row selection - open dialog to show project breakdown
            if selection and selection.selection.rows:
                selected_idx = selection.selection.rows[0]
                selected_row = display_df.iloc[selected_idx]
                emp_id = selected_row['employee_id']
                emp_name = selected_row['Employee']

                # Open modal dialog with employee project breakdown
                show_project_breakdown(emp_id, emp_name, month_key, time_entries_df)

            # Summary totals
            st.markdown("##### Summary Totals")
            summary_cols = st.columns(6)
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
                avg_util = filtered_df['utilization_pct'].mean()
                st.metric("Avg Utilization", f"{avg_util:.1f}%")

            # CSV Export (without employee_id column)
            csv_df = display_df.drop(columns=['employee_id'])
            csv = csv_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Utilization Report",
                data=csv,
                file_name=f"utilization_{selected_year}_{selected_month:02d}.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error loading utilization data: {str(e)}")
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.error(f"Error in utilization tab: {str(e)}", exc_info=True)
