<script setup lang="ts">
/**
 * Reports page -- Allocation Coverage, Employee Allocations, Project Allocations, Monthly Resource Allocation.
 *
 * Each report tab fetches projects + allocations data from the API and
 * computes its summary client-side.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import { formatPercent, downloadCsv } from '@/utils/helpers'
import type { Project, Allocation, Employee } from '@/types'
import type Plotly from 'plotly.js-dist-min'

// ---- CSV Template Generator types ----

interface TemplateRow {
  employee_id: number
  employee_name: string
  project_id: string
  allocation_date: string
  fte: number
  bill_rate: number | null
  role: string | null
}

// ---- State ----

const api = useApi()

const projects = ref<Project[]>([])
const allocations = ref<Allocation[]>([])
const employees = ref<Employee[]>([])

const loadingData = ref(true)
const errorMessage = ref<string | null>(null)
const activeTab = ref(0)

// ---- Data fetching ----

async function fetchData() {
  loadingData.value = true
  errorMessage.value = null
  try {
    const [p, a, e] = await Promise.all([
      api.get<Project[]>('/projects/'),
      api.get<Allocation[]>('/allocations/'),
      api.get<Employee[]>('/employees/'),
    ])
    projects.value = p
    allocations.value = a
    employees.value = e
  } catch {
    errorMessage.value = 'Failed to load report data.'
  } finally {
    loadingData.value = false
  }
}

onMounted(fetchData)

// ---- Helpers ----

function coverageColor(pct: number): string {
  if (pct >= 100) return '#4CAF50'
  if (pct >= 75) return '#FB8C00'
  return '#FF5252'
}

function utilizationColor(pct: number): string {
  if (pct > 100) return '#f44336'
  if (pct >= 80) return '#4caf50'
  return '#ff9800'
}

function budgetUsedColor(pct: number): string {
  if (pct > 90) return '#f44336'
  if (pct > 70) return '#ff9800'
  return '#4caf50'
}

// ==========================================================================
// TAB 1: Allocation Coverage
// ==========================================================================

interface CoverageRow {
  project_code: string
  project_name: string
  client: string
  status: string
  start_date: string
  end_date: string
  total_months: number
  months_covered: number
  months_missing: number
  coverage_pct: number
  allocation_status: string
  employee_count: number
  avg_fte: number
}

const coverageRows = computed<CoverageRow[]>(() => {
  if (projects.value.length === 0) return []

  const rows: CoverageRow[] = []

  for (const p of projects.value) {
    if (!p.start_date || !p.end_date) continue

    const start = new Date(p.start_date)
    const end = new Date(p.end_date)

    // Calculate total months
    const totalMonths =
      (end.getFullYear() - start.getFullYear()) * 12 +
      (end.getMonth() - start.getMonth()) + 1
    if (totalMonths <= 0) continue

    // Find allocations for this project
    const projAllocs = allocations.value.filter((a) => a.project_id === p.id)

    if (projAllocs.length === 0) {
      rows.push({
        project_code: p.id,
        project_name: p.name,
        client: p.client || '',
        status: p.status || '',
        start_date: p.start_date,
        end_date: p.end_date,
        total_months: totalMonths,
        months_covered: 0,
        months_missing: totalMonths,
        coverage_pct: 0,
        allocation_status: 'No Allocations',
        employee_count: 0,
        avg_fte: 0,
      })
    } else {
      const uniqueMonths = new Set(projAllocs.map((a) => a.allocation_date.substring(0, 7)))
      const monthsCovered = uniqueMonths.size
      const coveragePct = Math.min((monthsCovered / totalMonths) * 100, 100)
      const uniqueEmployees = new Set(projAllocs.map((a) => a.employee_id))

      // Average FTE: group by month, sum FTE per month, then average
      const monthFte: Record<string, number> = {}
      for (const a of projAllocs) {
        const key = a.allocation_date.substring(0, 7)
        monthFte[key] = (monthFte[key] || 0) + a.allocated_fte
      }
      const fteValues = Object.values(monthFte)
      const avgFte = fteValues.length > 0 ? fteValues.reduce((s, v) => s + v, 0) / fteValues.length : 0

      rows.push({
        project_code: p.id,
        project_name: p.name,
        client: p.client || '',
        status: p.status || '',
        start_date: p.start_date,
        end_date: p.end_date,
        total_months: totalMonths,
        months_covered: monthsCovered,
        months_missing: Math.max(totalMonths - monthsCovered, 0),
        coverage_pct: coveragePct,
        allocation_status: coveragePct >= 100 ? 'Fully Allocated' : 'Partial Coverage',
        employee_count: uniqueEmployees.size,
        avg_fte: avgFte,
      })
    }
  }
  return rows
})

// Coverage KPIs
const coverageKpis = computed(() => {
  const total = coverageRows.value.length
  const fully = coverageRows.value.filter((r) => r.coverage_pct >= 100).length
  const partial = coverageRows.value.filter((r) => r.coverage_pct >= 75 && r.coverage_pct < 100).length
  const uncovered = coverageRows.value.filter((r) => r.coverage_pct < 75).length
  return { total, fully, partial, uncovered }
})

// Coverage filter
const coverageStatusFilter = ref('All')
const coverageProjectStatusFilter = ref('Active')
const coverageStatusOptions = ['All', 'No Allocations', 'Partial Coverage', 'Fully Allocated']
const projectStatusOptions = ['All', 'Active', 'Future', 'Completed', 'On Hold', 'Cancelled']

const filteredCoverageRows = computed(() => {
  let rows = coverageRows.value
  if (coverageProjectStatusFilter.value !== 'All') {
    rows = rows.filter((r) => r.status === coverageProjectStatusFilter.value)
  }
  if (coverageStatusFilter.value !== 'All') {
    rows = rows.filter((r) => r.allocation_status === coverageStatusFilter.value)
  }
  return rows
})

const coverageHeaders = [
  { title: 'Project Code', key: 'project_code' },
  { title: 'Project Name', key: 'project_name' },
  { title: 'Client', key: 'client' },
  { title: 'Status', key: 'status' },
  { title: 'Total Months', key: 'total_months', align: 'end' as const },
  { title: 'Covered', key: 'months_covered', align: 'end' as const },
  { title: 'Missing', key: 'months_missing', align: 'end' as const },
  { title: 'Coverage %', key: 'coverage_pct', align: 'end' as const },
  { title: 'Employees', key: 'employee_count', align: 'end' as const },
  { title: 'Avg FTE', key: 'avg_fte', align: 'end' as const },
  { title: 'Allocation Status', key: 'allocation_status' },
]

function exportCoverage() {
  downloadCsv(filteredCoverageRows.value as unknown as Record<string, unknown>[], `allocation_coverage_${new Date().toISOString().slice(0, 10)}.csv`)
}

// ==========================================================================
// TAB 2: Employee Allocations
// ==========================================================================

interface EmployeeAllocRow {
  employee_id: number
  employee_name: string
  department: string
  role: string
  total_allocated_fte: number
  target_fte: number
  variance_pct: number
  project_count: number
  projects: string
  available_capacity_pct: number
}

const employeeAllocRows = computed<EmployeeAllocRow[]>(() => {
  if (employees.value.length === 0) return []

  const rows: EmployeeAllocRow[] = []

  for (const emp of employees.value) {
    const empAllocs = allocations.value.filter((a) => a.employee_id === emp.id)

    // Skip non-billable employees with no allocations
    if (empAllocs.length === 0 && emp.billable === 0) continue

    // Average across months if multiple months
    const monthlyFte: Record<string, number> = {}
    for (const a of empAllocs) {
      const key = a.allocation_date.substring(0, 7)
      monthlyFte[key] = (monthlyFte[key] || 0) + a.allocated_fte
    }
    const fteValues = Object.values(monthlyFte)
    const avgMonthlyFte = fteValues.length > 0 ? fteValues.reduce((s, v) => s + v, 0) / fteValues.length : 0

    const targetFte = emp.target_allocation ?? 1.0
    const variancePct = targetFte > 0 ? (avgMonthlyFte / targetFte) * 100 : 0
    const uniqueProjects = new Set(empAllocs.map((a) => a.project_name || a.project_id))
    const projectNames = [...uniqueProjects]
    const projectsStr =
      projectNames.length > 3
        ? projectNames.slice(0, 3).join(', ') + ` (+${projectNames.length - 3} more)`
        : projectNames.join(', ')

    rows.push({
      employee_id: emp.id,
      employee_name: emp.name,
      department: emp.department || '',
      role: emp.role || '',
      total_allocated_fte: avgMonthlyFte,
      target_fte: targetFte,
      variance_pct: variancePct,
      project_count: uniqueProjects.size,
      projects: projectsStr,
      available_capacity_pct: Math.max(100 - variancePct, 0),
    })
  }

  return rows.sort((a, b) => b.total_allocated_fte - a.total_allocated_fte)
})

// Employee KPIs
const employeeKpis = computed(() => {
  const total = employeeAllocRows.value.length
  const over = employeeAllocRows.value.filter((r) => r.variance_pct > 100).length
  const healthy = employeeAllocRows.value.filter((r) => r.variance_pct >= 80 && r.variance_pct <= 100).length
  const under = employeeAllocRows.value.filter((r) => r.variance_pct < 80).length
  return { total, over, healthy, under }
})

const employeeAllocHeaders = [
  { title: 'Employee', key: 'employee_name' },
  { title: 'Department', key: 'department' },
  { title: 'Role', key: 'role' },
  { title: 'Target FTE', key: 'target_fte', align: 'end' as const },
  { title: 'Allocated FTE', key: 'total_allocated_fte', align: 'end' as const },
  { title: 'Utilization %', key: 'variance_pct', align: 'end' as const },
  { title: 'Projects', key: 'project_count', align: 'end' as const },
  { title: 'Project List', key: 'projects' },
  { title: 'Available %', key: 'available_capacity_pct', align: 'end' as const },
]

// Top 10 employees chart
const empChartData = computed<Plotly.Data[]>(() => {
  const top10 = employeeAllocRows.value.slice(0, 10)
  if (top10.length === 0) return []

  const names = top10.map((r) => r.employee_name)
  const ftes = top10.map((r) => r.total_allocated_fte)
  const targets = top10.map((r) => r.target_fte)
  const colors = top10.map((r) => {
    if (r.variance_pct > 100) return '#f44336'
    if (r.variance_pct >= 80) return '#4caf50'
    return '#ff9800'
  })

  return [
    {
      type: 'bar' as const,
      x: names,
      y: ftes,
      name: 'Allocated FTE',
      marker: { color: colors },
      text: ftes.map((f) => f.toFixed(2)),
      textposition: 'outside' as const,
    },
    {
      type: 'scatter' as const,
      x: names,
      y: targets,
      name: 'Target FTE',
      mode: 'lines+markers' as const,
      line: { color: 'red', width: 2, dash: 'dash' as const },
      marker: { size: 8 },
    },
  ]
})

const empChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 400,
  xaxis: { tickangle: -45 },
  yaxis: { title: { text: 'FTE' } },
  hovermode: 'x unified' as const,
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.12 },
}))

function exportEmployeeAlloc() {
  downloadCsv(employeeAllocRows.value as unknown as Record<string, unknown>[], `employee_allocations_${new Date().toISOString().slice(0, 10)}.csv`)
}

// ==========================================================================
// TAB 3: Project Allocations
// ==========================================================================

interface ProjectAllocRow {
  project_code: string
  project_name: string
  status: string
  total_fte: number
  employee_count: number
  employees: string
  budget_used_pct: number
}

const projectAllocRows = computed<ProjectAllocRow[]>(() => {
  if (projects.value.length === 0) return []

  const rows: ProjectAllocRow[] = []

  for (const p of projects.value) {
    const projAllocs = allocations.value.filter((a) => a.project_id === p.id)
    if (projAllocs.length === 0 && p.status !== 'Active' && p.status !== 'Future') continue

    // Average monthly FTE
    const monthlyFte: Record<string, number> = {}
    for (const a of projAllocs) {
      const key = a.allocation_date.substring(0, 7)
      monthlyFte[key] = (monthlyFte[key] || 0) + a.allocated_fte
    }
    const fteValues = Object.values(monthlyFte)
    const avgFte = fteValues.length > 0 ? fteValues.reduce((s, v) => s + v, 0) / fteValues.length : 0

    const uniqueEmployees = new Set(projAllocs.map((a) => a.employee_name || String(a.employee_id)))
    const empNames = [...uniqueEmployees]
    const empStr =
      empNames.length > 3
        ? empNames.slice(0, 3).join(', ') + ` (+${empNames.length - 3} more)`
        : empNames.join(', ')

    const budgetUsedPct =
      p.quoted_value && p.quoted_value > 0 && p.budget_used != null
        ? (p.budget_used / p.quoted_value) * 100
        : 0

    rows.push({
      project_code: p.id,
      project_name: p.name,
      status: p.status || '',
      total_fte: avgFte,
      employee_count: uniqueEmployees.size,
      employees: empStr,
      budget_used_pct: budgetUsedPct,
    })
  }

  return rows.sort((a, b) => b.total_fte - a.total_fte)
})

// Project alloc KPIs
const projectAllocKpis = computed(() => {
  const total = projectAllocRows.value.length
  const totalFte = projectAllocRows.value.reduce((s, r) => s + r.total_fte, 0)
  const totalEmployees = new Set(allocations.value.map((a) => a.employee_id)).size
  const avgFte = total > 0 ? totalFte / total : 0
  return { total, totalFte, totalEmployees, avgFte }
})

const projectAllocHeaders = [
  { title: 'Project Code', key: 'project_code' },
  { title: 'Project Name', key: 'project_name' },
  { title: 'Status', key: 'status' },
  { title: 'Total FTE', key: 'total_fte', align: 'end' as const },
  { title: 'Employees', key: 'employee_count', align: 'end' as const },
  { title: 'Team', key: 'employees' },
  { title: 'Budget Used %', key: 'budget_used_pct', align: 'end' as const },
]

// Project FTE chart (top 20)
const projChartData = computed<Plotly.Data[]>(() => {
  const top20 = projectAllocRows.value.slice(0, 20)
  if (top20.length === 0) return []

  const names = top20.map((r) => r.project_name)
  const ftes = top20.map((r) => r.total_fte)

  return [
    {
      type: 'bar' as const,
      y: names,
      x: ftes,
      orientation: 'h' as const,
      marker: { color: '#1976D2' },
      text: ftes.map((f) => f.toFixed(2)),
      textposition: 'outside' as const,
      hoverinfo: 'y+x' as const,
    },
  ]
})

const projChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: Math.max(400, projectAllocRows.value.slice(0, 20).length * 28 + 80),
  xaxis: { title: { text: 'Total FTE' } },
  yaxis: { automargin: true },
  margin: { l: 200, t: 20, r: 40, b: 40 },
}))

function exportProjectAlloc() {
  downloadCsv(projectAllocRows.value as unknown as Record<string, unknown>[], `project_allocations_${new Date().toISOString().slice(0, 10)}.csv`)
}

// ==========================================================================
// TAB 4: Monthly Resource Allocation
// ==========================================================================

const monthlyGroupBy = ref<'employee' | 'project'>('employee')

// Date range helpers
function buildMonthOptions(): { title: string; value: string }[] {
  const months = new Set<string>()
  for (const a of allocations.value) {
    const m = a.allocation_date.substring(0, 7)
    if (m) months.add(m)
  }
  const sorted = [...months].sort()
  return sorted.map((m) => ({ title: m, value: m }))
}

const monthOptions = computed(() => buildMonthOptions())

const monthlyStartMonth = ref<string | null>(null)
const monthlyEndMonth = ref<string | null>(null)

// Auto-set default range when data loads
watch(monthOptions, (opts) => {
  if (opts.length > 0 && !monthlyStartMonth.value) {
    monthlyStartMonth.value = opts[0]!.value
    monthlyEndMonth.value = opts[opts.length - 1]!.value
  }
})

// Filtered allocations by date range
const monthlyFilteredAllocs = computed(() => {
  const start = monthlyStartMonth.value
  const end = monthlyEndMonth.value
  return allocations.value.filter((a) => {
    const m = a.allocation_date.substring(0, 7)
    if (start && m < start) return false
    if (end && m > end) return false
    return true
  })
})

// Get sorted unique months in range
const monthlyColumns = computed(() => {
  const months = new Set<string>()
  for (const a of monthlyFilteredAllocs.value) {
    months.add(a.allocation_date.substring(0, 7))
  }
  return [...months].sort()
})

// Build grouped data
interface MonthlyRow {
  entity_id: string | number
  entity_name: string
  [month: string]: string | number
}

const monthlyRows = computed<MonthlyRow[]>(() => {
  const allocs = monthlyFilteredAllocs.value
  if (allocs.length === 0) return []

  const groupKey = monthlyGroupBy.value === 'employee' ? 'employee' : 'project'
  // Map: entityKey -> { name, months: { month -> fte } }
  const groups: Record<string, { id: string | number; name: string; months: Record<string, number> }> = {}

  for (const a of allocs) {
    const key = groupKey === 'employee' ? String(a.employee_id) : String(a.project_id)
    const name = groupKey === 'employee' ? (a.employee_name || String(a.employee_id)) : (a.project_name || String(a.project_id))
    const month = a.allocation_date.substring(0, 7)

    if (!groups[key]) {
      groups[key] = { id: groupKey === 'employee' ? a.employee_id : a.project_id, name, months: {} }
    }
    groups[key].months[month] = (groups[key].months[month] || 0) + a.allocated_fte
  }

  return Object.values(groups).map((g) => {
    const row: MonthlyRow = { entity_id: g.id, entity_name: g.name }
    for (const m of monthlyColumns.value) {
      row[m] = g.months[m] ?? 0
    }
    return row
  }).sort((a, b) => String(a.entity_name).localeCompare(String(b.entity_name)))
})

// Vuetify v-data-table headers
const monthlyHeaders = computed(() => {
  const label = monthlyGroupBy.value === 'employee' ? 'Employee' : 'Project'
  const cols: Array<{ title: string; key: string; sortable?: boolean; align?: 'start' | 'end' | 'center' }> = [
    { title: label, key: 'entity_name', sortable: true },
  ]
  for (const m of monthlyColumns.value) {
    cols.push({ title: m, key: m, sortable: true, align: 'end' as const })
  }
  return cols
})

// KPIs
const monthlyKpis = computed(() => {
  const allocs = monthlyFilteredAllocs.value
  const totalAllocations = allocs.length
  const entityCount = monthlyRows.value.length
  const totalFte = allocs.reduce((s, a) => s + a.allocated_fte, 0)
  const avgFte = entityCount > 0 ? totalFte / entityCount : 0

  // Peak month
  const monthTotals: Record<string, number> = {}
  for (const a of allocs) {
    const m = a.allocation_date.substring(0, 7)
    monthTotals[m] = (monthTotals[m] || 0) + a.allocated_fte
  }
  let peakMonth = '-'
  let peakVal = 0
  for (const [m, v] of Object.entries(monthTotals)) {
    if (v > peakVal) {
      peakVal = v
      peakMonth = m
    }
  }

  return { totalAllocations, avgFte, peakMonth, peakVal }
})

function exportMonthlyResource() {
  downloadCsv(monthlyRows.value as unknown as Record<string, unknown>[], `monthly_resource_allocation_${new Date().toISOString().slice(0, 10)}.csv`)
}

// ==========================================================================
// CSV Template Generator
// ==========================================================================

const csvTemplateDialog = ref(false)
const csvTemplateSelectedProjects = ref<string[]>([])
const csvTemplateStartMonth = ref('')
const csvTemplateEndMonth = ref('')

// Project options for the autocomplete
const csvProjectOptions = computed(() =>
  projects.value.map((p) => ({
    title: `${p.id} - ${p.name}`,
    value: p.id,
  }))
)

// Employees associated with selected projects (from allocations)
const csvTemplateEmployeeOptions = computed(() => {
  if (csvTemplateSelectedProjects.value.length === 0) return []

  const selectedIds = new Set(csvTemplateSelectedProjects.value)
  const relevantAllocs = allocations.value.filter((a) => selectedIds.has(a.project_id))

  const empMap = new Map<number, string>()
  for (const a of relevantAllocs) {
    if (!empMap.has(a.employee_id)) {
      empMap.set(a.employee_id, a.employee_name || String(a.employee_id))
    }
  }

  return [...empMap.entries()].map(([id, name]) => ({
    title: `${id} - ${name}`,
    value: id,
  }))
})

const csvTemplateSelectedEmployees = ref<number[]>([])

// Auto-select all employees when projects change
watch(csvTemplateEmployeeOptions, (opts) => {
  csvTemplateSelectedEmployees.value = opts.map((o) => o.value)
})

// Generate months between start and end (inclusive)
function generateMonthRange(start: string, end: string): string[] {
  if (!start || !end) return []
  const months: string[] = []
  const parts = start.split('-').map(Number)
  const endParts = end.split('-').map(Number)
  const sy = parts[0] ?? 0
  const sm = parts[1] ?? 0
  const ey = endParts[0] ?? 0
  const em = endParts[1] ?? 0

  let y = sy
  let m = sm
  while (y < ey || (y === ey && m <= em)) {
    months.push(`${y}-${String(m).padStart(2, '0')}`)
    m++
    if (m > 12) {
      m = 1
      y++
    }
  }
  return months
}

// Build template preview rows
const csvTemplateRows = computed<TemplateRow[]>(() => {
  const selectedProjectIds = new Set(csvTemplateSelectedProjects.value)
  const selectedEmpIds = new Set(csvTemplateSelectedEmployees.value)
  if (selectedProjectIds.size === 0) return []

  const months = generateMonthRange(csvTemplateStartMonth.value, csvTemplateEndMonth.value)
  if (months.length === 0) return []

  const rows: TemplateRow[] = []

  // Build a lookup: projectId+employeeId+month -> allocation
  const allocLookup = new Map<string, Allocation>()
  for (const a of allocations.value) {
    if (!selectedProjectIds.has(a.project_id)) continue
    const allocMonth = a.allocation_date.substring(0, 7)
    const key = `${a.project_id}|${a.employee_id}|${allocMonth}`
    allocLookup.set(key, a)
  }

  // Determine which employee-project pairs exist in allocations
  const empProjectPairs = new Set<string>()
  for (const a of allocations.value) {
    if (selectedProjectIds.has(a.project_id) && selectedEmpIds.has(a.employee_id)) {
      empProjectPairs.add(`${a.project_id}|${a.employee_id}`)
    }
  }

  // Employee name lookup
  const empNameMap = new Map<number, string>()
  for (const e of employees.value) {
    empNameMap.set(e.id, e.name)
  }
  for (const a of allocations.value) {
    if (a.employee_name && !empNameMap.has(a.employee_id)) {
      empNameMap.set(a.employee_id, a.employee_name)
    }
  }

  for (const pair of empProjectPairs) {
    const [projId = '', empIdStr] = pair.split('|')
    const empId = Number(empIdStr)
    const empName = empNameMap.get(empId) || String(empId)

    for (const month of months) {
      const key = `${projId}|${empId}|${month}`
      const existing = allocLookup.get(key)
      rows.push({
        employee_id: empId,
        employee_name: empName,
        project_id: projId,
        allocation_date: `${month}-01`,
        fte: existing?.allocated_fte ?? 0,
        bill_rate: existing?.bill_rate ?? null,
        role: existing?.role ?? null,
      })
    }
  }

  // Sort by project, employee, date
  rows.sort((a, b) => {
    if (a.project_id !== b.project_id) return a.project_id.localeCompare(b.project_id)
    if (a.employee_id !== b.employee_id) return a.employee_id - b.employee_id
    return a.allocation_date.localeCompare(b.allocation_date)
  })

  return rows
})

const csvTemplateHeaders = [
  { title: 'Employee ID', key: 'employee_id', sortable: true },
  { title: 'Employee Name', key: 'employee_name', sortable: true },
  { title: 'Project ID', key: 'project_id', sortable: true },
  { title: 'Allocation Date', key: 'allocation_date', sortable: true },
  { title: 'FTE', key: 'fte', sortable: true, align: 'end' as const },
  { title: 'Bill Rate', key: 'bill_rate', sortable: true, align: 'end' as const },
  { title: 'Role', key: 'role', sortable: true },
]

function downloadCsvTemplate() {
  const exportRows = csvTemplateRows.value.map((r) => ({
    employee_id: r.employee_id,
    employee_name: r.employee_name,
    project_id: r.project_id,
    allocation_date: r.allocation_date,
    fte: r.fte,
    bill_rate: r.bill_rate ?? '',
    role: r.role ?? '',
  }))
  downloadCsv(exportRows as unknown as Record<string, unknown>[], `allocation_template_${new Date().toISOString().slice(0, 10)}.csv`)
}

function openCsvTemplateDialog() {
  csvTemplateSelectedProjects.value = []
  csvTemplateSelectedEmployees.value = []
  const now = new Date()
  csvTemplateStartMonth.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  // Default end: 3 months from now
  const end = new Date(now.getFullYear(), now.getMonth() + 3, 1)
  csvTemplateEndMonth.value = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}`
  csvTemplateDialog.value = true
}
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-2">
      <h1 class="text-h4 font-weight-bold">Reports</h1>
      <v-btn color="primary" prepend-icon="mdi-file-table-outline" variant="outlined" @click="openCsvTemplateDialog">
        Generate CSV Template
      </v-btn>
    </div>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Allocation coverage, employee allocations, project allocations, and monthly resource allocation.
    </p>

    <!-- Error banner -->
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      closable
      class="mb-4"
      @click:close="errorMessage = null"
    >
      {{ errorMessage }}
    </v-alert>

    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab :value="0">Allocation Coverage</v-tab>
      <v-tab :value="1">Employee Allocations</v-tab>
      <v-tab :value="2">Project Allocations</v-tab>
      <v-tab :value="3">Monthly Resource Allocation</v-tab>
    </v-tabs>

    <!-- ============================================================ -->
    <!-- TAB 1: Allocation Coverage -->
    <!-- ============================================================ -->
    <v-tabs-window v-model="activeTab">
      <v-tabs-window-item :value="0">
        <!-- KPIs -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Projects"
              :value="String(coverageKpis.total)"
              icon="mdi-folder-multiple"
              color="#1976D2"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Fully Covered"
              :value="String(coverageKpis.fully)"
              icon="mdi-check-circle"
              color="#4CAF50"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Partially Covered"
              :value="String(coverageKpis.partial)"
              icon="mdi-alert-circle"
              color="#FB8C00"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Uncovered"
              :value="String(coverageKpis.uncovered)"
              icon="mdi-close-circle"
              color="#FF5252"
              :loading="loadingData"
            />
          </v-col>
        </v-row>

        <!-- Filters -->
        <v-card class="pa-4 mb-4">
          <v-row>
            <v-col cols="12" sm="6" md="4">
              <v-select
                v-model="coverageProjectStatusFilter"
                :items="projectStatusOptions"
                label="Project Status"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <v-select
                v-model="coverageStatusFilter"
                :items="coverageStatusOptions"
                label="Allocation Status"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" md="4" class="d-flex align-center">
              <v-btn
                prepend-icon="mdi-download"
                variant="outlined"
                color="primary"
                @click="exportCoverage"
                :disabled="filteredCoverageRows.length === 0"
              >
                Export CSV
              </v-btn>
            </v-col>
          </v-row>
        </v-card>

        <!-- Grid -->
        <v-card class="pa-0 mb-4">
          <v-skeleton-loader v-if="loadingData" type="table-heading, table-row@8" />
          <v-data-table
            v-else
            :headers="coverageHeaders"
            :items="filteredCoverageRows"
            :items-per-page="25"
            density="compact"
            hover
          >
            <template #item.coverage_pct="{ value }">
              <div v-if="value != null" class="d-flex align-center" style="min-width: 150px;">
                <v-progress-linear
                  :model-value="Math.min(Math.max(value, 0), 100)"
                  :color="coverageColor(value)"
                  height="16"
                  rounded
                  class="flex-grow-1 mr-2"
                />
                <span style="min-width: 45px; text-align: right;">{{ value.toFixed(1) }}%</span>
              </div>
              <span v-else>-</span>
            </template>
            <template #item.avg_fte="{ value }">
              {{ value != null ? value.toFixed(2) : '-' }}
            </template>
          </v-data-table>
        </v-card>
      </v-tabs-window-item>

      <!-- ============================================================ -->
      <!-- TAB 2: Employee Allocations -->
      <!-- ============================================================ -->
      <v-tabs-window-item :value="1">
        <!-- KPIs -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Employees"
              :value="String(employeeKpis.total)"
              icon="mdi-account-group"
              color="#1976D2"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Over-Allocated"
              :value="String(employeeKpis.over)"
              :subtitle="employeeKpis.total > 0 ? formatPercent(employeeKpis.over / employeeKpis.total * 100) : '0%'"
              icon="mdi-alert"
              color="#FF5252"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Healthy"
              :value="String(employeeKpis.healthy)"
              :subtitle="employeeKpis.total > 0 ? formatPercent(employeeKpis.healthy / employeeKpis.total * 100) : '0%'"
              icon="mdi-check-circle"
              color="#4CAF50"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Under-Allocated"
              :value="String(employeeKpis.under)"
              :subtitle="employeeKpis.total > 0 ? formatPercent(employeeKpis.under / employeeKpis.total * 100) : '0%'"
              icon="mdi-account-clock"
              color="#FB8C00"
              :loading="loadingData"
            />
          </v-col>
        </v-row>

        <!-- Export -->
        <v-card class="pa-4 mb-4">
          <v-row>
            <v-col class="d-flex align-center">
              <v-btn
                prepend-icon="mdi-download"
                variant="outlined"
                color="primary"
                @click="exportEmployeeAlloc"
                :disabled="employeeAllocRows.length === 0"
              >
                Export CSV
              </v-btn>
            </v-col>
          </v-row>
        </v-card>

        <!-- Grid -->
        <v-card class="pa-0 mb-4">
          <v-skeleton-loader v-if="loadingData" type="table-heading, table-row@8" />
          <v-data-table
            v-else
            :headers="employeeAllocHeaders"
            :items="employeeAllocRows"
            :items-per-page="25"
            density="compact"
            hover
          >
            <template #item.target_fte="{ value }">
              {{ value != null ? value.toFixed(2) : '-' }}
            </template>
            <template #item.total_allocated_fte="{ value }">
              {{ value != null ? value.toFixed(2) : '-' }}
            </template>
            <template #item.variance_pct="{ value }">
              <div v-if="value != null" class="d-flex align-center" style="min-width: 150px;">
                <v-progress-linear
                  :model-value="Math.min(Math.max(value, 0), 150) / 150 * 100"
                  :color="utilizationColor(value)"
                  height="16"
                  rounded
                  class="flex-grow-1 mr-2"
                />
                <span style="min-width: 45px; text-align: right;">{{ value.toFixed(1) }}%</span>
              </div>
              <span v-else>-</span>
            </template>
            <template #item.available_capacity_pct="{ value }">
              {{ value != null ? value.toFixed(1) + '%' : '-' }}
            </template>
          </v-data-table>
        </v-card>

        <!-- Chart -->
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-bar" size="20" class="mr-1" />
            Top 10 Most Allocated Employees
          </div>
          <PlotlyChart
            :data="empChartData"
            :layout="empChartLayout"
            :loading="loadingData"
          />
        </v-card>
      </v-tabs-window-item>

      <!-- ============================================================ -->
      <!-- TAB 3: Project Allocations -->
      <!-- ============================================================ -->
      <v-tabs-window-item :value="2">
        <!-- KPIs -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Projects"
              :value="String(projectAllocKpis.total)"
              icon="mdi-folder-multiple"
              color="#1976D2"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total FTE Allocated"
              :value="projectAllocKpis.totalFte.toFixed(1)"
              icon="mdi-account-multiple-check"
              color="#2E7D32"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Unique Employees"
              :value="String(projectAllocKpis.totalEmployees)"
              icon="mdi-account-group"
              color="#7B1FA2"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Avg FTE per Project"
              :value="projectAllocKpis.avgFte.toFixed(2)"
              icon="mdi-chart-timeline-variant"
              color="#E65100"
              :loading="loadingData"
            />
          </v-col>
        </v-row>

        <!-- Export -->
        <v-card class="pa-4 mb-4">
          <v-row>
            <v-col class="d-flex align-center">
              <v-btn
                prepend-icon="mdi-download"
                variant="outlined"
                color="primary"
                @click="exportProjectAlloc"
                :disabled="projectAllocRows.length === 0"
              >
                Export CSV
              </v-btn>
            </v-col>
          </v-row>
        </v-card>

        <!-- Grid -->
        <v-card class="pa-0 mb-4">
          <v-skeleton-loader v-if="loadingData" type="table-heading, table-row@8" />
          <v-data-table
            v-else
            :headers="projectAllocHeaders"
            :items="projectAllocRows"
            :items-per-page="25"
            density="compact"
            hover
          >
            <template #item.total_fte="{ value }">
              {{ value != null ? value.toFixed(2) : '-' }}
            </template>
            <template #item.budget_used_pct="{ value }">
              <div v-if="value != null" class="d-flex align-center" style="min-width: 150px;">
                <v-progress-linear
                  :model-value="Math.min(Math.max(value, 0), 100)"
                  :color="budgetUsedColor(value)"
                  height="16"
                  rounded
                  class="flex-grow-1 mr-2"
                />
                <span style="min-width: 45px; text-align: right;">{{ value.toFixed(1) }}%</span>
              </div>
              <span v-else>-</span>
            </template>
          </v-data-table>
        </v-card>

        <!-- Chart -->
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-bar" size="20" class="mr-1" />
            Projects by FTE Allocation
          </div>
          <PlotlyChart
            :data="projChartData"
            :layout="projChartLayout"
            :loading="loadingData"
          />
        </v-card>
      </v-tabs-window-item>

      <!-- ============================================================ -->
      <!-- TAB 4: Monthly Resource Allocation -->
      <!-- ============================================================ -->
      <v-tabs-window-item :value="3">
        <!-- KPIs -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="4">
            <KpiCard
              title="Total Allocations"
              :value="String(monthlyKpis.totalAllocations)"
              icon="mdi-calendar-check"
              color="#1976D2"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <KpiCard
              title="Avg FTE per Entity"
              :value="monthlyKpis.avgFte.toFixed(2)"
              icon="mdi-account-details"
              color="#2E7D32"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <KpiCard
              title="Peak Month"
              :value="monthlyKpis.peakMonth"
              :subtitle="monthlyKpis.peakVal > 0 ? monthlyKpis.peakVal.toFixed(2) + ' FTE' : ''"
              icon="mdi-chart-line-variant"
              color="#E65100"
              :loading="loadingData"
            />
          </v-col>
        </v-row>

        <!-- Filters -->
        <v-card class="pa-4 mb-4">
          <v-row align="center">
            <v-col cols="12" sm="6" md="3">
              <v-btn-toggle
                v-model="monthlyGroupBy"
                mandatory
                color="primary"
                density="compact"
                divided
                variant="outlined"
              >
                <v-btn value="employee">
                  <v-icon start icon="mdi-account-group" />
                  Group by Employee
                </v-btn>
                <v-btn value="project">
                  <v-icon start icon="mdi-folder-multiple" />
                  Group by Project
                </v-btn>
              </v-btn-toggle>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-select
                v-model="monthlyStartMonth"
                :items="monthOptions"
                label="Start Month"
                density="compact"
                variant="outlined"
                hide-details
                clearable
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-select
                v-model="monthlyEndMonth"
                :items="monthOptions"
                label="End Month"
                density="compact"
                variant="outlined"
                hide-details
                clearable
              />
            </v-col>
            <v-col cols="12" sm="6" md="3" class="d-flex align-center">
              <v-btn
                prepend-icon="mdi-download"
                variant="outlined"
                color="primary"
                @click="exportMonthlyResource"
                :disabled="monthlyRows.length === 0"
              >
                Export CSV
              </v-btn>
            </v-col>
          </v-row>
        </v-card>

        <!-- Data Table -->
        <v-card class="pa-0 mb-4">
          <v-skeleton-loader v-if="loadingData" type="table-heading, table-row@8" />
          <v-data-table
            v-else
            :headers="monthlyHeaders"
            :items="monthlyRows"
            :items-per-page="25"
            density="compact"
            class="elevation-0"
          >
            <template v-for="month in monthlyColumns" :key="month" #[`item.${month}`]="{ value }">
              <span :class="{ 'font-weight-bold': Number(value) > 0, 'text-grey-lighten-1': Number(value) === 0 }">
                {{ Number(value).toFixed(2) }}
              </span>
            </template>
            <template #no-data>
              <div class="text-center pa-4 text-medium-emphasis">
                No allocation data available for the selected range.
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-tabs-window-item>
    </v-tabs-window>

    <!-- CSV Template Generator Dialog -->
    <v-dialog v-model="csvTemplateDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="text-h5 pa-4 pb-2">
          <v-icon icon="mdi-file-table-outline" class="mr-2" />
          Generate Allocation CSV Template
        </v-card-title>

        <v-card-text class="pa-4">
          <v-row dense>
            <v-col cols="12">
              <v-autocomplete
                v-model="csvTemplateSelectedProjects"
                :items="csvProjectOptions"
                label="Select Projects"
                multiple
                chips
                closable-chips
                density="compact"
                variant="outlined"
                hint="Choose projects to include in the template"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="csvTemplateStartMonth"
                label="Start Month"
                type="month"
                density="compact"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="csvTemplateEndMonth"
                label="End Month"
                type="month"
                density="compact"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12">
              <v-autocomplete
                v-model="csvTemplateSelectedEmployees"
                :items="csvTemplateEmployeeOptions"
                label="Select Employees"
                multiple
                chips
                closable-chips
                density="compact"
                variant="outlined"
                hint="Pre-populated from allocations of selected projects"
                persistent-hint
              />
            </v-col>
          </v-row>

          <!-- Preview table -->
          <div v-if="csvTemplateRows.length > 0" class="mt-4">
            <div class="text-subtitle-2 mb-2">
              Preview ({{ csvTemplateRows.length }} rows)
            </div>
            <v-data-table
              :headers="csvTemplateHeaders"
              :items="csvTemplateRows"
              :items-per-page="10"
              density="compact"
              class="elevation-1"
            >
              <template #item.fte="{ value }">
                <span :class="{ 'text-grey-lighten-1': Number(value) === 0, 'font-weight-bold': Number(value) > 0 }">
                  {{ Number(value).toFixed(2) }}
                </span>
              </template>
              <template #item.bill_rate="{ value }">
                {{ value != null ? `$${Number(value).toFixed(0)}` : '-' }}
              </template>
            </v-data-table>
          </div>
          <div v-else-if="csvTemplateSelectedProjects.length > 0" class="mt-4 text-center text-medium-emphasis pa-4">
            No allocation data found for the selected projects and date range.
            Select projects and a date range to generate the template.
          </div>
          <div v-else class="mt-4 text-center text-medium-emphasis pa-4">
            Select at least one project to preview the template.
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="csvTemplateDialog = false">
            Close
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-download"
            :disabled="csvTemplateRows.length === 0"
            @click="downloadCsvTemplate"
          >
            Download CSV
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
