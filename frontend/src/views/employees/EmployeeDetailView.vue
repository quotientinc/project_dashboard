<script setup lang="ts">
import { ref, computed, onMounted, watch, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import type { Employee } from '@/types'

const route = useRoute()
const router = useRouter()
const { get, loading, error } = useApi()

const employeeId = computed(() => Number(route.params.id))
const employee = ref<Employee | null>(null)
const allEmployees = ref<Employee[]>([])

// Provide employee data to child tab components
provide('employee', employee)

// Employee switcher
const switcherValue = ref<number | null>(null)
const employeeItems = computed(() =>
  allEmployees.value.map((e) => ({
    title: `${e.id} - ${e.name}`,
    value: e.id,
  }))
)

async function fetchEmployee() {
  try {
    const [employeeData, employeesList] = await Promise.all([
      get<Employee>(`/employees/${employeeId.value}`),
      get<Employee[]>('/employees/'),
    ])
    employee.value = employeeData
    allEmployees.value = employeesList
    switcherValue.value = employeeData.id
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchEmployee)

// Re-fetch when employeeId changes (via switcher)
watch(employeeId, fetchEmployee)

function onEmployeeSwitch(newId: number | null) {
  if (newId != null && newId !== employeeId.value) {
    const pathSegments = route.path.split('/')
    const currentTab = pathSegments[pathSegments.length - 1] || 'details'
    router.push(`/employees/${newId}/${currentTab}`)
  }
}

// Tab navigation
const tabs = [
  { title: 'Details', value: 'details', icon: 'mdi-account' },
  { title: 'Allocation', value: 'allocation', icon: 'mdi-chart-pie' },
  { title: 'Utilization', value: 'utilization', icon: 'mdi-chart-bar' },
]

const currentTab = computed(() => {
  const pathSegments = route.path.split('/')
  return pathSegments[pathSegments.length - 1] || 'details'
})

function navigateTab(tab: string) {
  router.push(`/employees/${employeeId.value}/${tab}`)
}

// Billable chip color
function billableColor(billable: number): string {
  return billable === 1 ? 'success' : 'default'
}
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading && !employee" type="card, heading, card" />

    <!-- Error -->
    <v-alert v-else-if="error && !employee" type="error" class="mb-4">
      {{ error }}
      <template #append>
        <v-btn variant="text" @click="router.push('/employees')">Back to Employees</v-btn>
      </template>
    </v-alert>

    <!-- Content -->
    <template v-else-if="employee">
      <!-- Header -->
      <div class="d-flex align-center mb-2">
        <v-btn
          icon="mdi-arrow-left"
          variant="text"
          size="small"
          @click="router.push('/employees')"
          aria-label="Back to employees"
        />
        <div class="ml-3 flex-grow-1">
          <div class="d-flex align-center flex-wrap ga-2">
            <h1 class="text-h5 font-weight-bold">{{ employee.name }}</h1>
            <v-chip
              :color="billableColor(employee.billable)"
              size="small"
              label
            >
              {{ employee.billable === 1 ? 'Billable' : 'Non-billable' }}
            </v-chip>
            <v-chip
              v-if="employee.pay_type"
              color="info"
              size="small"
              label
            >
              {{ employee.pay_type }}
            </v-chip>
          </div>
          <div class="text-body-2 text-medium-emphasis mt-1">
            <span>ID: {{ employee.id }}</span>
            <span v-if="employee.department" class="ml-3">Dept: {{ employee.department }}</span>
            <span v-if="employee.role" class="ml-3">Role: {{ employee.role }}</span>
          </div>
        </div>

        <!-- Employee Switcher -->
        <v-autocomplete
          v-model="switcherValue"
          :items="employeeItems"
          item-title="title"
          item-value="value"
          label="Switch employee"
          density="compact"
          variant="outlined"
          hide-details
          style="max-width: 350px;"
          class="ml-4"
          @update:model-value="onEmployeeSwitch"
        />
      </div>

      <v-divider class="mb-2" />

      <!-- Tabs -->
      <v-tabs
        :model-value="currentTab"
        color="primary"
        class="mb-4"
      >
        <v-tab
          v-for="tab in tabs"
          :key="tab.value"
          :value="tab.value"
          :prepend-icon="tab.icon"
          @click="navigateTab(tab.value)"
        >
          {{ tab.title }}
        </v-tab>
      </v-tabs>

      <!-- Nested router view for tab content -->
      <router-view />
    </template>
  </div>
</template>
