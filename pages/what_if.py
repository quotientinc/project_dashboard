import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.logger import get_logger

logger = get_logger(__name__)

db = st.session_state.db_manager
processor = st.session_state.data_processor

st.markdown("### 🔮 What-If Scenario Analysis (🚨not ready yet)")

# Helper function to calculate revenue metrics from performance data
def calculate_project_revenue(project):
    """
    Calculate revenue_actual and revenue_projected for a project using get_performance_metrics().

    Returns:
        tuple: (revenue_actual, revenue_projected) or (0, 0) if project has no dates
    """
    # Check if project has valid dates
    if pd.isna(project['start_date']) or pd.isna(project['end_date']):
        return 0, 0

    try:
        # Get performance metrics for this project
        metrics = processor.get_performance_metrics(
            start_date=project['start_date'],
            end_date=project['end_date'],
            constraint={'project_id': str(project['id'])}
        )

        # Sum revenue from actuals (actual revenue from time_entries.amount)
        revenue_actual = 0
        for month_data in metrics.get('actuals', {}).values():
            for entity_data in month_data.values():
                revenue_actual += entity_data.get('revenue', 0)

        # Sum revenue from projected (projected revenue from allocations)
        revenue_projected = 0
        for month_data in metrics.get('projected', {}).values():
            for entity_data in month_data.values():
                revenue_projected += entity_data.get('revenue', 0)

        return revenue_actual, revenue_projected
    except Exception as e:
        logger.warning(f"Could not calculate revenue for project {project.get('name', 'Unknown')}: {e}")
        return 0, 0

# Function definitions
def project_cost_scenarios(db, processor):
    st.markdown("#### Project Cost Scenarios")

    projects_df = db.get_projects()

    if not projects_df.empty:
        selected_project = st.selectbox("Select Project", projects_df['name'].tolist())
        project = projects_df[projects_df['name'] == selected_project].iloc[0]

        # Calculate revenue metrics using performance data
        revenue_actual, revenue_projected = calculate_project_revenue(project)

        st.markdown("##### Current Baseline")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Budget Allocated", f"${project['contract_value']:,.0f}")
        with col2:
            st.metric("Budget Used", f"${project['budget_used']:,.0f}")
        with col3:
            st.metric("Revenue Actual", f"${revenue_actual:,.0f}")

        st.markdown("##### Define Scenarios")

        # Scenario inputs
        scenarios = []

        with st.expander("Scenario 1: Optimistic"):
            s1_cost_change = st.slider("Cost Change %", -50, 50, -10, key="s1_cost")
            s1_revenue_change = st.slider("Revenue Change %", -50, 50, 20, key="s1_revenue")
            s1_timeline_change = st.slider("Timeline Change (days)", -90, 90, -15, key="s1_timeline")

            scenarios.append({
                'name': 'Optimistic',
                'changes': [
                    {'type': 'multiply', 'field': 'budget_used', 'value': 1 + s1_cost_change/100},
                    {'type': 'multiply', 'field': 'revenue_actual', 'value': 1 + s1_revenue_change/100}
                ]
            })

        with st.expander("Scenario 2: Pessimistic"):
            s2_cost_change = st.slider("Cost Change %", -50, 50, 25, key="s2_cost")
            s2_revenue_change = st.slider("Revenue Change %", -50, 50, -10, key="s2_revenue")
            s2_timeline_change = st.slider("Timeline Change (days)", -90, 90, 30, key="s2_timeline")

            scenarios.append({
                'name': 'Pessimistic',
                'changes': [
                    {'type': 'multiply', 'field': 'budget_used', 'value': 1 + s2_cost_change/100},
                    {'type': 'multiply', 'field': 'revenue_actual', 'value': 1 + s2_revenue_change/100}
                ]
            })

        with st.expander("Scenario 3: Most Likely"):
            s3_cost_change = st.slider("Cost Change %", -50, 50, 5, key="s3_cost")
            s3_revenue_change = st.slider("Revenue Change %", -50, 50, 5, key="s3_revenue")
            s3_timeline_change = st.slider("Timeline Change (days)", -90, 90, 7, key="s3_timeline")

            scenarios.append({
                'name': 'Most Likely',
                'changes': [
                    {'type': 'multiply', 'field': 'budget_used', 'value': 1 + s3_cost_change/100},
                    {'type': 'multiply', 'field': 'revenue_actual', 'value': 1 + s3_revenue_change/100}
                ]
            })

        if st.button("Run Scenarios"):
            # Prepare base data
            base_data = {
                'labor_cost': project['budget_used'] * 0.7,  # Assume 70% is labor
                'expense_cost': project['budget_used'] * 0.3,  # Assume 30% is expenses
                'budget_used': project['budget_used'],
                'revenue_actual': revenue_actual,
                'total_cost': project['budget_used']
            }

            # Run profit analysis
            profit_results = processor.what_if_analysis(base_data, scenarios, 'profit')

            # Display results
            st.markdown("##### Scenario Results")

            # Results table
            results_df = pd.DataFrame()
            for scenario in scenarios + [{'name': 'Current'}]:
                if scenario['name'] == 'Current':
                    cost = project['budget_used']
                    revenue = revenue_actual
                else:
                    changes = scenario['changes']
                    cost = project['budget_used'] * changes[0]['value']
                    revenue = revenue_actual * changes[1]['value']

                profit = revenue - cost
                margin = (profit / revenue * 100) if revenue > 0 else 0

                results_df = pd.concat([results_df, pd.DataFrame({
                    'Scenario': [scenario['name']],
                    'Cost': [cost],
                    'Revenue': [revenue],
                    'Profit': [profit],
                    'Margin %': [margin]
                })])

            st.dataframe(results_df, width='stretch', hide_index=True)

            # Visualization
            fig = go.Figure()
            fig.add_trace(go.Bar(name='Cost', x=results_df['Scenario'], y=results_df['Cost'], marker_color='red'))
            fig.add_trace(go.Bar(name='Revenue', x=results_df['Scenario'], y=results_df['Revenue'], marker_color='green'))
            fig.add_trace(go.Scatter(
                name='Profit',
                x=results_df['Scenario'],
                y=results_df['Profit'],
                mode='lines+markers',
                yaxis='y2',
                line=dict(color='blue', width=2)
            ))

            fig.update_layout(
                title="Scenario Comparison",
                barmode='group',
                yaxis=dict(title="Amount ($)"),
                yaxis2=dict(title="Profit ($)", overlaying='y', side='right'),
                height=400
            )
            st.plotly_chart(fig, width='stretch')

def resource_allocation_scenarios(db, processor):
    st.markdown("#### Resource Allocation Scenarios")

    employees_df = db.get_employees()
    projects_df = db.get_projects()

    if not employees_df.empty and not projects_df.empty:
        st.markdown("##### Current Allocation")

        allocations_df = db.get_allocations()

        # Calculate current FTE by project from monthly allocations
        if not allocations_df.empty:
            # Convert allocation_date to datetime and extract month info
            allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
            allocations_df['period'] = allocations_df['allocation_date'].dt.strftime('%Y-%m')

            # Group by period and project to get FTE requirements
            current_fte = allocations_df.groupby(['period', 'project_name']).agg({
                'allocated_fte': 'sum'
            }).reset_index()
            current_fte.columns = ['period', 'project', 'fte_required']

            if not current_fte.empty:
                fig = px.bar(
                    current_fte,
                    x='period',
                    y='fte_required',
                    color='project',
                    title="Current FTE Requirements by Project"
                )
                st.plotly_chart(fig, width='stretch')
        else:
            st.info("No allocation data available to display FTE requirements.")

        st.markdown("##### Scenario Builder")

        # Add/Remove resources
        col1, col2 = st.columns(2)

        with col1:
            add_fte = st.number_input("Add FTE", min_value=0.0, max_value=10.0, step=0.5, value=0.0)
            add_rate = st.number_input("Hourly Rate for New FTE", min_value=0.0, step=10.0, value=120.0)

        with col2:
            remove_fte = st.number_input("Remove FTE", min_value=0.0, max_value=10.0, step=0.5, value=0.0)
            reallocation_pct = st.slider("Reallocation %", 0, 100, 20)

        if st.button("Analyze Impact"):
            total_employees = len(employees_df)

            # Calculate current average rate and total FTE from allocations
            if not allocations_df.empty:
                current_avg_rate = allocations_df['bill_rate'].mean()
                current_total_fte = allocations_df['allocated_fte'].sum()
            else:
                current_avg_rate = 120.0  # Default fallback
                current_total_fte = 0.0

            # Calculate scenarios
            scenarios_data = []

            # Current state
            current_capacity = current_total_fte * 160  # Monthly hours
            current_cost = current_capacity * current_avg_rate
            scenarios_data.append({
                'Scenario': 'Current',
                'Total FTE': current_total_fte,
                'Capacity (Hours)': current_capacity,
                'Monthly Cost': current_cost,
                'Avg Rate': current_avg_rate
            })

            # With added resources
            if add_fte > 0:
                new_total_fte = current_total_fte + add_fte
                new_capacity = new_total_fte * 160
                new_avg_rate = ((current_avg_rate * current_total_fte) + (add_rate * add_fte)) / new_total_fte
                new_cost = new_capacity * new_avg_rate
                scenarios_data.append({
                    'Scenario': f'+{add_fte} FTE',
                    'Total FTE': new_total_fte,
                    'Capacity (Hours)': new_capacity,
                    'Monthly Cost': new_cost,
                    'Avg Rate': new_avg_rate
                })

            # With removed resources
            if remove_fte > 0:
                reduced_fte = max(0, current_total_fte - remove_fte)
                reduced_capacity = reduced_fte * 160
                reduced_cost = reduced_capacity * current_avg_rate
                scenarios_data.append({
                    'Scenario': f'-{remove_fte} FTE',
                    'Total FTE': reduced_fte,
                    'Capacity (Hours)': reduced_capacity,
                    'Monthly Cost': reduced_cost,
                    'Avg Rate': current_avg_rate
                })

            # Display results
            scenarios_df = pd.DataFrame(scenarios_data)
            st.dataframe(scenarios_df, width='stretch', hide_index=True)

            # Impact visualization
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name='Capacity',
                x=scenarios_df['Scenario'],
                y=scenarios_df['Capacity (Hours)'],
                yaxis='y',
                marker_color='lightblue'
            ))
            fig.add_trace(go.Scatter(
                name='Cost',
                x=scenarios_df['Scenario'],
                y=scenarios_df['Monthly Cost'],
                yaxis='y2',
                mode='lines+markers',
                line=dict(color='red', width=2)
            ))

            fig.update_layout(
                title="Resource Scenario Impact",
                yaxis=dict(title="Capacity (Hours)"),
                yaxis2=dict(title="Monthly Cost ($)", overlaying='y', side='right'),
                height=400
            )
            st.plotly_chart(fig, width='stretch')

def revenue_projection_scenarios(db, processor):
    st.markdown("#### Revenue Projection Scenarios")

    projects_df = db.get_projects()

    if not projects_df.empty:
        # Calculate revenue for all projects using performance metrics
        current_revenue = 0
        projected_revenue = 0
        for _, project in projects_df.iterrows():
            rev_actual, rev_projected = calculate_project_revenue(project)
            current_revenue += rev_actual
            projected_revenue += rev_projected

        st.markdown("##### Current State")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Actual Revenue", f"${current_revenue:,.0f}")
        with col2:
            st.metric("Projected Revenue", f"${projected_revenue:,.0f}")
        with col3:
            achievement = (current_revenue / projected_revenue * 100) if projected_revenue > 0 else 0
            st.metric("Achievement", f"{achievement:.1f}%")

        st.markdown("##### Revenue Scenarios")

        # Scenario parameters
        col1, col2 = st.columns(2)

        with col1:
            new_projects = st.number_input("New Projects", min_value=0, max_value=10, value=2)
            avg_project_value = st.number_input("Avg Project Value", min_value=0, step=10000, value=100000)

        with col2:
            growth_rate = st.slider("Growth Rate %", -20, 50, 10)
            win_rate = st.slider("Win Rate %", 0, 100, 60)

        if st.button("Project Revenue"):
            # Calculate projections
            months = 12
            projections = []

            for month in range(1, months + 1):
                # Base revenue with growth
                base_revenue = current_revenue / 12 * (1 + growth_rate/100) ** (month/12)

                # New project revenue
                new_revenue = (new_projects * avg_project_value * win_rate/100) / 12

                # Total projection
                total = base_revenue + new_revenue

                projections.append({
                    'Month': f'Month {month}',
                    'Base Revenue': base_revenue,
                    'New Revenue': new_revenue,
                    'Total Revenue': total
                })

            projections_df = pd.DataFrame(projections)
            projections_df['Cumulative'] = projections_df['Total Revenue'].cumsum()

            # Display projections
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name='Base Revenue',
                x=projections_df['Month'],
                y=projections_df['Base Revenue'],
                marker_color='lightblue'
            ))
            fig.add_trace(go.Bar(
                name='New Revenue',
                x=projections_df['Month'],
                y=projections_df['New Revenue'],
                marker_color='lightgreen'
            ))
            fig.add_trace(go.Scatter(
                name='Cumulative',
                x=projections_df['Month'],
                y=projections_df['Cumulative'],
                mode='lines',
                yaxis='y2',
                line=dict(color='orange', width=2)
            ))

            fig.update_layout(
                title="Revenue Projections",
                barmode='stack',
                yaxis=dict(title="Monthly Revenue ($)"),
                yaxis2=dict(title="Cumulative ($)", overlaying='y', side='right'),
                height=400
            )
            st.plotly_chart(fig, width='stretch')

            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                total_projected = projections_df['Total Revenue'].sum()
                st.metric("12-Month Projection", f"${total_projected:,.0f}")
            with col2:
                monthly_avg = projections_df['Total Revenue'].mean()
                st.metric("Monthly Average", f"${monthly_avg:,.0f}")
            with col3:
                growth = ((total_projected - current_revenue) / current_revenue * 100)
                st.metric("Growth %", f"{growth:.1f}%")

def burn_rate_scenarios(db, processor):
    st.markdown("#### Burn Rate Scenarios")

    expenses_df = db.get_expenses()

    if not expenses_df.empty:
        current_burn = processor.calculate_burn_rate(expenses_df, 'monthly')

        if not current_burn.empty:
            avg_burn = current_burn['burn_rate'].mean()

            st.markdown("##### Current Burn Rate")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Average Monthly Burn", f"${avg_burn:,.0f}")
            with col2:
                st.metric("Total Burned", f"${current_burn['burn_rate'].sum():,.0f}")
            with col3:
                runway_months = 50000 / avg_burn if avg_burn > 0 else 0  # Assume $50k cash
                st.metric("Runway (Months)", f"{runway_months:.1f}")

            st.markdown("##### Burn Rate Scenarios")

            # Scenario inputs
            col1, col2 = st.columns(2)

            with col1:
                cost_reduction = st.slider("Cost Reduction %", 0, 50, 10)
                headcount_change = st.slider("Headcount Change", -5, 5, 0)

            with col2:
                efficiency_gain = st.slider("Efficiency Gain %", 0, 30, 10)
                cash_injection = st.number_input("Cash Injection", min_value=0, step=10000, value=0)

            if st.button("Calculate Scenarios"):
                scenarios_data = []

                # Current scenario
                cash_balance = 50000
                scenarios_data.append({
                    'Scenario': 'Current',
                    'Monthly Burn': avg_burn,
                    'Cash Balance': cash_balance,
                    'Runway (Months)': cash_balance / avg_burn if avg_burn > 0 else 0
                })

                # Optimized scenario
                optimized_burn = avg_burn * (1 - cost_reduction/100) * (1 - efficiency_gain/100)
                optimized_burn += headcount_change * 10000  # Assume $10k per headcount
                optimized_cash = cash_balance + cash_injection
                scenarios_data.append({
                    'Scenario': 'Optimized',
                    'Monthly Burn': optimized_burn,
                    'Cash Balance': optimized_cash,
                    'Runway (Months)': optimized_cash / optimized_burn if optimized_burn > 0 else 0
                })

                # Worst case
                worst_burn = avg_burn * 1.3  # 30% increase
                scenarios_data.append({
                    'Scenario': 'Worst Case',
                    'Monthly Burn': worst_burn,
                    'Cash Balance': cash_balance,
                    'Runway (Months)': cash_balance / worst_burn if worst_burn > 0 else 0
                })

                # Display results
                scenarios_df = pd.DataFrame(scenarios_data)
                st.dataframe(scenarios_df, width='stretch', hide_index=True)

                # Runway visualization
                fig = go.Figure()
                for _, scenario in scenarios_df.iterrows():
                    months = range(int(scenario['Runway (Months)']) + 1)
                    balance = [scenario['Cash Balance'] - (scenario['Monthly Burn'] * m) for m in months]
                    balance = [max(0, b) for b in balance]

                    fig.add_trace(go.Scatter(
                        x=list(months),
                        y=balance,
                        mode='lines',
                        name=scenario['Scenario']
                    ))

                fig.update_layout(
                    title="Cash Runway Scenarios",
                    xaxis_title="Months",
                    yaxis_title="Cash Balance ($)",
                    height=400
                )
                st.plotly_chart(fig, width='stretch')

# Scenario type selection
scenario_type = st.selectbox(
    "Select Scenario Type",
    ["Project Cost Scenarios", "Resource Allocation", "Revenue Projections", "Burn Rate Analysis"]
)

# Call the appropriate function
if scenario_type == "Project Cost Scenarios":
    project_cost_scenarios(db, processor)
elif scenario_type == "Resource Allocation":
    resource_allocation_scenarios(db, processor)
elif scenario_type == "Revenue Projections":
    revenue_projection_scenarios(db, processor)
else:
    burn_rate_scenarios(db, processor)