import streamlit as st
import pandas as pd
from datetime import datetime
import io
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager

st.markdown("### 📊 Data Management")

tab1, tab2, tab3, tab4 = st.tabs(["Import Data", "Export Data", "Data Backup", "Database Management"])

with tab1:
    st.markdown("#### Import Data")
    
    data_type = st.selectbox(
        "Select Data Type to Import",
        ["Projects", "Employees", "Allocations", "Time Entries", "Expenses"]
    )
    
    st.markdown("""
    **CSV Format Requirements:**
    - **Projects**: name, description, status, start_date, end_date, budget_allocated, budget_used, revenue_projected, revenue_actual, client, project_manager
    - **Employees**: name, email, department, role, hourly_rate, fte, utilization, skills, hire_date
    - **Allocations**: project_id, employee_id, allocation_percent, hours_projected, hours_actual, start_date, end_date, role
    - **Time Entries**: employee_id, project_id, date, hours, description, billable
    - **Expenses**: project_id, category, description, amount, date, approved
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
                        "Expenses": "expenses"
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
        ["Projects", "Employees", "Allocations", "Time Entries", "Expenses", "Complete Database"]
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
            else:  # Complete Database
                # Create a multi-sheet Excel file
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    db.get_projects().to_excel(writer, sheet_name='Projects', index=False)
                    db.get_employees().to_excel(writer, sheet_name='Employees', index=False)
                    db.get_allocations().to_excel(writer, sheet_name='Allocations', index=False)
                    db.get_time_entries().to_excel(writer, sheet_name='Time Entries', index=False)
                    db.get_expenses().to_excel(writer, sheet_name='Expenses', index=False)
                
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
                        'Expenses Count': [len(db.get_expenses())]
                    })
                    metadata.to_excel(writer, sheet_name='Metadata', index=False)
                    
                    # Add data sheets
                    db.get_projects().to_excel(writer, sheet_name='Projects', index=False)
                    db.get_employees().to_excel(writer, sheet_name='Employees', index=False)
                    db.get_allocations().to_excel(writer, sheet_name='Allocations', index=False)
                    db.get_time_entries().to_excel(writer, sheet_name='Time Entries', index=False)
                    db.get_expenses().to_excel(writer, sheet_name='Expenses', index=False)
                
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
        st.metric("Expenses", expenses_count)
        
        # Calculate database size (approximate)
        total_records = (projects_count + employees_count + allocations_count + 
                       time_entries_count + expenses_count)
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
    st.markdown("##### Generate Sample Data")
    st.write("Add sample data for testing and demonstration")
    
    if st.button("Generate Sample Data"):
        try:
            from utils.sample_data import generate_sample_data
            generate_sample_data(db)
            st.success("Sample data generated successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error generating sample data: {str(e)}")
