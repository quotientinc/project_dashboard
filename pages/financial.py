import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta


db = st.session_state.db_manager
processor = st.session_state.data_processor
filters = st.session_state.filters

st.markdown("### 💰 Financial Analysis")

# Load data
projects_df = db.get_projects()
expenses_df = db.get_expenses()
time_entries_df = db.get_time_entries()
allocations_df = db.get_allocations()

# Key Financial Metrics
st.markdown("#### Key Financial Metrics")
col1, col2, col3, col4 = st.columns(4)

with col1:
    total_revenue = projects_df['revenue_actual'].sum()
    st.metric("Total Revenue", f"${total_revenue:,.0f}")

with col2:
    total_costs = projects_df['budget_used'].sum()
    st.metric("Total Costs", f"${total_costs:,.0f}")

with col3:
    gross_profit = total_revenue - total_costs
    st.metric("Gross Profit", f"${gross_profit:,.0f}")

with col4:
    profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
    st.metric("Profit Margin", f"{profit_margin:.1f}%")

st.markdown("---")

# Tabs for different financial views
tab1, tab2, tab3, tab4 = st.tabs(["Revenue Analysis", "Cost Analysis", "Burn Rate", "Cash Flow"])

with tab1:
    st.markdown("#### Revenue Analysis")
    
    if not projects_df.empty:
        # Revenue by project
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Projected',
            x=projects_df['name'],
            y=projects_df['revenue_projected'],
            marker_color='lightblue'
        ))
        fig.add_trace(go.Bar(
            name='Actual',
            x=projects_df['name'],
            y=projects_df['revenue_actual'],
            marker_color='darkblue'
        ))
        fig.update_layout(
            title="Revenue: Projected vs Actual",
            barmode='group',
            height=400,
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Revenue by client
        client_revenue = projects_df.groupby('client')['revenue_actual'].sum().reset_index()
        fig = px.pie(
            client_revenue,
            values='revenue_actual',
            names='client',
            title="Revenue by Client"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Revenue trends
        if not time_entries_df.empty:
            time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
            time_entries_df['revenue'] = time_entries_df['hours'] * time_entries_df['hourly_rate']
            # Group by month using to_timestamp to avoid Period serialization issues
            time_entries_df['month'] = time_entries_df['date'].dt.to_period('M').dt.to_timestamp()
            monthly_revenue = time_entries_df.groupby('month')['revenue'].sum().reset_index()
            monthly_revenue.columns = ['date', 'revenue']

            fig = px.line(
                monthly_revenue,
                x='date',
                y='revenue',
                title="Monthly Revenue Trend",
                markers=True
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown("#### Cost Analysis")
    
    # Cost breakdown
    col1, col2 = st.columns(2)
    
    with col1:
        if not time_entries_df.empty:
            labor_costs = (time_entries_df['hours'] * time_entries_df['hourly_rate']).sum()
        else:
            labor_costs = 0
        
        if not expenses_df.empty:
            expense_costs = expenses_df['amount'].sum()
        else:
            expense_costs = 0
        
        total_costs = labor_costs + expense_costs
        
        cost_data = pd.DataFrame({
            'Category': ['Labor', 'Expenses'],
            'Amount': [labor_costs, expense_costs]
        })
        
        fig = px.pie(
            cost_data,
            values='Amount',
            names='Category',
            title="Cost Distribution"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if not expenses_df.empty:
            category_costs = expenses_df.groupby('category')['amount'].sum().reset_index()
            fig = px.bar(
                category_costs,
                x='category',
                y='amount',
                title="Expenses by Category"
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
    
    # Project costs comparison
    if not projects_df.empty:
        project_costs = []
        for _, project in projects_df.iterrows():
            costs = processor.calculate_project_costs(
                project['id'],
                allocations_df,
                expenses_df,
                time_entries_df
            )
            project_costs.append({
                'Project': project['name'],
                'Labor Cost': costs['labor_cost'],
                'Expense Cost': costs['expense_cost'],
                'Total Cost': costs['total_cost']
            })
        
        costs_df = pd.DataFrame(project_costs)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Labor', x=costs_df['Project'], y=costs_df['Labor Cost']))
        fig.add_trace(go.Bar(name='Expenses', x=costs_df['Project'], y=costs_df['Expense Cost']))
        fig.update_layout(
            title="Cost Breakdown by Project",
            barmode='stack',
            height=400,
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.markdown("#### Burn Rate Analysis")
    
    if not expenses_df.empty:
        # Calculate burn rate
        time_period = st.selectbox("Time Period", ["Daily", "Weekly", "Monthly"])
        period_map = {"Daily": "daily", "Weekly": "weekly", "Monthly": "monthly"}
        
        burn_rate_df = processor.calculate_burn_rate(expenses_df, period_map[time_period])
        
        if not burn_rate_df.empty:
            # Burn rate chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=burn_rate_df['period'].astype(str),
                y=burn_rate_df['burn_rate'],
                mode='lines+markers',
                name='Burn Rate',
                line=dict(color='orange', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=burn_rate_df['period'].astype(str),
                y=burn_rate_df['cumulative_burn'],
                mode='lines',
                name='Cumulative',
                line=dict(color='red', width=2, dash='dash'),
                yaxis='y2'
            ))
            fig.update_layout(
                title=f"{time_period} Burn Rate",
                height=400,
                yaxis=dict(title="Burn Rate ($)"),
                yaxis2=dict(title="Cumulative ($)", overlaying='y', side='right')
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Burn rate metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                avg_burn = burn_rate_df['burn_rate'].mean()
                st.metric("Average Burn Rate", f"${avg_burn:,.0f}")
            with col2:
                max_burn = burn_rate_df['burn_rate'].max()
                st.metric("Max Burn Rate", f"${max_burn:,.0f}")
            with col3:
                total_burn = burn_rate_df['burn_rate'].sum()
                st.metric("Total Burned", f"${total_burn:,.0f}")
    else:
        st.info("No expense data available for burn rate analysis")

with tab4:
    st.markdown("#### Cash Flow Analysis")
    
    # Create cash flow data
    if not projects_df.empty and not expenses_df.empty:
        # Simplified cash flow calculation
        projects_df['start_date'] = pd.to_datetime(projects_df['start_date'])
        expenses_df['date'] = pd.to_datetime(expenses_df['date'])
        
        # Monthly cash flow
        date_range = pd.date_range(
            start=projects_df['start_date'].min(),
            end=datetime.now(),
            freq='M'
        )
        
        cash_flow_data = []
        for date in date_range:
            month_start = date.replace(day=1)
            month_end = (month_start + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
            
            # Income (simplified - distributed evenly)
            monthly_income = projects_df['revenue_actual'].sum() / len(date_range)
            
            # Expenses
            month_expenses = expenses_df[
                (expenses_df['date'] >= month_start) &
                (expenses_df['date'] <= month_end)
            ]['amount'].sum()
            
            net_cash_flow = monthly_income - month_expenses
            
            cash_flow_data.append({
                'Month': date.strftime('%Y-%m'),
                'Income': monthly_income,
                'Expenses': month_expenses,
                'Net Cash Flow': net_cash_flow
            })
        
        cash_flow_df = pd.DataFrame(cash_flow_data)
        cash_flow_df['Cumulative'] = cash_flow_df['Net Cash Flow'].cumsum()
        
        # Cash flow chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Income',
            x=cash_flow_df['Month'],
            y=cash_flow_df['Income'],
            marker_color='green'
        ))
        fig.add_trace(go.Bar(
            name='Expenses',
            x=cash_flow_df['Month'],
            y=-cash_flow_df['Expenses'],
            marker_color='red'
        ))
        fig.add_trace(go.Scatter(
            name='Cumulative',
            x=cash_flow_df['Month'],
            y=cash_flow_df['Cumulative'],
            mode='lines',
            line=dict(color='blue', width=2),
            yaxis='y2'
        ))
        fig.update_layout(
            title="Monthly Cash Flow",
            barmode='relative',
            height=400,
            yaxis=dict(title="Amount ($)"),
            yaxis2=dict(title="Cumulative ($)", overlaying='y', side='right')
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Cash flow metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Avg Monthly Income", f"${cash_flow_df['Income'].mean():,.0f}")
        with col2:
            st.metric("Avg Monthly Expenses", f"${cash_flow_df['Expenses'].mean():,.0f}")
        with col3:
            st.metric("Avg Net Cash Flow", f"${cash_flow_df['Net Cash Flow'].mean():,.0f}")
        with col4:
            st.metric("Current Balance", f"${cash_flow_df['Cumulative'].iloc[-1]:,.0f}")
    else:
        st.info("Insufficient data for cash flow analysis")
