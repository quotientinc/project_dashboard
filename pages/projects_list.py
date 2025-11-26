"""
Project List tab - displays filterable table of all projects with summary metrics.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from utils.project_helpers import safe_budget_percentage, safe_currency_display


def render_project_list_tab(db, processor):
    """Render the Project List tab with filtering and sorting."""
    # Load projects
    projects_df = db.get_projects()

    if not projects_df.empty:
        # Filters and controls
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
            # Date range filter
            current_year = datetime.now().year
            date_filter_options = [
                f"Active in {current_year}",
                "All Projects",
                "Custom Date Range"
            ]
            date_filter = st.selectbox(
                "Date Range",
                options=date_filter_options,
                index=0,
                help="Filter projects by activity period"
            )

        with col3:
            sort_by = st.selectbox(
                "Sort by",
                options=[
                    "Name (A-Z)",
                    "Start Date (Newest)",
                    "Start Date (Oldest)",
                    "Budget % Used (High to Low)",
                    "Budget % Used (Low to High)",
                    "Client (A-Z)"
                ]
            )

        with col4:
            # Add data quality indicator for billable projects
            if 'is_billable' in projects_df.columns:
                billable_projects = projects_df[projects_df['is_billable'] != 0]
            else:
                # If is_billable column doesn't exist, assume all projects are billable
                billable_projects = projects_df
            billable_with_budget = len(billable_projects[
                pd.notna(billable_projects['quoted_value']) & pd.notna(billable_projects['awarded_value'])
            ])
            st.metric(
                "Billable w/ Budget",
                f"{billable_with_budget}/{len(billable_projects)}",
                help="Billable projects with quoted_value and awarded_value data"
            )

        # Custom date range inputs (only show if Custom Date Range selected)
        if date_filter == "Custom Date Range":
            date_col1, date_col2 = st.columns(2)
            with date_col1:
                custom_start = st.date_input(
                    "Filter Start Date",
                    value=datetime(current_year, 1, 1),
                    help="Show projects active on or after this date"
                )
            with date_col2:
                custom_end = st.date_input(
                    "Filter End Date",
                    value=datetime(current_year, 12, 31),
                    help="Show projects active on or before this date"
                )

        # Optional search
        search_term = st.text_input(
            "🔍 Search projects",
            placeholder="Search by name, client, or project manager...",
            label_visibility="collapsed"
        )

        st.markdown("---")

        # Apply filters
        filtered_df = projects_df.copy()

        # Status filter
        if selected_statuses:
            filtered_df = filtered_df[filtered_df['status'].isin(selected_statuses)]
        else:
            filtered_df = pd.DataFrame()

        # Date range filter
        if date_filter == f"Active in {current_year}":
            # Show projects that overlap with current year
            # start_date <= 2025-12-31 AND end_date >= 2025-01-01
            # Projects with missing dates are excluded
            year_start = pd.Timestamp(datetime(current_year, 1, 1))
            year_end = pd.Timestamp(datetime(current_year, 12, 31))

            filtered_df = filtered_df[
                pd.notna(filtered_df['start_date']) &
                pd.notna(filtered_df['end_date']) &
                (pd.to_datetime(filtered_df['start_date']) <= year_end) &
                (pd.to_datetime(filtered_df['end_date']) >= year_start)
            ]
        elif date_filter == "Custom Date Range":
            # Show projects that overlap with custom date range
            # Projects with missing dates are excluded
            range_start = pd.Timestamp(custom_start)
            range_end = pd.Timestamp(custom_end)

            filtered_df = filtered_df[
                pd.notna(filtered_df['start_date']) &
                pd.notna(filtered_df['end_date']) &
                (pd.to_datetime(filtered_df['start_date']) <= range_end) &
                (pd.to_datetime(filtered_df['end_date']) >= range_start)
            ]
        # If "All Projects", don't apply any date filter

        # Search filter
        if search_term:
            search_mask = (
                filtered_df['name'].str.contains(search_term, case=False, na=False) |
                filtered_df['client'].str.contains(search_term, case=False, na=False) |
                filtered_df['project_manager'].str.contains(search_term, case=False, na=False)
            )
            filtered_df = filtered_df[search_mask]

        # Apply sorting
        if sort_by == "Name (A-Z)":
            filtered_df = filtered_df.sort_values('name')
        elif sort_by == "Budget % Used (High to Low)":
            # Calculate percentage, keeping NaN for missing data - use quoted_value
            filtered_df['budget_pct'] = filtered_df.apply(
                lambda row: safe_budget_percentage(row['budget_used'], row['quoted_value'])[0],
                axis=1
            )
            # Sort with NaN last
            filtered_df = filtered_df.sort_values('budget_pct', ascending=False, na_position='last')
        elif sort_by == "Budget % Used (Low to High)":
            # Calculate percentage, keeping NaN for missing data - use quoted_value
            filtered_df['budget_pct'] = filtered_df.apply(
                lambda row: safe_budget_percentage(row['budget_used'], row['quoted_value'])[0],
                axis=1
            )
            # Sort with NaN last
            filtered_df = filtered_df.sort_values('budget_pct', ascending=True, na_position='last')
        elif sort_by == "Start Date (Newest)":
            filtered_df = filtered_df.sort_values('start_date', ascending=False, na_position='last')
        elif sort_by == "Start Date (Oldest)":
            filtered_df = filtered_df.sort_values('start_date', ascending=True, na_position='last')
        elif sort_by == "Client (A-Z)":
            filtered_df = filtered_df.sort_values('client')

        # Project Overview - showing metrics for filtered projects
        st.markdown("#### Project Overview")
        st.caption(f"Showing {len(filtered_df)} of {len(projects_df)} projects")

        # Summary metrics based on filtered data
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
            active_count = len(filtered_df[filtered_df['status'] == 'Active'])
            st.metric("Active", active_count)
        with col2:
            future_count = len(filtered_df[filtered_df['status'] == 'Future'])
            st.metric("Future", future_count, help="Projects not yet started")
        with col3:
            completed_count = len(filtered_df[filtered_df['status'] == 'Completed'])
            st.metric("Completed", completed_count)
        with col4:
            on_hold_count = len(filtered_df[filtered_df['status'] == 'On Hold'])
            st.metric("On Hold", on_hold_count)
        with col5:
            # Calculate over budget count with NULL handling
            over_budget_count = 0
            for _, proj in filtered_df.iterrows():
                pct, _ = safe_budget_percentage(proj['budget_used'], proj['quoted_value'])
                if pct is not None and pct > 100:
                    over_budget_count += 1

            st.metric("Over Budget", over_budget_count, delta_color="inverse")
        with col6:
            # Calculate missing budget count for billable projects only
            if 'is_billable' in filtered_df.columns:
                billable_projects = filtered_df[filtered_df['is_billable'] != 0]
            else:
                # If is_billable column doesn't exist, assume all projects are billable
                billable_projects = filtered_df
            missing_budget_count = len(billable_projects[
                pd.isna(billable_projects['quoted_value']) | pd.isna(billable_projects['awarded_value'])
            ])
            st.metric(
                "Missing Budget",
                missing_budget_count,
                help="Billable projects without quoted or awarded value data",
                delta_color="inverse"
            )
        with col7:
            total_quoted = filtered_df['quoted_value'].sum()
            st.metric("Total Quoted", f"${total_quoted/1e6:.1f}M")

        st.markdown("---")

        # Display projects in enhanced compact table
        if not filtered_df.empty:
            # Prepare display DataFrame
            display_df = pd.DataFrame()

            # Project basics
            display_df['Project'] = filtered_df['name']
            display_df['Client'] = filtered_df['client']
            display_df['PM'] = filtered_df['project_manager']
            display_df['Status'] = filtered_df['status']

            # Dates
            display_df['Start'] = filtered_df['start_date']
            display_df['End'] = filtered_df['end_date']

            # Calculate duration
            display_df['Duration'] = filtered_df.apply(
                lambda row: f"{(pd.to_datetime(row['end_date']) - pd.to_datetime(row['start_date'])).days} days"
                if pd.notna(row['start_date']) and pd.notna(row['end_date'])
                else '-',
                axis=1
            )

            # Budget - show both quoted and awarded values
            display_df['Quoted Value'] = filtered_df['quoted_value'].apply(safe_currency_display)
            display_df['Awarded Value'] = filtered_df['awarded_value'].apply(safe_currency_display)
            display_df['Budget Used'] = filtered_df['budget_used'].apply(safe_currency_display)

            # Budget percentage - use safe calculation with quoted_value
            budget_pcts = filtered_df.apply(
                lambda row: safe_budget_percentage(row['budget_used'], row['quoted_value'])[1],
                axis=1
            )
            display_df['Budget %'] = budget_pcts

            # Display with configuration
            st.dataframe(
                display_df,
                width='stretch',
                hide_index=True,
                height=600,
                column_config={
                    "Status": st.column_config.TextColumn(
                        "Status",
                        help="Project status",
                    ),
                    "Budget %": st.column_config.TextColumn(
                        "Budget %",
                        help="Percentage of allocated budget used. N/A = missing budget data",
                    ),
                }
            )

        else:
            # Empty state with helpful message
            if not selected_statuses:
                st.info("👆 Select at least one project status above to view projects")
            elif search_term:
                st.info(f"No projects found matching '{search_term}' with status: {', '.join(selected_statuses)}")
            else:
                st.info(f"No projects found with status: {', '.join(selected_statuses)}")

    else:
        st.info("No projects found. Import project data to get started.")
