<script setup lang="ts">
/**
 * Overview Dashboard page.
 *
 * Displays KPI cards, project status distribution, employee billable utilization,
 * monthly burn rate, utilization trends, and recent time entries.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import { utilPctColor, utilBandShapes } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type {
  OverviewKPIs,
  Project,
  Employee,
  TimeEntry,
  ProjectUtilizationEntry,
  MonthlyUtilizationTrendEntry,
  EmployeeBillableUtilizationEntry,
  MonthlyBurnRateEntry,
} from '@/types'
import type Plotly from 'plotly.js-dist-min'

// ---- Time Range Selector ----

type TimeRangeOption = 'Last 30 Days' | 'Last Quarter' | 'YTD' | 'This Year' | 'All Time'

const timeRange = ref<TimeRangeOption>('YTD')
const timeRangeOptions: TimeRangeOption[] = [
  'Last 30 Days',
  'Last Quarter',
  'YTD',
  'This Year',
  'All Time',
]

const timeRangeDates = computed<{ startDate: string | null; endDate: string | null }>(() => {
  const today = new Date()
  const yyyy = today.getFullYear()
  const pad = (n: number) => String(n).padStart(2, '0')
  const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  const todayStr = fmt(today)

  switch (timeRange.value) {
    case 'Last 30 Days': {
      const start = new Date(today)
      start.setDate(start.getDate() - 30)
      return { startDate: fmt(start), endDate: todayStr }
    }
    case 'Last Quarter': {
      // Previous quarter: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
      const currentQuarter = Math.floor(today.getMonth() / 3)
      let qYear = yyyy
      let prevQuarter = currentQuarter - 1
      if (prevQuarter < 0) {
        prevQuarter = 3
        qYear = yyyy - 1
      }
      const qStartMonth = prevQuarter * 3 // 0-indexed
      const qEndMonth = qStartMonth + 2
      const lastDay = new Date(qYear, qEndMonth + 1, 0).getDate()
      return {
        startDate: `${qYear}-${pad(qStartMonth + 1)}-01`,
        endDate: `${qYear}-${pad(qEndMonth + 1)}-${pad(lastDay)}`,
      }
    }
    case 'YTD':
      return { startDate: `${yyyy}-01-01`, endDate: todayStr }
    case 'This Year':
      return { startDate: `${yyyy}-01-01`, endDate: `${yyyy}-12-31` }
    case 'All Time':
      return { startDate: null, endDate: null }
    default:
      return { startDate: null, endDate: null }
  }
})

// ---- State ----

const api = useApi()

const kpis = ref<OverviewKPIs | null>(null)
const projects = ref<Project[]>([])
const employees = ref<Employee[]>([])
const timeEntries = ref<TimeEntry[]>([])
const projectUtilization = ref<ProjectUtilizationEntry[]>([])
const utilizationTrend = ref<MonthlyUtilizationTrendEntry[]>([])
const employeeUtilization = ref<EmployeeBillableUtilizationEntry[]>([])
const burnRateData = ref<MonthlyBurnRateEntry[]>([])

const loadingKpis = ref(true)
const loadingProjects = ref(true)
const loadingEmployees = ref(true)
const loadingTimeEntries = ref(true)
const loadingProjectUtil = ref(true)
const loadingUtilTrend = ref(true)
const loadingEmpUtil = ref(true)
const loadingBurnRate = ref(true)
const errorMessage = ref<string | null>(null)

// ---- Formatting helpers ----

function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`
  }
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function formatCurrencyFull(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`
}


// ---- KPI computed values ----

const burnRate = computed(() => {
  if (!kpis.value) return 0
  const quoted = kpis.value.total_quoted_value
  const used = kpis.value.total_budget_used
  return quoted > 0 ? (used / quoted) * 100 : 0
})

const budgetRemaining = computed(() => {
  if (!kpis.value) return 0
  return kpis.value.total_quoted_value - kpis.value.total_budget_used
})

// ---- Chart data (computed from fetched data) ----

// Project Status Distribution (donut chart) - filtered to billable projects only
const statusChartData = computed<Plotly.Data[]>(() => {
  const billableProjects = projects.value.filter(p => p.billable === 1)
  if (billableProjects.length === 0) return []

  const counts: Record<string, number> = {}
  for (const p of billableProjects) {
    const status = p.status || 'Unknown'
    counts[status] = (counts[status] || 0) + 1
  }

  const labels = Object.keys(counts)
  const values = Object.values(counts)

  const colorMap: Record<string, string> = {
    Active: '#4CAF50',
    Completed: '#1976D2',
    'On Hold': '#FB8C00',
    Cancelled: '#FF5252',
    Proposed: '#9C27B0',
  }
  const colors = labels.map((l) => colorMap[l] || '#757575')

  return [
    {
      type: 'pie' as const,
      labels,
      values,
      hole: 0.45,
      marker: { colors },
      textinfo: 'label+value' as const,
      hoverinfo: 'label+value+percent' as const,
    },
  ]
})

const statusChartLayout = computed<Partial<Plotly.Layout>>(() => {
  const billableProjects = projects.value.filter(p => p.billable === 1)
  const active = billableProjects.filter((p) => p.status === 'Active').length
  const total = billableProjects.length
  return {
    height: 350,
    showlegend: true,
    legend: { orientation: 'h' as const, y: -0.1 },
    annotations: [
      {
        text: `${active} Active<br>of ${total}`,
        x: 0.5,
        y: 0.5,
        font: { size: 14 },
        showarrow: false,
      },
    ],
  }
})

// Employee Billable Utilization (bar chart)
const utilizationChartData = computed<Plotly.Data[]>(() => {
  if (employeeUtilization.value.length === 0) return []

  const sorted = [...employeeUtilization.value]

  const names = sorted.map((e) => e.name)
  const pcts = sorted.map((e) => e.utilization_pct ?? 0)
  const colors = pcts.map((p) => utilPctColor(p))

  return [
    {
      type: 'bar' as const,
      x: names,
      y: pcts,
      marker: { color: colors },
      text: pcts.map((p) => `${(p ?? 0).toFixed(1)}%`),
      textposition: 'outside' as const,
      hoverinfo: 'x+y' as const,
    },
  ]
})

const utilizationChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  yaxis: { title: { text: 'Billable Utilization %' }, range: [0, 150] },
  xaxis: { tickangle: -45 },
  shapes: utilBandShapes(150) as unknown as Plotly.Shape[],
}))

// Monthly Burn Rate (stacked area + total line)
const burnRateChartData = computed<Plotly.Data[]>(() => {
  if (burnRateData.value.length === 0) return []

  const months = burnRateData.value.map((d) => d.month)
  const laborCosts = burnRateData.value.map((d) => d.labor_cost)
  const expenseCosts = burnRateData.value.map((d) => d.expense_cost)
  const totalBurn = burnRateData.value.map((d) => d.total_burn)

  return [
    {
      type: 'scatter' as const,
      x: months,
      y: laborCosts,
      mode: 'lines' as const,
      name: 'Labor Cost',
      line: { width: 0.5, color: '#1f77b4' },
      stackgroup: 'one',
      fillcolor: 'rgba(31, 119, 180, 0.5)',
    },
    {
      type: 'scatter' as const,
      x: months,
      y: expenseCosts,
      mode: 'lines' as const,
      name: 'Expenses',
      line: { width: 0.5, color: '#ff7f0e' },
      stackgroup: 'one',
      fillcolor: 'rgba(255, 127, 14, 0.5)',
    },
    {
      type: 'scatter' as const,
      x: months,
      y: totalBurn,
      mode: 'lines+markers' as const,
      name: 'Total Burn',
      line: { color: '#FF5252', width: 2 },
      marker: { size: 6 },
    },
  ]
})

const burnRateChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Amount ($)' } },
  hovermode: 'x unified' as const,
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.12 },
}))

// ---- Monthly Utilization Trend (actual vs projected) ----

const monthlyUtilTrendData = computed<Plotly.Data[]>(() => {
  if (utilizationTrend.value.length === 0) return []

  const actual = utilizationTrend.value.filter((d) => d.data_type === 'Actual')
  const projected = utilizationTrend.value.filter((d) => d.data_type === 'Projected')

  const traces: Plotly.Data[] = []

  if (actual.length > 0) {
    traces.push({
      type: 'scatter' as const,
      x: actual.map((d) => d.month_name),
      y: actual.map((d) => d.avg_utilization),
      mode: 'lines+markers' as const,
      name: 'Actual',
      line: { color: '#1f77b4', width: 3 },
      marker: { size: 8 },
    })
  }

  if (projected.length > 0) {
    traces.push({
      type: 'scatter' as const,
      x: projected.map((d) => d.month_name),
      y: projected.map((d) => d.avg_utilization),
      mode: 'lines+markers' as const,
      name: 'Projected',
      line: { color: '#ff7f0e', width: 3, dash: 'dash' },
      marker: { size: 8, symbol: 'diamond' },
    })
  }

  return traces
})

const monthlyUtilTrendLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Average Utilization %' }, range: [0, 120] },
  hovermode: 'x unified' as const,
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.12 },
  shapes: utilBandShapes(120) as unknown as Plotly.Shape[],
}))

// ---- Under-Utilized Projects ----

const underUtilizedProjects = computed<ProjectUtilizationEntry[]>(() => {
  return projectUtilization.value
    .filter((p) => p.utilization_pct !== null && p.utilization_pct < 70 && p.allocated_hours > 0)
    .sort((a, b) => (b.revenue_gap ?? 0) - (a.revenue_gap ?? 0))
})

const totalRevenueGap = computed(() =>
  underUtilizedProjects.value.reduce((sum, p) => sum + p.revenue_gap, 0)
)

const underUtilizedHeaders = [
  { title: 'Project Name', key: 'project_name' },
  { title: 'Utilization %', key: 'utilization_pct', align: 'end' as const, width: '130px' },
  { title: 'Revenue Gap', key: 'revenue_gap', align: 'end' as const, width: '140px' },
]


// ---- Recent activity ----

const recentEntries = computed(() => {
  if (timeEntries.value.length === 0) return []
  return [...timeEntries.value]
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 10)
})

const recentHeaders = [
  { title: 'Date', key: 'date', width: '110px' },
  { title: 'Employee', key: 'employee_name' },
  { title: 'Project', key: 'project_name' },
  { title: 'Hours', key: 'hours', align: 'end' as const, width: '80px' },
  { title: 'Billable', key: 'billable', width: '110px' },
  { title: 'Description', key: 'description' },
]

// ---- Data loading ----

async function fetchAllData() {
  errorMessage.value = null

  // Batch 1: lightweight endpoints that return quickly
  await Promise.allSettled([
    fetchProjects(),
    fetchEmployees(),
    fetchTimeEntries(),
    fetchBurnRate(),
  ])

  // Batch 2: heavy analytics endpoints that call get_performance_metrics
  // (these are slow and queue on a single-worker server)
  await Promise.allSettled([
    fetchKpis(),
    fetchProjectUtilization(),
    fetchUtilizationTrend(),
    fetchEmployeeUtilization(),
  ])
}

async function fetchKpis() {
  loadingKpis.value = true
  try {
    const params: Record<string, string> = {}
    const { startDate, endDate } = timeRangeDates.value
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    kpis.value = await api.get<OverviewKPIs>('/analytics/overview', { params })
  } catch {
    errorMessage.value = 'Failed to load KPI data.'
  } finally {
    loadingKpis.value = false
  }
}

async function fetchProjects() {
  loadingProjects.value = true
  try {
    projects.value = await api.get<Project[]>('/projects/')
  } catch {
    errorMessage.value = 'Failed to load projects.'
  } finally {
    loadingProjects.value = false
  }
}

async function fetchEmployees() {
  loadingEmployees.value = true
  try {
    employees.value = await api.get<Employee[]>('/employees/')
  } catch {
    errorMessage.value = 'Failed to load employees.'
  } finally {
    loadingEmployees.value = false
  }
}

async function fetchTimeEntries() {
  loadingTimeEntries.value = true
  try {
    const params: Record<string, string> = {}
    const { startDate, endDate } = timeRangeDates.value
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate

    timeEntries.value = await api.get<TimeEntry[]>('/time-entries/', { params })
  } catch {
    errorMessage.value = 'Failed to load time entries.'
  } finally {
    loadingTimeEntries.value = false
  }
}

async function fetchProjectUtilization() {
  loadingProjectUtil.value = true
  try {
    const params: Record<string, string> = {}
    const { startDate, endDate } = timeRangeDates.value
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    projectUtilization.value = await api.get<ProjectUtilizationEntry[]>(
      '/analytics/project-utilization',
      { params }
    )
  } catch {
    errorMessage.value = 'Failed to load project utilization data.'
  } finally {
    loadingProjectUtil.value = false
  }
}

async function fetchUtilizationTrend() {
  loadingUtilTrend.value = true
  try {
    const year = new Date().getFullYear()
    utilizationTrend.value = await api.get<MonthlyUtilizationTrendEntry[]>(
      '/analytics/overview/utilization-trend',
      { params: { year: String(year) } }
    )
  } catch {
    errorMessage.value = 'Failed to load utilization trend data.'
  } finally {
    loadingUtilTrend.value = false
  }
}

async function fetchEmployeeUtilization() {
  loadingEmpUtil.value = true
  try {
    const year = new Date().getFullYear()
    employeeUtilization.value = await api.get<EmployeeBillableUtilizationEntry[]>(
      '/analytics/overview/employee-utilization',
      { params: { year: String(year) } }
    )
  } catch {
    errorMessage.value = 'Failed to load employee utilization data.'
  } finally {
    loadingEmpUtil.value = false
  }
}

async function fetchBurnRate() {
  loadingBurnRate.value = true
  try {
    const params: Record<string, string> = { billable_only: 'true' }
    const { startDate, endDate } = timeRangeDates.value
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    burnRateData.value = await api.get<MonthlyBurnRateEntry[]>(
      '/analytics/overview/burn-rate',
      { params }
    )
  } catch {
    errorMessage.value = 'Failed to load burn rate data.'
  } finally {
    loadingBurnRate.value = false
  }
}

// ---- Lifecycle ----

onMounted(() => {
  fetchAllData()
})

// Re-fetch date-sensitive data when time range changes
watch(timeRange, () => {
  fetchKpis()
  fetchTimeEntries()
  fetchProjectUtilization()
  fetchUtilizationTrend()
  fetchEmployeeUtilization()
  fetchBurnRate()
})
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between flex-wrap mb-2">
      <h1 class="text-h4 font-weight-bold">Overview Dashboard</h1>
      <v-select
        v-model="timeRange"
        :items="timeRangeOptions"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width: 200px; min-width: 160px"
        prepend-inner-icon="mdi-calendar-range"
      />
    </div>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Key performance indicators, utilization trends, and recent activity.
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

    <!-- KPI Cards (4 columns) -->
    <v-row>
      <v-col cols="12" sm="6" md="4" lg="3">
        <KpiCard
          title="Avg Utilization"
          :value="kpis ? formatPercent(kpis.avg_utilization) : '--'"
          icon="mdi-chart-arc"
          :color="kpis && kpis.avg_utilization > 0 ? utilPctColor(kpis.avg_utilization) : '#1976D2'"
          :loading="loadingKpis"
        />
      </v-col>
      <v-col cols="12" sm="6" md="4" lg="3">
        <KpiCard
          title="Total Quoted Value"
          :value="kpis ? formatCurrency(kpis.total_quoted_value) : '--'"
          :subtitle="kpis ? formatCurrencyFull(kpis.total_quoted_value) : undefined"
          icon="mdi-currency-usd"
          color="#2E7D32"
          :loading="loadingKpis"
        />
      </v-col>
      <v-col cols="12" sm="6" md="4" lg="3">
        <KpiCard
          title="Total Accrued"
          :value="kpis ? formatCurrency(kpis.total_budget_used) : '--'"
          :subtitle="kpis ? formatCurrencyFull(kpis.total_budget_used) : undefined"
          icon="mdi-cash-check"
          color="#E65100"
          :loading="loadingKpis"
        />
      </v-col>
      <v-col cols="12" sm="6" md="4" lg="3">
        <KpiCard
          title="Budget Burn Rate"
          :value="kpis ? formatPercent(burnRate) : '--'"
          :subtitle="kpis ? `${formatCurrencyFull(budgetRemaining)} remaining` : undefined"
          icon="mdi-fire"
          :color="burnRate > 90 ? '#FF5252' : burnRate > 70 ? '#FB8C00' : '#4CAF50'"
          :loading="loadingKpis"
        />
      </v-col>
    </v-row>

    <!-- Under-Utilized Projects Alert -->
    <v-row v-if="!loadingProjectUtil && underUtilizedProjects.length > 0" class="mt-4">
      <v-col cols="12">
        <v-card class="pa-4 under-construction-wrapper">
          <!-- Under-construction watermark overlay -->
          <div class="under-construction-overlay" aria-hidden="true">
            <div class="under-construction-text">🚧 UNDER CONSTRUCTION 🚧</div>
          </div>
          <div class="text-h6 mb-3 d-flex align-center">
            <v-icon icon="mdi-alert-circle-outline" size="20" class="mr-1" />
            Under-Utilized Projects
            <v-menu location="bottom" :close-on-content-click="false" max-width="500">
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  icon="mdi-information-outline"
                  size="x-small"
                  variant="text"
                  class="ml-2 text-medium-emphasis"
                />
              </template>
              <v-card class="pa-4">
                <v-card-title class="text-subtitle-1 font-weight-bold pa-0 mb-2">
                  What does this mean?
                </v-card-title>
                <v-card-text class="pa-0 text-body-2">
                  <p class="mb-2">
                    <strong>Under-utilized projects</strong> have allocated staff capacity
                    (FTE allocations with bill rates) but aren't billing enough hours
                    against that capacity. This represents potential revenue that could be
                    captured.
                  </p>
                  <p class="mb-1"><strong>How it's calculated:</strong></p>
                  <p class="mb-2">
                    <strong>Utilization %</strong> = (Actual Billable Hours / Allocated Hours) &times; 100
                  </p>
                  <ul class="mb-2" style="padding-left: 20px">
                    <li>
                      <strong>Allocated Hours</strong>: From FTE allocations &mdash;
                      <code>allocated_fte &times; working_days &times; 8 hrs/day</code>
                      summed across all team members. For the current (partial) month,
                      allocated hours are prorated to elapsed working days.
                    </li>
                    <li>
                      <strong>Actual Billable Hours</strong>: From time entries marked as billable
                    </li>
                    <li>
                      <strong>Revenue Gap</strong>: Dollar value of unused capacity &mdash;
                      <code>(Allocated Hours - Actual Billable Hours) &times; avg bill rate</code>.
                      The avg bill rate is the blended rate across all team members on the
                      project, weighted by their allocated hours.
                    </li>
                  </ul>
                  <p class="mb-1"><strong>Color Key:</strong></p>
                  <ul style="padding-left: 20px">
                    <li><span style="color: #4CAF50">&#9679;</span> Green (&ge;90%): Well utilized</li>
                    <li><span style="color: #FB8C00">&#9679;</span> Yellow (70-89%): Minor risk</li>
                    <li><span style="color: #FF9800">&#9679;</span> Orange (50-69%): Medium risk</li>
                    <li><span style="color: #FF5252">&#9679;</span> Red (&lt;50%): Severely under-utilized</li>
                  </ul>
                  <p class="mt-2 text-caption font-italic">Based on YTD (Year-to-Date) data.</p>
                </v-card-text>
              </v-card>
            </v-menu>
          </div>
          <v-alert type="warning" variant="tonal" class="mb-4">
            <strong>{{ underUtilizedProjects.length }}</strong>
            project{{ underUtilizedProjects.length === 1 ? '' : 's' }}
            {{ underUtilizedProjects.length === 1 ? 'is' : 'are' }}
            under-utilized (below 70% of allocated capacity).
            Total estimated revenue gap:
            <strong>{{ formatCurrencyFull(totalRevenueGap) }}</strong>
          </v-alert>
          <v-data-table
            :headers="underUtilizedHeaders"
            :items="underUtilizedProjects"
            density="compact"
            :items-per-page="-1"
            hide-default-footer
            class="elevation-0"
          >
            <template #item.utilization_pct="{ item }">
              <v-chip
                :color="(item.utilization_pct ?? 0) >= 90 ? 'success' : (item.utilization_pct ?? 0) >= 70 ? 'warning' : (item.utilization_pct ?? 0) >= 50 ? 'orange' : 'error'"
                size="small"
                variant="tonal"
              >
                {{ (item.utilization_pct ?? 0).toFixed(1) }}%
              </v-chip>
            </template>
            <template #item.revenue_gap="{ item }">
              {{ formatCurrencyFull(item.revenue_gap) }}
            </template>
          </v-data-table>
        </v-card>
      </v-col>
    </v-row>

    <!-- Monthly Utilization Trend -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-line" size="20" class="mr-1" />
            Monthly Utilization Trend (Actual &amp; Projected)
          </div>
          <PlotlyChart
            :data="monthlyUtilTrendData"
            :layout="monthlyUtilTrendLayout"
            :loading="loadingUtilTrend"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Charts Row 1: Status Distribution + Employee Utilization -->
    <v-row class="mt-4">
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-pie" size="20" class="mr-1" />
            Project Status Distribution
          </div>
          <PlotlyChart
            :data="statusChartData"
            :layout="statusChartLayout"
            :loading="loadingProjects"
          />
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-account-clock" size="20" class="mr-1" />
            Employee Billable Utilization (Individual)
          </div>
          <PlotlyChart
            :data="utilizationChartData"
            :layout="utilizationChartLayout"
            :loading="loadingEmpUtil"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Charts Row 2: Burn Rate -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-cash-fast" size="20" class="mr-1" />
            Monthly Burn Rate (Labor + Expenses)
          </div>
          <PlotlyChart
            :data="burnRateChartData"
            :layout="burnRateChartLayout"
            :loading="loadingBurnRate"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Recent Activity -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card class="pa-4">
          <div class="text-h6 mb-3">
            <v-icon icon="mdi-clock-outline" size="20" class="mr-1" />
            Recent Activity
          </div>
          <v-skeleton-loader
            v-if="loadingTimeEntries"
            type="table-heading, table-row@5"
          />
          <v-data-table
            v-else-if="recentEntries.length > 0"
            :headers="recentHeaders"
            :items="recentEntries"
            density="compact"
            :items-per-page="-1"
            hide-default-footer
            class="elevation-0"
          >
            <template #item.hours="{ item }">
              {{ (item.hours ?? 0).toFixed(1) }}
            </template>
            <template #item.billable="{ item }">
              <v-chip
                :color="item.billable === 1 ? 'success' : 'default'"
                size="small"
                variant="tonal"
              >
                {{ item.billable === 1 ? 'Billable' : 'Non-billable' }}
              </v-chip>
            </template>
            <template #item.description="{ item }">
              <span class="text-truncate d-inline-block" style="max-width: 300px">
                {{ item.description || '--' }}
              </span>
            </template>
          </v-data-table>
          <div
            v-else
            class="text-center text-medium-emphasis pa-6"
          >
            No recent time entries
          </div>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<style scoped>
.under-construction-wrapper {
  position: relative;
  overflow: hidden;
}

.under-construction-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-surface), 0.55);
  pointer-events: none;
  z-index: 10;
}

.under-construction-text {
  transform: rotate(-25deg);
  font-size: 2.5rem;
  font-weight: 800;
  color: rgba(var(--v-theme-on-surface), 0.25);
  white-space: nowrap;
  text-shadow: none;
  letter-spacing: 2px;
}
</style>
