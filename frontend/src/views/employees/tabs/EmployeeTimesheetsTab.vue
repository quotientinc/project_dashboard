<script setup lang="ts">
import { ref, computed, inject, onMounted, watch, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { formatCurrency } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import TimeFrameFilters from '@/components/TimeFrameFilters.vue'
import type { Employee, TimeEntry } from '@/types'

const route = useRoute()
const { get, error } = useApi()

const employee = inject<Ref<Employee | null>>('employee', ref(null))
const employeeId = computed(() => Number(route.params.id))

// ---- Filter State ----

const filtersRef = ref<InstanceType<typeof TimeFrameFilters> | null>(null)

function getMonthName(index: number): string {
  return ['January','February','March','April','May','June','July','August','September','October','November','December'][index] ?? 'January'
}

const filterYear = ref(new Date().getFullYear())
const filterTimeFrameType = ref<'Monthly' | 'Quarterly' | 'QTD' | 'YTD'>('YTD')
const filterSelectedMonth = ref(getMonthName(new Date().getMonth()))
const filterSelectedQuarter = ref(`Q${Math.ceil((new Date().getMonth() + 1) / 3)}`)
const filterFyType = ref<'Company' | 'Gov'>('Company')

// ---- Data ----

const timeEntries = ref<TimeEntry[]>([])
const dataLoading = ref(true)

async function fetchTimeEntries() {
  dataLoading.value = true
  timeEntries.value = []
  try {
    timeEntries.value = await get<TimeEntry[]>('/time-entries/', {
      params: {
        employee_id: employeeId.value,
        start_date: filtersRef.value?.dateRange?.startDate,
        end_date: filtersRef.value?.dateRange?.endDate,
      },
    })
  } catch {
    timeEntries.value = []
  } finally {
    dataLoading.value = false
  }
}

onMounted(fetchTimeEntries)
watch(
  [employeeId, filterYear, filterTimeFrameType, filterSelectedMonth, filterSelectedQuarter, filterFyType],
  fetchTimeEntries,
  { flush: 'post' },
)

// ---- KPI Computations ----

const totalHours = computed(() =>
  timeEntries.value.reduce((sum, te) => sum + te.hours, 0),
)

const billableHours = computed(() =>
  timeEntries.value.filter((te) => te.billable === 1).reduce((sum, te) => sum + te.hours, 0),
)

const nonBillableHours = computed(() => totalHours.value - billableHours.value)

const totalRevenue = computed(() =>
  timeEntries.value.reduce((sum, te) => sum + te.hours * (te.hourly_rate ?? 0), 0),
)

// ---- Hours by Project (aggregated) ----

interface ProjectHours {
  project_id: string
  project_name: string
  billable_hrs: number
  nonbillable_hrs: number
  total_hrs: number
  amount: number
  pct_of_total: number
}

const hoursByProject = computed<ProjectHours[]>(() => {
  if (!timeEntries.value.length) return []

  const projectMap = new Map<string, {
    project_id: string; project_name: string
    billable_hrs: number; nonbillable_hrs: number; total_hrs: number; amount: number
  }>()

  for (const te of timeEntries.value) {
    const key = te.project_id
    const existing = projectMap.get(key) ?? {
      project_id: te.project_id,
      project_name: te.project_name ?? te.project_id,
      billable_hrs: 0, nonbillable_hrs: 0, total_hrs: 0, amount: 0,
    }
    existing.total_hrs += te.hours
    if (te.billable === 1) {
      existing.billable_hrs += te.hours
    } else {
      existing.nonbillable_hrs += te.hours
    }
    existing.amount += te.hours * (te.hourly_rate ?? 0)
    projectMap.set(key, existing)
  }

  const totalHrs = Array.from(projectMap.values()).reduce((s, p) => s + p.total_hrs, 0)
  return Array.from(projectMap.values())
    .map((p) => ({ ...p, pct_of_total: totalHrs > 0 ? (p.total_hrs / totalHrs) * 100 : 0 }))
    .sort((a, b) => b.total_hrs - a.total_hrs)
})

const hoursByProjectHeaders = [
  { title: 'Project Code', key: 'project_id' },
  { title: 'Project', key: 'project_name' },
  { title: 'Billable Hrs', key: 'billable_hrs', align: 'end' as const },
  { title: 'Non-billable Hrs', key: 'nonbillable_hrs', align: 'end' as const },
  { title: 'Total Hrs', key: 'total_hrs', align: 'end' as const },
  { title: 'Amount', key: 'amount', align: 'end' as const },
  { title: '% of Total', key: 'pct_of_total', align: 'end' as const },
]

// ---- Timesheet Entries (formatted) ----

const timesheetEntries = computed(() => {
  return timeEntries.value
    .map((te) => ({
      ...te,
      billable_label: te.billable === 1 ? 'Yes' : 'No',
      bill_rate_display: te.hourly_rate ?? 0,
      amount: te.hours * (te.hourly_rate ?? 0),
    }))
    .sort((a, b) => a.date.localeCompare(b.date))
})

const timesheetHeaders = [
  { title: 'Date', key: 'date' },
  { title: 'Project Code', key: 'project_id' },
  { title: 'Project', key: 'project_name' },
  { title: 'Hours', key: 'hours', align: 'end' as const },
  { title: 'Billable', key: 'billable_label' },
  { title: 'Bill Rate', key: 'bill_rate_display', align: 'end' as const },
  { title: 'Amount', key: 'amount', align: 'end' as const },
  { title: 'Description', key: 'description' },
]

function formatNum(val: number | null | undefined, decimals = 1): string {
  if (val == null) return '0'
  return val.toFixed(decimals)
}
</script>

<template>
  <div>
    <TimeFrameFilters
      ref="filtersRef"
      v-model:year="filterYear"
      v-model:time-frame-type="filterTimeFrameType"
      v-model:selected-month="filterSelectedMonth"
      v-model:selected-quarter="filterSelectedQuarter"
      v-model:fy-type="filterFyType"
      class="mb-4"
    />

    <!-- Loading -->
    <v-skeleton-loader v-if="dataLoading" type="card, card, table" />

    <template v-else>
      <!-- Error -->
      <v-alert v-if="error" type="error" closable class="mb-4">
        {{ error }}
      </v-alert>

      <!-- No Data -->
      <v-alert
        v-if="!timeEntries.length && !error"
        type="info"
        variant="tonal"
        class="mb-4"
      >
        No timesheet entries found for the selected period.
      </v-alert>

      <template v-if="timeEntries.length">
        <!-- KPI Cards -->
        <v-row class="mb-4">
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Hours"
              :value="formatNum(totalHours)"
              icon="mdi-clock-outline"
              color="#1976D2"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Billable Hours"
              :value="formatNum(billableHours)"
              icon="mdi-cash-check"
              color="#4CAF50"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Non-billable Hours"
              :value="formatNum(nonBillableHours)"
              icon="mdi-clock-minus-outline"
              color="#FF9800"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <KpiCard
              title="Total Revenue"
              :value="formatCurrency(totalRevenue)"
              icon="mdi-currency-usd"
              color="#9C27B0"
            />
          </v-col>
        </v-row>

        <!-- Hours by Project Table -->
        <v-card class="mb-6">
          <v-card-title class="text-subtitle-1 font-weight-bold">
            <v-icon class="mr-2" size="small">mdi-folder-multiple-outline</v-icon>
            Hours by Project
          </v-card-title>
          <v-card-text class="pa-0">
            <v-data-table
              :items="hoursByProject"
              :headers="hoursByProjectHeaders"
              density="compact"
              :items-per-page="-1"
              hide-default-footer
              no-data-text="No project data available"
            >
              <template #item.billable_hrs="{ value }">{{ value.toFixed(1) }}</template>
              <template #item.nonbillable_hrs="{ value }">{{ value.toFixed(1) }}</template>
              <template #item.total_hrs="{ value }">{{ value.toFixed(1) }}</template>
              <template #item.amount="{ value }">${{ value.toFixed(2) }}</template>
              <template #item.pct_of_total="{ value }">{{ value.toFixed(1) }}%</template>
            </v-data-table>
          </v-card-text>
        </v-card>

        <!-- Timesheet Entries Table -->
        <v-card>
          <v-card-title class="text-subtitle-1 font-weight-bold">
            <v-icon class="mr-2" size="small">mdi-clipboard-text-clock</v-icon>
            Timesheet Entries
          </v-card-title>
          <v-card-text class="pa-0">
            <v-data-table
              :items="timesheetEntries"
              :headers="timesheetHeaders"
              density="compact"
              :items-per-page="25"
              no-data-text="No timesheet entries available"
            >
              <template #item.hours="{ value }">{{ value.toFixed(2) }}</template>
              <template #item.bill_rate_display="{ value }">
                {{ value ? '$' + value.toFixed(2) : '-' }}
              </template>
              <template #item.amount="{ value }">${{ value.toFixed(2) }}</template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </template>
    </template>
  </div>
</template>
