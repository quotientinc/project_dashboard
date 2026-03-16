<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useApi } from '@/composables/useApi'
import { useEmployeesStore } from '@/stores/employees'
import { utilPctColor, downloadCsv } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { DetailedUtilizationEntry } from '@/types'

const router = useRouter()
const { get } = useApi()

// ---------------------------------------------------------------------------
// Pinia store -- persists filter/sort state across navigation
// ---------------------------------------------------------------------------
const store = useEmployeesStore()
const {
  utilYear, utilTimeFrameType, selectedMonth, selectedQuarter, fyType,
  includeProjectedHours, utilBandFilter, utilSearchTerm, utilTableSortBy,
} = storeToRefs(store)

// ---------------------------------------------------------------------------
// Local state
// ---------------------------------------------------------------------------
const utilData = ref<DetailedUtilizationEntry[]>([])
const utilLoading = ref(false)
const showTimeFrameDefs = ref<number | undefined>(undefined)
const selectedUtilEmployee = ref<string | null>(null)

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const now = new Date()

const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const currentQuarter = `Q${Math.ceil((now.getMonth() + 1) / 3)}`

const yearOptions = computed(() => {
  const y = now.getFullYear()
  return [y - 1, y, y + 1]
})

// Gov quarter mapping: Company Q1 (Jan-Mar) = Gov Q2, etc.
const govQuarterMap: Record<string, string> = { Q1: 'q2', Q2: 'q3', Q3: 'q4', Q4: 'q1' }

// ---------------------------------------------------------------------------
// Compute the API time_frame param based on filter selections
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
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

onMounted(fetchUtilizationData)
watch([utilYear, utilTimeFrame, includeProjectedHours], fetchUtilizationData)

// ---------------------------------------------------------------------------
// Utilization band filter options
// ---------------------------------------------------------------------------
const utilBandOptions = [
  { label: '\u2265111% Over', min: 111, max: Infinity },
  { label: '97-110% Good', min: 97, max: 111 },
  { label: '80-96% Fair', min: 80, max: 97 },
  { label: '51-79% Low', min: 51, max: 80 },
  { label: '\u226450% Under', min: 0, max: 51 },
]

// ---------------------------------------------------------------------------
// Filtered data
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// KPI computeds
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Utilization band summary cards
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Employee options for individual chart selector
// ---------------------------------------------------------------------------
const utilEmployeeOptions = computed(() => {
  return filteredUtilData.value
    .filter(e => e.monthly_breakdown && e.monthly_breakdown.length > 0)
    .map(e => ({ title: e.employee_name, value: e.employee_name }))
    .sort((a, b) => a.title.localeCompare(b.title))
})

// ---------------------------------------------------------------------------
// Individual employee utilization chart
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Planned vs Actual bar chart (all employees)
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// v-data-table headers for Utilization Overview
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Cumulative utilization chart - line per employee (top 10 by hours)
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Export CSV
// ---------------------------------------------------------------------------
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
</script>

<template>
  <div>
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
  </div>
</template>
