"""
Employee Allocation Planning tab - identifies employees projected to be over/under-allocated.

Focuses on: Allocated Hours (from allocations) vs Possible Hours (capacity)
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import calendar
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, ColumnsAutoSizeMode


def render_allocation_tab(db, processor, employee_id=None):
    """Render the Employee Allocation Planning tab showing allocated vs possible hours.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        employee_id: Optional employee ID to filter results to a single employee
    """
    st.markdown("#### Employee Allocation Planning")
    st.caption("Identify employees who are projected to be over/under-allocated")

    if "alloc_grid_selection_version" not in st.session_state:
        st.session_state.alloc_grid_selection_version = 0

    # Date range selection
    col1, col2 = st.columns([1, 1])

    with col1:
        # Year selector
        current_year = datetime.now().year
        year_options = list(range(current_year - 1, current_year + 3))
        selected_year = st.selectbox(
            "Year",
            options=year_options,
            index=year_options.index(current_year),
            key="alloc_year_filter"
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
            key="alloc_month_filter"
        )
        selected_month = month_names.index(selected_month_name) + 1

    # Build date range for get_performance_metrics
    start_date = f"{selected_year}-{selected_month:02d}-01"
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    end_date = f"{selected_year}-{selected_month:02d}-{last_day}"

    # Get performance metrics
    try:
        with st.spinner("Loading allocation data..."):
            # Get monthly metrics for selected month
            metrics = processor.get_performance_metrics(
                start_date=start_date,
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

        # Extract month key
        month_key = f"{month_names[selected_month - 1]} {selected_year}"

        # Calculate first and last day of report month for filtering
        first_day_of_month = datetime(selected_year, selected_month, 1).date()
        last_day_of_month = datetime(selected_year, selected_month, last_day).date()

        # Get months data for working days calculation
        months_df = db.get_months()

        # Get allocations for project breakdown
        allocations_df = db.get_allocations()
        if not allocations_df.empty:
            allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
            # Filter to selected month
            allocations_df = allocations_df[
                allocations_df['allocation_date'].dt.strftime('%Y-%m') == f"{selected_year}-{selected_month:02d}"
            ]

        # Helper function to get project allocation breakdown for an employee
        def get_employee_allocation_breakdown(employee_id, allocations_df, months_df, year, month):
            """Generate project-level allocation breakdown for a specific employee"""
            # Filter allocations for this employee
            emp_allocs = allocations_df[allocations_df['employee_id'] == employee_id]

            if emp_allocs.empty:
                return pd.DataFrame(columns=['Project', 'Allocated FTE', 'Allocated Hours', '% of Total'])

            # Get working days for the month
            month_info = months_df[(months_df['year'] == year) & (months_df['month'] == month)]
            working_days = int(month_info['working_days'].iloc[0]) if not month_info.empty else 21

            # Subtract holidays from working days to get available days
            holidays = month_info['holidays'].iloc[0] if (not month_info.empty and 'holidays' in month_info.columns) else 0
            holidays = holidays if pd.notna(holidays) else 0
            available_days = max(working_days - int(holidays), 0)

            # Group by project
            breakdown = []
            for _, alloc in emp_allocs.iterrows():
                allocated_fte = alloc.get('allocated_fte', 0)
                allocated_hours = allocated_fte * available_days * 8  # FTE × available days × 8 hrs/day

                breakdown.append({
                    'Project': alloc.get('project_name', 'Unknown'),
                    'Allocated FTE': allocated_fte,
                    'Allocated Hours': allocated_hours
                })

            breakdown_df = pd.DataFrame(breakdown)

            if not breakdown_df.empty:
                # Calculate percentage
                total_hours = breakdown_df['Allocated Hours'].sum()
                breakdown_df['% of Total'] = (breakdown_df['Allocated Hours'] / total_hours * 100).round(1)

                # Sort by allocated hours descending
                breakdown_df = breakdown_df.sort_values('Allocated Hours', ascending=False)

            return breakdown_df

        # Dialog function for showing employee allocation breakdown
        def clear_alloc_grid_selection():
            """Callback to clear grid selection when dialog is dismissed"""
            st.session_state.alloc_grid_selection_version += 1

        @st.dialog("Employee Allocation Breakdown", width="large", on_dismiss=clear_alloc_grid_selection)
        def show_allocation_breakdown(emp_id, emp_name, emp_fte, month_key, possible_hours, allocated_hours, allocation_pct):
            """Display project-level allocation breakdown for a selected employee in a modal dialog"""
            st.markdown(f"### {emp_name}")
            st.caption(f"{month_key} • Target FTE: {emp_fte}")

            # Metrics row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Possible Hours", f"{possible_hours:.1f}")
            with col2:
                st.metric("Allocated Hours", f"{allocated_hours:.1f}")
            with col3:
                # Color code the allocation %
                if allocation_pct > 120:
                    delta_color = "inverse"
                elif allocation_pct < 80:
                    delta_color = "inverse"
                else:
                    delta_color = "normal"
                st.metric("Allocation %", f"{allocation_pct:.1f}%", delta_color=delta_color)
            with col4:
                variance = allocated_hours - possible_hours
                st.metric("Variance", f"{variance:+.1f} hrs")

            st.markdown("---")

            # Get allocation breakdown
            breakdown_df = get_employee_allocation_breakdown(emp_id, allocations_df, months_df, selected_year, selected_month)

            if not breakdown_df.empty:
                col1, col2 = st.columns([1, 1])

                with col1:
                    # Display breakdown table
                    st.markdown("#### Allocation by Project")

                    # Format the breakdown table for display
                    breakdown_display = breakdown_df.copy()
                    breakdown_display['Allocated FTE'] = breakdown_display['Allocated FTE'].round(2)
                    breakdown_display['Allocated Hours'] = breakdown_display['Allocated Hours'].round(1)

                    st.dataframe(
                        breakdown_display,
                        width='stretch',
                        hide_index=True,
                        height=400
                    )

                with col2:
                    # Create pie chart
                    st.markdown("#### Distribution")

                    fig = px.pie(
                        breakdown_df,
                        values='Allocated Hours',
                        names='Project',
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    fig.update_layout(height=400, showlegend=True)
                    st.plotly_chart(fig, width='stretch')
            else:
                st.info(f"No allocations found for {emp_name} in {month_key}")

            st.markdown("---")
            if st.button("View Employee Details →", key="alloc_view_emp_btn"):
                st.session_state.selected_employee_id = emp_id
                st.session_state.selected_employee_name = emp_name
                st.switch_page("pages/employee_view.py")

        # Get employees dataframe for allocation calculations
        employees_df = db.get_employees()

        # Filter to specific employee if employee_id is provided
        if employee_id is not None:
            employees_df = employees_df[employees_df['id'] == employee_id]
            if employees_df.empty:
                st.error(f"Employee {employee_id} not found")
                return

        # Build allocation DataFrame
        alloc_data = []

        for _, emp in employees_df.iterrows():
            emp_id_str = str(emp['id'])

            # Skip non-billable employees
            if emp.get('billable', 0) != 1:
                continue

            # Determine employee's active date range
            if pd.notna(emp.get('hire_date')):
                hire_date = pd.to_datetime(emp['hire_date']).date()
                if hire_date > last_day_of_month:
                    continue  # Not hired yet
            else:
                hire_date = first_day_of_month

            if pd.notna(emp.get('term_date')):
                term_date = pd.to_datetime(emp['term_date']).date()
                if term_date < first_day_of_month:
                    continue  # Already terminated
            else:
                term_date = last_day_of_month

            # Get possible hours for this employee
            possible_month_data = metrics['possible'].get(month_key, {})
            emp_possible = possible_month_data.get(emp_id_str, {})

            # Adjust possible hours for hire/term dates if needed
            possible_hours = emp_possible.get('hours', 0)
            possible_worked_days = emp_possible.get('worked_days', 21)

            if possible_hours > 0:
                # Get actual working days for this employee
                working_days = get_working_days_in_range(hire_date, term_date, months_df, selected_year, selected_month)

                if working_days != possible_worked_days and possible_worked_days > 0:
                    # Adjust for partial month
                    daily_rate = possible_hours / possible_worked_days
                    possible_hours = daily_rate * working_days

            # Get allocated hours (projected data from allocations)
            projected_month_data = metrics['projected'].get(month_key, {})
            emp_projected = projected_month_data.get(emp_id_str, {})
            allocated_hours = emp_projected.get('hours', 0)

            # Calculate allocation percentage
            if possible_hours > 0:
                allocation_pct = (allocated_hours / possible_hours) * 100
            else:
                allocation_pct = 0

            # Determine status
            if allocation_pct > 120:
                status = "🔴 Over-Allocated"
                status_sort = 1
            elif allocation_pct > 100:
                status = "🟡 At Capacity"
                status_sort = 2
            elif allocation_pct >= 80:
                status = "🟢 Healthy"
                status_sort = 3
            else:
                status = "🔵 Under-Allocated"
                status_sort = 4

            # Calculate variance
            variance = allocated_hours - possible_hours

            alloc_data.append({
                'employee_id': emp['id'],
                'Employee': emp['name'],
                'Target FTE': emp.get('target_fte', 1.0),
                'Possible Hours': possible_hours,
                'Allocated Hours': allocated_hours,
                'Allocation %': allocation_pct,
                'Variance': variance,
                'Status': status,
                'status_sort': status_sort
            })

        alloc_df = pd.DataFrame(alloc_data)

        # Summary Metrics
        if not alloc_df.empty:
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Employees", len(alloc_df))

            with col2:
                over_allocated = len(alloc_df[alloc_df['Allocation %'] > 100])
                st.metric("Over-Allocated", over_allocated, delta_color="inverse")

            with col3:
                under_allocated = len(alloc_df[alloc_df['Allocation %'] < 80])
                st.metric("Under-Allocated", under_allocated, delta_color="inverse")

            with col4:
                avg_allocation = alloc_df['Allocation %'].mean()
                st.metric("Avg Allocation %", f"{avg_allocation:.1f}%")

        st.markdown("---")

        # Filters
        col1, col2 = st.columns([2, 2])

        with col1:
            status_filter = st.multiselect(
                "Filter by Status",
                options=["🔴 Over-Allocated", "🟡 At Capacity", "🟢 Healthy", "🔵 Under-Allocated"],
                default=["🔴 Over-Allocated", "🟡 At Capacity", "🟢 Healthy", "🔵 Under-Allocated"],
                key="alloc_status_filter"
            )

        with col2:
            search_term = st.text_input(
                "🔍 Search employees",
                placeholder="Search by name...",
                label_visibility="collapsed",
                key="alloc_search"
            )

        # Apply filters
        filtered_df = alloc_df.copy()

        if status_filter:
            filtered_df = filtered_df[filtered_df['Status'].isin(status_filter)]

        if search_term:
            filtered_df = filtered_df[filtered_df['Employee'].str.contains(search_term, case=False, na=False)]

        # Sort by allocation % descending (over-allocated first)
        filtered_df = filtered_df.sort_values('Allocation %', ascending=False)

        # Display table
        if not filtered_df.empty:
            st.markdown(f"#### Allocation Overview ({len(filtered_df)} employees)")
            st.info("Click on any row to view detailed allocation breakdown for that employee")

            # Create display dataframe (include employee_id for selection handling, hidden in grid)
            display_df = filtered_df[[
                'employee_id', 'Employee', 'Target FTE', 'Possible Hours', 'Allocated Hours', 'Allocation %', 'Variance', 'Status'
            ]].copy()

            # Round numbers (keep Variance as numeric -- AgGrid handles formatting)
            display_df['Target FTE'] = display_df['Target FTE'].round(2)
            display_df['Possible Hours'] = display_df['Possible Hours'].round(1)
            display_df['Allocated Hours'] = display_df['Allocated Hours'].round(1)
            display_df['Allocation %'] = display_df['Allocation %'].round(1)
            display_df['Variance'] = display_df['Variance'].round(1)

            # JsCode formatters
            numeric_formatter = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return '-';
    return params.value.toFixed(1);
}
""")

            variance_formatter = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return '-';
    var sign = params.value >= 0 ? '+' : '';
    return sign + params.value.toFixed(1);
}
""")

            pct_formatter = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return '-';
    return params.value.toFixed(1) + '%';
}
""")

            allocation_cell_style = JsCode("""
function(params) {
    if (params.value > 120) {
        return {'backgroundColor': '#ffcccc'};
    } else if (params.value > 100) {
        return {'backgroundColor': '#fff9cc'};
    } else if (params.value >= 80) {
        return {'backgroundColor': '#ccffcc'};
    } else {
        return {'backgroundColor': '#cce5ff'};
    }
}
""")

            # Build AgGrid options
            gb = GridOptionsBuilder.from_dataframe(display_df)
            gb.configure_selection(selection_mode='single', use_checkbox=False)
            gb.configure_default_column(sortable=True, filterable=False)
            gb.configure_column("employee_id", hide=True)
            gb.configure_column('Target FTE', valueFormatter=numeric_formatter)
            gb.configure_column('Possible Hours', valueFormatter=numeric_formatter)
            gb.configure_column('Allocated Hours', valueFormatter=numeric_formatter)
            gb.configure_column('Allocation %', cellStyle=allocation_cell_style, valueFormatter=pct_formatter)
            gb.configure_column('Variance', valueFormatter=variance_formatter)
            grid_options = gb.build()

            # Display AgGrid
            grid_response = AgGrid(
                display_df,
                gridOptions=grid_options,
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW,
                height=500,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                allow_unsafe_jscode=True,
                theme='streamlit',
                key=f"alloc_aggrid_v{st.session_state.alloc_grid_selection_version}"
            )

            # Handle row selection for modal dialog
            selected_rows = grid_response['selected_rows']
            if selected_rows is not None and len(selected_rows) > 0:
                selected_row = selected_rows.iloc[0] if hasattr(selected_rows, 'iloc') else selected_rows[0]

                show_allocation_breakdown(
                    emp_id=selected_row['employee_id'],
                    emp_name=selected_row['Employee'],
                    emp_fte=selected_row['Target FTE'],
                    month_key=month_key,
                    possible_hours=selected_row['Possible Hours'],
                    allocated_hours=selected_row['Allocated Hours'],
                    allocation_pct=selected_row['Allocation %']
                )

            # Allocation Chart
            st.markdown("---")
            st.markdown("#### Allocation % by Employee")

            # Assign colors based on allocation %
            colors = filtered_df['Allocation %'].apply(
                lambda x: '#ff4444' if x > 120 else (
                    '#ffaa00' if x > 100 else (
                        '#2E7D32' if x >= 80 else '#4488ff'
                    )
                )
            )

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=filtered_df['Employee'],
                y=filtered_df['Allocation %'],
                marker_color=colors,
                text=filtered_df['Allocation %'].apply(lambda x: f"{x:.1f}%"),
                textposition='outside'
            ))

            # Add 100% capacity line
            fig.add_shape(
                type="line",
                x0=-0.5,
                x1=len(filtered_df)-0.5,
                y0=100,
                y1=100,
                line=dict(color="black", dash="dash", width=2),
            )

            # Add 80% target line
            fig.add_shape(
                type="line",
                x0=-0.5,
                x1=len(filtered_df)-0.5,
                y0=80,
                y1=80,
                line=dict(color="gray", dash="dot", width=1),
            )

            fig.update_layout(
                height=400,
                xaxis_tickangle=-45,
                yaxis_title="Allocation %",
                yaxis=dict(range=[0, max(150, filtered_df['Allocation %'].max() + 10)]),
                showlegend=False
            )
            st.plotly_chart(fig, width='stretch')

            # Export
            st.markdown("---")
            csv = display_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Allocation Data",
                data=csv,
                file_name=f"allocation_planning_{selected_year}_{selected_month:02d}.csv",
                mime="text/csv"
            )

        else:
            st.info("No employees match the selected filters")

    except Exception as e:
        st.error(f"Error loading allocation data: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
