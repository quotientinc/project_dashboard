import random
from datetime import datetime, timedelta
import pandas as pd

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
            'name': 'John Smith',
            'email': 'john.smith@company.com',
            'department': 'Management',
            'role': 'Project Manager',
            'hourly_rate': 150,
            'fte': 1.0,
            'utilization': 85,
            'skills': 'Project Management, Agile, Scrum',
            'hire_date': '2020-01-15'
        },
        {
            'name': 'Jane Doe',
            'email': 'jane.doe@company.com',
            'department': 'Management',
            'role': 'Senior Project Manager',
            'hourly_rate': 175,
            'fte': 1.0,
            'utilization': 90,
            'skills': 'Project Management, Risk Management, Stakeholder Management',
            'hire_date': '2019-03-20'
        },
        {
            'name': 'Bob Wilson',
            'email': 'bob.wilson@company.com',
            'department': 'Engineering',
            'role': 'Senior Developer',
            'hourly_rate': 140,
            'fte': 1.0,
            'utilization': 75,
            'skills': 'Python, JavaScript, React, Node.js',
            'hire_date': '2021-06-01'
        },
        {
            'name': 'Alice Johnson',
            'email': 'alice.johnson@company.com',
            'department': 'Engineering',
            'role': 'Full Stack Developer',
            'hourly_rate': 120,
            'fte': 1.0,
            'utilization': 80,
            'skills': 'Java, Spring, Angular, PostgreSQL',
            'hire_date': '2022-02-15'
        },
        {
            'name': 'Charlie Brown',
            'email': 'charlie.brown@company.com',
            'department': 'Engineering',
            'role': 'DevOps Engineer',
            'hourly_rate': 130,
            'fte': 1.0,
            'utilization': 70,
            'skills': 'AWS, Docker, Kubernetes, CI/CD',
            'hire_date': '2021-09-01'
        },
        {
            'name': 'Emma Davis',
            'email': 'emma.davis@company.com',
            'department': 'Design',
            'role': 'UX Designer',
            'hourly_rate': 110,
            'fte': 1.0,
            'utilization': 65,
            'skills': 'Figma, Sketch, User Research, Prototyping',
            'hire_date': '2022-11-15'
        },
        {
            'name': 'Frank Miller',
            'email': 'frank.miller@company.com',
            'department': 'Engineering',
            'role': 'Backend Developer',
            'hourly_rate': 125,
            'fte': 0.8,
            'utilization': 85,
            'skills': 'Python, Django, Redis, MongoDB',
            'hire_date': '2023-01-10'
        },
        {
            'name': 'Grace Lee',
            'email': 'grace.lee@company.com',
            'department': 'QA',
            'role': 'QA Engineer',
            'hourly_rate': 100,
            'fte': 1.0,
            'utilization': 75,
            'skills': 'Selenium, Jest, Cypress, Test Automation',
            'hire_date': '2023-04-20'
        },
        {
            'name': 'Henry Taylor',
            'email': 'henry.taylor@company.com',
            'department': 'Data',
            'role': 'Data Analyst',
            'hourly_rate': 115,
            'fte': 1.0,
            'utilization': 70,
            'skills': 'SQL, Python, Tableau, Power BI',
            'hire_date': '2022-08-01'
        },
        {
            'name': 'Iris Wang',
            'email': 'iris.wang@company.com',
            'department': 'Engineering',
            'role': 'Frontend Developer',
            'hourly_rate': 115,
            'fte': 1.0,
            'utilization': 78,
            'skills': 'React, TypeScript, CSS, Redux',
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
        {'project_id': project_ids[0], 'employee_id': employee_ids[0], 'allocation_percent': 50,
         'hours_projected': 520, 'hours_actual': 450,
         'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Project Manager'},
        {'project_id': project_ids[0], 'employee_id': employee_ids[2], 'allocation_percent': 80,
         'hours_projected': 832, 'hours_actual': 720,
         'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Senior Developer'},
        {'project_id': project_ids[0], 'employee_id': employee_ids[5], 'allocation_percent': 60,
         'hours_projected': 624, 'hours_actual': 500,
         'start_date': (today - timedelta(days=120)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'UX Designer'},

        # Mobile App Development
        {'project_id': project_ids[1], 'employee_id': employee_ids[1], 'allocation_percent': 40,
         'hours_projected': 624, 'hours_actual': 400,
         'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
         'role': 'Project Manager'},
        {'project_id': project_ids[1], 'employee_id': employee_ids[3], 'allocation_percent': 100,
         'hours_projected': 1248, 'hours_actual': 800,
         'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
         'role': 'Full Stack Developer'},
        {'project_id': project_ids[1], 'employee_id': employee_ids[9], 'allocation_percent': 70,
         'hours_projected': 874, 'hours_actual': 560,
         'start_date': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=90)).strftime('%Y-%m-%d'),
         'role': 'Frontend Developer'},

        # Data Migration (Completed)
        {'project_id': project_ids[2], 'employee_id': employee_ids[2], 'allocation_percent': 60,
         'hours_projected': 480, 'hours_actual': 500,
         'start_date': (today - timedelta(days=240)).strftime('%Y-%m-%d'),
         'end_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Senior Developer'},
        {'project_id': project_ids[2], 'employee_id': employee_ids[8], 'allocation_percent': 50,
         'hours_projected': 400, 'hours_actual': 420,
         'start_date': (today - timedelta(days=240)).strftime('%Y-%m-%d'),
         'end_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'role': 'Data Analyst'},

        # API Integration
        {'project_id': project_ids[3], 'employee_id': employee_ids[3], 'allocation_percent': 50,
         'hours_projected': 390, 'hours_actual': 200,
         'start_date': (today - timedelta(days=60)).strftime('%Y-%m-%d'),
         'end_date': (today + timedelta(days=30)).strftime('%Y-%m-%d'),
         'role': 'Lead Developer'},
        {'project_id': project_ids[3], 'employee_id': employee_ids[6], 'allocation_percent': 60,
         'hours_projected': 468, 'hours_actual': 240,
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
    
    print("Sample data generated successfully!")
