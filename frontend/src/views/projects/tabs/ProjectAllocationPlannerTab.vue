<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { formatCurrency, formatCurrencyFull, formatPercent } from '@/utils/helpers'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type {
  Allocation,
  CombinedPerformanceResponse,
  CombinedMonthlyBreakdown,
  ProjectHealthEntry,
} from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const combinedPerf = ref<CombinedPerformanceResponse | null>(null)
const allocations = ref<Allocation[]>([])
const healthData = ref<ProjectHealthEntry | null>(null)

async function fetchData() {
  try {
    const [perfData, allocData, healthList] = await Promise.all([
      get<CombinedPerformanceResponse>(
        `/analytics/performance/combined?project_id=${encodeURIComponent(projectId.value)}`
      ),
      get<Allocation[]>(`/allocations/?project_id=${encodeURIComponent(projectId.value)}`),
      get<ProjectHealthEntry[]>('/analytics/health'),
    ])
    combinedPerf.value = perfData
    allocations.value = allocData
    healthData.value = healthList.find((h) => h.id === projectId.value) ?? null
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchData)
watch(projectId, fetchData)

// ---- Budget Health Dashboard ----

const awardedValue = computed(() => project.value?.awarded_value ?? 0)
const budgetUsed = computed(() => project.value?.budget_used ?? 0)

const budgetUsedPct = computed(() => {
  return awardedValue.value > 0 ? (budgetUsed.value / awardedValue.value) * 100 : 0
})

function budgetStatusColor(pct: number): string {
  if (pct < 80) return '#4CAF50'
  if (pct < 90) return '#FF9800'
  return '#F44336'
}

function budgetStatusVuetifyColor(pct: number): string {
  if (pct < 80) return 'success'
  if (pct < 90) return 'warning'
  return 'error'
}

// Projected outcome from combined performance data
const projectedFinalPct = computed(() => {
  if (!combinedPerf.value?.monthly_breakdown?.length || awardedValue.value === 0) return 0
  const breakdown = combinedPerf.value.monthly_breakdown
  const lastMonth = breakdown[breakdown.length - 1]
  if (!lastMonth) return 0
  return lastMonth.cumulative_revenue > 0
    ? (lastMonth.cumulative_revenue / awardedValue.value) * 100
    : 0
})

const projectedOutcomeLabel = computed(() => {
  const pct = projectedFinalPct.value
  if (pct >= 90 && pct <= 110) return 'On Track'
  if (pct > 110) return 'Over Budget'
  return 'Under Budget'
})

const projectedOutcomeColor = computed(() => {
  const label = projectedOutcomeLabel.value
  if (label === 'On Track') return '#4CAF50'
  if (label === 'Over Budget') return '#F44336'
  return '#FF9800'
})

// Health score
const healthScore = computed(() => healthData.value?.health_score ?? null)

function healthEmoji(score: number | null): string {
  if (score == null) return '--'
  if (score >= 70) return 'Healthy'
  if (score >= 40) return 'At Risk'
  return 'Critical'
}

function healthEmojiIcon(score: number | null): string {
  if (score == null) return 'mdi-help-circle-outline'
  if (score >= 70) return 'mdi-check-circle-outline'
  if (score >= 40) return 'mdi-alert-outline'
  return 'mdi-close-circle-outline'
}

function healthScoreColor(score: number | null): string {
  if (score == null) return '#9E9E9E'
  if (score >= 70) return '#4CAF50'
  if (score >= 40) return '#FF9800'
  return '#F44336'
}

// ---- Budget Trajectory Chart ----

const trajectoryChartData = computed(() => {
  if (!combinedPerf.value?.monthly_breakdown?.length || awardedValue.value === 0) return []

  const breakdown = combinedPerf.value.monthly_breakdown
  const months = breakdown.map((m) => m.month)

  // Actual data: months with actual data (past months)
  const actualMonths = breakdown.filter((m) => m.month_type === 'actual' || m.month_type === 'current')
  const projectedMonths = breakdown.filter((m) => m.month_type === 'future')

  // Actual cumulative line
  const actualX = actualMonths.map((m) => m.month)
  const actualY = actualMonths.map(
    (m) => (m.cumulative_revenue / awardedValue.value) * 100
  )

  // Projected cumulative line (starts from last actual point)
  const lastActual = actualMonths.length > 0 ? actualMonths[actualMonths.length - 1] : undefined
  const projectedX = [
    ...(lastActual ? [lastActual.month] : []),
    ...projectedMonths.map((m) => m.month),
  ]
  const projectedY = [
    ...(lastActual
      ? [(lastActual.cumulative_revenue / awardedValue.value) * 100]
      : []),
    ...projectedMonths.map((m) => (m.cumulative_revenue / awardedValue.value) * 100),
  ]

  const traces = []

  // Target zone shaded area (90%-110%)
  traces.push({
    x: [...months, ...months.slice().reverse()],
    y: [
      ...months.map(() => 110),
      ...months.slice().reverse().map(() => 90),
    ],
    fill: 'toself' as const,
    fillcolor: 'rgba(76, 175, 80, 0.1)',
    line: { color: 'transparent' },
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: 'Target Zone (90-110%)',
    showlegend: true,
    hoverinfo: 'skip' as const,
  })

  // 100% baseline
  traces.push({
    x: months,
    y: months.map(() => 100),
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: 'Budget Baseline (100%)',
    line: { color: '#F44336', dash: 'dash' as const, width: 2 },
    hoverinfo: 'skip' as const,
  })

  // Actual cumulative cost line
  if (actualX.length > 0) {
    traces.push({
      x: actualX,
      y: actualY,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Actual (% of Budget)',
      line: { color: '#1976D2', width: 3 },
      marker: { size: 6 },
    })
  }

  // Projected trajectory line
  if (projectedX.length > 1) {
    traces.push({
      x: projectedX,
      y: projectedY,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Projected (% of Budget)',
      line: { color: '#1976D2', dash: 'dot' as const, width: 2 },
      marker: { size: 5, symbol: 'diamond' },
    })
  }

  return traces
})

const trajectoryChartLayout = computed(() => ({
  title: { text: 'Budget Trajectory', font: { size: 14 } },
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: '% of Budget' }, ticksuffix: '%' },
  height: 400,
  legend: { orientation: 'h' as const, y: -0.25 },
  hovermode: 'x unified' as const,
}))

// ---- Allocation Table (future months only) ----

const futureMonthsBreakdown = computed<CombinedMonthlyBreakdown[]>(() => {
  if (!combinedPerf.value?.monthly_breakdown) return []
  return combinedPerf.value.monthly_breakdown.filter((m) => m.month_type === 'future')
})

// Build a map of allocation FTEs per month
const allocationFteByMonth = computed(() => {
  const map = new Map<string, number>()
  for (const alloc of allocations.value) {
    // allocation_date is YYYY-MM-DD, group by YYYY-MM
    const monthKey = alloc.allocation_date.substring(0, 7)
    map.set(monthKey, (map.get(monthKey) ?? 0) + alloc.allocated_fte)
  }
  return map
})

interface AllocationTableRow {
  month: string
  currentFte: number
  projectedHours: number
  projectedCost: number
  status: string
  statusColor: string
}

const allocationTableRows = computed<AllocationTableRow[]>(() => {
  return futureMonthsBreakdown.value.map((m) => {
    const monthKey = m.month.substring(0, 7)
    const currentFte = allocationFteByMonth.value.get(monthKey) ?? 0
    const budgetPct = m.budget_pct ?? 0

    let status = 'On Track'
    let statusColor = 'success'
    if (budgetPct > 110) {
      status = 'Over Budget'
      statusColor = 'error'
    } else if (budgetPct < 90) {
      status = 'Under Budget'
      statusColor = 'warning'
    }

    return {
      month: m.month,
      currentFte,
      projectedHours: m.projected_hours,
      projectedCost: m.projected_revenue,
      status,
      statusColor,
    }
  })
})

const allocationTableHeaders = [
  { title: 'Month', key: 'month', sortable: true },
  { title: 'Current Allocation (FTE)', key: 'currentFte', align: 'end' as const, sortable: true },
  { title: 'Projected Hours', key: 'projectedHours', align: 'end' as const, sortable: true },
  { title: 'Projected Cost', key: 'projectedCost', align: 'end' as const, sortable: true },
  { title: 'Status', key: 'status', sortable: true },
]

// ---- Scenario Analysis ----

interface ScenarioCard {
  name: string
  icon: string
  color: string
  projectedPct: number
  recommendation: string
}

const scenarios = computed<ScenarioCard[]>(() => {
  if (!combinedPerf.value?.monthly_breakdown?.length || awardedValue.value === 0) {
    return []
  }

  const breakdown = combinedPerf.value.monthly_breakdown

  // Get the last actual cumulative revenue
  const actualMonths = breakdown.filter(
    (m) => m.month_type === 'actual' || m.month_type === 'current'
  )
  const lastActualCumulative =
    actualMonths.length > 0 ? (actualMonths[actualMonths.length - 1]?.cumulative_revenue ?? 0) : 0

  // Sum future projected revenue
  const futureMonths = breakdown.filter((m) => m.month_type === 'future')
  const futureProjectedRevenue = futureMonths.reduce(
    (sum, m) => sum + m.projected_revenue,
    0
  )

  // Current plan
  const currentTotal = lastActualCumulative + futureProjectedRevenue
  const currentPct = (currentTotal / awardedValue.value) * 100

  // Conservative: reduce future by 20%
  const conservativeTotal = lastActualCumulative + futureProjectedRevenue * 0.8
  const conservativePct = (conservativeTotal / awardedValue.value) * 100

  // Aggressive: increase future by 20%
  const aggressiveTotal = lastActualCumulative + futureProjectedRevenue * 1.2
  const aggressivePct = (aggressiveTotal / awardedValue.value) * 100

  function getRecommendation(pct: number, label: string): string {
    if (pct >= 90 && pct <= 110) {
      return `${label} keeps spending within the target zone. Maintain current approach.`
    }
    if (pct > 110) {
      return `${label} projects overspend at ${pct.toFixed(1)}%. Consider reducing allocations.`
    }
    return `${label} projects underspend at ${pct.toFixed(1)}%. Consider increasing utilization to maximize contract value.`
  }

  return [
    {
      name: 'Current Plan',
      icon: 'mdi-target',
      color: currentPct >= 90 && currentPct <= 110 ? '#4CAF50' : currentPct > 110 ? '#F44336' : '#FF9800',
      projectedPct: currentPct,
      recommendation: getRecommendation(currentPct, 'Current plan'),
    },
    {
      name: 'Conservative (-20%)',
      icon: 'mdi-shield-check-outline',
      color: conservativePct >= 90 && conservativePct <= 110 ? '#4CAF50' : conservativePct > 110 ? '#F44336' : '#FF9800',
      projectedPct: conservativePct,
      recommendation: getRecommendation(conservativePct, 'Conservative scenario'),
    },
    {
      name: 'Aggressive (+20%)',
      icon: 'mdi-rocket-launch-outline',
      color: aggressivePct >= 90 && aggressivePct <= 110 ? '#4CAF50' : aggressivePct > 110 ? '#F44336' : '#FF9800',
      projectedPct: aggressivePct,
      recommendation: getRecommendation(aggressivePct, 'Aggressive scenario'),
    },
  ]
})
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading" type="card, card, image, table, card" />

    <!-- Error -->
    <v-alert v-else-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Content -->
    <template v-else-if="project && combinedPerf">
      <!-- Budget Health Dashboard -->
      <v-row class="mb-4">
        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4" :style="{ borderLeft: `4px solid ${budgetStatusColor(budgetUsedPct)}` }">
            <div class="text-caption text-medium-emphasis text-uppercase font-weight-medium mb-1">
              <v-icon icon="mdi-chart-donut" size="18" class="mr-1" />
              Current Status
            </div>
            <div class="text-h5 font-weight-bold" :style="{ color: budgetStatusColor(budgetUsedPct) }">
              {{ formatPercent(budgetUsedPct) }}
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              {{ formatCurrency(budgetUsed) }} of {{ formatCurrency(awardedValue) }}
            </div>
            <v-progress-linear
              :model-value="Math.min(budgetUsedPct, 100)"
              :color="budgetStatusVuetifyColor(budgetUsedPct)"
              height="6"
              rounded
              class="mt-2"
            />
          </v-card>
        </v-col>

        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4" :style="{ borderLeft: `4px solid ${projectedOutcomeColor}` }">
            <div class="text-caption text-medium-emphasis text-uppercase font-weight-medium mb-1">
              <v-icon icon="mdi-crystal-ball" size="18" class="mr-1" />
              Projected Outcome
            </div>
            <div class="text-h5 font-weight-bold" :style="{ color: projectedOutcomeColor }">
              {{ formatPercent(projectedFinalPct) }}
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              <v-chip
                :color="projectedOutcomeLabel === 'On Track' ? 'success' : projectedOutcomeLabel === 'Over Budget' ? 'error' : 'warning'"
                size="x-small"
                label
              >
                {{ projectedOutcomeLabel }}
              </v-chip>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4" :style="{ borderLeft: '4px solid #1976D2' }">
            <div class="text-caption text-medium-emphasis text-uppercase font-weight-medium mb-1">
              <v-icon icon="mdi-bullseye-arrow" size="18" class="mr-1" />
              Target Zone
            </div>
            <div class="text-h5 font-weight-bold" style="color: #1976D2;">
              90% - 110%
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              Acceptable budget utilization range
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4" :style="{ borderLeft: `4px solid ${healthScoreColor(healthScore)}` }">
            <div class="text-caption text-medium-emphasis text-uppercase font-weight-medium mb-1">
              <v-icon :icon="healthEmojiIcon(healthScore)" size="18" class="mr-1" />
              Health Score
            </div>
            <div class="text-h5 font-weight-bold" :style="{ color: healthScoreColor(healthScore) }">
              {{ healthScore != null ? healthScore.toFixed(0) : 'N/A' }}
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              <v-chip
                :color="healthScore != null && healthScore >= 70 ? 'success' : healthScore != null && healthScore >= 40 ? 'warning' : 'error'"
                size="x-small"
                label
              >
                {{ healthEmoji(healthScore) }}
              </v-chip>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Budget Trajectory Chart -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">
          <v-icon icon="mdi-chart-timeline-variant" size="small" class="mr-1" />
          Budget Trajectory
        </div>
        <PlotlyChart
          :data="trajectoryChartData"
          :layout="trajectoryChartLayout"
          :loading="false"
        />
        <div class="text-caption text-medium-emphasis mt-2">
          Solid line shows actual spend as a percentage of awarded budget. Dashed line projects future spend based on current allocations. Green band marks the 90-110% target zone.
        </div>
      </v-card>

      <!-- Allocation Table (future months) -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">
          <v-icon icon="mdi-table-clock" size="small" class="mr-1" />
          Future Month Allocations
        </div>

        <v-alert
          v-if="allocationTableRows.length === 0"
          type="info"
          variant="tonal"
          density="compact"
        >
          No future month data available for this project.
        </v-alert>

        <v-data-table
          v-else
          :headers="allocationTableHeaders"
          :items="allocationTableRows"
          density="compact"
          items-per-page="12"
          class="elevation-0"
        >
          <template #item.currentFte="{ item }">
            {{ item.currentFte.toFixed(2) }}
          </template>
          <template #item.projectedHours="{ item }">
            {{ item.projectedHours.toFixed(1) }} hrs
          </template>
          <template #item.projectedCost="{ item }">
            {{ formatCurrencyFull(item.projectedCost) }}
          </template>
          <template #item.status="{ item }">
            <v-chip :color="item.statusColor" size="small" label>
              {{ item.status }}
            </v-chip>
          </template>
        </v-data-table>
      </v-card>

      <!-- Scenario Analysis -->
      <v-card class="pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-4">
          <v-icon icon="mdi-swap-horizontal" size="small" class="mr-1" />
          Scenario Analysis
        </div>

        <v-alert
          v-if="scenarios.length === 0"
          type="info"
          variant="tonal"
          density="compact"
        >
          Insufficient data for scenario analysis.
        </v-alert>

        <v-row v-else>
          <v-col v-for="scenario in scenarios" :key="scenario.name" cols="12" md="4">
            <v-card
              variant="outlined"
              class="pa-4 h-100"
              :style="{ borderTop: `3px solid ${scenario.color}` }"
            >
              <div class="d-flex align-center mb-2">
                <v-icon :icon="scenario.icon" :color="scenario.color" size="24" class="mr-2" />
                <span class="text-subtitle-2 font-weight-bold">{{ scenario.name }}</span>
              </div>
              <div class="text-h4 font-weight-bold mb-2" :style="{ color: scenario.color }">
                {{ formatPercent(scenario.projectedPct) }}
              </div>
              <div class="text-body-2 text-medium-emphasis">
                {{ scenario.recommendation }}
              </div>
            </v-card>
          </v-col>
        </v-row>
      </v-card>
    </template>

    <!-- No combined performance data -->
    <v-alert v-else-if="project && !combinedPerf" type="info" variant="tonal">
      No combined performance data available for this project. The planner requires allocation and time entry data to generate projections.
    </v-alert>
  </div>
</template>
