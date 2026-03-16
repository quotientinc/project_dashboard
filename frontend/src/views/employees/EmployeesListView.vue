<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useApi } from '@/composables/useApi'
import { useEmployeesStore } from '@/stores/employees'
import { downloadCsv, formatCurrencyLocal } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import type { Employee } from '@/types'

const router = useRouter()
const { get, loading, error } = useApi()

// ---------------------------------------------------------------------------
// Pinia store -- persists filter/sort state across navigation
// ---------------------------------------------------------------------------
const {
  selectedBillableStatus,
  selectedPayType,
  searchTerm,
  employeeListSortBy,
} = storeToRefs(useEmployeesStore())

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------
const employees = ref<Employee[]>([])

async function fetchEmployees() {
  try {
    employees.value = await get<Employee[]>('/employees/')
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchEmployees)

// ---------------------------------------------------------------------------
// Filtered list
// ---------------------------------------------------------------------------
const filteredEmployees = computed(() => {
  let result = employees.value

  if (selectedBillableStatus.value === 'Billable') {
    result = result.filter((e) => e.billable === 1)
  } else if (selectedBillableStatus.value === 'Non-Billable') {
    result = result.filter((e) => e.billable !== 1)
  }

  if (selectedPayType.value === 'Hourly') {
    result = result.filter((e) => (e.pay_type ?? '').toLowerCase() === 'hourly')
  } else if (selectedPayType.value === 'Salary') {
    result = result.filter((e) => (e.pay_type ?? '').toLowerCase() === 'salary')
  }

  if (searchTerm.value) {
    const term = searchTerm.value.toLowerCase()
    result = result.filter(
      (e) => (e.name ?? '').toLowerCase().includes(term)
    )
  }

  return result
})

// ---------------------------------------------------------------------------
// Summary metrics
// ---------------------------------------------------------------------------
const totalEmployees = computed(() => filteredEmployees.value.length)

const avgUtilization = computed(() => {
  const vals = filteredEmployees.value
    .map((e) => e.utilization)
    .filter((v): v is number => v != null)
  if (vals.length === 0) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

const avgHourlyRate = computed(() => {
  const vals = filteredEmployees.value
    .map((e) => e.hourly_rate ?? e.cost_rate)
    .filter((v): v is number => v != null && v > 0)
  if (vals.length === 0) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

// Summary chip counts
const billableCount = computed(() => filteredEmployees.value.filter((e) => e.billable === 1).length)
const salaryCount = computed(() => filteredEmployees.value.filter((e) => (e.pay_type ?? '').toLowerCase() === 'salary').length)
const hourlyCount = computed(() => filteredEmployees.value.filter((e) => (e.pay_type ?? '').toLowerCase() === 'hourly').length)

// ---------------------------------------------------------------------------
// Table headers
// ---------------------------------------------------------------------------
const listHeaders = [
  { title: 'Name', key: 'name', minWidth: '160px' },
  { title: 'Role', key: 'role', minWidth: '140px' },
  { title: 'Pay Type', key: 'pay_type', minWidth: '100px' },
  { title: 'Billable', key: 'billable', minWidth: '90px' },
  { title: 'Cost Rate', key: 'cost_rate', minWidth: '120px', align: 'end' as const },
  { title: 'FTE', key: 'fte', minWidth: '80px', align: 'end' as const },
  { title: 'Target Alloc', key: 'target_allocation', minWidth: '110px', align: 'end' as const },
  { title: 'Hire Date', key: 'hire_date', minWidth: '120px' },
  { title: 'Term Date', key: 'term_date', minWidth: '120px' },
]

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
function onListRowClicked(item: Employee) {
  if (item?.id != null) {
    router.push(`/employees/${item.id}`)
  }
}

function exportListCsv() {
  downloadCsv(filteredEmployees.value as unknown as Record<string, unknown>[], 'employees.csv')
}
</script>

<template>
  <div>
    <!-- Error alert -->
    <v-alert v-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Filters Row -->
    <v-row class="mb-2">
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="selectedBillableStatus"
          label="Billable Status"
          :items="['All', 'Billable', 'Non-Billable']"
          density="compact"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="selectedPayType"
          label="Pay Type"
          :items="['All', 'Hourly', 'Salary']"
          density="compact"
        />
      </v-col>
      <v-col cols="12" sm="12" md="6">
        <v-text-field
          v-model="searchTerm"
          prepend-inner-icon="mdi-magnify"
          label="Search by name..."
          clearable
          density="compact"
          @click:clear="searchTerm = ''"
        />
      </v-col>
    </v-row>

    <!-- Summary Metrics -->
    <v-row class="mb-2" v-if="!loading">
      <v-col cols="12" sm="4">
        <KpiCard
          title="Total Employees"
          :value="String(totalEmployees)"
          icon="mdi-account-group"
          color="#1976D2"
          :subtitle="`${employees.length} total in database`"
        />
      </v-col>
      <v-col cols="12" sm="4">
        <KpiCard
          title="Avg Utilization"
          :value="avgUtilization.toFixed(1) + '%'"
          icon="mdi-chart-bar"
          color="#4CAF50"
        />
      </v-col>
      <v-col cols="12" sm="4">
        <KpiCard
          title="Avg Cost Rate"
          :value="'$' + avgHourlyRate.toFixed(2)"
          icon="mdi-currency-usd"
          color="#FF9800"
        />
      </v-col>
    </v-row>

    <!-- Summary Chips -->
    <div class="d-flex ga-2 mb-4" v-if="!loading">
      <v-chip color="green" variant="flat" size="small">
        {{ billableCount }} Billable
      </v-chip>
      <v-chip color="blue" variant="flat" size="small">
        {{ salaryCount }} Salary
      </v-chip>
      <v-chip color="orange" variant="flat" size="small">
        {{ hourlyCount }} Hourly
      </v-chip>
    </div>

    <!-- Loading skeleton -->
    <v-skeleton-loader v-if="loading" type="table" class="mb-4" />

    <!-- Data Table -->
    <v-card v-else>
      <v-card-text class="pa-0">
        <div class="d-flex align-center justify-space-between pa-3 pb-0">
          <div class="text-caption text-medium-emphasis">
            Showing {{ filteredEmployees.length }} of {{ employees.length }} employees
            &mdash; Click a row to view details
          </div>
          <v-btn
            variant="outlined"
            size="small"
            prepend-icon="mdi-download"
            @click="exportListCsv"
            :disabled="loading || filteredEmployees.length === 0"
          >
            Export CSV
          </v-btn>
        </div>
        <v-data-table
          :headers="listHeaders"
          :items="filteredEmployees"
          v-model:sort-by="employeeListSortBy"
          density="compact"
          hover
          class="cursor-pointer"
          items-per-page="25"
          @click:row="(_e: Event, { item }: { item: any }) => onListRowClicked(item)"
        >
          <template #item.billable="{ value }">
            <v-chip :color="value === 1 ? 'success' : 'grey'" size="small">
              {{ value === 1 ? 'Yes' : 'No' }}
            </v-chip>
          </template>
          <template #item.cost_rate="{ value }">
            {{ formatCurrencyLocal(value) }}
          </template>
          <template #item.fte="{ value }">
            {{ value != null ? value.toFixed(2) : '-' }}
          </template>
          <template #item.target_allocation="{ value }">
            {{ value != null ? (value * 100).toFixed(0) + '%' : '-' }}
          </template>
          <template #item.hire_date="{ value }">
            {{ value || '-' }}
          </template>
          <template #item.term_date="{ value }">
            {{ value || '-' }}
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>
  </div>
</template>
