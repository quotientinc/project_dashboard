<script setup lang="ts">
/**
 * Team-wide Utilization Tracking page.
 *
 * Displays KPI summary, utilization trend, distribution histogram,
 * hours breakdown chart, and a detail table with per-employee metrics.
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { utilPctColor, utilPctBgColor, utilBandShapes, downloadCsv } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import UtilizationFilters from '@/components/UtilizationFilters.vue'
import type { DetailedUtilizationEntry, TimeEntry } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const router = useRouter()
const api = useApi()

// ---- Filter state ----

const filtersRef = ref<InstanceType<typeof UtilizationFilters> | null>(null)

const filterYear = ref(new Date().getFullYear())
const filterTimeFrameType = ref<'Monthly' | 'Quarterly' | 'QTD' | 'YTD'>('YTD')
const filterSelectedMonth = ref(getMonthName(new Date().getMonth()))
const filterSelectedQuarter = ref(`Q${Math.ceil((new Date().getMonth() + 1) / 3)}`)
const filterFyType = ref('Company')
const filterIncludeProjected = ref(true)

const selectedEmployees = ref<number[]>([])

function getMonthName(index: number): string {
  return ['January','February','March','April','May','June','July','August','September','October','November','December'][index]
}

// ---- Data ----

const utilizationData = ref<DetailedUtilizationEntry[]>([])
const timeEntries = ref<TimeEntry[]>([])
const loadingUtilization = ref(true)
const loadingTimeEntries = ref(true)
const errorMessage = ref<string | null>(null)

// ---- Derived filter options ----

const employeeOptions = computed(() => {
  return utilizationData.value
    .map((e) => ({ title: e.employee_name, value: e.employee_id }))
    .sort((a, b) => a.title.localeCompare(b.title))
})

// ---- Filtered data ----

const filteredUtilization = computed(() => {
  let result = utilizationData.value
  if (selectedEmployees.value.length > 0) {
    result = result.filter((e) => selectedEmployees.value.includes(e.employee_id))
  }
  return result
})

const filteredTimeEntries = computed(() => {
  const empIds = new Set(filteredUtilization.value.map((e) => e.employee_id))
  return timeEntries.value.filter((te) => empIds.has(te.employee_id))
})

// ---- Per-employee rows (mapped from backend data) ----

interface EmployeeRow {
  id: number
  name: string
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
  billable_rate: number
}

const employeeRows = computed<EmployeeRow[]>(() => {
  return filteredUtilization.value.map((emp) => {
    const billableRate = emp.actual_hours > 0 ? (emp.actual_billable_hours / emp.actual_hours) * 100 : 0
    return {
      id: emp.employee_id,
      name: emp.employee_name,
      role: emp.role ?? '',
      fte: emp.target_allocation ?? 1,
      utilization_pct: Math.round((emp.utilization_pct ?? 0) * 10) / 10,
      total_hours: Math.round(emp.actual_hours),
      billable_hours: Math.round(emp.actual_billable_hours),
      non_billable_hours: Math.round(emp.actual_hours - emp.actual_billable_hours),
      available_hours: Math.round(emp.possible_hours ?? 0),
      pto_hours: Math.round(emp.pto_hours ?? 0),
      status: emp.status ?? '',
      status_num: 0,
      billable_rate: Math.round(billableRate * 10) / 10,
    }
  })
})

// ---- KPI computations ----

const totalEmployeesCount = computed(() => filteredUtilization.value.length)

const avgUtilization = computed(() => {
  if (filteredUtilization.value.length === 0) return 0
  const sum = filteredUtilization.value.reduce((s, r) => s + (r.utilization_pct ?? 0), 0)
  return sum / filteredUtilization.value.length
})

const totalHoursWorked = computed(() => {
  return filteredUtilization.value.reduce((s, r) => s + r.actual_hours, 0)
})

const totalBillableHours = computed(() => {
  return filteredUtilization.value.reduce((s, r) => s + r.actual_billable_hours, 0)
})

const overallBillableRate = computed(() => {
  if (totalHoursWorked.value === 0) return 0
  return (totalBillableHours.value / totalHoursWorked.value) * 100
})

const totalFteCount = computed(() => {
  return filteredUtilization.value.reduce((s, e) => s + (e.target_allocation ?? 1), 0)
})

// ---- Chart 1: Utilization Trend (line chart by month) ----

const trendChartData = computed<Plotly.Data[]>(() => {
  if (filteredTimeEntries.value.length === 0) return []

  const dr = filtersRef.value?.dateRange
  if (!dr) return []
  const startD = new Date(dr.startDate)
  const endD = new Date(dr.endDate)

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

  const totalFte = filteredUtilization.value.reduce((s, e) => s + (e.target_allocation ?? 1), 0)
  const monthlyCapacity = 160 * totalFte

  const utilPcts = allMonths.map((m) => {
    const hours = monthlyHours.get(m) ?? 0
    return monthlyCapacity > 0 ? (hours / monthlyCapacity) * 100 : 0
  })

  return [
    {
      x: allMonths,
      y: utilPcts,
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Avg Utilization',
      line: { color: '#1976D2', width: 2 },
      marker: { size: 6 },
    } as Plotly.Data,
  ]
})

const trendChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Utilization %' }, range: [0, 120] },
  hovermode: 'x unified',
  showlegend: true,
  legend: { orientation: 'h' as const, y: -0.25 },
  shapes: utilBandShapes(120) as Plotly.Shape[],
}))

// ---- Chart 2: Utilization Distribution (histogram using 5 bands) ----

const distributionChartData = computed<Plotly.Data[]>(() => {
  if (employeeRows.value.length === 0) return []

  const bands = [
    { label: '≤50%', min: -Infinity, max: 51, color: '#DC3545' },
    { label: '51-79%', min: 51, max: 80, color: '#FD7E14' },
    { label: '80-96%', min: 80, max: 97, color: '#FFC107' },
    { label: '97-110%', min: 97, max: 111, color: '#28A745' },
    { label: '≥111%', min: 111, max: Infinity, color: '#9C27B0' },
  ]

  const counts = bands.map((b) => {
    return employeeRows.value.filter((e) => {
      const rounded = Math.round(e.utilization_pct)
      return rounded >= b.min && (b.max === Infinity ? true : rounded < b.max)
    }).length
  })

  return [
    {
      x: bands.map((b) => b.label),
      y: counts,
      type: 'bar' as const,
      marker: { color: bands.map((b) => b.color) },
      text: counts.map(String),
      textposition: 'outside' as const,
      hoverinfo: 'x+y' as const,
    },
  ]
})

const distributionChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Utilization Band' } },
  yaxis: { title: { text: 'Employee Count' } },
  bargap: 0.15,
}))

// ---- Chart 3: Hours Breakdown (stacked bar by month) ----

const hoursChartData = computed<Plotly.Data[]>(() => {
  if (filteredTimeEntries.value.length === 0) return []

  const dr = filtersRef.value?.dateRange
  if (!dr) return []
  const startD = new Date(dr.startDate)
  const endD = new Date(dr.endDate)

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
  const totalFte = filteredUtilization.value.reduce((s, e) => s + (e.target_allocation ?? 1), 0)
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
  { title: 'Status', key: 'status', width: '70px' },
  { title: 'Employee Name', key: 'name' },
  { title: 'Role', key: 'role' },
  { title: 'FTE', key: 'fte', align: 'end' as const },
  { title: 'Utilization %', key: 'utilization_pct', align: 'end' as const },
  { title: 'Total Hours', key: 'total_hours', align: 'end' as const },
  { title: 'Billable Hours', key: 'billable_hours', align: 'end' as const },
  { title: 'Non-billable Hours', key: 'non_billable_hours', align: 'end' as const },
  { title: 'Available Hours', key: 'available_hours', align: 'end' as const },
  { title: 'PTO Hours', key: 'pto_hours', align: 'end' as const },
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

async function fetchUtilization() {
  loadingUtilization.value = true
  try {
    utilizationData.value = await api.get<DetailedUtilizationEntry[]>(
      '/analytics/utilization/detailed',
      {
        params: {
          year: filterYear.value,
          time_frame: filtersRef.value?.timeFrame ?? 'ytd_company',
          include_projected: filterIncludeProjected.value,
        },
      }
    )
  } catch {
    errorMessage.value = 'Failed to load utilization data.'
  } finally {
    loadingUtilization.value = false
  }
}

async function fetchTimeEntries() {
  loadingTimeEntries.value = true
  try {
    const dr = filtersRef.value?.dateRange
    timeEntries.value = await api.get<TimeEntry[]>('/time-entries/', {
      params: {
        start_date: dr?.startDate ?? '',
        end_date: dr?.endDate ?? '',
      },
    })
  } catch {
    errorMessage.value = 'Failed to load time entries.'
  } finally {
    loadingTimeEntries.value = false
  }
}

async function fetchAllData() {
  errorMessage.value = null
  await Promise.allSettled([fetchUtilization(), fetchTimeEntries()])
}

const isLoading = computed(() => loadingUtilization.value || loadingTimeEntries.value)

// ---- Re-fetch when filter state changes ----

watch(
  [filterYear, filterTimeFrameType, filterSelectedMonth, filterSelectedQuarter, filterFyType, filterIncludeProjected],
  () => fetchAllData(),
  { flush: 'post' },
)

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
        <UtilizationFilters
          ref="filtersRef"
          v-model:year="filterYear"
          v-model:time-frame-type="filterTimeFrameType"
          v-model:selected-month="filterSelectedMonth"
          v-model:selected-quarter="filterSelectedQuarter"
          v-model:fy-type="filterFyType"
          v-model:include-projected-hours="filterIncludeProjected"
        />
        <v-row align="center" class="mt-2">
          <v-col cols="12" sm="6" md="4">
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
          :color="utilPctColor(avgUtilization)"
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

    <!-- Charts Row 2: Hours Breakdown -->
    <v-row class="mb-4">
      <v-col cols="12">
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
          <template #item.status="{ value }">
            <span :title="value">{{ value }}</span>
          </template>

          <template #item.name="{ value }">
            <span class="text-primary text-decoration-underline" style="cursor: pointer;">
              {{ value }}
            </span>
          </template>

          <template #item.fte="{ value }">
            {{ value != null ? value.toFixed(2) : '-' }}
          </template>

          <template #item.utilization_pct="{ value }">
            <span
              v-if="value != null"
              :style="{ fontWeight: 600, color: utilPctColor(value), background: utilPctBgColor(value), padding: '2px 8px', borderRadius: '4px', display: 'inline-block' }"
            >
              {{ value.toFixed(1) }}%
            </span>
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

          <template #item.available_hours="{ value }">
            {{ value != null ? value.toLocaleString() : '-' }}
          </template>

          <template #item.pto_hours="{ value }">
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
