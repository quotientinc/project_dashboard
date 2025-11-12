import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dateutil.relativedelta import relativedelta
import calendar
import streamlit as st
from utils.logger import get_logger

logger = get_logger(__name__)

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
            (health_metrics['contract_value'] - health_metrics['budget_used']) / 
            health_metrics['contract_value'] * 100
        ).fillna(0)
        
        # Schedule health (days remaining vs total days)
        health_metrics['start_date'] = pd.to_datetime(health_metrics['start_date'])
        health_metrics['end_date'] = pd.to_datetime(health_metrics['end_date'])
        today = pd.Timestamp.now()

        total_days = (health_metrics['end_date'] - health_metrics['start_date']).dt.days
        days_elapsed = (today - health_metrics['start_date']).dt.days
        health_metrics['schedule_progress'] = (days_elapsed / total_days * 100).clip(0, 100)

        # Margin calculation: remaining budget as percentage of contract value
        health_metrics['profit_margin'] = (
            (health_metrics['contract_value'] - health_metrics['budget_used']) /
            health_metrics['contract_value'] * 100
        ).fillna(0)

        # Overall health score (weighted average of budget health and schedule progress)
        health_metrics['health_score'] = (
            health_metrics['budget_health'].clip(0, 100) * 0.5 +
            (100 - abs(health_metrics['schedule_progress'] - 50)) * 0.5
        ).round(1)
        
        return health_metrics
    
    @staticmethod
    def calculate_employee_utilization(
        employees_df: pd.DataFrame,
        allocations_df: pd.DataFrame,
        time_entries_df: pd.DataFrame,
        current_month_working_days: int = 21,
        target_year: int = None,
        target_month: int = None
    ) -> pd.DataFrame:
        """
        Calculate employee utilization metrics using improved methodology.

        Improved calculation uses:
        - Target FTE allocation as baseline (not fixed 160 hours)
        - Actual working days in the month
        - PTO and holiday adjustments
        - Separate tracking of billable vs total utilization
        - ONLY time entries from the specified month

        Formula:
        Expected Hours = Target FTE × Working Days × 8 hours/day × (1 - Overhead Allocation)
        Utilization Rate = (Total Hours Worked / Expected Hours) × 100%
        Billable Utilization = (Billable Hours Worked / Expected Hours) × 100%

        Args:
            employees_df: DataFrame with employee data including target_allocation, overhead_allocation
            allocations_df: DataFrame with project allocations
            time_entries_df: DataFrame with time entries (will be filtered to target month)
            current_month_working_days: Number of working days in the current month (default 21)
            target_year: Year to filter time entries (defaults to current year)
            target_month: Month to filter time entries (defaults to current month)
        """
        from datetime import datetime

        if employees_df.empty:
            return pd.DataFrame()

        # Default to current year/month if not specified
        if target_year is None:
            target_year = datetime.now().year
        if target_month is None:
            target_month = datetime.now().month

        # Filter out terminated employees who left before the reporting period
        # If terminated during the month, include them (they worked part of the month)
        # If terminated before the month started, exclude them
        utilization = employees_df.copy()

        # Convert term_date to datetime if it exists
        if 'term_date' in utilization.columns:
            utilization['term_date_dt'] = pd.to_datetime(utilization['term_date'], errors='coerce')

            # First day of the target month
            target_month_start = datetime(target_year, target_month, 1)

            # Filter: keep employees who either:
            # 1. Have no term date (still active), OR
            # 2. Were terminated during or after the target month
            utilization = utilization[
                (utilization['term_date_dt'].isna()) |
                (utilization['term_date_dt'] >= target_month_start)
            ].copy()

            # Drop the temporary datetime column
            utilization = utilization.drop(columns=['term_date_dt'])

        if utilization.empty:
            return pd.DataFrame()

        # Calculate allocated FTE and get rates from allocations
        if not allocations_df.empty:
            allocated = allocations_df.groupby('employee_id').agg({
                'bill_rate': 'mean',  # Average rate across allocations
                'allocated_fte': 'sum'    # Sum FTE across all allocations
            }).reset_index()

            utilization = utilization.merge(allocated, left_on='id', right_on='employee_id', how='left')
            utilization['bill_rate'] = utilization['bill_rate'].fillna(0)
            utilization['allocated_fte'] = utilization['allocated_fte'].fillna(0)
        else:
            utilization['bill_rate'] = 0
            utilization['allocated_fte'] = 0

        # FILTER time entries to only the target month
        if not time_entries_df.empty:
            # Ensure date column is datetime
            time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])

            # Filter to target year and month
            month_entries = time_entries_df[
                (time_entries_df['date'].dt.year == target_year) &
                (time_entries_df['date'].dt.month == target_month)
            ].copy()

            if not month_entries.empty:
                # Calculate billable vs non-billable hours for THIS MONTH ONLY
                billable = month_entries.groupby(['employee_id', 'billable'])['hours'].sum().unstack(fill_value=0)
                if 1 in billable.columns:
                    billable_hours = billable[1].reset_index()
                    billable_hours.columns = ['employee_id', 'billable_hours']
                    utilization = utilization.merge(billable_hours, left_on='id', right_on='employee_id', how='left')
                    utilization['billable_hours'] = utilization['billable_hours'].fillna(0)
                else:
                    utilization['billable_hours'] = 0

                total_hours = month_entries.groupby('employee_id')['hours'].sum().reset_index()
                total_hours.columns = ['employee_id', 'total_hours']
                utilization = utilization.merge(total_hours, left_on='id', right_on='employee_id', how='left')
                utilization['total_hours'] = utilization['total_hours'].fillna(0)
            else:
                # No time entries for this month
                utilization['billable_hours'] = 0
                utilization['total_hours'] = 0
        else:
            utilization['billable_hours'] = 0
            utilization['total_hours'] = 0

        # IMPROVED CALCULATION: Use target allocation and actual working days
        # Ensure target_allocation and overhead_allocation exist
        if 'target_allocation' not in utilization.columns:
            utilization['target_allocation'] = 1.0  # Default to full-time
        if 'overhead_allocation' not in utilization.columns:
            utilization['overhead_allocation'] = 0.0  # Default to no overhead

        # Fill NaN values
        utilization['target_allocation'] = utilization['target_allocation'].fillna(1.0)
        utilization['overhead_allocation'] = utilization['overhead_allocation'].fillna(0.0)

        # Calculate expected hours based on target FTE and working days
        # Expected Hours = Target FTE × Working Days × 8 hours/day × (1 - Overhead %)
        hours_per_day = 8
        utilization['expected_hours'] = (
            utilization['target_allocation'] *
            current_month_working_days *
            hours_per_day *
            (1 - utilization['overhead_allocation'])
        )

        # Calculate utilization rates
        # Total utilization (includes both billable and non-billable work)
        utilization['utilization_rate'] = np.where(
            utilization['expected_hours'] > 0,
            (utilization['total_hours'] / utilization['expected_hours'] * 100).clip(0, 200),  # Allow up to 200% for overtime
            0
        )

        # Billable utilization (only billable hours against expected)
        utilization['billable_utilization'] = np.where(
            utilization['expected_hours'] > 0,
            (utilization['billable_hours'] / utilization['expected_hours'] * 100).clip(0, 200),
            0
        )

        # Billable rate (percentage of worked hours that are billable)
        utilization['billable_rate'] = np.where(
            utilization['total_hours'] > 0,
            utilization['billable_hours'] / utilization['total_hours'] * 100,
            0
        )

        # Revenue calculations - use actual time entry data when available
        if not time_entries_df.empty and not month_entries.empty:
            # Check if amount column exists in time_entries
            if 'amount' in month_entries.columns:
                # Calculate actual revenue from time entries (use amount when available)
                def calculate_row_revenue(row):
                    if pd.notna(row.get('amount')) and row['amount'] != 0:
                        return row['amount']
                    elif pd.notna(row.get('bill_rate')):
                        return row['hours'] * row['bill_rate']
                    else:
                        return 0

                month_entries['revenue'] = month_entries.apply(calculate_row_revenue, axis=1)
                actual_revenue = month_entries.groupby('employee_id')['revenue'].sum().reset_index()
                actual_revenue.columns = ['employee_id', 'actual_revenue']
                utilization = utilization.merge(actual_revenue, left_on='id', right_on='employee_id', how='left')
                utilization['revenue_generated'] = utilization['actual_revenue'].fillna(0)
            else:
                # Fallback to calculated revenue using bill_rate from allocations
                if 'cost_rate' in utilization.columns:
                    effective_rate = utilization['cost_rate'].fillna(utilization['bill_rate'])
                else:
                    effective_rate = utilization['bill_rate']
                utilization['revenue_generated'] = utilization['billable_hours'] * effective_rate
        else:
            # No time entries - use calculated revenue
            if 'cost_rate' in utilization.columns:
                effective_rate = utilization['cost_rate'].fillna(utilization['bill_rate'])
            else:
                effective_rate = utilization['bill_rate']
            utilization['revenue_generated'] = utilization['billable_hours'] * effective_rate

        # Cost calculations (keep as-is for expected costs)
        # Use cost_rate from employee record (falls back to bill_rate from allocations)
        if 'cost_rate' in utilization.columns:
            effective_rate = utilization['cost_rate'].fillna(utilization['bill_rate'])
        else:
            effective_rate = utilization['bill_rate']

        utilization['monthly_cost'] = effective_rate * utilization['expected_hours']

        return utilization

    @staticmethod
    def calculate_monthly_utilization_trend(
        employees_df: pd.DataFrame,
        allocations_df: pd.DataFrame,
        time_entries_df: pd.DataFrame,
        months_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate monthly average utilization showing YTD actual (from time entries)
        and projected (from allocations) for the remainder of the year.

        Returns DataFrame with columns: month, month_name, avg_utilization, type
        """
        from datetime import datetime

        if employees_df.empty:
            return pd.DataFrame()

        current_year = datetime.now().year
        current_month = datetime.now().month

        # Get months for current year
        current_year_months = months_df[months_df['year'] == current_year].copy()
        if current_year_months.empty:
            # Fallback: generate basic month structure
            current_year_months = pd.DataFrame({
                'month': range(1, 13),
                'month_name': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
                'working_days': [21] * 12  # Default approximation
            })

        total_employees = len(employees_df)
        standard_monthly_hours = 160

        result = []

        for _, month_row in current_year_months.iterrows():
            month_num = month_row['month']
            month_name = month_row['month_name']

            if month_num <= current_month:
                # YTD Actual: Calculate from time entries
                if not time_entries_df.empty:
                    # Filter time entries for this month
                    time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
                    month_entries = time_entries_df[
                        (time_entries_df['date'].dt.year == current_year) &
                        (time_entries_df['date'].dt.month == month_num)
                    ]

                    if not month_entries.empty:
                        total_hours = month_entries['hours'].sum()
                        # Average utilization = total hours / (employees × standard hours) × 100
                        avg_utilization = (total_hours / (total_employees * standard_monthly_hours)) * 100
                    else:
                        avg_utilization = 0
                else:
                    avg_utilization = 0

                result.append({
                    'month': month_num,
                    'month_name': month_name,
                    'avg_utilization': min(avg_utilization, 100),  # Cap at 100%
                    'type': 'Actual'
                })
            else:
                # Future months: Projected from allocations
                if not allocations_df.empty:
                    # Calculate average FTE allocation
                    # Note: This is simplified - assumes allocations are for the entire year
                    total_fte = allocations_df['allocated_fte'].sum()
                    avg_utilization = (total_fte / total_employees) * 100
                else:
                    avg_utilization = 0

                result.append({
                    'month': month_num,
                    'month_name': month_name,
                    'avg_utilization': min(avg_utilization, 100),  # Cap at 100%
                    'type': 'Projected'
                })

        return pd.DataFrame(result)

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
                # Use amount if available, otherwise calculate from bill_rate
                project_time_copy = project_time.copy()

                if 'amount' in project_time.columns and project_time['amount'].notna().any():
                    # Calculate cost: use amount when available, fallback to hours × bill_rate
                    def calculate_cost(row):
                        if pd.notna(row.get('amount')) and row['amount'] != 0:
                            return row['amount']
                        elif pd.notna(row.get('bill_rate')):
                            return row['hours'] * row['bill_rate']
                        else:
                            # Fallback to hourly_rate if it exists (for backward compatibility)
                            return row['hours'] * row.get('hourly_rate', 0)

                    project_time_copy['cost'] = project_time_copy.apply(calculate_cost, axis=1)
                elif 'bill_rate' in project_time.columns:
                    project_time_copy['cost'] = project_time_copy['hours'] * project_time_copy['bill_rate']
                else:
                    # Fallback to hourly_rate if it exists (for backward compatibility)
                    project_time_copy['cost'] = project_time_copy['hours'] * project_time_copy.get('hourly_rate', 0)

                labor_cost = project_time_copy['cost'].sum()
                costs['labor_cost'] = labor_cost

                # Breakdown by employee
                if 'employee_name' in project_time_copy.columns:
                    employee_costs = project_time_copy.groupby('employee_name')['cost'].sum().to_dict()
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
            project_time = time_entries_df[time_entries_df['project_id'] == project['id']].copy()
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
            total_budget_hours = project['contract_value'] / 150 if project['contract_value'] else 0
            hours_used = project_time['hours'].sum()
            remaining_hours = max(0, total_budget_hours - hours_used)
            
            # Forecast completion
            if avg_daily_hours > 0:
                days_to_complete = remaining_hours / avg_daily_hours
                forecast_date = pd.Timestamp.now() + timedelta(days=days_to_complete)
                if pd.to_datetime(project['end_date']) is None:
                    on_track = 1
                else:
                    on_track = forecast_date <= pd.to_datetime(project['end_date'])
                
                forecasts.append({
                    'project_name': project['name'],
                    'current_progress': (hours_used / total_budget_hours * 100) if total_budget_hours > 0 else 0,
                    'avg_daily_burn': avg_daily_hours,
                    'remaining_hours': remaining_hours,
                    'days_to_complete': days_to_complete,
                    'forecast_completion': forecast_date,
                    'scheduled_end': pd.to_datetime(project['end_date']),
                    'on_track': on_track
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
                project_fte = active.groupby('project_name')['allocated_fte'].sum()

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

    @staticmethod
    def calculate_working_days(year: int, month: int, project_working_days: Dict = None) -> Dict:
        """Calculate working days for a given month

        Args:
            year: Year of the month
            month: Month (1-12)
            project_working_days: Optional dict mapping (year, month) tuples to working days
                                 Useful for projects that started mid-month or have custom schedules
        """
        # Use project-specific working days if provided
        if project_working_days and (year, month) in project_working_days:
            working_days = project_working_days[(year, month)]
        else:
            # Get the number of days in the month
            days_in_month = calendar.monthrange(year, month)[1]

            # Count weekdays (Monday=0, Sunday=6)
            working_days = 0
            for day in range(1, days_in_month + 1):
                if datetime(year, month, day).weekday() < 5:  # Monday-Friday
                    working_days += 1

        # Calculate elapsed and remaining days based on current date
        today = datetime.now()
        if year == today.year and month == today.month:
            # Current month - calculate worked and remaining days
            days_in_month = calendar.monthrange(year, month)[1]
            worked_days = sum(1 for day in range(1, min(today.day, days_in_month) + 1)
                            if datetime(year, month, day).weekday() < 5)
            remaining_days = working_days - worked_days
        elif datetime(year, month, 1) > today:
            # Future month - all days are remaining
            worked_days = 0
            remaining_days = working_days
        else:
            # Past month - all days are worked
            worked_days = working_days
            remaining_days = 0

        return {
            'working_days': working_days,
            'worked_days': worked_days,
            'remaining_days': remaining_days
        }

    @staticmethod
    def build_hours_sheet_data(
        project: pd.Series,
        allocations_df: pd.DataFrame,
        time_entries_by_month: pd.DataFrame
    ) -> pd.DataFrame:
        """Build Hours sheet data structure from database data"""
        if allocations_df.empty:
            return pd.DataFrame()

        # Parse project dates
        start_date = pd.to_datetime(project['start_date'])
        end_date = pd.to_datetime(project['end_date'])

        # Generate month range
        months = pd.date_range(
            start=start_date.replace(day=1),
            end=end_date + pd.DateOffset(months=1),
            freq='MS'
        )[:-1]  # Remove the extra month

        # Get unique employees (group allocations by employee)
        unique_employees = allocations_df.drop_duplicates(subset=['employee_id'])[
            ['employee_id', 'employee_name', 'role', 'effective_rate']
        ].to_dict('records')

        # Initialize data structure
        rows = []

        for emp in unique_employees:
            row_data = {
                'employee_id': emp['employee_id'],
                'employee_name': emp['employee_name'],
                'role': emp.get('role', ''),
                'rate': emp['effective_rate'],
                'total_projected_hours': 0
            }

            # Add columns for each month
            for month_date in months:
                month_key = month_date.strftime('%Y-%m')
                year = month_date.year
                month = month_date.month

                # Get FTE and working_days for this specific month from allocations
                # Look for allocation with matching allocation_date
                month_alloc = allocations_df[
                    (allocations_df['employee_id'] == emp['employee_id']) &
                    (allocations_df['allocation_date'] == month_date.strftime('%Y-%m-%d'))
                ]

                if not month_alloc.empty:
                    fte = month_alloc['allocated_fte'].iloc[0]
                    # Use stored working_days if available, otherwise calculate
                    if 'working_days' in month_alloc.columns and pd.notna(month_alloc['working_days'].iloc[0]):
                        working_days = int(month_alloc['working_days'].iloc[0])
                        days_info = DataProcessor.calculate_working_days(year, month,
                            project_working_days={(year, month): working_days})
                    else:
                        days_info = DataProcessor.calculate_working_days(year, month)

                    # Use stored remaining_days if available, otherwise use calculated
                    if 'remaining_days' in month_alloc.columns and pd.notna(month_alloc['remaining_days'].iloc[0]):
                        remaining_days = int(month_alloc['remaining_days'].iloc[0])
                    else:
                        remaining_days = days_info['remaining_days']
                else:
                    # Fallback to any allocation for this employee
                    emp_allocs = allocations_df[allocations_df['employee_id'] == emp['employee_id']]
                    #fte = emp_allocs['allocation_percent'].iloc[0] / 100 if not emp_allocs.empty else 0
                    fte = 0
                    # Calculate working days normally if no specific allocation
                    days_info = DataProcessor.calculate_working_days(year, month)
                    remaining_days = days_info['remaining_days']

                # Calculate Possible hours
                possible_hours = days_info['working_days'] * 8 * fte if fte <= 1 else fte

                # Get actual hours from time_entries
                actual_hours = 0
                if not time_entries_by_month.empty:
                    time_entry = time_entries_by_month[
                        (time_entries_by_month['employee_id'] == emp['employee_id']) &
                        (time_entries_by_month['month'] == month_key)
                    ]
                    if not time_entry.empty:
                        actual_hours = time_entry['actual_hours'].iloc[0]

                # Calculate Projected hours - use custom remaining_days if available
                projected_hours = remaining_days * 8 * fte if fte <= 1 else 0

                # Total hours
                total_hours = actual_hours + projected_hours

                # Store month data
                row_data[f'fte_{month_key}'] = fte
                row_data[f'possible_{month_key}'] = possible_hours
                row_data[f'actual_{month_key}'] = actual_hours
                row_data[f'projected_{month_key}'] = projected_hours
                row_data[f'total_{month_key}'] = total_hours
                row_data[f'working_days_{month_key}'] = days_info['working_days']
                row_data[f'remaining_days_{month_key}'] = days_info['remaining_days']

                row_data['total_projected_hours'] += total_hours

            rows.append(row_data)

        return pd.DataFrame(rows)

    @staticmethod
    def build_hours_by_month_data(
        hours_df: pd.DataFrame,
        project: pd.Series,
        employees_df: pd.DataFrame = None
    ) -> pd.DataFrame:
        """Build Hours By Month sheet from Hours sheet data"""
        if hours_df.empty:
            return pd.DataFrame()

        # Get all months that exist in the hours_df (including planning months)
        # Find all month columns (those with format YYYY-MM in column names)
        month_cols = [col for col in hours_df.columns if '-' in col and col.split('_')[-1].count('-') == 1]

        # Extract unique month keys (YYYY-MM format)
        month_keys = set()
        for col in month_cols:
            parts = col.split('_')
            if len(parts) >= 2:
                month_key = parts[-1]  # Get YYYY-MM part
                month_keys.add(month_key)

        # Convert to datetime objects and sort
        months = sorted([pd.to_datetime(mk + '-01') for mk in month_keys])

        num_months = len(months)

        # Initialize data structure
        rows = []

        # Check for edited target hours in session state
        import streamlit as st
        fte_edits = st.session_state.get('burn_rate_fte_edits', {})

        for _, emp_data in hours_df.iterrows():
            # Get employee FTE from allocations (stored in emp_data from hours_df)
            employee_name = emp_data['employee_name']
            # Calculate average FTE across all months for this employee
            fte_cols = [col for col in emp_data.index if col.startswith('fte_')]
            if fte_cols:
                nominal_fte = sum(emp_data[col] for col in fte_cols) / len(fte_cols)
            else:
                nominal_fte = 0.0

            # Calculate target hours: FTE × 160 hours/month × number of months
            # Check if user edited the target hours for this employee
            if employee_name in fte_edits and 'target_hours' in fte_edits[employee_name]:
                target_hours = fte_edits[employee_name]['target_hours']
            else:
                target_hours = nominal_fte * 160 * num_months

            row = {
                'employee_name': employee_name,
                'role': emp_data['role'],
                'nominal_fte_target': nominal_fte,
                'target_hours': target_hours,
                'rate': emp_data['rate'],
                'total_hours': 0,
                'total_cost': 0
            }

            # Add monthly hours and costs
            for month_date in months:
                month_key = month_date.strftime('%Y-%m')
                total_col = f'total_{month_key}'

                if total_col in emp_data:
                    hours = emp_data[total_col]
                    cost = hours * emp_data['rate']

                    row[f'hours_{month_key}'] = hours
                    row[f'cost_{month_key}'] = cost
                    row['total_hours'] += hours
                    row['total_cost'] += cost

            # Calculate over/under
            row['over_under'] = row['total_hours'] - row['target_hours']

            rows.append(row)

        # Create DataFrame
        hbm_df = pd.DataFrame(rows)

        # Add summary rows
        if not hbm_df.empty:
            # Calculate project totals
            actual_cost = hbm_df['total_cost'].sum()
            current_funding = project.get('contract_value', 0)
            balance = current_funding - actual_cost

            return hbm_df, {
                'actual_cost': actual_cost,
                'current_funding': current_funding,
                'balance': balance
            }

        return hbm_df, {}

    @staticmethod
    def apply_conditional_formatting_rules(value, column_name: str, threshold_values: Dict) -> str:
        """Apply conditional formatting rules and return CSS style string"""
        styles = []

        # Negative costs (red font)
        if 'cost_' in column_name and value < 0:
            styles.append('color: #FF0000')

        # Hours over 176 (light red background)
        if 'hours_' in column_name and value > 176:
            styles.append('background-color: #F4C7C3')

        # Hours over 160 (light red background)
        elif 'hours_' in column_name and value > 160:
            styles.append('background-color: #F4C7C3')

        # Total hours over annual target (light red background)
        if column_name == 'total_hours' and value > threshold_values.get('annual_target', 2000):
            styles.append('background-color: #F4C7C3')

        return '; '.join(styles) if styles else ''

    @staticmethod
    @st.cache_data(ttl=60, show_spinner=False)
    def get_performance_metrics(
        start_date: str,
        end_date: str,
        constraint: Optional[Dict] = None
    ) -> Dict:
        """
        Generate performance metrics data for reporting.

        Assembles data in a common format for individual reports to operate over.
        Returns three groups of data: actuals (from time_entries), projected
        (from allocations), and possible (from employees).

        All data excludes time_entries with project_id='FRINGE.HOL'.

        Args:
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            constraint: Optional dict to filter data, e.g., {"project_id": "200200.000.00.00"}
                       or {"employee_id": "100047"}

        Returns:
            Dictionary with structure:
            {
                'actuals': {
                    'January 2025': {
                        '100047': {'hours': 100, 'revenue': 10000.00, 'worked_days': 22},
                        ...
                    },
                    ...
                },
                'projected': {...},
                'possible': {...}
            }

            When constraint is None, data is grouped by employee only.
            When constraint is {"project_id": "..."}, data is grouped by employee.
            When constraint is {"employee_id": "..."}, data is grouped by project.
        """

        # Access database manager from session state
        db = st.session_state.db_manager

        # Parse dates
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        # Determine filter type
        filter_type = None
        filter_value = None
        if constraint:
            if 'project_id' in constraint:
                filter_type = 'project'
                filter_value = constraint['project_id']
            elif 'employee_id' in constraint:
                filter_type = 'employee'
                filter_value = str(constraint['employee_id'])

        # Initialize result structure
        result = {
            'actuals': {},
            'projected': {},
            'possible': {}
        }

        # Get months data for working_days and holidays
        months_df = db.get_months()

        # Build ACTUALS data from time_entries
        logger.info(f"Building actuals data from {start_date} to {end_date}")
        actuals_data = DataProcessor._build_actuals_data(
            db, start, end, filter_type, filter_value
        )
        result['actuals'] = actuals_data

        # Build PROJECTED data from allocations
        logger.info(f"Building projected data from {start_date} to {end_date}")
        projected_data = DataProcessor._build_projected_data(
            db, start, end, filter_type, filter_value, months_df
        )
        result['projected'] = projected_data

        # Build POSSIBLE data from employees
        logger.info(f"Building possible data from {start_date} to {end_date}")
        possible_data = DataProcessor._build_possible_data(
            db, start, end, filter_type, filter_value, months_df
        )
        result['possible'] = possible_data

        return result

    @staticmethod
    def _build_actuals_data(
        db,
        start: pd.Timestamp,
        end: pd.Timestamp,
        filter_type: Optional[str],
        filter_value: Optional[str]
    ) -> Dict:
        """Build actuals data from time_entries table"""

        # Build query to get time entries
        # Use LEFT JOIN instead of correlated subquery for better performance
        query = """
            SELECT
                t.employee_id,
                t.project_id,
                t.date,
                t.hours,
                t.amount,
                t.billable,
                t.bill_rate as time_entry_bill_rate,
                COALESCE(a.bill_rate, 0) as allocation_bill_rate
            FROM time_entries t
            LEFT JOIN (
                SELECT DISTINCT employee_id, project_id, bill_rate
                FROM allocations
            ) a ON t.employee_id = a.employee_id AND t.project_id = a.project_id
            WHERE t.date >= ?
                AND t.date <= ?
                AND t.project_id != 'FRINGE.HOL'
        """
        params = [start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')]

        # Add constraint filter
        if filter_type == 'project' and filter_value:
            query += " AND t.project_id = ?"
            params.append(filter_value)
        elif filter_type == 'employee' and filter_value:
            query += " AND t.employee_id = ?"
            params.append(filter_value)

        time_entries_df = pd.read_sql_query(query, db.conn, params=params)

        if time_entries_df.empty:
            return {}

        # Convert date to datetime
        time_entries_df['date'] = pd.to_datetime(time_entries_df['date'])
        time_entries_df['year'] = time_entries_df['date'].dt.year
        time_entries_df['month'] = time_entries_df['date'].dt.month
        time_entries_df['month_name'] = time_entries_df['date'].dt.strftime('%B %Y')

        # Calculate revenue: Use amount if available, otherwise calculate from hours × bill_rate
        # Priority: 1) time_entries.amount, 2) hours × allocation.bill_rate
        def calculate_revenue(row):
            if pd.notna(row['amount']) and row['amount'] != 0:
                return row['amount']
            else:
                # Fallback to calculated revenue using allocation bill_rate
                return row['hours'] * row['allocation_bill_rate']

        time_entries_df['revenue'] = time_entries_df.apply(calculate_revenue, axis=1)

        # Determine grouping key based on filter type
        if filter_type == 'employee':
            group_key = 'project_id'
        else:
            # Default to employee grouping (when filter_type is 'project' or None)
            group_key = 'employee_id'

        # Optimized: Single groupby with conditional aggregation instead of two separate groupbys
        # This reduces iteration through the DataFrame from 2x to 1x
        grouped = time_entries_df.groupby(['month_name', group_key]).agg(
            hours=('hours', 'sum'),
            revenue=('revenue', 'sum'),
            worked_days=('date', 'nunique'),  # Count unique dates for worked_days
            billable_hours=('hours', lambda x: x[time_entries_df.loc[x.index, 'billable'] == 1].sum())
        ).reset_index()

        # Build nested dictionary structure
        actuals = {}
        for _, row in grouped.iterrows():
            month = row['month_name']
            key = str(row[group_key])

            if month not in actuals:
                actuals[month] = {}

            actuals[month][key] = {
                'hours': float(row['hours']),
                'billable_hours': float(row['billable_hours']),
                'revenue': float(row['revenue']),
                'worked_days': int(row['worked_days'])
            }

        return actuals

    @staticmethod
    def _build_projected_data(
        db,
        start: pd.Timestamp,
        end: pd.Timestamp,
        filter_type: Optional[str],
        filter_value: Optional[str],
        months_df: pd.DataFrame
    ) -> Dict:
        """Build projected data from allocations table"""

        # Build query to get allocations
        query = """
            SELECT
                a.employee_id,
                a.project_id,
                a.allocation_date,
                a.allocated_fte,
                a.bill_rate
            FROM allocations a
            WHERE a.allocation_date >= ?
                AND a.allocation_date <= ?
        """
        params = [start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')]

        # Add constraint filter
        if filter_type == 'project' and filter_value:
            query += " AND a.project_id = ?"
            params.append(filter_value)
        elif filter_type == 'employee' and filter_value:
            query += " AND a.employee_id = ?"
            params.append(filter_value)

        allocations_df = pd.read_sql_query(query, db.conn, params=params)

        if allocations_df.empty:
            return {}

        # Convert allocation_date to datetime
        allocations_df['allocation_date'] = pd.to_datetime(allocations_df['allocation_date'])
        allocations_df['year'] = allocations_df['allocation_date'].dt.year
        allocations_df['month'] = allocations_df['allocation_date'].dt.month
        allocations_df['month_name'] = allocations_df['allocation_date'].dt.strftime('%B %Y')

        if allocations_df.empty:
            return {}

        # Join with months table to get working_days and holidays
        if not months_df.empty:
            allocations_df = allocations_df.merge(
                months_df[['year', 'month', 'working_days', 'holidays']],
                on=['year', 'month'],
                how='left'
            )
            # Fill missing values with defaults
            allocations_df['working_days'] = allocations_df['working_days'].fillna(21)
            allocations_df['holidays'] = allocations_df['holidays'].fillna(0)
        else:
            allocations_df['working_days'] = 21
            allocations_df['holidays'] = 0

        # Calculate projected hours and revenue
        # TODO: Factor PTO?
        # Formula: hours = (working_days) × allocated_fte × 8
        allocations_df['hours'] = (
            (allocations_df['working_days']) *
            allocations_df['allocated_fte'] *
            8
        )
        allocations_df['revenue'] = allocations_df['hours'] * allocations_df['bill_rate']

        # Determine grouping key based on filter type
        if filter_type == 'employee':
            group_key = 'project_id'
        else:
            # Default to employee grouping
            group_key = 'employee_id'

        # Group by month and employee/project
        grouped = allocations_df.groupby(['month_name', group_key, 'working_days']).agg({
            'hours': 'sum',
            'revenue': 'sum'
        }).reset_index()

        # Build nested dictionary structure
        projected = {}
        for _, row in grouped.iterrows():
            month = row['month_name']
            key = str(row[group_key])

            if month not in projected:
                projected[month] = {}

            projected[month][key] = {
                'hours': float(row['hours']),
                'revenue': float(row['revenue']),
                'worked_days': int(row['working_days'])
            }

        return projected

    @staticmethod
    def _build_possible_data(
        db,
        start: pd.Timestamp,
        end: pd.Timestamp,
        filter_type: Optional[str],
        filter_value: Optional[str],
        months_df: pd.DataFrame
    ) -> Dict:
        """Build possible data from employees table"""

        # Get active employees
        query = """
            SELECT
                e.id as employee_id,
                e.target_allocation,
                e.overhead_allocation,
                e.hire_date,
                e.term_date
            FROM employees e
            WHERE e.billable = 1
        """

        # If filtering by employee, limit to that employee
        if filter_type == 'employee' and filter_value:
            query += " AND e.id = ?"
            params = [filter_value]
            employees_df = pd.read_sql_query(query, db.conn, params=params)
        else:
            employees_df = pd.read_sql_query(query, db.conn)

        if employees_df.empty:
            return {}

        # Parse hire_date and term_date as datetime
        employees_df['hire_date'] = pd.to_datetime(employees_df['hire_date'], errors='coerce')
        employees_df['term_date'] = pd.to_datetime(employees_df['term_date'], errors='coerce')

        # Filter out terminated employees based on date range
        # Keep employees who are either active (no term_date) or were terminated after start date
        employees_df = employees_df[
            (employees_df['term_date'].isna()) |
            (employees_df['term_date'] >= start)
        ]

        if employees_df.empty:
            return {}

        # Get months in the date range
        if not months_df.empty:
            months_in_range = months_df[
                (months_df['year'] >= start.year) &
                (months_df['year'] <= end.year)
            ].copy()

            # Further filter by month
            months_in_range = months_in_range[
                ((months_in_range['year'] == start.year) & (months_in_range['month'] >= start.month)) |
                ((months_in_range['year'] == end.year) & (months_in_range['month'] <= end.month)) |
                ((months_in_range['year'] > start.year) & (months_in_range['year'] < end.year))
            ]
        else:
            # Fallback: generate months manually
            months_list = []
            current = start
            while current <= end:
                months_list.append({
                    'year': current.year,
                    'month': current.month,
                    'month_name': current.strftime('%b'),
                    'working_days': 21,
                    'holidays': 0
                })
                current = current + relativedelta(months=1)
            months_in_range = pd.DataFrame(months_list)

        if months_in_range.empty:
            return {}

        # Create month name for display
        months_in_range['month_name_full'] = pd.to_datetime(
            months_in_range['year'].astype(str) + '-' +
            months_in_range['month'].astype(str) + '-01'
        ).dt.strftime('%B %Y')

        # Cross join employees with months to get all combinations
        employees_df['key'] = 1
        months_in_range['key'] = 1
        cross_join = employees_df.merge(months_in_range, on='key').drop('key', axis=1)

        # Create month_start and month_end dates for filtering
        cross_join['month_start'] = pd.to_datetime(
            cross_join['year'].astype(str) + '-' +
            cross_join['month'].astype(str) + '-01'
        )
        cross_join['month_end'] = cross_join['month_start'] + pd.offsets.MonthEnd(0)

        # Filter out months where employee wasn't active
        # Keep only if: (no hire_date OR month_end >= hire_date) AND (no term_date OR month_start <= term_date)
        cross_join = cross_join[
            (cross_join['hire_date'].isna() | (cross_join['month_end'] >= cross_join['hire_date'])) &
            (cross_join['term_date'].isna() | (cross_join['month_start'] <= cross_join['term_date']))
        ]

        if cross_join.empty:
            return {}

        # Calculate proration factor for partial months
        def calculate_proration_factor(row):
            """Calculate the proportion of the month the employee was active"""
            month_start = row['month_start']
            month_end = row['month_end']
            hire_date = row['hire_date']
            term_date = row['term_date']

            # Determine actual start and end dates for this employee in this month
            actual_start = month_start if pd.isna(hire_date) else max(month_start, hire_date)
            actual_end = month_end if pd.isna(term_date) else min(month_end, term_date)

            # If full month, return 1.0
            if actual_start == month_start and actual_end == month_end:
                return 1.0

            # Calculate proportion of month worked
            days_in_month = (month_end - month_start).days + 1
            days_worked = (actual_end - actual_start).days + 1

            return days_worked / days_in_month

        cross_join['proration_factor'] = cross_join.apply(calculate_proration_factor, axis=1)

        # Calculate possible hours with proration
        # Formula: (working_days) × (target_allocation - overhead_allocation) × 8 × proration_factor
        cross_join['hours'] = (
            (cross_join['working_days']) *
            (cross_join['target_allocation'] - cross_join['overhead_allocation']) *
            8 *
            cross_join['proration_factor']
        )

        # Set revenue to 0 (as per user instruction)
        cross_join['revenue'] = 0

        # Group by month and employee (only employee grouping for possible data)
        grouped = cross_join.groupby(['month_name_full', 'employee_id', 'working_days']).agg({
            'hours': 'sum',
            'revenue': 'sum'
        }).reset_index()

        # Build nested dictionary structure
        possible = {}
        for _, row in grouped.iterrows():
            month = row['month_name_full']
            key = str(row['employee_id'])

            if month not in possible:
                possible[month] = {}

            possible[month][key] = {
                'hours': float(row['hours']),
                'revenue': float(row['revenue']),
                'worked_days': int(row['working_days'])
            }

        return possible

    @staticmethod
    def combine_actual_projected_smartly(
        actuals_dict: Dict,
        projected_dict: Dict,
        months_df: pd.DataFrame,
        current_date: Optional[datetime] = None
    ) -> Dict[str, Dict]:
        """
        Intelligently combine actual and projected data based on month status.

        Logic:
        - Past months: Use ONLY actual data
        - Current/active month: Use actual + partial projected (if month is incomplete)
        - Future months: Use ONLY projected data

        Args:
            actuals_dict: Nested dict from get_performance_metrics()['actuals']
                         Format: {month_name: {entity_id: {hours, revenue, worked_days}}}
            projected_dict: Nested dict from get_performance_metrics()['projected']
                           Format: {month_name: {entity_id: {hours, revenue, worked_days}}}
            months_df: DataFrame with columns [year, month, working_days, holidays]
            current_date: Optional datetime for testing, defaults to now()

        Returns:
            Combined dictionary with structure:
            {
                month_name: {
                    entity_id: {
                        'hours': float,
                        'revenue': float,
                        'worked_days': int,
                        'month_type': str  # 'past', 'active', or 'future'
                    }
                }
            }
        """
        if current_date is None:
            current_date = datetime.now()

        # Get first day of current month for comparison
        current_month_start = pd.Timestamp(current_date.year, current_date.month, 1)

        # Get all unique months from both actuals and projected
        all_months = set(list(actuals_dict.keys()) + list(projected_dict.keys()))

        combined = {}

        for month_name in all_months:
            # Parse month name to datetime (format: "January 2025")
            try:
                month_date = pd.to_datetime(month_name, format='%B %Y')
            except:
                logger.warning(f"Could not parse month name: {month_name}, skipping")
                continue

            # Determine month type
            if month_date < current_month_start:
                month_type = 'past'
            elif month_date == current_month_start:
                month_type = 'current'
            else:
                month_type = 'future'

            # Get month info from months_df
            month_info = months_df[
                (months_df['year'] == month_date.year) &
                (months_df['month'] == month_date.month)
            ]

            if not month_info.empty:
                working_days = int(month_info['working_days'].iloc[0])
                expected_working_days = working_days
            else:
                # Fallback to default if month not in database
                logger.warning(f"Month {month_name} not found in months_df, using defaults")
                expected_working_days = 21

            # Get entities from both actuals and projected for this month
            actuals_month = actuals_dict.get(month_name, {})
            projected_month = projected_dict.get(month_name, {})
            all_entities = set(list(actuals_month.keys()) + list(projected_month.keys()))

            combined[month_name] = {}

            for entity_id in all_entities:
                actual_data = actuals_month.get(entity_id, {'hours': 0, 'revenue': 0, 'worked_days': 0})
                projected_data = projected_month.get(entity_id, {'hours': 0, 'revenue': 0, 'worked_days': 0})

                # Apply combination logic based on month type
                if month_type == 'past':
                    # Past month: Use ONLY actuals
                    combined[month_name][entity_id] = {
                        'hours': actual_data['hours'],
                        'revenue': actual_data['revenue'],
                        'worked_days': actual_data.get('worked_days', 0),
                        'month_type': 'past'
                    }

                elif month_type == 'future':
                    # Future month: Use ONLY projected
                    combined[month_name][entity_id] = {
                        'hours': projected_data['hours'],
                        'revenue': projected_data['revenue'],
                        'worked_days': projected_data.get('worked_days', expected_working_days),
                        'month_type': 'future'
                    }

                else:  # month_type == 'current'
                    # Current month: Check if active (has remaining days)
                    worked_days = actual_data.get('worked_days', 0)

                    # Determine if month is "active" (incomplete)
                    is_active = worked_days < expected_working_days

                    if is_active and expected_working_days > 0:
                        # Active month: Blend actual + partial projected
                        # Formula: actual + (remaining_days_ratio × projected)
                        remaining_days = expected_working_days - worked_days
                        remaining_ratio = remaining_days / expected_working_days

                        # Calculate blended values
                        blended_hours = actual_data['hours'] + (remaining_ratio * projected_data['hours'])
                        blended_revenue = actual_data['revenue'] + (remaining_ratio * projected_data['revenue'])

                        combined[month_name][entity_id] = {
                            'hours': blended_hours,
                            'revenue': blended_revenue,
                            'worked_days': worked_days,
                            'month_type': 'active'
                        }
                    else:
                        # Current month is complete (all days worked): Use ONLY actuals
                        combined[month_name][entity_id] = {
                            'hours': actual_data['hours'],
                            'revenue': actual_data['revenue'],
                            'worked_days': worked_days,
                            'month_type': 'past'  # Treat as past since it's complete
                        }

        return combined
