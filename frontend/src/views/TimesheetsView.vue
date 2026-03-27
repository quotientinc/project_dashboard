<script setup lang="ts">
/**
 * Timesheets page.
 *
 * Displays performance metrics data across three tabs: Actuals, Projected,
 * and Possible. Users can filter by date range and optionally by employee
 * or project (mutually exclusive). Each tab shows KPI summary cards, a
 * data table with monthly columns, and a CSV download button.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import { formatCurrency, downloadCsv } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'

// ---- Types ----

interface EntityData {
  hours: number
  revenue: number
  worked_days: number
}

interface PerformanceResponse {
  actuals: Record<string, Record<string, EntityData>>
  projected: Record<string, Record<string, EntityData>>
  possible: Record<string, Record<string, EntityData>>
}

interface EmployeeOption {
  id: number
  name: string
}

interface ProjectOption {
  id: string
  name: string
}

interface TableRow {
  entity: string
  metric: string
  rowspan?: number
  [monthKey: string]: string | number | undefined
}

// ---- State ----

const api = useApi()

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const currentYear = new Date().getFullYear()
const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i)

const startYear = ref(currentYear)
const startMonth = ref('January')
const endYear = ref(currentYear)
const endMonth = ref('December')

const selectedEmployee = ref<number | null>(null)
const selectedProject = ref<string | null>(null)

const employees = ref<EmployeeOption[]>([])
const projects = ref<ProjectOption[]>([])

const performanceData = ref<PerformanceResponse | null>(null)
const loading = ref(false)
const loadingEmployees = ref(false)
const loadingProjects = ref(false)
const errorMessage = ref<string | null>(null)

const activeTab = ref('actuals')

// ---- Computed ----

const groupingInfo = computed(() => {
  if (selectedEmployee.value) {
    const emp = employees.value.find(e => e.id === selectedEmployee.value)
    return `Grouped by project for employee: ${emp?.name || selectedEmployee.value}`
  }
  if (selectedProject.value) {
    const proj = projects.value.find(p => p.id === selectedProject.value)
    return `Grouped by employee for project: ${proj?.name || selectedProject.value}`
  }
  return 'Grouped by employee (default)'
})

const startMonthIndex = computed(() => MONTHS.indexOf(startMonth.value))
const endMonthIndex = computed(() => MONTHS.indexOf(endMonth.value))

/**
 * Build a sorted list of month column keys present in the data for the
 * active tab section.
 */
function getSortedMonths(section: Record<string, Record<string, EntityData>> | undefined): string[] {
  if (!section) return []
  const keys = Object.keys(section)
  // Sort chronologically: "January 2025" etc.
  keys.sort((a, b) => {
    const [mA, yA] = a.split(' ')
    const [mB, yB] = b.split(' ')
    const diff = Number(yA) - Number(yB)
    if (diff !== 0) return diff
    return MONTHS.indexOf(mA ?? '') - MONTHS.indexOf(mB ?? '')
  })
  return keys
}

/**
 * Build a name lookup from the entity ID.
 * When filtering by employee → entities are project IDs (strings).
 * When filtering by project or no filter → entities are employee IDs (numeric strings).
 */
function resolveEntityName(id: string): string {
  if (selectedEmployee.value) {
    // Entities are project IDs
    const proj = projects.value.find(p => p.id === id)
    return proj?.name ?? id
  }
  // Entities are employee IDs
  const emp = employees.value.find(e => String(e.id) === id)
  return emp?.name ?? id
}

const entityColumnTitle = computed(() => {
  return selectedEmployee.value ? 'Project' : 'Employee'
})

function buildTableData(section: Record<string, Record<string, EntityData>> | undefined): {
  rows: TableRow[]
  headers: { title: string; key: string; sortable: boolean; align?: 'start' | 'end' | 'center'; width?: string }[]
  months: string[]
} {
  if (!section) return { rows: [], headers: [], months: [] }

  const months = getSortedMonths(section)
  const entityIds = new Set<string>()
  for (const monthData of Object.values(section)) {
    for (const eid of Object.keys(monthData)) entityIds.add(eid)
  }

  // Build entity groups with their 3 metric rows
  interface GroupData {
    entityName: string
    hours: Record<string, number>
    hoursRow: TableRow
    revenueRow: TableRow
    daysRow: TableRow
  }

  const groups: GroupData[] = []
  for (const entityId of entityIds) {
    const displayName = resolveEntityName(entityId)
    const hours: Record<string, number> = {}
    const hoursRow: TableRow = { entity: displayName, metric: 'Hours', rowspan: 3 }
    const revenueRow: TableRow = { entity: displayName, metric: 'Revenue' }
    const daysRow: TableRow = { entity: displayName, metric: 'Worked Days' }

    for (const month of months) {
      const data = section[month]?.[entityId]
      const h = data ? data.hours : 0
      hours[month] = h
      hoursRow[month] = h
      revenueRow[month] = data ? data.revenue : 0
      daysRow[month] = data ? data.worked_days : 0
    }

    groups.push({ entityName: displayName, hours, hoursRow, revenueRow, daysRow })
  }

  // Sort groups alphabetically by entity name
  groups.sort((a, b) => a.entityName.localeCompare(b.entityName))

  // Flatten groups to rows
  const rows: TableRow[] = []
  for (const g of groups) {
    rows.push(g.hoursRow, g.revenueRow, g.daysRow)
  }

  const headers = [
    { title: entityColumnTitle.value, key: 'entity', sortable: false, width: '180px' },
    { title: 'Metric', key: 'metric', sortable: false, width: '100px' },
    ...months.map(m => ({ title: m, key: m, sortable: false, align: 'end' as const, width: '120px' })),
  ]

  return { rows, headers, months }
}

function metricColorClass(metric: string): string {
  if (metric === 'Hours') return 'hrs-cell'
  if (metric === 'Revenue') return 'rev-cell'
  return 'days-cell'
}

function formatMetricValue(value: unknown, metric: string): string {
  const num = Number(value) || 0
  if (metric === 'Revenue') return formatCurrency(num)
  if (metric === 'Worked Days') return String(Math.round(num))
  return num.toFixed(1)
}

function computeKpis(section: Record<string, Record<string, EntityData>> | undefined): {
  totalHours: number
  totalRevenue: number
  avgHoursPerMonth: number
} {
  if (!section) return { totalHours: 0, totalRevenue: 0, avgHoursPerMonth: 0 }

  let totalHours = 0
  let totalRevenue = 0
  const monthCount = Object.keys(section).length

  for (const monthData of Object.values(section)) {
    for (const entityData of Object.values(monthData)) {
      totalHours += entityData.hours
      totalRevenue += entityData.revenue
    }
  }

  return {
    totalHours,
    totalRevenue,
    avgHoursPerMonth: monthCount > 0 ? totalHours / monthCount : 0,
  }
}

const actualsData = computed(() => buildTableData(performanceData.value?.actuals))
const projectedData = computed(() => buildTableData(performanceData.value?.projected))
const possibleData = computed(() => buildTableData(performanceData.value?.possible))

const actualsKpis = computed(() => computeKpis(performanceData.value?.actuals))
const projectedKpis = computed(() => computeKpis(performanceData.value?.projected))
const possibleKpis = computed(() => computeKpis(performanceData.value?.possible))

// ---- Data fetching ----

async function loadFilterOptions() {
  loadingEmployees.value = true
  loadingProjects.value = true
  try {
    const [empResult, projResult] = await Promise.all([
      api.get<{ items?: EmployeeOption[]; data?: EmployeeOption[] } | EmployeeOption[]>('/employees/'),
      api.get<{ items?: ProjectOption[]; data?: ProjectOption[] } | ProjectOption[]>('/projects/'),
    ])
    employees.value = Array.isArray(empResult) ? empResult : (empResult.items || empResult.data || [])
    projects.value = Array.isArray(projResult) ? projResult : (projResult.items || projResult.data || [])
  } catch {
    // Filter options are non-critical; silently ignore
  } finally {
    loadingEmployees.value = false
    loadingProjects.value = false
  }
}

async function fetchPerformance() {
  loading.value = true
  errorMessage.value = null
  performanceData.value = null

  // Backend expects start_date and end_date in YYYY-MM-DD format
  const sMonth = startMonthIndex.value + 1
  const eMonth = endMonthIndex.value + 1
  const lastDay = new Date(endYear.value, eMonth, 0).getDate()
  const params: Record<string, string | number> = {
    start_date: `${startYear.value}-${String(sMonth).padStart(2, '0')}-01`,
    end_date: `${endYear.value}-${String(eMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
  }

  if (selectedEmployee.value) {
    params.employee_id = selectedEmployee.value
  }
  if (selectedProject.value) {
    params.project_id = selectedProject.value
  }

  try {
    performanceData.value = await api.get<PerformanceResponse>('/analytics/performance', { params })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to load performance data'
    errorMessage.value = msg
  } finally {
    loading.value = false
  }
}

function handleRefresh() {
  fetchPerformance()
}

// ---- Mutual exclusion for filters ----

watch(selectedEmployee, (val) => {
  if (val) selectedProject.value = null
})

watch(selectedProject, (val) => {
  if (val) selectedEmployee.value = null
})

// ---- CSV download ----

function handleDownloadCsv(tabName: string) {
  const dataMap: Record<string, { rows: TableRow[]; months: string[] }> = {
    actuals: actualsData.value,
    projected: projectedData.value,
    possible: possibleData.value,
  }

  const { rows, months } = dataMap[tabName] || { rows: [], months: [] }
  if (rows.length === 0) return

  const csvRows = rows.map(row => {
    const out: Record<string, unknown> = {
      [entityColumnTitle.value]: row.entity,
      Metric: row.metric,
    }
    for (const m of months) { out[m] = row[m] ?? 0 }
    return out
  })

  downloadCsv(csvRows, `timesheets_${tabName}_${startYear.value}_${startMonth.value}_to_${endYear.value}_${endMonth.value}.csv`)
}

// ---- Tab descriptions ----

const tabDescriptions: Record<string, string> = {
  actuals: 'Actual hours and revenue recorded from timesheet entries within the selected date range.',
  projected: 'Projected hours and revenue based on current allocations and planned schedules.',
  possible: 'Maximum possible capacity assuming full utilization of all available resources.',
}

// ---- Lifecycle ----

onMounted(() => {
  loadFilterOptions()
  fetchPerformance()
})
</script>

<template>
  <div>
    <!-- Page Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4 font-weight-bold">Timesheets</h1>
    </div>

    <!-- Filters Card -->
    <v-card class="mb-4">
      <v-card-title class="text-subtitle-1">Filters</v-card-title>
      <v-card-text>
        <!-- Date range selectors -->
        <v-row>
          <v-col cols="12" sm="3">
            <v-select
              v-model="startYear"
              label="Start Year"
              :items="yearOptions"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-select
              v-model="startMonth"
              label="Start Month"
              :items="MONTHS"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-select
              v-model="endYear"
              label="End Year"
              :items="yearOptions"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-select
              v-model="endMonth"
              label="End Month"
              :items="MONTHS"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
        </v-row>

        <!-- Entity filters -->
        <v-row class="mt-2">
          <v-col cols="12" sm="6">
            <v-autocomplete
              v-model="selectedEmployee"
              label="Filter by Employee"
              :items="employees"
              item-title="name"
              item-value="id"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              :disabled="!!selectedProject"
              :loading="loadingEmployees"
              placeholder="Select an employee..."
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-autocomplete
              v-model="selectedProject"
              label="Filter by Project"
              :items="projects"
              item-title="name"
              item-value="id"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              :disabled="!!selectedEmployee"
              :loading="loadingProjects"
              placeholder="Select a project..."
            />
          </v-col>
        </v-row>

        <!-- Info alert and Refresh -->
        <v-row class="mt-2" align="center">
          <v-col>
            <v-alert type="info" variant="tonal" density="compact" class="mb-0">
              {{ groupingInfo }}
            </v-alert>
          </v-col>
          <v-col cols="auto">
            <v-btn
              color="primary"
              variant="elevated"
              :loading="loading"
              prepend-icon="mdi-refresh"
              @click="handleRefresh"
            >
              Refresh
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Error state -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" closable class="mb-4" @click:close="errorMessage = null">
      {{ errorMessage }}
    </v-alert>

    <!-- Loading skeleton -->
    <template v-if="loading">
      <v-row class="mb-4">
        <v-col v-for="n in 3" :key="n" cols="12" md="4">
          <v-skeleton-loader type="card" />
        </v-col>
      </v-row>
      <v-skeleton-loader type="table" />
    </template>

    <!-- Main content -->
    <template v-else-if="performanceData">
      <v-card>
        <v-tabs v-model="activeTab" color="primary">
          <v-tab value="actuals">Actuals</v-tab>
          <v-tab value="projected">Projected</v-tab>
          <v-tab value="possible">Possible</v-tab>
        </v-tabs>

        <v-card-text>
          <!-- Actuals Tab -->
          <v-window v-model="activeTab">
            <v-window-item value="actuals">
              <p class="text-body-2 text-medium-emphasis mb-4">{{ tabDescriptions.actuals }}</p>

              <v-row class="mb-4">
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Total Hours"
                    :value="actualsKpis.totalHours.toFixed(1)"
                    icon="mdi-clock-outline"
                    color="#1976D2"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Total Revenue"
                    :value="formatCurrency(actualsKpis.totalRevenue)"
                    icon="mdi-currency-usd"
                    color="#4CAF50"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Avg Hours/Month"
                    :value="actualsKpis.avgHoursPerMonth.toFixed(1)"
                    icon="mdi-chart-line"
                    color="#FF9800"
                  />
                </v-col>
              </v-row>

              <v-alert v-if="actualsData.rows.length === 0" type="warning" variant="tonal" class="mb-4">
                No actuals data available for the selected filters and date range.
              </v-alert>

              <template v-else>
                <div style="height: 600px; overflow: auto;">
                  <v-data-table
                    :headers="actualsData.headers"
                    :items="actualsData.rows"
                    :items-per-page="-1"
                    density="compact"
                    fixed-header
                    class="elevation-1 timesheet-table"
                  >
                    <template #item.entity="{ item }">
                      <span v-if="item.rowspan" class="entity-name">{{ item.entity }}</span>
                    </template>
                    <template #item.metric="{ item }">
                      <span class="metric-label">{{ item.metric }}</span>
                    </template>
                    <template v-for="month in actualsData.months" :key="month" #[`item.${month}`]="{ item }">
                      <span :class="metricColorClass(item.metric)">
                        {{ formatMetricValue(item[month], item.metric) }}
                      </span>
                    </template>
                    <template #bottom />
                  </v-data-table>
                </div>

                <div class="d-flex justify-end mt-3">
                  <v-btn
                    variant="outlined"
                    prepend-icon="mdi-download"
                    @click="handleDownloadCsv('actuals')"
                  >
                    Download CSV
                  </v-btn>
                </div>
              </template>
            </v-window-item>

            <!-- Projected Tab -->
            <v-window-item value="projected">
              <p class="text-body-2 text-medium-emphasis mb-4">{{ tabDescriptions.projected }}</p>

              <v-row class="mb-4">
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Total Hours"
                    :value="projectedKpis.totalHours.toFixed(1)"
                    icon="mdi-clock-outline"
                    color="#1976D2"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Total Revenue"
                    :value="formatCurrency(projectedKpis.totalRevenue)"
                    icon="mdi-currency-usd"
                    color="#4CAF50"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Avg Hours/Month"
                    :value="projectedKpis.avgHoursPerMonth.toFixed(1)"
                    icon="mdi-chart-line"
                    color="#FF9800"
                  />
                </v-col>
              </v-row>

              <v-alert v-if="projectedData.rows.length === 0" type="warning" variant="tonal" class="mb-4">
                No projected data available for the selected filters and date range.
              </v-alert>

              <template v-else>
                <div style="height: 600px; overflow: auto;">
                  <v-data-table
                    :headers="projectedData.headers"
                    :items="projectedData.rows"
                    :items-per-page="-1"
                    density="compact"
                    fixed-header
                    class="elevation-1 timesheet-table"
                  >
                    <template #item.entity="{ item }">
                      <span v-if="item.rowspan" class="entity-name">{{ item.entity }}</span>
                    </template>
                    <template #item.metric="{ item }">
                      <span class="metric-label">{{ item.metric }}</span>
                    </template>
                    <template v-for="month in projectedData.months" :key="month" #[`item.${month}`]="{ item }">
                      <span :class="metricColorClass(item.metric)">
                        {{ formatMetricValue(item[month], item.metric) }}
                      </span>
                    </template>
                    <template #bottom />
                  </v-data-table>
                </div>

                <div class="d-flex justify-end mt-3">
                  <v-btn
                    variant="outlined"
                    prepend-icon="mdi-download"
                    @click="handleDownloadCsv('projected')"
                  >
                    Download CSV
                  </v-btn>
                </div>
              </template>
            </v-window-item>

            <!-- Possible Tab -->
            <v-window-item value="possible">
              <p class="text-body-2 text-medium-emphasis mb-4">{{ tabDescriptions.possible }}</p>

              <v-row class="mb-4">
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Total Hours"
                    :value="possibleKpis.totalHours.toFixed(1)"
                    icon="mdi-clock-outline"
                    color="#1976D2"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Total Revenue"
                    :value="formatCurrency(possibleKpis.totalRevenue)"
                    icon="mdi-currency-usd"
                    color="#4CAF50"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <KpiCard
                    title="Avg Hours/Month"
                    :value="possibleKpis.avgHoursPerMonth.toFixed(1)"
                    icon="mdi-chart-line"
                    color="#FF9800"
                  />
                </v-col>
              </v-row>

              <v-alert v-if="possibleData.rows.length === 0" type="warning" variant="tonal" class="mb-4">
                No possible capacity data available for the selected filters and date range.
              </v-alert>

              <template v-else>
                <div style="height: 600px; overflow: auto;">
                  <v-data-table
                    :headers="possibleData.headers"
                    :items="possibleData.rows"
                    :items-per-page="-1"
                    density="compact"
                    fixed-header
                    class="elevation-1 timesheet-table"
                  >
                    <template #item.entity="{ item }">
                      <span v-if="item.rowspan" class="entity-name">{{ item.entity }}</span>
                    </template>
                    <template #item.metric="{ item }">
                      <span class="metric-label">{{ item.metric }}</span>
                    </template>
                    <template v-for="month in possibleData.months" :key="month" #[`item.${month}`]="{ item }">
                      <span :class="metricColorClass(item.metric)">
                        {{ formatMetricValue(item[month], item.metric) }}
                      </span>
                    </template>
                    <template #bottom />
                  </v-data-table>
                </div>

                <div class="d-flex justify-end mt-3">
                  <v-btn
                    variant="outlined"
                    prepend-icon="mdi-download"
                    @click="handleDownloadCsv('possible')"
                  >
                    Download CSV
                  </v-btn>
                </div>
              </template>
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>

<style scoped>
:deep(.timesheet-table table) {
  table-layout: fixed;
  width: 100%;
}

.entity-name {
  font-weight: 600;
  text-decoration: none;
}

.metric-label {
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.hrs-cell {
  color: #42a5f5;
}

.rev-cell {
  color: #66bb6a;
}

.days-cell {
  color: #ffb74d;
}

/*
 * Entity column border handling:
 * - 1st row of group (3n+1): no bottom border on entity cell (visually merges with rows below)
 * - 2nd row of group (3n+2): no bottom border on entity cell
 * - 3rd row of group (3n+0): thick group separator border on ALL cells including entity
 */
:deep(.v-data-table tbody tr:nth-child(3n+1) td:first-child),
:deep(.v-data-table tbody tr:nth-child(3n+2) td:first-child) {
  border-bottom: none !important;
}

/* Group separator: thick border on the last row of each 3-row group */
:deep(.v-data-table tbody tr:nth-child(3n) td) {
  border-bottom: 2px solid rgba(var(--v-border-color), 0.3) !important;
}

</style>
