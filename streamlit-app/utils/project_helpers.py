"""
Helper functions for project-related calculations and formatting.
"""
import pandas as pd


def safe_budget_percentage(budget_used, contract_value):
    """
    Safely calculate budget percentage with NULL/NaN handling.
    Returns tuple: (percentage: float or None, display_string: str)
    """
    if pd.isna(contract_value) or contract_value == 0:
        return None, 'N/A'
    if pd.isna(budget_used):
        return None, 'N/A'

    pct = (budget_used / contract_value) * 100
    return pct, f"{pct:.1f}%"


def safe_currency_display(value):
    """Safely display currency with NULL handling."""
    if pd.isna(value):
        return '-'
    return f"${value:,.0f}"
