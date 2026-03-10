<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import PlotlyChart from '@/components/PlotlyChart.vue'
import KpiCard from '@/components/KpiCard.vue'
import type { Allocation } from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const allocations = ref<Allocation[]>([])

async function fetchData() {
  try {
    const allocationsData = await get<Allocation[]>(`/allocations/?project_id=${encodeURIComponent(projectId.value)}`)
    allocations.value = allocationsData
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchData)
watch(projectId, fetchData)

// Duration computations
const startDate = computed(() => project.value?.start_date ?? null)
const endDate = computed(() => project.value?.end_date ?? null)

const durationDays = computed(() => {
  if (!startDate.value || !endDate.value) return null
  const diff = new Date(endDate.value).getTime() - new Date(startDate.value).getTime()
  return Math.round(diff / (1000 * 60 * 60 * 24))
})

const daysRemaining = computed(() => {
  if (!endDate.value) return null
  const diff = new Date(endDate.value).getTime() - new Date().getTime()
  return Math.round(diff / (1000 * 60 * 60 * 24))
})

const daysElapsed = computed(() => {
  if (!startDate.value) return null
  const diff = new Date().getTime() - new Date(startDate.value).getTime()
  return Math.max(0, Math.round(diff / (1000 * 60 * 60 * 24)))
})

const progressPct = computed(() => {
  if (!durationDays.value || durationDays.value <= 0 || !daysElapsed.value) return 0
  return Math.min(100, (daysElapsed.value / durationDays.value) * 100)
})

function progressColor(pct: number): string {
  if (pct >= 100) return 'error'
  if (pct >= 80) return 'warning'
  return 'primary'
}

// Group allocations by employee for the Gantt chart
interface EmployeeTimeline {
  employee_id: number
  employee_name: string
  role: string | null
  months: string[]
  ftes: number[]
}

const employeeTimelines = computed<EmployeeTimeline[]>(() => {
  const map = new Map<number, EmployeeTimeline>()

  for (const alloc of allocations.value) {
    const existing = map.get(alloc.employee_id)
    if (existing) {
      existing.months.push(alloc.allocation_date)
      existing.ftes.push(alloc.allocated_fte)
    } else {
      map.set(alloc.employee_id, {
        employee_id: alloc.employee_id,
        employee_name: alloc.employee_name ?? 'Unknown',
        role: alloc.role,
        months: [alloc.allocation_date],
        ftes: [alloc.allocated_fte],
      })
    }
  }

  return Array.from(map.values())
})

// Gantt-style horizontal bar chart
const ganttChartData = computed<Plotly.Data[]>(() => {
  if (employeeTimelines.value.length === 0) return []

  const traces: Plotly.Data[] = []

  for (const emp of employeeTimelines.value) {
    // Sort months
    const sorted = emp.months
      .map((m, i) => ({ month: m, fte: emp.ftes[i] }))
      .sort((a, b) => a.month.localeCompare(b.month))

    if (sorted.length === 0) continue

    // Each employee gets a bar from first to last allocation month
    const firstMonth = sorted[0]!.month
    const lastMonth = sorted[sorted.length - 1]!.month

    // Create start/end dates for the bar (first day of first month to last day of last month)
    const barStart = firstMonth + '-01'
    const lastDate = new Date(lastMonth + '-01')
    lastDate.setMonth(lastDate.getMonth() + 1)
    lastDate.setDate(lastDate.getDate() - 1)
    const barEnd = lastDate.toISOString().split('T')[0]

    const avgFte = sorted.reduce((sum, s) => sum + (s.fte ?? 0), 0) / sorted.length
    const label = `${emp.employee_name}${emp.role ? ' (' + emp.role + ')' : ''}`

    traces.push({
      x: [barStart, barEnd] as Plotly.Datum[],
      y: [label, label] as Plotly.Datum[],
      type: 'scatter' as const,
      mode: 'lines' as const,
      line: { width: 16 },
      name: emp.employee_name,
      hovertemplate:
        `<b>${emp.employee_name}</b><br>` +
        `${firstMonth} to ${lastMonth}<br>` +
        `Avg FTE: ${(avgFte * 100).toFixed(0)}%<br>` +
        `Months: ${sorted.length}<extra></extra>`,
      showlegend: false,
    })
  }

  return traces
})

const ganttChartLayout = computed<Partial<Plotly.Layout>>(() => {
  const numEmployees = employeeTimelines.value.length
  const chartHeight = Math.max(200, numEmployees * 40 + 80)

  return {
    xaxis: {
      title: { text: 'Timeline' },
      type: 'date' as const,
    },
    yaxis: {
      automargin: true,
    },
    height: chartHeight,
    showlegend: false,
    // Add project start/end date markers if available
    shapes: [
      ...(startDate.value
        ? [
            {
              type: 'line' as const,
              x0: startDate.value,
              x1: startDate.value,
              y0: 0,
              y1: 1,
              yref: 'paper' as const,
              line: { color: '#4CAF50', width: 2, dash: 'dash' as const },
            },
          ]
        : []),
      ...(endDate.value
        ? [
            {
              type: 'line' as const,
              x0: endDate.value,
              x1: endDate.value,
              y0: 0,
              y1: 1,
              yref: 'paper' as const,
              line: { color: '#F44336', width: 2, dash: 'dash' as const },
            },
          ]
        : []),
    ],
  }
})
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading" type="card, card, image" />

    <!-- Error -->
    <v-alert v-else-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Content -->
    <template v-else-if="project">
      <!-- Project Duration Info -->
      <v-row class="mb-4">
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Start Date"
            :value="startDate ?? 'Not set'"
            icon="mdi-calendar-start"
            color="#4CAF50"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="End Date"
            :value="endDate ?? 'Not set'"
            icon="mdi-calendar-end"
            color="#F44336"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Duration"
            :value="durationDays != null ? `${durationDays} days` : 'N/A'"
            icon="mdi-calendar-range"
            color="#1976D2"
            :subtitle="daysElapsed != null ? `${daysElapsed} days elapsed` : undefined"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <KpiCard
            title="Days Remaining"
            :value="daysRemaining != null ? `${daysRemaining} days` : 'N/A'"
            icon="mdi-timer-sand"
            :color="daysRemaining != null && daysRemaining < 0 ? '#F44336' : '#FF9800'"
            :subtitle="daysRemaining != null && daysRemaining < 0 ? 'Past due' : undefined"
          />
        </v-col>
      </v-row>

      <!-- Schedule Progress Bar -->
      <v-card v-if="durationDays" class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Schedule Progress</div>
        <div class="d-flex justify-space-between text-body-2 mb-1">
          <span>{{ startDate }}</span>
          <span>{{ endDate }}</span>
        </div>
        <v-progress-linear
          :model-value="progressPct"
          :color="progressColor(progressPct)"
          height="20"
          rounded
        >
          <template #default>
            <strong>{{ progressPct.toFixed(0) }}%</strong>
          </template>
        </v-progress-linear>
      </v-card>

      <!-- Team Timeline (Gantt Chart) -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Team Timeline</div>
        <PlotlyChart
          v-if="employeeTimelines.length > 0"
          :data="ganttChartData"
          :layout="ganttChartLayout"
          :loading="loading"
        />
        <v-alert
          v-else
          type="info"
          variant="tonal"
          density="compact"
        >
          No team allocations to display in the timeline.
        </v-alert>
      </v-card>

      <!-- Team Allocation Summary Table -->
      <v-card class="pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Team Allocation Details</div>
        <v-data-table
          v-if="allocations.length > 0"
          :headers="[
            { title: 'Employee', key: 'employee_name' },
            { title: 'Role', key: 'role' },
            { title: 'Month', key: 'allocation_date' },
            { title: 'FTE Allocation', key: 'allocated_fte' },
          ]"
          :items="allocations"
          density="compact"
          :items-per-page="15"
          :sort-by="[{ key: 'allocation_date', order: 'asc' }]"
        >
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
          <template #item.allocated_fte="{ item }">
            {{ (item.allocated_fte * 100).toFixed(0) }}%
          </template>
          <template #item.role="{ item }">
            {{ item.role ?? '-' }}
          </template>
        </v-data-table>
        <v-alert v-else type="info" variant="tonal" density="compact">
          No allocations recorded for this project.
        </v-alert>
      </v-card>
    </template>
  </div>
</template>
