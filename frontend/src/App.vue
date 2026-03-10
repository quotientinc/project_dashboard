<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'

const drawer = ref(true)
const rail = ref(false)
const route = useRoute()
const { get } = useApi()

interface NavItem {
  title: string
  icon: string
  to: string
  value: string
}

const navItems: NavItem[] = [
  { title: 'Overview Dashboard', icon: 'mdi-view-dashboard', to: '/', value: 'overview' },
  { title: 'Projects', icon: 'mdi-rocket-launch', to: '/projects', value: 'projects' },
  { title: 'Employees', icon: 'mdi-account-group', to: '/employees', value: 'employees' },
  { title: 'Timesheets', icon: 'mdi-clock-outline', to: '/timesheets', value: 'timesheets' },
  { title: 'Utilization', icon: 'mdi-gauge', to: '/utilization', value: 'utilization' },
  { title: 'Financial', icon: 'mdi-currency-usd', to: '/financial', value: 'financial' },
  { title: 'Reports', icon: 'mdi-chart-line', to: '/reports', value: 'reports' },
  { title: 'What-If Scenarios', icon: 'mdi-crystal-ball', to: '/what-if', value: 'what-if' },
  { title: 'Months', icon: 'mdi-calendar', to: '/months', value: 'months' },
  { title: 'Data Management', icon: 'mdi-content-save', to: '/data-management', value: 'data-management' },
  { title: 'Budget Mockup', icon: 'mdi-cash-multiple', to: '/budget-mockup', value: 'budget-mockup' },
]

const activeItem = computed(() => {
  const path = route.path
  const match = navItems.find((item) => {
    if (item.to === '/') return path === '/'
    return path.startsWith(item.to)
  })
  return match?.value || 'overview'
})

// Quick Stats
interface OverviewKPIs {
  total_projects: number
  active_projects: number
  completed_projects: number
  total_employees: number
  billable_employees: number
  total_quoted_value: number
  total_awarded_value: number
  total_budget_used: number
  total_hours_logged: number
  total_billable_hours: number
}

const quickStats = ref<OverviewKPIs | null>(null)
const statsLoading = ref(false)

async function fetchQuickStats() {
  statsLoading.value = true
  try {
    quickStats.value = await get<OverviewKPIs>('/analytics/overview')
  } catch {
    // silently fail for sidebar stats
  } finally {
    statsLoading.value = false
  }
}

onMounted(fetchQuickStats)

function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return '$' + (value / 1_000_000).toFixed(1) + 'M'
  }
  if (value >= 1_000) {
    return '$' + (value / 1_000).toFixed(0) + 'K'
  }
  return '$' + value.toFixed(0)
}
</script>

<template>
  <v-app>
    <v-app-bar
      color="primary"
      density="comfortable"
      elevation="2"
    >
      <v-app-bar-nav-icon
        @click="rail = !rail"
        aria-label="Toggle navigation"
      />
      <v-app-bar-title class="text-h6 font-weight-bold">
        Project Dashboard
      </v-app-bar-title>
      <v-spacer />
      <v-btn
        icon="mdi-refresh"
        variant="text"
        aria-label="Refresh data"
        @click="fetchQuickStats"
      />
    </v-app-bar>

    <v-navigation-drawer
      v-model="drawer"
      :rail="rail"
      permanent
      color="surface"
      elevation="1"
    >
      <v-list
        density="comfortable"
        nav
        :selected="[activeItem]"
        color="primary"
      >
        <v-list-item
          v-for="item in navItems"
          :key="item.value"
          :prepend-icon="item.icon"
          :title="item.title"
          :value="item.value"
          :to="item.to"
          rounded="lg"
          class="mb-1"
        />
      </v-list>

      <!-- Quick Stats Section -->
      <template v-if="!rail">
        <v-divider class="mx-3 my-2" />

        <div class="px-3 py-1">
          <div class="text-subtitle-2 font-weight-bold text-medium-emphasis mb-2">
            Quick Stats
          </div>

          <v-skeleton-loader v-if="statsLoading" type="list-item-three-line" />

          <template v-else-if="quickStats">
            <div class="mb-3">
              <div class="text-caption text-medium-emphasis">Total Contract Value</div>
              <div class="text-body-1 font-weight-bold">
                {{ formatCurrency(quickStats.total_quoted_value) }}
              </div>
            </div>

            <div class="mb-3">
              <div class="text-caption text-medium-emphasis">Total Projects YTD</div>
              <div class="text-body-1 font-weight-bold">
                {{ quickStats.active_projects }}
                <span class="text-caption text-medium-emphasis ml-1">
                  of {{ quickStats.total_projects }} total
                </span>
              </div>
            </div>

            <div class="mb-3">
              <div class="text-caption text-medium-emphasis">Total Billable Employees</div>
              <div class="text-body-1 font-weight-bold">
                {{ quickStats.billable_employees }}
                <span class="text-caption text-medium-emphasis ml-1">
                  of {{ quickStats.total_employees }} total
                </span>
              </div>
            </div>

            <v-btn
              block
              variant="tonal"
              size="small"
              prepend-icon="mdi-refresh"
              @click="fetchQuickStats"
              :loading="statsLoading"
              class="mt-2"
            >
              Refresh Data
            </v-btn>
          </template>
        </div>
      </template>

      <template #append>
        <div class="pa-2">
          <v-divider class="mb-2" />
          <v-list-item
            v-if="!rail"
            density="compact"
            class="text-caption text-medium-emphasis"
          >
            Project Dashboard v2.0
          </v-list-item>
        </div>
      </template>
    </v-navigation-drawer>

    <v-main>
      <v-container fluid class="pa-6">
        <router-view />
      </v-container>
    </v-main>
  </v-app>
</template>

<style>
html {
  overflow-y: auto !important;
}
</style>