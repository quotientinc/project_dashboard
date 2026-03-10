<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import type { Allocation, ProjectHealthEntry } from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const allocations = ref<Allocation[]>([])
const healthData = ref<ProjectHealthEntry | null>(null)

async function fetchData() {
  try {
    const [allocationsData, healthList] = await Promise.all([
      get<Allocation[]>(`/allocations/?project_id=${encodeURIComponent(projectId.value)}`),
      get<ProjectHealthEntry[]>('/analytics/health'),
    ])
    allocations.value = allocationsData
    healthData.value = healthList.find((h) => h.id === projectId.value) ?? null
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchData)
watch(projectId, fetchData)

// Computed metrics
const budgetAllocated = computed(() => project.value?.quoted_value ?? 0)
const budgetUsed = computed(() => project.value?.budget_used ?? 0)
const revenue = computed(() => project.value?.awarded_value ?? 0)
const profitMargin = computed(() => {
  if (!healthData.value) return null
  return healthData.value.profit_margin
})
const healthScore = computed(() => healthData.value?.health_score ?? null)
const budgetRemaining = computed(() => budgetAllocated.value - budgetUsed.value)
const budgetPct = computed(() =>
  budgetAllocated.value > 0 ? (budgetUsed.value / budgetAllocated.value) * 100 : 0
)

function formatCurrency(value: number | null | undefined): string {
  if (value == null) return '-'
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function healthColor(score: number | null): string {
  if (score == null) return 'grey'
  if (score >= 70) return 'success'
  if (score >= 40) return 'warning'
  return 'error'
}

function budgetStatusColor(pct: number): string {
  if (pct > 100) return 'error'
  if (pct >= 80) return 'warning'
  return 'success'
}

const allocationCoverageWarning = computed(() => {
  if (!project.value?.start_date || !project.value?.end_date || allocations.value.length === 0) return null

  const projectStart = new Date(project.value.start_date)
  const projectEnd = new Date(project.value.end_date)

  const allocDates = allocations.value
    .map(a => new Date(a.allocation_date))
    .filter(d => !isNaN(d.getTime()))

  if (allocDates.length === 0) return null

  const minAlloc = new Date(Math.min(...allocDates.map(d => d.getTime())))
  const maxAlloc = new Date(Math.max(...allocDates.map(d => d.getTime())))

  const warnings: string[] = []

  // Count missing months at start
  if (minAlloc > projectStart) {
    const startMonths = (minAlloc.getFullYear() - projectStart.getFullYear()) * 12 + (minAlloc.getMonth() - projectStart.getMonth())
    if (startMonths > 0) {
      warnings.push(`Missing ${startMonths} month${startMonths > 1 ? 's' : ''} at start`)
    }
  }

  // Count missing months at end
  if (maxAlloc < projectEnd) {
    const endMonths = (projectEnd.getFullYear() - maxAlloc.getFullYear()) * 12 + (projectEnd.getMonth() - maxAlloc.getMonth())
    if (endMonths > 0) {
      warnings.push(`Missing ${endMonths} month${endMonths > 1 ? 's' : ''} at end`)
    }
  }

  if (warnings.length === 0) return null

  const formatMonth = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  return `Allocation data only exists for ${formatMonth(minAlloc)} to ${formatMonth(maxAlloc)}. ${warnings.join(', ')}.`
})

// Team allocation table
const teamHeaders = [
  { title: 'Employee', key: 'employee_name' },
  { title: 'Role', key: 'role' },
  { title: 'FTE Allocation', key: 'allocated_fte' },
  { title: 'Bill Rate', key: 'bill_rate' },
  { title: 'Month', key: 'allocation_date' },
]
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
      <!-- KPI Cards -->
      <v-row class="mb-4">
        <v-col cols="12" sm="6" md="4" lg="2">
          <v-card class="pa-4 text-center">
            <div class="text-caption text-medium-emphasis">Quoted Value</div>
            <div class="text-h6 font-weight-bold">{{ formatCurrency(budgetAllocated) }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="4" lg="2">
          <v-card class="pa-4 text-center">
            <div class="text-caption text-medium-emphasis">Budget Used</div>
            <div class="text-h6 font-weight-bold">{{ formatCurrency(budgetUsed) }}</div>
            <v-progress-linear
              :model-value="budgetPct"
              :color="budgetStatusColor(budgetPct)"
              height="4"
              class="mt-2"
            />
            <div class="text-caption mt-1">{{ budgetPct.toFixed(1) }}% used</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="4" lg="2">
          <v-card class="pa-4 text-center">
            <div class="text-caption text-medium-emphasis">Awarded Value</div>
            <div class="text-h6 font-weight-bold">{{ formatCurrency(revenue) }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="4" lg="2">
          <v-card class="pa-4 text-center">
            <div class="text-caption text-medium-emphasis">Budget Remaining</div>
            <div class="text-h6 font-weight-bold" :class="budgetRemaining < 0 ? 'text-error' : 'text-success'">
              {{ formatCurrency(budgetRemaining) }}
            </div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="4" lg="2">
          <v-card class="pa-4 text-center">
            <div class="text-caption text-medium-emphasis">Profit Margin</div>
            <div class="text-h6 font-weight-bold">
              {{ profitMargin != null ? profitMargin.toFixed(1) + '%' : 'N/A' }}
            </div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="4" lg="2">
          <v-card class="pa-4 text-center">
            <div class="text-caption text-medium-emphasis">Health Score</div>
            <div class="text-h6 font-weight-bold">
              <v-chip
                v-if="healthScore != null"
                :color="healthColor(healthScore)"
                size="small"
                label
              >
                {{ healthScore.toFixed(0) }}
              </v-chip>
              <span v-else class="text-medium-emphasis">N/A</span>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Allocation Coverage Warning -->
      <v-alert
        v-if="allocationCoverageWarning"
        type="warning"
        variant="tonal"
        class="mb-4"
        density="compact"
        icon="mdi-calendar-alert"
      >
        {{ allocationCoverageWarning }}
      </v-alert>

      <!-- Project Description -->
      <v-card v-if="project.description" class="mb-4 pa-4">
        <div class="text-subtitle-2 text-medium-emphasis mb-1">Description</div>
        <div class="text-body-2">{{ project.description }}</div>
      </v-card>

      <!-- Project Info and Dates -->
      <v-row class="mb-4">
        <v-col cols="12" md="6">
          <v-card class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-3">Project Details</div>
            <v-table density="compact">
              <tbody>
                <tr>
                  <td class="text-medium-emphasis">Project Code</td>
                  <td>{{ project.id }}</td>
                </tr>
                <tr>
                  <td class="text-medium-emphasis">Client</td>
                  <td>{{ project.client ?? 'N/A' }}</td>
                </tr>
                <tr>
                  <td class="text-medium-emphasis">Project Manager</td>
                  <td>{{ project.project_manager ?? 'N/A' }}</td>
                </tr>
                <tr>
                  <td class="text-medium-emphasis">Status</td>
                  <td>{{ project.status ?? 'N/A' }}</td>
                </tr>
                <tr>
                  <td class="text-medium-emphasis">Billable</td>
                  <td>{{ project.billable ? 'Yes' : 'No' }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
        </v-col>
        <v-col cols="12" md="6">
          <v-card class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-3">Schedule</div>
            <v-table density="compact">
              <tbody>
                <tr>
                  <td class="text-medium-emphasis">Start Date</td>
                  <td>{{ project.start_date ?? 'N/A' }}</td>
                </tr>
                <tr>
                  <td class="text-medium-emphasis">End Date</td>
                  <td>{{ project.end_date ?? 'N/A' }}</td>
                </tr>
                <tr v-if="project.start_date && project.end_date">
                  <td class="text-medium-emphasis">Duration</td>
                  <td>
                    {{
                      Math.round(
                        (new Date(project.end_date).getTime() -
                          new Date(project.start_date).getTime()) /
                          (1000 * 60 * 60 * 24)
                      )
                    }}
                    days
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
        </v-col>
      </v-row>

      <!-- Team Allocations Table -->
      <v-card class="pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Team Allocations</div>
        <v-data-table
          v-if="allocations.length > 0"
          :headers="teamHeaders"
          :items="allocations"
          density="compact"
          :items-per-page="10"
        >
          <template #item.allocated_fte="{ item }">
            {{ (item.allocated_fte * 100).toFixed(0) }}%
          </template>
          <template #item.bill_rate="{ item }">
            {{ item.bill_rate != null ? formatCurrency(item.bill_rate) + '/hr' : '-' }}
          </template>
          <template #item.employee_name="{ item }">
            <router-link
              v-if="item.employee_id"
              :to="`/employees/${item.employee_id}`"
              class="text-primary text-decoration-none"
            >
              {{ item.employee_name ?? 'Unknown' }}
            </router-link>
            <span v-else>{{ item.employee_name ?? 'Unknown' }}</span>
          </template>
        </v-data-table>
        <v-alert v-else type="info" variant="tonal" density="compact">
          No team members allocated to this project.
        </v-alert>
      </v-card>
    </template>
  </div>
</template>
