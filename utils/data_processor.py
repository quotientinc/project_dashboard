import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

class DataProcessor:
    """Process and analyze project management data"""
    
    @staticmethod
    def calculate_burn_rate(expenses_df: pd.DataFrame, time_period: str = 'monthly') -> pd.DataFrame:
        """Calculate burn rate over time"""
        if expenses_df.empty:
            return pd.DataFrame()
        
        expenses_df['date'] = pd.to_datetime(expenses_df['date'])
        
        if time_period == 'daily':
            grouped = expenses_df.groupby(expenses_df['date'].dt.date)
        elif time_period == 'weekly':
            grouped = expenses_df.groupby(expenses_df['date'].dt.to_period('W'))
        elif time_period == 'monthly':
            grouped = expenses_df.groupby(expenses_df['date'].dt.to_period('M'))
        else:
            grouped = expenses_df.groupby(expenses_df['date'].dt.to_period('Y'))
        
        burn_rate = grouped['amount'].sum().reset_index()
        burn_rate.columns = ['period', 'burn_rate']

        # Convert Period objects to strings for JSON serialization
        if time_period != 'daily':
            burn_rate['period'] = burn_rate['period'].astype(str)

        # Calculate cumulative burn
        burn_rate['cumulative_burn'] = burn_rate['burn_rate'].cumsum()

        return burn_rate
    
    @staticmethod
    def calculate_project_health(project_df: pd.DataFrame, allocations_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate project health metrics"""
        if project_df.empty:
            return pd.DataFrame()
        
        health_metrics = project_df.copy()
        
        # Budget health
        health_metrics['budget_health'] = (
            (health_metrics['budget_allocated'] - health_metrics['budget_used']) / 
            health_metrics['budget_allocated'] * 100
        ).fillna(0)
        
        # Schedule health (days remaining vs total days)
        health_metrics['start_date'] = pd.to_datetime(health_metrics['start_date'])
        health_metrics['end_date'] = pd.to_datetime(health_metrics['end_date'])
        today = pd.Timestamp.now()
        
        total_days = (health_metrics['end_date'] - health_metrics['start_date']).dt.days
        days_elapsed = (today - health_metrics['start_date']).dt.days
        health_metrics['schedule_progress'] = (days_elapsed / total_days * 100).clip(0, 100)
        
        # Revenue vs Cost
        health_metrics['profit_margin'] = (
            (health_metrics['revenue_actual'] - health_metrics['budget_used']) / 
            health_metrics['revenue_actual'] * 100
        ).fillna(0)
        
        # Overall health score
        health_metrics['health_score'] = (
            health_metrics['budget_health'].clip(0, 100) * 0.3 +
            (100 - abs(health_metrics['schedule_progress'] - 50)) * 0.3 +
            health_metrics['profit_margin'].clip(0, 100) * 0.4
        ).round(1)
        
        return health_metrics
    
    @staticmethod
    def calculate_employee_utilization(
        employees_df: pd.DataFrame, 
        allocations_df: pd.DataFrame,
        time_entries_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Calculate employee utilization metrics"""
        if employees_df.empty:
            return pd.DataFrame()
        
        utilization = employees_df.copy()
        
        # Calculate allocated hours
        if not allocations_df.empty:
            allocated = allocations_df.groupby('employee_id').agg({
                'allocation_percent': 'sum',
                'hours_projected': 'sum',
                'hours_actual': 'sum'
            }).reset_index()
            
            utilization = utilization.merge(allocated, left_on='id', right_on='employee_id', how='left')
            utilization['allocation_percent'] = utilization['allocation_percent'].fillna(0)
            utilization['hours_projected'] = utilization['hours_projected'].fillna(0)
            utilization['hours_actual'] = utilization['hours_actual'].fillna(0)
        else:
            utilization['allocation_percent'] = 0
            utilization['hours_projected'] = 0
            utilization['hours_actual'] = 0
        
        # Calculate billable vs non-billable hours
        if not time_entries_df.empty:
            billable = time_entries_df.groupby(['employee_id', 'billable'])['hours'].sum().unstack(fill_value=0)
            if 1 in billable.columns:
                billable_hours = billable[1].reset_index()
                billable_hours.columns = ['employee_id', 'billable_hours']
                utilization = utilization.merge(billable_hours, left_on='id', right_on='employee_id', how='left')
                utilization['billable_hours'] = utilization['billable_hours'].fillna(0)
            else:
                utilization['billable_hours'] = 0
            
            total_hours = time_entries_df.groupby('employee_id')['hours'].sum().reset_index()
            total_hours.columns = ['employee_id', 'total_hours']
            utilization = utilization.merge(total_hours, left_on='id', right_on='employee_id', how='left')
            utilization['total_hours'] = utilization['total_hours'].fillna(0)
        else:
            utilization['billable_hours'] = 0
            utilization['total_hours'] = 0
        
        # Calculate utilization rate
        standard_hours = 160  # Monthly standard hours
        utilization['utilization_rate'] = (utilization['total_hours'] / standard_hours * 100).clip(0, 100)
        utilization['billable_rate'] = np.where(
            utilization['total_hours'] > 0,
            utilization['billable_hours'] / utilization['total_hours'] * 100,
            0
        )
        
        # Cost calculations
        utilization['monthly_cost'] = utilization['hourly_rate'] * utilization['fte'] * standard_hours
        utilization['revenue_generated'] = utilization['billable_hours'] * utilization['hourly_rate']
        
        return utilization
    
    @staticmethod
    def calculate_project_costs(
        project_id: int,
        allocations_df: pd.DataFrame,
        expenses_df: pd.DataFrame,
        time_entries_df: pd.DataFrame
    ) -> Dict:
        """Calculate detailed project costs"""
        costs = {
            'labor_cost': 0,
            'expense_cost': 0,
            'total_cost': 0,
            'cost_breakdown': {}
        }
        
        # Labor costs
        if not allocations_df.empty and not time_entries_df.empty:
            project_time = time_entries_df[time_entries_df['project_id'] == project_id]
            if not project_time.empty:
                labor_cost = (project_time['hours'] * project_time['hourly_rate']).sum()
                costs['labor_cost'] = labor_cost
                
                # Breakdown by employee
                employee_costs = project_time.groupby('employee_name').apply(
                    lambda x: (x['hours'] * x['hourly_rate']).sum()
                ).to_dict()
                costs['cost_breakdown']['by_employee'] = employee_costs
        
        # Expense costs
        if not expenses_df.empty:
            project_expenses = expenses_df[expenses_df['project_id'] == project_id]
            if not project_expenses.empty:
                expense_cost = project_expenses['amount'].sum()
                costs['expense_cost'] = expense_cost
                
                # Breakdown by category
                category_costs = project_expenses.groupby('category')['amount'].sum().to_dict()
                costs['cost_breakdown']['by_category'] = category_costs
        
        costs['total_cost'] = costs['labor_cost'] + costs['expense_cost']
        
        return costs
    
    @staticmethod
    def forecast_project_completion(
        project_df: pd.DataFrame,
        time_entries_df: pd.DataFrame,
        lookback_days: int = 30
    ) -> pd.DataFrame:
        """Forecast project completion based on current burn rate"""
        if project_df.empty or time_entries_df.empty:
            return pd.DataFrame()
        
        forecasts = []
        
        for _, project in project_df.iterrows():
            if project['status'] != 'Active':
                continue
            
            # Get recent time entries
            project_time = time_entries_df[time_entries_df['project_id'] == project['id']]
            if project_time.empty:
                continue
            
            project_time['date'] = pd.to_datetime(project_time['date'])
            recent_time = project_time[
                project_time['date'] >= (pd.Timestamp.now() - timedelta(days=lookback_days))
            ]
            
            if recent_time.empty:
                continue
            
            # Calculate average daily burn
            daily_hours = recent_time.groupby('date')['hours'].sum()
            avg_daily_hours = daily_hours.mean()
            
            # Calculate remaining work (simplified)
            total_budget_hours = project['budget_allocated'] / 150 if project['budget_allocated'] else 0
            hours_used = project_time['hours'].sum()
            remaining_hours = max(0, total_budget_hours - hours_used)
            
            # Forecast completion
            if avg_daily_hours > 0:
                days_to_complete = remaining_hours / avg_daily_hours
                forecast_date = pd.Timestamp.now() + timedelta(days=days_to_complete)
                
                forecasts.append({
                    'project_name': project['name'],
                    'current_progress': (hours_used / total_budget_hours * 100) if total_budget_hours > 0 else 0,
                    'avg_daily_burn': avg_daily_hours,
                    'remaining_hours': remaining_hours,
                    'days_to_complete': days_to_complete,
                    'forecast_completion': forecast_date,
                    'scheduled_end': pd.to_datetime(project['end_date']),
                    'on_track': forecast_date <= pd.to_datetime(project['end_date'])
                })
        
        return pd.DataFrame(forecasts)
    
    @staticmethod
    def what_if_analysis(
        base_data: Dict,
        scenarios: List[Dict],
        metric: str = 'total_cost'
    ) -> pd.DataFrame:
        """Perform what-if scenario analysis"""
        results = []
        
        # Base scenario
        base_result = {
            'scenario': 'Current',
            metric: base_data.get(metric, 0)
        }
        results.append(base_result)
        
        # Apply scenarios
        for scenario in scenarios:
            scenario_data = base_data.copy()
            
            # Apply changes
            for change in scenario.get('changes', []):
                if change['type'] == 'multiply':
                    scenario_data[change['field']] *= change['value']
                elif change['type'] == 'add':
                    scenario_data[change['field']] += change['value']
                elif change['type'] == 'set':
                    scenario_data[change['field']] = change['value']
            
            # Recalculate metric
            if metric == 'total_cost':
                result_value = scenario_data.get('labor_cost', 0) + scenario_data.get('expense_cost', 0)
            elif metric == 'profit':
                result_value = scenario_data.get('revenue', 0) - scenario_data.get('total_cost', 0)
            elif metric == 'utilization':
                result_value = scenario_data.get('utilization_rate', 0)
            else:
                result_value = scenario_data.get(metric, 0)
            
            results.append({
                'scenario': scenario['name'],
                metric: result_value,
                'change_from_base': result_value - base_result[metric],
                'percent_change': ((result_value - base_result[metric]) / base_result[metric] * 100) 
                                  if base_result[metric] != 0 else 0
            })
        
        return pd.DataFrame(results)
    
    @staticmethod
    def calculate_fte_requirements(
        project_df: pd.DataFrame,
        allocations_df: pd.DataFrame,
        time_period: str = 'monthly'
    ) -> pd.DataFrame:
        """Calculate FTE requirements by project and time period"""
        if allocations_df.empty:
            return pd.DataFrame()
        
        allocations_df['start_date'] = pd.to_datetime(allocations_df['start_date'])
        allocations_df['end_date'] = pd.to_datetime(allocations_df['end_date'])
        
        # Create date range
        date_range = pd.date_range(
            start=allocations_df['start_date'].min(),
            end=allocations_df['end_date'].max(),
            freq='D'
        )
        
        fte_requirements = []
        
        for date in date_range:
            # Find active allocations for this date
            active = allocations_df[
                (allocations_df['start_date'] <= date) & 
                (allocations_df['end_date'] >= date)
            ]
            
            if not active.empty:
                # Calculate FTE by project
                project_fte = active.groupby('project_name')['allocation_percent'].sum() / 100
                
                for project, fte in project_fte.items():
                    fte_requirements.append({
                        'date': date,
                        'project': project,
                        'fte_required': fte
                    })
        
        fte_df = pd.DataFrame(fte_requirements)
        
        if not fte_df.empty:
            # Aggregate by time period
            if time_period == 'weekly':
                fte_df['period'] = fte_df['date'].dt.to_period('W').astype(str)
            elif time_period == 'monthly':
                fte_df['period'] = fte_df['date'].dt.to_period('M').astype(str)
            else:
                fte_df['period'] = fte_df['date'].dt.to_period('Q').astype(str)

            fte_summary = fte_df.groupby(['period', 'project'])['fte_required'].mean().reset_index()
            return fte_summary
        
        return pd.DataFrame()
