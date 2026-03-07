# Project Management Dashboard 📊

A comprehensive Streamlit-based project management dashboard for tracking projects, employees, finances, and resources with advanced analytics and reporting capabilities.

## Features 🚀

### Core Functionality
- **Project Management**: Track multiple projects with budgets, timelines, and status
- **Employee Management**: Manage team members, roles, and utilization rates
- **Financial Analysis**: Revenue tracking, cost analysis, burn rate monitoring
- **Resource Allocation**: Track employee allocations and FTE requirements
- **Time Tracking**: Log and monitor hours worked on projects
- **Expense Management**: Track and categorize project expenses

### Advanced Features
- **What-If Scenarios**: Analyze different scenarios for costs, resources, and revenue
- **Comprehensive Reporting**: Generate executive, financial, and resource reports
- **Data Import/Export**: CSV and Excel support for data management
- **Interactive Visualizations**: Charts and graphs using Plotly
- **Global Filtering**: Filter data across all views by project, employee, date, etc.
- **Real-time Metrics**: KPIs, utilization rates, and financial metrics

## Installation 🛠️

### Prerequisites
- Python 3.8 or higher
- pip package manager
- Optional venv

### Setup Instructions

1. **Clone or download the project**
```bash
cd project_dashboard
```

Optional venv
```bash
python -m venv .venv
source .venv/bin/activate
```

2. **Install required packages**
```bash
pip install -r requirements.txt
```

3. **Run the application**
```bash
streamlit run app.py
```

4. **Access the dashboard**
Open your browser and navigate to `http://localhost:8501`

## Docker 🐳

### Development

Quick start with Docker for local development:

```bash
cd docker
docker compose up --build
```

Access the dashboard at http://localhost:8501. Data is persisted in the `data/` directory.

To build the image separately:

```bash
./docker/build
```

### Deployment (Production Server)

#### Option 1: Deploy Script (Build on Server)

For deploying to a server where you build the image locally. The `docker/deploy.sh` script automates: git pull, docker build, restart, healthcheck, and rollback on failure.

**First-time setup on the server:**

1. Clone the repo on the server
2. Run the deploy script:

```bash
./docker/deploy.sh master
```

The script:
- Pulls the latest code from the specified branch
- Builds and tags the image with the git commit hash
- Restarts the container with the new image
- Waits for the healthcheck to pass
- Rolls back automatically if deployment fails
- Prunes old images (keeps last 5)

Configuration via environment variables:
- `QPD_REPO_DIR` -- path to the git repo (default: auto-detected from script location)
- `QPD_DEPLOY_DIR` -- deployment data directory (default: `/var/www/vhosts/project-dashboard`)

#### Option 2: CI/CD with GitHub Container Registry

For automated builds via GitHub Actions with server-side pull deployment.

GitHub Actions (`.github/workflows/build-push.yml`) automatically builds and pushes the Docker image to GHCR on every push to `master`. It can also be triggered manually via `workflow_dispatch`.

**Server-side deployment:**

One-time setup:
```bash
docker login ghcr.io
# Use a GitHub personal access token with read:packages scope
```

Deploy:
```bash
QPD_IMAGE=your-org/project_dashboard ./docker/pull-deploy.sh
# Or pull a specific version:
QPD_IMAGE=your-org/project_dashboard ./docker/pull-deploy.sh abc1234
```

Configuration via environment variables:
- `QPD_IMAGE` -- **required**, the GHCR image name (e.g., `your-org/project_dashboard`)
- `QPD_REGISTRY` -- container registry (default: `ghcr.io`)
- `QPD_DEPLOY_DIR` -- deployment data directory (default: `/var/www/vhosts/project-dashboard`)

### Data Persistence

The SQLite database is stored in the `data/` directory, which is mounted as a Docker volume. This directory is preserved across container restarts and redeployments. Both deployment scripts ensure the data directory exists before starting.

## Usage Guide 📖

### Navigation
The dashboard is organized into several main sections accessible from the sidebar:

#### 1. **Overview Dashboard**
- View key performance indicators
- Monitor project health scores
- Track burn rates and utilization
- See revenue vs cost comparisons
- Get project completion forecasts

#### 2. **Projects**
- **Project List**: View all projects in table or card format
- **Project Details**: Deep dive into individual projects
- **Add Project**: Create new projects
- **Project Analytics**: Compare and analyze projects

#### 3. **Employees**
- **Employee List**: Browse team members by department/role
- **Utilization**: Analyze employee utilization rates
- **Add Employee**: Add new team members

#### 4. **Financial Analysis**
- **Revenue Analysis**: Track projected vs actual revenue
- **Cost Analysis**: Breakdown of labor and expense costs
- **Burn Rate**: Monitor spending over time
- **Cash Flow**: Analyze income and expenses

#### 5. **Reports**
- **Executive Summary**: High-level overview reports
- **Project Status**: Detailed project reports
- **Resource Utilization**: Team utilization reports
- **Financial Reports**: Comprehensive financial analysis
- **Custom Reports**: Build your own reports

#### 6. **What-If Scenarios**
- **Project Cost Scenarios**: Analyze optimistic/pessimistic outcomes
- **Resource Allocation**: Plan team changes
- **Revenue Projections**: Forecast future revenue
- **Burn Rate Analysis**: Project runway scenarios

#### 7. **Data Management**
- **Import Data**: Upload CSV files
- **Export Data**: Download data in CSV/Excel format
- **Backup & Restore**: Create and restore backups
- **Database Management**: Manage and clean data

### Global Filters
Use the sidebar filters to narrow down data across all views:
- Date range selection
- Project filtering
- Employee filtering
- Department filtering
- Status filtering

## Data Structure 📁

### Database Tables
The application uses SQLite with the following tables:

1. **projects**: Project information (name, budget, revenue, dates, status)
2. **employees**: Employee details (name, role, rate, department)
3. **allocations**: Project-employee assignments
4. **time_entries**: Time tracking records
5. **expenses**: Project expenses

### CSV Import Format
When importing data, use these column formats:

**Projects CSV:**
```
name,description,status,start_date,end_date,budget_allocated,budget_used,revenue_projected,revenue_actual,client,project_manager
```

**Employees CSV:**
```
name,email,department,role,hourly_rate,fte,utilization,skills,hire_date
```

## Sample Data 🎯

The application includes a sample data generator that creates:
- 5 sample projects
- 10 employees
- Allocations and time entries
- Expense records

To generate sample data:
1. Go to **Data Management** tab
2. Click **Generate Sample Data**

## Key Metrics Explained 📊

- **Utilization Rate**: Percentage of available hours being used
- **Burn Rate**: Rate of spending over time
- **FTE (Full-Time Equivalent)**: Standard measure of employee allocation
- **Health Score**: Composite metric of budget, schedule, and profit performance
- **Profit Margin**: (Revenue - Costs) / Revenue × 100

## Tips for Best Use 💡

1. **Start with sample data** to understand the system
2. **Use global filters** to focus on specific projects or time periods
3. **Export reports regularly** for external sharing
4. **Create backups** before major data changes
5. **Use What-If scenarios** for planning and forecasting
6. **Monitor health scores** to identify at-risk projects
7. **Track utilization** to optimize resource allocation

## Troubleshooting 🔧

### Common Issues

**Application won't start:**
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check Python version: `python --version` (should be 3.8+)

**Data not appearing:**
- Check global filters in the sidebar
- Ensure date ranges include your data
- Try generating sample data first

**Import errors:**
- Verify CSV format matches requirements
- Check for required columns
- Ensure dates are in YYYY-MM-DD format

**Performance issues:**
- Limit date ranges when working with large datasets
- Use filters to reduce data displayed
- Consider archiving old data

## Customization 🎨

The dashboard can be customized by modifying:
- Color schemes in the CSS (app.py)
- Chart types and layouts in page modules
- Metrics calculations in data_processor.py
- Database schema in database.py

## Future Enhancements 🔮

Potential features for expansion:
- User authentication and permissions
- API integration for external data sources
- Automated report scheduling
- Mobile-responsive design
- Real-time collaboration features
- Advanced forecasting with ML
- Gantt chart visualization
- Risk management module
- Client portal access
- Notification system

## Support 📞

For issues or questions:
1. Check the troubleshooting section
2. Review the usage guide
3. Examine sample data structure
4. Verify data formats for imports

## License 📄

This project is provided as-is for project management and demonstration purposes.

---

**Version**: 1.0  
**Last Updated**: 2024  
**Built with**: Streamlit, Plotly, Pandas, SQLite
