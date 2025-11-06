import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 👥 Employee Management")

tab1, tab2, tab3 = st.tabs(["Utilization", "Employee List", "Employee Detail (Edit)"])

with tab1:
    from datetime import datetime
    import calendar

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
        logger.error(f"Error in utilization tab: {str(e)}", exc_info=True)

with tab2:
    st.markdown("#### Employee List")

    employees_df = db.get_employees()

    if not employees_df.empty:
        # Display options
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("#### All Employees")
        with col2:
            view_mode = st.selectbox("View", ["Table", "Cards"], label_visibility="collapsed")

        if view_mode == "Table":
            # Table view - no filters, just display all data
            # The dataframe itself has built-in sorting and filtering
            display_df = employees_df.copy()

            st.dataframe(display_df, width='stretch', hide_index=True)

        else:
            # Card view with role filter only
            role_filter = st.selectbox("Filter by Role", ["All"] + sorted(employees_df['role'].dropna().unique().tolist()), key="card_role_filter")

            # Apply filter
            filtered_df = employees_df.copy()
            if role_filter != "All":
                filtered_df = filtered_df[filtered_df['role'] == role_filter]

            # Sort by name
            filtered_df = filtered_df.sort_values('name')

            # Display cards
            cols = st.columns(3)
            for idx, (_, emp) in enumerate(filtered_df.iterrows()):
                with cols[idx % 3]:
                    with st.container():
                        st.markdown(f"### 👤 {emp['name']}")
                        st.write(f"**Role:** {emp['role'] if pd.notna(emp['role']) else 'N/A'}")
                        st.write(f"**Hire Date:** {emp['hire_date'] if pd.notna(emp['hire_date']) else 'N/A'}")

                        if pd.notna(emp.get('skills')) and emp['skills']:
                            st.write(f"**Skills:** {emp['skills']}")

                        # Show current allocations with FTE
                        allocations = db.get_allocations(employee_id=emp['id'])
                        if not allocations.empty:
                            total_fte = allocations['allocated_fte'].sum() if 'allocated_fte' in allocations.columns else 0
                            st.write(f"**Total FTE:** {total_fte:.2f}")

                            with st.expander("Current Projects"):
                                for _, alloc in allocations.iterrows():
                                    fte = alloc.get('allocated_fte', 0)
                                    st.write(f"• {alloc['project_name']} ({fte * 100:.0f}%)")

                        st.markdown("---")
    else:
        st.info("No employees found")

with tab3:
    st.markdown("#### Employee Detail (Edit)")

    employees_df = db.get_employees()

    if not employees_df.empty:
        # Select employee to edit
        selected_employee_name = st.selectbox(
            "Select Employee",
            options=employees_df['name'].tolist(),
            key="edit_employee_select"
        )

        if selected_employee_name:
            employee = employees_df[employees_df['name'] == selected_employee_name].iloc[0]
            employee_id = employee['id']

            st.markdown(f"### {employee['name']}")

            # Create subtabs for Project Allocations and Employee Data
            detail_tab1, detail_tab2 = st.tabs(["Project Allocations", "Edit Employee Data"])

            # Subtab 1: Project Allocation Management
            with detail_tab1:
                st.markdown("#### Project Allocation Management")

                # Get employee target FTE (accounting for overhead)
                target_fte = employee.get('target_allocation', 1.0) - employee.get('overhead_allocation', 0.0)

                # Current allocations
                allocations_df = db.get_allocations(employee_id=employee_id)

                if not allocations_df.empty:
                    # Group allocations by month
                    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
                    allocations_df['month_key'] = allocations_df['allocation_date'].dt.strftime('%B %Y')
                    allocations_df['sort_key'] = allocations_df['allocation_date'].dt.to_period('M')

                    # Group by month
                    grouped = allocations_df.groupby('month_key')

                    # Sort months chronologically
                    month_order = allocations_df.sort_values('sort_key')['month_key'].unique()

                    st.markdown("##### Current Allocations by Month")

                    for month in month_order:
                        month_allocs = allocations_df[allocations_df['month_key'] == month]

                        # Calculate total FTE for this month
                        total_fte = month_allocs['allocated_fte'].sum()

                        # Calculate allocation percentage
                        allocation_pct = (total_fte / target_fte * 100) if target_fte > 0 else 0

                        # Determine color and emoji based on allocation
                        if allocation_pct > 120:
                            emoji = "🔴"
                            bg_color = "#ffcccc"
                        elif allocation_pct >= 100:
                            emoji = "🟡"
                            bg_color = "#fff9cc"
                        elif allocation_pct >= 80:
                            emoji = "🟢"
                            bg_color = "#ccffcc"
                        else:
                            emoji = "🔵"
                            bg_color = "#cce5ff"

                        # Display month header with color coding
                        st.markdown(
                            f"<div style='background-color: {bg_color}; padding: 10px; border-radius: 5px; margin: 10px 0;'>"
                            f"<b>📅 {month} ({total_fte:.1f} FTE of {target_fte:.1f} Target FTE) {emoji}</b>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        # Display allocations for this month
                        for _, alloc in month_allocs.iterrows():
                            col1, col2, col3 = st.columns([4, 2, 1])

                            with col1:
                                st.write(f"  • **{alloc['project_name']}**")

                            with col2:
                                fte = alloc.get('allocated_fte', 0)
                                st.write(f"{fte:.2f} FTE")

                            with col3:
                                if st.button("Remove", key=f"remove_emp_alloc_{alloc['id']}"):
                                    try:
                                        db.delete_allocation(alloc['id'])
                                        st.success(f"Removed from {alloc['project_name']}")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error removing allocation: {str(e)}")

                        st.markdown("")  # Add spacing between months
                else:
                    st.info("Not allocated to any projects")

                # Add new allocation
                st.markdown("##### Add to Project")

                projects_df = db.get_projects()

                # Filter out projects already allocated
                if not allocations_df.empty:
                    allocated_proj_ids = allocations_df['project_id'].tolist()
                    available_projects = projects_df[~projects_df['id'].isin(allocated_proj_ids)]
                else:
                    available_projects = projects_df

                if not available_projects.empty:
                    with st.form(key=f"add_alloc_employee_{employee_id}"):
                        col1, col2 = st.columns(2)

                        with col1:
                            project_name = st.selectbox(
                                "Select Project",
                                options=available_projects['name'].tolist(),
                                key=f"new_proj_select_{employee_id}"
                            )
                            allocated_fte = st.number_input("Allocation (FTE)", min_value=0.0, max_value=1.0, step=0.05, value=0.5, key=f"emp_alloc_{employee_id}", help="0.5 = 50% of full-time, 1.0 = 100% full-time")

                        with col2:
                            role_in_project = st.text_input("Role in Project", key=f"emp_role_{employee_id}")

                        selected_proj = available_projects[available_projects['name'] == project_name].iloc[0]

                        col1, col2 = st.columns(2)
                        with col1:
                            alloc_start = st.date_input("Start Date", value=pd.to_datetime(selected_proj['start_date']), key=f"emp_alloc_start_{employee_id}")
                        with col2:
                            alloc_end = st.date_input("End Date", value=pd.to_datetime(selected_proj['end_date']), key=f"emp_alloc_end_{employee_id}")

                        if st.form_submit_button("Add to Project"):
                            try:
                                # Get employee's cost_rate to use as bill_rate
                                bill_rate = employee.get('cost_rate', None)

                                allocation_data = {
                                    'project_id': selected_proj['id'],
                                    'employee_id': employee_id,
                                    'allocated_fte': allocated_fte,
                                    'start_date': alloc_start.strftime('%Y-%m-%d'),
                                    'end_date': alloc_end.strftime('%Y-%m-%d'),
                                    'role': role_in_project,
                                    'bill_rate': bill_rate
                                }

                                db.add_allocation(allocation_data)
                                st.success(f"Added {employee['name']} to {project_name}!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error adding to project: {str(e)}")
                else:
                    st.info("Employee is already allocated to all available projects")

            # Subtab 2: Edit Employee Data
            with detail_tab2:
                st.markdown("#### Edit Employee Data")

                with st.form("edit_employee_form"):
                    # === Basic Information ===
                    st.markdown("**Basic Information**")
                    col1, col2 = st.columns(2)

                    with col1:
                        name = st.text_input("Name*", value=employee['name'])
                        role = st.text_input("Role*", value=employee['role'])

                    with col2:
                        hire_date = st.date_input(
                            "Hire Date",
                            value=pd.to_datetime(employee['hire_date']) if pd.notna(employee.get('hire_date')) else None
                        )
                        term_date = st.date_input(
                            "Term Date (optional)",
                            value=pd.to_datetime(employee['term_date']) if pd.notna(employee.get('term_date')) else None,
                            help="Leave empty if employee is active"
                        )

                    st.markdown("---")

                    # === Compensation ===
                    st.markdown("**Compensation**")

                    # Pay Type selection
                    pay_type_options = ["Hourly", "Salary"]
                    current_pay_type = employee.get('pay_type', 'Hourly')
                    if current_pay_type not in pay_type_options:
                        current_pay_type = "Hourly"

                    pay_type = st.radio(
                        "Pay Type*",
                        options=pay_type_options,
                        index=pay_type_options.index(current_pay_type),
                        horizontal=True
                    )

                    col1, col2 = st.columns(2)

                    # Conditional fields based on pay type
                    if pay_type == "Hourly":
                        with col1:
                            cost_rate = st.number_input(
                                "Cost Rate ($/hour)*",
                                min_value=0.0,
                                value=float(employee.get('cost_rate', 0.0)) if pd.notna(employee.get('cost_rate')) else 0.0,
                                step=1.0,
                                format="%.2f",
                                help="Hourly rate for this employee"
                            )
                        with col2:
                            st.info("Annual salary field is hidden for Hourly employees")

                        # For form submission
                        annual_salary = None
                        calculated_rate_display = None

                    else:  # Salary
                        with col1:
                            annual_salary = st.number_input(
                                "Annual Salary ($)*",
                                min_value=0.0,
                                value=float(employee.get('annual_salary', 0.0)) if pd.notna(employee.get('annual_salary')) else 0.0,
                                step=1000.0,
                                format="%.2f",
                                help="Annual salary for this employee"
                            )

                        # Auto-calculate cost rate from annual salary
                        if annual_salary > 0:
                            calculated_cost_rate = annual_salary / 2080
                            with col2:
                                st.info(f"**Calculated Hourly Rate:** ${calculated_cost_rate:.2f}/hour  \n(Based on 2080 hours/year)")
                            cost_rate = calculated_cost_rate
                        else:
                            cost_rate = 0.0
                            with col2:
                                st.warning("Enter annual salary to calculate hourly rate")

                    st.markdown("---")

                    # === Benefits ===
                    st.markdown("**Benefits**")
                    col1, col2 = st.columns(2)

                    with col1:
                        pto_accrual = st.number_input(
                            "PTO Accrual (hours/year)",
                            min_value=0.0,
                            value=float(employee.get('pto_accrual', 120.0)) if pd.notna(employee.get('pto_accrual')) else 120.0,
                            step=8.0,
                            format="%.1f",
                            help="Annual PTO hours"
                        )

                    with col2:
                        holidays = st.number_input(
                            "Holidays (hours/year)",
                            min_value=0.0,
                            value=float(employee.get('holidays', 88.0 if pay_type == "Salary" else 0.0)) if pd.notna(employee.get('holidays')) else (88.0 if pay_type == "Salary" else 0.0),
                            step=8.0,
                            format="%.1f",
                            help="Typically 88 for Salary, 0 for Hourly"
                        )

                    st.markdown("---")

                    # === Allocation Settings ===
                    st.markdown("**Allocation Settings**")
                    col1, col2 = st.columns(2)

                    with col1:
                        billable = st.checkbox(
                            "Billable Employee",
                            value=bool(employee.get('billable', 0)),
                            help="Check if this employee's time is billable to clients",
                            key=f"billable_{employee_id}"
                        )

                        overhead_allocation = st.number_input(
                            "Overhead Allocation",
                            min_value=0.0,
                            max_value=1.0,
                            value=float(employee.get('overhead_allocation', 0.0)) if pd.notna(employee.get('overhead_allocation')) else 0.0,
                            step=0.05,
                            format="%.2f",
                            help="Percentage of time allocated to overhead (0-1)",
                            key=f"overhead_{employee_id}"
                        )

                    with col2:
                        # Determine default target allocation based on pay type and billable status
                        current_target = float(employee.get('target_allocation', 0.3)) if pd.notna(employee.get('target_allocation')) else 0.3

                        target_allocation = st.number_input(
                            "Target Allocation",
                            min_value=0.0,
                            max_value=1.0,
                            value=current_target,
                            step=0.05,
                            format="%.2f",
                            help="Target FTE allocation for this employee (0-1). Billable Salary: 1.0, Billable Hourly: 0.3",
                            key=f"target_{employee_id}"
                        )

                    # Apply defaults for billable employees
                    if billable:
                        overhead_allocation = 0.0
                        # Show info about defaults
                        if pay_type == "Salary":
                            st.info("💡 Billable Salary employees: overhead set to 0, target typically 1.0")
                        else:  # Hourly
                            st.info("💡 Billable Hourly employees: overhead set to 0, target typically 0.3")

                    st.markdown("---")

                    # === Skills ===
                    st.markdown("**Skills**")

                    # Skills options
                    skills_options = [
                        "jr. developer",
                        "sr. developer",
                        "sr. consultant",
                        "technical SME",
                        "project lead",
                        "project manager",
                        "scheduler"
                    ]

                    # Parse current skills from comma-separated string
                    current_skills_str = employee.get('skills', '')
                    if pd.notna(current_skills_str) and current_skills_str:
                        current_skills = [s.strip() for s in current_skills_str.split(',')]
                    else:
                        current_skills = []

                    selected_skills = st.multiselect(
                        "Skills (select multiple)",
                        options=skills_options,
                        default=[s for s in current_skills if s in skills_options],
                        help="Select one or more skills for this employee"
                    )

                    # Convert selected skills back to comma-separated string
                    skills_str = ', '.join(selected_skills) if selected_skills else None

                    st.markdown("---")

                    # Submit button
                    update_button = st.form_submit_button("Update Employee", type="primary")

                    if update_button:
                        # Validation
                        if not name or not role:
                            st.error("Please fill in all required fields marked with *")
                        elif pay_type == "Hourly" and cost_rate <= 0:
                            st.error("Cost Rate must be greater than 0 for Hourly employees")
                        elif pay_type == "Salary" and annual_salary <= 0:
                            st.error("Annual Salary must be greater than 0 for Salary employees")
                        elif term_date and hire_date and term_date < hire_date:
                            st.error("Term Date cannot be before Hire Date")
                        else:
                            # Prepare updates
                            updates = {
                                'name': name,
                                'role': role,
                                'hire_date': hire_date.strftime('%Y-%m-%d') if hire_date else None,
                                'term_date': term_date.strftime('%Y-%m-%d') if term_date else None,
                                'pay_type': pay_type,
                                'cost_rate': cost_rate,
                                'annual_salary': annual_salary if pay_type == "Salary" else None,
                                'pto_accrual': pto_accrual,
                                'holidays': holidays,
                                'skills': skills_str,
                                'billable': 1 if billable else 0,
                                'overhead_allocation': overhead_allocation,
                                'target_allocation': target_allocation
                            }

                            try:
                                db.update_employee(employee_id, updates)
                                st.success(f"Employee '{name}' updated successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error updating employee: {str(e)}")

    else:
        st.info("No employees available to edit")
