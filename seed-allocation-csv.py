import pandas as pd

# Load the CSV file
df = pd.read_csv('sample-data/TimesheetData.csv')

# Create a dataframe with unique Employee ID and Project ID combinations
# Including Billing Rate and PLC Desc for each combo
unique_combos = df.groupby(['Employee ID', 'Project ID']).agg({
    ' Billing Rate ': 'first',  # Take the first billing rate for this combo
    'PLC Desc': 'first'  # Take the first PLC Desc for this combo
}).reset_index()

# Display the results
print(f"Total unique Employee-Project combinations: {len(unique_combos)}")
print("\nFirst 10 combinations:")
print(unique_combos.head(10))

# If you want to see combinations where Billing Rate is not null
combos_with_rate = unique_combos[unique_combos[' Billing Rate '].notna()]
print(f"\nCombinations with billing rate: {len(combos_with_rate)}")
print(combos_with_rate.head(10))

# Write the dataframe to CSV
unique_combos.to_csv('sample-data/AllocationData.csv', index=False)
print(f"\n✅ Written {len(unique_combos)} rows to sample-data/AllocationData.csv")
