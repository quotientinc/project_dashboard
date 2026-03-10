<script setup lang="ts">
/**
 * Budget Trajectory Mockup page.
 *
 * Visualizes a stepped budget ceiling over time for a hard-coded project,
 * overlaying actual cumulative costs as a percentage of the applicable
 * contract ceiling at each point in time.
 */
import { ref, computed, onMounted } from 'vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import KpiCard from '@/components/KpiCard.vue'
import { useApi } from '@/composables/useApi'
import { formatCurrency, formatCurrencyFull } from '@/utils/helpers'
import type Plotly from 'plotly.js-dist-min'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROJECT_ID = '220306.00.009.01'
const CONTRACT_START = '2023-01-01'
const CONTRACT_END = '2025-12-31'

interface Modification {
  mod_number: string
  mod_date: string
  ceiling: number
}

const modifications: Modification[] = [
  { mod_number: 'Base', mod_date: '2023-01-01', ceiling: 300000 },
  { mod_number: 'Mod 1', mod_date: '2023-06-01', ceiling: 500000 },
  { mod_number: 'Mod 2', mod_date: '2024-01-01', ceiling: 750000 },
  { mod_number: 'Mod 3', mod_date: '2024-06-01', ceiling: 1000000 },
  { mod_number: 'Mod 4', mod_date: '2025-01-01', ceiling: 1250000 },
]

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

const { get, loading, error } = useApi()

interface PerformanceResponse {
  actuals: Record<string, Record<string, { hours: number; revenue: number; worked_days?: number }>>
  projected: Record<string, Record<string, { hours: number; revenue: number }>>
  possible: Record<string, Record<string, { hours: number; revenue: number }>>
}

const performanceData = ref<PerformanceResponse | null>(null)

async function fetchData() {
  try {
    const params = new URLSearchParams({
      start_date: CONTRACT_START,
      end_date: CONTRACT_END,
      project_id: PROJECT_ID,
    })
    performanceData.value = await get<PerformanceResponse>(
      `/analytics/performance?${params.toString()}`
    )
  } catch {
    // error is already captured by useApi
  }
}

onMounted(fetchData)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBudgetAtDate(date: Date): number {
  const applicable = modifications.filter((m) => new Date(m.mod_date) <= date)
  return applicable.length > 0 ? applicable[applicable.length - 1]!.ceiling : modifications[0]!.ceiling
}

/**
 * Parse a month-name key like "January 2023" into a Date representing the
 * first day of that month.
 */
/**
 * Generate an array of first-of-month dates between start and end (inclusive).
 */
function generateMonthRange(start: string, end: string): Date[] {
  const months: Date[] = []
  const s = new Date(start)
  const e = new Date(end)
  const current = new Date(s.getFullYear(), s.getMonth(), 1)
  while (current <= e) {
    months.push(new Date(current))
    current.setMonth(current.getMonth() + 1)
  }
  return months
}

// ---------------------------------------------------------------------------
// Modification table
// ---------------------------------------------------------------------------

const modTableHeaders = [
  { title: 'Modification', key: 'mod_number' },
  { title: 'Effective Date', key: 'mod_date' },
  { title: 'Contract Ceiling', key: 'ceiling' },
  { title: 'Funding Added', key: 'funding_added' },
]

const modTableItems = computed(() =>
  modifications.map((m, i) => ({
    ...m,
    ceiling_display: formatCurrencyFull(m.ceiling),
    funding_added: i === 0 ? m.ceiling : m.ceiling - modifications[i - 1]!.ceiling,
    funding_added_display: formatCurrencyFull(
      i === 0 ? m.ceiling : m.ceiling - modifications[i - 1]!.ceiling
    ),
  }))
)

// ---------------------------------------------------------------------------
// Chart data
// ---------------------------------------------------------------------------

const today = new Date()
const allMonths = generateMonthRange(CONTRACT_START, CONTRACT_END)

/** Build a lookup: month label -> total revenue from actuals */
function actualsRevenueByMonth(): Map<string, number> {
  const map = new Map<string, number>()
  if (!performanceData.value) return map

  for (const [monthLabel, employees] of Object.entries(performanceData.value.actuals)) {
    let total = 0
    for (const emp of Object.values(employees)) {
      total += emp.revenue ?? 0
    }
    map.set(monthLabel, total)
  }
  return map
}

function projectedRevenueByMonth(): Map<string, number> {
  const map = new Map<string, number>()
  if (!performanceData.value) return map

  for (const [monthLabel, employees] of Object.entries(performanceData.value.projected)) {
    let total = 0
    for (const emp of Object.values(employees)) {
      total += emp.revenue ?? 0
    }
    map.set(monthLabel, total)
  }
  return map
}

/**
 * Format a Date to the same key format returned by the backend: "January 2023"
 */
function toMonthLabel(d: Date): string {
  return d.toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

const chartData = computed<Plotly.Data[]>(() => {
  if (!performanceData.value) return []

  const actualsMap = actualsRevenueByMonth()
  const projectedMap = projectedRevenueByMonth()

  // Build cumulative cost arrays
  const dates: string[] = []
  const baselinePct: number[] = []
  const upperPct: number[] = []
  const lowerPct: number[] = []
  const actualPct: (number | null)[] = []
  const projectedPct: (number | null)[] = []

  let cumulativeActual = 0
  let cumulativeProjected = 0

  for (const month of allMonths) {
    const label = toMonthLabel(month)
    const dateStr = month.toISOString().slice(0, 10)
    dates.push(dateStr)

    const ceiling = getBudgetAtDate(month)

    // Cumulate actuals
    const actualRev = actualsMap.get(label) ?? 0
    cumulativeActual += actualRev

    // Cumulate projected
    const projRev = projectedMap.get(label) ?? 0
    cumulativeProjected += projRev

    // Budget baseline is always 100% of current ceiling
    baselinePct.push(100)
    upperPct.push(110)
    lowerPct.push(90)

    // Actual cost percentage of applicable ceiling
    const isPast = month <= today
    if (isPast && cumulativeActual > 0) {
      actualPct.push((cumulativeActual / ceiling) * 100)
    } else {
      actualPct.push(null)
    }

    // Projected is shown for all months
    if (cumulativeProjected > 0) {
      projectedPct.push((cumulativeProjected / ceiling) * 100)
    } else {
      projectedPct.push(null)
    }
  }

  const traces: Plotly.Data[] = []

  // Target zone (shaded area between upper and lower)
  traces.push({
    x: [...dates, ...dates.slice().reverse()],
    y: [...upperPct, ...lowerPct.slice().reverse()],
    fill: 'toself',
    fillcolor: 'rgba(76, 175, 80, 0.1)',
    line: { color: 'transparent' },
    type: 'scatter',
    mode: 'lines',
    name: 'Target Zone',
    hoverinfo: 'skip',
    showlegend: true,
  })

  // Budget baseline at 100%
  traces.push({
    x: dates,
    y: baselinePct,
    type: 'scatter',
    mode: 'lines',
    name: 'Budget Baseline (100%)',
    line: { color: '#4CAF50', width: 2 },
    hovertemplate: '%{x|%b %Y}: %{y:.1f}%<extra>Budget Baseline</extra>',
  })

  // Upper target boundary
  traces.push({
    x: dates,
    y: upperPct,
    type: 'scatter',
    mode: 'lines',
    name: 'Upper Target (110%)',
    line: { color: '#4CAF50', width: 1, dash: 'dot' },
    hovertemplate: '%{x|%b %Y}: %{y:.1f}%<extra>Upper Target</extra>',
  })

  // Lower target boundary
  traces.push({
    x: dates,
    y: lowerPct,
    type: 'scatter',
    mode: 'lines',
    name: 'Lower Target (90%)',
    line: { color: '#4CAF50', width: 1, dash: 'dot' },
    hovertemplate: '%{x|%b %Y}: %{y:.1f}%<extra>Lower Target</extra>',
  })

  // Actual costs
  traces.push({
    x: dates,
    y: actualPct,
    type: 'scatter',
    mode: 'lines+markers',
    name: 'Actual Costs',
    line: { color: '#1976D2', width: 2 },
    marker: { size: 5, color: '#1976D2' },
    connectgaps: true,
    hovertemplate: '%{x|%b %Y}: %{y:.1f}%<extra>Actual Costs</extra>',
  })

  // Projected trajectory
  traces.push({
    x: dates,
    y: projectedPct,
    type: 'scatter',
    mode: 'lines',
    name: 'Projected Trajectory',
    line: { color: '#FF9800', width: 2, dash: 'dash' },
    connectgaps: true,
    hovertemplate: '%{x|%b %Y}: %{y:.1f}%<extra>Projected</extra>',
  })

  return traces
})

const chartLayout = computed<Partial<Plotly.Layout>>(() => {
  const shapes: Partial<Plotly.Shape>[] = []
  const annotations: Partial<Plotly.Annotations>[] = []

  // Add vertical dashed lines for each modification
  for (const mod of modifications) {
    shapes.push({
      type: 'line',
      x0: mod.mod_date,
      x1: mod.mod_date,
      y0: 0,
      y1: 1,
      yref: 'paper',
      line: { color: '#9E9E9E', width: 1, dash: 'dash' },
    })
    annotations.push({
      x: mod.mod_date,
      y: 1.05,
      yref: 'paper',
      text: `${mod.mod_number}<br>${formatCurrency(mod.ceiling)}`,
      showarrow: false,
      font: { size: 10, color: '#616161' },
      xanchor: 'center',
    })
  }

  return {
    title: {
      text: 'Budget Trajectory - Cumulative Cost vs. Contract Ceiling',
      font: { size: 14 },
    },
    xaxis: {
      title: { text: 'Date' },
      type: 'date',
      tickformat: '%b %Y',
      dtick: 'M3',
      gridcolor: 'rgba(0,0,0,0.05)',
    },
    yaxis: {
      title: { text: '% of Contract Ceiling' },
      ticksuffix: '%',
      gridcolor: 'rgba(0,0,0,0.05)',
      range: [0, 130],
    },
    legend: {
      orientation: 'h',
      y: -0.2,
      x: 0.5,
      xanchor: 'center',
    },
    shapes,
    annotations,
    margin: { t: 60, r: 30, b: 80, l: 60 },
    hovermode: 'x unified',
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Roboto, sans-serif', size: 12 },
    height: 500,
  }
})

// ---------------------------------------------------------------------------
// Summary KPIs
// ---------------------------------------------------------------------------

const totalActualCosts = computed(() => {
  if (!performanceData.value) return 0
  let total = 0
  for (const employees of Object.values(performanceData.value.actuals)) {
    for (const emp of Object.values(employees)) {
      total += emp.revenue ?? 0
    }
  }
  return total
})

const totalProjectedCosts = computed(() => {
  if (!performanceData.value) return 0
  let total = 0
  for (const employees of Object.values(performanceData.value.projected)) {
    for (const emp of Object.values(employees)) {
      total += emp.revenue ?? 0
    }
  }
  return total
})

const currentCeiling = computed(() => {
  return modifications[modifications.length - 1]!.ceiling
})

const totalFundingAdded = computed(() => {
  return modifications.reduce((sum, m, i) => {
    return sum + (i === 0 ? m.ceiling : m.ceiling - modifications[i - 1]!.ceiling)
  }, 0)
})
</script>

<template>
  <div>
    <!-- Header Section -->
    <div class="d-flex align-center justify-space-between mb-2">
      <div>
        <h1 class="text-h4 font-weight-bold">Budget Trajectory Mockup</h1>
        <p class="text-subtitle-1 text-medium-emphasis mt-1">
          Multi-Modification Project Visualization
        </p>
      </div>
    </div>

    <v-alert type="info" variant="tonal" class="mb-4">
      This page visualizes the budget trajectory for a project with multiple contract
      modifications. Each modification raises the contract ceiling, creating a stepped
      budget over the life of the project. Cumulative actual and projected costs are shown
      as percentages of the applicable ceiling at each point in time.
    </v-alert>

    <!-- Project Summary Bar -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text>
        <v-row dense>
          <v-col cols="12" sm="3">
            <div class="text-caption text-medium-emphasis">Project ID</div>
            <div class="text-body-1 font-weight-medium">{{ PROJECT_ID }}</div>
          </v-col>
          <v-col cols="12" sm="3">
            <div class="text-caption text-medium-emphasis">Contract Period</div>
            <div class="text-body-1 font-weight-medium">Jan 2023 - Dec 2025</div>
          </v-col>
          <v-col cols="12" sm="3">
            <div class="text-caption text-medium-emphasis">Total Modifications</div>
            <div class="text-body-1 font-weight-medium">{{ modifications.length }}</div>
          </v-col>
          <v-col cols="12" sm="3">
            <div class="text-caption text-medium-emphasis">Current Contract Ceiling</div>
            <div class="text-body-1 font-weight-medium">
              {{ formatCurrencyFull(currentCeiling) }}
            </div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Error Alert -->
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" closable>
      Failed to load performance data: {{ error }}
    </v-alert>

    <!-- Contract Modification History Table -->
    <v-card class="mb-4">
      <v-card-title class="text-subtitle-1">Contract Modification History</v-card-title>
      <v-card-text>
        <v-data-table
          :headers="modTableHeaders"
          :items="modTableItems"
          density="comfortable"
          :items-per-page="-1"
          hide-default-footer
        >
          <template #item.ceiling="{ item }">
            {{ item.ceiling_display }}
          </template>
          <template #item.funding_added="{ item }">
            <v-chip
              size="small"
              :color="item.funding_added > 0 ? 'success' : 'default'"
              variant="tonal"
            >
              +{{ item.funding_added_display }}
            </v-chip>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Budget Trajectory Chart -->
    <v-card class="mb-4">
      <v-card-title class="text-subtitle-1">Budget Trajectory Chart</v-card-title>
      <v-card-text>
        <PlotlyChart :data="chartData" :layout="chartLayout" :loading="loading" />
      </v-card-text>
    </v-card>

    <!-- Chart Explanation -->
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-subtitle-1">
        <v-icon icon="mdi-information-outline" size="small" class="mr-1" />
        Understanding the Chart
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="6">
            <h3 class="text-body-1 font-weight-bold mb-2">Key Features</h3>
            <ul class="ml-4">
              <li class="mb-1">
                <strong>Stepped budget ceiling</strong> -- each contract modification
                raises the ceiling, recalculating the percentage base.
              </li>
              <li class="mb-1">
                <strong>Target zone (green shaded area)</strong> -- represents the
                acceptable range of plus or minus 10% of budget baseline.
              </li>
              <li class="mb-1">
                <strong>Actual costs (blue line)</strong> -- cumulative costs from
                time entries expressed as a percentage of the applicable ceiling.
              </li>
              <li class="mb-1">
                <strong>Projected trajectory (orange dashed line)</strong> -- based on
                allocation projections for future months.
              </li>
              <li class="mb-1">
                <strong>Vertical dashed lines</strong> -- mark the effective date of
                each contract modification with its new ceiling value.
              </li>
            </ul>
          </v-col>
          <v-col cols="12" md="6">
            <h3 class="text-body-1 font-weight-bold mb-2">Why This Matters</h3>
            <p class="text-body-2">
              Contract modifications are common in government and large-enterprise
              projects. Tracking how cumulative spend relates to the current contract
              ceiling helps project managers identify whether they are burning through
              budget too quickly or leaving funded capacity on the table.
            </p>
            <p class="text-body-2 mt-2">
              When the actual cost line stays within the green target zone, the project
              is on track for healthy budget execution. Deviations above 110% signal
              potential overruns while spending below 90% may indicate under-utilization
              of awarded funding.
            </p>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Summary Metrics -->
    <v-row class="mb-4">
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Actual Costs"
          :value="formatCurrency(totalActualCosts)"
          :subtitle="`${((totalActualCosts / currentCeiling) * 100).toFixed(1)}% of ceiling`"
          icon="mdi-cash-check"
          color="#1976D2"
          :loading="loading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Projected Costs"
          :value="formatCurrency(totalProjectedCosts)"
          :subtitle="`${((totalProjectedCosts / currentCeiling) * 100).toFixed(1)}% of ceiling`"
          icon="mdi-chart-timeline-variant"
          color="#FF9800"
          :loading="loading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Current Budget Ceiling"
          :value="formatCurrency(currentCeiling)"
          :subtitle="`After ${modifications.length} modifications`"
          icon="mdi-shield-check"
          color="#4CAF50"
          :loading="loading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Funding Added"
          :value="formatCurrency(totalFundingAdded)"
          :subtitle="`${modifications.length - 1} modifications since base`"
          icon="mdi-cash-plus"
          color="#9C27B0"
          :loading="loading"
        />
      </v-col>
    </v-row>
  </div>
</template>
