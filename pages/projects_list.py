"""
Project List tab - displays filterable table of all projects with summary metrics.
"""
import streamlit as st
import pandas as pd
from utils.project_helpers import safe_budget_percentage, safe_currency_display


def render_project_list_tab(db, processor):
    """Render the Project List tab with filtering and sorting."""
    # Load projects
    projects_df = db.get_projects()

    if not projects_df.empty:
        st.markdown("#### Project Overview")

        # Summary metrics
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            active_count = len(projects_df[projects_df['status'] == 'Active'])
            st.metric("Active", active_count)
        with col2:
            future_count = len(projects_df[projects_df['status'] == 'Future'])
            st.metric("Future", future_count, help="Projects not yet started")
        with col3:
            completed_count = len(projects_df[projects_df['status'] == 'Completed'])
            st.metric("Completed", completed_count)
        with col4:
            on_hold_count = len(projects_df[projects_df['status'] == 'On Hold'])
            st.metric("On Hold", on_hold_count)
        with col5:
            # Calculate over budget count with NULL handling
            over_budget_count = 0
            for _, proj in projects_df.iterrows():
                pct, _ = safe_budget_percentage(proj['budget_used'], proj['contract_value'])
                if pct is not None and pct > 100:
                    over_budget_count += 1

            st.metric("Over Budget", over_budget_count, delta_color="inverse")
        with col6:
            total_budget = projects_df['contract_value'].sum()
            st.metric("Total Budget", f"${total_budget/1e6:.1f}M")

        st.markdown("---")

        # Filters and controls
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            status_options = ['Active', 'Future', 'Completed', 'On Hold', 'Cancelled']
            selected_statuses = st.multiselect(
                "Filter by Status",
                options=status_options,
                default=['Active'],
                help="Select one or more statuses to display"
            )

        with col2:
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

        with col3:
            # Add data quality indicator
            projects_with_budget = len(projects_df[pd.notna(projects_df['contract_value'])])
            st.metric(
                "With Budget Data",
                f"{projects_with_budget}/{len(projects_df)}",
                help="Number of projects with contract_value data"
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
            # Calculate percentage, keeping NaN for missing data
            filtered_df['budget_pct'] = filtered_df.apply(
                lambda row: safe_budget_percentage(row['budget_used'], row['contract_value'])[0],
                axis=1
            )
            # Sort with NaN last
            filtered_df = filtered_df.sort_values('budget_pct', ascending=False, na_position='last')
        elif sort_by == "Budget % Used (Low to High)":
            # Calculate percentage, keeping NaN for missing data
            filtered_df['budget_pct'] = filtered_df.apply(
                lambda row: safe_budget_percentage(row['budget_used'], row['contract_value'])[0],
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

        # Show count
        st.caption(f"Showing {len(filtered_df)} of {len(projects_df)} projects")

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

            # Budget - use safe helpers
            display_df['Budget Allocated'] = filtered_df['contract_value'].apply(safe_currency_display)
            display_df['Budget Used'] = filtered_df['budget_used'].apply(safe_currency_display)

            # Budget percentage - use safe calculation
            budget_pcts = filtered_df.apply(
                lambda row: safe_budget_percentage(row['budget_used'], row['contract_value'])[1],
                axis=1
            )
            display_df['Budget %'] = budget_pcts

            # Display with configuration
            st.dataframe(
                display_df,
                use_container_width=True,
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
