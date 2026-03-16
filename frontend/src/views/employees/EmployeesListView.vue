<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useApi } from '@/composables/useApi'
import { useEmployeesStore } from '@/stores/employees'
import { downloadCsv } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type {
  Employee,
  AllocationPlanningEntry,
  AllocationProjectBreakdown,
  DetailedUtilizationEntry,
} from '@/types'

const route = useRoute()
const router = useRouter()
const { get, loading, error } = useApi()

// ---------------------------------------------------------------------------
// Pinia store – persists filter/sort state across navigation
// ---------------------------------------------------------------------------
const store = useEmployeesStore()
const {
  // Tab 1: Employee List
  selectedBillableStatus, selectedPayType, searchTerm, employeeListSortBy,
  // Tab 2: Allocation Overview
  allocYear, allocMonth, allocStatusFilter, allocSearchTerm,
  // Tab 3: Utilization Overview
  utilYear, utilTimeFrameType, selectedMonth, selectedQuarter, fyType,
  includeProjectedHours, utilBandFilter, utilSearchTerm, utilTableSortBy,
} = storeToRefs(store)

// ---------------------------------------------------------------------------
// Shared state
// ---------------------------------------------------------------------------
const tabPathMap: Record<string, number> = {
  '/employees': 0,
  '/employees/allocation_overview': 1,
  '/employees/utilization_overview': 2,
}

const tabIndexToPath: Record<number, string> = {
  0: '/employees',
  1: '/employees/allocation_overview',
  2: '/employees/utilization_overview',
}

const activeTab = computed(() => tabPathMap[route.path] ?? 0)

function navigateTab(tabIndex: number) {
  const path = tabIndexToPath[tabIndex] ?? '/employees'
  if (route.path !== path) {
    router.push(path)
  }
}
const employees = ref<Employee[]>([])

async function fetchEmployees() {
  try {
    employees.value = await get<Employee[]>('/employees/')
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchEmployees)

// =====================================================================
// TAB 1 - Employee List
// =====================================================================

// Filters (state stored in Pinia – see storeToRefs above)

const filteredEmployees = computed(() => {
  let result = employees.value

  if (selectedBillableStatus.value === 'Billable') {
    result = result.filter((e) => e.billable === 1)
  } else if (selectedBillableStatus.value === 'Non-Billable') {
    result = result.filter((e) => e.billable !== 1)
  }

  if (selectedPayType.value === 'Hourly') {
    result = result.filter((e) => (e.pay_type ?? '').toLowerCase() === 'hourly')
  } else if (selectedPayType.value === 'Salary') {
    result = result.filter((e) => (e.pay_type ?? '').toLowerCase() === 'salary')
  }

  if (searchTerm.value) {
    const term = searchTerm.value.toLowerCase()
    result = result.filter(
      (e) =>
        (e.name ?? '').toLowerCase().includes(term)
    )
  }

  return result
})

// Summary metrics
const totalEmployees = computed(() => filteredEmployees.value.length)

const avgUtilization = computed(() => {
  const vals = filteredEmployees.value
    .map((e) => e.utilization)
    .filter((v): v is number => v != null)
  if (vals.length === 0) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

const avgHourlyRate = computed(() => {
  const vals = filteredEmployees.value
    .map((e) => e.hourly_rate ?? e.cost_rate)
    .filter((v): v is number => v != null && v > 0)
  if (vals.length === 0) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

// Summary chip counts
const billableCount = computed(() => filteredEmployees.value.filter((e) => e.billable === 1).length)
const salaryCount = computed(() => filteredEmployees.value.filter((e) => (e.pay_type ?? '').toLowerCase() === 'salary').length)
const hourlyCount = computed(() => filteredEmployees.value.filter((e) => (e.pay_type ?? '').toLowerCase() === 'hourly').length)

// Currency formatter
function formatCurrencyLocal(value: number | null | undefined): string {
  if (value == null) return '-'
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// v-data-table headers for Employee List
const listHeaders = [
  { title: 'Name', key: 'name', minWidth: '160px' },
  { title: 'Role', key: 'role', minWidth: '140px' },
  { title: 'Pay Type', key: 'pay_type', minWidth: '100px' },
  { title: 'Billable', key: 'billable', minWidth: '90px' },
  { title: 'Cost Rate', key: 'cost_rate', minWidth: '120px', align: 'end' as const },
  { title: 'FTE', key: 'fte', minWidth: '80px', align: 'end' as const },
  { title: 'Target Alloc', key: 'target_allocation', minWidth: '110px', align: 'end' as const },
  { title: 'Hire Date', key: 'hire_date', minWidth: '120px' },
  { title: 'Term Date', key: 'term_date', minWidth: '120px' },
]

function onListRowClicked(item: Employee) {
  if (item?.id != null) {
    router.push(`/employees/${item.id}`)
  }
}

function exportListCsv() {
  downloadCsv(filteredEmployees.value as unknown as Record<string, unknown>[], 'employees.csv')
}

// =====================================================================
// TAB 2 - Allocation Overview
// =====================================================================

const now = new Date()
// allocYear, allocMonth stored in Pinia – see storeToRefs above
const allocData = ref<AllocationPlanningEntry[]>([])
const allocLoading = ref(false)

// Dialog for project breakdown
const allocDialogOpen = ref(false)
const allocDialogEmployee = ref<AllocationPlanningEntry | null>(null)

const yearOptions = computed(() => {
  const y = now.getFullYear()
  return [y - 1, y, y + 1]
})

const monthOptions = [
  { title: 'January', value: 1 },
  { title: 'February', value: 2 },
  { title: 'March', value: 3 },
  { title: 'April', value: 4 },
  { title: 'May', value: 5 },
  { title: 'June', value: 6 },
  { title: 'July', value: 7 },
  { title: 'August', value: 8 },
  { title: 'September', value: 9 },
  { title: 'October', value: 10 },
  { title: 'November', value: 11 },
  { title: 'December', value: 12 },
]

async function fetchAllocationData() {
  allocLoading.value = true
  try {
    allocData.value = await get<AllocationPlanningEntry[]>(
      `/analytics/allocation-planning?year=${allocYear.value}&month=${allocMonth.value}`
    )
  } catch {
    // error handled by useApi
  } finally {
    allocLoading.value = false
  }
}

watch([allocYear, allocMonth], fetchAllocationData)
watch(activeTab, (tab) => {
  if (tab === 1 && allocData.value.length === 0 && !allocLoading.value) {
    fetchAllocationData()
  }
})

// KPI computeds
const allocTotalEmployees = computed(() => filteredAllocData.value.length)
const allocOverAllocated = computed(() => filteredAllocData.value.filter((e) => e.allocation_pct > 100).length)
const allocUnderAllocated = computed(() => filteredAllocData.value.filter((e) => e.allocation_pct < 80).length)
const allocAvgPct = computed(() => {
  if (filteredAllocData.value.length === 0) return 0
  return filteredAllocData.value.reduce((sum, e) => sum + e.allocation_pct, 0) / filteredAllocData.value.length
})

// Allocation filters (state stored in Pinia – see storeToRefs above)

const allocStatusOptions = ['Over-Allocated', 'Fully Allocated', 'On Target', 'Under-Allocated', 'Warning']

const filteredAllocData = computed(() => {
  let result = allocData.value

  if (allocStatusFilter.value.length > 0) {
    result = result.filter(e => allocStatusFilter.value.includes(e.status))
  }

  if (allocSearchTerm.value) {
    const term = allocSearchTerm.value.toLowerCase()
    result = result.filter(e => (e.employee_name ?? '').toLowerCase().includes(term))
  }

  return result
})

// v-data-table headers for Allocation Overview
const allocHeaders = [
  { title: 'Employee Name', key: 'employee_name', minWidth: '160px' },
  { title: 'Target FTE', key: 'target_fte', minWidth: '100px', align: 'end' as const },
  { title: 'Possible Hours', key: 'possible_hours', minWidth: '120px', align: 'end' as const },
  { title: 'Allocated Hours', key: 'allocated_hours', minWidth: '130px', align: 'end' as const },
  { title: 'Allocation %', key: 'allocation_pct', minWidth: '120px', align: 'end' as const },
  { title: 'Variance', key: 'variance', minWidth: '100px', align: 'end' as const },
  { title: 'Status', key: 'status', minWidth: '130px' },
]

function onAllocRowClicked(item: AllocationPlanningEntry) {
  if (item) {
    allocDialogEmployee.value = item
    allocDialogOpen.value = true
  }
}

// Dialog project breakdown table headers
const breakdownHeaders = [
  { title: 'Project', key: 'project_name' },
  { title: 'FTE', key: 'allocated_fte' },
  { title: 'Hours', key: 'allocated_hours' },
  { title: 'Bill Rate', key: 'bill_rate' },
]

// Pie chart data for dialog
const dialogPieData = computed(() => {
  const emp = allocDialogEmployee.value
  if (!emp || !emp.project_breakdown || emp.project_breakdown.length === 0) return []
  return [
    {
      type: 'pie' as const,
      labels: emp.project_breakdown.map((p: AllocationProjectBreakdown) => p.project_name),
      values: emp.project_breakdown.map((p: AllocationProjectBreakdown) => p.allocated_hours),
      hole: 0.4,
      textinfo: 'label+percent' as const,
    },
  ]
})

const dialogPieLayout = { margin: { t: 10, r: 10, b: 10, l: 10 }, height: 300, showlegend: false }

// Bar chart: Allocation % by Employee
const allocBarData = computed(() => {
  if (filteredAllocData.value.length === 0) return []
  const sorted = [...filteredAllocData.value].sort((a, b) => b.allocation_pct - a.allocation_pct)
  const colors = sorted.map((e) => {
    if (e.allocation_pct > 120) return '#F44336'
    if (e.allocation_pct > 100) return '#FF9800'
    if (e.allocation_pct >= 80) return '#4CAF50'
    return '#2196F3'
  })
  return [
    {
      type: 'bar' as const,
      x: sorted.map((e) => e.employee_name),
      y: sorted.map((e) => e.allocation_pct),
      marker: { color: colors },
    },
  ]
})

const allocBarLayout = computed(() => ({
  height: 350,
  margin: { t: 20, r: 20, b: 100, l: 50 },
  xaxis: { tickangle: -45 },
  yaxis: { title: { text: 'Allocation %' } },
  shapes: [
    {
      type: 'line' as const,
      x0: 0, x1: 1, xref: 'paper' as const,
      y0: 80, y1: 80, yref: 'y' as const,
      line: { color: '#4CAF50', width: 2, dash: 'dash' as const },
    },
    {
      type: 'line' as const,
      x0: 0, x1: 1, xref: 'paper' as const,
      y0: 100, y1: 100, yref: 'y' as const,
      line: { color: '#F44336', width: 2, dash: 'dash' as const },
    },
  ],
}))

function exportAllocCsv() {
  const rows = filteredAllocData.value.map((e) => ({
    Employee: e.employee_name,
    'Target FTE': e.target_fte,
    'Possible Hours': e.possible_hours,
    'Allocated Hours': e.allocated_hours,
    'Allocation %': e.allocation_pct,
    Variance: e.variance,
    Status: e.status,
  }))
  downloadCsv(rows, `allocation_overview_${allocYear.value}_${allocMonth.value}.csv`)
}

// =====================================================================
// TAB 3 - Utilization Overview
// =====================================================================

// utilYear, includeProjectedHours, utilTimeFrameType, selectedMonth,
// selectedQuarter, fyType stored in Pinia – see storeToRefs above
const utilData = ref<DetailedUtilizationEntry[]>([])
const utilLoading = ref(false)

const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const currentQuarter = `Q${Math.ceil((now.getMonth() + 1) / 3)}`

// Gov quarter mapping: Company Q1 (Jan-Mar) = Gov Q2, etc.
const govQuarterMap: Record<string, string> = { Q1: 'q2', Q2: 'q3', Q3: 'q4', Q4: 'q1' }

// Compute the API time_frame param based on filter selections
const utilTimeFrame = computed(() => {
  switch (utilTimeFrameType.value) {
    case 'Monthly':
      return selectedMonth.value.toLowerCase()
    case 'Quarterly':
      if (fyType.value === 'Gov') {
        return govQuarterMap[selectedQuarter.value] ?? selectedQuarter.value.toLowerCase()
      }
      return selectedQuarter.value.toLowerCase()
    case 'QTD':
      return fyType.value === 'Gov' ? 'qtd_gov' : 'qtd_company'
    case 'YTD':
      return fyType.value === 'Gov' ? 'ytd_gov' : 'ytd_company'
    default:
      return 'ytd_company'
  }
})

async function fetchUtilizationData() {
  utilLoading.value = true
  try {
    utilData.value = await get<DetailedUtilizationEntry[]>(
      `/analytics/utilization/detailed?year=${utilYear.value}&time_frame=${utilTimeFrame.value}&include_projected=${includeProjectedHours.value}`
    )
  } catch {
    // error handled by useApi
  } finally {
    utilLoading.value = false
  }
}

watch([utilYear, utilTimeFrame, includeProjectedHours], fetchUtilizationData)
watch(activeTab, (tab) => {
  if (tab === 2 && utilData.value.length === 0 && !utilLoading.value) {
    fetchUtilizationData()
  }
})

// KPI computeds
const utilTotalEmployees = computed(() => filteredUtilData.value.length)
const utilAvgUtilization = computed(() => {
  const vals = filteredUtilData.value
    .map((e) => e.utilization_pct)
    .filter((v): v is number => v != null)
  if (vals.length === 0) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
})
const utilOverTarget = computed(() => filteredUtilData.value.filter((e) => (e.utilization_pct ?? 0) >= 80).length)
const utilUnderTarget = computed(() => filteredUtilData.value.filter((e) => (e.utilization_pct ?? 0) < 80).length)
const utilPtoHours = computed(() => filteredUtilData.value.reduce((sum, e) => sum + (e.pto_hours ?? 0), 0))
const utilTotalPossibleHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.possible_hours ?? 0), 0))
const utilTotalActualHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.actual_hours ?? 0), 0))
const utilTotalBillableHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.actual_billable_hours ?? 0), 0))
const utilTotalProjectedMissingHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.projected_hours ?? 0), 0))
const utilTotalEffectiveBillableHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.effective_billable_hours ?? 0), 0))
const utilTotalHolidayHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.holiday_hours ?? 0), 0))

// Utilization filters (utilBandFilter, utilSearchTerm stored in Pinia)
const showTimeFrameDefs = ref<number | undefined>(undefined)
const selectedUtilEmployee = ref<string | null>(null)

const utilBandOptions = [
  { label: '\u2265111% Over', min: 111, max: Infinity },
  { label: '97-110% Good', min: 97, max: 111 },
  { label: '80-96% Fair', min: 80, max: 97 },
  { label: '51-79% Low', min: 51, max: 80 },
  { label: '\u226450% Under', min: 0, max: 51 },
]

const filteredUtilData = computed(() => {
  let result = utilData.value

  if (utilBandFilter.value.length > 0) {
    result = result.filter(e => {
      const pct = Math.round(e.utilization_pct ?? 0)
      return utilBandFilter.value.some(label => {
        const band = utilBandOptions.find(b => b.label === label)
        if (!band) return false
        return pct >= band.min && pct < band.max
      })
    })
  }

  if (utilSearchTerm.value) {
    const term = utilSearchTerm.value.toLowerCase()
    result = result.filter(e => (e.employee_name ?? '').toLowerCase().includes(term))
  }

  return result
})

// Utilization band summary cards
const utilBandSummary = computed(() => {
  const data = filteredUtilData.value
  const bands = [
    { label: '111%+', icon: '\uD83D\uDFE3', bgColor: '#fce4ec', borderColor: '#e91e63', min: 111, max: Infinity, employees: [] as { name: string; pct: number }[] },
    { label: '97% - 110%', icon: '\uD83D\uDFE2', bgColor: '#e8f5e9', borderColor: '#28a745', min: 97, max: 111, employees: [] as { name: string; pct: number }[] },
    { label: '80% - 96%', icon: '\uD83D\uDFE1', bgColor: '#fff8e1', borderColor: '#ffc107', min: 80, max: 97, employees: [] as { name: string; pct: number }[] },
    { label: '51% - 79%', icon: '\uD83D\uDFE0', bgColor: '#fff3e0', borderColor: '#fd7e14', min: 51, max: 80, employees: [] as { name: string; pct: number }[] },
    { label: '\u2264 50%', icon: '\uD83D\uDD34', bgColor: '#ffebee', borderColor: '#dc3545', min: 0, max: 51, employees: [] as { name: string; pct: number }[] },
  ]

  for (const emp of data) {
    const pct = Math.round(emp.utilization_pct ?? 0)
    for (const band of bands) {
      if (pct >= band.min && (band.max === Infinity ? true : pct < band.max)) {
        band.employees.push({ name: emp.employee_name, pct: Math.round(emp.utilization_pct ?? 0) })
        break
      }
    }
  }

  // Sort employees within each band by pct descending
  for (const band of bands) {
    band.employees.sort((a, b) => b.pct - a.pct)
  }

  return bands
})

// Employee options for individual chart selector
const utilEmployeeOptions = computed(() => {
  return filteredUtilData.value
    .filter(e => e.monthly_breakdown && e.monthly_breakdown.length > 0)
    .map(e => ({ title: e.employee_name, value: e.employee_name }))
    .sort((a, b) => a.title.localeCompare(b.title))
})

// Individual employee utilization chart
const selectedEmployeeChartData = computed(() => {
  if (!selectedUtilEmployee.value) return []
  const emp = filteredUtilData.value.find(e => e.employee_name === selectedUtilEmployee.value)
  if (!emp?.monthly_breakdown?.length) return []

  const traces = [
    {
      type: 'bar' as const,
      name: 'Actual Billable Hours',
      x: emp.monthly_breakdown.map(m => m.month),
      y: emp.monthly_breakdown.map(m => m.actual_billable_hours ?? 0),
      marker: { color: '#4CAF50' },
    },
    {
      type: 'bar' as const,
      name: 'Possible Hours',
      x: emp.monthly_breakdown.map(m => m.month),
      y: emp.monthly_breakdown.map(m => m.possible_hours ?? 0),
      marker: { color: '#E0E0E0' },
    },
  ]

  if (includeProjectedHours.value) {
    traces.push({
      type: 'bar' as const,
      name: 'Projected Hours',
      x: emp.monthly_breakdown.map(m => m.month),
      y: emp.monthly_breakdown.map(m => m.projected_hours ?? 0),
      marker: { color: '#2196F3' },
    })
  }

  return traces
})

const selectedEmployeeChartLayout = {
  height: 350,
  margin: { t: 20, r: 20, b: 60, l: 50 },
  barmode: 'group' as const,
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  legend: { orientation: 'h' as const, y: -0.3 },
}

// Planned vs Actual bar chart (all employees)
const plannedVsActualData = computed(() => {
  const data = filteredUtilData.value
  if (data.length === 0) return []

  const sorted = [...data].sort((a, b) => (b.actual_billable_hours ?? 0) - (a.actual_billable_hours ?? 0)).slice(0, 20)

  const traces = [
    {
      type: 'bar' as const,
      name: 'Actual Billable Hours',
      x: sorted.map(e => e.employee_name),
      y: sorted.map(e => e.actual_billable_hours ?? 0),
      marker: { color: '#4CAF50' },
    },
    {
      type: 'bar' as const,
      name: 'Possible Hours',
      x: sorted.map(e => e.employee_name),
      y: sorted.map(e => e.possible_hours ?? 0),
      marker: { color: '#E0E0E0' },
    },
  ]

  if (includeProjectedHours.value) {
    traces.push({
      type: 'bar' as const,
      name: 'Projected Hours',
      x: sorted.map(e => e.employee_name),
      y: sorted.map(e => e.projected_hours ?? 0),
      marker: { color: '#2196F3' },
    })
  }

  return traces
})

const plannedVsActualLayout = {
  height: 400,
  margin: { t: 20, r: 20, b: 120, l: 50 },
  barmode: 'group' as const,
  xaxis: { tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  legend: { orientation: 'h' as const, y: -0.4 },
}

// v-data-table headers for Utilization Overview
const utilHeaders = [
  { title: 'Employee', key: 'employee_name', minWidth: '160px' },
  { title: 'Possible Billable Hrs', key: 'possible_hours', minWidth: '140px', align: 'end' as const },
  { title: 'Actual Hrs', key: 'actual_hours', minWidth: '100px', align: 'end' as const },
  { title: 'Actual Billable Hrs', key: 'actual_billable_hours', minWidth: '130px', align: 'end' as const },
  { title: 'Projected Missing Hrs', key: 'projected_hours', minWidth: '140px', align: 'end' as const },
  { title: 'Effective Billable Hrs', key: 'effective_billable_hours', minWidth: '150px', align: 'end' as const },
  { title: 'PTO Hrs', key: 'pto_hours', minWidth: '90px', align: 'end' as const },
  { title: 'Holiday Hrs', key: 'holiday_hours', minWidth: '100px', align: 'end' as const },
  { title: 'Other Non-billable Hrs', key: 'other_nonbillable_hours', minWidth: '150px', align: 'end' as const },
  { title: 'Billable Utilization %', key: 'utilization_pct', minWidth: '140px', align: 'end' as const },
  { title: 'Status', key: 'status', minWidth: '100px' },
]

// Cumulative utilization chart - line per employee (top 10 by hours)
const utilChartData = computed(() => {
  if (filteredUtilData.value.length === 0) return []

  // Pick top 10 employees by actual hours for readability
  const sorted = [...filteredUtilData.value]
    .filter((e) => e.monthly_breakdown && e.monthly_breakdown.length > 0)
    .sort((a, b) => b.actual_hours - a.actual_hours)
    .slice(0, 10)

  const traces = sorted.map((emp) => ({
    type: 'scatter' as const,
    mode: 'lines+markers' as const,
    name: emp.employee_name,
    x: emp.monthly_breakdown.map((m) => m.month),
    y: emp.monthly_breakdown.map((m) => m.utilization_pct ?? 0),
  }))

  return traces
})

const utilChartLayout = computed(() => ({
  height: 400,
  margin: { t: 20, r: 20, b: 60, l: 50 },
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Utilization %' } },
  legend: { orientation: 'h' as const, y: -0.3 },
  shapes: [
    {
      type: 'line' as const,
      x0: 0, x1: 1, xref: 'paper' as const,
      y0: 80, y1: 80, yref: 'y' as const,
      line: { color: '#4CAF50', width: 2, dash: 'dash' as const },
    },
  ],
}))

function exportUtilCsv() {
  const rows = filteredUtilData.value.map((e) => ({
    Employee: e.employee_name,
    'Possible Billable Hrs': e.possible_hours,
    'Actual Hrs': e.actual_hours,
    'Actual Billable Hrs': e.actual_billable_hours,
    'Projected Missing Hrs': e.projected_hours,
    'Effective Billable Hrs': e.effective_billable_hours ?? '',
    'PTO Hrs': e.pto_hours,
    'Holiday Hrs': e.holiday_hours,
    'Other Non-billable Hrs': e.other_nonbillable_hours ?? '',
    'Billable Utilization %': e.utilization_pct ?? '',
    Status: e.status ?? '',
  }))
  downloadCsv(rows, `utilization_overview_${utilYear.value}_${utilTimeFrame.value}.csv`)

}

// Helper: allocation % color
function allocPctColor(v: number | null | undefined): string {
  if (v == null) return '#2196F3'
  if (v > 120) return '#F44336'
  if (v > 100) return '#FF9800'
  if (v >= 80) return '#4CAF50'
  return '#2196F3'
}

// Helper: allocation status chip color
function allocStatusColor(s: string): string {
  if (s === 'Over-Allocated') return 'error'
  if (s === 'Fully Allocated' || s === 'On Target') return 'success'
  if (s === 'Under-Allocated') return 'info'
  if (s === 'Warning') return 'warning'
  return 'grey'
}

// Helper: utilization % color
function utilPctColor(v: number | null | undefined): string {
  if (v == null) return '#F44336'
  if (v >= 80) return '#4CAF50'
  if (v >= 60) return '#FF9800'
  return '#F44336'
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4 font-weight-bold">Employees</h1>
      <v-btn color="primary" prepend-icon="mdi-plus">
        Add Employee
      </v-btn>
    </div>

    <!-- Error alert -->
    <v-alert v-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Tabs -->
    <v-tabs :model-value="activeTab" @update:model-value="navigateTab" class="mb-4">
      <v-tab :value="0">Employee List</v-tab>
      <v-tab :value="1">Allocation Overview</v-tab>
      <v-tab :value="2">Utilization Overview</v-tab>
    </v-tabs>

    <v-window :model-value="activeTab" class="pt-2">
      <!-- ============================================================= -->
      <!-- TAB 1: Employee List -->
      <!-- ============================================================= -->
      <v-window-item :value="0">
        <!-- Filters Row -->
        <v-row class="mb-2">
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="selectedBillableStatus"
              label="Billable Status"
              :items="['All', 'Billable', 'Non-Billable']"
              density="compact"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="selectedPayType"
              label="Pay Type"
              :items="['All', 'Hourly', 'Salary']"
              density="compact"
            />
          </v-col>
          <v-col cols="12" sm="12" md="6">
            <v-text-field
              v-model="searchTerm"
              prepend-inner-icon="mdi-magnify"
              label="Search by name..."
              clearable
              density="compact"
              @click:clear="searchTerm = ''"
            />
          </v-col>
        </v-row>

        <!-- Summary Metrics -->
        <v-row class="mb-2" v-if="!loading">
          <v-col cols="12" sm="4">
            <KpiCard
              title="Total Employees"
              :value="String(totalEmployees)"
              icon="mdi-account-group"
              color="#1976D2"
              :subtitle="`${employees.length} total in database`"
            />
          </v-col>
          <v-col cols="12" sm="4">
            <KpiCard
              title="Avg Utilization"
              :value="avgUtilization.toFixed(1) + '%'"
              icon="mdi-chart-bar"
              color="#4CAF50"
            />
          </v-col>
          <v-col cols="12" sm="4">
            <KpiCard
              title="Avg Cost Rate"
              :value="'$' + avgHourlyRate.toFixed(2)"
              icon="mdi-currency-usd"
              color="#FF9800"
            />
          </v-col>
        </v-row>

        <!-- Summary Chips -->
        <div class="d-flex ga-2 mb-4" v-if="!loading">
          <v-chip color="green" variant="flat" size="small">
            {{ billableCount }} Billable
          </v-chip>
          <v-chip color="blue" variant="flat" size="small">
            {{ salaryCount }} Salary
          </v-chip>
          <v-chip color="orange" variant="flat" size="small">
            {{ hourlyCount }} Hourly
          </v-chip>
        </div>

        <!-- Loading skeleton -->
        <v-skeleton-loader v-if="loading" type="table" class="mb-4" />

        <!-- Data Table -->
        <v-card v-else>
          <v-card-text class="pa-0">
            <div class="d-flex align-center justify-space-between pa-3 pb-0">
              <div class="text-caption text-medium-emphasis">
                Showing {{ filteredEmployees.length }} of {{ employees.length }} employees
                &mdash; Click a row to view details
              </div>
              <v-btn
                variant="outlined"
                size="small"
                prepend-icon="mdi-download"
                @click="exportListCsv"
                :disabled="loading || filteredEmployees.length === 0"
              >
                Export CSV
              </v-btn>
            </div>
            <v-data-table
              :headers="listHeaders"
              :items="filteredEmployees"
              v-model:sort-by="employeeListSortBy"
              density="compact"
              hover
              class="cursor-pointer"
              items-per-page="25"
              @click:row="(_e: Event, { item }: { item: any }) => onListRowClicked(item)"
            >
              <template #item.billable="{ value }">
                <v-chip :color="value === 1 ? 'success' : 'grey'" size="small">
                  {{ value === 1 ? 'Yes' : 'No' }}
                </v-chip>
              </template>
              <template #item.cost_rate="{ value }">
                {{ formatCurrencyLocal(value) }}
              </template>
              <template #item.fte="{ value }">
                {{ value != null ? value.toFixed(2) : '-' }}
              </template>
              <template #item.target_allocation="{ value }">
                {{ value != null ? (value * 100).toFixed(0) + '%' : '-' }}
              </template>
              <template #item.hire_date="{ value }">
                {{ value || '-' }}
              </template>
              <template #item.term_date="{ value }">
                {{ value || '-' }}
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- ============================================================= -->
      <!-- TAB 2: Allocation Overview -->
      <!-- ============================================================= -->
      <v-window-item :value="1">
        <!-- Controls -->
        <v-row class="mb-2">
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="allocYear"
              label="Year"
              :items="yearOptions"
              density="compact"
            />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="allocMonth"
              label="Month"
              :items="monthOptions"
              item-title="title"
              item-value="value"
              density="compact"
            />
          </v-col>
        </v-row>

        <!-- Allocation Filters -->
        <v-row class="mb-2">
          <v-col cols="12" md="8">
            <div class="d-flex flex-wrap ga-2">
              <v-chip
                v-for="status in allocStatusOptions"
                :key="status"
                :color="allocStatusFilter.includes(status) ? 'primary' : undefined"
                :variant="allocStatusFilter.includes(status) ? 'flat' : 'outlined'"
                size="small"
                @click="
                  allocStatusFilter.includes(status)
                    ? allocStatusFilter = allocStatusFilter.filter(s => s !== status)
                    : allocStatusFilter = [...allocStatusFilter, status]
                "
              >
                {{ status }}
              </v-chip>
              <v-chip
                v-if="allocStatusFilter.length > 0"
                color="grey"
                variant="text"
                size="small"
                @click="allocStatusFilter = []"
              >
                Clear filters
              </v-chip>
            </div>
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="allocSearchTerm"
              prepend-inner-icon="mdi-magnify"
              label="Search by name..."
              clearable
              density="compact"
              hide-details
              @click:clear="allocSearchTerm = ''"
            />
          </v-col>
        </v-row>

        <!-- KPI Cards -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Employees"
              :value="String(allocTotalEmployees)"
              icon="mdi-account-group"
              color="#1976D2"
              :loading="allocLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Over-Allocated"
              :value="String(allocOverAllocated)"
              icon="mdi-arrow-up-bold"
              color="#F44336"
              :loading="allocLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Under-Allocated"
              :value="String(allocUnderAllocated)"
              icon="mdi-arrow-down-bold"
              color="#2196F3"
              :loading="allocLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Avg Allocation %"
              :value="allocAvgPct.toFixed(1) + '%'"
              icon="mdi-percent"
              color="#4CAF50"
              :loading="allocLoading"
            />
          </v-col>
        </v-row>

        <!-- Loading skeleton -->
        <v-skeleton-loader v-if="allocLoading" type="table" class="mb-4" />

        <!-- Data Table -->
        <v-card v-else class="mb-4">
          <v-card-text class="pa-0">
            <div class="d-flex align-center justify-space-between pa-3 pb-0">
              <div class="text-caption text-medium-emphasis">
                {{ filteredAllocData.length }} of {{ allocData.length }} employees &mdash; Click a row to view project breakdown
              </div>
              <v-btn
                variant="outlined"
                size="small"
                prepend-icon="mdi-download"
                @click="exportAllocCsv"
                :disabled="filteredAllocData.length === 0"
              >
                Export CSV
              </v-btn>
            </div>
            <v-data-table
              :headers="allocHeaders"
              :items="filteredAllocData"
              density="compact"
              hover
              class="cursor-pointer"
              items-per-page="25"
              @click:row="(_e: Event, { item }: { item: any }) => onAllocRowClicked(item)"
            >
              <template #item.target_fte="{ value }">
                {{ value != null ? value.toFixed(2) : '-' }}
              </template>
              <template #item.possible_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.allocated_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.allocation_pct="{ value }">
                <span v-if="value != null" :style="{ fontWeight: 600, color: allocPctColor(value) }">
                  {{ value.toFixed(1) }}%
                </span>
                <span v-else>-</span>
              </template>
              <template #item.variance="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.status="{ value }">
                <v-chip v-if="value" :color="allocStatusColor(value)" size="small">
                  {{ value }}
                </v-chip>
                <span v-else>-</span>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>

        <!-- Bar chart: Allocation % by Employee -->
        <v-card v-if="!allocLoading && allocBarData.length > 0" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-medium">
            Allocation % by Employee
          </v-card-title>
          <v-card-text>
            <PlotlyChart :data="allocBarData" :layout="allocBarLayout" />
          </v-card-text>
        </v-card>

        <!-- Project breakdown dialog -->
        <v-dialog v-model="allocDialogOpen" max-width="700">
          <v-card v-if="allocDialogEmployee">
            <v-card-title class="text-h6">
              {{ allocDialogEmployee.employee_name }}
            </v-card-title>
            <v-card-subtitle>
              Allocation: {{ allocDialogEmployee.allocation_pct.toFixed(1) }}% &mdash; {{ allocDialogEmployee.status }}
            </v-card-subtitle>
            <v-card-text>
              <v-data-table
                :headers="breakdownHeaders"
                :items="allocDialogEmployee.project_breakdown"
                density="compact"
                class="mb-4"
              >
                <template #item.allocated_fte="{ item }">
                  {{ item.allocated_fte.toFixed(2) }}
                </template>
                <template #item.allocated_hours="{ item }">
                  {{ item.allocated_hours.toFixed(1) }}
                </template>
                <template #item.bill_rate="{ item }">
                  {{ formatCurrencyLocal(item.bill_rate) }}
                </template>
              </v-data-table>

              <div v-if="dialogPieData.length > 0" class="text-subtitle-2 font-weight-medium mb-2">
                Allocation by Project
              </div>
              <PlotlyChart
                v-if="dialogPieData.length > 0"
                :data="dialogPieData"
                :layout="dialogPieLayout"
              />
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="allocDialogOpen = false">Close</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </v-window-item>

      <!-- ============================================================= -->
      <!-- TAB 3: Utilization Overview -->
      <!-- ============================================================= -->
      <v-window-item :value="2">
        <!-- Controls -->
        <v-row class="mb-4" align="center">
          <v-col cols="2">
            <v-select v-model="utilYear" :items="yearOptions" label="Year" density="compact" variant="outlined" hide-details />
          </v-col>
          <v-col cols="2">
            <v-select v-model="utilTimeFrameType" :items="['Monthly', 'Quarterly', 'QTD', 'YTD']" label="Time Frame" density="compact" variant="outlined" hide-details />
          </v-col>
          <v-col cols="2" v-if="utilTimeFrameType === 'Monthly'">
            <v-select v-model="selectedMonth" :items="monthNames" label="Month" density="compact" variant="outlined" hide-details />
          </v-col>
          <v-col cols="2" v-if="utilTimeFrameType === 'Quarterly'">
            <v-select v-model="selectedQuarter" :items="['Q1','Q2','Q3','Q4']" label="Quarter" density="compact" variant="outlined" hide-details />
          </v-col>
          <v-col cols="2" v-if="['Quarterly','QTD','YTD'].includes(utilTimeFrameType)">
            <v-radio-group v-model="fyType" inline hide-details density="compact" label="FY Type">
              <v-radio label="Company" value="Company" />
              <v-radio label="Gov" value="Gov" />
            </v-radio-group>
          </v-col>
        </v-row>

        <!-- Utilization Filters -->
        <v-row class="mb-2">
          <v-col cols="12" md="6">
            <div class="d-flex flex-wrap ga-2 align-center">
              <span class="text-caption text-medium-emphasis mr-1">Filter by band:</span>
              <v-chip
                v-for="band in utilBandOptions"
                :key="band.label"
                :color="utilBandFilter.includes(band.label) ? 'primary' : undefined"
                :variant="utilBandFilter.includes(band.label) ? 'flat' : 'outlined'"
                size="small"
                @click="
                  utilBandFilter.includes(band.label)
                    ? utilBandFilter = utilBandFilter.filter(b => b !== band.label)
                    : utilBandFilter = [...utilBandFilter, band.label]
                "
              >
                {{ band.label }}
              </v-chip>
              <v-chip
                v-if="utilBandFilter.length > 0"
                color="grey"
                variant="text"
                size="small"
                @click="utilBandFilter = []"
              >
                Clear
              </v-chip>
            </div>
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field
              v-model="utilSearchTerm"
              prepend-inner-icon="mdi-magnify"
              label="Search by name..."
              clearable
              density="compact"
              hide-details
              @click:clear="utilSearchTerm = ''"
            />
          </v-col>
          <v-col cols="12" md="3">
            <v-checkbox
              v-model="includeProjectedHours"
              label="Include projected hours"
              density="compact"
              hide-details
            />
          </v-col>
        </v-row>

        <!-- Time Frame Definitions -->
        <v-expansion-panels v-model="showTimeFrameDefs" class="mb-4">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-subtitle-2">
              Time Frame Definitions
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-list density="compact">
                <v-list-item>
                  <strong>Current Month</strong>: The current calendar month
                </v-list-item>
                <v-list-item>
                  <strong>YTD (Company)</strong>: Jan 1 through today (company fiscal year)
                </v-list-item>
                <v-list-item>
                  <strong>YTD (Gov)</strong>: Oct 1 through today (government fiscal year)
                </v-list-item>
                <v-list-item>
                  <strong>QTD (Company)</strong>: Current company quarter to date
                </v-list-item>
                <v-list-item>
                  <strong>QTD (Gov)</strong>: Current government quarter to date
                </v-list-item>
                <v-list-item>
                  <strong>Q1-Q4</strong>: Specific quarters of the selected year
                </v-list-item>
                <v-list-item>
                  <strong>Monthly</strong>: Select a specific month of the selected year
                </v-list-item>
              </v-list>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <!-- KPI Cards - Row 1 -->
        <v-row class="mb-2">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Employees"
              :value="String(utilTotalEmployees)"
              icon="mdi-account-group"
              color="#1976D2"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Avg Utilization"
              :value="utilAvgUtilization.toFixed(1) + '%'"
              icon="mdi-chart-line"
              color="#4CAF50"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Over Target (&ge;80%)"
              :value="String(utilOverTarget)"
              icon="mdi-arrow-up-bold"
              color="#4CAF50"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Under Target (&lt;80%)"
              :value="String(utilUnderTarget)"
              icon="mdi-arrow-down-bold"
              color="#F44336"
              :loading="utilLoading"
            />
          </v-col>
        </v-row>

        <!-- KPI Cards - Row 2 -->
        <v-row class="mb-2">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Possible Hrs"
              :value="utilTotalPossibleHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-clock-outline"
              color="#1976D2"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Actual Hrs"
              :value="utilTotalActualHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-clock-check-outline"
              color="#2196F3"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Billable Hrs"
              :value="utilTotalBillableHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-currency-usd"
              color="#4CAF50"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Projected Missing Hrs"
              :value="utilTotalProjectedMissingHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-clock-alert-outline"
              color="#FF9800"
              :loading="utilLoading"
            />
          </v-col>
        </v-row>

        <!-- KPI Cards - Row 3 -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Effective Billable Hrs"
              :value="utilTotalEffectiveBillableHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-check-circle-outline"
              color="#4CAF50"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total PTO Hrs"
              :value="utilPtoHours.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-beach"
              color="#FF9800"
              :loading="utilLoading"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Holiday Hrs"
              :value="utilTotalHolidayHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
              icon="mdi-calendar-star"
              color="#9C27B0"
              :loading="utilLoading"
            />
          </v-col>
        </v-row>

        <!-- Utilization Band Summary Cards -->
        <v-row class="mb-4" v-if="!utilLoading" align="start">
          <v-col v-for="band in utilBandSummary" :key="band.label" cols="12" sm="6" md style="min-width: 0">
            <div
              :style="{
                backgroundColor: band.bgColor,
                padding: '15px',
                borderRadius: '10px',
                borderLeft: '5px solid ' + band.borderColor,
                color: '#333',
              }"
            >
              <div class="d-flex align-center mb-2">
                <span style="font-size: 24px; margin-right: 8px">{{ band.icon }}</span>
                <span style="font-size: 18px; font-weight: bold">{{ band.label }}</span>
              </div>
              <div style="font-size: 28px; font-weight: bold; margin-bottom: 5px">
                {{ band.employees.length }} Employees
              </div>
              <div style="font-size: 13px; color: #555">
                <template v-if="band.employees.length > 0">
                  <div v-for="emp in band.employees" :key="emp.name">
                    {{ emp.name }} ({{ emp.pct }}%)
                  </div>
                </template>
                <em v-else>None</em>
              </div>
            </div>
          </v-col>
        </v-row>

        <!-- Loading skeleton -->
        <v-skeleton-loader v-if="utilLoading" type="table" class="mb-4" />

        <!-- Data Table -->
        <v-card v-else class="mb-4">
          <v-card-text class="pa-0">
            <div class="d-flex align-center justify-space-between pa-3 pb-0">
              <div class="text-caption text-medium-emphasis">
                {{ filteredUtilData.length }} of {{ utilData.length }} employees
              </div>
              <v-btn
                variant="outlined"
                size="small"
                prepend-icon="mdi-download"
                @click="exportUtilCsv"
                :disabled="filteredUtilData.length === 0"
              >
                Export CSV
              </v-btn>
            </div>
            <v-data-table
              :headers="utilHeaders"
              :items="filteredUtilData"
              v-model:sort-by="utilTableSortBy"
              density="compact"
              hover
              items-per-page="25"
            >
              <template #item.possible_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.actual_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.actual_billable_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.projected_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.effective_billable_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.pto_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.holiday_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.other_nonbillable_hours="{ value }">
                {{ value != null ? value.toFixed(1) : '-' }}
              </template>
              <template #item.utilization_pct="{ value }">
                <span v-if="value != null" :style="{ fontWeight: 600, color: utilPctColor(value) }">
                  {{ value.toFixed(1) }}%
                </span>
                <span v-else>-</span>
              </template>
              <template #item.status="{ value }">
                {{ value ?? '-' }}
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>

        <!-- Cumulative Utilization Chart -->
        <v-card v-if="!utilLoading && utilChartData.length > 0" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-medium">
            Cumulative Utilization by Month (Top 10)
          </v-card-title>
          <v-card-text>
            <PlotlyChart :data="utilChartData" :layout="utilChartLayout" />
          </v-card-text>
        </v-card>

        <!-- Planned vs Actual Billable Hours -->
        <v-card v-if="!utilLoading && plannedVsActualData.length > 0" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-medium">
            Planned vs Actual Billable Hours (Top 20)
          </v-card-title>
          <v-card-text>
            <PlotlyChart :data="plannedVsActualData" :layout="plannedVsActualLayout" />
          </v-card-text>
        </v-card>

        <!-- Individual Employee Utilization -->
        <v-card v-if="!utilLoading && utilEmployeeOptions.length > 0" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-medium">
            Individual Employee Utilization
          </v-card-title>
          <v-card-text>
            <v-select
              v-model="selectedUtilEmployee"
              label="Select employee"
              :items="utilEmployeeOptions"
              item-title="title"
              item-value="value"
              clearable
              density="compact"
              class="mb-4"
              style="max-width: 400px;"
            />
            <PlotlyChart
              v-if="selectedEmployeeChartData.length > 0"
              :data="selectedEmployeeChartData"
              :layout="selectedEmployeeChartLayout"
            />
            <v-alert v-else-if="selectedUtilEmployee" type="info" variant="tonal" density="compact">
              No monthly breakdown data available for this employee.
            </v-alert>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>
  </div>
</template>
