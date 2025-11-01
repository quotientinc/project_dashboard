import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager

st.markdown("### 📅 Months Management")

# Display summary metrics
months_df = db.get_months()

if not months_df.empty:
    col1, col2, col3 = st.columns(3)
    with col1:
        unique_years = months_df['year'].nunique()
        st.metric("Total Years", unique_years)
    with col2:
        total_months = len(months_df)
        st.metric("Total Months", total_months)
    with col3:
        total_holidays = months_df['holidays'].sum()
        st.metric("Total Holidays Tracked", int(total_holidays))

st.divider()

# Create tabs
tab1, tab2 = st.tabs(["📊 View & Edit Months", "➕ Add Year"])

with tab1:
    st.markdown("#### Month Calendar Data")
    st.info("Edit working days and holidays directly in the table below. Click 'Save Changes' when done.")

    months_df = db.get_months()

    if not months_df.empty:
        # Prepare dataframe for editing
        display_df = months_df[['id', 'year', 'month', 'month_name', 'quarter', 'total_days', 'working_days', 'holidays']].copy()

        # Configure columns for data editor
        column_config = {
            'id': st.column_config.NumberColumn(
                'ID',
                help='Database record ID',
                disabled=True,
                width='small'
            ),
            'year': st.column_config.NumberColumn(
                'Year',
                help='Calendar year',
                disabled=True,
                width='small'
            ),
            'month': st.column_config.NumberColumn(
                'Month',
                help='Month number (1-12)',
                disabled=True,
                width='small'
            ),
            'month_name': st.column_config.TextColumn(
                'Month Name',
                help='Name of the month',
                disabled=True,
                width='medium'
            ),
            'quarter': st.column_config.TextColumn(
                'Quarter',
                help='Calendar quarter (Q1-Q4)',
                disabled=True,
                width='small'
            ),
            'total_days': st.column_config.NumberColumn(
                'Total Days',
                help='Total days in month',
                disabled=True,
                width='small'
            ),
            'working_days': st.column_config.NumberColumn(
                'Working Days',
                help='Editable: Number of working days (Mon-Fri)',
                min_value=0,
                max_value=31,
                step=1,
                width='small',
                required=True
            ),
            'holidays': st.column_config.NumberColumn(
                'Holidays',
                help='Editable: Number of federal/company holidays',
                min_value=0,
                max_value=31,
                step=1,
                width='small',
                required=True
            ),
        }

        # Display editable table
        edited_df = st.data_editor(
            display_df,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            key='months_editor'
        )

        # Save changes button
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("💾 Save Changes", type="primary"):
                try:
                    changes_made = 0

                    # Compare original and edited dataframes
                    for idx in range(len(display_df)):
                        month_id = int(edited_df.iloc[idx]['id'])

                        # Check if working_days or holidays changed
                        original_working_days = display_df.iloc[idx]['working_days']
                        edited_working_days = edited_df.iloc[idx]['working_days']
                        original_holidays = display_df.iloc[idx]['holidays']
                        edited_holidays = edited_df.iloc[idx]['holidays']

                        if (original_working_days != edited_working_days or
                            original_holidays != edited_holidays):

                            # Validate that working_days + holidays <= total_days
                            total_days = edited_df.iloc[idx]['total_days']
                            if edited_working_days + edited_holidays > total_days:
                                st.error(f"Row {idx + 1}: Working days ({edited_working_days}) + Holidays ({edited_holidays}) cannot exceed total days ({total_days})")
                                continue

                            # Update the record
                            updates = {
                                'working_days': int(edited_working_days),
                                'holidays': int(edited_holidays)
                            }
                            db.update_month(month_id, updates)
                            changes_made += 1

                    if changes_made > 0:
                        st.success(f"✅ Successfully updated {changes_made} month(s)!")
                        st.rerun()
                    else:
                        st.info("No changes detected")

                except Exception as e:
                    st.error(f"Error saving changes: {str(e)}")
                    logger.error(f"Error updating months: {str(e)}")

        with col2:
            if st.button("🔄 Refresh Data"):
                st.rerun()

    else:
        st.info("No months found. Use the 'Add Year' tab to generate month data for a new year.")

with tab2:
    st.markdown("#### Generate Months for a New Year")
    st.write("Automatically generate all 12 months for a selected year with calculated working days.")

    col1, col2 = st.columns(2)

    with col1:
        current_year = datetime.now().year
        year_to_add = st.number_input(
            "Year",
            min_value=2020,
            max_value=2050,
            value=current_year,
            step=1
        )

    with col2:
        # Option to copy holidays from previous year
        copy_holidays = st.checkbox(
            "Copy holidays from previous year",
            value=False,
            help="If checked, will copy holiday counts from the previous year's months"
        )

    if st.button("➕ Generate All Months", type="primary"):
        try:
            # Check if year already exists
            existing_months = db.get_months(year=year_to_add)
            if not existing_months.empty:
                st.warning(f"⚠️ Year {year_to_add} already has {len(existing_months)} months in the database. Use the 'View & Edit' tab to modify them.")
            else:
                # Get previous year's holidays if requested
                previous_year_holidays = {}
                if copy_holidays:
                    prev_year_df = db.get_months(year=year_to_add - 1)
                    if not prev_year_df.empty:
                        previous_year_holidays = dict(zip(prev_year_df['month'], prev_year_df['holidays']))
                        st.info(f"Copying holidays from {year_to_add - 1}")

                # Generate months data
                months_to_add = []

                for month_num in range(1, 13):
                    # Get actual days in month
                    total_days = calendar.monthrange(year_to_add, month_num)[1]
                    month_name = calendar.month_name[month_num]

                    # Calculate quarter (Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec)
                    quarter = f"Q{((month_num - 1) // 3) + 1}"

                    # Calculate working days (Mon-Fri)
                    working_days = 0
                    for day in range(1, total_days + 1):
                        weekday = calendar.weekday(year_to_add, month_num, day)
                        if weekday < 5:  # Monday=0, Friday=4
                            working_days += 1

                    # Get holidays from previous year or default to 0
                    holidays = previous_year_holidays.get(month_num, 0)

                    month_data = {
                        'year': year_to_add,
                        'month': month_num,
                        'month_name': month_name,
                        'quarter': quarter,
                        'total_days': total_days,
                        'working_days': working_days,
                        'holidays': int(holidays)
                    }
                    months_to_add.append(month_data)

                # Bulk insert
                db.bulk_upsert_months(months_to_add)

                st.success(f"✅ Successfully generated all 12 months for {year_to_add}!")
                st.balloons()

                # Show preview
                st.markdown("##### Preview of Generated Months")
                preview_df = pd.DataFrame(months_to_add)
                st.dataframe(
                    preview_df[['month', 'month_name', 'quarter', 'total_days', 'working_days', 'holidays']],
                    use_container_width=True,
                    hide_index=True
                )

                # Wait a moment before reloading
                import time
                time.sleep(2)
                st.rerun()

        except Exception as e:
            st.error(f"Error generating months: {str(e)}")
            logger.error(f"Error generating months for year {year_to_add}: {str(e)}")

st.divider()

# Help section
with st.expander("ℹ️ Help & Information"):
    st.markdown("""
    ### About Months Management

    This page allows you to track working days and holidays for each month, which is used for:
    - Resource planning and allocation calculations
    - Burn rate analysis
    - Capacity planning

    ### How to Use

    **View & Edit Tab:**
    - View all months in the database sorted by year (newest first)
    - Edit working days and holidays directly in the table
    - Click "Save Changes" to commit your edits

    **Add Year Tab:**
    - Generate all 12 months for a new year automatically
    - Working days are calculated based on weekdays (Mon-Fri)
    - Optionally copy holiday counts from the previous year
    - You can edit the values after generation using the View & Edit tab

    ### Field Definitions

    - **Total Days**: Actual number of days in the month (auto-calculated, accounts for leap years)
    - **Working Days**: Number of business days (typically Mon-Fri, excluding holidays)
    - **Holidays**: Number of federal or company holidays that fall on working days

    ### Notes

    - Working days are initially calculated as all weekdays (Mon-Fri)
    - You should edit the working days to subtract holidays if needed
    - Each year/month combination can only exist once in the database
    """)
