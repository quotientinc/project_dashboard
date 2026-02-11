"""
Project Timeline / Gantt page - visual project timeline with Gantt chart,
budget tracking, and phase management with CSV import support.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from utils.project_helpers import safe_currency_display, safe_budget_percentage
from utils.logger import get_logger

logger = get_logger(__name__)

# Constants for dropdown options
PHASE_TYPE_OPTIONS = ['Planning', 'Execution', 'Testing', 'Deployment', 'Review', 'Other']
RISK_OPTIONS = ['Low', 'Medium', 'High']
STATUS_OPTIONS = ['Not Started', 'In Progress', 'Completed', 'Delayed']

# Color map for phase types in the Gantt chart
PHASE_TYPE_COLOR_MAP = {
    'Planning': '#3498DB',
    'Execution': '#2ECC71',
    'Testing': '#F39C12',
    'Deployment': '#9B59B6',
    'Review': '#1ABC9C',
    'Other': '#95A5A6',
}


def render_project_timeline_tab(db, processor, project_id=None):
    """Render the Project Timeline / Gantt page.

    Args:
        db: DatabaseManager instance
        processor: DataProcessor instance
        project_id: Optional project ID. If provided, skips the selectbox and uses this project directly.
    """
    st.markdown("### Project Timeline / Gantt")

    projects_df = db.get_projects()

    if projects_df.empty:
        st.info("No projects available. Add projects first to view timelines.")
        return

    if project_id is not None:
        # Use provided project ID directly
        project_match = projects_df[projects_df['id'] == project_id]
        if project_match.empty:
            st.error(f"Project {project_id} not found")
            return
        project = project_match.iloc[0]
    else:
        # Original selectbox behavior
        project_names = projects_df['name'].tolist()
        selected_project_name = st.selectbox(
            "Select Project",
            options=project_names,
            key="timeline_project_selector"
        )

        if not selected_project_name:
            return
        project = projects_df[projects_df['name'] == selected_project_name].iloc[0]

    project_id = project['id']  # Ensure project_id is set for later use

    # --- Financial Summary ---
    _render_financial_summary(project)

    st.markdown("---")

    # --- Budget Timeline Chart ---
    _render_budget_timeline_chart(db, project, project_id)

    st.markdown("---")

    # --- Gantt Chart ---
    _render_gantt_chart(db, project_id)

    st.markdown("---")

    # --- Phase Data Table and Management ---
    _render_phase_management(db, project_id)


def _render_financial_summary(project):
    """Render the top financial summary row with 4 metric columns."""
    quoted = project['quoted_value'] if pd.notna(project['quoted_value']) else 0
    awarded = project['awarded_value'] if pd.notna(project['awarded_value']) else 0
    budget_used = project['budget_used'] if pd.notna(project['budget_used']) else 0
    budget_remaining = awarded - budget_used

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Quoted Value", safe_currency_display(quoted))
    with col2:
        st.metric("Awarded Value", safe_currency_display(awarded))
    with col3:
        st.metric("Budget Used", safe_currency_display(budget_used))
    with col4:
        delta_color = "normal" if budget_remaining >= 0 else "inverse"
        st.metric(
            "Budget Remaining",
            safe_currency_display(budget_remaining),
            delta=f"{((budget_remaining / awarded) * 100):.1f}% of awarded" if awarded > 0 else None,
            delta_color=delta_color
        )


def _render_budget_timeline_chart(db, project, project_id):
    """Render the cumulative burn timeline chart with quoted/awarded reference lines."""
    st.markdown("#### Budget Timeline")

    time_entries = db.get_time_entries(project_id=project_id)

    quoted = project['quoted_value'] if pd.notna(project['quoted_value']) else 0
    awarded = project['awarded_value'] if pd.notna(project['awarded_value']) else 0

    if time_entries.empty:
        st.info("No time entries found for this project. The budget timeline chart will appear once time data is available.")
        return

    try:
        # Calculate cost per entry: use amount if available, else hours * bill_rate (or hourly_rate fallback)
        def calculate_entry_cost(row):
            if pd.notna(row.get('amount')) and row.get('amount', 0) != 0:
                return row['amount']
            rate = row.get('bill_rate')
            if pd.isna(rate):
                rate = row.get('hourly_rate')
            if pd.notna(rate) and pd.notna(row.get('hours')):
                return row['hours'] * rate
            return 0.0

        time_entries = time_entries.copy()
        time_entries['cost'] = time_entries.apply(calculate_entry_cost, axis=1)
        time_entries['date'] = pd.to_datetime(time_entries['date'])
        time_entries['month'] = time_entries['date'].dt.to_period('M').dt.to_timestamp()

        # Group by month and compute cumulative burn
        monthly_burn = time_entries.groupby('month')['cost'].sum().reset_index()
        monthly_burn.columns = ['month', 'monthly_cost']
        monthly_burn = monthly_burn.sort_values('month')
        monthly_burn['cumulative_burn'] = monthly_burn['monthly_cost'].cumsum()

        fig = go.Figure()

        # Cumulative burn line with fill
        fig.add_trace(go.Scatter(
            x=monthly_burn['month'],
            y=monthly_burn['cumulative_burn'],
            name='Cumulative Actual Burn',
            mode='lines+markers',
            line=dict(color='#2E86C1', width=3),
            fill='tozeroy',
            fillcolor='rgba(46, 134, 193, 0.15)'
        ))

        # Awarded value horizontal reference line
        if awarded > 0:
            fig.add_hline(
                y=awarded,
                line_dash="dash",
                line_color="green",
                annotation_text=f"Awarded: {safe_currency_display(awarded)}",
                annotation_position="top left"
            )

        # Quoted value horizontal reference line
        if quoted > 0:
            fig.add_hline(
                y=quoted,
                line_dash="dot",
                line_color="blue",
                annotation_text=f"Quoted: {safe_currency_display(quoted)}",
                annotation_position="bottom left"
            )

        fig.update_layout(
            title="Cumulative Budget Burn Over Time",
            xaxis_title="Month",
            yaxis_title="Amount ($)",
            height=400,
            hovermode='x unified'
        )

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        logger.error(f"Error rendering budget timeline chart: {str(e)}", exc_info=True)
        st.error(f"Error rendering budget timeline chart: {str(e)}")


def _render_gantt_chart(db, project_id):
    """Render the Gantt chart from project phases."""
    st.markdown("#### Project Gantt Chart")

    phases_df = db.get_project_phases(project_id=project_id)

    if phases_df.empty:
        st.info("No phases defined yet. Add phases below to see the Gantt chart.")
        return

    try:
        # Prepare data for timeline
        gantt_df = phases_df.copy()

        # Ensure date columns are datetime
        gantt_df['start_date'] = pd.to_datetime(gantt_df['start_date'], errors='coerce')
        gantt_df['end_date'] = pd.to_datetime(gantt_df['end_date'], errors='coerce')

        # Drop rows with invalid dates
        valid_mask = gantt_df['start_date'].notna() & gantt_df['end_date'].notna()
        if not valid_mask.any():
            st.warning("All phases have missing or invalid dates. Please update phase dates.")
            return

        gantt_df = gantt_df[valid_mask].copy()

        # Fill missing phase_type for color mapping
        gantt_df['phase_type'] = gantt_df['phase_type'].fillna('Other')

        # Fill missing fields for hover data
        gantt_df['status'] = gantt_df['status'].fillna('Not Started')
        gantt_df['risk'] = gantt_df['risk'].fillna('Low')
        gantt_df['predecessors'] = gantt_df['predecessors'].fillna('')
        gantt_df['completion_pct'] = gantt_df['completion_pct'].fillna(0)

        fig = px.timeline(
            gantt_df,
            x_start="start_date",
            x_end="end_date",
            y="phase_name",
            color="phase_type",
            hover_data=["status", "risk", "predecessors", "completion_pct"],
            color_discrete_map=PHASE_TYPE_COLOR_MAP
        )

        # Reverse y-axis so the first phase appears at the top
        fig.update_yaxes(
            categoryorder='array',
            categoryarray=list(reversed(gantt_df['phase_name'].tolist()))
        )

        fig.update_layout(
            height=max(400, len(gantt_df) * 60),
            xaxis_title="Date",
            yaxis_title="Phase",
            showlegend=True
        )

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        logger.error(f"Error rendering Gantt chart: {str(e)}", exc_info=True)
        st.error(f"Error rendering Gantt chart: {str(e)}")


def _render_phase_management(db, project_id):
    """Render the phase data table (AgGrid) and management controls."""
    st.markdown("#### Phase Management")

    phases_df = db.get_project_phases(project_id=project_id)

    # --- Action buttons row ---
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])

    with btn_col1:
        if st.button("Add Phase", key="add_phase_btn", use_container_width=True):
            _show_add_phase_dialog(db, project_id)

    with btn_col2:
        delete_disabled = phases_df.empty
        if st.button("Delete Phase", key="delete_phase_btn", disabled=delete_disabled, use_container_width=True):
            st.session_state['timeline_confirm_delete'] = True

    with btn_col3:
        uploaded_file = st.file_uploader(
            "Import Phases from CSV",
            type=['csv'],
            key="phase_csv_uploader",
            help="Upload a CSV with columns: Phase Name, Type, Start Date, End Date, Predecessors, Risk, Status, % Complete"
        )
        if uploaded_file is not None:
            _handle_csv_import(db, project_id, uploaded_file)

    if phases_df.empty:
        st.info("No phases defined for this project. Use 'Add Phase' or 'Import from CSV' to get started.")
        return

    # --- Phase data table (AgGrid) ---
    display_df = phases_df[['id', 'phase_name', 'phase_type', 'start_date', 'end_date',
                             'predecessors', 'risk', 'status', 'completion_pct']].copy()

    # Fill NaN for display
    display_df['predecessors'] = display_df['predecessors'].fillna('')
    display_df['completion_pct'] = display_df['completion_pct'].fillna(0)
    display_df['phase_type'] = display_df['phase_type'].fillna('Other')
    display_df['risk'] = display_df['risk'].fillna('Low')
    display_df['status'] = display_df['status'].fillna('Not Started')
    display_df['start_date'] = display_df['start_date'].fillna('')
    display_df['end_date'] = display_df['end_date'].fillna('')

    gb = GridOptionsBuilder.from_dataframe(display_df)

    # Configure selection
    gb.configure_selection(selection_mode='single', use_checkbox=False)

    # Hide the id column
    gb.configure_column("id", hide=True)

    # Editable columns
    gb.configure_column("phase_name", header_name="Phase Name", editable=True, minWidth=180)
    gb.configure_column(
        "phase_type",
        header_name="Type",
        editable=True,
        cellEditor='agSelectCellEditor',
        cellEditorParams={'values': PHASE_TYPE_OPTIONS},
        minWidth=120
    )
    gb.configure_column("start_date", header_name="Start Date", editable=True, minWidth=120)
    gb.configure_column("end_date", header_name="End Date", editable=True, minWidth=120)
    gb.configure_column("predecessors", header_name="Predecessors", editable=True, minWidth=120)
    gb.configure_column(
        "risk",
        header_name="Risk",
        editable=True,
        cellEditor='agSelectCellEditor',
        cellEditorParams={'values': RISK_OPTIONS},
        minWidth=100
    )
    gb.configure_column(
        "status",
        header_name="Status",
        editable=True,
        cellEditor='agSelectCellEditor',
        cellEditorParams={'values': STATUS_OPTIONS},
        minWidth=130
    )
    gb.configure_column(
        "completion_pct",
        header_name="% Complete",
        editable=True,
        type=["numericColumn"],
        minWidth=110
    )

    grid_options = gb.build()

    grid_response = AgGrid(
        display_df,
        gridOptions=grid_options,
        height=min(500, max(200, len(display_df) * 45 + 50)),
        update_mode=GridUpdateMode.SELECTION_CHANGED | GridUpdateMode.VALUE_CHANGED,
        theme='streamlit',
        key="phase_aggrid"
    )

    # --- Save edits button ---
    if st.button("Save Changes", key="save_phase_changes_btn", type="primary"):
        _save_phase_edits(db, grid_response, project_id)

    # --- Handle delete confirmation ---
    if st.session_state.get('timeline_confirm_delete', False):
        selected_rows = grid_response.selected_rows
        if selected_rows is not None and len(selected_rows) > 0:
            selected_row = selected_rows.iloc[0] if isinstance(selected_rows, pd.DataFrame) else selected_rows[0]
            phase_name = selected_row.get('phase_name', 'Unknown')
            phase_id = selected_row.get('id')

            st.warning(f"Are you sure you want to delete phase '{phase_name}'?")
            confirm_col1, confirm_col2 = st.columns(2)
            with confirm_col1:
                if st.button("Yes, Delete", key="confirm_delete_yes", type="primary"):
                    try:
                        db.delete_project_phase(phase_id)
                        st.session_state['timeline_confirm_delete'] = False
                        logger.info(f"Deleted phase id={phase_id} name='{phase_name}' from project {project_id}")
                        st.toast(f"Phase '{phase_name}' deleted successfully.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        logger.error(f"Error deleting phase: {str(e)}", exc_info=True)
                        st.error(f"Error deleting phase: {str(e)}")
            with confirm_col2:
                if st.button("Cancel", key="confirm_delete_no"):
                    st.session_state['timeline_confirm_delete'] = False
                    st.rerun()
        else:
            st.warning("Please select a phase row in the table above before deleting.")
            st.session_state['timeline_confirm_delete'] = False


def _save_phase_edits(db, grid_response, project_id):
    """Persist edits from the AgGrid back to the database."""
    try:
        edited_data = grid_response['data']
        if isinstance(edited_data, pd.DataFrame):
            edited_rows = edited_data.to_dict('records')
        else:
            edited_rows = edited_data

        updated_count = 0
        for row in edited_rows:
            phase_id = row.get('id')
            if pd.isna(phase_id):
                continue

            updates = {
                'phase_name': row.get('phase_name', ''),
                'phase_type': row.get('phase_type', 'Other'),
                'start_date': row.get('start_date', ''),
                'end_date': row.get('end_date', ''),
                'predecessors': row.get('predecessors', ''),
                'risk': row.get('risk', 'Low'),
                'status': row.get('status', 'Not Started'),
                'completion_pct': max(0.0, min(100.0, float(row.get('completion_pct', 0)))) if pd.notna(row.get('completion_pct')) else 0,
            }
            db.update_project_phase(phase_id, updates)
            updated_count += 1

        logger.info(f"Saved {updated_count} phase edits for project {project_id}")
        st.toast(f"Saved {updated_count} phase(s) successfully.")
        st.cache_data.clear()
        st.rerun()

    except Exception as e:
        logger.error(f"Error saving phase edits: {str(e)}", exc_info=True)
        st.error(f"Error saving phase edits: {str(e)}")


@st.dialog("Add Phase", width="large")
def _show_add_phase_dialog(db, project_id):
    """Dialog for adding a new phase to the project."""
    with st.form("add_phase_form"):
        phase_name = st.text_input("Phase Name", placeholder="e.g., Requirements Gathering")

        type_col, risk_col = st.columns(2)
        with type_col:
            phase_type = st.selectbox("Phase Type", options=PHASE_TYPE_OPTIONS)
        with risk_col:
            risk = st.selectbox("Risk Level", options=RISK_OPTIONS)

        date_col1, date_col2 = st.columns(2)
        with date_col1:
            start_date = st.date_input("Start Date", value=date.today())
        with date_col2:
            end_date = st.date_input("End Date", value=date.today())

        predecessors = st.text_input(
            "Predecessors",
            placeholder="e.g., Phase 1, Phase 2",
            help="Comma-separated list of predecessor phase names"
        )

        status = st.selectbox("Status", options=STATUS_OPTIONS)
        completion_pct = st.slider("% Complete", min_value=0, max_value=100, value=0, step=5)

        submitted = st.form_submit_button("Add Phase", type="primary")

        if submitted:
            if not phase_name.strip():
                st.error("Phase Name is required.")
                return

            if end_date < start_date:
                st.error("End Date must be on or after Start Date.")
                return

            phase_data = {
                'project_id': str(project_id),
                'phase_name': phase_name.strip(),
                'phase_type': phase_type,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'predecessors': predecessors.strip(),
                'risk': risk,
                'status': status,
                'completion_pct': float(completion_pct),
            }

            try:
                db.add_project_phase(phase_data)
                logger.info(f"Added phase '{phase_name}' to project {project_id}")
                st.toast(f"Phase '{phase_name}' added successfully.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                logger.error(f"Error adding phase: {str(e)}", exc_info=True)
                st.error(f"Error adding phase: {str(e)}")


def _handle_csv_import(db, project_id, uploaded_file):
    """Handle CSV import for project phases."""
    try:
        csv_df = pd.read_csv(uploaded_file)
        logger.info(f"CSV import: Read {len(csv_df)} rows with columns: {list(csv_df.columns)}")

        # Normalize column names: lowercase, strip whitespace, replace spaces with underscores
        csv_df.columns = [col.strip().lower().replace(' ', '_').replace('%', 'pct') for col in csv_df.columns]

        # Map expected column names to actual column names (flexible matching)
        column_map = _build_column_map(csv_df.columns)

        # Validate required columns
        if 'phase_name' not in column_map:
            st.error(
                "CSV must contain a 'Phase Name' column (or similar). "
                f"Found columns: {list(csv_df.columns)}"
            )
            return

        # Transform CSV data into phase dicts
        phases_list = []
        errors = []

        for idx, row in csv_df.iterrows():
            try:
                phase = _parse_csv_row(row, column_map, idx)
                phases_list.append(phase)
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")

        if errors:
            st.warning(f"Skipped {len(errors)} rows with errors:")
            for err in errors[:10]:
                st.text(f"  - {err}")
            if len(errors) > 10:
                st.text(f"  ... and {len(errors) - 10} more")

        if not phases_list:
            st.error("No valid phases found in CSV file.")
            return

        # Show preview
        st.markdown(f"**Preview: {len(phases_list)} phases to import**")
        preview_df = pd.DataFrame(phases_list)
        preview_cols = [c for c in ['phase_name', 'phase_type', 'start_date', 'end_date',
                                      'risk', 'status', 'completion_pct'] if c in preview_df.columns]
        st.dataframe(preview_df[preview_cols], hide_index=True, use_container_width=True)

        st.warning("This will replace ALL existing phases for this project.")

        if st.button("Confirm Import", key="confirm_csv_import", type="primary"):
            db.bulk_insert_project_phases(phases_list, project_id)
            logger.info(f"Imported {len(phases_list)} phases from CSV for project {project_id}")
            st.toast(f"Successfully imported {len(phases_list)} phases.")
            st.cache_data.clear()
            st.rerun()

    except Exception as e:
        logger.error(f"Error importing CSV: {str(e)}", exc_info=True)
        st.error(f"Error reading CSV file: {str(e)}")


def _build_column_map(columns):
    """
    Build a flexible mapping from canonical field names to actual CSV column names.
    Handles case-insensitive matching, underscores vs spaces, and common variations.
    """
    column_map = {}
    columns_list = list(columns)

    # Define patterns for each canonical field
    patterns = {
        'phase_name': ['phase_name', 'phase', 'name', 'task_name', 'task', 'activity', 'milestone'],
        'phase_type': ['phase_type', 'type', 'category', 'task_type'],
        'start_date': ['start_date', 'start', 'begin_date', 'begin', 'from_date', 'from'],
        'end_date': ['end_date', 'end', 'finish_date', 'finish', 'to_date', 'to', 'due_date', 'due'],
        'predecessors': ['predecessors', 'predecessor', 'depends_on', 'dependencies', 'dependency'],
        'risk': ['risk', 'risk_level', 'priority'],
        'status': ['status', 'state', 'phase_status', 'task_status'],
        'completion_pct': ['completion_pct', 'pct_complete', 'complete', 'completion',
                           'percent_complete', 'progress', 'done_pct'],
    }

    for canonical, variations in patterns.items():
        for variation in variations:
            if variation in columns_list:
                column_map[canonical] = variation
                break

    return column_map


def _parse_csv_row(row, column_map, idx):
    """Parse a single CSV row into a phase dict using the column map."""
    phase = {}

    # Phase name (required)
    raw_name = row.get(column_map.get('phase_name', ''), '')
    if pd.isna(raw_name) or str(raw_name).strip() == '':
        raise ValueError("Missing phase name")
    phase['phase_name'] = str(raw_name).strip()

    # Phase type
    raw_type = row.get(column_map.get('phase_type', ''), 'Other')
    if pd.isna(raw_type) or str(raw_type).strip() == '':
        raw_type = 'Other'
    phase_type = str(raw_type).strip()
    # Normalize to valid options
    if phase_type not in PHASE_TYPE_OPTIONS:
        # Try case-insensitive match
        match = [opt for opt in PHASE_TYPE_OPTIONS if opt.lower() == phase_type.lower()]
        phase_type = match[0] if match else 'Other'
    phase['phase_type'] = phase_type

    # Start date
    raw_start = row.get(column_map.get('start_date', ''), '')
    if pd.notna(raw_start) and str(raw_start).strip():
        try:
            parsed = pd.to_datetime(str(raw_start).strip())
            phase['start_date'] = parsed.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            raise ValueError(f"Invalid start date: '{raw_start}'")
    else:
        phase['start_date'] = ''

    # End date
    raw_end = row.get(column_map.get('end_date', ''), '')
    if pd.notna(raw_end) and str(raw_end).strip():
        try:
            parsed = pd.to_datetime(str(raw_end).strip())
            phase['end_date'] = parsed.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            raise ValueError(f"Invalid end date: '{raw_end}'")
    else:
        phase['end_date'] = ''

    # Predecessors
    raw_pred = row.get(column_map.get('predecessors', ''), '')
    phase['predecessors'] = str(raw_pred).strip() if pd.notna(raw_pred) else ''

    # Risk
    raw_risk = row.get(column_map.get('risk', ''), 'Low')
    if pd.isna(raw_risk) or str(raw_risk).strip() == '':
        raw_risk = 'Low'
    risk = str(raw_risk).strip()
    if risk not in RISK_OPTIONS:
        match = [opt for opt in RISK_OPTIONS if opt.lower() == risk.lower()]
        risk = match[0] if match else 'Low'
    phase['risk'] = risk

    # Status
    raw_status = row.get(column_map.get('status', ''), 'Not Started')
    if pd.isna(raw_status) or str(raw_status).strip() == '':
        raw_status = 'Not Started'
    status = str(raw_status).strip()
    if status not in STATUS_OPTIONS:
        match = [opt for opt in STATUS_OPTIONS if opt.lower() == status.lower()]
        status = match[0] if match else 'Not Started'
    phase['status'] = status

    # Completion percentage
    raw_pct = row.get(column_map.get('completion_pct', ''), 0)
    if pd.isna(raw_pct) or str(raw_pct).strip() == '':
        raw_pct = 0
    try:
        pct = float(str(raw_pct).strip().replace('%', ''))
        pct = max(0.0, min(100.0, pct))
    except (ValueError, TypeError):
        pct = 0.0
    phase['completion_pct'] = pct

    return phase
