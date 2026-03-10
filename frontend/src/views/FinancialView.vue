<script setup lang="ts">
/**
 * Financial Analysis page with 3-tab interface:
 *   1. Monthly Trends - Revenue vs Cost trend with KPIs
 *   2. Client Analysis - Revenue/profit by client
 *   3. Full Year Forecast - Allocation-based or simple average projections
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import { formatCurrency, formatCurrencyFull, formatPercent } from '@/utils/helpers'
import type { Expense, ClientAnalysisEntry, YearForecastResponse, YearForecastMonth } from '@/types'
import type Plotly from 'plotly.js-dist-min'

// ---- State ----

const api = useApi()

const loadingData = ref(true)
const errorMessage = ref<string | null>(null)

// ---- Filters ----

const currentYear = new Date().getFullYear()
const yearOptions = [currentYear - 1, currentYear, currentYear + 1]
const selectedYear = ref(currentYear)

// ---- Tabs ----

const activeTab = ref(0)

// ---- Tab 1: Monthly Trends data ----

interface PerformanceActuals {
  [monthName: string]: {
    [employeeId: string]: {
      hours: number
      revenue: number
      billable_hours: number
    }
  }
}

interface PerformanceResponse {
  actuals: PerformanceActuals
  projected: Record<string, unknown>
  possible: Record<string, unknown>
}

const performanceData = ref<PerformanceResponse | null>(null)
const expenses = ref<Expense[]>([])

// ---- Tab 2: Client Analysis data ----

const clientData = ref<ClientAnalysisEntry[]>([])
const loadingClient = ref(false)

// ---- Tab 3: Forecast data ----

const forecastData = ref<YearForecastResponse | null>(null)
const forecastMethod = ref(0) // 0 = allocations, 1 = simple_average
const loadingForecast = ref(false)

// ---- Data Fetching ----

async function fetchMonthlyTrends() {
  loadingData.value = true
  errorMessage.value = null
  try {
    const yearStart = `${selectedYear.value}-01-01`
    const yearEnd = `${selectedYear.value}-12-31`
    const [perf, exp] = await Promise.all([
      api.get<PerformanceResponse>('/analytics/performance', {
        params: { start_date: yearStart, end_date: yearEnd },
      }),
      api.get<Expense[]>('/expenses/', {
        params: { start_date: yearStart, end_date: yearEnd },
      }),
    ])
    performanceData.value = perf
    expenses.value = exp
  } catch {
    errorMessage.value = 'Failed to load monthly trends data.'
  } finally {
    loadingData.value = false
  }
}

async function fetchClientAnalysis() {
  loadingClient.value = true
  try {
    clientData.value = await api.get<ClientAnalysisEntry[]>('/analytics/client-analysis', {
      params: { year: selectedYear.value },
    })
  } catch {
    errorMessage.value = 'Failed to load client analysis data.'
  } finally {
    loadingClient.value = false
  }
}

async function fetchForecast() {
  loadingForecast.value = true
  try {
    const method = forecastMethod.value === 0 ? 'allocations' : 'simple_average'
    forecastData.value = await api.get<YearForecastResponse>('/analytics/year-forecast', {
      params: { year: selectedYear.value, method },
    })
  } catch {
    errorMessage.value = 'Failed to load forecast data.'
  } finally {
    loadingForecast.value = false
  }
}

onMounted(() => {
  fetchMonthlyTrends()
})

// Watch year changes: refetch all loaded tabs
watch(selectedYear, () => {
  fetchMonthlyTrends()
  if (clientData.value.length > 0 || activeTab.value === 1) {
    fetchClientAnalysis()
  }
  if (forecastData.value || activeTab.value === 2) {
    fetchForecast()
  }
})

// Lazy-load tab data when switching tabs
watch(activeTab, (tab) => {
  if (tab === 1 && clientData.value.length === 0) {
    fetchClientAnalysis()
  }
  if (tab === 2 && !forecastData.value) {
    fetchForecast()
  }
})

// Refetch forecast when method changes
watch(forecastMethod, () => {
  fetchForecast()
})

// ---- Tab 1: Monthly Trends computed ----

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

interface MonthRow {
  month: string
  monthKey: string
  revenue: number
  laborCost: number
  expensesCost: number
  totalCost: number
  profit: number
  marginPct: number
}

const monthlyRows = computed<MonthRow[]>(() => {
  const rows: MonthRow[] = []
  const actuals = performanceData.value?.actuals || {}

  // Build lookup for expenses by month
  const expByMonth: Record<string, number> = {}
  for (const ex of expenses.value) {
    const m = ex.date.substring(0, 7) // "YYYY-MM"
    expByMonth[m] = (expByMonth[m] || 0) + (ex.amount || 0)
  }

  for (let i = 0; i < 12; i++) {
    const monthName = `${MONTH_NAMES[i]} ${selectedYear.value}`
    const monthKey = `${selectedYear.value}-${String(i + 1).padStart(2, '0')}`

    // Sum revenue from actuals for this month
    let revenue = 0
    let laborCost = 0
    const monthActuals = actuals[monthName]
    if (monthActuals) {
      for (const empId of Object.keys(monthActuals)) {
        const entry = monthActuals[empId]!
        revenue += entry.revenue || 0
        laborCost += entry.revenue || 0
      }
    }

    const expenseCost = expByMonth[monthKey] || 0
    // Total cost = labor cost from expenses (all expenses include labor)
    const totalCost = laborCost + expenseCost
    const profit = revenue - totalCost
    const marginPct = revenue > 0 ? (profit / revenue) * 100 : 0

    rows.push({
      month: MONTH_NAMES[i]!,
      monthKey,
      revenue,
      laborCost,
      expensesCost: expenseCost,
      totalCost,
      profit,
      marginPct,
    })
  }

  return rows
})

const ytdRevenue = computed(() => monthlyRows.value.reduce((s, r) => s + r.revenue, 0))
const ytdLaborCost = computed(() => monthlyRows.value.reduce((s, r) => s + r.laborCost, 0))
const ytdExpensesCost = computed(() => monthlyRows.value.reduce((s, r) => s + r.expensesCost, 0))
const ytdTotalCost = computed(() => monthlyRows.value.reduce((s, r) => s + r.totalCost, 0))
const ytdProfit = computed(() => ytdRevenue.value - ytdTotalCost.value)
const ytdMargin = computed(() =>
  ytdRevenue.value > 0 ? (ytdProfit.value / ytdRevenue.value) * 100 : 0
)

const costSubtitle = computed(() =>
  `Labor: ${formatCurrencyFull(ytdLaborCost.value)} | Expenses: ${formatCurrencyFull(ytdExpensesCost.value)}`
)

// Monthly Trends chart
const trendChartData = computed<Plotly.Data[]>(() => {
  const filtered = monthlyRows.value.filter((r) => r.revenue > 0 || r.totalCost > 0)
  if (filtered.length === 0) return []

  const months = filtered.map((r) => r.month)
  const revenues = filtered.map((r) => r.revenue)
  const costs = filtered.map((r) => r.totalCost)
  const profits = filtered.map((r) => r.profit)

  return [
    {
      type: 'bar' as const,
      name: 'Revenue',
      x: months,
      y: revenues,
      marker: { color: '#2E86C1' },
    },
    {
      type: 'bar' as const,
      name: 'Total Cost',
      x: months,
      y: costs,
      marker: { color: '#E74C3C' },
    },
    {
      type: 'scatter' as const,
      name: 'Profit',
      x: months,
      y: profits,
      mode: 'lines+markers' as const,
      line: { color: '#27AE60', width: 3 },
      yaxis: 'y2',
    },
  ]
})

const trendChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 400,
  barmode: 'group' as const,
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Revenue & Costs ($)' } },
  yaxis2: { title: { text: 'Profit ($)' }, overlaying: 'y' as const, side: 'right' as const },
  hovermode: 'x unified' as const,
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.12 },
}))

// Monthly Trends table headers
const trendTableHeaders = [
  { title: 'Month', key: 'month', sortable: false },
  { title: 'Revenue', key: 'revenue', align: 'end' as const },
  { title: 'Total Cost', key: 'totalCost', align: 'end' as const },
  { title: 'Profit', key: 'profit', align: 'end' as const },
  { title: 'Margin %', key: 'marginPct', align: 'end' as const },
]

// ---- Tab 2: Client Analysis computed ----

const clientPieData = computed<Plotly.Data[]>(() => {
  if (clientData.value.length === 0) return []
  return [
    {
      type: 'pie' as const,
      labels: clientData.value.map((c) => c.client),
      values: clientData.value.map((c) => c.revenue),
      textinfo: 'label+percent' as const,
      hoverinfo: 'label+value+percent' as const,
      hole: 0.4,
    },
  ]
})

const clientPieLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 400,
  showlegend: true,
  legend: { orientation: 'h' as const, y: -0.15 },
}))

const clientBarData = computed<Plotly.Data[]>(() => {
  if (clientData.value.length === 0) return []
  const sorted = [...clientData.value].sort((a, b) => b.margin_pct - a.margin_pct)
  const colors = sorted.map((c) => {
    if (c.margin_pct > 20) return '#27AE60'
    if (c.margin_pct >= 0) return '#F1C40F'
    return '#E74C3C'
  })
  return [
    {
      type: 'bar' as const,
      y: sorted.map((c) => c.client),
      x: sorted.map((c) => c.margin_pct),
      orientation: 'h' as const,
      marker: { color: colors },
      text: sorted.map((c) => c.margin_pct.toFixed(1) + '%'),
      textposition: 'outside' as const,
      hoverinfo: 'y+x' as const,
    },
  ]
})

const clientBarLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: Math.max(350, clientData.value.length * 30 + 80),
  xaxis: { title: { text: 'Profit Margin %' } },
  yaxis: { automargin: true },
  margin: { l: 180, t: 20, r: 80, b: 40 },
}))

const clientTableHeaders = [
  { title: 'Client', key: 'client' },
  { title: 'Revenue', key: 'revenue', align: 'end' as const },
  { title: 'Total Cost', key: 'total_cost', align: 'end' as const },
  { title: 'Profit', key: 'profit', align: 'end' as const },
  { title: 'Margin %', key: 'margin_pct', align: 'end' as const },
]

// ---- Tab 3: Forecast computed ----

const forecastMonths = computed<YearForecastMonth[]>(() => {
  return forecastData.value?.months || []
})

const forecastChartData = computed<Plotly.Data[]>(() => {
  const months = forecastMonths.value
  if (months.length === 0) return []

  const actualMonths = months.filter((m) => m.data_type === 'Actual')
  const projectedMonths = months.filter((m) => m.data_type === 'Projected')

  const traces: Plotly.Data[] = []

  if (actualMonths.length > 0) {
    traces.push({
      type: 'bar' as const,
      name: 'Actual',
      x: actualMonths.map((m) => m.month_name),
      y: actualMonths.map((m) => m.revenue),
      marker: { color: '#2E86C1' },
    })
  }

  if (projectedMonths.length > 0) {
    traces.push({
      type: 'bar' as const,
      name: 'Projected',
      x: projectedMonths.map((m) => m.month_name),
      y: projectedMonths.map((m) => m.revenue),
      marker: {
        color: '#85C1E2',
        pattern: {
          shape: '/' as const,
          size: 6,
        },
      },
    })
  }

  return traces
})

const forecastChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 400,
  barmode: 'group' as const,
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Revenue ($)' } },
  hovermode: 'x unified' as const,
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.12 },
}))

const forecastTableHeaders = [
  { title: 'Month', key: 'month_name', sortable: false },
  { title: 'Revenue', key: 'revenue', align: 'end' as const },
  { title: 'Data Type', key: 'data_type' },
]

const isForecastYearCurrent = computed(() => selectedYear.value === currentYear)
</script>

<template>
  <div>
    <h1 class="text-h4 font-weight-bold mb-2">Financial Analysis</h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Revenue, cost, and profitability analysis.
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

    <!-- Year Selector -->
    <v-card class="pa-4 mb-4">
      <v-row align="center">
        <v-col cols="12" sm="4" md="3">
          <v-select
            v-model="selectedYear"
            :items="yearOptions"
            label="Year"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab :value="0">
        <v-icon icon="mdi-chart-line" class="mr-2" size="18" />
        Monthly Trends
      </v-tab>
      <v-tab :value="1">
        <v-icon icon="mdi-account-group" class="mr-2" size="18" />
        Client Analysis
      </v-tab>
      <v-tab :value="2">
        <v-icon icon="mdi-crystal-ball" class="mr-2" size="18" />
        Full Year Forecast
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- Tab 1: Monthly Trends -->
      <v-window-item :value="0">
        <!-- KPI Cards -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="YTD Revenue"
              :value="formatCurrency(ytdRevenue)"
              :subtitle="formatCurrencyFull(ytdRevenue)"
              icon="mdi-cash-plus"
              color="#2E86C1"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="YTD Costs"
              :value="formatCurrency(ytdTotalCost)"
              :subtitle="costSubtitle"
              icon="mdi-cash-minus"
              color="#E74C3C"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="YTD Profit"
              :value="formatCurrency(ytdProfit)"
              :subtitle="formatCurrencyFull(ytdProfit)"
              icon="mdi-chart-line"
              :color="ytdProfit >= 0 ? '#27AE60' : '#E74C3C'"
              :loading="loadingData"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="YTD Margin"
              :value="formatPercent(ytdMargin)"
              icon="mdi-percent"
              :color="ytdMargin >= 0 ? '#27AE60' : '#E74C3C'"
              :loading="loadingData"
            />
          </v-col>
        </v-row>

        <!-- Revenue vs Cost Chart -->
        <v-card class="pa-4 mb-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-bar" size="20" class="mr-1" />
            Revenue vs Costs Trend
          </div>
          <PlotlyChart
            :data="trendChartData"
            :layout="trendChartLayout"
            :loading="loadingData"
          />
        </v-card>

        <!-- Monthly Breakdown Table -->
        <v-card class="pa-4">
          <div class="text-h6 mb-3">
            <v-icon icon="mdi-table" size="20" class="mr-1" />
            Monthly Breakdown
          </div>
          <v-skeleton-loader v-if="loadingData" type="table-heading, table-row@6" />
          <v-data-table
            v-else
            :headers="trendTableHeaders"
            :items="monthlyRows"
            density="compact"
            items-per-page="-1"
            hide-default-footer
          >
            <template #item.revenue="{ item }">
              {{ formatCurrencyFull(item.revenue) }}
            </template>
            <template #item.totalCost="{ item }">
              {{ formatCurrencyFull(item.totalCost) }}
            </template>
            <template #item.profit="{ item }">
              <span :style="{ color: item.profit >= 0 ? '#27AE60' : '#E74C3C' }">
                {{ formatCurrencyFull(item.profit) }}
              </span>
            </template>
            <template #item.marginPct="{ item }">
              <span :style="{ color: item.marginPct >= 0 ? '#27AE60' : '#E74C3C' }">
                {{ formatPercent(item.marginPct) }}
              </span>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <!-- Tab 2: Client Analysis -->
      <v-window-item :value="1">
        <v-skeleton-loader v-if="loadingClient" type="card, table" />
        <template v-else>
          <v-row class="mb-4">
            <v-col cols="12" md="6">
              <v-card class="pa-4">
                <div class="text-h6 mb-2">
                  <v-icon icon="mdi-chart-pie" size="20" class="mr-1" />
                  Revenue by Client
                </div>
                <PlotlyChart
                  :data="clientPieData"
                  :layout="clientPieLayout"
                  :loading="loadingClient"
                />
              </v-card>
            </v-col>
            <v-col cols="12" md="6">
              <v-card class="pa-4">
                <div class="text-h6 mb-2">
                  <v-icon icon="mdi-chart-bar" size="20" class="mr-1" />
                  Profit Margin by Client
                </div>
                <PlotlyChart
                  :data="clientBarData"
                  :layout="clientBarLayout"
                  :loading="loadingClient"
                />
              </v-card>
            </v-col>
          </v-row>

          <!-- Client Summary Table -->
          <v-card class="pa-4">
            <div class="text-h6 mb-3">
              <v-icon icon="mdi-table" size="20" class="mr-1" />
              Client Summary
            </div>
            <v-data-table
              :headers="clientTableHeaders"
              :items="clientData"
              density="compact"
              items-per-page="-1"
              hide-default-footer
            >
              <template #item.revenue="{ item }">
                {{ formatCurrencyFull(item.revenue) }}
              </template>
              <template #item.total_cost="{ item }">
                {{ formatCurrencyFull(item.total_cost) }}
              </template>
              <template #item.profit="{ item }">
                <span :style="{ color: item.profit >= 0 ? '#27AE60' : '#E74C3C' }">
                  {{ formatCurrencyFull(item.profit) }}
                </span>
              </template>
              <template #item.margin_pct="{ item }">
                <span :style="{ color: item.margin_pct >= 0 ? '#27AE60' : '#E74C3C' }">
                  {{ formatPercent(item.margin_pct) }}
                </span>
              </template>
            </v-data-table>
          </v-card>
        </template>
      </v-window-item>

      <!-- Tab 3: Full Year Forecast -->
      <v-window-item :value="2">
        <!-- Method toggle -->
        <v-card class="pa-4 mb-4">
          <v-btn-toggle
            v-model="forecastMethod"
            mandatory
            color="primary"
            variant="outlined"
            density="compact"
          >
            <v-btn :value="0">Allocations-Based</v-btn>
            <v-btn :value="1">Simple Average</v-btn>
          </v-btn-toggle>
        </v-card>

        <!-- Info if not current year -->
        <v-alert
          v-if="!isForecastYearCurrent"
          type="info"
          variant="tonal"
          class="mb-4"
        >
          Forecast is only available for the current year ({{ currentYear }}).
          Showing historical data for {{ selectedYear }}.
        </v-alert>

        <v-skeleton-loader v-if="loadingForecast" type="card, table" />
        <template v-else-if="forecastData">
          <!-- KPI Cards -->
          <v-row class="mb-4">
            <v-col cols="12" sm="4">
              <KpiCard
                title="YTD Actual"
                :value="formatCurrency(forecastData.ytd_actual)"
                :subtitle="formatCurrencyFull(forecastData.ytd_actual)"
                icon="mdi-check-circle"
                color="#2E86C1"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <KpiCard
                title="Projected Remaining"
                :value="formatCurrency(forecastData.projected_remaining)"
                :subtitle="formatCurrencyFull(forecastData.projected_remaining)"
                icon="mdi-clock-outline"
                color="#85C1E2"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <KpiCard
                title="Full Year Forecast"
                :value="formatCurrency(forecastData.full_year_forecast)"
                :subtitle="formatCurrencyFull(forecastData.full_year_forecast)"
                icon="mdi-crystal-ball"
                color="#27AE60"
              />
            </v-col>
          </v-row>

          <!-- Forecast Chart -->
          <v-card class="pa-4 mb-4">
            <div class="text-h6 mb-2">
              <v-icon icon="mdi-chart-bar" size="20" class="mr-1" />
              Monthly Revenue Forecast
            </div>
            <PlotlyChart
              :data="forecastChartData"
              :layout="forecastChartLayout"
              :loading="loadingForecast"
            />
          </v-card>

          <!-- Forecast Table -->
          <v-card class="pa-4">
            <div class="text-h6 mb-3">
              <v-icon icon="mdi-table" size="20" class="mr-1" />
              Forecast Details
            </div>
            <v-data-table
              :headers="forecastTableHeaders"
              :items="forecastMonths"
              density="compact"
              items-per-page="-1"
              hide-default-footer
            >
              <template #item.revenue="{ item }">
                {{ formatCurrencyFull(item.revenue) }}
              </template>
              <template #item.data_type="{ item }">
                <v-chip
                  :color="item.data_type === 'Actual' ? 'blue' : 'grey'"
                  size="small"
                  variant="tonal"
                >
                  {{ item.data_type }}
                </v-chip>
              </template>
            </v-data-table>
          </v-card>
        </template>
      </v-window-item>
    </v-window>
  </div>
</template>
