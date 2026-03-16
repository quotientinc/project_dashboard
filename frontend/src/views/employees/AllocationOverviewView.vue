<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useApi } from '@/composables/useApi'
import { useEmployeesStore } from '@/stores/employees'
import { downloadCsv, allocPctColor, allocStatusColor, formatCurrencyLocal } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type {
  AllocationPlanningEntry,
  AllocationProjectBreakdown,
} from '@/types'

const { get } = useApi()

// ---------------------------------------------------------------------------
// Pinia store -- persists filter/sort state across navigation
// ---------------------------------------------------------------------------
const store = useEmployeesStore()
const {
  allocYear,
  allocMonth,
  allocStatusFilter,
  allocSearchTerm,
} = storeToRefs(store)

// ---------------------------------------------------------------------------
// Local state
// ---------------------------------------------------------------------------
const allocData = ref<AllocationPlanningEntry[]>([])
const allocLoading = ref(false)

// Dialog for project breakdown
const allocDialogOpen = ref(false)
const allocDialogEmployee = ref<AllocationPlanningEntry | null>(null)

// ---------------------------------------------------------------------------
// Year / month options
// ---------------------------------------------------------------------------
const now = new Date()

const yearOptions = computed(() => {
  const y = now.getFullYear()
  return [y - 1, y, y + 1]
})

const monthOptions = [
  { title: 'January', value: 1 },
  { title: 'February', value: 2 },
  { title: 'March', value: 3 },
  { title: 'April', value: 4 },
  { title: 'May', value: 5 },
  { title: 'June', value: 6 },
  { title: 'July', value: 7 },
  { title: 'August', value: 8 },
  { title: 'September', value: 9 },
  { title: 'October', value: 10 },
  { title: 'November', value: 11 },
  { title: 'December', value: 12 },
]

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function fetchAllocationData() {
  allocLoading.value = true
  try {
    allocData.value = await get<AllocationPlanningEntry[]>(
      `/analytics/allocation-planning?year=${allocYear.value}&month=${allocMonth.value}`
    )
  } catch {
    // error handled by useApi
  } finally {
    allocLoading.value = false
  }
}

onMounted(fetchAllocationData)
watch([allocYear, allocMonth], fetchAllocationData)

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------
const allocStatusOptions = ['Over-Allocated', 'Fully Allocated', 'On Target', 'Under-Allocated', 'Warning']

const filteredAllocData = computed(() => {
  let result = allocData.value

  if (allocStatusFilter.value.length > 0) {
    result = result.filter(e => allocStatusFilter.value.includes(e.status))
  }

  if (allocSearchTerm.value) {
    const term = allocSearchTerm.value.toLowerCase()
    result = result.filter(e => (e.employee_name ?? '').toLowerCase().includes(term))
  }

  return result
})

// ---------------------------------------------------------------------------
// KPI computeds
// ---------------------------------------------------------------------------
const allocTotalEmployees = computed(() => filteredAllocData.value.length)
const allocOverAllocated = computed(() => filteredAllocData.value.filter((e) => e.allocation_pct > 100).length)
const allocUnderAllocated = computed(() => filteredAllocData.value.filter((e) => e.allocation_pct < 80).length)
const allocAvgPct = computed(() => {
  if (filteredAllocData.value.length === 0) return 0
  return filteredAllocData.value.reduce((sum, e) => sum + e.allocation_pct, 0) / filteredAllocData.value.length
})

// ---------------------------------------------------------------------------
// Data table
// ---------------------------------------------------------------------------
const allocHeaders = [
  { title: 'Employee Name', key: 'employee_name', minWidth: '160px' },
  { title: 'Target FTE', key: 'target_fte', minWidth: '100px', align: 'end' as const },
  { title: 'Possible Hours', key: 'possible_hours', minWidth: '120px', align: 'end' as const },
  { title: 'Allocated Hours', key: 'allocated_hours', minWidth: '130px', align: 'end' as const },
  { title: 'Allocation %', key: 'allocation_pct', minWidth: '120px', align: 'end' as const },
  { title: 'Variance', key: 'variance', minWidth: '100px', align: 'end' as const },
  { title: 'Status', key: 'status', minWidth: '130px' },
]

function onAllocRowClicked(item: AllocationPlanningEntry) {
  if (item) {
    allocDialogEmployee.value = item
    allocDialogOpen.value = true
  }
}

// ---------------------------------------------------------------------------
// Dialog: project breakdown table + pie chart
// ---------------------------------------------------------------------------
const breakdownHeaders = [
  { title: 'Project', key: 'project_name' },
  { title: 'FTE', key: 'allocated_fte' },
  { title: 'Hours', key: 'allocated_hours' },
  { title: 'Bill Rate', key: 'bill_rate' },
]

const dialogPieData = computed(() => {
  const emp = allocDialogEmployee.value
  if (!emp || !emp.project_breakdown || emp.project_breakdown.length === 0) return []
  return [
    {
      type: 'pie' as const,
      labels: emp.project_breakdown.map((p: AllocationProjectBreakdown) => p.project_name),
      values: emp.project_breakdown.map((p: AllocationProjectBreakdown) => p.allocated_hours),
      hole: 0.4,
      textinfo: 'label+percent' as const,
    },
  ]
})

const dialogPieLayout = { margin: { t: 10, r: 10, b: 10, l: 10 }, height: 300, showlegend: false }

// ---------------------------------------------------------------------------
// Bar chart: Allocation % by Employee
// ---------------------------------------------------------------------------
const allocBarData = computed(() => {
  if (filteredAllocData.value.length === 0) return []
  const sorted = [...filteredAllocData.value].sort((a, b) => b.allocation_pct - a.allocation_pct)
  const colors = sorted.map((e) => {
    if (e.allocation_pct > 120) return '#F44336'
    if (e.allocation_pct > 100) return '#FF9800'
    if (e.allocation_pct >= 80) return '#4CAF50'
    return '#2196F3'
  })
  return [
    {
      type: 'bar' as const,
      x: sorted.map((e) => e.employee_name),
      y: sorted.map((e) => e.allocation_pct),
      marker: { color: colors },
    },
  ]
})

const allocBarLayout = computed(() => ({
  height: 350,
  margin: { t: 20, r: 20, b: 100, l: 50 },
  xaxis: { tickangle: -45 },
  yaxis: { title: { text: 'Allocation %' } },
  shapes: [
    {
      type: 'line' as const,
      x0: 0, x1: 1, xref: 'paper' as const,
      y0: 80, y1: 80, yref: 'y' as const,
      line: { color: '#4CAF50', width: 2, dash: 'dash' as const },
    },
    {
      type: 'line' as const,
      x0: 0, x1: 1, xref: 'paper' as const,
      y0: 100, y1: 100, yref: 'y' as const,
      line: { color: '#F44336', width: 2, dash: 'dash' as const },
    },
  ],
}))

// ---------------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------------
function exportAllocCsv() {
  const rows = filteredAllocData.value.map((e) => ({
    Employee: e.employee_name,
    'Target FTE': e.target_fte,
    'Possible Hours': e.possible_hours,
    'Allocated Hours': e.allocated_hours,
    'Allocation %': e.allocation_pct,
    Variance: e.variance,
    Status: e.status,
  }))
  downloadCsv(rows, `allocation_overview_${allocYear.value}_${allocMonth.value}.csv`)
}
</script>

<template>
  <!-- Controls -->
  <v-row class="mb-2">
    <v-col cols="12" sm="4" md="3">
      <v-select
        v-model="allocYear"
        label="Year"
        :items="yearOptions"
        density="compact"
      />
    </v-col>
    <v-col cols="12" sm="4" md="3">
      <v-select
        v-model="allocMonth"
        label="Month"
        :items="monthOptions"
        item-title="title"
        item-value="value"
        density="compact"
      />
    </v-col>
  </v-row>

  <!-- Allocation Filters -->
  <v-row class="mb-2">
    <v-col cols="12" md="8">
      <div class="d-flex flex-wrap ga-2">
        <v-chip
          v-for="status in allocStatusOptions"
          :key="status"
          :color="allocStatusFilter.includes(status) ? 'primary' : undefined"
          :variant="allocStatusFilter.includes(status) ? 'flat' : 'outlined'"
          size="small"
          @click="
            allocStatusFilter.includes(status)
              ? allocStatusFilter = allocStatusFilter.filter(s => s !== status)
              : allocStatusFilter = [...allocStatusFilter, status]
          "
        >
          {{ status }}
        </v-chip>
        <v-chip
          v-if="allocStatusFilter.length > 0"
          color="grey"
          variant="text"
          size="small"
          @click="allocStatusFilter = []"
        >
          Clear filters
        </v-chip>
      </div>
    </v-col>
    <v-col cols="12" md="4">
      <v-text-field
        v-model="allocSearchTerm"
        prepend-inner-icon="mdi-magnify"
        label="Search by name..."
        clearable
        density="compact"
        hide-details
        @click:clear="allocSearchTerm = ''"
      />
    </v-col>
  </v-row>

  <!-- KPI Cards -->
  <v-row class="mb-4">
    <v-col cols="12" sm="6" md="3">
      <KpiCard
        title="Total Employees"
        :value="String(allocTotalEmployees)"
        icon="mdi-account-group"
        color="#1976D2"
        :loading="allocLoading"
      />
    </v-col>
    <v-col cols="12" sm="6" md="3">
      <KpiCard
        title="Over-Allocated"
        :value="String(allocOverAllocated)"
        icon="mdi-arrow-up-bold"
        color="#F44336"
        :loading="allocLoading"
      />
    </v-col>
    <v-col cols="12" sm="6" md="3">
      <KpiCard
        title="Under-Allocated"
        :value="String(allocUnderAllocated)"
        icon="mdi-arrow-down-bold"
        color="#2196F3"
        :loading="allocLoading"
      />
    </v-col>
    <v-col cols="12" sm="6" md="3">
      <KpiCard
        title="Avg Allocation %"
        :value="allocAvgPct.toFixed(1) + '%'"
        icon="mdi-percent"
        color="#4CAF50"
        :loading="allocLoading"
      />
    </v-col>
  </v-row>

  <!-- Loading skeleton -->
  <v-skeleton-loader v-if="allocLoading" type="table" class="mb-4" />

  <!-- Data Table -->
  <v-card v-else class="mb-4">
    <v-card-text class="pa-0">
      <div class="d-flex align-center justify-space-between pa-3 pb-0">
        <div class="text-caption text-medium-emphasis">
          {{ filteredAllocData.length }} of {{ allocData.length }} employees &mdash; Click a row to view project breakdown
        </div>
        <v-btn
          variant="outlined"
          size="small"
          prepend-icon="mdi-download"
          @click="exportAllocCsv"
          :disabled="filteredAllocData.length === 0"
        >
          Export CSV
        </v-btn>
      </div>
      <v-data-table
        :headers="allocHeaders"
        :items="filteredAllocData"
        density="compact"
        hover
        class="cursor-pointer"
        items-per-page="25"
        @click:row="(_e: Event, { item }: { item: any }) => onAllocRowClicked(item)"
      >
        <template #item.target_fte="{ value }">
          {{ value != null ? value.toFixed(2) : '-' }}
        </template>
        <template #item.possible_hours="{ value }">
          {{ value != null ? value.toFixed(1) : '-' }}
        </template>
        <template #item.allocated_hours="{ value }">
          {{ value != null ? value.toFixed(1) : '-' }}
        </template>
        <template #item.allocation_pct="{ value }">
          <span v-if="value != null" :style="{ fontWeight: 600, color: allocPctColor(value) }">
            {{ value.toFixed(1) }}%
          </span>
          <span v-else>-</span>
        </template>
        <template #item.variance="{ value }">
          {{ value != null ? value.toFixed(1) : '-' }}
        </template>
        <template #item.status="{ value }">
          <v-chip v-if="value" :color="allocStatusColor(value)" size="small">
            {{ value }}
          </v-chip>
          <span v-else>-</span>
        </template>
      </v-data-table>
    </v-card-text>
  </v-card>

  <!-- Bar chart: Allocation % by Employee -->
  <v-card v-if="!allocLoading && allocBarData.length > 0" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-medium">
      Allocation % by Employee
    </v-card-title>
    <v-card-text>
      <PlotlyChart :data="allocBarData" :layout="allocBarLayout" />
    </v-card-text>
  </v-card>

  <!-- Project breakdown dialog -->
  <v-dialog v-model="allocDialogOpen" max-width="700">
    <v-card v-if="allocDialogEmployee">
      <v-card-title class="text-h6">
        {{ allocDialogEmployee.employee_name }}
      </v-card-title>
      <v-card-subtitle>
        Allocation: {{ allocDialogEmployee.allocation_pct.toFixed(1) }}% &mdash; {{ allocDialogEmployee.status }}
      </v-card-subtitle>
      <v-card-text>
        <v-data-table
          :headers="breakdownHeaders"
          :items="allocDialogEmployee.project_breakdown"
          density="compact"
          class="mb-4"
        >
          <template #item.allocated_fte="{ item }">
            {{ item.allocated_fte.toFixed(2) }}
          </template>
          <template #item.allocated_hours="{ item }">
            {{ item.allocated_hours.toFixed(1) }}
          </template>
          <template #item.bill_rate="{ item }">
            {{ formatCurrencyLocal(item.bill_rate) }}
          </template>
        </v-data-table>

        <div v-if="dialogPieData.length > 0" class="text-subtitle-2 font-weight-medium mb-2">
          Allocation by Project
        </div>
        <PlotlyChart
          v-if="dialogPieData.length > 0"
          :data="dialogPieData"
          :layout="dialogPieLayout"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="allocDialogOpen = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
