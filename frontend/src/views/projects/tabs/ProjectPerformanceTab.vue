<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { CombinedPerformanceResponse } from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'
import { formatCurrency, formatPercent, downloadCsv } from '@/utils/helpers'
import type Plotly from 'plotly.js-dist-min'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const performance = ref<CombinedPerformanceResponse | null>(null)

async function fetchData() {
  try {
    performance.value = await get<CombinedPerformanceResponse>(
      `/analytics/performance/combined?project_id=${encodeURIComponent(projectId.value)}`
    )
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchData)
watch(projectId, fetchData)

// Summary computeds
const summary = computed(() => performance.value?.summary ?? null)
const breakdown = computed(() => performance.value?.monthly_breakdown ?? [])

const budgetStatusColor = computed(() => {
  const pct = summary.value?.budget_pct ?? 0
  if (pct > 100) return '#F44336'
  if (pct > 80) return '#FF9800'
  return '#4CAF50'
})

// Table headers
const tableHeaders = [
  { title: 'Month', key: 'month', sortable: true },
  { title: 'Type', key: 'month_type', sortable: true },
  { title: 'Combined Hours', key: 'combined_hours', align: 'end' as const },
  { title: 'Actual Hours', key: 'actual_hours', align: 'end' as const },
  { title: 'Projected Hours', key: 'projected_hours', align: 'end' as const },
  { title: 'Combined Revenue', key: 'combined_revenue', align: 'end' as const },
  { title: 'Actual Revenue', key: 'actual_revenue', align: 'end' as const },
  { title: 'Projected Revenue', key: 'projected_revenue', align: 'end' as const },
  { title: 'Cumulative Revenue', key: 'cumulative_revenue', align: 'end' as const },
  { title: 'Budget %', key: 'budget_pct', align: 'end' as const },
  { title: 'Status', key: 'status' },
]

function monthTypeIcon(type: string): string {
  switch (type) {
    case 'past': return 'mdi-chart-bar'
    case 'active': return 'mdi-flash'
    case 'future': return 'mdi-chart-line'
    default: return 'mdi-help-circle-outline'
  }
}

function monthTypeColor(type: string): string {
  switch (type) {
    case 'past': return '#2E86C1'
    case 'active': return '#F39C12'
    case 'future': return '#85C1E2'
    default: return '#9E9E9E'
  }
}

function formatDollars(value: number): string {
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// Chart 1: Cumulative Revenue vs Budget
const cumulativeChartData = computed<Plotly.Data[]>(() => {
  if (breakdown.value.length === 0) return []

  const months = breakdown.value.map((m) => m.month)
  const cumulativeRevenue = breakdown.value.map((m) => m.cumulative_revenue)
  const budgetValue = project.value?.awarded_value ?? 0

  const traces: Plotly.Data[] = [
    {
      x: months,
      y: cumulativeRevenue,
      type: 'scatter' as const,
      mode: 'lines' as const,
      fill: 'tozeroy' as const,
      name: 'Cumulative Revenue',
      line: { color: '#1976D2', width: 2 },
      fillcolor: 'rgba(25, 118, 210, 0.15)',
    },
  ]

  if (budgetValue > 0) {
    traces.push({
      x: months,
      y: months.map(() => budgetValue),
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: 'Budget (Awarded Value)',
      line: { color: '#F44336', width: 2, dash: 'dash' },
    })
  }

  return traces
})

const cumulativeChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Amount ($)' }, tickformat: '$,.0f' },
  legend: { orientation: 'h' as const, y: -0.25 },
  height: 350,
}))

// Chart 2: Hours by Month
const hoursChartData = computed<Plotly.Data[]>(() => {
  if (breakdown.value.length === 0) return []

  const months = breakdown.value.map((m) => m.month)
  const hours = breakdown.value.map((m) => m.combined_hours)
  const colors = breakdown.value.map((m) => monthTypeColor(m.month_type))

  return [
    {
      x: months,
      y: hours,
      type: 'bar' as const,
      name: 'Combined Hours',
      marker: { color: colors },
    },
  ]
})

const hoursChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  height: 350,
  showlegend: false,
}))

// CSV export
function exportCsv() {
  if (breakdown.value.length === 0) return
  const rows = breakdown.value.map((m) => ({
    month: m.month,
    month_type: m.month_type,
    combined_hours: m.combined_hours,
    actual_hours: m.actual_hours,
    projected_hours: m.projected_hours,
    combined_revenue: m.combined_revenue,
    actual_revenue: m.actual_revenue,
    projected_revenue: m.projected_revenue,
    cumulative_revenue: m.cumulative_revenue,
    budget_pct: m.budget_pct,
    status: m.status,
  }))
  downloadCsv(rows, `performance_${projectId.value}.csv`)
}
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading && !performance" type="card, card, table" />

    <!-- Error -->
    <v-alert v-else-if="error && !performance" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Content -->
    <template v-else-if="performance">
      <!-- KPI Summary Cards -->
      <v-row class="mb-4">
        <v-col cols="12" sm="6" md="4">
          <KpiCard
            title="Total Hours"
            :value="summary ? summary.total_hours.toFixed(1) : '-'"
            icon="mdi-clock-outline"
            color="#1976D2"
          />
        </v-col>
        <v-col cols="12" sm="6" md="4">
          <KpiCard
            title="Total Accrued"
            :value="summary ? formatCurrency(summary.total_accrued) : '-'"
            icon="mdi-currency-usd"
            color="#4CAF50"
          />
        </v-col>
        <v-col cols="12" sm="6" md="4">
          <KpiCard
            title="Budget Status"
            :value="summary ? summary.budget_status : '-'"
            :subtitle="summary ? formatPercent(summary.budget_pct) + ' of budget' : undefined"
            icon="mdi-target"
            :color="budgetStatusColor"
          />
        </v-col>
      </v-row>

      <!-- Monthly Breakdown Table -->
      <v-card class="mb-4 pa-4">
        <div class="d-flex align-center mb-3">
          <div class="text-subtitle-1 font-weight-bold flex-grow-1">Monthly Breakdown</div>
          <v-btn
            variant="outlined"
            size="small"
            prepend-icon="mdi-download"
            :disabled="breakdown.length === 0"
            @click="exportCsv"
          >
            Export CSV
          </v-btn>
        </div>

        <v-data-table
          v-if="breakdown.length > 0"
          :headers="tableHeaders"
          :items="breakdown"
          density="compact"
          :items-per-page="25"
          class="performance-table"
        >
          <template #item.month_type="{ item }">
            <v-chip
              size="x-small"
              label
              :color="monthTypeColor(item.month_type)"
              text-color="white"
            >
              <v-icon :icon="monthTypeIcon(item.month_type)" size="12" class="mr-1" />
              {{ item.month_type }}
            </v-chip>
          </template>
          <template #item.combined_hours="{ item }">
            {{ item.combined_hours.toFixed(1) }}
          </template>
          <template #item.actual_hours="{ item }">
            {{ item.actual_hours.toFixed(1) }}
          </template>
          <template #item.projected_hours="{ item }">
            {{ item.projected_hours.toFixed(1) }}
          </template>
          <template #item.combined_revenue="{ item }">
            {{ formatDollars(item.combined_revenue) }}
          </template>
          <template #item.actual_revenue="{ item }">
            {{ formatDollars(item.actual_revenue) }}
          </template>
          <template #item.projected_revenue="{ item }">
            {{ formatDollars(item.projected_revenue) }}
          </template>
          <template #item.cumulative_revenue="{ item }">
            {{ formatDollars(item.cumulative_revenue) }}
          </template>
          <template #item.budget_pct="{ item }">
            <template v-if="item.budget_pct != null">
              <v-chip
                size="x-small"
                :color="item.budget_pct > 100 ? 'error' : item.budget_pct > 80 ? 'warning' : 'success'"
                label
              >
                {{ formatPercent(item.budget_pct) }}
              </v-chip>
            </template>
            <span v-else class="text-medium-emphasis">-</span>
          </template>
          <template #item.status="{ item }">
            <span v-if="item.status" class="text-caption">{{ item.status }}</span>
            <span v-else class="text-medium-emphasis">-</span>
          </template>
        </v-data-table>

        <v-alert v-else type="info" variant="tonal" density="compact">
          No performance data available for this project.
        </v-alert>
      </v-card>

      <!-- Charts -->
      <v-row class="mb-4">
        <v-col cols="12" lg="6">
          <v-card class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-2">Cumulative Revenue vs Budget</div>
            <PlotlyChart
              :data="cumulativeChartData"
              :layout="cumulativeChartLayout"
              :loading="loading"
            />
          </v-card>
        </v-col>
        <v-col cols="12" lg="6">
          <v-card class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-2">Hours by Month</div>
            <div class="d-flex ga-3 mb-2">
              <div class="d-flex align-center">
                <div class="legend-swatch" style="background: #2E86C1;" />
                <span class="text-caption ml-1">Past</span>
              </div>
              <div class="d-flex align-center">
                <div class="legend-swatch" style="background: #F39C12;" />
                <span class="text-caption ml-1">Active</span>
              </div>
              <div class="d-flex align-center">
                <div class="legend-swatch" style="background: #85C1E2;" />
                <span class="text-caption ml-1">Future</span>
              </div>
            </div>
            <PlotlyChart
              :data="hoursChartData"
              :layout="hoursChartLayout"
              :loading="loading"
            />
          </v-card>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.legend-swatch {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.performance-table :deep(th) {
  white-space: nowrap;
}
</style>
