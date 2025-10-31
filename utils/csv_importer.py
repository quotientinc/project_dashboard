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
                'term_date': None,
                'pay_type': None,
                'cost_rate': None,
                'annual_salary': None,
                'pto_accrual': None,
                'holidays': None,
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

            # Determine billable status based on project ID pattern
            project_id = row['Project ID']
            is_billable = 1  # Default to billable

            # Check for non-billable project patterns
            if (project_id.startswith('FRINGE.') or
                project_id.startswith('GENADM.') or
                project_id.startswith('OVHDGS.') or
                project_id.endswith('.99') or
                not project_id[0].isdigit()):
                is_billable = 0

            time_entry = {
                'employee_id': int(row['Employee ID']),
                'project_id': row['Project ID'],
                'date': row['date_parsed'],
                'hours': float(row['Entered Hours']),
                'description': row['Comments'] if pd.notna(row['Comments']) else None,
                'billable': is_billable,
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


class EmployeeMasterCSVImporter:
    """
    Imports employee master data from CSV files with format:
    id, name, hire_date, term_date, pay_type, cost_rate, annual_salary, pto_accrual, holidays
    """

    def __init__(self, csv_path):
        """Initialize importer with CSV file path"""
        self.csv_path = csv_path
        self.df = None
        self.employees = []

    def parse_csv(self):
        """Parse the CSV file"""
        self.df = pd.read_csv(self.csv_path)

        # Validate required columns
        required_columns = ['id', 'name']
        missing_columns = [col for col in required_columns if col not in self.df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Clean up data
        self.df['id'] = self.df['id'].astype(int)
        self.df['name'] = self.df['name'].astype(str).str.strip()

        return self

    def extract_employees(self):
        """Extract employee data from CSV"""
        now = datetime.now().isoformat()
        self.employees = []

        for _, row in self.df.iterrows():
            employee = {
                'id': int(row['id']),
                'name': str(row['name']),
                'hire_date': str(row['hire_date']) if pd.notna(row.get('hire_date')) else None,
                'term_date': str(row['term_date']) if pd.notna(row.get('term_date')) else None,
                'pay_type': str(row['pay_type']) if pd.notna(row.get('pay_type')) else None,
                'cost_rate': float(row['cost_rate']) if pd.notna(row.get('cost_rate')) else None,
                'annual_salary': float(row['annual_salary']) if pd.notna(row.get('annual_salary')) else None,
                'pto_accrual': float(row['pto_accrual']) if pd.notna(row.get('pto_accrual')) else None,
                'holidays': float(row['holidays']) if pd.notna(row.get('holidays')) else None,
                'updated_at': now
            }
            self.employees.append(employee)

        return self

    def get_summary(self):
        """Get summary statistics of the import"""
        if self.df is None:
            return {}

        return {
            'total_employees': len(self.employees),
            'with_hire_date': sum(1 for e in self.employees if e['hire_date']),
            'with_term_date': sum(1 for e in self.employees if e['term_date']),
            'hourly_employees': sum(1 for e in self.employees if e['pay_type'] == 'Hourly'),
            'salaried_employees': sum(1 for e in self.employees if e['pay_type'] == 'Salary')
        }

    def import_all(self):
        """
        Parse CSV and extract all employee data
        Returns: (employees, summary)
        """
        self.parse_csv()
        self.extract_employees()

        return self.employees, self.get_summary()