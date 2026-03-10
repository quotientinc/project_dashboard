<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { formatCurrencyFull } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { Expense, BurnRateEntry } from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const expenses = ref<Expense[]>([])
const burnRateData = ref<BurnRateEntry[]>([])

async function fetchData() {
  try {
    const [expensesData, burnData] = await Promise.all([
      get<Expense[]>(`/expenses/?project_id=${encodeURIComponent(projectId.value)}`),
      get<BurnRateEntry[]>(`/analytics/burn-rate?project_id=${encodeURIComponent(projectId.value)}`),
    ])
    expenses.value = expensesData
    burnRateData.value = burnData
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchData)
watch(projectId, fetchData)

// Budget KPIs
const quotedValue = computed(() => project.value?.quoted_value ?? 0)
const awardedValue = computed(() => project.value?.awarded_value ?? 0)
const budgetUsed = computed(() => project.value?.budget_used ?? 0)
const budgetRemaining = computed(() => quotedValue.value - budgetUsed.value)
const budgetPct = computed(() =>
  quotedValue.value > 0 ? (budgetUsed.value / quotedValue.value) * 100 : 0
)

function budgetBarColor(pct: number): string {
  if (pct > 100) return 'error'
  if (pct >= 80) return 'warning'
  return 'success'
}

function remainingColor(): string {
  return budgetRemaining.value < 0 ? '#F44336' : '#4CAF50'
}

// Burn rate chart data
const burnChartData = computed<Plotly.Data[]>(() => {
  if (burnRateData.value.length === 0) return []
  return [
    {
      x: burnRateData.value.map((d) => d.period),
      y: burnRateData.value.map((d) => d.total_amount),
      type: 'bar' as const,
      name: 'Monthly Spend',
      marker: { color: '#1976D2' },
    },
    {
      x: burnRateData.value.map((d) => d.period),
      y: burnRateData.value.map((d) => d.cumulative_amount),
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Cumulative',
      yaxis: 'y2',
      line: { color: '#FF9800', width: 2 },
      marker: { size: 5 },
    },
  ]
})

const burnChartLayout = computed<Partial<Plotly.Layout>>(() => ({
  xaxis: { title: { text: 'Period' } },
  yaxis: { title: { text: 'Monthly Spend ($)' } },
  yaxis2: {
    title: { text: 'Cumulative ($)' },
    overlaying: 'y' as const,
    side: 'right' as const,
  },
  legend: { orientation: 'h' as const, y: -0.2 },
  height: 350,
}))

// Expenses table
const expenseHeaders = [
  { title: 'Date', key: 'date' },
  { title: 'Category', key: 'category' },
  { title: 'Amount', key: 'amount' },
  { title: 'Description', key: 'description' },
  { title: 'Approved', key: 'approved' },
]

// --- Expense Category Analysis ---
interface CategorySummary {
  category: string
  total_amount: number
  pct_of_total: number
}

const categoryAnalysis = computed<CategorySummary[]>(() => {
  if (expenses.value.length === 0) return []

  const catMap = new Map<string, number>()
  let grandTotal = 0

  for (const exp of expenses.value) {
    const cat = exp.category ?? 'Uncategorized'
    catMap.set(cat, (catMap.get(cat) ?? 0) + exp.amount)
    grandTotal += exp.amount
  }

  return Array.from(catMap.entries())
    .map(([category, total_amount]) => ({
      category,
      total_amount,
      pct_of_total: grandTotal > 0 ? (total_amount / grandTotal) * 100 : 0,
    }))
    .sort((a, b) => b.total_amount - a.total_amount)
})

const categorySummaryHeaders = [
  { title: 'Category', key: 'category' },
  { title: 'Total Amount', key: 'total_amount', align: 'end' as const },
  { title: '% of Total', key: 'pct_of_total', align: 'end' as const },
]

const categoryPieData = computed<Plotly.Data[]>(() => {
  if (categoryAnalysis.value.length === 0) return []
  return [
    {
      labels: categoryAnalysis.value.map((c) => c.category),
      values: categoryAnalysis.value.map((c) => c.total_amount),
      type: 'pie' as const,
      textinfo: 'label+percent' as const,
      hovertemplate: '%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>',
    },
  ]
})

const categoryPieLayout = computed<Partial<Plotly.Layout>>(() => ({
  height: 350,
  showlegend: true,
  legend: { orientation: 'h' as const, y: -0.1 },
}))
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading" type="card, card, image, table" />

    <!-- Error -->
    <v-alert v-else-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Content -->
    <template v-else-if="project">
      <!-- Budget KPI Cards -->
      <v-row class="mb-4">
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Quoted Value"
            :value="formatCurrencyFull(quotedValue)"
            icon="mdi-file-document-outline"
            color="#1976D2"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Awarded Value"
            :value="formatCurrencyFull(awardedValue)"
            icon="mdi-trophy-outline"
            color="#7B1FA2"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Budget Used"
            :value="formatCurrencyFull(budgetUsed)"
            icon="mdi-cash-minus"
            color="#FF9800"
            :subtitle="`${budgetPct.toFixed(1)}% of quoted value`"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Budget Remaining"
            :value="formatCurrencyFull(budgetRemaining)"
            icon="mdi-cash-plus"
            :color="remainingColor()"
            :subtitle="budgetRemaining < 0 ? 'Over budget' : 'Under budget'"
          />
        </v-col>
      </v-row>

      <!-- Budget Utilization Progress Bar -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Budget Utilization</div>
        <div class="d-flex justify-space-between text-body-2 mb-1">
          <span>{{ formatCurrencyFull(budgetUsed) }} used</span>
          <span>{{ formatCurrencyFull(quotedValue) }} total</span>
        </div>
        <v-progress-linear
          :model-value="Math.min(budgetPct, 100)"
          :color="budgetBarColor(budgetPct)"
          height="24"
          rounded
        >
          <template #default>
            <strong class="text-white">{{ budgetPct.toFixed(1) }}%</strong>
          </template>
        </v-progress-linear>
        <v-alert
          v-if="budgetPct > 100"
          type="error"
          variant="tonal"
          density="compact"
          class="mt-3"
        >
          Budget exceeded by {{ formatCurrencyFull(Math.abs(budgetRemaining)) }}
          ({{ (budgetPct - 100).toFixed(1) }}% over)
        </v-alert>
      </v-card>

      <!-- Monthly Burn Rate Chart -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Monthly Burn Rate</div>
        <PlotlyChart
          :data="burnChartData"
          :layout="burnChartLayout"
          :loading="loading"
        />
        <v-alert
          v-if="burnRateData.length === 0 && !loading"
          type="info"
          variant="tonal"
          density="compact"
          class="mt-2"
        >
          No expense data available to display burn rate.
        </v-alert>
      </v-card>

      <!-- Expenses Table -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Expenses</div>
        <v-data-table
          v-if="expenses.length > 0"
          :headers="expenseHeaders"
          :items="expenses"
          density="compact"
          :items-per-page="15"
          :sort-by="[{ key: 'date', order: 'desc' }]"
        >
          <template #item.amount="{ item }">
            {{ formatCurrencyFull(item.amount) }}
          </template>
          <template #item.category="{ item }">
            <v-chip size="small" variant="tonal" label>
              {{ item.category ?? 'Uncategorized' }}
            </v-chip>
          </template>
          <template #item.description="{ item }">
            {{ item.description ?? '-' }}
          </template>
          <template #item.approved="{ item }">
            <v-icon
              :icon="item.approved ? 'mdi-check-circle' : 'mdi-clock-outline'"
              :color="item.approved ? 'success' : 'grey'"
              size="small"
            />
          </template>
        </v-data-table>
        <v-alert v-else type="info" variant="tonal" density="compact">
          No expenses recorded for this project.
        </v-alert>
      </v-card>

      <!-- Expense Category Analysis -->
      <v-card class="pa-4" v-if="categoryAnalysis.length > 0">
        <div class="text-subtitle-1 font-weight-bold mb-3">Expense Category Analysis</div>
        <v-row>
          <v-col cols="12" md="6">
            <v-data-table
              :headers="categorySummaryHeaders"
              :items="categoryAnalysis"
              density="compact"
              :items-per-page="-1"
              hide-default-footer
            >
              <template #item.category="{ item }">
                <v-chip size="small" variant="tonal" label>
                  {{ item.category }}
                </v-chip>
              </template>
              <template #item.total_amount="{ item }">
                {{ formatCurrencyFull(item.total_amount) }}
              </template>
              <template #item.pct_of_total="{ item }">
                {{ item.pct_of_total.toFixed(1) }}%
              </template>
            </v-data-table>
          </v-col>
          <v-col cols="12" md="6">
            <PlotlyChart
              :data="categoryPieData"
              :layout="categoryPieLayout"
              :loading="loading"
            />
          </v-col>
        </v-row>
      </v-card>
    </template>
  </div>
</template>
