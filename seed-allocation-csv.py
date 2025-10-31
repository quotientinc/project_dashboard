import pandas as pd

# Load the CSV file
df = pd.read_csv('sample-data/TimesheetData.csv')

# Filter to only include Project IDs that start with a number
df = df[df['Project ID'].astype(str).str[0].str.isdigit()]

# Parse dates and extract year-month in YYYY-MM format
df['Month'] = pd.to_datetime(df['Hours Date'], format='%d-%b-%y').dt.strftime('%Y-%m')

# Create a dataframe with unique Employee ID, Project ID, and Month combinations
# Including Billing Rate, PLC Desc, and Allocation (FTE based on hours worked)
unique_combos = df.groupby(['Employee ID', 'Project ID', 'Month']).agg({
    'Entered Hours': 'sum',  # Sum total hours worked on this project in this month
    ' Billing Rate ': 'first',  # Take the first billing rate for this combo
    'PLC Desc': 'first'  # Take the first PLC Desc for this combo
}).reset_index()

# Calculate Allocation as FTE (Full-Time Equivalent)
# Assuming 160 hours per month = 1.0 FTE (40 hours/week * 4 weeks)
unique_combos['Allocation'] = unique_combos['Entered Hours'] / 160.0

# Round to major increments: 0.25, 0.5, 0.75, 1.0
# This rounds to the nearest 0.25
unique_combos['Allocation'] = (unique_combos['Allocation'] / 0.25).round() * 0.25

# Filter out allocations that are 0 or less
unique_combos = unique_combos[unique_combos['Allocation'] > 0]

# Drop the intermediate 'Entered Hours' column as we only need the Allocation
unique_combos = unique_combos.drop(columns=['Entered Hours'])

# Display the results
print(f"Total unique Employee-Project-Month combinations: {len(unique_combos)}")
print("\nFirst 10 combinations:")
print(unique_combos.head(10))

# If you want to see combinations where Billing Rate is not null
combos_with_rate = unique_combos[unique_combos[' Billing Rate '].notna()]
print(f"\nCombinations with billing rate: {len(combos_with_rate)}")
print(combos_with_rate.head(10))

# Write the dataframe to CSV
unique_combos.to_csv('sample-data/AllocationData.csv', index=False)
print(f"\n✅ Written {len(unique_combos)} rows to sample-data/AllocationData.csv")

