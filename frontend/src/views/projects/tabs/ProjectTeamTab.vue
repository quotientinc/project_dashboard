<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { Allocation, TimeEntry } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const route = useRoute()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)
const allocations = ref<Allocation[]>([])
const timeEntries = ref<TimeEntry[]>([])

const STANDARD_MONTHLY_HOURS = 160

async function fetchData() {
  try {
    const [allocData, timeData] = await Promise.all([
      get<Allocation[]>(`/allocations/?project_id=${encodeURIComponent(projectId.value)}`),
      get<TimeEntry[]>(`/time-entries/?project_id=${encodeURIComponent(projectId.value)}`),
    ])
    allocations.value = allocData
    timeEntries.value = timeData
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchData)
watch(projectId, fetchData)

// Group allocations by employee for summary view
const employeeSummary = computed(() => {
  const map = new Map<
    number,
    {
      employee_id: number
      employee_name: string
      role: string | null
      months: number
      avg_fte: number
      total_fte: number
    }
  >()

  for (const alloc of allocations.value) {
    const existing = map.get(alloc.employee_id)
    if (existing) {
      existing.months++
      existing.total_fte += alloc.allocated_fte
      existing.avg_fte = existing.total_fte / existing.months
    } else {
      map.set(alloc.employee_id, {
        employee_id: alloc.employee_id,
        employee_name: alloc.employee_name ?? 'Unknown',
        role: alloc.role,
        months: 1,
        avg_fte: alloc.allocated_fte,
        total_fte: alloc.allocated_fte,
      })
    }
  }

  return Array.from(map.values())
})

const summaryHeaders = [
  { title: 'Employee', key: 'employee_name' },
  { title: 'Role', key: 'role' },
  { title: 'Avg Allocation', key: 'avg_fte' },
  { title: 'Months Allocated', key: 'months' },
]

const detailHeaders = [
  { title: 'Employee', key: 'employee_name' },
  { title: 'Role', key: 'role' },
  { title: 'Month', key: 'allocation_date' },
  { title: 'FTE Allocation', key: 'allocated_fte' },
  { title: 'Bill Rate', key: 'bill_rate' },
  { title: 'Effective Rate', key: 'effective_rate' },
]

function formatCurrency(value: number | null | undefined): string {
  if (value == null) return '-'
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// --- Per-Employee Monthly Breakdown ---

// Collect all unique months from allocations and time entries
const allMonths = computed(() => {
  const monthSet = new Set<string>()
  for (const alloc of allocations.value) {
    if (alloc.allocation_date) {
      monthSet.add(alloc.allocation_date.substring(0, 7)) // YYYY-MM
    }
  }
  for (const entry of timeEntries.value) {
    if (entry.date) {
      monthSet.add(entry.date.substring(0, 7))
    }
  }
  return Array.from(monthSet).sort()
})

// Collect all unique employees
const allEmployees = computed(() => {
  const empMap = new Map<number, string>()
  for (const alloc of allocations.value) {
    empMap.set(alloc.employee_id, alloc.employee_name ?? 'Unknown')
  }
  for (const entry of timeEntries.value) {
    empMap.set(entry.employee_id, entry.employee_name ?? 'Unknown')
  }
  return Array.from(empMap.entries()).map(([id, name]) => ({ id, name }))
})

interface MonthlyBreakdownRow {
  employee_id: number
  employee_name: string
  [key: string]: string | number // dynamic month columns
}

const monthlyBreakdown = computed(() => {
  // Build allocation lookup: empId -> month -> allocated_fte
  const allocLookup = new Map<string, number>()
  for (const alloc of allocations.value) {
    const month = alloc.allocation_date?.substring(0, 7)
    if (month) {
      const key = `${alloc.employee_id}|${month}`
      allocLookup.set(key, (allocLookup.get(key) ?? 0) + alloc.allocated_fte)
    }
  }

  // Build time entry lookup: empId -> month -> actual_hours
  const timeLookup = new Map<string, number>()
  for (const entry of timeEntries.value) {
    const month = entry.date?.substring(0, 7)
    if (month) {
      const key = `${entry.employee_id}|${month}`
      timeLookup.set(key, (timeLookup.get(key) ?? 0) + entry.hours)
    }
  }

  const rows: MonthlyBreakdownRow[] = []
  for (const emp of allEmployees.value) {
    const row: MonthlyBreakdownRow = {
      employee_id: emp.id,
      employee_name: emp.name,
    }
    for (const month of allMonths.value) {
      const key = `${emp.id}|${month}`
      const fte = allocLookup.get(key) ?? 0
      const allocHours = fte * STANDARD_MONTHLY_HOURS
      const actualHours = timeLookup.get(key) ?? 0
      row[`${month}_fte`] = fte
      row[`${month}_alloc`] = allocHours
      row[`${month}_actual`] = actualHours
      row[`${month}_var`] = actualHours - allocHours
    }
    rows.push(row)
  }
  return rows
})

// Dynamic headers for monthly breakdown table
const breakdownHeaders = computed(() => {
  const headers: Array<{ title: string; key: string; align?: 'start' | 'center' | 'end' }> = [
    { title: 'Employee', key: 'employee_name' },
  ]
  for (const month of allMonths.value) {
    const label = month // YYYY-MM
    headers.push({ title: `${label} FTE%`, key: `${month}_fte`, align: 'end' })
    headers.push({ title: `${label} Alloc Hrs`, key: `${month}_alloc`, align: 'end' })
    headers.push({ title: `${label} Actual Hrs`, key: `${month}_actual`, align: 'end' })
    headers.push({ title: `${label} Variance`, key: `${month}_var`, align: 'end' })
  }
  return headers
})

// --- Chart 1: Allocated vs Actual Hours (grouped bar) ---
const allocVsActualData = computed<Plotly.Data[]>(() => {
  if (allEmployees.value.length === 0 || allMonths.value.length === 0) return []

  const xLabels: string[] = []
  const allocatedHours: number[] = []
  const actualHours: number[] = []

  for (const emp of allEmployees.value) {
    for (const month of allMonths.value) {
      const fte = (() => {
        let total = 0
        for (const alloc of allocations.value) {
          if (alloc.employee_id === emp.id && alloc.allocation_date?.substring(0, 7) === month) {
            total += alloc.allocated_fte
          }
        }
        return total
      })()
      const actual = (() => {
        let total = 0
        for (const entry of timeEntries.value) {
          if (entry.employee_id === emp.id && entry.date?.substring(0, 7) === month) {
            total += entry.hours
          }
        }
        return total
      })()

      if (fte > 0 || actual > 0) {
        xLabels.push(`${emp.name} (${month})`)
        allocatedHours.push(fte * STANDARD_MONTHLY_HOURS)
        actualHours.push(actual)
      }
    }
  }

  return [
    {
      x: xLabels,
      y: allocatedHours,
      type: 'bar' as const,
      name: 'Allocated Hours',
      marker: { color: '#1976D2' },
    },
    {
      x: xLabels,
      y: actualHours,
      type: 'bar' as const,
      name: 'Actual Hours',
      marker: { color: '#FF9800' },
    },
  ]
})

const allocVsActualLayout = computed<Partial<Plotly.Layout>>(() => ({
  barmode: 'group' as const,
  xaxis: { title: { text: 'Employee / Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  legend: { orientation: 'h' as const, y: -0.3 },
  height: 400,
}))

// --- Chart 2: Team Allocation % FTE Over Time (line per employee) ---
const fteTrendData = computed<Plotly.Data[]>(() => {
  if (allEmployees.value.length === 0 || allMonths.value.length === 0) return []

  const traces: Plotly.Data[] = []
  for (const emp of allEmployees.value) {
    const yValues = allMonths.value.map((month) => {
      let total = 0
      for (const alloc of allocations.value) {
        if (alloc.employee_id === emp.id && alloc.allocation_date?.substring(0, 7) === month) {
          total += alloc.allocated_fte
        }
      }
      return total * 100 // convert to percentage
    })

    traces.push({
      x: allMonths.value,
      y: yValues,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: emp.name,
      marker: { size: 5 },
    })
  }
  return traces
})

const fteTrendLayout = computed<Partial<Plotly.Layout>>(() => ({
  xaxis: { title: { text: 'Month' } },
  yaxis: { title: { text: 'Allocated FTE %' }, rangemode: 'tozero' },
  legend: { orientation: 'h' as const, y: -0.2 },
  height: 350,
}))
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading" type="table" />

    <!-- Error -->
    <v-alert v-else-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <template v-else>
      <!-- No allocations -->
      <v-alert
        v-if="allocations.length === 0"
        type="info"
        variant="tonal"
        class="mb-4"
      >
        No team members allocated to this project.
      </v-alert>

      <template v-else>
        <!-- Employee Summary -->
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold">Team Summary</v-card-title>
          <v-card-text>
            <v-data-table
              :headers="summaryHeaders"
              :items="employeeSummary"
              density="compact"
              :items-per-page="-1"
              hide-default-footer
            >
              <template #item.employee_name="{ item }">
                <router-link
                  :to="`/employees/${item.employee_id}`"
                  class="text-primary text-decoration-none"
                >
                  {{ item.employee_name }}
                </router-link>
              </template>
              <template #item.avg_fte="{ item }">
                {{ (item.avg_fte * 100).toFixed(0) }}%
              </template>
              <template #item.role="{ item }">
                {{ item.role ?? '-' }}
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>

        <!-- Detailed Monthly Allocations -->
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold">Monthly Allocations</v-card-title>
          <v-card-text>
            <v-data-table
              :headers="detailHeaders"
              :items="allocations"
              density="compact"
              :items-per-page="25"
              :sort-by="[{ key: 'allocation_date', order: 'asc' }]"
            >
              <template #item.employee_name="{ item }">
                <router-link
                  :to="`/employees/${item.employee_id}`"
                  class="text-primary text-decoration-none"
                >
                  {{ item.employee_name ?? 'Unknown' }}
                </router-link>
              </template>
              <template #item.allocated_fte="{ item }">
                {{ (item.allocated_fte * 100).toFixed(0) }}%
              </template>
              <template #item.bill_rate="{ item }">
                {{ item.bill_rate != null ? formatCurrency(item.bill_rate) + '/hr' : '-' }}
              </template>
              <template #item.effective_rate="{ item }">
                {{ item.effective_rate != null ? formatCurrency(item.effective_rate) + '/hr' : '-' }}
              </template>
              <template #item.role="{ item }">
                {{ item.role ?? '-' }}
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>

        <!-- Per-Employee Monthly Breakdown -->
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold">
            Per-Employee Monthly Breakdown
          </v-card-title>
          <v-card-text>
            <v-alert
              v-if="monthlyBreakdown.length === 0"
              type="info"
              variant="tonal"
              density="compact"
            >
              No monthly breakdown data available.
            </v-alert>
            <div v-else style="overflow-x: auto;">
              <v-data-table
                :headers="breakdownHeaders"
                :items="monthlyBreakdown"
                density="compact"
                :items-per-page="-1"
                hide-default-footer
              >
                <template #item.employee_name="{ item }">
                  <router-link
                    :to="`/employees/${item.employee_id}`"
                    class="text-primary text-decoration-none"
                  >
                    {{ item.employee_name }}
                  </router-link>
                </template>
                <template v-for="month in allMonths" :key="`fte-${month}`" #[`item.${month}_fte`]="{ item }">
                  {{ ((item[`${month}_fte`] as number) * 100).toFixed(0) }}%
                </template>
                <template v-for="month in allMonths" :key="`alloc-${month}`" #[`item.${month}_alloc`]="{ item }">
                  {{ (item[`${month}_alloc`] as number).toFixed(1) }}
                </template>
                <template v-for="month in allMonths" :key="`actual-${month}`" #[`item.${month}_actual`]="{ item }">
                  {{ (item[`${month}_actual`] as number).toFixed(1) }}
                </template>
                <template v-for="month in allMonths" :key="`var-${month}`" #[`item.${month}_var`]="{ item }">
                  <span :class="(item[`${month}_var`] as number) < 0 ? 'text-error' : 'text-success'">
                    {{ (item[`${month}_var`] as number).toFixed(1) }}
                  </span>
                </template>
              </v-data-table>
            </div>
          </v-card-text>
        </v-card>

        <!-- Chart: Allocated vs Actual Hours -->
        <v-card class="mb-4 pa-4">
          <div class="text-subtitle-1 font-weight-bold mb-3">Allocated vs Actual Hours</div>
          <PlotlyChart
            :data="allocVsActualData"
            :layout="allocVsActualLayout"
            :loading="loading"
          />
        </v-card>

        <!-- Chart: Team Allocation % FTE Over Time -->
        <v-card class="mb-4 pa-4">
          <div class="text-subtitle-1 font-weight-bold mb-3">Team Allocation % FTE Over Time</div>
          <PlotlyChart
            :data="fteTrendData"
            :layout="fteTrendLayout"
            :loading="loading"
          />
        </v-card>
      </template>
    </template>
  </div>
</template>
