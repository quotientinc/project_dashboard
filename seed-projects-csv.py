import pandas as pd

# Load the CSV file
df = pd.read_csv('sample-data/TimesheetData.csv')

# Filter to only include Project IDs that start with a number
df = df[df['Project ID'].astype(str).str[0].str.isdigit()]

# Parse dates to determine project start and end dates
df['parsed_date'] = pd.to_datetime(df['Hours Date'], format='%d-%b-%y')

# Create a dataframe with unique Project IDs and their date ranges
projects = df.groupby('Project ID').agg({
    'parsed_date': ['min', 'max']  # Get earliest and latest dates
}).reset_index()

# Flatten the multi-level column names
projects.columns = ['Project ID', 'start_date', 'end_date']

# Format dates as YYYY-MM-DD
projects['start_date'] = projects['start_date'].dt.strftime('%Y-%m-%d')
projects['end_date'] = projects['end_date'].dt.strftime('%Y-%m-%d')

# Create the project dataframe with all required columns
project_data = pd.DataFrame({
    'id': projects['Project ID'],
    'name': projects['Project ID'],
    'description': 'Seeded from TimesheetData.',
    'status': 'Active',
    'start_date': projects['start_date'],
    'end_date': projects['end_date'],
    'budget_allocated': 100.00,
    'budget_used': 100.00,
    'revenue_projected': 100.00,
    'revenue_actual': 100.00,
    'client': 'TODO',
    'project_manager': 'TODO'
})

# Display the results
print(f"Total unique projects: {len(project_data)}")
print("\nFirst 10 projects:")
print(project_data.head(10))

# Write the dataframe to CSV
project_data.to_csv('sample-data/ProjectData.csv', index=False)
print(f"\n✅ Written {len(project_data)} rows to sample-data/ProjectData.csv")