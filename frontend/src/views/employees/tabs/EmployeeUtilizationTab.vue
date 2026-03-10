<script setup lang="ts">
import { ref, computed, inject, onMounted, watch, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { Employee, DetailedUtilizationEntry, EmployeeMonthUtilization } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const route = useRoute()
const { get, error } = useApi()

const employee = inject<Ref<Employee | null>>('employee', ref(null))
const employeeId = computed(() => Number(route.params.id))

// ---- Time Frame Selectors ----

const currentYear = new Date().getFullYear()
const yearOptions = [currentYear - 1, currentYear, currentYear + 1]
const selectedYear = ref(currentYear)

const timeFrameOptions = [
  { title: 'Current Month', value: 'current_month' },
  { title: 'QTD (Company)', value: 'qtd_company' },
  { title: 'QTD (Gov)', value: 'qtd_gov' },
  { title: 'YTD (Company)', value: 'ytd_company' },
  { title: 'YTD (Gov)', value: 'ytd_gov' },
  { title: 'Q1', value: 'q1' },
  { title: 'Q2', value: 'q2' },
  { title: 'Q3', value: 'q3' },
  { title: 'Q4', value: 'q4' },
  { title: 'January', value: 'january' },
  { title: 'February', value: 'february' },
  { title: 'March', value: 'march' },
  { title: 'April', value: 'april' },
  { title: 'May', value: 'may' },
  { title: 'June', value: 'june' },
  { title: 'July', value: 'july' },
  { title: 'August', value: 'august' },
  { title: 'September', value: 'september' },
  { title: 'October', value: 'october' },
  { title: 'November', value: 'november' },
  { title: 'December', value: 'december' },
]
const selectedTimeFrame = ref('ytd_company')

// ---- Data ----

const utilizationEntry = ref<DetailedUtilizationEntry | null>(null)
const dataLoading = ref(true)

async function fetchData() {
  dataLoading.value = true
  utilizationEntry.value = null
  try {
    const result = await get<DetailedUtilizationEntry[]>(
      `/analytics/utilization/detailed?year=${selectedYear.value}&time_frame=${selectedTimeFrame.value}&employee_id=${employeeId.value}`
    )
    utilizationEntry.value = result.length > 0 ? result[0] ?? null : null
  } catch {
    // error handled by useApi
  } finally {
    dataLoading.value = false
  }
}

onMounted(fetchData)
watch([employeeId, selectedYear, selectedTimeFrame], fetchData)

// ---- KPI Computations ----

const utilizationPct = computed(() => utilizationEntry.value?.utilization_pct ?? 0)
const actualHours = computed(() => utilizationEntry.value?.actual_hours ?? 0)
const billableHours = computed(() => utilizationEntry.value?.actual_billable_hours ?? 0)
const ptoHours = computed(() => utilizationEntry.value?.pto_hours ?? 0)
const holidayHours = computed(() => utilizationEntry.value?.holiday_hours ?? 0)

const utilizationColor = computed(() => {
  const pct = utilizationPct.value
  if (pct >= 80) return '#4CAF50'
  if (pct >= 60) return '#FF9800'
  return '#FF5252'
})

const targetAllocationLabel = computed(() => {
  const target = employee.value?.target_allocation
  if (target != null && target > 0) {
    return `Target: ${(target * 100).toFixed(0)}%`
  }
  return undefined
})

// ---- Monthly Breakdown Table ----

const monthlyBreakdown = computed<EmployeeMonthUtilization[]>(() => {
  return utilizationEntry.value?.monthly_breakdown ?? []
})

const tableHeaders = [
  { title: 'Month', key: 'month', sortable: true },
  { title: 'Possible Hours', key: 'possible_hours', sortable: true },
  { title: 'Actual Hours', key: 'actual_hours', sortable: true },
  { title: 'Billable Hours', key: 'actual_billable_hours', sortable: true },
  { title: 'Projected Hours', key: 'projected_hours', sortable: true },
  { title: 'PTO Hours', key: 'pto_hours', sortable: true },
  { title: 'Holiday Hours', key: 'holiday_hours', sortable: true },
  { title: 'Utilization %', key: 'utilization_pct', sortable: true },
]

function utilizationChipColor(pct: number | null): string {
  if (pct == null) return 'grey'
  if (pct >= 80) return 'success'
  if (pct >= 60) return 'warning'
  return 'error'
}

// ---- Cumulative Utilization Chart ----

const utilizationChartData = computed<Plotly.Data[]>(() => {
  const breakdown = monthlyBreakdown.value
  if (breakdown.length === 0) return []

  const months = breakdown.map((m) => m.month)
  const utilPcts = breakdown.map((m) => m.utilization_pct ?? 0)

  return [
    {
      x: months,
      y: utilPcts,
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Utilization %',
      line: { color: '#1976D2', width: 2 },
      marker: { size: 6 },
    } as Plotly.Data,
  ]
})

const utilizationChartLayout = computed<Partial<Plotly.Layout>>(() => {
  return {
    xaxis: {
      title: { text: 'Month' },
      tickangle: -45,
    },
    yaxis: {
      title: { text: 'Utilization %' },
      range: [0, 110],
    },
    height: 350,
    legend: {
      orientation: 'h' as const,
      y: -0.3,
    },
    shapes: [
      // Red zone (0-60)
      {
        type: 'rect' as const,
        xref: 'paper' as const,
        yref: 'y' as const,
        x0: 0,
        x1: 1,
        y0: 0,
        y1: 60,
        fillcolor: 'rgba(255, 82, 82, 0.08)',
        line: { width: 0 },
        layer: 'below',
      },
      // Yellow zone (60-80)
      {
        type: 'rect' as const,
        xref: 'paper' as const,
        yref: 'y' as const,
        x0: 0,
        x1: 1,
        y0: 60,
        y1: 80,
        fillcolor: 'rgba(255, 152, 0, 0.08)',
        line: { width: 0 },
        layer: 'below',
      },
      // Green zone (80-100)
      {
        type: 'rect' as const,
        xref: 'paper' as const,
        yref: 'y' as const,
        x0: 0,
        x1: 1,
        y0: 80,
        y1: 100,
        fillcolor: 'rgba(76, 175, 80, 0.08)',
        line: { width: 0 },
        layer: 'below',
      },
      // Target line at 80%
      {
        type: 'line' as const,
        xref: 'paper' as const,
        yref: 'y' as const,
        x0: 0,
        x1: 1,
        y0: 80,
        y1: 80,
        line: { color: '#4CAF50', width: 1.5, dash: 'dash' },
        layer: 'below',
      },
    ] as Plotly.Shape[],
  }
})

// ---- Hours Breakdown Chart (stacked bar) ----

const hoursChartData = computed<Plotly.Data[]>(() => {
  const breakdown = monthlyBreakdown.value
  if (breakdown.length === 0) return []

  const months = breakdown.map((m) => m.month)
  const billable = breakdown.map((m) => m.actual_billable_hours)
  const nonBillable = breakdown.map((m) => m.actual_hours - m.actual_billable_hours)
  const pto = breakdown.map((m) => m.pto_hours)

  return [
    {
      x: months,
      y: billable,
      type: 'bar',
      name: 'Billable Hours',
      marker: { color: '#4CAF50' },
    } as Plotly.Data,
    {
      x: months,
      y: nonBillable,
      type: 'bar',
      name: 'Non-billable Hours',
      marker: { color: '#1976D2' },
    } as Plotly.Data,
    {
      x: months,
      y: pto,
      type: 'bar',
      name: 'PTO Hours',
      marker: { color: '#FF9800' },
    } as Plotly.Data,
  ]
})

const hoursChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  barmode: 'stack' as const,
  xaxis: {
    title: { text: 'Month' },
    tickangle: -45,
  },
  yaxis: {
    title: { text: 'Hours' },
  },
  height: 350,
  legend: {
    orientation: 'h' as const,
    y: -0.3,
  },
}))

function formatNum(val: number | null | undefined, decimals = 1): string {
  if (val == null) return '0'
  return val.toFixed(decimals)
}
</script>

<template>
  <div>
    <!-- Time Frame Selectors -->
    <v-card class="mb-4">
      <v-card-text>
        <v-row align="center">
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="selectedYear"
              :items="yearOptions"
              label="Year"
              density="compact"
              hide-details
              variant="outlined"
            />
          </v-col>
          <v-col cols="12" sm="8" md="5">
            <v-select
              v-model="selectedTimeFrame"
              :items="timeFrameOptions"
              item-title="title"
              item-value="value"
              label="Time Frame"
              density="compact"
              hide-details
              variant="outlined"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Loading -->
    <v-skeleton-loader v-if="dataLoading" type="card, card, image, table" />

    <template v-else>
      <!-- Error -->
      <v-alert v-if="error" type="error" closable class="mb-4">
        {{ error }}
      </v-alert>

      <!-- No Data -->
      <v-alert
        v-if="!utilizationEntry && !error"
        type="info"
        variant="tonal"
        class="mb-4"
      >
        No utilization data available for this employee with the selected time frame.
      </v-alert>

      <template v-if="utilizationEntry">
        <!-- KPI Cards -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md>
            <KpiCard
              title="Utilization"
              :value="formatNum(utilizationPct) + '%'"
              :subtitle="targetAllocationLabel"
              icon="mdi-gauge"
              :color="utilizationColor"
            />
          </v-col>
          <v-col cols="12" sm="6" md>
            <KpiCard
              title="Total Hours"
              :value="formatNum(actualHours)"
              icon="mdi-clock-outline"
              color="#1976D2"
            />
          </v-col>
          <v-col cols="12" sm="6" md>
            <KpiCard
              title="Billable Hours"
              :value="formatNum(billableHours)"
              icon="mdi-cash-check"
              color="#4CAF50"
            />
          </v-col>
          <v-col cols="12" sm="6" md>
            <KpiCard
              title="PTO Hours"
              :value="formatNum(ptoHours)"
              icon="mdi-beach"
              color="#FF9800"
            />
          </v-col>
          <v-col cols="12" sm="6" md>
            <KpiCard
              title="Holiday Hours"
              :value="formatNum(holidayHours)"
              icon="mdi-calendar-star"
              color="#9C27B0"
            />
          </v-col>
        </v-row>

        <!-- Charts Row -->
        <v-row class="mb-4">
          <!-- Cumulative Utilization Chart -->
          <v-col cols="12" md="6">
            <v-card>
              <v-card-title class="text-subtitle-1 font-weight-bold">
                <v-icon class="mr-2" size="small">mdi-chart-line</v-icon>
                Monthly Utilization Trend
              </v-card-title>
              <v-card-text>
                <PlotlyChart
                  :data="utilizationChartData"
                  :layout="utilizationChartLayout"
                  :loading="dataLoading"
                />
                <div
                  v-if="monthlyBreakdown.length === 0"
                  class="text-center text-medium-emphasis py-8"
                >
                  No monthly data available.
                </div>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Hours Breakdown Chart -->
          <v-col cols="12" md="6">
            <v-card>
              <v-card-title class="text-subtitle-1 font-weight-bold">
                <v-icon class="mr-2" size="small">mdi-chart-bar-stacked</v-icon>
                Hours Breakdown
              </v-card-title>
              <v-card-text>
                <PlotlyChart
                  :data="hoursChartData"
                  :layout="hoursChartLayout"
                  :loading="dataLoading"
                />
                <div
                  v-if="monthlyBreakdown.length === 0"
                  class="text-center text-medium-emphasis py-8"
                >
                  No monthly data available.
                </div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <!-- Monthly Hours Table -->
        <v-card>
          <v-card-title class="text-subtitle-1 font-weight-bold">
            <v-icon class="mr-2" size="small">mdi-table</v-icon>
            Monthly Hours Breakdown
          </v-card-title>
          <v-card-text class="pa-0">
            <v-data-table
              :headers="tableHeaders"
              :items="monthlyBreakdown"
              :items-per-page="12"
              density="compact"
              no-data-text="No monthly data available for the selected time frame"
            >
              <template #item.possible_hours="{ item }">
                {{ formatNum(item.possible_hours) }}
              </template>
              <template #item.actual_hours="{ item }">
                {{ formatNum(item.actual_hours) }}
              </template>
              <template #item.actual_billable_hours="{ item }">
                {{ formatNum(item.actual_billable_hours) }}
              </template>
              <template #item.projected_hours="{ item }">
                {{ formatNum(item.projected_hours) }}
              </template>
              <template #item.pto_hours="{ item }">
                {{ formatNum(item.pto_hours) }}
              </template>
              <template #item.holiday_hours="{ item }">
                {{ formatNum(item.holiday_hours) }}
              </template>
              <template #item.utilization_pct="{ item }">
                <v-chip
                  :color="utilizationChipColor(item.utilization_pct)"
                  size="small"
                  label
                >
                  {{ item.utilization_pct != null ? formatNum(item.utilization_pct) + '%' : 'N/A' }}
                </v-chip>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </template>
    </template>
  </div>
</template>
