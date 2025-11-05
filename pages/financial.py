import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

# Get current year
current_year = datetime.now().year

# Year selector (default to current year)
selected_year = st.selectbox(
    "Select Year",
    options=[current_year - 1, current_year, current_year + 1],
    index=1,  # Default to current year
    help="Financial analysis for the selected calendar year"
)

st.markdown(f"### 💰 Financial Analysis - {selected_year} (🚨not ready yet)")

# Load data filtered to selected year
projects_df = db.get_projects()

# Filter projects active in selected year (start or end date within year)
year_start = f"{selected_year}-01-01"
year_end = f"{selected_year}-12-31"

if not projects_df.empty:
    projects_df['start_date_dt'] = pd.to_datetime(projects_df['start_date'])
    projects_df['end_date_dt'] = pd.to_datetime(projects_df['end_date'])

    # Keep projects that overlap with selected year
    projects_df = projects_df[
        (projects_df['start_date_dt'] <= year_end) &
        (projects_df['end_date_dt'] >= year_start)
    ]

# Get time entries for selected year
time_entries_df = db.get_time_entries()
if not time_entries_df.empty:
    time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
    time_entries_df = time_entries_df[time_entries_df['date'].dt.year == selected_year]

# Get expenses for selected year
expenses_df = db.get_expenses()
if not expenses_df.empty:
    expenses_df['date'] = pd.to_datetime(expenses_df['date'])
    expenses_df = expenses_df[expenses_df['date'].dt.year == selected_year]

# Get allocations for selected year
allocations_df = db.get_allocations()
if not allocations_df.empty:
    allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
    allocations_df = allocations_df[allocations_df['allocation_date'].dt.year == selected_year]

# Calculate YTD actuals from time_entries
ytd_revenue = 0
ytd_labor_cost = 0

if not time_entries_df.empty:
    # Revenue calculation
    def calculate_entry_revenue(row):
        if pd.notna(row.get('amount')) and row['amount'] != 0:
            return row['amount']
        elif pd.notna(row.get('hourly_rate')) and pd.notna(row.get('hours')):
            return row['hours'] * row['hourly_rate']
        return 0

    time_entries_df['revenue'] = time_entries_df.apply(calculate_entry_revenue, axis=1)
    ytd_revenue = time_entries_df['revenue'].sum()
    ytd_labor_cost = ytd_revenue  # Labor cost equals revenue for billable work

# Expense costs
ytd_expense_cost = expenses_df['amount'].sum() if not expenses_df.empty else 0
ytd_total_cost = ytd_labor_cost + ytd_expense_cost

# Metrics
ytd_profit = ytd_revenue - ytd_total_cost
ytd_margin = (ytd_profit / ytd_revenue * 100) if ytd_revenue > 0 else 0

# Display key metrics
st.markdown("#### Year-to-Date Performance")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("YTD Revenue", f"${ytd_revenue:,.0f}")
with col2:
    st.metric("YTD Costs", f"${ytd_total_cost:,.0f}",
              help=f"Labor: ${ytd_labor_cost:,.0f} | Expenses: ${ytd_expense_cost:,.0f}")
with col3:
    st.metric("YTD Profit", f"${ytd_profit:,.0f}")
with col4:
    st.metric("YTD Margin", f"{ytd_margin:.1f}%")

st.markdown("---")

# Tabs for focused analysis
tab1, tab2, tab3 = st.tabs(["Monthly Trends", "Client Analysis", "Full Year Forecast"])

with tab1:
    st.markdown("#### 📈 Monthly Trends")

    if not time_entries_df.empty:
        # Prepare monthly data
        monthly_df = time_entries_df.copy()
        monthly_df['month'] = monthly_df['date'].dt.to_period('M').astype(str)

        # Calculate monthly revenue
        monthly_revenue = monthly_df.groupby('month')['revenue'].sum().reset_index()
        monthly_revenue.columns = ['Month', 'Revenue']

        # Calculate monthly labor costs (same as revenue for billable)
        monthly_labor = monthly_df.groupby('month')['revenue'].sum().reset_index()
        monthly_labor.columns = ['Month', 'Labor Cost']

        # Calculate monthly expenses
        if not expenses_df.empty:
            exp_df = expenses_df.copy()
            exp_df['month'] = exp_df['date'].dt.to_period('M').astype(str)
            monthly_expenses = exp_df.groupby('month')['amount'].sum().reset_index()
            monthly_expenses.columns = ['Month', 'Expenses']
        else:
            monthly_expenses = pd.DataFrame(columns=['Month', 'Expenses'])

        # Merge all monthly data
        monthly_combined = monthly_revenue.merge(monthly_labor, on='Month', how='outer')
        monthly_combined = monthly_combined.merge(monthly_expenses, on='Month', how='outer').fillna(0)
        monthly_combined['Total Cost'] = monthly_combined['Labor Cost'] + monthly_combined['Expenses']
        monthly_combined['Profit'] = monthly_combined['Revenue'] - monthly_combined['Total Cost']
        monthly_combined['Margin %'] = (monthly_combined['Profit'] / monthly_combined['Revenue'] * 100).fillna(0)

        # Sort by month
        monthly_combined = monthly_combined.sort_values('Month')

        # Chart: Revenue, Cost, and Profit by Month
        fig = go.Figure()

        fig.add_trace(go.Bar(
            name='Revenue',
            x=monthly_combined['Month'],
            y=monthly_combined['Revenue'],
            marker_color='#2E86C1'
        ))

        fig.add_trace(go.Bar(
            name='Total Cost',
            x=monthly_combined['Month'],
            y=monthly_combined['Total Cost'],
            marker_color='#E74C3C'
        ))

        fig.add_trace(go.Scatter(
            name='Profit',
            x=monthly_combined['Month'],
            y=monthly_combined['Profit'],
            mode='lines+markers',
            line=dict(color='#27AE60', width=3),
            yaxis='y2'
        ))

        fig.update_layout(
            title=f"Monthly Revenue, Costs & Profit - {selected_year}",
            xaxis_title="Month",
            yaxis_title="Revenue & Costs ($)",
            yaxis2=dict(
                title="Profit ($)",
                overlaying='y',
                side='right'
            ),
            barmode='group',
            height=400,
            hovermode='x unified'
        )

        st.plotly_chart(fig, use_container_width=True)

        # Display monthly breakdown table
        st.markdown("##### Monthly Breakdown")
        display_monthly = monthly_combined.copy()
        display_monthly['Revenue'] = display_monthly['Revenue'].apply(lambda x: f"${x:,.0f}")
        display_monthly['Total Cost'] = display_monthly['Total Cost'].apply(lambda x: f"${x:,.0f}")
        display_monthly['Profit'] = display_monthly['Profit'].apply(lambda x: f"${x:,.0f}")
        display_monthly['Margin %'] = display_monthly['Margin %'].apply(lambda x: f"{x:.1f}%")

        st.dataframe(display_monthly, use_container_width=True, hide_index=True)
    else:
        st.info(f"No time entry data found for {selected_year}")

with tab2:
    st.markdown("#### 🏢 Client Analysis")

    if not time_entries_df.empty and not projects_df.empty:
        # Join time_entries with projects to get client info
        client_df = time_entries_df.merge(
            projects_df[['id', 'client']],
            left_on='project_id',
            right_on='id',
            how='left'
        )

        # Calculate revenue by client
        client_revenue = client_df.groupby('client')['revenue'].sum().reset_index()
        client_revenue.columns = ['Client', 'Revenue']

        # Get labor costs by client (same as revenue for billable)
        client_labor = client_df.groupby('client')['revenue'].sum().reset_index()
        client_labor.columns = ['Client', 'Labor Cost']

        # Get expenses by client (via project)
        if not expenses_df.empty:
            exp_client = expenses_df.merge(
                projects_df[['id', 'client']],
                left_on='project_id',
                right_on='id',
                how='left'
            )
            client_expenses = exp_client.groupby('client')['amount'].sum().reset_index()
            client_expenses.columns = ['Client', 'Expenses']
        else:
            client_expenses = pd.DataFrame(columns=['Client', 'Expenses'])

        # Combine client data
        client_summary = client_revenue.merge(client_labor, on='Client', how='outer')
        client_summary = client_summary.merge(client_expenses, on='Client', how='outer').fillna(0)
        client_summary['Total Cost'] = client_summary['Labor Cost'] + client_summary['Expenses']
        client_summary['Profit'] = client_summary['Revenue'] - client_summary['Total Cost']
        client_summary['Margin %'] = (client_summary['Profit'] / client_summary['Revenue'] * 100).fillna(0)

        # Sort by revenue descending
        client_summary = client_summary.sort_values('Revenue', ascending=False)

        # Chart 1: Revenue by Client (Pie)
        col1, col2 = st.columns(2)

        with col1:
            fig_pie = px.pie(
                client_summary,
                values='Revenue',
                names='Client',
                title=f"Revenue by Client - {selected_year}"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            # Chart 2: Profit Margin by Client (Bar)
            fig_margin = go.Figure()
            fig_margin.add_trace(go.Bar(
                x=client_summary['Client'],
                y=client_summary['Margin %'],
                marker_color=client_summary['Margin %'].apply(
                    lambda x: '#27AE60' if x > 20 else '#F39C12' if x > 0 else '#E74C3C'
                ),
                text=client_summary['Margin %'].apply(lambda x: f"{x:.1f}%"),
                textposition='outside'
            ))
            fig_margin.update_layout(
                title=f"Profit Margin by Client - {selected_year}",
                xaxis_title="Client",
                yaxis_title="Margin %",
                height=400
            )
            st.plotly_chart(fig_margin, use_container_width=True)

        # Client summary table
        st.markdown("##### Client Summary")
        display_client = client_summary.copy()
        display_client['Revenue'] = display_client['Revenue'].apply(lambda x: f"${x:,.0f}")
        display_client['Total Cost'] = display_client['Total Cost'].apply(lambda x: f"${x:,.0f}")
        display_client['Profit'] = display_client['Profit'].apply(lambda x: f"${x:,.0f}")
        display_client['Margin %'] = display_client['Margin %'].apply(lambda x: f"{x:.1f}%")

        st.dataframe(display_client, use_container_width=True, hide_index=True)
    else:
        st.info(f"No data found for {selected_year}")

with tab3:
    st.markdown("#### 🔮 Full Year Forecast")

    # Projection method toggle
    projection_method = st.radio(
        "Projection Method",
        options=["Allocations-Based", "Simple Average"],
        horizontal=True,
        help="Allocations-Based uses planned allocations for future months. Simple Average uses YTD monthly average."
    )

    # Get current month
    current_month = datetime.now().month

    # Only show forecast for current year
    if selected_year == current_year:
        # Calculate YTD months and remaining months
        ytd_months = current_month
        remaining_months = 12 - current_month

        if not time_entries_df.empty:
            # YTD actuals by month
            ytd_df = time_entries_df.copy()
            ytd_df['month_num'] = ytd_df['date'].dt.month
            ytd_monthly = ytd_df.groupby('month_num')['revenue'].sum().to_dict()

            # Calculate projections
            forecast_data = []

            if projection_method == "Simple Average":
                # Simple average of YTD months
                ytd_avg = ytd_revenue / ytd_months if ytd_months > 0 else 0
                projected_remaining = ytd_avg * remaining_months

                # Build full year forecast
                for month in range(1, 13):
                    if month <= current_month:
                        # Actual data
                        revenue = ytd_monthly.get(month, 0)
                        data_type = 'Actual'
                    else:
                        # Projected
                        revenue = ytd_avg
                        data_type = 'Projected (Avg)'

                    forecast_data.append({
                        'Month': month,
                        'Month Name': datetime(selected_year, month, 1).strftime('%B'),
                        'Revenue': revenue,
                        'Type': data_type
                    })

            else:  # Allocations-Based
                # Use allocations for smart projections
                if not allocations_df.empty:
                    # Get projected data from allocations
                    projected_monthly = {}

                    for month_num in range(current_month + 1, 13):
                        month_str = f"{selected_year}-{month_num:02d}"
                        month_allocs = allocations_df[
                            allocations_df['allocation_date'].dt.strftime('%Y-%m') == month_str
                        ]

                        if not month_allocs.empty:
                            # Calculate projected revenue from allocations
                            # allocated_fte × bill_rate × working_days × 8 hours/day
                            months_df = db.get_months()
                            month_info = months_df[
                                (months_df['year'] == selected_year) &
                                (months_df['month'] == month_num)
                            ]

                            if not month_info.empty:
                                working_days = month_info['working_days'].iloc[0]

                                month_revenue = 0
                                for _, alloc in month_allocs.iterrows():
                                    if pd.notna(alloc.get('bill_rate')) and pd.notna(alloc.get('allocated_fte')):
                                        hours = working_days * alloc['allocated_fte'] * 8
                                        month_revenue += hours * alloc['bill_rate']

                                projected_monthly[month_num] = month_revenue

                    # Build full year forecast
                    for month in range(1, 13):
                        if month <= current_month:
                            # Actual data
                            revenue = ytd_monthly.get(month, 0)
                            data_type = 'Actual'
                        else:
                            # Projected from allocations
                            revenue = projected_monthly.get(month, 0)
                            data_type = 'Projected (Alloc)'

                        forecast_data.append({
                            'Month': month,
                            'Month Name': datetime(selected_year, month, 1).strftime('%B'),
                            'Revenue': revenue,
                            'Type': data_type
                        })
                else:
                    st.warning("No allocation data available for future months. Using Simple Average instead.")
                    # Fall back to simple average
                    ytd_avg = ytd_revenue / ytd_months if ytd_months > 0 else 0

                    for month in range(1, 13):
                        if month <= current_month:
                            revenue = ytd_monthly.get(month, 0)
                            data_type = 'Actual'
                        else:
                            revenue = ytd_avg
                            data_type = 'Projected (Avg)'

                        forecast_data.append({
                            'Month': month,
                            'Month Name': datetime(selected_year, month, 1).strftime('%B'),
                            'Revenue': revenue,
                            'Type': data_type
                        })

            forecast_df = pd.DataFrame(forecast_data)

            # Calculate full year projection
            full_year_projected = forecast_df['Revenue'].sum()
            projected_remaining_rev = forecast_df[forecast_df['Type'].str.contains('Projected')]['Revenue'].sum()

            # Display forecast metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("YTD Actual", f"${ytd_revenue:,.0f}")
            with col2:
                st.metric("Projected Remaining", f"${projected_remaining_rev:,.0f}")
            with col3:
                st.metric("Full Year Forecast", f"${full_year_projected:,.0f}")

            # Chart: Full year forecast
            fig = go.Figure()

            # Actual bars
            actual_data = forecast_df[forecast_df['Type'] == 'Actual']
            fig.add_trace(go.Bar(
                name='Actual',
                x=actual_data['Month Name'],
                y=actual_data['Revenue'],
                marker_color='#2E86C1'
            ))

            # Projected bars
            projected_data = forecast_df[forecast_df['Type'].str.contains('Projected')]
            fig.add_trace(go.Bar(
                name='Projected',
                x=projected_data['Month Name'],
                y=projected_data['Revenue'],
                marker_color='#85C1E2',
                marker_pattern_shape="/"
            ))

            fig.update_layout(
                title=f"Full Year Revenue Forecast - {selected_year}",
                xaxis_title="Month",
                yaxis_title="Revenue ($)",
                height=400,
                hovermode='x unified'
            )

            st.plotly_chart(fig, use_container_width=True)

            # Forecast table
            st.markdown("##### Monthly Forecast")
            display_forecast = forecast_df.copy()
            display_forecast['Revenue'] = display_forecast['Revenue'].apply(lambda x: f"${x:,.0f}")
            display_forecast = display_forecast[['Month Name', 'Revenue', 'Type']]
            display_forecast.columns = ['Month', 'Revenue', 'Data Type']

            st.dataframe(display_forecast, use_container_width=True, hide_index=True)
        else:
            st.info(f"No data found for {selected_year}")
    else:
        # For past/future years, just show actuals
        st.info(f"Forecast is only available for the current year ({current_year}). Showing actual data for {selected_year}.")

        if not time_entries_df.empty:
            # Show actual monthly revenue for selected year
            ytd_df = time_entries_df.copy()
            ytd_df['month_num'] = ytd_df['date'].dt.month
            monthly_actual = ytd_df.groupby('month_num')['revenue'].sum().reset_index()
            monthly_actual['Month Name'] = monthly_actual['month_num'].apply(
                lambda x: datetime(selected_year, x, 1).strftime('%B')
            )
            monthly_actual = monthly_actual.rename(columns={'revenue': 'Revenue'})

            # Chart
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=monthly_actual['Month Name'],
                y=monthly_actual['Revenue'],
                marker_color='#2E86C1'
            ))

            fig.update_layout(
                title=f"Actual Revenue by Month - {selected_year}",
                xaxis_title="Month",
                yaxis_title="Revenue ($)",
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)

            # Table
            display_actual = monthly_actual[['Month Name', 'Revenue']].copy()
            display_actual['Revenue'] = display_actual['Revenue'].apply(lambda x: f"${x:,.0f}")
            st.dataframe(display_actual, use_container_width=True, hide_index=True)
