"""
CSV Timesheet Importer
Parses timesheet CSV files in the format from TimesheetData.csv
"""

import pandas as pd
from datetime import datetime
import re


class TimesheetCSVImporter:
    """
    Imports timesheet data from CSV files with format:
    Employee ID, Employee Name, Project ID, Hours Date, Entered Hours, Comments, PLC ID, PLC Desc, Billing Rate, Amount
    """

    def __init__(self, csv_path):
        """Initialize importer with CSV file path"""
        self.csv_path = csv_path
        self.df = None
        self.projects = []
        self.employees = []
        self.time_entries = []

    def parse_csv(self):
        """Parse the CSV file"""
        # Read CSV with correct column names
        self.df = pd.read_csv(
            self.csv_path,
            names=[
                'Employee ID', 'Employee Name', 'Project ID', 'Hours Date',
                'Entered Hours', 'Comments', 'PLC ID', 'PLC Desc',
                'Billing Rate', 'Amount'
            ],
            skiprows=1  # Skip header row
        )

        # Clean up data
        self.df['Employee ID'] = self.df['Employee ID'].astype(int)
        self.df['Project ID'] = self.df['Project ID'].astype(str).str.strip()
        self.df['Employee Name'] = self.df['Employee Name'].astype(str).str.strip()
        self.df['Entered Hours'] = pd.to_numeric(self.df['Entered Hours'], errors='coerce').fillna(0)

        # Convert date format from "DD-MMM-YY" to "YYYY-MM-DD"
        self.df['date_parsed'] = self.df['Hours Date'].apply(self._parse_date)

        return self

    def _parse_date(self, date_str):
        """Convert date from 'DD-MMM-YY' format to 'YYYY-MM-DD'"""
        try:
            # Parse date like "25-Dec-24"
            dt = datetime.strptime(str(date_str), '%d-%b-%y')
            return dt.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            return None

    def _parse_employee_name(self, name_str):
        """
        Parse employee name from format: "LastName, FirstName (EmployeeID)"
        Returns: (first_name, last_name)
        """
        try:
            # Remove the (EmployeeID) part
            name_clean = re.sub(r'\s*\(\d+\)', '', name_str).strip()
            # Split by comma
            if ',' in name_clean:
                parts = name_clean.split(',')
                last_name = parts[0].strip()
                first_name = parts[1].strip() if len(parts) > 1 else ''
                return first_name, last_name
            else:
                return name_clean, ''
        except Exception:
            return name_str, ''

    def extract_projects(self):
        """Extract unique projects from CSV"""
        now = datetime.now().isoformat()
        self.projects = []

        for project_id, group_df in self.df.groupby('Project ID'):
            # project_id is the group key (e.g., '202800.Y2.000.00')
            # group_df is a DataFrame with all rows for that project

            project_name = project_id

            # TODO: Add project ref lookups here...
            project = {
                'id': project_id,
                'name': project_name,
                'description': f'Imported from timesheet CSV',
                'status': 'Active',
                'start_date': None,
                'end_date': None,
                'budget_allocated': None,
                'budget_used': None,
                'revenue_projected': None,
                'revenue_actual': None,
                'client': None,
                'project_manager': None,
                'created_at': now,
                'updated_at': now
            }
            self.projects.append(project)

        return self

    def extract_employees(self):
        """Extract unique employees from CSV"""
        unique_employees = self.df.groupby('Employee ID').agg({
            'Employee Name': 'first',
            'PLC Desc': 'first'
        }).reset_index()

        now = datetime.now().isoformat()
        self.employees = []

        for _, row in unique_employees.iterrows():
            employee_id = int(row['Employee ID'])
            first_name, last_name = self._parse_employee_name(row['Employee Name'])
            full_name = f"{first_name} {last_name}".strip() or row['Employee Name']

            # Use PLC Desc as role if available
            role = None
            if pd.notna(row['PLC Desc']) and row['PLC Desc']:
                role = str(row['PLC Desc'])

            employee = {
                'id': employee_id,
                'name': full_name,
                'role': role,
                'skills': None,
                'hire_date': None,
                'created_at': now,
                'updated_at': now
            }
            self.employees.append(employee)

        return self

    def extract_time_entries(self):
        """Extract time entries from CSV"""
        now = datetime.now().isoformat()
        self.time_entries = []

        for _, row in self.df.iterrows():
            # Skip rows with invalid dates or zero hours
            if not row['date_parsed'] or row['Entered Hours'] <= 0:
                continue

            time_entry = {
                'employee_id': int(row['Employee ID']),
                'project_id': row['Project ID'],
                'date': row['date_parsed'],
                'hours': float(row['Entered Hours']),
                'description': row['Comments'] if pd.notna(row['Comments']) else None,
                'billable': 1,  # Default to billable
                'is_projected': 0,
                'created_at': now
            }
            self.time_entries.append(time_entry)

        return self

    def get_summary(self):
        """Get summary statistics of the import"""
        if self.df is None:
            return {}

        date_range = None
        if 'date_parsed' in self.df.columns:
            valid_dates = self.df[self.df['date_parsed'].notna()]['date_parsed']
            if len(valid_dates) > 0:
                date_range = (valid_dates.min(), valid_dates.max())

        return {
            'total_rows': len(self.df),
            'unique_projects': len(self.projects),
            'unique_employees': len(self.employees),
            'time_entries': len(self.time_entries),
            'date_range': date_range,
            'total_hours': self.df['Entered Hours'].sum()
        }

    def import_all(self):
        """
        Parse CSV and extract all data
        Returns: (projects, employees, time_entries, summary)
        """
        self.parse_csv()
        self.extract_projects()
        self.extract_employees()
        self.extract_time_entries()

        return self.projects, self.employees, self.time_entries, self.get_summary()