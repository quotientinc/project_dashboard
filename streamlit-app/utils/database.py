import sqlite3
import pandas as pd
from pathlib import Path
import json
from datetime import datetime
import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    def __init__(self, db_path=str(Path(__file__).resolve().parent.parent.parent / 'data' / 'project_dashboard.db')):
        """Initialize database connection and create tables if they don't exist"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)

        # Performance PRAGMAs
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA cache_size = -64000;")
        self.conn.execute("PRAGMA temp_store = MEMORY;")
        self.conn.execute("PRAGMA mmap_size = 268435456;")

        self.create_tables()
        self.migrate_employee_allocation_fields()
        self.migrate_allocation_bill_rate()
        self.migrate_time_entries_bill_rate()
        self.migrate_projects_schema_cleanup()
        self.migrate_contract_value_split()
        self.migrate_remove_deprecated_allocation_columns()
        self.migrate_add_allocation_unique_constraint()
        self.create_indexes()
        self.migrate_add_project_phases_table()

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
                quoted_value REAL,
                awarded_value REAL,
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
                bill_rate REAL,
                allocation_date TEXT,
                working_days INTEGER,
                remaining_days INTEGER,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id),
                FOREIGN KEY (employee_id) REFERENCES employees (id),
                UNIQUE (employee_id, project_id, allocation_date)
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
                bill_rate REAL,
                amount REAL,
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

    def migrate_allocation_bill_rate(self):
        """
        Migrate allocations table from employee_rate to bill_rate.
        - Adds bill_rate column if it doesn't exist
        - Copies data from employee_rate to bill_rate if employee_rate exists
        - This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Check if columns exist
        cursor.execute("PRAGMA table_info(allocations)")
        columns = [col[1] for col in cursor.fetchall()]

        # If employee_rate exists and bill_rate doesn't, this is an old database
        if 'employee_rate' in columns and 'bill_rate' not in columns:
            print("Migrating allocations: employee_rate -> bill_rate...")

            # Add bill_rate column
            cursor.execute('ALTER TABLE allocations ADD COLUMN bill_rate REAL')
            print("Added 'bill_rate' column to allocations table")

            # Copy data from employee_rate to bill_rate
            cursor.execute('UPDATE allocations SET bill_rate = employee_rate')
            rows_updated = cursor.rowcount
            print(f"Copied employee_rate to bill_rate for {rows_updated} allocations")

            self.conn.commit()
            print("✅ Migration complete: employee_rate -> bill_rate")

            # Note: We don't drop the old columns yet for safety
            # They can be dropped in a future cleanup migration
        elif 'bill_rate' in columns:
            # Migration already done
            pass
        else:
            # New database - bill_rate column created by create_tables
            pass

    def migrate_time_entries_bill_rate(self):
        """
        Migrate time_entries table to add bill_rate and amount columns, remove is_projected.
        - Adds bill_rate REAL column if it doesn't exist
        - Adds amount REAL column if it doesn't exist
        - Removes is_projected column if it exists
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Check if columns exist
        cursor.execute("PRAGMA table_info(time_entries)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add bill_rate column
        if 'bill_rate' not in columns:
            cursor.execute('ALTER TABLE time_entries ADD COLUMN bill_rate REAL')
            print("Added 'bill_rate' column to time_entries table")

        # Add amount column
        if 'amount' not in columns:
            cursor.execute('ALTER TABLE time_entries ADD COLUMN amount REAL')
            print("Added 'amount' column to time_entries table")

        # Remove is_projected column if it exists
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        if 'is_projected' in columns:
            print("Removing 'is_projected' column from time_entries table...")

            # Get all data
            cursor.execute("SELECT id, employee_id, project_id, date, hours, description, billable, bill_rate, amount, created_at FROM time_entries")
            data = cursor.fetchall()

            # Drop and recreate table
            cursor.execute("DROP TABLE time_entries")
            cursor.execute('''
                CREATE TABLE time_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER,
                    project_id TEXT,
                    date TEXT,
                    hours REAL,
                    description TEXT,
                    billable INTEGER,
                    bill_rate REAL,
                    amount REAL,
                    created_at TEXT,
                    FOREIGN KEY (employee_id) REFERENCES employees (id),
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                )
            ''')

            # Restore data
            if data:
                cursor.executemany(
                    "INSERT INTO time_entries (id, employee_id, project_id, date, hours, description, billable, bill_rate, amount, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    data
                )
                print(f"Restored {len(data)} time entries")

            print("✅ Removed 'is_projected' column from time_entries table")

        self.conn.commit()

    def migrate_projects_schema_cleanup(self):
        """
        Clean up projects table schema:
        - Rename budget_allocated -> contract_value
        - Remove budget_used (always calculated from time_entries)
        - Remove revenue_projected
        - Remove revenue_actual
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Check current schema
        cursor.execute("PRAGMA table_info(projects)")
        columns = [col[1] for col in cursor.fetchall()]

        # Check if migration already completed
        if 'contract_value' in columns and 'budget_allocated' not in columns:
            print("Projects schema already cleaned up")
            return

        # Check if migration is needed
        needs_migration = False
        if 'budget_allocated' in columns:
            needs_migration = True
        if 'budget_used' in columns:
            needs_migration = True
        if 'revenue_projected' in columns:
            needs_migration = True
        if 'revenue_actual' in columns:
            needs_migration = True

        if not needs_migration:
            print("Projects schema does not need cleanup migration")
            return

        print("Starting projects schema cleanup migration...")

        # SQLite doesn't support ALTER TABLE DROP COLUMN or RENAME COLUMN easily
        # We need to recreate the table

        # Step 1: Get all current data
        cursor.execute("SELECT * FROM projects")
        projects_data = cursor.fetchall()
        cursor.execute("PRAGMA table_info(projects)")
        old_columns = cursor.fetchall()
        old_column_names = [col[1] for col in old_columns]

        # Step 2: Create column mapping (old -> new)
        column_mapping = {}
        for old_col in old_column_names:
            if old_col == 'budget_allocated':
                column_mapping[old_col] = 'contract_value'
            elif old_col in ['budget_used', 'revenue_projected', 'revenue_actual']:
                column_mapping[old_col] = None  # Drop these columns
            else:
                column_mapping[old_col] = old_col  # Keep as-is

        # Step 3: Build new column list (excluding dropped columns)
        new_column_names = [column_mapping[old_col] for old_col in old_column_names if column_mapping[old_col] is not None]

        # Step 4: Transform data for new schema
        transformed_data = []
        for row in projects_data:
            new_row = []
            for i, old_col in enumerate(old_column_names):
                new_col = column_mapping[old_col]
                if new_col is not None:  # Only include if not dropped
                    new_row.append(row[i])
            transformed_data.append(tuple(new_row))

        # Step 5: Drop old table
        cursor.execute("DROP TABLE projects")

        # Step 6: Create new table with updated schema
        cursor.execute('''
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT,
                start_date TEXT,
                end_date TEXT,
                contract_value REAL,
                client TEXT,
                project_manager TEXT,
                billable INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # Step 7: Restore data
        if transformed_data:
            placeholders = ','.join('?' * len(new_column_names))
            query = f"INSERT INTO projects ({','.join(new_column_names)}) VALUES ({placeholders})"
            cursor.executemany(query, transformed_data)
            print(f"Migrated {len(transformed_data)} projects to new schema")

        self.conn.commit()
        print("✅ Projects schema cleanup complete:")
        print("   - Renamed: budget_allocated -> contract_value")
        print("   - Removed: budget_used, revenue_projected, revenue_actual")

    def migrate_contract_value_split(self):
        """
        Split contract_value into quoted_value and awarded_value.
        - quoted_value: What the project was bid/quoted for
        - awarded_value: What has actually been funded/awarded
        - For existing projects, both values are set to the current contract_value
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Check current schema
        cursor.execute("PRAGMA table_info(projects)")
        columns = [col[1] for col in cursor.fetchall()]

        # Check if migration already completed
        if 'quoted_value' in columns and 'awarded_value' in columns and 'contract_value' not in columns:
            print("Contract value split migration already completed")
            return

        # Check if we need to migrate from contract_value
        if 'contract_value' not in columns:
            print("Contract value split migration not needed (new database)")
            return

        print("Starting contract value split migration...")
        print("  - Splitting contract_value into quoted_value and awarded_value")

        # Step 1: Get all current data
        cursor.execute("SELECT * FROM projects")
        projects_data = cursor.fetchall()
        cursor.execute("PRAGMA table_info(projects)")
        old_columns = cursor.fetchall()
        old_column_names = [col[1] for col in old_columns]

        # Step 2: Create column mapping (old -> new)
        # contract_value will be copied to BOTH new fields
        column_mapping = {}
        for old_col in old_column_names:
            if old_col == 'contract_value':
                column_mapping[old_col] = ['quoted_value', 'awarded_value']  # Split into two
            else:
                column_mapping[old_col] = [old_col]  # Keep as-is

        # Step 3: Build new column list
        new_column_names = []
        for old_col in old_column_names:
            new_cols = column_mapping[old_col]
            new_column_names.extend(new_cols)

        # Step 4: Transform data for new schema
        transformed_data = []
        for row in projects_data:
            new_row = []
            for i, old_col in enumerate(old_column_names):
                new_cols = column_mapping[old_col]
                if old_col == 'contract_value':
                    # Copy contract_value to both quoted_value and awarded_value
                    new_row.append(row[i])  # quoted_value
                    new_row.append(row[i])  # awarded_value
                else:
                    new_row.append(row[i])
            transformed_data.append(tuple(new_row))

        # Step 5: Drop old table
        cursor.execute("DROP TABLE projects")

        # Step 6: Create new table with updated schema
        cursor.execute('''
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT,
                start_date TEXT,
                end_date TEXT,
                quoted_value REAL,
                awarded_value REAL,
                client TEXT,
                project_manager TEXT,
                billable INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # Step 7: Restore data
        if transformed_data:
            placeholders = ','.join('?' * len(new_column_names))
            query = f"INSERT INTO projects ({','.join(new_column_names)}) VALUES ({placeholders})"
            cursor.executemany(query, transformed_data)
            print(f"  - Migrated {len(transformed_data)} projects to new schema")
            print(f"  - Both quoted_value and awarded_value set to original contract_value")

        self.conn.commit()
        print("✅ Contract value split migration complete")
        print("   - Added: quoted_value (original bid/quote)")
        print("   - Added: awarded_value (actual funding)")
        print("   - Removed: contract_value")

    def migrate_remove_deprecated_allocation_columns(self):
        """
        Remove deprecated columns from allocations table:
        - start_date (stored but never queried)
        - end_date (stored but never queried)
        - working_days (never populated)
        - remaining_days (never populated)

        With monthly allocation_date as source of truth, these are redundant.
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Check current schema
        cursor.execute("PRAGMA table_info(allocations)")
        columns = [col[1] for col in cursor.fetchall()]

        # Check if migration already completed
        if 'start_date' not in columns and 'end_date' not in columns:
            print("Deprecated allocation columns already removed")
            return

        print("Starting allocation table cleanup migration...")
        print("  - Removing: start_date, end_date, working_days, remaining_days")

        # Step 1: Get all current data
        cursor.execute("SELECT * FROM allocations")
        allocations_data = cursor.fetchall()
        cursor.execute("PRAGMA table_info(allocations)")
        old_columns = cursor.fetchall()
        old_column_names = [col[1] for col in old_columns]

        # Step 2: Define new schema (only keep essential columns)
        new_columns = [
            'id', 'project_id', 'employee_id', 'allocated_fte',
            'allocation_date', 'role', 'bill_rate', 'created_at', 'updated_at'
        ]

        # Step 3: Extract data for columns we're keeping
        col_indexes = []
        for new_col in new_columns:
            if new_col in old_column_names:
                col_indexes.append(old_column_names.index(new_col))
            else:
                col_indexes.append(None)  # Column doesn't exist yet

        new_data = []
        for row in allocations_data:
            new_row = []
            for idx in col_indexes:
                if idx is not None:
                    new_row.append(row[idx])
                else:
                    new_row.append(None)
            new_data.append(tuple(new_row))

        # Step 4: Drop old table
        cursor.execute("DROP TABLE allocations")

        # Step 5: Create new table with clean schema
        cursor.execute('''
            CREATE TABLE allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                employee_id INTEGER,
                allocated_fte REAL,
                allocation_date TEXT,
                role TEXT,
                bill_rate REAL,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id),
                FOREIGN KEY (employee_id) REFERENCES employees (id)
            )
        ''')

        # Step 6: Restore data
        if new_data:
            placeholders = ','.join('?' * len(new_columns))
            query = f"INSERT INTO allocations ({','.join(new_columns)}) VALUES ({placeholders})"
            cursor.executemany(query, new_data)
            print(f"  - Migrated {len(new_data)} allocation records")

        self.conn.commit()
        print("✅ Allocation table cleanup complete")
        print("   - Removed: start_date, end_date, working_days, remaining_days")
        print("   - Kept: allocation_date (source of truth)")

    def migrate_add_allocation_unique_constraint(self):
        """
        Add UNIQUE constraint on (employee_id, project_id, allocation_date) to the allocations table.
        This prevents duplicate allocation entries when data is re-imported.
        Also normalizes allocation_date values from YYYY-MM-DD to YYYY-MM format
        and deduplicates existing rows (keeping the highest id for each unique combo).
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        # Idempotency check: see if the CREATE TABLE DDL already has a UNIQUE constraint
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='allocations'")
        result = cursor.fetchone()
        if result is None:
            # Table doesn't exist yet; create_tables() will handle it
            return
        create_sql = result[0]
        if 'UNIQUE' in create_sql.upper():
            print("Allocation unique constraint already present")
            return

        print("Starting allocation unique constraint migration...")

        # Step 1: Read all existing data and column info
        cursor.execute("PRAGMA table_info(allocations)")
        columns = cursor.fetchall()
        col_names = [col[1] for col in columns]

        cursor.execute("SELECT * FROM allocations")
        all_rows = cursor.fetchall()

        # Step 2: Normalize allocation_date — truncate any YYYY-MM-DD values to YYYY-MM
        allocation_date_idx = col_names.index('allocation_date')
        normalized_rows = []
        for row in all_rows:
            row_list = list(row)
            raw_date = row_list[allocation_date_idx]
            if raw_date and len(str(raw_date)) > 7:
                row_list[allocation_date_idx] = str(raw_date)[:7]
            normalized_rows.append(row_list)

        # Step 3: Deduplicate — group by (employee_id, project_id, allocation_date), keep highest id
        id_idx = col_names.index('id')
        emp_idx = col_names.index('employee_id')
        proj_idx = col_names.index('project_id')

        seen = {}
        for row in normalized_rows:
            key = (row[emp_idx], row[proj_idx], row[allocation_date_idx])
            if key not in seen or row[id_idx] > seen[key][id_idx]:
                seen[key] = row

        deduped_rows = list(seen.values())
        duplicates_removed = len(normalized_rows) - len(deduped_rows)
        print(f"  - Found {len(normalized_rows)} rows, removing {duplicates_removed} duplicate(s)")

        # Step 4: Drop old table, recreate with UNIQUE constraint
        cursor.execute("DROP TABLE allocations")
        cursor.execute('''
            CREATE TABLE allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                employee_id INTEGER,
                allocated_fte REAL,
                allocation_date TEXT,
                role TEXT,
                bill_rate REAL,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id),
                FOREIGN KEY (employee_id) REFERENCES employees (id),
                UNIQUE (employee_id, project_id, allocation_date)
            )
        ''')

        # Step 5: Restore deduplicated data
        if deduped_rows:
            placeholders = ','.join('?' * len(col_names))
            query = f"INSERT INTO allocations ({','.join(col_names)}) VALUES ({placeholders})"
            cursor.executemany(query, [tuple(r) for r in deduped_rows])
            print(f"  - Migrated {len(deduped_rows)} allocation records")

        self.conn.commit()
        print("Allocation unique constraint migration complete")
        print("   - Added: UNIQUE(employee_id, project_id, allocation_date)")
        print(f"   - Removed {duplicates_removed} duplicate(s) from {len(normalized_rows)} rows")
        logger.info(f"Allocation unique constraint migration complete. Removed {duplicates_removed} duplicate(s) from {len(normalized_rows)} rows.")

    def create_indexes(self):
        """
        Create performance indexes on frequently queried columns.
        This method is idempotent - safe to run multiple times.
        Indexes significantly improve query performance, especially on large tables.
        """
        cursor = self.conn.cursor()

        def index_exists(index_name):
            """Check if an index already exists"""
            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type = 'index' AND name = ?
            """, (index_name,))
            return cursor.fetchone()[0] > 0

        # Define all indexes to create
        indexes = [
            # Critical indexes on time_entries (largest table)
            ('idx_time_entries_employee_id',
             'CREATE INDEX idx_time_entries_employee_id ON time_entries(employee_id)'),
            ('idx_time_entries_project_id',
             'CREATE INDEX idx_time_entries_project_id ON time_entries(project_id)'),
            ('idx_time_entries_date',
             'CREATE INDEX idx_time_entries_date ON time_entries(date)'),
            ('idx_time_entries_project_date',
             'CREATE INDEX idx_time_entries_project_date ON time_entries(project_id, date)'),
            ('idx_time_entries_employee_date',
             'CREATE INDEX idx_time_entries_employee_date ON time_entries(employee_id, date)'),

            # High-value indexes on allocations
            ('idx_allocations_employee_id',
             'CREATE INDEX idx_allocations_employee_id ON allocations(employee_id)'),
            ('idx_allocations_project_id',
             'CREATE INDEX idx_allocations_project_id ON allocations(project_id)'),
            ('idx_allocations_allocation_date',
             'CREATE INDEX idx_allocations_allocation_date ON allocations(allocation_date)'),

            # Optional indexes for filtering
            ('idx_employees_billable',
             'CREATE INDEX idx_employees_billable ON employees(billable)'),
            ('idx_time_entries_billable',
             'CREATE INDEX idx_time_entries_billable ON time_entries(billable)'),

            # Project phases index
            ('idx_project_phases_project_id',
             'CREATE INDEX idx_project_phases_project_id ON project_phases(project_id)'),
        ]

        created_count = 0
        for index_name, create_sql in indexes:
            if not index_exists(index_name):
                try:
                    cursor.execute(create_sql)
                    created_count += 1
                except Exception as e:
                    logger.warning(f"Failed to create index {index_name}: {str(e)}")

        if created_count > 0:
            self.conn.commit()
            # Update statistics for query planner
            cursor.execute("ANALYZE")
            self.conn.commit()
            logger.info(f"Created {created_count} database indexes for improved performance")

    def migrate_add_project_phases_table(self):
        """
        Create the project_phases table if it does not exist.
        Tracks phases/milestones within a project lifecycle.
        This migration is safe to run multiple times.
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                phase_name TEXT NOT NULL,
                phase_type TEXT,
                start_date TEXT,
                end_date TEXT,
                predecessors TEXT,
                risk TEXT,
                status TEXT,
                completion_pct REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        ''')

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
    @st.cache_data(ttl=60, show_spinner=False)
    def get_projects(_self, filters=None):
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

        df = pd.read_sql_query(query, _self.conn, params=params)

        # Calculate budget_used from time_entries for all projects in bulk (avoid N+1 query)
        if not df.empty:
            # Get all time entries once
            all_time_entries = _self.get_time_entries()

            if not all_time_entries.empty:
                # Calculate cost for each entry
                def calculate_entry_cost(row):
                    if pd.notna(row.get('amount')) and row['amount'] != 0:
                        return row['amount']
                    elif pd.notna(row.get('bill_rate')) and pd.notna(row.get('hours')):
                        return row['hours'] * row['bill_rate']
                    else:
                        return 0.0

                all_time_entries['cost'] = all_time_entries.apply(calculate_entry_cost, axis=1)

                # Group by project_id and sum costs
                budget_by_project = all_time_entries.groupby('project_id')['cost'].sum().reset_index()
                budget_by_project.columns = ['id', 'budget_used']

                # Merge with projects dataframe
                df = df.merge(budget_by_project, on='id', how='left')

                # Fill NaN with 0.0 for projects with no time entries
                df['budget_used'] = df['budget_used'].fillna(0.0)
            else:
                # No time entries at all
                df['budget_used'] = 0.0

        return df

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

    # Project Phase methods
    @st.cache_data(ttl=60, show_spinner=False)
    def get_project_phases(_self, project_id=None):
        """Get all project phases or filtered by project_id, ordered by start_date"""
        query = "SELECT * FROM project_phases"
        params = []

        if project_id is not None:
            query += " WHERE project_id = ?"
            # Convert numpy types to Python types (project_id is TEXT)
            params.append(str(project_id) if hasattr(project_id, 'item') else project_id)

        query += " ORDER BY start_date"
        return pd.read_sql_query(query, _self.conn, params=params)

    def add_project_phase(self, phase_data):
        """Add a new project phase"""
        phase_data['created_at'] = datetime.now().isoformat()
        phase_data['updated_at'] = datetime.now().isoformat()

        # Convert numpy types to Python types
        for key, value in phase_data.items():
            if hasattr(value, 'item'):
                phase_data[key] = value.item()

        columns = list(phase_data.keys())
        placeholders = ','.join('?' * len(columns))
        query = f"INSERT INTO project_phases ({','.join(columns)}) VALUES ({placeholders})"

        cursor = self.conn.cursor()
        cursor.execute(query, list(phase_data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def update_project_phase(self, phase_id, updates):
        """Update a project phase"""
        updates['updated_at'] = datetime.now().isoformat()

        # Convert numpy types to Python types
        for key, value in updates.items():
            if hasattr(value, 'item'):
                updates[key] = value.item()

        set_clause = ','.join([f"{k}=?" for k in updates.keys()])
        query = f"UPDATE project_phases SET {set_clause} WHERE id=?"

        # Convert numpy types to Python types for the phase_id
        phase_id = int(phase_id) if hasattr(phase_id, 'item') else phase_id

        cursor = self.conn.cursor()
        cursor.execute(query, list(updates.values()) + [phase_id])
        self.conn.commit()
        return cursor.rowcount

    def delete_project_phase(self, phase_id):
        """Delete a project phase"""
        # Convert numpy types to Python types
        phase_id = int(phase_id) if hasattr(phase_id, 'item') else phase_id

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM project_phases WHERE id = ?", (phase_id,))
        self.conn.commit()

    def bulk_insert_project_phases(self, phases_list, project_id):
        """
        Bulk insert project phases for a given project.
        First deletes all existing phases for the project_id,
        then inserts all phases from phases_list.
        Wrapped in an explicit transaction for atomicity.

        Args:
            phases_list: List of dicts with phase data
            project_id: The project ID to associate phases with
        """
        if not phases_list:
            return

        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        # Convert numpy types to Python types for project_id (TEXT)
        project_id = str(project_id) if hasattr(project_id, 'item') else project_id

        cursor.execute("BEGIN")
        try:
            # Delete existing phases for this project
            cursor.execute("DELETE FROM project_phases WHERE project_id = ?", (project_id,))

            # Insert all phases
            for phase in phases_list:
                phase['project_id'] = project_id
                phase['created_at'] = now
                phase['updated_at'] = now

                # Convert numpy types to Python types
                for key, value in phase.items():
                    if hasattr(value, 'item'):
                        phase[key] = value.item()

                columns = list(phase.keys())
                placeholders = ','.join('?' * len(columns))
                query = f"INSERT INTO project_phases ({','.join(columns)}) VALUES ({placeholders})"
                cursor.execute(query, list(phase.values()))

            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise

    # Employee methods
    @st.cache_data(ttl=300, show_spinner=False)
    def get_employees(_self, filters=None):
        """Get all employees or filtered employees"""
        query = "SELECT * FROM employees"
        params = []

        # Note: department filter removed as department column no longer exists
        # filters parameter kept for future extensibility

        return pd.read_sql_query(query, _self.conn, params=params)

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
    @st.cache_data(ttl=300, show_spinner=False)
    def get_allocations(_self, project_id=None, employee_id=None):
        """Get allocations filtered by project or employee"""
        query = """
            SELECT a.*, p.name as project_name, e.name as employee_name,
                   a.bill_rate as effective_rate
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

        return pd.read_sql_query(query, _self.conn, params=params)

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
        query = f"""INSERT INTO allocations ({','.join(columns)}) VALUES ({placeholders})
            ON CONFLICT(employee_id, project_id, allocation_date) DO UPDATE SET
                allocated_fte=excluded.allocated_fte,
                bill_rate=excluded.bill_rate,
                role=excluded.role,
                updated_at=excluded.updated_at"""

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

    def get_existing_allocations_date_range(self):
        """Get the date range of existing allocations in the database"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT MIN(allocation_date) as min_date, MAX(allocation_date) as max_date
            FROM allocations
        """)
        result = cursor.fetchone()
        if result and result[0] and result[1]:
            return (result[0], result[1])
        return None

    def delete_allocations_by_date_range(self, start_date, end_date):
        """
        Delete allocations within a specific date range (inclusive).
        Used for incremental imports to clear overlapping data.
        Returns the number of allocations deleted.

        WARNING: This deletes ALL allocations across ALL projects in the date range.
        Use delete_allocations_by_scope() for safer, project-specific deletion.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM allocations
            WHERE allocation_date >= ? AND allocation_date <= ?
        """, (start_date, end_date))
        self.conn.commit()
        return cursor.rowcount

    def delete_allocations_by_scope(self, allocations_data):
        """
        Delete allocations only for the specific (employee_id, project_id, allocation_date)
        combinations present in the incoming data.

        This is the safe method for incremental imports - it only removes allocations
        that will be replaced by the import, leaving other projects untouched.

        Args:
            allocations_data: List of dicts with 'employee_id', 'project_id', 'allocation_date'

        Returns:
            Number of allocations deleted
        """
        if not allocations_data:
            return 0

        cursor = self.conn.cursor()

        # Extract unique (employee_id, project_id, allocation_date) tuples
        scopes = set()
        for alloc in allocations_data:
            scopes.add((
                alloc['employee_id'],
                alloc['project_id'],
                alloc['allocation_date']
            ))

        # Delete in batch using OR conditions
        # For better performance with large datasets, we could use a temp table,
        # but for typical allocation imports (hundreds to thousands), this is fine
        deleted_count = 0

        for employee_id, project_id, allocation_date in scopes:
            cursor.execute("""
                DELETE FROM allocations
                WHERE employee_id = ?
                  AND project_id = ?
                  AND allocation_date = ?
            """, (employee_id, project_id, allocation_date))
            deleted_count += cursor.rowcount

        self.conn.commit()
        return deleted_count

    def bulk_insert_allocations(self, allocations_data):
        """
        Bulk insert allocations from list of dicts.
        Uses ON CONFLICT upsert to handle duplicates - updates existing rows while preserving id and created_at.
        """
        if not allocations_data:
            return

        cursor = self.conn.cursor()

        # Get column names from first record
        columns = list(allocations_data[0].keys())
        placeholders = ','.join('?' * len(columns))

        # Use ON CONFLICT upsert to handle duplicates
        query = f"""INSERT INTO allocations ({','.join(columns)}) VALUES ({placeholders})
            ON CONFLICT(employee_id, project_id, allocation_date) DO UPDATE SET
                allocated_fte=excluded.allocated_fte,
                bill_rate=excluded.bill_rate,
                role=excluded.role,
                updated_at=excluded.updated_at"""

        # Convert data to list of tuples
        values = []
        for allocation in allocations_data:
            row_values = []
            for col in columns:
                value = allocation[col]
                # Convert numpy types to Python types
                if hasattr(value, 'item'):
                    value = value.item()
                row_values.append(value)
            values.append(tuple(row_values))

        cursor.executemany(query, values)
        self.conn.commit()

    def validate_allocation_foreign_keys(self, allocations_data):
        """
        Validate that all employee_id and project_id references exist in the database.
        Returns a tuple of (is_valid, error_messages)
        """
        cursor = self.conn.cursor()
        errors = []

        # Get unique employee and project IDs
        employee_ids = set(a['employee_id'] for a in allocations_data)
        project_ids = set(a['project_id'] for a in allocations_data)

        # Check employees exist
        for employee_id in employee_ids:
            cursor.execute("SELECT COUNT(*) FROM employees WHERE id = ?", (employee_id,))
            if cursor.fetchone()[0] == 0:
                errors.append(f"Employee ID {employee_id} does not exist in database")

        # Check projects exist
        for project_id in project_ids:
            cursor.execute("SELECT COUNT(*) FROM projects WHERE id = ?", (project_id,))
            if cursor.fetchone()[0] == 0:
                errors.append(f"Project ID {project_id} does not exist in database")

        return (len(errors) == 0, errors)

    # Time tracking methods
    @st.cache_data(ttl=30, show_spinner=False)
    def get_time_entries(_self, start_date=None, end_date=None, employee_id=None, project_id=None):
        """Get time entries with filters"""
        query = """
            SELECT t.*, e.name as employee_name, p.name as project_name,
                   (SELECT a.bill_rate
                    FROM allocations a
                    WHERE a.project_id = t.project_id
                    AND a.employee_id = t.employee_id
                    LIMIT 1) as hourly_rate
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

        return pd.read_sql_query(query, _self.conn, params=params)

    def get_existing_time_entries_date_range(self):
        """
        Get the current date range of time_entries in the database.

        Returns:
            Tuple (min_date, max_date) in 'YYYY-MM-DD' format, or None if no entries exist
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT MIN(date), MAX(date) FROM time_entries")
        result = cursor.fetchone()

        if result and result[0] and result[1]:
            return (result[0], result[1])
        return None

    def delete_time_entries_by_date_range(self, start_date: str, end_date: str):
        """
        Delete time_entries within a specific date range (inclusive).

        Args:
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format

        Returns:
            Number of rows deleted
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM time_entries WHERE date >= ? AND date <= ?",
            (start_date, end_date)
        )
        rows_deleted = cursor.rowcount
        self.conn.commit()
        return rows_deleted

    def calculate_budget_used(self, project_id: str) -> float:
        """
        Calculate total budget used from time_entries for a project.
        Returns sum of (hours × bill_rate) or amount for all time entries.
        Returns 0.0 if no time entries exist.
        """
        time_entries = self.get_time_entries(project_id=project_id)
        if time_entries.empty:
            return 0.0

        # Calculate cost for each entry
        def calculate_entry_cost(row):
            if pd.notna(row.get('amount')) and row['amount'] != 0:
                return row['amount']
            elif pd.notna(row.get('bill_rate')) and pd.notna(row.get('hours')):
                return row['hours'] * row['bill_rate']
            else:
                return 0.0

        time_entries['cost'] = time_entries.apply(calculate_entry_cost, axis=1)
        return float(time_entries['cost'].sum())

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
                t.bill_rate as rate,
                strftime('%Y-%m', t.date) as month,
                SUM(t.hours) as actual_hours,
                SUM(t.amount) as actual_revenue
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

        query += " GROUP BY t.employee_id, e.name, e.role, month ORDER BY e.name, month"

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
    @st.cache_data(ttl=3600, show_spinner=False)
    def get_months(_self, year=None):
        """Get all months or filtered by year, sorted by year DESC, month ASC"""
        query = "SELECT * FROM months"
        params = []

        if year:
            query += " WHERE year = ?"
            params.append(year)

        query += " ORDER BY year DESC, month ASC"
        return pd.read_sql_query(query, _self.conn, params=params)

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
