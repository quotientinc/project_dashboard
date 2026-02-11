"""
Project Review Meeting page - funding-focused project review showing all projects
with funding health at a glance, with drill-down to individual project details.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

from utils.funding_helpers import (
    calculate_avg_monthly_invoice,
    calculate_funding_runway,
    get_funding_health_status,
    calculate_current_month_potential,
)
from utils.project_helpers import safe_currency_display, safe_budget_percentage
from utils.logger import get_logger

logger = get_logger(__name__)


def _compute_time_period_dates(period_choice, custom_start, custom_end):
    """
    Return (start_date, end_date) as date objects based on the selected time period.

    Args:
        period_choice: One of 'YTD', 'Current Month', 'Quarter', 'Custom'.
        custom_start: User-supplied start date (used when period_choice is 'Custom').
        custom_end: User-supplied end date (used when period_choice is 'Custom').

    Returns:
        Tuple of (start_date, end_date) as Python date objects.
    """
    today = date.today()
    if period_choice == "YTD":
        return date(today.year, 1, 1), today
    elif period_choice == "Current Month":
        return date(today.year, today.month, 1), today
    elif period_choice == "Quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, quarter_start_month, 1), today
    else:
        return custom_start, custom_end


def _build_project_table(projects_df, db, processor):
    """
    Build the summary DataFrame used to populate the main AgGrid table.

    For each billable project, computes funding metrics including remaining funding,
    average monthly invoice, months of runway, and health status.

    Args:
        projects_df: DataFrame of billable projects from db.get_projects().
        db: DatabaseManager instance.
        processor: DataProcessor class reference.

    Returns:
        DataFrame with columns suitable for display in AgGrid.
    """
    rows = []

    for _, proj in projects_df.iterrows():
        project_id = proj["id"]
        project_name = proj.get("name", "")
        client = proj.get("client", "")
        pm = proj.get("project_manager", "")
        status = proj.get("status", "")
        quoted_value = proj.get("quoted_value", 0) or 0
        awarded_value = proj.get("awarded_value", 0) or 0
        budget_used = proj.get("budget_used", 0) or 0

        remaining_funding = awarded_value - budget_used
        funding_pct_val, funding_pct_display = safe_budget_percentage(
            remaining_funding, awarded_value
        )
        # If percentage could not be computed, default to 0 for sorting/health
        if funding_pct_val is None or pd.isna(funding_pct_val):
            funding_pct_val = 0.0

        avg_monthly = calculate_avg_monthly_invoice(project_id, db, processor)
        months_left = calculate_funding_runway(remaining_funding, avg_monthly)
        health_label, health_color, health_icon = get_funding_health_status(funding_pct_val)

        rows.append(
            {
                "Project Name": project_name,
                "Project Code": str(project_id),
                "Client": client,
                "PM": pm,
                "Status": status,
                "Quoted Value": quoted_value,
                "Awarded Value": awarded_value,
                "Budget Used": budget_used,
                "Funding Left ($)": remaining_funding,
                "Funding Left (%)": round(funding_pct_val, 1),
                "Health Status": f"{health_icon} {health_label}",
                "Avg Monthly Invoice": avg_monthly,
                "Months Left": round(months_left, 1) if months_left != float("inf") else None,
                # Hidden helper columns for sorting / dialog
                "_health_color": health_color,
                "_funding_pct_raw": funding_pct_val,
            }
        )

    return pd.DataFrame(rows)


def _apply_filters(table_df, name_filter, client_filter, funding_filter, sort_by):
    """
    Apply user-selected filters and sort order to the project table DataFrame.

    Args:
        table_df: The full project table DataFrame.
        name_filter: List of selected project names (empty means all).
        client_filter: List of selected clients (empty means all).
        funding_filter: String representing funding threshold filter.
        sort_by: String representing the desired sort column/direction.

    Returns:
        Filtered and sorted DataFrame.
    """
    df = table_df.copy()

    if name_filter:
        df = df[df["Project Name"].isin(name_filter)]

    if client_filter:
        df = df[df["Client"].isin(client_filter)]

    if funding_filter == ">90% Left":
        df = df[df["_funding_pct_raw"] > 90]
    elif funding_filter == ">75% Left":
        df = df[df["_funding_pct_raw"] > 75]
    elif funding_filter == ">50% Left":
        df = df[df["_funding_pct_raw"] > 50]
    elif funding_filter == "Critical Only":
        df = df[df["_funding_pct_raw"] < 10]

    if sort_by == "Project Name":
        df = df.sort_values("Project Name")
    elif sort_by == "Client":
        df = df.sort_values("Client")
    elif sort_by == "Funding Left (Low->High)":
        df = df.sort_values("_funding_pct_raw", ascending=True)
    elif sort_by == "Funding Left (High->Low)":
        df = df.sort_values("_funding_pct_raw", ascending=False)

    return df


def _build_funding_timeline_chart(project_id, project_name, awarded_value, db, processor):
    """
    Build a Plotly bar chart showing monthly invoice amounts over the project lifetime
    with a horizontal dashed line for the awarded value.

    Args:
        project_id: The project identifier (TEXT).
        project_name: Display name of the project.
        awarded_value: Total awarded value used for the reference line.
        db: DatabaseManager instance.
        processor: DataProcessor class reference.

    Returns:
        Plotly Figure object (bar chart with reference line).
    """
    # Use a wide window: 24 months back from today
    end_dt = datetime.now()
    start_dt = end_dt - relativedelta(months=24)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    try:
        metrics = processor.get_performance_metrics(
            start_date=start_str,
            end_date=end_str,
            constraint={"project_id": str(project_id)},
        )
    except Exception as e:
        logger.error(f"Failed to get performance metrics for timeline chart: {e}")
        return None

    actuals = metrics.get("actuals", {})
    if not actuals:
        return None

    # Build monthly revenue series, sorted chronologically
    monthly_data = []
    for month_name, employees in actuals.items():
        month_revenue = sum(emp.get("revenue", 0) for emp in employees.values())
        # Parse month_name like "January 2025" for sorting
        try:
            month_dt = datetime.strptime(month_name, "%B %Y")
        except ValueError:
            continue
        monthly_data.append({"month": month_dt, "label": month_name, "revenue": month_revenue})

    if not monthly_data:
        return None

    monthly_data.sort(key=lambda x: x["month"])
    months = [d["label"] for d in monthly_data]
    revenues = [d["revenue"] for d in monthly_data]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=months,
            y=revenues,
            name="Monthly Invoice",
            marker_color="#1f77b4",
            text=[f"${v:,.0f}" for v in revenues],
            textposition="outside",
        )
    )

    if awarded_value and awarded_value > 0:
        fig.add_hline(
            y=awarded_value,
            line_dash="dash",
            line_color="green",
            annotation_text=f"Awarded: ${awarded_value:,.0f}",
            annotation_position="top left",
        )

    fig.update_layout(
        title=f"Monthly Invoice - {project_name}",
        xaxis_title="Month",
        yaxis_title="Amount ($)",
        yaxis_tickformat="$,.0f",
        height=400,
        margin=dict(t=60, b=40),
    )

    return fig


def _build_funding_gauge(months_left, project_name):
    """
    Build a Plotly gauge chart showing months of funding left.

    Uses red/yellow/green zones to indicate funding urgency.

    Args:
        months_left: Number of months of funding remaining (float or None/inf).
        project_name: Display name of the project.

    Returns:
        Plotly Figure object (gauge indicator).
    """
    is_unlimited = months_left is None or months_left == float("inf")
    max_range = 24
    if is_unlimited:
        display_value = max_range
    else:
        display_value = min(months_left, max_range)
        max_range = max(max_range, display_value + 6)

    # Determine bar color based on value
    if is_unlimited:
        bar_color = "#28a745"
    elif display_value < 3:
        bar_color = "#dc3545"
    elif display_value < 6:
        bar_color = "#ffc107"
    else:
        bar_color = "#28a745"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=display_value,
            number={"suffix": " mo"},
            title={"text": "Months of Funding Left"},
            gauge={
                "axis": {"range": [0, max_range]},
                "bar": {"color": bar_color},
                "steps": [
                    {"range": [0, 3], "color": "#ffcccc"},
                    {"range": [3, 6], "color": "#fff3cd"},
                    {"range": [6, max_range], "color": "#d4edda"},
                ],
            },
        )
    )

    fig.update_layout(height=300, margin=dict(t=60, b=20))
    return fig


def render_project_review_tab(db, processor):
    """
    Main render function for the Project Review Meeting page.

    Provides a filterable AgGrid table of all billable projects with funding
    health metrics and a drill-down dialog for individual project details.

    Args:
        db: DatabaseManager instance.
        processor: DataProcessor class reference.
    """
    st.markdown("#### Project Review Meeting")

    try:
        # Initialize session state for grid selection versioning (to clear selection on dialog dismiss)
        if "pr_grid_selection_version" not in st.session_state:
            st.session_state.pr_grid_selection_version = 0

        # ---- Fetch data ----
        projects_df = db.get_projects()
        if projects_df.empty:
            st.info("No projects found in the database.")
            return

        # Filter to billable projects only
        billable_projects = projects_df[projects_df["billable"] == 1].copy()
        if billable_projects.empty:
            st.info("No billable projects found.")
            return

        # ---- Filters row ----
        filter_cols = st.columns([2, 2, 1, 1])

        with filter_cols[0]:
            project_names = sorted(billable_projects["name"].dropna().unique().tolist())
            name_filter = st.multiselect("Project Name", project_names, key="pr_name_filter")

        with filter_cols[1]:
            clients = sorted(billable_projects["client"].dropna().unique().tolist())
            client_filter = st.multiselect("Client", clients, key="pr_client_filter")

        with filter_cols[2]:
            funding_filter = st.selectbox(
                "Funding Filter",
                ["All", ">90% Left", ">75% Left", ">50% Left", "Critical Only"],
                key="pr_funding_filter",
            )

        with filter_cols[3]:
            sort_by = st.selectbox(
                "Sort By",
                ["Project Name", "Client", "Funding Left (Low->High)", "Funding Left (High->Low)"],
                key="pr_sort_by",
            )

        # ---- Build project table ----
        with st.spinner("Computing funding metrics..."):
            table_df = _build_project_table(billable_projects, db, processor)

        if table_df.empty:
            st.warning("No data to display after computing funding metrics.")
            return

        # Apply user filters
        filtered_df = _apply_filters(table_df, name_filter, client_filter, funding_filter, sort_by)

        if filtered_df.empty:
            st.warning("No projects match the selected filters.")
            return

        # ---- Summary metrics ----
        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("Total Projects", len(filtered_df))
        with summary_cols[1]:
            critical_count = len(filtered_df[filtered_df["_funding_pct_raw"] < 10])
            st.metric("Critical Projects", critical_count)
        with summary_cols[2]:
            total_remaining = filtered_df["Funding Left ($)"].sum()
            st.metric("Total Remaining Funding", safe_currency_display(total_remaining))
        with summary_cols[3]:
            avg_funding_pct = filtered_df["_funding_pct_raw"].mean()
            if pd.isna(avg_funding_pct):
                avg_funding_pct = 0.0
            st.metric("Avg Funding Left", f"{avg_funding_pct:.1f}%")

        # ---- Prepare display DataFrame (drop hidden helper columns) ----
        display_cols = [
            "Project Name",
            "Project Code",
            "Client",
            "PM",
            "Status",
            "Quoted Value",
            "Awarded Value",
            "Budget Used",
            "Funding Left ($)",
            "Funding Left (%)",
            "Health Status",
            "Avg Monthly Invoice",
            "Months Left",
        ]
        display_df = filtered_df[display_cols].reset_index(drop=True)

        # ---- AgGrid configuration ----
        # JsCode for Health Status cell styling
        health_cell_style = JsCode("""
        function(params) {
            var val = params.value || '';
            if (val.indexOf('Risk') >= 0 && val.indexOf('Minor') < 0) {
                return {'backgroundColor': '#ffcccc', 'fontWeight': 'bold'};
            } else if (val.indexOf('Medium') >= 0) {
                return {'backgroundColor': '#ffe0b2', 'fontWeight': 'bold'};
            } else if (val.indexOf('Minor') >= 0) {
                return {'backgroundColor': '#fff9cc', 'fontWeight': 'bold'};
            } else if (val.indexOf('Good') >= 0) {
                return {'backgroundColor': '#ccffcc', 'fontWeight': 'bold'};
            }
            return {};
        }
        """)

        # JsCode for Funding Left (%) cell styling
        funding_pct_cell_style = JsCode("""
        function(params) {
            var val = params.value;
            if (val === null || val === undefined) return {};
            if (val < 10) {
                return {'backgroundColor': '#ffcccc'};
            } else if (val < 30) {
                return {'backgroundColor': '#ffe0b2'};
            } else if (val < 50) {
                return {'backgroundColor': '#fff9cc'};
            } else {
                return {'backgroundColor': '#ccffcc'};
            }
        }
        """)

        # Currency formatter
        currency_formatter = JsCode("""
        function(params) {
            if (params.value === null || params.value === undefined) return '-';
            return '$' + params.value.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
        }
        """)

        # Percentage formatter
        pct_formatter = JsCode("""
        function(params) {
            if (params.value === null || params.value === undefined) return 'N/A';
            return params.value.toFixed(1) + '%';
        }
        """)

        # Months formatter
        months_formatter = JsCode("""
        function(params) {
            if (params.value === null || params.value === undefined) return 'N/A';
            return params.value.toFixed(1);
        }
        """)

        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_selection(selection_mode="single", use_checkbox=False)
        gb.configure_default_column(sortable=True, filterable=False)

        # Configure currency columns
        for col_name in ["Quoted Value", "Awarded Value", "Budget Used", "Funding Left ($)", "Avg Monthly Invoice"]:
            gb.configure_column(col_name, valueFormatter=currency_formatter)

        # Configure percentage column with conditional styling
        gb.configure_column(
            "Funding Left (%)",
            cellStyle=funding_pct_cell_style,
            valueFormatter=pct_formatter,
        )

        # Configure Health Status with conditional styling
        gb.configure_column("Health Status", cellStyle=health_cell_style)

        # Configure Months Left
        gb.configure_column("Months Left", valueFormatter=months_formatter)

        grid_options = gb.build()

        st.markdown("---")
        st.info("Click on any row to view detailed project drill-down")

        grid_response = AgGrid(
            display_df,
            gridOptions=grid_options,
            height=500,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            allow_unsafe_jscode=True,
            theme="streamlit",
            key=f"project_review_aggrid_v{st.session_state.pr_grid_selection_version}",
        )

        # ---- Handle row selection => drill-down dialog ----
        def _clear_pr_grid_selection():
            """Callback to clear grid selection when dialog is dismissed."""
            st.session_state.pr_grid_selection_version += 1

        @st.dialog("Project Drill-Down", width="large", on_dismiss=_clear_pr_grid_selection)
        def _show_project_drilldown(row_data, db, processor):
            """
            Display detailed project drill-down in a dialog.

            Shows project details, financial KPIs, totals, a funding timeline chart,
            and a funding runway gauge.

            Args:
                row_data: The selected row from the AgGrid table (dict-like).
                db: DatabaseManager instance.
                processor: DataProcessor class reference.
            """
            project_code = row_data["Project Code"]
            project_name = row_data["Project Name"]

            st.markdown(f"### {project_name}")
            st.caption(f"Project Code: {project_code}")

            # ---- Project Details ----
            # Look up full project info
            all_projects = db.get_projects()
            proj_row = all_projects[all_projects["id"] == project_code]

            if proj_row.empty:
                st.error(f"Project {project_code} not found.")
                return

            proj = proj_row.iloc[0]
            client = proj.get("client", "-")
            pm = proj.get("project_manager", "-")
            start_date_str = proj.get("start_date", "-")
            end_date_str = proj.get("end_date", "-")
            quoted_value = proj.get("quoted_value", 0) or 0
            awarded_value = proj.get("awarded_value", 0) or 0
            budget_used = proj.get("budget_used", 0) or 0
            remaining_funding = awarded_value - budget_used

            # Team members from allocations
            allocations_df = db.get_allocations(project_id=project_code)
            if not allocations_df.empty and "employee_name" in allocations_df.columns:
                team_members = sorted(allocations_df["employee_name"].dropna().unique().tolist())
                team_str = ", ".join(team_members) if team_members else "No team allocated"
            else:
                team_str = "No allocations found"

            st.markdown("##### Project Details")
            detail_cols = st.columns(4)
            with detail_cols[0]:
                st.markdown(f"**Client:** {client}")
            with detail_cols[1]:
                st.markdown(f"**Project ID:** {project_code}")
            with detail_cols[2]:
                st.markdown(f"**Start:** {start_date_str}")
            with detail_cols[3]:
                st.markdown(f"**End:** {end_date_str}")

            st.markdown(f"**Team:** {team_str}")

            st.markdown("---")

            # ---- Financial KPIs (3 columns) ----
            st.markdown("##### Financial KPIs")

            # Past month invoice: actuals from last complete month
            now = datetime.now()
            last_month_end = date(now.year, now.month, 1) - relativedelta(days=1)
            last_month_start = date(last_month_end.year, last_month_end.month, 1)
            past_month_invoice = 0.0
            try:
                pm_metrics = processor.get_performance_metrics(
                    start_date=last_month_start.strftime("%Y-%m-%d"),
                    end_date=last_month_end.strftime("%Y-%m-%d"),
                    constraint={"project_id": str(project_code)},
                )
                pm_actuals = pm_metrics.get("actuals", {})
                for month_name, employees in pm_actuals.items():
                    past_month_invoice += sum(
                        emp.get("revenue", 0) for emp in employees.values()
                    )
            except Exception as e:
                logger.warning(f"Could not compute past month invoice for {project_code}: {e}")

            avg_monthly = calculate_avg_monthly_invoice(project_code, db, processor)
            current_potential = calculate_current_month_potential(project_code, db)

            kpi_cols = st.columns(3)
            with kpi_cols[0]:
                last_month_label = last_month_start.strftime("%B %Y")
                st.metric(f"Past Month Invoice ({last_month_label})", safe_currency_display(past_month_invoice))
            with kpi_cols[1]:
                st.metric("Average Monthly Invoice", safe_currency_display(avg_monthly))
            with kpi_cols[2]:
                st.metric("Current Monthly Potential", safe_currency_display(current_potential))

            st.markdown("---")

            # ---- Totals (3 columns) ----
            st.markdown("##### Totals")

            # YTD Total Invoice: sum of actuals revenue for current year
            ytd_start = date(now.year, 1, 1)
            ytd_invoice = 0.0
            try:
                ytd_metrics = processor.get_performance_metrics(
                    start_date=ytd_start.strftime("%Y-%m-%d"),
                    end_date=now.strftime("%Y-%m-%d"),
                    constraint={"project_id": str(project_code)},
                )
                ytd_actuals = ytd_metrics.get("actuals", {})
                for month_name, employees in ytd_actuals.items():
                    ytd_invoice += sum(
                        emp.get("revenue", 0) for emp in employees.values()
                    )
            except Exception as e:
                logger.warning(f"Could not compute YTD invoice for {project_code}: {e}")

            totals_cols = st.columns(3)
            with totals_cols[0]:
                st.metric("Total Contract (Quoted)", safe_currency_display(quoted_value))
            with totals_cols[1]:
                st.metric("YTD Total Invoice", safe_currency_display(ytd_invoice))
            with totals_cols[2]:
                st.metric("Remaining Funding", safe_currency_display(remaining_funding))

            st.markdown("---")

            # ---- Funding Timeline Chart ----
            st.markdown("##### Funding Timeline")

            timeline_fig = _build_funding_timeline_chart(
                project_code, project_name, awarded_value, db, processor
            )
            if timeline_fig:
                st.plotly_chart(timeline_fig, use_container_width=True)
            else:
                st.info("No revenue data available to build the funding timeline chart.")

            # ---- Funding Runway Gauge ----
            st.markdown("##### Funding Runway")

            months_left = calculate_funding_runway(remaining_funding, avg_monthly)
            if months_left is None or months_left == float("inf"):
                st.info("No monthly spend detected \u2014 funding runway is effectively unlimited.")
            gauge_fig = _build_funding_gauge(months_left, project_name)
            st.plotly_chart(gauge_fig, use_container_width=True)

        # Trigger dialog on row selection
        selected_rows = grid_response["selected_rows"]
        if selected_rows is not None and len(selected_rows) > 0:
            selected_row = selected_rows.iloc[0] if hasattr(selected_rows, "iloc") else selected_rows[0]
            _show_project_drilldown(selected_row, db, processor)

    except Exception as e:
        st.error(f"Error loading project review data: {str(e)}")
        logger.error(f"Error in project review tab: {str(e)}", exc_info=True)
