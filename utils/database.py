import sqlite3
import pandas as pd
from pathlib import Path
import json
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    def __init__(self, db_path='data/project_dashboard.db'):
        """Initialize database connection and create tables if they don't exist"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)
        self.create_tables()
        self.migrate_employee_allocation_fields()

    def create_tables(self):
        """Create all necessary tables"""
        cursor = self.conn.cursor()

        # Projects table - id is now TEXT to store CSV Project IDs like "202800.Y2.000.00"
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT,
                start_date TEXT,
                end_date TEXT,
                budget_allocated REAL,
                budget_used REAL,
                revenue_projected REAL,
                revenue_actual REAL,
                client TEXT,
                project_manager TEXT,
                billable INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # Employees table - id is now INTEGER (not autoincrement) to store CSV Employee IDs like 100482
        # Removed: email, department, hourly_rate, fte, utilization (moved to allocations or removed)
        # Added: term_date, pay_type, cost_rate, annual_salary, pto_accrual, holidays (HR fields)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                skills TEXT,
                hire_date TEXT,
                term_date TEXT,
                pay_type TEXT,
                cost_rate REAL,
                annual_salary REAL,
                pto_accrual REAL,
                holidays REAL,
                billable INTEGER DEFAULT 0,
                overhead_allocation REAL DEFAULT 0,
                target_allocation REAL DEFAULT 0.3,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # Project allocations table
        # Simplified schema: removed allocation_percent (use allocated_fte only), removed hours_projected/hours_actual
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                employee_id INTEGER,
                allocated_fte REAL,
                start_date TEXT,
                end_date TEXT,
                role TEXT,
                project_rate REAL,
                employee_rate REAL,
                allocation_date TEXT,
                working_days INTEGER,
                remaining_days INTEGER,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id),
                FOREIGN KEY (employee_id) REFERENCES employees (id)
            )
        ''')

        # Time tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS time_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                project_id TEXT,
                date TEXT,
                hours REAL,
                description TEXT,
                billable INTEGER,
                is_projected INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (employee_id) REFERENCES employees (id),
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        ''')

        # Expenses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                category TEXT,
                description TEXT,
                amount REAL,
                date TEXT,
                approved INTEGER,
                created_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        ''')

        # Months table - tracks working days and holidays per month
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS months (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                month_name TEXT NOT NULL,
                quarter TEXT NOT NULL,
                total_days INTEGER NOT NULL,
                working_days INTEGER NOT NULL,
                holidays INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(year, month)
            )
        ''')

        self.conn.commit()

    def migrate_schema_for_csv_import(self):
        """
        Migrate database schema to support CSV timesheet import.
        Changes:
        - projects.id: INTEGER AUTOINCREMENT -> TEXT (to store CSV Project IDs)
        - employees.id: INTEGER AUTOINCREMENT -> INTEGER (to store CSV Employee IDs)
        - Updates foreign keys in allocations, time_entries, and expenses

        WARNING: This will delete all data except allocations (which may have orphaned references)
        """
        cursor = self.conn.cursor()

        # Check if migration is needed
        cursor.execute("PRAGMA table_info(projects)")
        columns = cursor.fetchall()
        project_id_type = [col for col in columns if col[1] == 'id'][0][2]  # Get type of id column

        if project_id_type == 'TEXT':
            print("Schema already migrated for CSV import")
            return

        print("Starting schema migration for CSV import...")

        # Step 1: Save allocations data
        cursor.execute("SELECT * FROM allocations")
        allocations_backup = cursor.fetchall()
        cursor.execute("PRAGMA table_info(allocations)")
        allocations_columns = [col[1] for col in cursor.fetchall()]

        # Step 2: Drop all tables
        cursor.execute("DROP TABLE IF EXISTS time_entries")
        cursor.execute("DROP TABLE IF EXISTS expenses")
        cursor.execute("DROP TABLE IF EXISTS allocations")
        cursor.execute("DROP TABLE IF EXISTS projects")
        cursor.execute("DROP TABLE IF EXISTS employees")

        # Step 3: Recreate tables with new schema
        self.create_tables()

        # Step 4: Restore allocations (may have orphaned references until CSV import)
        if allocations_backup:
            print(f"Restoring {len(allocations_backup)} allocations (note: references may be orphaned until CSV import)")
            placeholders = ','.join('?' * len(allocations_columns))
            query = f"INSERT INTO allocations ({','.join(allocations_columns)}) VALUES ({placeholders})"
            cursor.executemany(query, allocations_backup)

        self.conn.commit()
        print("Schema migration complete. Allocations preserved, all other data cleared.")
        print("Note: Allocation foreign keys may be orphaned until CSV data is imported.")

    def migrate_employee_allocation_fields(self):
        """
        Add billable, overhead_allocation, and target_allocation columns to employees table.
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Check if columns exist
        cursor.execute("PRAGMA table_info(employees)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add billable column
        if 'billable' not in columns:
            cursor.execute('ALTER TABLE employees ADD COLUMN billable INTEGER DEFAULT 0')
            print("Added 'billable' column to employees table")

        # Add overhead_allocation column
        if 'overhead_allocation' not in columns:
            cursor.execute('ALTER TABLE employees ADD COLUMN overhead_allocation REAL DEFAULT 0')
            print("Added 'overhead_allocation' column to employees table")

        # Add target_allocation column
        if 'target_allocation' not in columns:
            cursor.execute('ALTER TABLE employees ADD COLUMN target_allocation REAL DEFAULT 0.3')
            print("Added 'target_allocation' column to employees table")

        self.conn.commit()

    def is_empty(self):
        """Check if database is empty"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM projects")
        project_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM employees")
        employee_count = cursor.fetchone()[0]
        return project_count == 0 and employee_count == 0

    # Project methods
    def get_projects(self, filters=None):
        """Get all projects or filtered projects"""
        query = "SELECT * FROM projects"
        params = []

        if filters:
            conditions = []
            if 'status' in filters and filters['status']:
                placeholders = ','.join('?' * len(filters['status']))
                conditions.append(f"status IN ({placeholders})")
                params.extend(filters['status'])
            if 'start_date' in filters:
                conditions.append("start_date >= ?")
                params.append(filters['start_date'])
            if 'end_date' in filters:
                conditions.append("end_date <= ?")
                params.append(filters['end_date'])

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        return pd.read_sql_query(query, self.conn, params=params)

    def add_project(self, project_data):
        """Add a new project"""
        project_data['created_at'] = datetime.now().isoformat()
        project_data['updated_at'] = datetime.now().isoformat()

        columns = list(project_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO projects ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(project_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def update_project(self, project_id, updates):
        """Update a project"""
        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ','.join([f"{k}=?" for k in updates.keys()])
        query = f"UPDATE projects SET {set_clause} WHERE id=?"

        # Convert numpy types to Python types
        project_id = int(project_id) if hasattr(project_id, 'item') else project_id

        cursor = self.conn.cursor()
        params = list(updates.values()) + [project_id]

        # Debug logging
        logger.info(f"update_project called with project_id={project_id}")
        logger.info(f"SQL: {query}")
        logger.info(f"Params: {params}")

        cursor.execute(query, params)
        rows_affected = cursor.rowcount

        logger.info(f"Rows affected: {rows_affected}")

        if rows_affected == 0:
            raise ValueError(f"No project found with id={project_id}. Update failed.")

        self.conn.commit()
        logger.info("Commit successful")
        return rows_affected

    # Employee methods
    def get_employees(self, filters=None):
        """Get all employees or filtered employees"""
        query = "SELECT * FROM employees"
        params = []

        # Note: department filter removed as department column no longer exists
        # filters parameter kept for future extensibility

        return pd.read_sql_query(query, self.conn, params=params)

    def add_employee(self, employee_data):
        """Add a new employee"""
        employee_data['created_at'] = datetime.now().isoformat()
        employee_data['updated_at'] = datetime.now().isoformat()

        columns = list(employee_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO employees ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(employee_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def update_employee(self, employee_id, updates):
        """Update an employee"""
        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ','.join([f"{k}=?" for k in updates.keys()])
        query = f"UPDATE employees SET {set_clause} WHERE id=?"

        # Convert numpy types to Python types
        employee_id = int(employee_id) if hasattr(employee_id, 'item') else employee_id

        cursor = self.conn.cursor()
        cursor.execute(query, list(updates.values()) + [employee_id])
        self.conn.commit()

    # Allocation methods
    def get_allocations(self, project_id=None, employee_id=None):
        """Get allocations filtered by project or employee"""
        query = """
            SELECT a.*, p.name as project_name, e.name as employee_name,
                   COALESCE(a.project_rate, a.employee_rate) as effective_rate
            FROM allocations a
            JOIN projects p ON a.project_id = p.id
            JOIN employees e ON a.employee_id = e.id
        """
        params = []
        conditions = []

        if project_id:
            conditions.append("a.project_id = ?")
            # Convert numpy types to Python types (project_id is TEXT)
            params.append(str(project_id) if hasattr(project_id, 'item') else project_id)
        if employee_id:
            conditions.append("a.employee_id = ?")
            # Convert numpy types to Python types
            params.append(int(employee_id) if hasattr(employee_id, 'item') else employee_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        return pd.read_sql_query(query, self.conn, params=params)

    def add_allocation(self, allocation_data):
        """Add a new allocation"""
        allocation_data['created_at'] = datetime.now().isoformat()
        allocation_data['updated_at'] = datetime.now().isoformat()

        # Convert numpy types to Python types
        for key, value in allocation_data.items():
            if hasattr(value, 'item'):  # Check if it's a numpy type
                allocation_data[key] = value.item()

        columns = list(allocation_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO allocations ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(allocation_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def delete_allocation(self, allocation_id):
        """Delete an allocation"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM allocations WHERE id = ?", (allocation_id,))
        self.conn.commit()

    def update_allocation(self, allocation_id, updates):
        """Update an allocation"""
        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ','.join([f"{k}=?" for k in updates.keys()])
        query = f"UPDATE allocations SET {set_clause} WHERE id=?"

        # Convert numpy types to Python types
        allocation_id = int(allocation_id) if hasattr(allocation_id, 'item') else allocation_id

        cursor = self.conn.cursor()
        cursor.execute(query, list(updates.values()) + [allocation_id])
        self.conn.commit()

    # Time tracking methods
    def get_time_entries(self, start_date=None, end_date=None, employee_id=None, project_id=None):
        """Get time entries with filters"""
        query = """
            SELECT t.*, e.name as employee_name, p.name as project_name,
                   COALESCE(
                       (SELECT a.project_rate
                        FROM allocations a
                        WHERE a.project_id = t.project_id
                        AND a.employee_id = t.employee_id
                        LIMIT 1),
                       (SELECT a.employee_rate
                        FROM allocations a
                        WHERE a.project_id = t.project_id
                        AND a.employee_id = t.employee_id
                        LIMIT 1)
                   ) as hourly_rate
            FROM time_entries t
            JOIN employees e ON t.employee_id = e.id
            JOIN projects p ON t.project_id = p.id
        """
        params = []
        conditions = []

        if start_date:
            conditions.append("t.date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("t.date <= ?")
            params.append(end_date)
        if employee_id:
            conditions.append("t.employee_id = ?")
            # Convert numpy types to Python types
            params.append(int(employee_id) if hasattr(employee_id, 'item') else employee_id)
        if project_id:
            conditions.append("t.project_id = ?")
            # Convert numpy types to Python types (project_id is TEXT)
            params.append(str(project_id) if hasattr(project_id, 'item') else project_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        return pd.read_sql_query(query, self.conn, params=params)

    def add_time_entry(self, time_data):
        """Add a time entry"""
        time_data['created_at'] = datetime.now().isoformat()

        columns = list(time_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO time_entries ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(time_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def get_time_entries_by_month(self, project_id, start_date=None, end_date=None):
        """Get time entries grouped by employee and month for a project"""
        query = """
            SELECT
                t.employee_id,
                e.name as employee_name,
                e.role,
                COALESCE(
                    (SELECT a.project_rate
                     FROM allocations a
                     WHERE a.project_id = t.project_id
                     AND a.employee_id = t.employee_id
                     LIMIT 1),
                    (SELECT a.employee_rate
                     FROM allocations a
                     WHERE a.project_id = t.project_id
                     AND a.employee_id = t.employee_id
                     LIMIT 1)
                ) as rate,
                strftime('%Y-%m', t.date) as month,
                SUM(t.hours) as actual_hours
            FROM time_entries t
            JOIN employees e ON t.employee_id = e.id
            WHERE t.project_id = ?
        """
        # Convert numpy types to Python types (project_id is TEXT)
        params = [str(project_id) if hasattr(project_id, 'item') else project_id]

        if start_date:
            query += " AND t.date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND t.date <= ?"
            params.append(end_date)

        query += " GROUP BY t.employee_id, e.name, e.role, rate, month ORDER BY e.name, month"

        return pd.read_sql_query(query, self.conn, params=params)

    # Expense methods
    def get_expenses(self, project_id=None):
        """Get expenses"""
        query = """
            SELECT e.*, p.name as project_name
            FROM expenses e
            JOIN projects p ON e.project_id = p.id
        """
        params = []

        if project_id:
            query += " WHERE e.project_id = ?"
            # Convert numpy types to Python types (project_id is TEXT)
            params.append(str(project_id) if hasattr(project_id, 'item') else project_id)

        return pd.read_sql_query(query, self.conn, params=params)

    def add_expense(self, expense_data):
        """Add an expense"""
        expense_data['created_at'] = datetime.now().isoformat()

        columns = list(expense_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO expenses ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(expense_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    # Bulk insert methods for CSV import
    def bulk_insert_projects(self, projects_data):
        """Bulk insert projects from list of dicts"""
        if not projects_data:
            return

        cursor = self.conn.cursor()
        columns = list(projects_data[0].keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT OR IGNORE INTO projects ({','.join(columns)}) VALUES ({placeholders})"

        values = [tuple(p[col] for col in columns) for p in projects_data]
        cursor.executemany(query, values)
        self.conn.commit()

    def bulk_insert_employees(self, employees_data):
        """Bulk insert employees from list of dicts"""
        if not employees_data:
            return

        cursor = self.conn.cursor()
        columns = list(employees_data[0].keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT OR IGNORE INTO employees ({','.join(columns)}) VALUES ({placeholders})"

        values = [tuple(e[col] for col in columns) for e in employees_data]
        cursor.executemany(query, values)
        self.conn.commit()

    def upsert_employees(self, employees_data, preserve_fields=None):
        """
        Upsert (insert or update) employees from list of dicts.
        Matches on employee id. If employee exists, updates with new data.
        If employee doesn't exist, inserts new record.

        Args:
            employees_data: List of employee dicts with 'id' field
            preserve_fields: List of field names to preserve from existing records (not overwrite)
                           Common fields: ['skills', 'overhead_allocation', 'target_allocation', 'created_at']
        """
        if not employees_data:
            return

        preserve_fields = preserve_fields or []
        cursor = self.conn.cursor()

        for employee in employees_data:
            employee_id = employee['id']

            # Check if employee exists
            cursor.execute("SELECT * FROM employees WHERE id = ?", (employee_id,))
            existing = cursor.fetchone()

            if existing:
                # Employee exists - UPDATE
                # Get column names from existing record
                existing_columns = [desc[0] for desc in cursor.description]
                existing_data = dict(zip(existing_columns, existing))

                # Build update data, preserving specified fields
                update_data = employee.copy()
                for field in preserve_fields:
                    if field in existing_data and existing_data[field] is not None:
                        # Preserve existing value
                        update_data[field] = existing_data[field]

                # Update timestamp
                update_data['updated_at'] = datetime.now().isoformat()

                # Build UPDATE query
                update_fields = [k for k in update_data.keys() if k != 'id']
                set_clause = ', '.join([f"{field} = ?" for field in update_fields])
                values = [update_data[field] for field in update_fields] + [employee_id]

                query = f"UPDATE employees SET {set_clause} WHERE id = ?"
                cursor.execute(query, values)
            else:
                # Employee doesn't exist - INSERT
                employee['created_at'] = datetime.now().isoformat()
                employee['updated_at'] = datetime.now().isoformat()

                # Apply smart defaults for billable employees
                if employee.get('billable') == 1:
                    # Set overhead_allocation to 0 for billable employees
                    if 'overhead_allocation' not in employee:
                        employee['overhead_allocation'] = 0.0

                    # Set target_allocation based on pay_type
                    if 'target_allocation' not in employee:
                        pay_type = employee.get('pay_type')
                        if pay_type == 'Salary':
                            employee['target_allocation'] = 1.0
                        elif pay_type == 'Hourly':
                            employee['target_allocation'] = 0.3
                        else:
                            employee['target_allocation'] = 0.3  # Default

                columns = list(employee.keys())
                placeholders = ','.join('?' * len(columns))
                query = f"INSERT INTO employees ({','.join(columns)}) VALUES ({placeholders})"

                values = [employee[col] for col in columns]
                cursor.execute(query, values)

        self.conn.commit()

    def upsert_projects(self, projects_data, preserve_fields=None):
        """
        Upsert (insert or update) projects from list of dicts.
        Matches on project id. If project exists, updates with new data.
        If project doesn't exist, inserts new record.

        Args:
            projects_data: List of project dicts with 'id' field
            preserve_fields: List of field names to preserve from existing records (not overwrite)
                           Common fields: ['description', 'status', 'project_manager', 'created_at']
        """
        if not projects_data:
            return

        preserve_fields = preserve_fields or []
        cursor = self.conn.cursor()

        for project in projects_data:
            project_id = project['id']

            # Check if project exists
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            existing = cursor.fetchone()

            if existing:
                # Project exists - UPDATE
                # Get column names from existing record
                existing_columns = [desc[0] for desc in cursor.description]
                existing_data = dict(zip(existing_columns, existing))

                # Build update data, preserving specified fields
                update_data = project.copy()
                for field in preserve_fields:
                    if field in existing_data and existing_data[field] is not None:
                        # Preserve existing value
                        update_data[field] = existing_data[field]

                # Update timestamp
                update_data['updated_at'] = datetime.now().isoformat()

                # Build UPDATE query
                update_fields = [k for k in update_data.keys() if k != 'id']
                set_clause = ', '.join([f"{field} = ?" for field in update_fields])
                values = [update_data[field] for field in update_fields] + [project_id]

                query = f"UPDATE projects SET {set_clause} WHERE id = ?"
                cursor.execute(query, values)
            else:
                # Project doesn't exist - INSERT
                project['created_at'] = datetime.now().isoformat()
                project['updated_at'] = datetime.now().isoformat()

                columns = list(project.keys())
                placeholders = ','.join('?' * len(columns))
                query = f"INSERT INTO projects ({','.join(columns)}) VALUES ({placeholders})"

                values = [project[col] for col in columns]
                cursor.execute(query, values)

        self.conn.commit()

    def bulk_insert_time_entries(self, time_entries_data):
        """Bulk insert time entries from list of dicts"""
        if not time_entries_data:
            return

        cursor = self.conn.cursor()
        columns = list(time_entries_data[0].keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO time_entries ({','.join(columns)}) VALUES ({placeholders})"

        values = [tuple(t[col] for col in columns) for t in time_entries_data]
        cursor.executemany(query, values)
        self.conn.commit()
    # Import/Export methods
    def import_csv(self, file, table_name):
        """Import data from CSV file"""
        df = pd.read_csv(file)
        df.to_sql(table_name, self.conn, if_exists='append', index=False)
        self.conn.commit()

    def export_to_csv(self, table_name, file_path):
        """Export table to CSV"""
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", self.conn)
        df.to_csv(file_path, index=False)
        return df

    # Months methods
    def get_months(self, year=None):
        """Get all months or filtered by year, sorted by year DESC, month ASC"""
        query = "SELECT * FROM months"
        params = []

        if year:
            query += " WHERE year = ?"
            params.append(year)

        query += " ORDER BY year DESC, month ASC"
        return pd.read_sql_query(query, self.conn, params=params)

    def add_month(self, month_data):
        """Add a new month record"""
        month_data['created_at'] = datetime.now().isoformat()
        month_data['updated_at'] = datetime.now().isoformat()

        columns = list(month_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO months ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(month_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def update_month(self, month_id, updates):
        """Update a month record"""
        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ','.join([f"{k}=?" for k in updates.keys()])
        query = f"UPDATE months SET {set_clause} WHERE id=?"

        cursor = self.conn.cursor()
        cursor.execute(query, list(updates.values()) + [month_id])
        self.conn.commit()
        return cursor.rowcount

    def delete_month(self, month_id):
        """Delete a month record"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM months WHERE id = ?", (month_id,))
        self.conn.commit()

    def bulk_upsert_months(self, months_data):
        """Bulk insert or update months from list of dicts"""
        if not months_data:
            return

        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        for month_data in months_data:
            month_data['updated_at'] = now
            if 'created_at' not in month_data:
                month_data['created_at'] = now

            columns = list(month_data.keys())
            placeholders = ','.join('?' * len(columns))

            # Use INSERT OR REPLACE to handle duplicates (based on UNIQUE constraint on year, month)
            query = f"INSERT OR REPLACE INTO months ({','.join(columns)}) VALUES ({placeholders})"
            cursor.execute(query, list(month_data.values()))

        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()
