<script setup lang="ts">
/**
 * What-If Scenario Analysis page.
 *
 * Provides interactive sliders for exploring hypothetical changes to
 * staffing, costs, timelines, and revenue. All scenario calculations
 * happen client-side in real-time using computed properties.
 */
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { OverviewKPIs, Project } from '@/types'
import type Plotly from 'plotly.js-dist-min'

// ---- State ----

const api = useApi()

const kpis = ref<OverviewKPIs | null>(null)
const projects = ref<Project[]>([])
const loadingBaseline = ref(true)
const errorMessage = ref<string | null>(null)

// ---- Scenario Controls ----

// Cost scenarios
const rateChange = ref(0) // -50% to +50%
const teamSizeChange = ref(0) // -5 to +10 people
const overheadChange = ref(0) // -20% to +20%

// Timeline scenarios
const durationChange = ref(0) // -6 to +12 months
const utilizationTarget = ref(80) // 50% to 100%

// Revenue scenarios
const revenueGrowth = ref(0) // -30% to +50%
const newProjects = ref(0) // 0 to 5
const avgProjectValue = ref(100000) // text field

// ---- Formatting helpers ----

function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`
  }
  if (Math.abs(value) >= 1_000) {
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

function formatDelta(value: number, isCurrency = true): string {
  const sign = value >= 0 ? '+' : ''
  if (isCurrency) {
    return `${sign}${formatCurrencyFull(value)}`
  }
  return `${sign}${value.toFixed(1)}%`
}

// ---- Baseline calculations ----

const baselineRevenue = computed(() => {
  if (!kpis.value) return 0
  return kpis.value.total_awarded_value || kpis.value.total_quoted_value || 0
})

const baselineCosts = computed(() => {
  if (!kpis.value) return 0
  return kpis.value.total_budget_used || 0
})

const baselineProfit = computed(() => {
  return baselineRevenue.value - baselineCosts.value
})

const baselineMargin = computed(() => {
  if (baselineRevenue.value === 0) return 0
  return (baselineProfit.value / baselineRevenue.value) * 100
})

const baselineTeamSize = computed(() => {
  if (!kpis.value) return 0
  return kpis.value.total_employees || 0
})

const baselineDuration = computed(() => {
  if (projects.value.length === 0) return 12
  // Average project duration in months
  let totalMonths = 0
  let count = 0
  for (const p of projects.value) {
    if (p.start_date && p.end_date) {
      const start = new Date(p.start_date)
      const end = new Date(p.end_date)
      const months =
        (end.getFullYear() - start.getFullYear()) * 12 +
        (end.getMonth() - start.getMonth()) +
        1
      totalMonths += months
      count++
    }
  }
  return count > 0 ? Math.max(1, Math.round(totalMonths / count)) : 12
})

// ---- Scenario calculations ----

const scenarioRevenue = computed(() => {
  const growthAdjusted = baselineRevenue.value * (1 + revenueGrowth.value / 100)
  const newProjectRevenue = newProjects.value * avgProjectValue.value
  return growthAdjusted + newProjectRevenue
})

const scenarioCosts = computed(() => {
  const effectiveTeamSize = baselineTeamSize.value > 0 ? baselineTeamSize.value : 1
  const rateMultiplier = 1 + rateChange.value / 100
  const teamMultiplier = (effectiveTeamSize + teamSizeChange.value) / effectiveTeamSize
  const overheadMultiplier = 1 + overheadChange.value / 100
  const effectiveBaseDuration = baselineDuration.value > 0 ? baselineDuration.value : 12
  const durationMultiplier =
    (effectiveBaseDuration + durationChange.value) / effectiveBaseDuration
  const utilizationMultiplier = utilizationTarget.value / 80 // 80% is the baseline target

  let costs = baselineCosts.value
  costs *= rateMultiplier
  costs *= Math.max(0.1, teamMultiplier) // prevent negative
  costs *= overheadMultiplier
  costs *= Math.max(0.1, durationMultiplier)
  costs *= utilizationMultiplier

  return costs
})

const scenarioProfit = computed(() => {
  return scenarioRevenue.value - scenarioCosts.value
})

const scenarioMargin = computed(() => {
  if (scenarioRevenue.value === 0) return 0
  return (scenarioProfit.value / scenarioRevenue.value) * 100
})

// Deltas
const revenueDelta = computed(() => scenarioRevenue.value - baselineRevenue.value)
const costsDelta = computed(() => scenarioCosts.value - baselineCosts.value)
const profitDelta = computed(() => scenarioProfit.value - baselineProfit.value)
const marginDelta = computed(() => scenarioMargin.value - baselineMargin.value)

// Delta colors
function deltaColor(value: number, invertSign = false): string {
  const effective = invertSign ? -value : value
  if (effective > 0) return '#4CAF50'
  if (effective < 0) return '#FF5252'
  return '#757575'
}

// ---- Chart: Revenue vs Cost Projection ----

const revenueCostChartData = computed<Plotly.Data[]>(() => {
  if (!kpis.value) return []

  return [
    {
      type: 'bar' as const,
      name: 'Revenue',
      x: ['Baseline', 'Scenario'],
      y: [baselineRevenue.value, scenarioRevenue.value],
      marker: { color: ['#1976D2', '#42A5F5'] },
      text: [formatCurrencyFull(baselineRevenue.value), formatCurrencyFull(scenarioRevenue.value)],
      textposition: 'outside' as const,
      hoverinfo: 'x+y+name' as const,
    },
    {
      type: 'bar' as const,
      name: 'Costs',
      x: ['Baseline', 'Scenario'],
      y: [baselineCosts.value, scenarioCosts.value],
      marker: { color: ['#E65100', '#FF8A65'] },
      text: [formatCurrencyFull(baselineCosts.value), formatCurrencyFull(scenarioCosts.value)],
      textposition: 'outside' as const,
      hoverinfo: 'x+y+name' as const,
    },
    {
      type: 'scatter' as const,
      name: 'Profit',
      x: ['Baseline', 'Scenario'],
      y: [baselineProfit.value, scenarioProfit.value],
      mode: 'lines+markers' as const,
      line: { color: '#4CAF50', width: 3 },
      marker: { size: 10 },
      yaxis: 'y2',
      hoverinfo: 'x+y+name' as const,
    },
  ]
})

const revenueCostChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  barmode: 'group' as const,
  yaxis: { title: { text: 'Amount ($)' } },
  yaxis2: { title: { text: 'Profit ($)' }, overlaying: 'y' as const, side: 'right' as const },
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.15 },
  hovermode: 'x unified' as const,
}))

// ---- Chart: Monthly Cash Flow ----

const monthlyCashFlowData = computed<Plotly.Data[]>(() => {
  if (!kpis.value) return []

  const months = 12
  const baseMonthlyRevenue = baselineRevenue.value / months
  const baseMonthlyExpense = baselineCosts.value / months
  const scenarioMonthlyRevenue = scenarioRevenue.value / months
  const scenarioMonthlyExpense = scenarioCosts.value / months

  const labels: string[] = []
  const baselineProfit: number[] = []
  const scenarioProfit: number[] = []

  for (let i = 1; i <= months; i++) {
    labels.push(`Month ${i}`)
    baselineProfit.push(baseMonthlyRevenue - baseMonthlyExpense)
    scenarioProfit.push(scenarioMonthlyRevenue - scenarioMonthlyExpense)
  }

  return [
    {
      type: 'scatter' as const,
      name: 'Baseline Profit',
      x: labels,
      y: baselineProfit,
      mode: 'lines+markers' as const,
      line: { color: '#757575', width: 2, dash: 'dash' },
      marker: { size: 6 },
      hoverinfo: 'x+y+name' as const,
    },
    {
      type: 'scatter' as const,
      name: 'Scenario Profit',
      x: labels,
      y: scenarioProfit,
      mode: 'lines+markers' as const,
      line: { color: '#1976D2', width: 2 },
      marker: { size: 6 },
      fill: 'tonexty' as const,
      fillcolor: 'rgba(25, 118, 210, 0.1)',
      hoverinfo: 'x+y+name' as const,
    },
  ]
})

const monthlyCashFlowLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Monthly Profit ($)' } },
  showlegend: true,
  legend: { orientation: 'h' as const, y: 1.15 },
  hovermode: 'x unified' as const,
  shapes: [
    {
      type: 'line' as const,
      x0: 0,
      x1: 1,
      y0: 0,
      y1: 0,
      xref: 'paper' as const,
      line: { color: '#FF5252', dash: 'dot', width: 1 },
    },
  ],
}))

// ---- Chart: Sensitivity / Tornado ----

const sensitivityData = computed<Plotly.Data[]>(() => {
  if (!kpis.value) return []

  // Calculate the profit impact of each variable at its max positive value
  // We measure: "if only this one variable were at its current slider value, what's the profit delta?"
  const variables = [
    {
      label: 'Revenue Growth',
      impact: baselineRevenue.value * (revenueGrowth.value / 100),
    },
    {
      label: 'New Projects',
      impact: newProjects.value * avgProjectValue.value,
    },
    {
      label: 'Hourly Rate Change',
      impact: -baselineCosts.value * (rateChange.value / 100),
    },
    {
      label: 'Team Size Change',
      impact:
        baselineTeamSize.value > 0
          ? -baselineCosts.value * (teamSizeChange.value / baselineTeamSize.value)
          : 0,
    },
    {
      label: 'Overhead Change',
      impact: -baselineCosts.value * (overheadChange.value / 100),
    },
    {
      label: 'Duration Change',
      impact:
        baselineDuration.value > 0
          ? -baselineCosts.value * (durationChange.value / baselineDuration.value)
          : 0,
    },
    {
      label: 'Utilization Target',
      impact: -baselineCosts.value * ((utilizationTarget.value - 80) / 80),
    },
  ]

  // Sort by absolute impact descending
  variables.sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))

  const labels = variables.map((v) => v.label)
  const impacts = variables.map((v) => v.impact)
  const colors = impacts.map((v) => (v >= 0 ? '#4CAF50' : '#FF5252'))

  return [
    {
      type: 'bar' as const,
      y: labels,
      x: impacts,
      orientation: 'h' as const,
      marker: { color: colors },
      text: impacts.map((v) => formatCurrencyFull(Math.round(v))),
      textposition: 'outside' as const,
      hoverinfo: 'y+x' as const,
    },
  ]
})

const sensitivityLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  xaxis: { title: { text: 'Profit Impact ($)' }, zeroline: true },
  yaxis: { automargin: true },
  margin: { l: 150, t: 20, r: 80, b: 40 },
  shapes: [
    {
      type: 'line' as const,
      x0: 0,
      x1: 0,
      y0: -0.5,
      y1: 6.5,
      line: { color: '#757575', width: 1 },
    },
  ],
}))

// ---- Actions ----

function resetSliders() {
  rateChange.value = 0
  teamSizeChange.value = 0
  overheadChange.value = 0
  durationChange.value = 0
  utilizationTarget.value = 80
  revenueGrowth.value = 0
  newProjects.value = 0
  avgProjectValue.value = 100000
}

const savedScenarios = ref<
  Array<{
    name: string
    timestamp: string
    params: Record<string, number>
    results: { revenue: number; costs: number; profit: number; margin: number }
  }>
>([])
const saveDialogOpen = ref(false)
const scenarioName = ref('')

function openSaveDialog() {
  scenarioName.value = `Scenario ${savedScenarios.value.length + 1}`
  saveDialogOpen.value = true
}

function saveScenario() {
  savedScenarios.value.push({
    name: scenarioName.value,
    timestamp: new Date().toLocaleString(),
    params: {
      rateChange: rateChange.value,
      teamSizeChange: teamSizeChange.value,
      overheadChange: overheadChange.value,
      durationChange: durationChange.value,
      utilizationTarget: utilizationTarget.value,
      revenueGrowth: revenueGrowth.value,
      newProjects: newProjects.value,
      avgProjectValue: avgProjectValue.value,
    },
    results: {
      revenue: scenarioRevenue.value,
      costs: scenarioCosts.value,
      profit: scenarioProfit.value,
      margin: scenarioMargin.value,
    },
  })
  saveDialogOpen.value = false
}

function loadScenario(index: number) {
  const s = savedScenarios.value[index]
  if (!s) return
  rateChange.value = s.params.rateChange ?? 0
  teamSizeChange.value = s.params.teamSizeChange ?? 0
  overheadChange.value = s.params.overheadChange ?? 0
  durationChange.value = s.params.durationChange ?? 0
  utilizationTarget.value = s.params.utilizationTarget ?? 80
  revenueGrowth.value = s.params.revenueGrowth ?? 0
  newProjects.value = s.params.newProjects ?? 0
  avgProjectValue.value = s.params.avgProjectValue ?? 100000
}

function removeScenario(index: number) {
  savedScenarios.value.splice(index, 1)
}

// ---- Data loading ----

async function fetchBaseline() {
  loadingBaseline.value = true
  errorMessage.value = null

  try {
    const [kpiData, projectData] = await Promise.all([
      api.get<OverviewKPIs>('/analytics/overview'),
      api.get<Project[]>('/projects/'),
    ])
    kpis.value = kpiData
    projects.value = projectData
  } catch {
    errorMessage.value = 'Failed to load baseline data. Please try again.'
  } finally {
    loadingBaseline.value = false
  }
}

onMounted(() => {
  fetchBaseline()
})
</script>

<template>
  <div>
    <h1 class="text-h4 font-weight-bold mb-1">What-If Scenario Analysis</h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Explore the impact of changes to staffing, costs, and timelines.
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

    <v-row>
      <!-- ====== Left Panel: Controls (4 cols) ====== -->
      <v-col cols="12" md="4">
        <!-- Cost Scenarios -->
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold pb-0">
            <v-icon icon="mdi-cash-multiple" size="20" class="mr-2" />
            Cost Scenarios
          </v-card-title>
          <v-card-text>
            <div class="mb-3">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Hourly Rate Change</span>
                <span class="font-weight-bold" :style="{ color: rateChange !== 0 ? '#1976D2' : undefined }">
                  {{ rateChange >= 0 ? '+' : '' }}{{ rateChange }}%
                </span>
              </div>
              <v-slider
                v-model="rateChange"
                :min="-50"
                :max="50"
                :step="5"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>

            <div class="mb-3">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Team Size Change</span>
                <span class="font-weight-bold" :style="{ color: teamSizeChange !== 0 ? '#1976D2' : undefined }">
                  {{ teamSizeChange >= 0 ? '+' : '' }}{{ teamSizeChange }} people
                </span>
              </div>
              <v-slider
                v-model="teamSizeChange"
                :min="-5"
                :max="10"
                :step="1"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>

            <div>
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Overhead Change</span>
                <span class="font-weight-bold" :style="{ color: overheadChange !== 0 ? '#1976D2' : undefined }">
                  {{ overheadChange >= 0 ? '+' : '' }}{{ overheadChange }}%
                </span>
              </div>
              <v-slider
                v-model="overheadChange"
                :min="-20"
                :max="20"
                :step="5"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>
          </v-card-text>
        </v-card>

        <!-- Timeline Scenarios -->
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold pb-0">
            <v-icon icon="mdi-clock-outline" size="20" class="mr-2" />
            Timeline Scenarios
          </v-card-title>
          <v-card-text>
            <div class="mb-3">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Project Duration Change</span>
                <span class="font-weight-bold" :style="{ color: durationChange !== 0 ? '#1976D2' : undefined }">
                  {{ durationChange >= 0 ? '+' : '' }}{{ durationChange }} months
                </span>
              </div>
              <v-slider
                v-model="durationChange"
                :min="-6"
                :max="12"
                :step="1"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>

            <div>
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Utilization Target</span>
                <span class="font-weight-bold" :style="{ color: utilizationTarget !== 80 ? '#1976D2' : undefined }">
                  {{ utilizationTarget }}%
                </span>
              </div>
              <v-slider
                v-model="utilizationTarget"
                :min="50"
                :max="100"
                :step="5"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>
          </v-card-text>
        </v-card>

        <!-- Revenue Scenarios -->
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold pb-0">
            <v-icon icon="mdi-trending-up" size="20" class="mr-2" />
            Revenue Scenarios
          </v-card-title>
          <v-card-text>
            <div class="mb-3">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Revenue Growth</span>
                <span class="font-weight-bold" :style="{ color: revenueGrowth !== 0 ? '#1976D2' : undefined }">
                  {{ revenueGrowth >= 0 ? '+' : '' }}{{ revenueGrowth }}%
                </span>
              </div>
              <v-slider
                v-model="revenueGrowth"
                :min="-30"
                :max="50"
                :step="5"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>

            <div class="mb-3">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>New Projects</span>
                <span class="font-weight-bold" :style="{ color: newProjects !== 0 ? '#1976D2' : undefined }">
                  {{ newProjects }}
                </span>
              </div>
              <v-slider
                v-model="newProjects"
                :min="0"
                :max="5"
                :step="1"
                color="primary"
                track-color="grey-lighten-3"
                hide-details
                density="compact"
              />
            </div>

            <v-text-field
              v-model.number="avgProjectValue"
              label="Average Project Value"
              type="number"
              prefix="$"
              variant="outlined"
              density="compact"
              hide-details
              :min="0"
            />
          </v-card-text>
        </v-card>

        <!-- Actions -->
        <div class="d-flex gap-2 mb-4">
          <v-btn
            variant="outlined"
            color="grey"
            prepend-icon="mdi-refresh"
            @click="resetSliders"
          >
            Reset
          </v-btn>
          <v-btn
            variant="elevated"
            color="primary"
            prepend-icon="mdi-content-save"
            @click="openSaveDialog"
          >
            Save Scenario
          </v-btn>
        </div>

        <!-- Saved Scenarios -->
        <v-card v-if="savedScenarios.length > 0">
          <v-card-title class="text-subtitle-1 font-weight-bold pb-0">
            <v-icon icon="mdi-bookmark-multiple" size="20" class="mr-2" />
            Saved Scenarios
          </v-card-title>
          <v-card-text>
            <v-list density="compact">
              <v-list-item
                v-for="(s, i) in savedScenarios"
                :key="i"
                @click="loadScenario(i)"
                class="px-0"
              >
                <template #default>
                  <v-list-item-title class="text-body-2 font-weight-medium">
                    {{ s.name }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption">
                    Profit: {{ formatCurrencyFull(s.results.profit) }}
                    ({{ formatPercent(s.results.margin) }})
                  </v-list-item-subtitle>
                </template>
                <template #append>
                  <v-btn
                    icon="mdi-close"
                    size="x-small"
                    variant="text"
                    @click.stop="removeScenario(i)"
                  />
                </template>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- ====== Right Panel: Results (8 cols) ====== -->
      <v-col cols="12" md="8">
        <!-- KPI Impact Row -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" lg="3">
            <KpiCard
              title="Projected Revenue"
              :value="kpis ? formatCurrency(scenarioRevenue) : '--'"
              :subtitle="kpis ? formatDelta(revenueDelta) : undefined"
              icon="mdi-trending-up"
              :color="deltaColor(revenueDelta)"
              :loading="loadingBaseline"
            />
          </v-col>
          <v-col cols="12" sm="6" lg="3">
            <KpiCard
              title="Projected Costs"
              :value="kpis ? formatCurrency(scenarioCosts) : '--'"
              :subtitle="kpis ? formatDelta(costsDelta) : undefined"
              icon="mdi-cash-minus"
              :color="deltaColor(costsDelta, true)"
              :loading="loadingBaseline"
            />
          </v-col>
          <v-col cols="12" sm="6" lg="3">
            <KpiCard
              title="Projected Profit"
              :value="kpis ? formatCurrency(scenarioProfit) : '--'"
              :subtitle="kpis ? formatDelta(profitDelta) : undefined"
              icon="mdi-chart-line"
              :color="deltaColor(profitDelta)"
              :loading="loadingBaseline"
            />
          </v-col>
          <v-col cols="12" sm="6" lg="3">
            <KpiCard
              title="Profit Margin"
              :value="kpis ? formatPercent(scenarioMargin) : '--'"
              :subtitle="kpis ? formatDelta(marginDelta, false) : undefined"
              icon="mdi-percent"
              :color="deltaColor(marginDelta)"
              :loading="loadingBaseline"
            />
          </v-col>
        </v-row>

        <!-- Baseline Reference -->
        <v-alert
          v-if="kpis && !loadingBaseline"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          <strong>Baseline:</strong>
          Revenue {{ formatCurrencyFull(baselineRevenue) }} |
          Costs {{ formatCurrencyFull(baselineCosts) }} |
          Profit {{ formatCurrencyFull(baselineProfit) }}
          ({{ formatPercent(baselineMargin) }})
        </v-alert>

        <!-- Revenue vs Cost Projection -->
        <v-card class="pa-4 mb-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-bar" size="20" class="mr-1" />
            Revenue vs Cost Projection
          </div>
          <PlotlyChart
            :data="revenueCostChartData"
            :layout="revenueCostChartLayout"
            :loading="loadingBaseline"
          />
        </v-card>

        <!-- Monthly Cash Flow -->
        <v-card class="pa-4 mb-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-chart-timeline-variant" size="20" class="mr-1" />
            Monthly Cash Flow Comparison
          </div>
          <PlotlyChart
            :data="monthlyCashFlowData"
            :layout="monthlyCashFlowLayout"
            :loading="loadingBaseline"
          />
        </v-card>

        <!-- Sensitivity / Tornado -->
        <v-card class="pa-4">
          <div class="text-h6 mb-2">
            <v-icon icon="mdi-swap-horizontal" size="20" class="mr-1" />
            Sensitivity Analysis
          </div>
          <p class="text-caption text-medium-emphasis mb-2">
            Shows the individual profit impact of each variable at its current setting.
          </p>
          <PlotlyChart
            :data="sensitivityData"
            :layout="sensitivityLayout"
            :loading="loadingBaseline"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Save Scenario Dialog -->
    <v-dialog v-model="saveDialogOpen" max-width="400">
      <v-card>
        <v-card-title>Save Scenario</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="scenarioName"
            label="Scenario Name"
            variant="outlined"
            density="compact"
            autofocus
            @keyup.enter="saveScenario"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="saveDialogOpen = false">Cancel</v-btn>
          <v-btn color="primary" variant="elevated" @click="saveScenario">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
