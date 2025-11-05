import streamlit as st
import pandas as pd
from datetime import datetime
import io
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager

st.markdown("### 📊 Data Management (🚨use with caution some import logic needs updated)")

tab1, tab2, tab3, tab4 = st.tabs(["Import Data", "Export Data", "Data Backup", "Database Management"])

with tab1:
    st.markdown("#### Import Data")

    # Timesheet CSV Import Section
    st.markdown("##### 📋 Import Timesheet CSV")
    st.info("Import timesheet data from TimesheetData.csv format. This will migrate the database schema and replace all time entries.")

    with st.expander("Timesheet CSV Import", expanded=False):
        st.markdown("""
        **Timesheet CSV Format:**
        - Columns: Employee ID, Employee Name, Project ID, Hours Date, Entered Hours, Comments, PLC ID, PLC Desc, Billing Rate, Amount
        - Date Format: DD-MMM-YY (e.g., "25-Dec-24")
        - Automatically creates projects and employees from CSV data

        **⚠️ Warning:**
        - This will migrate the database to use CSV ID formats
        - Projects will use string IDs (e.g., "202800.Y2.000.00")
        - Employees will use CSV Employee IDs (e.g., 100482)
        - All existing time entries and expenses will be deleted
        - Allocations will be preserved but may have orphaned references
        """)

        timesheet_file = st.file_uploader(
            "Choose Timesheet CSV file",
            type=['csv'],
            key="timesheet_upload",
            help="Upload a CSV file in TimesheetData.csv format"
        )

        if timesheet_file is not None:
            try:
                from utils.csv_importer import TimesheetCSVImporter

                # Parse and preview
                importer = TimesheetCSVImporter(timesheet_file)
                projects, employees, time_entries, summary = importer.import_all()

                # Show summary
                st.markdown("##### Import Preview")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Rows", summary['total_rows'])
                with col2:
                    st.metric("Projects", summary['unique_projects'])
                with col3:
                    st.metric("Employees", summary['unique_employees'])
                with col4:
                    st.metric("Time Entries", summary['time_entries'])

                if summary['date_range']:
                    st.write(f"**Date Range:** {summary['date_range'][0]} to {summary['date_range'][1]}")
                st.write(f"**Total Hours:** {summary['total_hours']:,.1f}")

                # Show date range comparison
                if summary['date_range']:
                    existing_range = db.get_existing_time_entries_date_range()

                    st.markdown("### 📅 Date Range Impact")
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown("**Incoming CSV:**")
                        st.info(f"{summary['date_range'][0]}\nto\n{summary['date_range'][1]}")

                    with col2:
                        st.markdown("**Current Database:**")
                        if existing_range:
                            st.info(f"{existing_range[0]}\nto\n{existing_range[1]}")
                        else:
                            st.info("No existing\ntime entries")

                    with col3:
                        st.markdown("**Will Be Deleted:**")
                        if existing_range:
                            # Calculate overlap
                            csv_start = summary['date_range'][0]
                            csv_end = summary['date_range'][1]
                            db_start = existing_range[0]
                            db_end = existing_range[1]

                            # Overlap is max(start1, start2) to min(end1, end2)
                            overlap_start = max(csv_start, db_start)
                            overlap_end = min(csv_end, db_end)

                            if overlap_start <= overlap_end:
                                st.warning(f"{overlap_start}\nto\n{overlap_end}")
                            else:
                                st.success("No overlap\n(safe import)")
                        else:
                            st.success("No existing\ndata")

                # Show sample data
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Sample Projects:**")
                    st.dataframe(
                        pd.DataFrame(projects[:5])[['id', 'name']],
                        height=150,
                        hide_index=True
                    )
                with col2:
                    st.markdown("**Sample Employees:**")
                    st.dataframe(
                        pd.DataFrame(employees[:5])[['id', 'name', 'role']],
                        height=150,
                        hide_index=True
                    )

                # Confirmation checkbox
                if summary['date_range']:
                    existing_range = db.get_existing_time_entries_date_range()
                    if existing_range:
                        csv_start = summary['date_range'][0]
                        csv_end = summary['date_range'][1]
                        db_start = existing_range[0]
                        db_end = existing_range[1]
                        overlap_start = max(csv_start, db_start)
                        overlap_end = min(csv_end, db_end)

                        if overlap_start <= overlap_end:
                            confirm_text = f"I understand this will delete time entries from {overlap_start} to {overlap_end}, and migrate the database schema"
                        else:
                            confirm_text = "I understand this will import new data and migrate the database schema (no existing data will be deleted)"
                    else:
                        confirm_text = "I understand this will import new data and migrate the database schema (no existing data to delete)"
                else:
                    confirm_text = "I understand this will delete all existing time entries and expenses, and migrate the database schema"

                confirm_import = st.checkbox(
                    confirm_text,
                    key="confirm_timesheet_import"
                )

                if st.button("Import Timesheet Data", type="primary", disabled=not confirm_import):
                    try:
                        progress_bar = st.progress(0, text="Starting import...")

                        # Step 1: Migrate schema
                        progress_bar.progress(10, text="Migrating database schema...")
                        db.migrate_schema_for_csv_import()

                        # Step 2: Delete existing time entries in the CSV date range
                        # This enables incremental imports while preserving data outside the range
                        deleted_count = 0
                        if summary['date_range']:
                            csv_start, csv_end = summary['date_range']
                            existing_range = db.get_existing_time_entries_date_range()

                            if existing_range:
                                # Calculate overlap
                                db_start, db_end = existing_range
                                overlap_start = max(csv_start, db_start)
                                overlap_end = min(csv_end, db_end)

                                if overlap_start <= overlap_end:
                                    progress_bar.progress(20, text=f"Clearing time entries from {overlap_start} to {overlap_end}...")
                                    deleted_count = db.delete_time_entries_by_date_range(overlap_start, overlap_end)
                                else:
                                    progress_bar.progress(20, text="No overlapping time entries to clear...")
                            else:
                                progress_bar.progress(20, text="No existing time entries (first import)...")

                            # Always clear expenses (they're typically regenerated on import)
                            cursor = db.conn.cursor()
                            cursor.execute("DELETE FROM expenses")
                            db.conn.commit()
                        else:
                            # Fallback: No date range available, clear all (original behavior)
                            progress_bar.progress(20, text="Clearing all existing time entries and expenses...")
                            cursor = db.conn.cursor()
                            cursor.execute("DELETE FROM time_entries")
                            cursor.execute("DELETE FROM expenses")
                            db.conn.commit()
                            cursor.execute("SELECT changes()")
                            deleted_count = cursor.fetchone()[0]

                        # Step 3: Import projects
                        progress_bar.progress(30, text=f"Importing {len(projects)} projects...")
                        db.bulk_insert_projects(projects)

                        # Step 4: Import employees
                        progress_bar.progress(50, text=f"Importing {len(employees)} employees...")
                        db.bulk_insert_employees(employees)

                        # Step 5: Import time entries
                        progress_bar.progress(70, text=f"Importing {len(time_entries)} time entries...")
                        db.bulk_insert_time_entries(time_entries)

                        progress_bar.progress(100, text="Import complete!")

                        # Build success message with deletion info
                        success_msg = f"""
                        ✅ Timesheet import completed successfully!
                        - Imported {len(projects)} projects
                        - Imported {len(employees)} employees
                        - Imported {len(time_entries)} time entries
                        - Total hours: {summary['total_hours']:,.1f}
                        """
                        if deleted_count > 0:
                            if summary['date_range']:
                                csv_start, csv_end = summary['date_range']
                                success_msg += f"\n- Replaced {deleted_count} existing time entries in date range {csv_start} to {csv_end}"
                            else:
                                success_msg += f"\n- Deleted {deleted_count} previous time entries"

                        st.success(success_msg)
                        st.balloons()

                        # Wait a moment before reloading
                        import time
                        time.sleep(2)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error importing timesheet data: {str(e)}")
                        st.exception(e)

            except Exception as e:
                st.error(f"Error parsing timesheet CSV: {str(e)}")
                st.exception(e)

    st.divider()

    # Employee Reference CSV Import Section
    st.markdown("##### 👥 Import Employee Reference CSV")
    st.info("Import employee data from EmployeeReference.csv format. This will merge with existing employee data - CSV is authoritative for matched fields, database-only fields are preserved.")

    with st.expander("Employee Reference CSV Import", expanded=False):
        st.markdown("""
        **Employee Reference CSV Format:**
        - Columns: Employee Id, Last Name, Preferred/First Name, Billable, Hire Date, Term Date, Job Title, Pay Type Code, Base Rate, Annual Salary, PTO Accural, Holidays
        - Date Format: M/D/YY (e.g., "1/15/19")
        - Employee ID is used to match existing records

        **Merge Behavior:**
        - Existing employees: Updates data from CSV, preserves skills/allocations manually set in database
        - New employees: Creates new records with smart defaults for billable employees
        - CSV fields override database values for matched employees
        - Database-only fields (skills, overhead_allocation, target_allocation) are preserved
        """)

        employee_ref_file = st.file_uploader(
            "Choose Employee Reference CSV file",
            type=['csv'],
            key="employee_ref_upload",
            help="Upload a CSV file in EmployeeReference.csv format"
        )

        if employee_ref_file is not None:
            try:
                from utils.csv_importer import EmployeeReferenceCSVImporter

                # Parse and preview
                importer = EmployeeReferenceCSVImporter(employee_ref_file)
                employees, summary = importer.import_all()

                # Show summary
                st.markdown("##### Import Preview")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Employees", summary['total_employees'])
                with col2:
                    st.metric("Billable", summary['billable_employees'])
                with col3:
                    st.metric("Salary", summary['salary_employees'])
                with col4:
                    st.metric("Hourly", summary['hourly_employees'])

                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Active Employees:** {summary['active_employees']}")
                with col2:
                    st.write(f"**Terminated:** {summary['with_term_date']}")

                # Show sample data
                st.markdown("**Sample Employees:**")
                sample_df = pd.DataFrame(employees[:10])
                display_cols = ['id', 'name', 'role', 'billable', 'pay_type', 'hire_date', 'term_date']
                available_cols = [col for col in display_cols if col in sample_df.columns]
                st.dataframe(
                    sample_df[available_cols],
                    height=300,
                    hide_index=True
                )

                # Confirmation checkbox
                confirm_import = st.checkbox(
                    "I understand this will merge employee data (CSV is authoritative, preserving skills and allocation settings)",
                    key="confirm_employee_ref_import"
                )

                if st.button("Import Employee Reference Data", type="primary", disabled=not confirm_import):
                    try:
                        progress_bar = st.progress(0, text="Starting import...")

                        # Merge employees using upsert
                        progress_bar.progress(50, text=f"Merging {len(employees)} employees...")

                        # Preserve database-only fields
                        preserve_fields = ['skills', 'overhead_allocation', 'target_allocation', 'created_at']
                        db.upsert_employees(employees, preserve_fields=preserve_fields)

                        progress_bar.progress(100, text="Import complete!")

                        st.success(f"""
                        ✅ Employee Reference import completed successfully!
                        - Processed {len(employees)} employees
                        - Billable: {summary['billable_employees']}
                        - Active: {summary['active_employees']}
                        - Terminated: {summary['with_term_date']}
                        """)
                        st.balloons()

                        # Wait a moment before reloading
                        import time
                        time.sleep(2)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error importing employee reference data: {str(e)}")
                        st.exception(e)

            except Exception as e:
                st.error(f"Error parsing employee reference CSV: {str(e)}")
                st.exception(e)

    st.divider()

    # Project Reference CSV Import
    st.markdown("##### 📋 Import Project Reference CSV")
    st.markdown("Import project reference data from CSV file (e.g., ProjectReference.csv from Deltek).")
    with st.expander("Project Reference CSV Import", expanded=False):
        st.markdown("""**Project CSV Format:**
        - **Project**: Project ID and name combined (e.g., "101715.Y2.000.00 NIH CC OY2")
        - **POP Start Date**: Format MM/DD/YYYY
        - **POP End Date**: Format MM/DD/YYYY
        - **Total Contract Value (All Mods)**: Currency with commas
        - **Total Contract Funding (All Mods)**: Currency with commas

        **Note:** This import will update existing projects while preserving manually-entered descriptions,
        status, and project manager assignments.
        """)

        project_ref_file = st.file_uploader(
            "Upload Project Reference CSV",
            type=['csv'],
            key='project_ref_upload',
            help="Select a ProjectReference.csv file to import"
        )

        if project_ref_file is not None:
            try:
                from utils.csv_importer import ProjectReferenceCSVImporter
                import tempfile

                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
                    tmp_file.write(project_ref_file.getvalue())
                    tmp_path = tmp_file.name

                # Parse CSV
                importer = ProjectReferenceCSVImporter(tmp_path)
                projects, summary = importer.import_all()

                # Show preview
                st.markdown("##### Import Preview")
                preview_df = pd.DataFrame(projects)
                st.dataframe(preview_df.head(10), use_container_width=True)

                # Show summary statistics
                st.markdown("##### Import Summary")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Projects", summary['total_projects'])
                with col2:
                    st.metric("With Budget", summary['with_budget'])
                with col3:
                    st.metric("With Funding", summary['with_funding'])
                with col4:
                    st.metric("With Dates", summary['with_dates'])

                col5, col6 = st.columns(2)
                with col5:
                    st.metric("Total Budget", f"${summary['total_budget']:,.2f}")
                with col6:
                    st.metric("Total Funding", f"${summary['total_funding']:,.2f}")

                # Import button
                if st.button("Import Project Reference Data", type="primary", key='import_project_ref'):
                    try:
                        # Use upsert to merge with existing projects
                        # Preserve description, status, and project_manager
                        db.upsert_projects(
                            projects,
                            preserve_fields=['description', 'status', 'project_manager', 'created_at']
                        )

                        # Auto-complete projects that have passed their end_date (but only if Active or Future)
                        from datetime import datetime
                        cursor = db.conn.cursor()
                        today = datetime.now().strftime('%Y-%m-%d')

                        cursor.execute("""
                            UPDATE projects
                            SET status = 'Completed', updated_at = ?
                            WHERE end_date < ?
                            AND status IN ('Active', 'Future')
                        """, (datetime.now().isoformat(), today))
                        rows_completed = cursor.rowcount

                        # Auto-activate projects that have started (but only if currently Future)
                        cursor.execute("""
                            UPDATE projects
                            SET status = 'Active', updated_at = ?
                            WHERE start_date <= ?
                            AND status = 'Future'
                        """, (datetime.now().isoformat(), today))
                        rows_activated = cursor.rowcount

                        db.conn.commit()

                        success_msg = f"""
                        Successfully imported project reference data!

                        - Processed {len(projects)} projects
                        - With Budget: {summary['with_budget']}
                        - With Funding: {summary['with_funding']}
                        - Total Budget: ${summary['total_budget']:,.2f}
                        - Total Funding: ${summary['total_funding']:,.2f}
                        """

                        if rows_completed > 0:
                            success_msg += f"\n        - Auto-marked {rows_completed} project(s) as Completed (end_date has passed)"
                        if rows_activated > 0:
                            success_msg += f"\n        - Auto-marked {rows_activated} project(s) as Active (start_date has arrived)"

                        st.success(success_msg)
                        st.balloons()

                        # Wait a moment before reloading
                        import time
                        time.sleep(2)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error importing project reference data: {str(e)}")
                        st.exception(e)

            except Exception as e:
                st.error(f"Error parsing project reference CSV: {str(e)}")
                st.exception(e)

    st.divider()

    # Standard Import Section
    st.markdown("##### 📁 Standard CSV Import")
    data_type = st.selectbox(
        "Select Data Type to Import",
        ["Projects", "Employees", "Allocations", "Expenses", "Months"]
    )

    st.markdown("""
    **CSV Format Requirements:**
    - **Projects**: name, description, status, start_date, end_date, contract_value, budget_used, revenue_projected, revenue_actual, client, project_manager, billable
    - **Employees**: name, role, skills, hire_date, term_date, pay_type, cost_rate, annual_salary, pto_accrual, holidays, billable, overhead_allocation, target_allocation
    - **Allocations**: project_id, employee_id, allocated_fte, start_date, end_date, role, bill_rate, allocation_date, working_days, remaining_days
    - **Expenses**: project_id, category, description, amount, date, approved
    - **Months**: year, month, month_name, quarter, total_days, working_days, holidays

    **Note:** For time entries, use the Timesheet CSV Import above.
    """)

    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=['csv'],
        help="Upload a CSV file with the required format"
    )

    if uploaded_file is not None:
        # Preview the data
        try:
            df = pd.read_csv(uploaded_file)
            st.markdown("##### Data Preview")
            st.dataframe(df.head(), width='stretch')

            # Data validation
            st.markdown("##### Data Validation")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Rows", len(df))
            with col2:
                st.metric("Columns", len(df.columns))

            # Import button
            if st.button("Import Data"):
                try:
                    table_map = {
                        "Projects": "projects",
                        "Employees": "employees",
                        "Allocations": "allocations",
                        "Time Entries": "time_entries",
                        "Expenses": "expenses",
                        "Months": "months"
                    }

                    # Reset file pointer
                    uploaded_file.seek(0)

                    # Import data
                    db.import_csv(uploaded_file, table_map[data_type])
                    st.success(f"Successfully imported {len(df)} records into {data_type}")
                    st.balloons()

                    # Refresh the page
                    st.rerun()

                except Exception as e:
                    st.error(f"Error importing data: {str(e)}")
                    st.write("Please ensure your CSV has the correct column names and data types.")

        except Exception as e:
            st.error(f"Error reading file: {str(e)}")

with tab2:
    st.markdown("#### Export Data")

    export_type = st.selectbox(
        "Select Data to Export",
        ["Projects", "Employees", "Allocations", "Time Entries", "Expenses", "Months", "Complete Database"]
    )

    # Date range filter for time-based data
    if export_type in ["Time Entries", "Expenses"]:
        col1, col2 = st.columns(2)
        with col1:
            export_start = st.date_input("Start Date", key="export_start")
        with col2:
            export_end = st.date_input("End Date", key="export_end")

    if st.button("Generate Export"):
        try:
            if export_type == "Projects":
                export_df = db.get_projects()
            elif export_type == "Employees":
                export_df = db.get_employees()
            elif export_type == "Allocations":
                export_df = db.get_allocations()
            elif export_type == "Time Entries":
                export_df = db.get_time_entries(
                    start_date=export_start.strftime('%Y-%m-%d'),
                    end_date=export_end.strftime('%Y-%m-%d')
                )
            elif export_type == "Expenses":
                export_df = db.get_expenses()
            elif export_type == "Months":
                export_df = db.get_months()
            else:  # Complete Database
                # Create a multi-sheet Excel file
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    db.get_projects().to_excel(writer, sheet_name='Projects', index=False)
                    db.get_employees().to_excel(writer, sheet_name='Employees', index=False)
                    db.get_allocations().to_excel(writer, sheet_name='Allocations', index=False)
                    db.get_time_entries().to_excel(writer, sheet_name='Time Entries', index=False)
                    db.get_expenses().to_excel(writer, sheet_name='Expenses', index=False)
                    db.get_months().to_excel(writer, sheet_name='Months', index=False)

                st.download_button(
                    label="Download Complete Database (Excel)",
                    data=output.getvalue(),
                    file_name=f"database_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("Export ready for download!")
                st.stop()  # Stop execution for complete database export

            # Single table export
            if not export_df.empty:
                csv = export_df.to_csv(index=False)

                st.download_button(
                    label=f"Download {export_type} (CSV)",
                    data=csv,
                    file_name=f"{export_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

                # Preview
                st.markdown("##### Export Preview")
                st.dataframe(export_df.head(), width='stretch')
                st.info(f"Export contains {len(export_df)} records")
            else:
                st.warning(f"No data found for {export_type}")

        except Exception as e:
            st.error(f"Error generating export: {str(e)}")

with tab3:
    st.markdown("#### Data Backup & Restore")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Create Backup")
        st.write("Create a complete backup of all data")

        if st.button("Create Backup"):
            try:
                # Create backup
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    # Add metadata sheet
                    metadata = pd.DataFrame({
                        'Backup Date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                        'Projects Count': [len(db.get_projects())],
                        'Employees Count': [len(db.get_employees())],
                        'Allocations Count': [len(db.get_allocations())],
                        'Time Entries Count': [len(db.get_time_entries())],
                        'Expenses Count': [len(db.get_expenses())],
                        'Months Count': [len(db.get_months())]
                    })
                    metadata.to_excel(writer, sheet_name='Metadata', index=False)

                    # Add data sheets
                    db.get_projects().to_excel(writer, sheet_name='Projects', index=False)
                    db.get_employees().to_excel(writer, sheet_name='Employees', index=False)
                    db.get_allocations().to_excel(writer, sheet_name='Allocations', index=False)
                    db.get_time_entries().to_excel(writer, sheet_name='Time Entries', index=False)
                    db.get_expenses().to_excel(writer, sheet_name='Expenses', index=False)
                    db.get_months().to_excel(writer, sheet_name='Months', index=False)

                st.download_button(
                    label="Download Backup File",
                    data=output.getvalue(),
                    file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("Backup created successfully!")

            except Exception as e:
                st.error(f"Error creating backup: {str(e)}")

    with col2:
        st.markdown("##### Restore from Backup")
        st.warning("⚠️ Restoring will replace all current data!")

        backup_file = st.file_uploader(
            "Choose backup file",
            type=['xlsx'],
            key="backup_restore"
        )

        if backup_file is not None:
            try:
                # Read backup file
                backup_data = pd.read_excel(backup_file, sheet_name=None)

                if 'Metadata' in backup_data:
                    st.info(f"Backup created: {backup_data['Metadata']['Backup Date'].iloc[0]}")

                if st.button("Restore Backup", type="secondary"):
                    # Here you would implement the restore logic
                    # For safety, we'll just show a message
                    st.info("Restore functionality would be implemented here")
                    st.write("Backup contains:")
                    for sheet_name in backup_data.keys():
                        if sheet_name != 'Metadata':
                            st.write(f"- {sheet_name}: {len(backup_data[sheet_name])} records")

            except Exception as e:
                st.error(f"Error reading backup file: {str(e)}")

with tab4:
    st.markdown("#### Database Management")

    # Database statistics
    st.markdown("##### Database Statistics")

    col1, col2, col3 = st.columns(3)

    with col1:
        projects_count = len(db.get_projects())
        employees_count = len(db.get_employees())
        st.metric("Projects", projects_count)
        st.metric("Employees", employees_count)

    with col2:
        allocations_count = len(db.get_allocations())
        time_entries_count = len(db.get_time_entries())
        st.metric("Allocations", allocations_count)
        st.metric("Time Entries", time_entries_count)

    with col3:
        expenses_count = len(db.get_expenses())
        months_count = len(db.get_months())
        st.metric("Expenses", expenses_count)
        st.metric("Months", months_count)

        # Calculate database size (approximate)
        total_records = (projects_count + employees_count + allocations_count +
                       time_entries_count + expenses_count + months_count)
        st.metric("Total Records", total_records)

    # Data cleanup options
    st.markdown("##### Data Cleanup")

    cleanup_option = st.selectbox(
        "Select Cleanup Action",
        ["Remove Completed Projects", "Archive Old Data", "Clear Test Data", "Reset Database"]
    )

    if cleanup_option == "Remove Completed Projects":
        completed = db.get_projects()
        if not completed.empty:
            completed = completed[completed['status'] == 'Completed']
            if not completed.empty:
                st.write(f"Found {len(completed)} completed projects")
                if st.button("Remove Completed Projects", type="secondary"):
                    st.info("This would remove completed projects and associated data")
            else:
                st.info("No completed projects found")

    elif cleanup_option == "Archive Old Data":
        archive_date = st.date_input("Archive data older than")
        if st.button("Archive Old Data", type="secondary"):
            st.info(f"This would archive data older than {archive_date}")

    elif cleanup_option == "Clear Test Data":
        st.warning("This will remove all sample/test data")
        if st.button("Clear Test Data", type="secondary"):
            st.info("Test data clearing would be implemented here")

    elif cleanup_option == "Reset Database":
        st.error("⚠️ This will delete ALL data and cannot be undone!")
        confirm_text = st.text_input("Type 'RESET' to confirm")
        if confirm_text == "RESET":
            if st.button("Reset Database", type="primary"):
                st.info("Database reset would be implemented here")

    # Sample data generation
    # st.markdown("##### Generate Sample Data")
    # st.write("Add sample data for testing and demonstration")
    #
    # if st.button("Generate Sample Data"):
    #     try:
    #         from utils.sample_data import generate_sample_data
    #         generate_sample_data(db)
    #         st.success("Sample data generated successfully!")
    #         st.rerun()
    #     except Exception as e:
    #         st.error(f"Error generating sample data: {str(e)}")
