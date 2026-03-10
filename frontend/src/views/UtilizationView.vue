<script setup lang="ts">
/**
 * Team-wide Utilization Tracking page.
 *
 * Displays KPI summary, utilization trend, distribution histogram,
 * department breakdown, hours breakdown charts, and a detail AG Grid
 * table with per-employee metrics.
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { downloadCsv } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { Employee, TimeEntry } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const router = useRouter()
const api = useApi()

// ---- Filter state ----

const now = new Date()
const filterStartDate = ref(new Date(now.getFullYear(), 0, 1).toISOString().slice(0, 10))
const filterEndDate = ref(now.toISOString().slice(0, 10))
const timePeriod = ref<'Monthly' | 'Quarterly' | 'YTD'>('Monthly')
const selectedDepartments = ref<string[]>([])
const selectedEmployees = ref<number[]>([])

// ---- Data ----

const employees = ref<Employee[]>([])
const timeEntries = ref<TimeEntry[]>([])
const loadingEmployees = ref(true)
const loadingTimeEntries = ref(true)
const errorMessage = ref<string | null>(null)

// ---- Derived filter options ----

const departmentOptions = computed(() => {
  const depts = new Set<string>()
  for (const e of employees.value) {
    if (e.department) depts.add(e.department)
  }
  return Array.from(depts).sort()
})

const employeeOptions = computed(() => {
  return employees.value
    .filter((e) => e.billable === 1)
    .map((e) => ({ title: e.name, value: e.id }))
    .sort((a, b) => a.title.localeCompare(b.title))
})

// ---- Filtered data ----

const filteredEmployees = computed(() => {
  let result = employees.value.filter((e) => e.billable === 1)

  // Exclude terminated before period start and hired after period end
  const periodStart = new Date(filterStartDate.value)
  const periodEnd = new Date(filterEndDate.value)
  result = result.filter((e) => {
    if (e.term_date) {
      const termDate = new Date(e.term_date)
      if (termDate < periodStart) return false
    }
    if (e.hire_date) {
      const hireDate = new Date(e.hire_date)
      if (hireDate > periodEnd) return false
    }
    return true
  })

  if (selectedDepartments.value.length > 0) {
    result = result.filter((e) => selectedDepartments.value.includes(e.department ?? ''))
  }
  if (selectedEmployees.value.length > 0) {
    result = result.filter((e) => selectedEmployees.value.includes(e.id))
  }
  return result
})

const filteredTimeEntries = computed(() => {
  const empIds = new Set(filteredEmployees.value.map((e) => e.id))
  return timeEntries.value.filter((te) => empIds.has(te.employee_id))
})

// ---- Per-employee aggregation ----

interface EmployeeRow {
  id: number
  name: string
  department: string
  role: string
  fte: number
  target_utilization: number
  actual_utilization: number
  total_hours: number
  billable_hours: number
  non_billable_hours: number
  billable_rate: number
}

const employeeRows = computed<EmployeeRow[]>(() => {
  // Calculate months in range for capacity
  const startD = new Date(filterStartDate.value)
  const endD = new Date(filterEndDate.value)
  const monthsDiff =
    (endD.getFullYear() - startD.getFullYear()) * 12 +
    endD.getMonth() -
    startD.getMonth() +
    1

  // Aggregate time entries per employee
  const hoursMap = new Map<number, { total: number; billable: number }>()
  for (const te of filteredTimeEntries.value) {
    const existing = hoursMap.get(te.employee_id) ?? { total: 0, billable: 0 }
    existing.total += te.hours
    if (te.billable === 1) existing.billable += te.hours
    hoursMap.set(te.employee_id, existing)
  }

  return filteredEmployees.value.map((emp) => {
    const hours = hoursMap.get(emp.id) ?? { total: 0, billable: 0 }
    const standardHours = 160 * monthsDiff * (emp.fte ?? 1)
    const utilPct = standardHours > 0 ? Math.min((hours.total / standardHours) * 100, 100) : 0
    const billableRate = hours.total > 0 ? (hours.billable / hours.total) * 100 : 0
    const target = emp.target_allocation != null ? emp.target_allocation * 100 : 80

    return {
      id: emp.id,
      name: emp.name,
      department: emp.department ?? '',
      role: emp.role ?? '',
      fte: emp.fte ?? 1,
      target_utilization: target,
      actual_utilization: Math.round(utilPct * 10) / 10,
      total_hours: Math.round(hours.total),
      billable_hours: Math.round(hours.billable),
      non_billable_hours: Math.round(hours.total - hours.billable),
      billable_rate: Math.round(billableRate * 10) / 10,
    }
  })
})

// ---- KPI computations ----

const totalEmployeesCount = computed(() => filteredEmployees.value.length)

const avgUtilization = computed(() => {
  if (employeeRows.value.length === 0) return 0
  const sum = employeeRows.value.reduce((s, r) => s + r.actual_utilization, 0)
  return sum / employeeRows.value.length
})

const totalHoursWorked = computed(() => {
  return employeeRows.value.reduce((s, r) => s + r.total_hours, 0)
})

const totalBillableHours = computed(() => {
  return employeeRows.value.reduce((s, r) => s + r.billable_hours, 0)
})

const overallBillableRate = computed(() => {
  if (totalHoursWorked.value === 0) return 0
  return (totalBillableHours.value / totalHoursWorked.value) * 100
})

const totalFteCount = computed(() => {
  return filteredEmployees.value.reduce((s, e) => s + (e.fte ?? 1), 0)
})

// ---- Helpers ----

function utilizationColor(pct: number): string {
  if (pct >= 80) return '#4CAF50'
  if (pct >= 60) return '#FB8C00'
  return '#FF5252'
}

// ---- Chart 1: Utilization Trend (line chart by month) ----

const trendChartData = computed<Plotly.Data[]>(() => {
  if (filteredTimeEntries.value.length === 0) return []

  const startD = new Date(filterStartDate.value)
  const endD = new Date(filterEndDate.value)

  // Group time entries by month
  const monthlyHours = new Map<string, number>()
  for (const te of filteredTimeEntries.value) {
    const month = te.date.slice(0, 7) // YYYY-MM
    monthlyHours.set(month, (monthlyHours.get(month) ?? 0) + te.hours)
  }

  // Generate all months in range
  const allMonths: string[] = []
  const cursor = new Date(startD.getFullYear(), startD.getMonth(), 1)
  while (cursor <= endD) {
    allMonths.push(
      `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}`
    )
    cursor.setMonth(cursor.getMonth() + 1)
  }

  const totalFte = filteredEmployees.value.reduce((s, e) => s + (e.fte ?? 1), 0)
  const monthlyCapacity = 160 * totalFte

  const utilPcts = allMonths.map((m) => {
    const hours = monthlyHours.get(m) ?? 0
    return monthlyCapacity > 0 ? Math.min((hours / monthlyCapacity) * 100, 100) : 0
  })

  const traces: Plotly.Data[] = [
    {
      x: allMonths,
      y: utilPcts,
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Avg Utilization',
      line: { color: '#1976D2', width: 2 },
      marker: { size: 6 },
    } as Plotly.Data,
    {
      x: allMonths,
      y: allMonths.map(() => 80),
      type: 'scatter',
      mode: 'lines',
      name: 'Target (80%)',
      line: { color: '#FF9800', width: 2, dash: 'dash' },
    } as Plotly.Data,
  ]

  // If department filter is active, add per-department lines
  if (selectedDepartments.value.length > 0 && selectedDepartments.value.length > 1) {
    const deptColors = ['#E91E63', '#9C27B0', '#00BCD4', '#8BC34A', '#FF5722', '#607D8B']
    selectedDepartments.value.forEach((dept, idx) => {
      const deptEmpIds = new Set(
        filteredEmployees.value.filter((e) => e.department === dept).map((e) => e.id)
      )
      const deptFte = filteredEmployees.value
        .filter((e) => e.department === dept)
        .reduce((s, e) => s + (e.fte ?? 1), 0)
      const deptCapacity = 160 * deptFte

      const deptMonthlyHours = new Map<string, number>()
      for (const te of filteredTimeEntries.value) {
        if (!deptEmpIds.has(te.employee_id)) continue
        const month = te.date.slice(0, 7)
        deptMonthlyHours.set(month, (deptMonthlyHours.get(month) ?? 0) + te.hours)
      }

      const deptPcts = allMonths.map((m) => {
        const hours = deptMonthlyHours.get(m) ?? 0
        return deptCapacity > 0 ? Math.min((hours / deptCapacity) * 100, 100) : 0
      })

      traces.push({
        x: allMonths,
        y: deptPcts,
        type: 'scatter',
        mode: 'lines',
        name: dept,
        line: { color: deptColors[idx % deptColors.length], width: 1.5 },
      } as Plotly.Data)
    })
  }

  return traces
})

const trendChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Utilization %' }, range: [0, 110] },
  hovermode: 'x unified',
  showlegend: true,
  legend: { orientation: 'h' as const, y: -0.25 },
}))

// ---- Chart 2: Utilization Distribution (histogram) ----

const distributionChartData = computed<Plotly.Data[]>(() => {
  if (employeeRows.value.length === 0) return []

  const ranges = [
    { label: '0-20%', min: 0, max: 20, color: '#FF5252' },
    { label: '20-40%', min: 20, max: 40, color: '#FF5252' },
    { label: '40-60%', min: 40, max: 60, color: '#FF5252' },
    { label: '60-80%', min: 60, max: 80, color: '#FB8C00' },
    { label: '80-100%', min: 80, max: 100, color: '#4CAF50' },
  ]

  const counts = ranges.map((r) => {
    return employeeRows.value.filter(
      (e) => e.actual_utilization >= r.min && (r.max === 100 ? e.actual_utilization <= r.max : e.actual_utilization < r.max)
    ).length
  })

  return [
    {
      x: ranges.map((r) => r.label),
      y: counts,
      type: 'bar' as const,
      marker: { color: ranges.map((r) => r.color) },
      text: counts.map(String),
      textposition: 'outside' as const,
      hoverinfo: 'x+y' as const,
    },
  ]
})

const distributionChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Utilization Range' } },
  yaxis: { title: { text: 'Employee Count' } },
  bargap: 0.15,
}))

// ---- Chart 3: Department Utilization (horizontal bar) ----

const deptChartData = computed<Plotly.Data[]>(() => {
  if (employeeRows.value.length === 0) return []

  // Group by department
  const deptMap = new Map<string, { totalUtil: number; count: number }>()
  for (const row of employeeRows.value) {
    const dept = row.department || 'Unknown'
    const existing = deptMap.get(dept) ?? { totalUtil: 0, count: 0 }
    existing.totalUtil += row.actual_utilization
    existing.count++
    deptMap.set(dept, existing)
  }

  // Build sorted entries
  const entries = Array.from(deptMap.entries())
    .map(([dept, data]) => ({
      dept,
      avgUtil: data.count > 0 ? data.totalUtil / data.count : 0,
    }))
    .sort((a, b) => a.avgUtil - b.avgUtil) // ascending for horizontal bar

  const depts = entries.map((e) => e.dept)
  const avgUtils = entries.map((e) => Math.round(e.avgUtil * 10) / 10)
  const colors = avgUtils.map((u) => utilizationColor(u))

  return [
    {
      y: depts,
      x: avgUtils,
      type: 'bar' as const,
      orientation: 'h' as const,
      marker: { color: colors },
      text: avgUtils.map((u) => `${u.toFixed(1)}%`),
      textposition: 'outside' as const,
      hoverinfo: 'y+x' as const,
    },
  ]
})

const deptChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: Math.max(300, (new Set(employeeRows.value.map((r) => r.department))).size * 40 + 80),
  xaxis: { title: { text: 'Avg Utilization %' }, range: [0, 110] },
  yaxis: { automargin: true },
  margin: { l: 150, t: 20, r: 40, b: 40 },
  shapes: [
    {
      type: 'line' as const,
      x0: 80,
      x1: 80,
      y0: 0,
      y1: 1,
      yref: 'paper' as const,
      line: { color: '#FF9800', dash: 'dash', width: 2 },
    },
  ],
}))

// ---- Chart 4: Hours Breakdown (stacked bar by month) ----

const hoursChartData = computed<Plotly.Data[]>(() => {
  if (filteredTimeEntries.value.length === 0) return []

  const startD = new Date(filterStartDate.value)
  const endD = new Date(filterEndDate.value)

  // Generate all months in range
  const allMonths: string[] = []
  const cursor = new Date(startD.getFullYear(), startD.getMonth(), 1)
  while (cursor <= endD) {
    allMonths.push(
      `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}`
    )
    cursor.setMonth(cursor.getMonth() + 1)
  }

  // Aggregate by month
  const monthlyData = new Map<string, { billable: number; nonBillable: number }>()
  for (const te of filteredTimeEntries.value) {
    const month = te.date.slice(0, 7)
    const existing = monthlyData.get(month) ?? { billable: 0, nonBillable: 0 }
    if (te.billable === 1) {
      existing.billable += te.hours
    } else {
      existing.nonBillable += te.hours
    }
    monthlyData.set(month, existing)
  }

  const billableByMonth = allMonths.map((m) => Math.round(monthlyData.get(m)?.billable ?? 0))
  const nonBillableByMonth = allMonths.map(
    (m) => Math.round(monthlyData.get(m)?.nonBillable ?? 0)
  )

  // Total capacity line
  const totalFte = filteredEmployees.value.reduce((s, e) => s + (e.fte ?? 1), 0)
  const monthlyCapacity = 160 * totalFte
  const capacityLine = allMonths.map(() => monthlyCapacity)

  return [
    {
      x: allMonths,
      y: billableByMonth,
      type: 'bar',
      name: 'Billable Hours',
      marker: { color: '#4CAF50' },
    } as Plotly.Data,
    {
      x: allMonths,
      y: nonBillableByMonth,
      type: 'bar',
      name: 'Non-billable Hours',
      marker: { color: '#FF9800' },
    } as Plotly.Data,
    {
      x: allMonths,
      y: capacityLine,
      type: 'scatter',
      mode: 'lines',
      name: 'Total Capacity',
      line: { color: '#1976D2', width: 2, dash: 'dash' },
    } as Plotly.Data,
  ]
})

const hoursChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  barmode: 'stack' as const,
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  hovermode: 'x unified' as const,
  showlegend: true,
  legend: { orientation: 'h' as const, y: -0.25 },
}))

// ---- Data Table ----

const headers = [
  { title: 'Employee Name', key: 'name' },
  { title: 'Department', key: 'department' },
  { title: 'Role', key: 'role' },
  { title: 'FTE', key: 'fte', align: 'end' as const },
  { title: 'Target Util %', key: 'target_utilization', align: 'end' as const },
  { title: 'Actual Util %', key: 'actual_utilization', align: 'end' as const },
  { title: 'Total Hours', key: 'total_hours', align: 'end' as const },
  { title: 'Billable Hours', key: 'billable_hours', align: 'end' as const },
  { title: 'Non-billable Hours', key: 'non_billable_hours', align: 'end' as const },
  { title: 'Billable Rate %', key: 'billable_rate', align: 'end' as const },
]

function billableRateColor(value: number): string {
  if (value >= 75) return '#4CAF50'
  if (value >= 50) return '#FB8C00'
  return '#FF5252'
}

function onRowClicked(item: EmployeeRow) {
  if (item?.id != null) {
    router.push(`/employees/${encodeURIComponent(item.id)}?tab=utilization`)
  }
}

function exportCsv() {
  downloadCsv(employeeRows.value as unknown as Record<string, unknown>[], 'utilization_report.csv')
}

// ---- Data fetching ----

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
    params.start_date = filterStartDate.value
    params.end_date = filterEndDate.value

    timeEntries.value = await api.get<TimeEntry[]>('/time-entries/', { params })
  } catch {
    errorMessage.value = 'Failed to load time entries.'
  } finally {
    loadingTimeEntries.value = false
  }
}

async function fetchAllData() {
  errorMessage.value = null
  await Promise.allSettled([fetchEmployees(), fetchTimeEntries()])
}

function applyFilters() {
  // Adjust date range based on time period selection
  const currentYear = now.getFullYear()
  if (timePeriod.value === 'YTD') {
    filterStartDate.value = `${currentYear}-01-01`
    filterEndDate.value = now.toISOString().slice(0, 10)
  } else if (timePeriod.value === 'Quarterly') {
    const currentQuarter = Math.floor(now.getMonth() / 3)
    const quarterStart = new Date(currentYear, currentQuarter * 3, 1)
    filterStartDate.value = quarterStart.toISOString().slice(0, 10)
    filterEndDate.value = now.toISOString().slice(0, 10)
  }
  // For 'Monthly', use whatever dates are set in the pickers
  fetchTimeEntries()
}

const isLoading = computed(() => loadingEmployees.value || loadingTimeEntries.value)

// ---- Lifecycle ----

onMounted(fetchAllData)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-2">
      <div>
        <h1 class="text-h4 font-weight-bold">Utilization</h1>
        <p class="text-body-1 text-medium-emphasis mt-1">
          Team-wide utilization tracking and analysis.
        </p>
      </div>
      <v-btn
        variant="outlined"
        prepend-icon="mdi-download"
        :disabled="isLoading || employeeRows.length === 0"
        @click="exportCsv"
      >
        Export CSV
      </v-btn>
    </div>

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

    <!-- Filter Section -->
    <v-card class="mb-4">
      <v-card-text>
        <v-row align="center">
          <v-col cols="12" sm="6" md="2">
            <v-text-field
              v-model="filterStartDate"
              label="Start Date"
              type="date"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-text-field
              v-model="filterEndDate"
              label="End Date"
              type="date"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-btn-toggle
              v-model="timePeriod"
              mandatory
              density="compact"
              color="primary"
              divided
            >
              <v-btn value="Monthly" size="small">Monthly</v-btn>
              <v-btn value="Quarterly" size="small">Quarterly</v-btn>
              <v-btn value="YTD" size="small">YTD</v-btn>
            </v-btn-toggle>
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-select
              v-model="selectedDepartments"
              label="Department"
              :items="departmentOptions"
              multiple
              chips
              closable-chips
              clearable
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-autocomplete
              v-model="selectedEmployees"
              label="Employee"
              :items="employeeOptions"
              item-title="title"
              item-value="value"
              multiple
              chips
              closable-chips
              clearable
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-btn
              color="primary"
              @click="applyFilters"
              :loading="isLoading"
              prepend-icon="mdi-filter"
              block
            >
              Apply Filters
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- KPI Summary Row -->
    <v-row class="mb-4">
      <v-col cols="6" sm="4" md="2">
        <KpiCard
          title="Total Employees"
          :value="String(totalEmployeesCount)"
          icon="mdi-account-group"
          color="#1976D2"
          :loading="isLoading"
        />
      </v-col>
      <v-col cols="6" sm="4" md="2">
        <KpiCard
          title="Avg Utilization"
          :value="avgUtilization.toFixed(1) + '%'"
          icon="mdi-gauge"
          :color="utilizationColor(avgUtilization)"
          :loading="isLoading"
        />
      </v-col>
      <v-col cols="6" sm="4" md="2">
        <KpiCard
          title="Total Hours"
          :value="totalHoursWorked.toLocaleString()"
          icon="mdi-clock-outline"
          color="#7B1FA2"
          :loading="isLoading"
        />
      </v-col>
      <v-col cols="6" sm="4" md="2">
        <KpiCard
          title="Billable Hours"
          :value="totalBillableHours.toLocaleString()"
          icon="mdi-cash-check"
          color="#4CAF50"
          :loading="isLoading"
        />
      </v-col>
      <v-col cols="6" sm="4" md="2">
        <KpiCard
          title="Billable Rate"
          :value="overallBillableRate.toFixed(1) + '%'"
          icon="mdi-percent"
          :color="overallBillableRate >= 75 ? '#4CAF50' : overallBillableRate >= 50 ? '#FB8C00' : '#FF5252'"
          :loading="isLoading"
        />
      </v-col>
      <v-col cols="6" sm="4" md="2">
        <KpiCard
          title="FTE Count"
          :value="totalFteCount.toFixed(1)"
          icon="mdi-account-multiple-check"
          color="#E65100"
          :loading="isLoading"
        />
      </v-col>
    </v-row>

    <!-- Charts Row 1: Utilization Trend + Distribution -->
    <v-row class="mb-4">
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-line" size="20" class="mr-1" />
            Utilization Trend
          </div>
          <PlotlyChart
            :data="trendChartData"
            :layout="trendChartLayout"
            :loading="isLoading"
          />
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-histogram" size="20" class="mr-1" />
            Utilization Distribution
          </div>
          <PlotlyChart
            :data="distributionChartData"
            :layout="distributionChartLayout"
            :loading="isLoading"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Charts Row 2: Department Utilization + Hours Breakdown -->
    <v-row class="mb-4">
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-office-building" size="20" class="mr-1" />
            Department Utilization
          </div>
          <PlotlyChart
            :data="deptChartData"
            :layout="deptChartLayout"
            :loading="isLoading"
          />
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-bar-stacked" size="20" class="mr-1" />
            Hours Breakdown
          </div>
          <PlotlyChart
            :data="hoursChartData"
            :layout="hoursChartLayout"
            :loading="isLoading"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Detail Table -->
    <v-card>
      <v-card-text class="pa-0">
        <div class="text-caption text-medium-emphasis pa-3 pb-0">
          Showing {{ employeeRows.length }} billable employees &mdash; Click a row to view
          employee utilization details
        </div>
        <v-skeleton-loader v-if="isLoading" type="table" />
        <v-data-table
          v-else
          :headers="headers"
          :items="employeeRows"
          :items-per-page="25"
          density="compact"
          hover
          class="cursor-pointer"
          @click:row="(_e: Event, { item }: { item: any }) => onRowClicked(item)"
        >
          <template #item.name="{ value }">
            <span class="text-primary text-decoration-underline" style="cursor: pointer;">
              {{ value }}
            </span>
          </template>

          <template #item.fte="{ value }">
            {{ value != null ? value.toFixed(2) : '-' }}
          </template>

          <template #item.target_utilization="{ value }">
            {{ value != null ? value.toFixed(1) + '%' : '-' }}
          </template>

          <template #item.actual_utilization="{ value }">
            <v-chip
              v-if="value != null"
              :color="utilizationColor(value)"
              size="small"
              label
            >
              {{ value.toFixed(1) }}%
            </v-chip>
            <span v-else>-</span>
          </template>

          <template #item.total_hours="{ value }">
            {{ value != null ? value.toLocaleString() : '-' }}
          </template>

          <template #item.billable_hours="{ value }">
            {{ value != null ? value.toLocaleString() : '-' }}
          </template>

          <template #item.non_billable_hours="{ value }">
            {{ value != null ? value.toLocaleString() : '-' }}
          </template>

          <template #item.billable_rate="{ value }">
            <span
              v-if="value != null"
              :style="{ color: billableRateColor(value), fontWeight: 600 }"
            >
              {{ value.toFixed(1) }}%
            </span>
            <span v-else>-</span>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>
  </div>
</template>
