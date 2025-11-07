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
        # Read CSV with correct column names, handling BOM
        self.df = pd.read_csv(
            self.csv_path,
            names=[
                'Employee ID', 'Employee Name', 'Project ID', 'Hours Date',
                'Entered Hours', 'Comments', 'PLC ID', 'PLC Desc',
                'Billing Rate', 'Amount'
            ],
            skiprows=1,  # Skip header row
            encoding='utf-8-sig'  # Handle UTF-8 BOM
        )

        # Strip whitespace from column names (in case header has extra spaces)
        self.df.columns = self.df.columns.str.strip()

        # Remove rows where Employee ID is missing (subtotals, footer rows, etc.)
        self.df = self.df.dropna(subset=['Employee ID'])

        # Clean up data
        self.df['Employee ID'] = self.df['Employee ID'].astype(int)
        self.df['Project ID'] = self.df['Project ID'].astype(str).str.strip()
        self.df['Employee Name'] = self.df['Employee Name'].astype(str).str.strip()
        self.df['Entered Hours'] = pd.to_numeric(self.df['Entered Hours'], errors='coerce').fillna(0)

        # Convert date format to "YYYY-MM-DD" (handles multiple input formats)
        self.df['date_parsed'] = self.df['Hours Date'].apply(self._parse_date)

        return self

    def _parse_date(self, date_str):
        """
        Convert date to 'YYYY-MM-DD' format.
        Handles multiple input formats:
        - 'DD-MMM-YY' (e.g., "25-Dec-24")
        - 'MMM DD, YYYY' (e.g., "Dec 25, 2024")
        """
        if pd.isna(date_str) or str(date_str).strip() == '':
            return None

        # Try multiple date formats
        formats = [
            '%d-%b-%y',      # "25-Dec-24"
            '%b %d, %Y',     # "Dec 25, 2024"
            '%m/%d/%Y',      # "12/25/2024"
            '%Y-%m-%d'       # "2024-12-25" (already correct format)
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(str(date_str).strip(), fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        # If no format worked, log error and return None
        print(f"Error parsing date '{date_str}': No matching format found")
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
                'contract_value': None,
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

            # Extract bill_rate and amount from CSV (columns have spaces in names)
            bill_rate = None
            if pd.notna(row['Billing Rate']):
                try:
                    bill_rate = float(row['Billing Rate'])
                except (ValueError, TypeError):
                    bill_rate = None

            amount = None
            if pd.notna(row['Amount']):
                try:
                    amount = float(row['Amount'])
                except (ValueError, TypeError):
                    amount = None

            time_entry = {
                'employee_id': int(row['Employee ID']),
                'project_id': row['Project ID'],
                'date': row['date_parsed'],
                'hours': float(row['Entered Hours']),
                'description': row['Comments'] if pd.notna(row['Comments']) else None,
                'billable': is_billable,
                'bill_rate': bill_rate,
                'amount': amount,
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


class EmployeeReferenceCSVImporter:
    """
    Imports employee data from EmployeeReference.csv format for merging with existing data.
    CSV columns: Employee Id, Last Name, Preferred/First Name, Billable, Division Description,
                 Employee Status Description, Hire Date, Rehire Date, Term Date,
                 Employment Type Description, Job Title, Pay Frequency Code, Pay Type Code,
                 Base Rate, Per Check Salary, Annual Salary, PTO Accrual, Holidays, Budgeted Increase
    """

    def __init__(self, csv_path):
        """Initialize importer with CSV file path"""
        self.csv_path = csv_path
        self.df = None
        self.employees = []

    def parse_csv(self):
        """Parse the CSV file"""
        # Read CSV with encoding that handles BOM
        self.df = pd.read_csv(self.csv_path, encoding='utf-8-sig')

        # Clean up column names (strip whitespace)
        self.df.columns = self.df.columns.str.strip()

        # Clean up data
        self.df['Employee Id'] = pd.to_numeric(self.df['Employee Id'], errors='coerce').fillna(0).astype(int)
        self.df['Last Name'] = self.df['Last Name'].astype(str).str.strip()
        self.df['Preferred/First Name'] = self.df['Preferred/First Name'].astype(str).str.strip()

        # Clean numeric fields
        self.df['Base Rate'] = pd.to_numeric(self.df['Base Rate'], errors='coerce').fillna(0)
        self.df['Annual Salary'] = pd.to_numeric(self.df['Annual Salary'], errors='coerce').fillna(0)
        self.df['PTO Accrual'] = pd.to_numeric(self.df['PTO Accrual'], errors='coerce').fillna(0)
        self.df['Holidays'] = pd.to_numeric(self.df['Holidays'], errors='coerce').fillna(0)

        return self

    def _parse_date(self, date_str):
        """Convert date from 'M/D/YY' format to 'YYYY-MM-DD'"""
        if pd.isna(date_str) or str(date_str).strip() == '':
            return None
        try:
            # Parse date like "1/15/19"
            dt = datetime.strptime(str(date_str).strip(), '%m/%d/%y')
            return dt.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            return None

    def _parse_billable(self, billable_str):
        """Convert billable field to 1/0"""
        if pd.isna(billable_str):
            return 0
        return 1 if str(billable_str).strip().upper() == 'YES' else 0

    def _parse_pay_type(self, pay_type_code):
        """Convert pay type code to Salary/Hourly"""
        if pd.isna(pay_type_code):
            return None
        code = str(pay_type_code).strip().upper()
        return 'Salary' if code == 'S' else 'Hourly'

    def extract_employees(self):
        """Extract employee data from CSV and map to database format"""
        now = datetime.now().isoformat()
        self.employees = []

        for _, row in self.df.iterrows():
            # Skip rows with invalid employee ID
            if row['Employee Id'] <= 0:
                continue

            # Construct name from first and last
            first_name = str(row['Preferred/First Name']).strip()
            last_name = str(row['Last Name']).strip()
            full_name = f"{first_name} {last_name}".strip()

            # Parse dates
            hire_date = self._parse_date(row.get('Hire Date'))
            term_date = self._parse_date(row.get('Term Date'))

            # Parse billable
            billable = self._parse_billable(row.get('Billable'))

            # Parse pay type
            pay_type = self._parse_pay_type(row.get('Pay Type Code'))

            # Get cost rate and annual salary
            cost_rate = float(row['Base Rate']) if row['Base Rate'] > 0 else None
            annual_salary = float(row['Annual Salary']) if row['Annual Salary'] > 0 else None

            # Convert PTO accrual from days to hours (multiply by 8)
            pto_accrual = float(row['PTO Accrual']) * 8 if row['PTO Accrual'] > 0 else None

            # Get holidays
            holidays = float(row['Holidays']) if row['Holidays'] > 0 else None

            # Get role from Job Title
            role = str(row['Job Title']).strip() if pd.notna(row.get('Job Title')) else None

            employee = {
                'id': int(row['Employee Id']),
                'name': full_name,
                'role': role,
                'hire_date': hire_date,
                'term_date': term_date,
                'pay_type': pay_type,
                'cost_rate': cost_rate,
                'annual_salary': annual_salary,
                'pto_accrual': pto_accrual,
                'holidays': holidays,
                'billable': billable,
                'updated_at': now
            }
            self.employees.append(employee)

        return self

    def get_summary(self):
        """Get summary statistics of the import"""
        if self.df is None:
            return {}

        billable_count = sum(1 for e in self.employees if e['billable'] == 1)
        salary_count = sum(1 for e in self.employees if e['pay_type'] == 'Salary')
        hourly_count = sum(1 for e in self.employees if e['pay_type'] == 'Hourly')
        with_hire_date = sum(1 for e in self.employees if e['hire_date'])
        with_term_date = sum(1 for e in self.employees if e['term_date'])

        return {
            'total_employees': len(self.employees),
            'billable_employees': billable_count,
            'non_billable_employees': len(self.employees) - billable_count,
            'salary_employees': salary_count,
            'hourly_employees': hourly_count,
            'with_hire_date': with_hire_date,
            'with_term_date': with_term_date,
            'active_employees': len(self.employees) - with_term_date
        }

    def import_all(self):
        """
        Parse CSV and extract all employee data
        Returns: (employees, summary)
        """
        self.parse_csv()
        self.extract_employees()

        return self.employees, self.get_summary()


class ProjectReferenceCSVImporter:
    """
    Imports project data from ProjectReference.csv format for merging with existing data.
    CSV columns:
      - Required: Project, POP Start Date, POP End Date, Total Contract Value (All Mods)
      - Optional: is_parent (0 or 1), parent_id (project ID string)

    The "Project" column contains both project ID and name (e.g., "101715.Y2.000.00 NIH CC OY2")
    which is split on the first space.

    Hierarchy fields:
      - is_parent: 1 for parent (3rd level) projects, 0 for leaf (4th level) projects (default: 0)
      - parent_id: ID of parent project for leaf projects (default: None)
    """

    def __init__(self, csv_path):
        """Initialize importer with CSV file path"""
        self.csv_path = csv_path
        self.df = None
        self.projects = []

    def parse_csv(self):
        """Parse the CSV file"""
        # Read CSV with encoding that handles BOM
        self.df = pd.read_csv(self.csv_path, encoding='utf-8-sig')

        # Clean up column names (strip whitespace)
        self.df.columns = self.df.columns.str.strip()

        # Clean up data
        self.df['Project'] = self.df['Project'].astype(str).str.strip()

        return self

    def _parse_date(self, date_str):
        """Convert date from 'MM/DD/YYYY' format to 'YYYY-MM-DD', handling typos like 01//01/2024"""
        if pd.isna(date_str) or str(date_str).strip() == '':
            return None
        try:
            # Clean up double slashes and extra spaces
            cleaned = str(date_str).strip().replace('//', '/')
            # Parse date like "01/01/2024"
            dt = datetime.strptime(cleaned, '%m/%d/%Y')
            return dt.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            return None

    def _parse_currency(self, currency_str):
        """Convert currency string to float, handling commas and quotes"""
        if pd.isna(currency_str):
            return None
        try:
            # Remove commas and convert to float
            cleaned = str(currency_str).strip().replace(',', '')
            value = float(cleaned)
            return value if value > 0 else None
        except Exception as e:
            print(f"Error parsing currency '{currency_str}': {e}")
            return None

    def _split_project_column(self, project_str):
        """
        Split project column into ID and name.
        Format: "101715.Y2.000.00 NIH CC OY2"
        Returns: (id, name)
        """
        try:
            parts = project_str.split(' ', 1)
            project_id = parts[0].strip()
            project_name = parts[1].strip() if len(parts) > 1 else project_id
            return project_id, project_name
        except Exception:
            return project_str, project_str

    def extract_projects(self):
        """Extract project data from CSV and map to database format"""
        now = datetime.now().isoformat()
        self.projects = []

        for _, row in self.df.iterrows():
            # Split Project column into id and name
            project_id, project_name = self._split_project_column(row['Project'])

            # Skip if no valid project ID
            if not project_id:
                continue

            # Parse dates
            start_date = self._parse_date(row.get('POP Start Date'))
            end_date = self._parse_date(row.get('POP End Date'))

            # Parse currency values
            contract_value = self._parse_currency(row.get('Total\nContract Value\n(All Mods)'))

            # Default all projects to billable
            billable = 1

            # Determine status based on start_date and end_date
            status = 'Active'
            if start_date and end_date:
                try:
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                    today = datetime.now()

                    if start_date_obj > today:
                        status = 'Future'  # Project hasn't started yet
                    elif end_date_obj < today:
                        status = 'Completed'  # Project has ended
                    else:
                        status = 'Active'  # Project is currently running
                except (ValueError, TypeError):
                    # If date parsing fails, default to Active
                    status = 'Active'

            # Optional hierarchy fields (default to leaf project if not specified)
            is_parent = 0
            parent_id = None

            if 'is_parent' in row and pd.notna(row['is_parent']):
                try:
                    is_parent = int(row['is_parent'])
                except (ValueError, TypeError):
                    is_parent = 0

            if 'parent_id' in row and pd.notna(row['parent_id']):
                parent_id = str(row['parent_id']).strip()
                if parent_id == '':
                    parent_id = None

            project = {
                'id': project_id,
                'name': project_name,
                'start_date': start_date,
                'end_date': end_date,
                'status': status,
                'contract_value': contract_value,
                'billable': billable,
                'is_parent': is_parent,
                'parent_id': parent_id,
                'updated_at': now
            }
            self.projects.append(project)

        return self

    def get_summary(self):
        """Get summary statistics of the import"""
        if self.df is None:
            return {}

        with_budget = sum(1 for p in self.projects if p['contract_value'])
        with_dates = sum(1 for p in self.projects if p['start_date'] and p['end_date'])

        total_budget = sum(p['contract_value'] for p in self.projects if p['contract_value'])

        return {
            'total_projects': len(self.projects),
            'with_budget': with_budget,
            'with_dates': with_dates,
            'total_budget': total_budget
        }

    def import_all(self):
        """
        Parse CSV and extract all project data
        Returns: (projects, summary)
        """
        self.parse_csv()
        self.extract_projects()

        return self.projects, self.get_summary()


class AllocationCSVImporter:
    """
    Imports allocation data from CSV files with format:
    employee_id, project_id, allocation_date, bill_rate, allocated_fte, role (optional)

    The allocation_date should be in YYYY-MM format (e.g., "2024-12", "2025-01")
    """

    def __init__(self, csv_path, db=None):
        """Initialize importer with CSV file path and optional database instance"""
        self.csv_path = csv_path
        self.db = db
        self.df = None
        self.allocations = []
        self.validation_errors = []

    def parse_csv(self):
        """Parse the CSV file"""
        # Read CSV with encoding that handles BOM
        self.df = pd.read_csv(self.csv_path, encoding='utf-8-sig')

        # Clean up column names (strip whitespace)
        self.df.columns = self.df.columns.str.strip()

        # Validate required columns
        required_columns = ['employee_id', 'project_id', 'allocation_date', 'allocated_fte']
        missing_columns = [col for col in required_columns if col not in self.df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Clean up data
        self.df['employee_id'] = pd.to_numeric(self.df['employee_id'], errors='coerce').fillna(0).astype(int)
        self.df['project_id'] = self.df['project_id'].astype(str).str.strip()
        self.df['allocated_fte'] = pd.to_numeric(self.df['allocated_fte'], errors='coerce').fillna(0.0)

        # Parse bill_rate (optional field)
        if 'bill_rate' in self.df.columns:
            self.df['bill_rate'] = pd.to_numeric(self.df['bill_rate'], errors='coerce')

        # Handle optional role column
        if 'role' not in self.df.columns:
            self.df['role'] = None

        # Parse allocation_date to ensure YYYY-MM format
        self.df['allocation_date_parsed'] = self.df['allocation_date'].apply(self._parse_allocation_date)

        return self

    def _parse_allocation_date(self, date_str):
        """
        Convert date to 'YYYY-MM' format
        Handles various input formats: YYYY-MM, YYYY-M, M/YYYY, MM/YYYY, etc.
        """
        if pd.isna(date_str) or str(date_str).strip() == '':
            return None

        try:
            date_str = str(date_str).strip()

            # If already in YYYY-MM format, validate and return
            if re.match(r'^\d{4}-\d{2}$', date_str):
                # Validate it's a valid date
                datetime.strptime(date_str + '-01', '%Y-%m-%d')
                return date_str

            # If in YYYY-M format (single digit month)
            if re.match(r'^\d{4}-\d{1}$', date_str):
                year, month = date_str.split('-')
                return f"{year}-{month.zfill(2)}"

            # If in M/YYYY or MM/YYYY format
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 2:
                    month, year = parts
                    return f"{year}-{month.zfill(2)}"

            # Try to parse as full date and extract year-month
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%Y-%m')

        except Exception as e:
            print(f"Error parsing allocation_date '{date_str}': {e}")
            return None

    def extract_allocations(self):
        """Extract allocation data from CSV and map to database format"""
        now = datetime.now().isoformat()
        self.allocations = []
        self.validation_errors = []

        for idx, row in self.df.iterrows():
            # Skip rows with invalid data
            if row['employee_id'] <= 0:
                self.validation_errors.append(f"Row {idx + 2}: Invalid employee_id")
                continue

            if not row['project_id']:
                self.validation_errors.append(f"Row {idx + 2}: Missing project_id")
                continue

            if not row['allocation_date_parsed']:
                self.validation_errors.append(f"Row {idx + 2}: Invalid allocation_date")
                continue

            if row['allocated_fte'] < 0:
                self.validation_errors.append(f"Row {idx + 2}: Invalid allocated_fte (must be >= 0)")
                continue

            # Validate project is leaf node (not a parent project)
            if self.db:
                try:
                    self.db.validate_allocation_project(row['project_id'])
                except ValueError as e:
                    self.validation_errors.append(f"Row {idx + 2}: {str(e)}")
                    continue

            # Build allocation record
            allocation = {
                'employee_id': int(row['employee_id']),
                'project_id': str(row['project_id']),
                'allocation_date': row['allocation_date_parsed'],
                'allocated_fte': float(row['allocated_fte']),
                'created_at': now,
                'updated_at': now
            }

            # Add optional bill_rate
            if 'bill_rate' in row and pd.notna(row['bill_rate']) and row['bill_rate'] > 0:
                allocation['bill_rate'] = float(row['bill_rate'])
            else:
                allocation['bill_rate'] = None

            # Add optional role
            if 'role' in row and pd.notna(row['role']) and str(row['role']).strip():
                allocation['role'] = str(row['role']).strip()
            else:
                allocation['role'] = None

            self.allocations.append(allocation)

        return self

    def get_summary(self):
        """Get summary statistics of the import"""
        if self.df is None:
            return {}

        unique_employees = len(set(a['employee_id'] for a in self.allocations))
        unique_projects = len(set(a['project_id'] for a in self.allocations))

        # Get date range
        date_range = None
        if self.allocations:
            dates = [a['allocation_date'] for a in self.allocations]
            date_range = (min(dates), max(dates))

        # Count allocations with bill_rate
        with_bill_rate = sum(1 for a in self.allocations if a.get('bill_rate'))

        # Count allocations with role
        with_role = sum(1 for a in self.allocations if a.get('role'))

        return {
            'total_allocations': len(self.allocations),
            'unique_employees': unique_employees,
            'unique_projects': unique_projects,
            'date_range': date_range,
            'with_bill_rate': with_bill_rate,
            'with_role': with_role,
            'validation_errors': self.validation_errors
        }

    def import_all(self):
        """
        Parse CSV and extract all allocation data
        Returns: (allocations, summary)
        """
        self.parse_csv()
        self.extract_allocations()

        return self.allocations, self.get_summary()


class MonthsCSVImporter:
    """
    Imports month reference data from CSV files with format:
    year, month, month_name, total_days, working_days, holidays, quarter

    This data is essential for capacity planning and working day calculations.
    """

    def __init__(self, csv_path):
        """Initialize importer with CSV file path"""
        self.csv_path = csv_path
        self.df = None
        self.months = []
        self.validation_errors = []

    def parse_csv(self):
        """Parse the CSV file"""
        # Read CSV with encoding that handles BOM
        self.df = pd.read_csv(self.csv_path, encoding='utf-8-sig')

        # Clean up column names (strip whitespace)
        self.df.columns = self.df.columns.str.strip()

        # Validate required columns
        required_columns = ['year', 'month', 'month_name', 'total_days', 'working_days', 'holidays', 'quarter']
        missing_columns = [col for col in required_columns if col not in self.df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Clean up data
        self.df['year'] = pd.to_numeric(self.df['year'], errors='coerce').fillna(0).astype(int)
        self.df['month'] = pd.to_numeric(self.df['month'], errors='coerce').fillna(0).astype(int)
        self.df['total_days'] = pd.to_numeric(self.df['total_days'], errors='coerce').fillna(0).astype(int)
        self.df['working_days'] = pd.to_numeric(self.df['working_days'], errors='coerce').fillna(0).astype(int)
        self.df['holidays'] = pd.to_numeric(self.df['holidays'], errors='coerce').fillna(0).astype(int)
        self.df['month_name'] = self.df['month_name'].astype(str).str.strip()
        self.df['quarter'] = self.df['quarter'].astype(str).str.strip()

        return self

    def extract_months(self):
        """Extract month data from CSV and map to database format"""
        now = datetime.now().isoformat()
        self.months = []
        self.validation_errors = []

        for idx, row in self.df.iterrows():
            # Validate data
            if row['year'] < 2000 or row['year'] > 2100:
                self.validation_errors.append(f"Row {idx + 2}: Invalid year {row['year']}")
                continue

            if row['month'] < 1 or row['month'] > 12:
                self.validation_errors.append(f"Row {idx + 2}: Invalid month {row['month']}")
                continue

            if row['total_days'] < 28 or row['total_days'] > 31:
                self.validation_errors.append(f"Row {idx + 2}: Invalid total_days {row['total_days']}")
                continue

            if row['working_days'] < 0 or row['working_days'] > 31:
                self.validation_errors.append(f"Row {idx + 2}: Invalid working_days {row['working_days']}")
                continue

            if row['holidays'] < 0 or row['holidays'] > 10:
                self.validation_errors.append(f"Row {idx + 2}: Invalid holidays {row['holidays']}")
                continue

            # Build month record
            month = {
                'year': int(row['year']),
                'month': int(row['month']),
                'month_name': str(row['month_name']),
                'total_days': int(row['total_days']),
                'working_days': int(row['working_days']),
                'holidays': int(row['holidays']),
                'quarter': str(row['quarter']),
                'created_at': now,
                'updated_at': now
            }
            self.months.append(month)

        return self

    def get_summary(self):
        """Get summary statistics of the import"""
        if self.df is None:
            return {}

        unique_years = len(set(m['year'] for m in self.months))
        unique_quarters = len(set(m['quarter'] for m in self.months))

        # Get year range
        year_range = None
        if self.months:
            years = [m['year'] for m in self.months]
            year_range = (min(years), max(years))

        # Calculate totals
        total_working_days = sum(m['working_days'] for m in self.months)
        total_holidays = sum(m['holidays'] for m in self.months)

        return {
            'total_months': len(self.months),
            'unique_years': unique_years,
            'unique_quarters': unique_quarters,
            'year_range': year_range,
            'total_working_days': total_working_days,
            'total_holidays': total_holidays,
            'validation_errors': self.validation_errors
        }

    def import_all(self):
        """
        Parse CSV and extract all month data
        Returns: (months, summary)
        """
        self.parse_csv()
        self.extract_months()

        return self.months, self.get_summary()