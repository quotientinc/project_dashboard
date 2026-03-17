<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import { formatCurrencyFull } from '@/utils/helpers'
import type { Project, ProjectUtilizationEntry } from '@/types'

const router = useRouter()
const { get, post, error } = useApi()

// Data
const projects = ref<Project[]>([])
const utilizationData = ref<ProjectUtilizationEntry[]>([])
const dataLoaded = ref(false)

// Filters
const selectedStatuses = ref<string[]>(['Active', 'Future', 'Completed'])
const statusOptions = ['Active', 'Future', 'Completed', 'On Hold', 'Cancelled']
const searchTerm = ref('')
const dateFilter = ref(`Active in ${new Date().getFullYear()}`)
const dateFilterOptions = [
  `Active in ${new Date().getFullYear()}`,
  'All Projects',
]

// Utilization filter
const utilizationFilter = ref('All')
const utilizationFilterOptions = [
  'All',
  '<70% Under-Utilized',
  '<50% Severely',
  '>=90% Well Utilized',
]

// Add Project Dialog
const addProjectDialog = ref(false)
const addProjectLoading = ref(false)
const addProjectError = ref<string | null>(null)
const addProjectSuccess = ref(false)
const newProject = ref({
  id: '',
  name: '',
  client: '',
  project_manager: '',
  status: 'Active',
  start_date: '',
  end_date: '',
  quoted_value: null as number | null,
  awarded_value: null as number | null,
  billable: true,
})

function resetNewProject() {
  newProject.value = {
    id: '',
    name: '',
    client: '',
    project_manager: '',
    status: 'Active',
    start_date: '',
    end_date: '',
    quoted_value: null,
    awarded_value: null,
    billable: true,
  }
  addProjectError.value = null
}

function openAddDialog() {
  resetNewProject()
  addProjectDialog.value = true
}

async function submitNewProject() {
  if (!newProject.value.id || !newProject.value.name) {
    addProjectError.value = 'Project ID and Name are required.'
    return
  }
  addProjectLoading.value = true
  addProjectError.value = null
  try {
    const payload: Record<string, unknown> = {
      id: newProject.value.id,
      name: newProject.value.name,
      status: newProject.value.status || null,
      billable: newProject.value.billable ? 1 : 0,
    }
    if (newProject.value.client) payload.client = newProject.value.client
    if (newProject.value.project_manager) payload.project_manager = newProject.value.project_manager
    if (newProject.value.start_date) payload.start_date = newProject.value.start_date
    if (newProject.value.end_date) payload.end_date = newProject.value.end_date
    if (newProject.value.quoted_value != null) payload.quoted_value = newProject.value.quoted_value
    if (newProject.value.awarded_value != null) payload.awarded_value = newProject.value.awarded_value

    await post('/projects/', payload)
    addProjectDialog.value = false
    addProjectSuccess.value = true
    setTimeout(() => { addProjectSuccess.value = false }, 4000)
    await fetchData()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to create project.'
    addProjectError.value = msg
  } finally {
    addProjectLoading.value = false
  }
}

// Fetch data
async function fetchData() {
  try {
    const now = new Date()
    const currentYear = now.getFullYear()
    const ytdEnd = `${currentYear}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    const [projectsData, utilizationResult] = await Promise.all([
      get<Project[]>('/projects/'),
      get<ProjectUtilizationEntry[]>(
        `/analytics/project-utilization?start_date=${currentYear}-01-01&end_date=${ytdEnd}`
      ),
    ])
    projects.value = projectsData
    utilizationData.value = utilizationResult
    dataLoaded.value = true
  } catch {
    // error is set by useApi
  }
}

onMounted(fetchData)

// Build utilization lookup
const utilizationMap = computed(() => {
  const map = new Map<string, ProjectUtilizationEntry>()
  for (const u of utilizationData.value) {
    map.set(u.project_id, u)
  }
  return map
})

// Filtered projects
const filteredProjects = computed(() => {
  let result = projects.value

  // Status filter
  if (selectedStatuses.value.length > 0) {
    result = result.filter((p) => selectedStatuses.value.includes(p.status ?? ''))
  }

  // Date filter
  const currentYear = new Date().getFullYear()
  if (dateFilter.value === `Active in ${currentYear}`) {
    const yearStart = `${currentYear}-01-01`
    const yearEnd = `${currentYear}-12-31`
    result = result.filter(
      (p) =>
        p.start_date &&
        p.end_date &&
        p.start_date <= yearEnd &&
        p.end_date >= yearStart
    )
  }

  // Search filter
  if (searchTerm.value) {
    const term = searchTerm.value.toLowerCase()
    result = result.filter(
      (p) =>
        p.id.toLowerCase().includes(term) ||
        (p.name ?? '').toLowerCase().includes(term) ||
        (p.client ?? '').toLowerCase().includes(term) ||
        (p.project_manager ?? '').toLowerCase().includes(term)
    )
  }

  // Utilization filter
  if (utilizationFilter.value !== 'All') {
    result = result.filter((p) => {
      const u = utilizationMap.value.get(p.id)
      const pct = u?.utilization_pct ?? null
      if (pct == null) return false
      switch (utilizationFilter.value) {
        case '<70% Under-Utilized':
          return pct < 70
        case '<50% Severely':
          return pct < 50
        case '>=90% Well Utilized':
          return pct >= 90
        default:
          return true
      }
    })
  }

  return result
})

// Grid row data with utilization merged in
const rowData = computed(() =>
  filteredProjects.value.map((p) => {
    const util = utilizationMap.value.get(p.id)
    const budgetPctUsed =
      p.quoted_value && p.quoted_value > 0 && p.budget_used != null
        ? (p.budget_used / p.quoted_value) * 100
        : null
    return {
      ...p,
      budget_pct_used: budgetPctUsed,
      utilization_pct: util?.utilization_pct ?? null,
      revenue_gap: util?.revenue_gap != null ? Math.max(util.revenue_gap, 0) : null,
    }
  })
)

// Summary metrics
const activeCount = computed(() => filteredProjects.value.filter((p) => p.status === 'Active').length)
const futureCount = computed(() => filteredProjects.value.filter((p) => p.status === 'Future').length)
const completedCount = computed(() => filteredProjects.value.filter((p) => p.status === 'Completed').length)
const totalQuoted = computed(() =>
  filteredProjects.value.reduce((sum, p) => sum + (p.quoted_value ?? 0), 0)
)
const underUtilizedCount = computed(() => {
  return filteredProjects.value.filter((p) => {
    const u = utilizationMap.value.get(p.id)
    return u?.utilization_pct != null && u.utilization_pct < 70
  }).length
})

// Status color mapping
function statusColor(status: string | null): string {
  switch (status) {
    case 'Active':
      return 'success'
    case 'Completed':
      return 'info'
    case 'On Hold':
      return 'warning'
    case 'Future':
      return 'secondary'
    case 'Cancelled':
      return 'error'
    default:
      return 'default'
  }
}

// Vuetify data table headers
const headers = [
  { title: 'Project Code', key: 'id', minWidth: '160px' },
  { title: 'Project Name', key: 'name', minWidth: '200px' },
  { title: 'Client', key: 'client', minWidth: '140px' },
  { title: 'Status', key: 'status', minWidth: '120px' },
  { title: 'PM', key: 'project_manager', minWidth: '140px' },
  { title: 'Quoted Value', key: 'quoted_value', minWidth: '130px', align: 'end' as const },
  { title: 'Awarded Value', key: 'awarded_value', minWidth: '130px', align: 'end' as const },
  { title: 'Budget Used', key: 'budget_used', minWidth: '130px', align: 'end' as const },
  { title: 'Start Date', key: 'start_date', minWidth: '115px' },
  { title: 'End Date', key: 'end_date', minWidth: '115px' },
  { title: 'Budget % Used', key: 'budget_pct_used', minWidth: '130px', align: 'end' as const },
  { title: 'Utilization %', key: 'utilization_pct', minWidth: '130px', align: 'end' as const },
  { title: 'Revenue Gap', key: 'revenue_gap', minWidth: '130px', align: 'end' as const },
]

// Color helpers for table chips
function budgetPctChipColor(value: number): string {
  if (value > 100) return 'error'
  if (value >= 80) return 'warning'
  return 'success'
}

function utilizationPctChipColor(value: number): string {
  if (value >= 90) return 'success'
  if (value >= 70) return 'warning'
  if (value >= 50) return 'orange'
  return 'error'
}

function onRowClicked(item: Record<string, unknown>) {
  if (item.id) {
    router.push({ name: 'project-overview', params: { id: String(item.id) } })
  }
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4 font-weight-bold">Projects</h1>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openAddDialog">
        Add Project
      </v-btn>
    </div>

    <!-- Success snackbar -->
    <v-snackbar v-model="addProjectSuccess" color="success" :timeout="4000" location="top">
      Project created successfully.
    </v-snackbar>

    <!-- Error alert -->
    <v-alert v-if="error" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Filters Row -->
    <v-row class="mb-4">
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="selectedStatuses"
          label="Status"
          :items="statusOptions"
          multiple
          chips
          closable-chips
        />
      </v-col>
      <v-col cols="12" sm="6" md="2">
        <v-select
          v-model="dateFilter"
          label="Date Range"
          :items="dateFilterOptions"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="utilizationFilter"
          label="Utilization"
          :items="utilizationFilterOptions"
        />
      </v-col>
      <v-col cols="12" sm="6" md="4">
        <v-text-field
          v-model="searchTerm"
          prepend-inner-icon="mdi-magnify"
          label="Search projects..."
          clearable
          @click:clear="searchTerm = ''"
        />
      </v-col>
    </v-row>

    <!-- Summary Metrics -->
    <v-row class="mb-4" v-if="dataLoaded">
      <v-col>
        <v-card class="pa-3 text-center">
          <div class="text-caption text-medium-emphasis">Active</div>
          <div class="text-h6 font-weight-bold text-success">{{ activeCount }}</div>
        </v-card>
      </v-col>
      <v-col>
        <v-card class="pa-3 text-center">
          <div class="text-caption text-medium-emphasis">Future</div>
          <div class="text-h6 font-weight-bold">{{ futureCount }}</div>
        </v-card>
      </v-col>
      <v-col>
        <v-card class="pa-3 text-center">
          <div class="text-caption text-medium-emphasis">Completed</div>
          <div class="text-h6 font-weight-bold text-info">{{ completedCount }}</div>
        </v-card>
      </v-col>
      <v-col>
        <v-card class="pa-3 text-center">
          <div class="text-caption text-medium-emphasis">Total Quoted</div>
          <div class="text-h6 font-weight-bold">${{ (totalQuoted / 1e6).toFixed(1) }}M</div>
        </v-card>
      </v-col>
      <v-col>
        <v-card class="pa-3 text-center">
          <div class="text-caption text-medium-emphasis">Under-Utilized</div>
          <div class="text-h6 font-weight-bold text-warning">{{ underUtilizedCount }}</div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Loading skeleton -->
    <v-skeleton-loader v-if="!dataLoaded" type="table" class="mb-4" />

    <!-- Projects Table -->
    <v-card v-else>
      <v-card-text class="pa-0">
        <div class="d-flex align-center pa-3 pb-0">
          <div class="text-caption text-medium-emphasis">
            Showing {{ filteredProjects.length }} of {{ projects.length }} projects
            &mdash; Click a row to view details
          </div>
          <v-spacer />
          <v-menu location="bottom end" :close-on-content-click="false" max-width="420">
            <template v-slot:activator="{ props }">
              <v-btn v-bind="props" variant="text" size="small" prepend-icon="mdi-information-outline" color="primary">
                How is utilization calculated?
              </v-btn>
            </template>
            <v-card class="pa-4">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-0 mb-2">
                How is Utilization Calculated?
              </v-card-title>
              <v-card-text class="pa-0 text-body-2">
                <p class="mb-2">
                  <strong>Utilization %</strong> = (Actual Billable Hours / Allocated Hours) &times; 100
                </p>
                <ul class="mb-2" style="padding-left: 20px;">
                  <li><strong>Allocated Hours</strong>: From FTE allocations &mdash; <code>allocated_fte &times; working_days &times; 8 hrs/day</code> summed across all team members. For the current (partial) month, allocated hours are prorated to elapsed working days.</li>
                  <li><strong>Actual Billable Hours</strong>: From time entries marked as billable</li>
                  <li><strong>Revenue Gap</strong>: Dollar value of unused capacity &mdash; <code>(Allocated Hours &minus; Actual Billable Hours) &times; avg bill rate</code>. The avg bill rate is the blended rate across all team members on the project, weighted by their allocated hours.</li>
                </ul>
                <p class="mb-1 font-weight-medium">Color Key:</p>
                <ul class="mb-2" style="padding-left: 20px; list-style: none;">
                  <li>&#x1F7E2; Green (&ge;90%): Well utilized</li>
                  <li>&#x1F7E1; Yellow (70-89%): Minor risk &mdash; some unused capacity</li>
                  <li>&#x1F7E0; Orange (50-69%): Medium risk &mdash; significant money on the table</li>
                  <li>&#x1F534; Red (&lt;50%): Severely under-utilized</li>
                </ul>
                <p class="mb-1"><strong>N/A</strong> means the project has no FTE allocations, so utilization cannot be calculated.</p>
                <p class="mb-0 font-italic text-medium-emphasis">Note: Based on YTD (Year-to-Date) data.</p>
              </v-card-text>
            </v-card>
          </v-menu>
        </div>
        <v-data-table
          :headers="headers"
          :items="rowData"
          :items-per-page="25"
          density="compact"
          hover
          class="cursor-pointer"
          @click:row="(_e: Event, { item }: { item: any }) => onRowClicked(item)"
        >
          <template #item.status="{ value }">
            <v-chip
              :color="statusColor(value)"
              size="small"
              label
            >
              {{ value }}
            </v-chip>
          </template>

          <template #item.quoted_value="{ value }">
            {{ value != null ? formatCurrencyFull(value) : '' }}
          </template>

          <template #item.awarded_value="{ value }">
            {{ value != null ? formatCurrencyFull(value) : '' }}
          </template>

          <template #item.budget_used="{ value }">
            {{ value != null ? formatCurrencyFull(value) : '' }}
          </template>

          <template #item.budget_pct_used="{ value }">
            <v-chip
              v-if="value != null"
              :color="budgetPctChipColor(value)"
              size="x-small"
              label
              variant="tonal"
            >
              {{ value.toFixed(1) }}%
            </v-chip>
            <span v-else class="text-grey">N/A</span>
          </template>

          <template #item.utilization_pct="{ value }">
            <v-chip
              v-if="value != null"
              :color="utilizationPctChipColor(value)"
              size="x-small"
              label
              variant="tonal"
            >
              {{ value.toFixed(1) }}%
            </v-chip>
            <span v-else class="text-grey">N/A</span>
          </template>

          <template #item.revenue_gap="{ value }">
            <span :class="value == null ? 'text-grey' : ''">
              {{ value != null ? '$' + Math.round(value).toLocaleString() : 'N/A' }}
            </span>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Add Project Dialog -->
    <v-dialog v-model="addProjectDialog" max-width="650" persistent>
      <v-card>
        <v-card-title class="text-h5 pa-4 pb-2">
          <v-icon icon="mdi-folder-plus" class="mr-2" />
          Add New Project
        </v-card-title>

        <v-card-text class="pa-4">
          <v-alert v-if="addProjectError" type="error" variant="tonal" class="mb-4" closable @click:close="addProjectError = null">
            {{ addProjectError }}
          </v-alert>

          <v-row dense>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="newProject.id"
                label="Project ID *"
                hint="e.g. 220300.00.001.00"
                persistent-hint
                :rules="[v => !!v || 'Required']"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="newProject.name"
                label="Project Name *"
                :rules="[v => !!v || 'Required']"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="newProject.client"
                label="Client"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="newProject.project_manager"
                label="Project Manager"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-select
                v-model="newProject.status"
                label="Status"
                :items="statusOptions"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-switch
                v-model="newProject.billable"
                label="Billable"
                color="primary"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="newProject.start_date"
                label="Start Date"
                type="date"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="newProject.end_date"
                label="End Date"
                type="date"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="newProject.quoted_value"
                label="Quoted Value"
                type="number"
                prefix="$"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="newProject.awarded_value"
                label="Awarded Value"
                type="number"
                prefix="$"
              />
            </v-col>
          </v-row>
        </v-card-text>

        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="addProjectDialog = false" :disabled="addProjectLoading">
            Cancel
          </v-btn>
          <v-btn color="primary" variant="flat" @click="submitNewProject" :loading="addProjectLoading">
            Create Project
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
