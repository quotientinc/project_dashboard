import random
from datetime import datetime, timedelta
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)


def generate_sample_data(db_manager):
    """Generate sample data for the dashboard"""

    # Calculate current dates for realistic project timelines
    today = datetime.now()

    # Sample projects with current dates
    projects = [
        {
            'name': 'Website Redesign',
            'description': 'Complete redesign of company website',
            'status': 'Active',
            'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
            'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
            'budget_allocated': 150000,
            'budget_used': 85000,
            'revenue_projected': 200000,
            'revenue_actual': 110000,
            'client': 'TechCorp Inc',
            'project_manager': 'John Smith'
        },
        {
            'name': 'Mobile App Development',
            'description': 'iOS and Android app development',
            'status': 'Active',
            'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
            'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
            'budget_allocated': 250000,
            'budget_used': 120000,
            'revenue_projected': 350000,
            'revenue_actual': 150000,
            'client': 'StartupXYZ',
            'project_manager': 'Jane Doe'
        },
        {
            'name': 'Data Migration',
            'description': 'Legacy system data migration to cloud',
            'status': 'Completed',
            'start_date': (today - timedelta(days=240)).strftime('%Y-%m-%d'),
            'end_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
            'budget_allocated': 80000,
            'budget_used': 75000,
            'revenue_projected': 100000,
            'revenue_actual': 95000,
            'client': 'Enterprise Co',
            'project_manager': 'Bob Wilson'
        },
        {
            'name': 'API Integration',
            'description': 'Third-party API integration project',
            'status': 'Active',
            'start_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
            'end_date': (today + timedelta(days=30)).strftime('%Y-%m-%d'),
            'budget_allocated': 60000,
            'budget_used': 25000,
            'revenue_projected': 80000,
            'revenue_actual': 30000,
            'client': 'FinTech Solutions',
            'project_manager': 'Alice Johnson'
        },
        {
            'name': 'Security Audit',
            'description': 'Comprehensive security audit and implementation',
            'status': 'On Hold',
            'start_date': (today - timedelta(days=30)).strftime('%Y-%m-%d'),
            'end_date': (today + timedelta(days=120)).strftime('%Y-%m-%d'),
            'budget_allocated': 45000,
            'budget_used': 10000,
            'revenue_projected': 60000,
            'revenue_actual': 10000,
            'client': 'SecureBank',
            'project_manager': 'Charlie Brown'
        }
    ]

    # Sample employees
    employees = [
        {
            'name': 'John Smith',            'role': 'Project Manager',            'skills': 'Project Management, Agile, Scrum',
            'hire_date': '2020-01-15'
        },
        {
            'name': 'Jane Doe',            'role': 'Senior Project Manager',            'skills': 'Project Management, Risk Management, Stakeholder Management',
            'hire_date': '2019-03-20'
        },
        {
            'name': 'Bob Wilson',            'role': 'Senior Developer',            'skills': 'Python, JavaScript, React, Node.js',
            'hire_date': '2021-06-01'
        },
        {
            'name': 'Alice Johnson',            'role': 'Full Stack Developer',            'skills': 'Java, Spring, Angular, PostgreSQL',
            'hire_date': '2022-02-15'
        },
        {
            'name': 'Charlie Brown',            'role': 'DevOps Engineer',            'skills': 'AWS, Docker, Kubernetes, CI/CD',
            'hire_date': '2021-09-01'
        },
        {
            'name': 'Emma Davis',            'role': 'UX Designer',            'skills': 'Figma, Sketch, User Research, Prototyping',
            'hire_date': '2022-11-15'
        },
        {
            'name': 'Frank Miller',            'role': 'Backend Developer',            'skills': 'Python, Django, Redis, MongoDB',
            'hire_date': '2023-01-10'
        },
        {
            'name': 'Grace Lee',            'role': 'QA Engineer',            'skills': 'Selenium, Jest, Cypress, Test Automation',
            'hire_date': '2023-04-20'
        },
        {
            'name': 'Henry Taylor',            'role': 'Data Analyst',            'skills': 'SQL, Python, Tableau, Power BI',
            'hire_date': '2022-08-01'
        },
        {
            'name': 'Iris Wang',            'role': 'Frontend Developer',            'skills': 'React, TypeScript, CSS, Redux',
            'hire_date': '2023-06-15'
        }
    ]

    # Insert projects and employees
    project_ids = []
    for project in projects:
        project_id = db_manager.add_project(project)
        project_ids.append(project_id)

    employee_ids = []
    for employee in employees:
        employee_id = db_manager.add_employee(employee)
        employee_ids.append(employee_id)

    # Generate allocations with current dates
    allocations = [
        # Website Redesign
        {'project_id': project_ids[0], 'employee_id': employee_ids[0], 'allocated_fte': 0.50,
         'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Project Manager'},
        {'project_id': project_ids[0], 'employee_id': employee_ids[2], 'allocated_fte': 0.80,
         'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Senior Developer'},
        {'project_id': project_ids[0], 'employee_id': employee_ids[5], 'allocated_fte': 0.60,
         'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'UX Designer'},

        # Mobile App Development
        {'project_id': project_ids[1], 'employee_id': employee_ids[1], 'allocated_fte': 0.40,
         'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
         'role': 'Project Manager'},
        {'project_id': project_ids[1], 'employee_id': employee_ids[3], 'allocated_fte': 1.00,
         'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
         'role': 'Full Stack Developer'},
        {'project_id': project_ids[1], 'employee_id': employee_ids[9], 'allocated_fte': 0.70,
         'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
         'role': 'Frontend Developer'},

        # Data Migration (Completed)
        {'project_id': project_ids[2], 'employee_id': employee_ids[2], 'allocated_fte': 0.60,
         'start_date': (today - timedelta(days=240)).strftime('%Y-%m-%d'),
         'end_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Senior Developer'},
        {'project_id': project_ids[2], 'employee_id': employee_ids[8], 'allocated_fte': 0.50,
         'start_date': (today - timedelta(days=240)).strftime('%Y-%m-%d'),
         'end_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Data Analyst'},

        # API Integration
        {'project_id': project_ids[3], 'employee_id': employee_ids[3], 'allocated_fte': 0.50,
         'start_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=30)).strftime('%Y-%m-%d'),
         'role': 'Lead Developer'},
        {'project_id': project_ids[3], 'employee_id': employee_ids[6], 'allocated_fte': 0.60,
         'start_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=30)).strftime('%Y-%m-%d'),
         'role': 'Backend Developer'},
    ]

    for allocation in allocations:
        db_manager.add_allocation(allocation)

    # Generate time entries with recent dates (last 90 days)
    time_entry_start = today - timedelta(days=90)
    time_entry_end = today

    for project_id in project_ids[:4]:  # Only for active/completed projects
        for employee_id in random.sample(employee_ids, k=random.randint(2, 4)):
            num_entries = random.randint(20, 40)
            for _ in range(num_entries):
                entry_date = time_entry_start + timedelta(days=random.randint(0, (time_entry_end - time_entry_start).days))
                hours = random.choice([2, 4, 6, 8])
                billable = random.choice([0, 1, 1, 1])  # 75% billable

                time_entry = {
                    'employee_id': employee_id,
                    'project_id': project_id,
                    'date': entry_date.strftime('%Y-%m-%d'),
                    'hours': hours,
                    'description': f'Development work on project',
                    'billable': billable
                }
                db_manager.add_time_entry(time_entry)

    # Generate expenses with recent dates (last 120 days)
    expense_categories = ['Software Licenses', 'Hardware', 'Travel', 'Training', 'Contractors', 'Infrastructure']
    expense_start = today - timedelta(days=120)

    for project_id in project_ids:
        num_expenses = random.randint(5, 15)
        for _ in range(num_expenses):
            expense_date = expense_start + timedelta(days=random.randint(0, 120))
            category = random.choice(expense_categories)
            amount = random.randint(500, 5000)

            expense = {
                'project_id': project_id,
                'category': category,
                'description': f'{category} expense for project',
                'amount': amount,
                'date': expense_date.strftime('%Y-%m-%d'),
                'approved': random.choice([0, 1, 1])  # 67% approved
            }
            db_manager.add_expense(expense)

    # Add NIA (OY2) project data
    logger.info("Adding NIA project data...")

    # NIA Project
    nia_project = {
        'name': 'NIA (OY2) 202800.Y2.000',
        'description': 'NIA Option Year 2 - Web Development Services',
        'status': 'Active',
        'start_date': '2024-11-01',
        'end_date': '2025-10-31',
        'budget_allocated': 327145,
        'budget_used': 50000,
        'revenue_projected': 327145,
        'revenue_actual': 50000,
        'client': 'NIA/NIH',
        'project_manager': 'Jennifer Johns'
    }

    nia_project_id = db_manager.add_project(nia_project)
    project_ids.append(nia_project_id)

    # NIA Employees
    nia_employees = [
        {
            'name': 'Jennifer Johns',            'role': 'Web Project Manager',            'skills': 'Project Management, Agile, Web Development',
            'hire_date': '2023-01-15'
        },
        {
            'name': 'Matt Canton',            'role': 'Web Software Developer',            'skills': 'Full Stack Development, JavaScript, Python, React',
            'hire_date': '2023-02-01'
        },
        {
            'name': 'Jacob Coleman',            'role': 'Web Software Developer',            'skills': 'Full Stack Development, Node.js, Database Design',
            'hire_date': '2022-09-15'
        },
        {
            'name': 'Caleb Andree',            'role': 'Application Specialist 1',            'skills': 'Application Support, Testing, Documentation',
            'hire_date': '2024-01-10'
        }
    ]

    nia_employee_ids = []
    for employee in nia_employees:
        employee_id = db_manager.add_employee(employee)
        nia_employee_ids.append(employee_id)
        employee_ids.append(employee_id)

    # NIA Allocations (monthly allocations with varying FTE)
    # Sample months from Nov 2024 through Nov 2025
    nia_months = [
        '2024-11-01', '2024-12-01', '2025-01-01', '2025-02-01', '2025-03-01',
        '2025-04-01', '2025-05-01', '2025-06-01', '2025-07-01', '2025-08-01',
        '2025-09-01', '2025-10-01'
    ]


    # Monthly FTE allocations for each employee (from Hours CSV)
    # FTE varies by month; actual hours for past/current months only
    # Working days from CSV (project-specific - NIA started late November)
    # Possible, Projected, and Total hours are calculated by build_hours_sheet_data()

    # Working days per month from Hours CSV header
    nia_working_days_by_month = [1, 21, 21, 19, 21, 22, 21, 20, 22, 21, 21, 22]

    nia_allocations_data = [
        # Jennifer Johns (PM) - FTE varies: 20%, 15%, 10%, 10%, 10%, 10%, 10%, 10%, 10%, 7%, 7%, 7%
        {'employee_idx': 0, 'fte_by_month': [20, 15, 10, 10, 10, 10, 10, 10, 10, 7, 7, 7],
         'actual_hours': [0.5, 8.75, 9.3, 17.3, 18.25, 13.8, 11.75, 14.25, 10.5, 9.25, 13.25, 0]},
        # Matt Canton - FTE varies: 65%, 50%, 50%, 50%, 50%, 50%, 50%, 50%, 20%, 15%, 15%, 15%
        {'employee_idx': 1, 'fte_by_month': [65, 50, 50, 50, 50, 50, 50, 50, 20, 15, 15, 15],
         'actual_hours': [5.5, 71.5, 72, 76.75, 90, 75.75, 38.5, 44.75, 68.75, 24.5, 22.5, 0]},
        # Jacob Coleman - FTE varies: 45%, then 100% for remaining months
        {'employee_idx': 2, 'fte_by_month': [45, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
         'actual_hours': [0, 120, 120, 152, 168, 176, 134.5, 150.5, 159, 146, 114, 0]},
        # Caleb Andree - FTE varies: 12.5% initially, then 1% from August onwards
        {'employee_idx': 3, 'fte_by_month': [12.5, 12.5, 12.5, 12.5, 12.5, 12.5, 12.5, 12.5, 1, 1, 1, 1],
         'actual_hours': [0, 74, 74, 85.75, 94.75, 110.25, 92, 23.5, 2.75, 2, 0, 0]}
    ]

    for emp_data in nia_allocations_data:
        for month_idx, month_date in enumerate(nia_months):
            # Create monthly allocation record with month-specific FTE and working days
            allocation = {
                'project_id': nia_project_id,
                'employee_id': nia_employee_ids[emp_data['employee_idx']],
                'allocated_fte': emp_data['fte_by_month'][month_idx] / 100,  # Convert percentage to FTE
                'allocation_date': month_date,
                'start_date': month_date,
                'end_date': month_date,
                'role': nia_employees[emp_data['employee_idx']]['role'],
                'project_rate': nia_employees[emp_data['employee_idx']]['hourly_rate'],
                'working_days': nia_working_days_by_month[month_idx]
            }
            db_manager.add_allocation(allocation)

            # Create time entry for actual hours (past months - Nov 2024 through March 2025)
            if month_idx < 5 and emp_data['actual_hours'][month_idx] > 0:
                time_entry = {
                    'employee_id': nia_employee_ids[emp_data['employee_idx']],
                    'project_id': nia_project_id,
                    'date': month_date,
                    'hours': emp_data['actual_hours'][month_idx],
                    'description': f'NIA web development work - {month_date}',
                    'billable': 1,
                    'is_projected': 0
                }
                db_manager.add_time_entry(time_entry)
            # Create projected hours for future months (April 2025 onwards)
            elif month_idx >= 5 and emp_data['actual_hours'][month_idx] > 0:
                time_entry = {
                    'employee_id': nia_employee_ids[emp_data['employee_idx']],
                    'project_id': nia_project_id,
                    'date': month_date,
                    'hours': emp_data['actual_hours'][month_idx],
                    'description': f'NIA web development work (projected) - {month_date}',
                    'billable': 1,
                    'is_projected': 1
                }
                db_manager.add_time_entry(time_entry)

    logger.info(f"Added NIA project with {len(nia_employees)} employees and monthly allocations")

    logger.info("Sample data generated successfully!")
