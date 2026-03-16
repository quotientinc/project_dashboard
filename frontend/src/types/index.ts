/**
 * Shared TypeScript interfaces for the Project Dashboard frontend.
 *
 * These mirror the Pydantic response models defined in backend/app/models/.
 */

import type { InjectionKey, Ref } from 'vue'

// ---- Provide/Inject Keys ----

export interface ProjectContext {
  project: Ref<Project | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  refreshProject: () => Promise<void>
}

export const PROJECT_CONTEXT_KEY: InjectionKey<ProjectContext> = Symbol('projectContext')

// ---- Projects ----

export interface Project {
  id: string
  name: string
  description: string | null
  status: string | null
  start_date: string | null
  end_date: string | null
  quoted_value: number | null
  awarded_value: number | null
  budget_used: number | null
  client: string | null
  project_manager: string | null
  billable: number
  created_at: string | null
  updated_at: string | null
}

export interface ProjectUpdate {
  name?: string
  description?: string
  status?: string
  start_date?: string
  end_date?: string
  quoted_value?: number
  awarded_value?: number
  client?: string
  project_manager?: string
  billable?: number
}

// ---- Allocations ----

export interface Allocation {
  id: number
  project_id: string
  employee_id: number
  allocated_fte: number
  allocation_date: string
  role: string | null
  bill_rate: number | null
  project_name: string | null
  employee_name: string | null
  effective_rate: number | null
  created_at: string | null
  updated_at: string | null
}

// ---- Employees ----

export interface Employee {
  id: number
  name: string
  email: string | null
  department: string | null
  role: string | null
  hourly_rate: number | null
  fte: number | null
  utilization: number | null
  skills: string | null
  billable: number
  hire_date: string | null
  term_date: string | null
  pay_type: string | null
  cost_rate: number | null
  annual_salary: number | null
  pto_accrual: number | null
  holidays: number | null
  target_allocation: number | null
  overhead_allocation: number | null
  created_at: string | null
  updated_at: string | null
}

export interface EmployeeUpdate {
  name?: string
  role?: string
  skills?: string
  hire_date?: string | null
  term_date?: string | null
  pay_type?: string
  cost_rate?: number
  annual_salary?: number | null
  pto_accrual?: number
  holidays?: number
  billable?: number
  overhead_allocation?: number
  target_allocation?: number
}

export interface AllocationCreate {
  project_id: string
  employee_id: number
  allocated_fte: number
  allocation_date: string
  role?: string
  bill_rate?: number
}

// ---- Analytics ----

export interface ProjectHealthEntry {
  id: string
  name: string
  status: string | null
  budget_health: number
  schedule_progress: number
  profit_margin: number
  health_score: number
}

export interface OverviewKPIs {
  total_projects: number
  active_projects: number
  completed_projects: number
  total_employees: number
  billable_employees: number
  total_quoted_value: number
  total_awarded_value: number
  total_budget_used: number
  total_hours_logged: number
  total_billable_hours: number
  avg_utilization: number
}

export interface UtilizationEntry {
  employee_id: number
  name: string
  role: string
  total_hours: number
  standard_hours: number
  utilization_pct: number
}

// ---- Expenses ----

export interface Expense {
  id: number
  project_id: string
  project_name: string | null
  category: string | null
  amount: number
  date: string
  description: string | null
  approved: number | null
  created_at: string | null
}

// ---- Burn Rate ----

export interface BurnRateEntry {
  period: string
  total_amount: number
  cumulative_amount: number
}

// ---- Time Entries ----

export interface TimeEntry {
  id: number
  employee_id: number
  employee_name: string
  project_id: string
  project_name: string
  date: string
  hours: number
  billable: number
  description: string | null
  hourly_rate: number | null
}

// ---- Client Analysis ----

export interface ClientAnalysisEntry {
  client: string
  revenue: number
  labor_cost: number
  expenses: number
  total_cost: number
  profit: number
  margin_pct: number
}

// ---- Year Forecast ----

export interface YearForecastMonth {
  month: number
  month_name: string
  revenue: number
  data_type: string
}

export interface YearForecastResponse {
  ytd_actual: number
  projected_remaining: number
  full_year_forecast: number
  months: YearForecastMonth[]
}

// ---- Funding Review ----

export interface FundingReviewEntry {
  project_id: string
  project_name: string
  client: string | null
  project_manager: string | null
  status: string | null
  quoted_value: number
  awarded_value: number
  budget_used: number
  remaining: number
  avg_monthly_invoice: number
  funding_runway_months: number | null
  funding_pct: number
  health_label: string
  current_month_potential: number
}

export interface MonthlyRevenueEntry {
  month: string
  revenue: number
}

export interface FundingReviewDetailResponse extends FundingReviewEntry {
  past_month_revenue: number
  monthly_revenue_history: MonthlyRevenueEntry[]
}

// ---- Detailed Utilization ----

export interface EmployeeMonthUtilization {
  month: string
  possible_hours: number
  actual_hours: number
  actual_billable_hours: number
  projected_hours: number
  pto_hours: number
  holiday_hours: number
  utilization_pct: number | null
  effective_billable_hours?: number
  other_nonbillable_hours?: number
  status?: string
  status_num?: number
}

export interface DetailedUtilizationEntry {
  employee_id: number
  employee_name: string
  role: string | null
  billable: number
  possible_hours: number
  actual_hours: number
  actual_billable_hours: number
  projected_hours: number
  pto_hours: number
  holiday_hours: number
  utilization_pct: number | null
  effective_billable_hours?: number
  other_nonbillable_hours?: number
  status?: string
  status_num?: number
  monthly_breakdown: EmployeeMonthUtilization[]
}

// ---- Allocation Planning ----

export interface AllocationProjectBreakdown {
  project_id: string
  project_name: string
  allocated_fte: number
  allocated_hours: number
  bill_rate: number
}

export interface AllocationPlanningEntry {
  employee_id: number
  employee_name: string
  target_fte: number
  possible_hours: number
  allocated_hours: number
  allocation_pct: number
  variance: number
  status: string
  project_breakdown: AllocationProjectBreakdown[]
}

// ---- Project Utilization ----

export interface ProjectUtilizationEntry {
  project_id: string
  project_name: string
  allocated_hours: number
  actual_billable_hours: number
  utilization_pct: number | null
  revenue_gap: number
  health_label: string
}

// ---- Combined Performance ----

export interface CombinedMonthlyBreakdown {
  month: string
  month_type: string
  actual_hours: number
  projected_hours: number
  combined_hours: number
  actual_revenue: number
  projected_revenue: number
  combined_revenue: number
  cumulative_revenue: number
  budget_pct: number | null
  status: string | null
}

export interface CombinedPerformanceSummary {
  total_hours: number
  total_accrued: number
  budget_status: string
  budget_pct: number
}

export interface CombinedPerformanceResponse {
  summary: CombinedPerformanceSummary
  monthly_breakdown: CombinedMonthlyBreakdown[]
}

// ---- Overview Dashboard Endpoints ----

export interface MonthlyUtilizationTrendEntry {
  month: number
  month_name: string
  avg_utilization: number
  data_type: string
}

export interface EmployeeBillableUtilizationEntry {
  employee_id: number
  name: string
  department: string
  role: string
  fte: number
  utilization_pct: number
  total_hours: number
  billable_hours: number
  non_billable_hours: number
  available_hours: number
  pto_hours: number
  status: string
  status_num: number
}

export interface MonthlyBurnRateEntry {
  month: string
  labor_cost: number
  expense_cost: number
  total_burn: number
}
