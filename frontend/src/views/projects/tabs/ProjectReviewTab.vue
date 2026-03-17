<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { formatCurrency, formatCurrencyFull, formatPercent } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type {
  Allocation,
  ProjectHealthEntry,
  TimeEntry,
  FundingReviewEntry,
  FundingReviewDetailResponse,
} from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const healthData = ref<ProjectHealthEntry | null>(null)
const allocations = ref<Allocation[]>([])
const timeEntries = ref<TimeEntry[]>([])

// Funding review
const fundingReviewData = ref<FundingReviewEntry[]>([])
const fundingLoading = ref(false)
const fundingError = ref<string | null>(null)

// Drill-down dialog
const dialogVisible = ref(false)
const dialogLoading = ref(false)
const dialogDetail = ref<FundingReviewDetailResponse | null>(null)

function healthLabelColor(label: string): string {
  switch (label) {
    case 'Good': return 'success'
    case 'Minor Risk': return 'lime'
    case 'Medium': return 'warning'
    case 'Risk': return 'error'
    default: return 'grey'
  }
}

async function fetchData() {
  try {
    const [healthList, allocationsData, timeData] = await Promise.all([
      get<ProjectHealthEntry[]>('/analytics/health'),
      get<Allocation[]>(`/allocations/?project_id=${encodeURIComponent(projectId.value)}`),
      get<TimeEntry[]>(`/time-entries/?project_id=${encodeURIComponent(projectId.value)}`),
    ])
    healthData.value = healthList.find((h) => h.id === projectId.value) ?? null
    allocations.value = allocationsData
    timeEntries.value = timeData
  } catch {
    // error handled by useApi
  }
}

async function fetchFundingReview() {
  fundingLoading.value = true
  fundingError.value = null
  try {
    fundingReviewData.value = await get<FundingReviewEntry[]>('/analytics/funding-review')
  } catch (err) {
    fundingError.value = 'Failed to load funding review data.'
  } finally {
    fundingLoading.value = false
  }
}

onMounted(() => {
  fetchData()
  fetchFundingReview()
})
watch(projectId, () => {
  fetchData()
  fetchFundingReview()
})

// Health metrics
const healthScore = computed(() => healthData.value?.health_score ?? null)
const budgetHealth = computed(() => healthData.value?.budget_health ?? null)
const scheduleProgress = computed(() => healthData.value?.schedule_progress ?? null)
const profitMargin = computed(() => healthData.value?.profit_margin ?? null)

function healthColor(score: number | null): string {
  if (score == null) return '#9E9E9E'
  if (score >= 70) return '#4CAF50'
  if (score >= 40) return '#FF9800'
  return '#F44336'
}

function healthVuetifyColor(score: number | null): string {
  if (score == null) return 'grey'
  if (score >= 70) return 'success'
  if (score >= 40) return 'warning'
  return 'error'
}

function healthLabel(score: number | null): string {
  if (score == null) return 'N/A'
  if (score >= 70) return 'Healthy'
  if (score >= 40) return 'At Risk'
  return 'Critical'
}

// Performance metrics from time entries
const totalHoursLogged = computed(() => {
  return timeEntries.value.reduce((sum, e) => sum + e.hours, 0)
})

const totalBillableHours = computed(() => {
  return timeEntries.value.reduce((sum, e) => sum + (e.billable ? e.hours : 0), 0)
})

const billableRate = computed(() => {
  return totalHoursLogged.value > 0
    ? (totalBillableHours.value / totalHoursLogged.value) * 100
    : 0
})

const budgetUtilization = computed(() => {
  const quoted = project.value?.quoted_value ?? 0
  const used = project.value?.budget_used ?? 0
  return quoted > 0 ? (used / quoted) * 100 : 0
})

const revenueGenerated = computed(() => project.value?.awarded_value ?? 0)

// Performance summary items for the v-table
const performanceSummary = computed(() => [
  {
    metric: 'Total Hours Logged',
    value: `${totalHoursLogged.value.toFixed(1)} hrs`,
    icon: 'mdi-clock-outline',
  },
  {
    metric: 'Billable Hours',
    value: `${totalBillableHours.value.toFixed(1)} hrs`,
    icon: 'mdi-cash-clock',
  },
  {
    metric: 'Billable Rate',
    value: formatPercent(billableRate.value),
    icon: 'mdi-percent',
  },
  {
    metric: 'Budget Utilization',
    value: formatPercent(budgetUtilization.value),
    icon: 'mdi-chart-donut',
  },
  {
    metric: 'Revenue Generated',
    value: formatCurrencyFull(revenueGenerated.value),
    icon: 'mdi-currency-usd',
  },
])

// Recommendations based on health components
const recommendations = computed(() => {
  const recs: Array<{ type: 'error' | 'warning' | 'info' | 'success'; text: string }> = []

  if (healthScore.value == null) {
    recs.push({
      type: 'info',
      text: 'Health score is not available. Ensure the project has budget and schedule data for accurate health assessment.',
    })
    return recs
  }

  if (budgetHealth.value != null && budgetHealth.value < 50) {
    recs.push({
      type: 'error',
      text: 'Review budget allocation and spending patterns. Budget health is below 50%, indicating potential overspend.',
    })
  }

  if (
    scheduleProgress.value != null &&
    scheduleProgress.value > 90 &&
    budgetUtilization.value < 80
  ) {
    recs.push({
      type: 'warning',
      text: 'Project nearing deadline with budget remaining. Consider accelerating deliverables or reallocating unused funds.',
    })
  }

  if (profitMargin.value != null && profitMargin.value < 20) {
    recs.push({
      type: 'warning',
      text: `Profit margin is at ${profitMargin.value.toFixed(1)}%. Consider reviewing pricing or cost structure to improve margins.`,
    })
  }

  if (profitMargin.value != null && profitMargin.value < 0) {
    recs.push({
      type: 'error',
      text: `Project has a negative profit margin (${profitMargin.value.toFixed(1)}%). Costs exceed revenue - immediate review of billing and expenses recommended.`,
    })
  }

  if (budgetUtilization.value > 90) {
    recs.push({
      type: 'error',
      text: `Budget utilization is at ${budgetUtilization.value.toFixed(1)}%. Consider requesting additional funding or reducing scope.`,
    })
  }

  if (scheduleProgress.value != null && scheduleProgress.value < 40) {
    recs.push({
      type: 'error',
      text: 'Schedule progress is critically low. Review timeline and identify blockers to get back on track.',
    })
  }

  if (healthScore.value >= 70) {
    recs.push({
      type: 'success',
      text: 'Project is healthy - maintain current trajectory. Continue monitoring key metrics to sustain performance.',
    })
  }

  return recs
})

// ---- Funding Review Section ----

// Summary KPIs
const fundingTotalProjects = computed(() => fundingReviewData.value.length)
const fundingCriticalCount = computed(
  () => fundingReviewData.value.filter((e) => e.health_label === 'Risk').length
)
const fundingTotalRemaining = computed(
  () => fundingReviewData.value.reduce((sum, e) => sum + e.remaining, 0)
)
const fundingAvgPct = computed(() => {
  if (fundingReviewData.value.length === 0) return 0
  return (
    fundingReviewData.value.reduce((sum, e) => sum + e.funding_pct, 0) /
    fundingReviewData.value.length
  )
})

// Funding table headers for v-data-table
const fundingHeaders = [
  { title: 'Project Name', key: 'project_name', minWidth: '180px' },
  { title: 'Client', key: 'client', minWidth: '120px' },
  { title: 'PM', key: 'project_manager', minWidth: '120px' },
  { title: 'Status', key: 'status', width: '110px' },
  { title: 'Awarded Value ($)', key: 'awarded_value', align: 'end' as const, width: '150px' },
  { title: 'Budget Used ($)', key: 'budget_used', align: 'end' as const, width: '140px' },
  { title: 'Remaining ($)', key: 'remaining', align: 'end' as const, width: '140px' },
  { title: 'Avg Monthly Invoice ($)', key: 'avg_monthly_invoice', align: 'end' as const, width: '170px' },
  { title: 'Funding Runway (months)', key: 'funding_runway_months', align: 'end' as const, width: '170px' },
  { title: 'Funding %', key: 'funding_pct', align: 'end' as const, width: '130px' },
  { title: 'Health', key: 'health_label', width: '120px' },
  { title: 'Current Month Potential ($)', key: 'current_month_potential', align: 'end' as const, width: '190px' },
]

function onFundingRowClicked(item: FundingReviewEntry) {
  openDrillDown(item.project_id)
}

async function openDrillDown(fundingProjectId: string) {
  dialogVisible.value = true
  dialogLoading.value = true
  dialogDetail.value = null
  try {
    dialogDetail.value = await get<FundingReviewDetailResponse>(
      `/analytics/funding-review/${encodeURIComponent(fundingProjectId)}`
    )
  } catch {
    // error handled by useApi
  } finally {
    dialogLoading.value = false
  }
}

// Plotly data for drill-down dialog
const timelineChartData = computed(() => {
  if (!dialogDetail.value?.monthly_revenue_history?.length) return []
  const history = dialogDetail.value.monthly_revenue_history
  return [
    {
      x: history.map((e) => e.month),
      y: history.map((e) => e.revenue),
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Monthly Revenue',
      line: { color: '#1976D2', width: 2 },
      marker: { size: 6 },
    },
  ]
})

const timelineChartLayout = computed(() => ({
  title: { text: 'Funding Timeline', font: { size: 14 } },
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Revenue ($)' }, tickprefix: '$' },
  height: 300,
}))

const runwayGaugeData = computed(() => {
  if (!dialogDetail.value) return []
  const runway = dialogDetail.value.funding_runway_months ?? 0
  return [
    {
      type: 'indicator' as const,
      mode: 'gauge+number' as const,
      value: runway,
      title: { text: 'Funding Runway (Months)', font: { size: 14 } },
      gauge: {
        axis: { range: [0, Math.max(runway * 1.5, 24)] },
        bar: { color: runway > 6 ? '#4CAF50' : runway > 3 ? '#FF9800' : '#F44336' },
        steps: [
          { range: [0, 3], color: '#FFEBEE' },
          { range: [3, 6], color: '#FFF3E0' },
          { range: [6, Math.max(runway * 1.5, 24)], color: '#E8F5E9' },
        ],
      },
    },
  ]
})

const runwayGaugeLayout = computed(() => ({
  height: 250,
  margin: { t: 40, b: 10, l: 30, r: 30 },
}))
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading" type="card, card, table" />

    <!-- Error -->
    <v-alert v-else-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Content -->
    <template v-else-if="project">
      <!-- Health Score Gauge -->
      <v-card class="mb-4 pa-6">
        <v-row align="center">
          <v-col cols="12" md="4" class="text-center">
            <div class="text-subtitle-1 font-weight-bold text-medium-emphasis mb-4">
              Project Health Score
            </div>
            <v-progress-circular
              :model-value="healthScore ?? 0"
              :size="200"
              :width="15"
              :color="healthVuetifyColor(healthScore)"
            >
              <div class="text-center">
                <div
                  class="text-h3 font-weight-bold"
                  :style="{ color: healthColor(healthScore) }"
                >
                  {{ healthScore != null ? healthScore.toFixed(0) : 'N/A' }}
                </div>
                <div class="text-body-2 text-medium-emphasis mt-1">/ 100</div>
              </div>
            </v-progress-circular>
            <div class="mt-3">
              <v-chip
                :color="healthVuetifyColor(healthScore)"
                variant="tonal"
                size="large"
                label
              >
                {{ healthLabel(healthScore) }}
              </v-chip>
            </div>
            <div class="text-caption text-medium-emphasis mt-2">
              Composite of budget health (30%), schedule progress (30%), and profit margin (40%)
            </div>
          </v-col>

          <!-- Health Breakdown Cards -->
          <v-col cols="12" md="8">
            <v-row>
              <v-col cols="12">
                <v-card variant="outlined" class="pa-4">
                  <div class="d-flex justify-space-between align-center mb-2">
                    <div>
                      <v-icon icon="mdi-cash-check" size="small" class="mr-1" />
                      <span class="text-subtitle-2 font-weight-bold">Budget Health</span>
                      <v-chip size="x-small" variant="text" class="ml-1 text-medium-emphasis">
                        30% weight
                      </v-chip>
                    </div>
                    <span
                      class="text-h6 font-weight-bold"
                      :style="{ color: healthColor(budgetHealth) }"
                    >
                      {{ budgetHealth != null ? budgetHealth.toFixed(1) + '%' : 'N/A' }}
                    </span>
                  </div>
                  <v-progress-linear
                    :model-value="budgetHealth != null ? Math.max(0, Math.min(budgetHealth, 100)) : 0"
                    :color="healthVuetifyColor(budgetHealth)"
                    height="10"
                    rounded
                  />
                  <div class="text-caption text-medium-emphasis mt-1">
                    (Budget Allocated - Budget Used) / Budget Allocated
                  </div>
                </v-card>
              </v-col>

              <v-col cols="12">
                <v-card variant="outlined" class="pa-4">
                  <div class="d-flex justify-space-between align-center mb-2">
                    <div>
                      <v-icon icon="mdi-calendar-check" size="small" class="mr-1" />
                      <span class="text-subtitle-2 font-weight-bold">Schedule Progress</span>
                      <v-chip size="x-small" variant="text" class="ml-1 text-medium-emphasis">
                        30% weight
                      </v-chip>
                    </div>
                    <span
                      class="text-h6 font-weight-bold"
                      :style="{ color: healthColor(scheduleProgress) }"
                    >
                      {{ scheduleProgress != null ? scheduleProgress.toFixed(1) + '%' : 'N/A' }}
                    </span>
                  </div>
                  <v-progress-linear
                    :model-value="scheduleProgress != null ? Math.max(0, Math.min(scheduleProgress, 100)) : 0"
                    :color="healthVuetifyColor(scheduleProgress)"
                    height="10"
                    rounded
                  />
                  <div class="text-caption text-medium-emphasis mt-1">
                    Based on percentage of duration elapsed vs planned
                  </div>
                </v-card>
              </v-col>

              <v-col cols="12">
                <v-card variant="outlined" class="pa-4">
                  <div class="d-flex justify-space-between align-center mb-2">
                    <div>
                      <v-icon icon="mdi-chart-line" size="small" class="mr-1" />
                      <span class="text-subtitle-2 font-weight-bold">Profit Margin</span>
                      <v-chip size="x-small" variant="text" class="ml-1 text-medium-emphasis">
                        40% weight
                      </v-chip>
                    </div>
                    <span
                      class="text-h6 font-weight-bold"
                      :style="{ color: healthColor(profitMargin != null && profitMargin >= 0 ? Math.min(profitMargin * 2, 100) : 0) }"
                    >
                      {{ profitMargin != null ? profitMargin.toFixed(1) + '%' : 'N/A' }}
                    </span>
                  </div>
                  <v-progress-linear
                    :model-value="profitMargin != null ? Math.max(0, Math.min(profitMargin, 100)) : 0"
                    :color="healthVuetifyColor(profitMargin != null && profitMargin >= 0 ? Math.min(profitMargin * 2, 100) : 0)"
                    height="10"
                    rounded
                  />
                  <div class="text-caption text-medium-emphasis mt-1">
                    (Revenue - Costs) / Revenue
                  </div>
                </v-card>
              </v-col>
            </v-row>
          </v-col>
        </v-row>
      </v-card>

      <!-- Performance Summary Table -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Project Performance Summary</div>
        <v-table density="compact">
          <thead>
            <tr>
              <th>Metric</th>
              <th class="text-right">Value</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in performanceSummary" :key="item.metric">
              <td>
                <v-icon :icon="item.icon" size="small" class="mr-2 text-medium-emphasis" />
                {{ item.metric }}
              </td>
              <td class="text-right font-weight-medium">{{ item.value }}</td>
            </tr>
          </tbody>
        </v-table>
        <v-alert
          v-if="timeEntries.length === 0"
          type="info"
          variant="tonal"
          density="compact"
          class="mt-3"
        >
          No time entries recorded for this project. Hours and billable metrics will update once time is logged.
        </v-alert>
      </v-card>

      <!-- Recommendations -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">
          <v-icon icon="mdi-lightbulb-outline" size="small" class="mr-1" />
          Recommendations
        </div>
        <v-alert
          v-for="(rec, idx) in recommendations"
          :key="idx"
          :type="rec.type"
          variant="tonal"
          density="compact"
          class="mb-2"
        >
          {{ rec.text }}
        </v-alert>
        <v-alert
          v-if="recommendations.length === 0"
          type="info"
          variant="tonal"
          density="compact"
        >
          No recommendations available.
        </v-alert>
      </v-card>

      <!-- Funding Review Section -->
      <v-card class="pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-4">
          <v-icon icon="mdi-bank-outline" size="small" class="mr-1" />
          Funding Review - All Projects
        </div>

        <v-skeleton-loader v-if="fundingLoading" type="card, table" />

        <v-alert v-else-if="fundingError" type="error" variant="tonal" density="compact" class="mb-4">
          {{ fundingError }}
        </v-alert>

        <template v-else>
          <!-- Summary KPIs -->
          <v-row class="mb-4">
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Total Projects"
                :value="String(fundingTotalProjects)"
                icon="mdi-folder-multiple-outline"
                color="#1976D2"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Critical"
                :value="String(fundingCriticalCount)"
                icon="mdi-alert-circle-outline"
                :color="fundingCriticalCount > 0 ? '#F44336' : '#4CAF50'"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Total Remaining Funding"
                :value="formatCurrency(fundingTotalRemaining)"
                icon="mdi-cash-multiple"
                color="#2E7D32"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Avg Funding %"
                :value="formatPercent(fundingAvgPct)"
                icon="mdi-percent-outline"
                :color="fundingAvgPct >= 50 ? '#4CAF50' : fundingAvgPct >= 30 ? '#FF9800' : '#F44336'"
              />
            </v-col>
          </v-row>

          <!-- Funding Table -->
          <v-data-table
            :headers="fundingHeaders"
            :items="fundingReviewData"
            :items-per-page="20"
            density="compact"
            hover
            class="cursor-pointer"
            @click:row="(_e: Event, { item }: { item: FundingReviewEntry }) => onFundingRowClicked(item)"
          >
            <template #item.awarded_value="{ value }">
              {{ value != null ? formatCurrencyFull(value) : '' }}
            </template>
            <template #item.budget_used="{ value }">
              {{ value != null ? formatCurrencyFull(value) : '' }}
            </template>
            <template #item.remaining="{ value }">
              {{ value != null ? formatCurrencyFull(value) : '' }}
            </template>
            <template #item.avg_monthly_invoice="{ value }">
              {{ value != null ? formatCurrencyFull(value) : '' }}
            </template>
            <template #item.funding_runway_months="{ value }">
              {{ value != null ? value.toFixed(1) : 'N/A' }}
            </template>
            <template #item.funding_pct="{ value }">
              <v-chip
                v-if="value != null"
                :color="value >= 50 ? 'success' : value >= 30 ? 'warning' : value >= 10 ? 'orange' : 'error'"
                size="x-small"
                label
                variant="tonal"
              >
                {{ value.toFixed(1) }}%
              </v-chip>
            </template>
            <template #item.health_label="{ item }">
              <v-chip
                v-if="item.health_label"
                :color="healthLabelColor(item.health_label)"
                size="small"
                label
                variant="tonal"
              >
                {{ item.health_label }}
              </v-chip>
            </template>
            <template #item.current_month_potential="{ value }">
              {{ value != null ? formatCurrencyFull(value) : '' }}
            </template>
          </v-data-table>

          <div class="text-caption text-medium-emphasis mt-2">
            Click a row to view detailed funding breakdown for that project.
          </div>
        </template>
      </v-card>
    </template>

    <!-- Drill-down Dialog -->
    <v-dialog v-model="dialogVisible" max-width="800" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-bank-outline" class="mr-2" />
          {{ dialogDetail?.project_name ?? 'Project Funding Detail' }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="dialogVisible = false" />
        </v-card-title>

        <v-card-text>
          <v-skeleton-loader v-if="dialogLoading" type="card, image, image" />

          <template v-else-if="dialogDetail">
            <!-- KPI Cards -->
            <v-row class="mb-4">
              <v-col cols="12" sm="4">
                <KpiCard
                  title="Past Month Revenue"
                  :value="formatCurrencyFull(dialogDetail.past_month_revenue)"
                  icon="mdi-calendar-month-outline"
                  color="#1976D2"
                />
              </v-col>
              <v-col cols="12" sm="4">
                <KpiCard
                  title="Avg Monthly Invoice"
                  :value="formatCurrencyFull(dialogDetail.avg_monthly_invoice)"
                  icon="mdi-receipt-text-outline"
                  color="#7B1FA2"
                />
              </v-col>
              <v-col cols="12" sm="4">
                <KpiCard
                  title="Current Month Potential"
                  :value="formatCurrencyFull(dialogDetail.current_month_potential)"
                  icon="mdi-trending-up"
                  color="#2E7D32"
                />
              </v-col>
            </v-row>

            <!-- Funding Timeline Chart -->
            <v-card variant="outlined" class="mb-4 pa-3">
              <PlotlyChart
                :data="timelineChartData"
                :layout="timelineChartLayout"
                :loading="false"
              />
            </v-card>

            <!-- Funding Runway Gauge -->
            <v-card variant="outlined" class="pa-3">
              <PlotlyChart
                :data="runwayGaugeData"
                :layout="runwayGaugeLayout"
                :loading="false"
              />
            </v-card>
          </template>

          <v-alert v-else type="info" variant="tonal">
            No detail data available.
          </v-alert>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>
