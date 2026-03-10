<script setup lang="ts">
import { ref, computed, inject, onMounted, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { Employee, Allocation, Project, AllocationCreate } from '@/types'

const route = useRoute()
const router = useRouter()
const { get, post, del, error } = useApi()

const employee = inject<Ref<Employee | null>>('employee', ref(null))
const employeeId = computed(() => Number(route.params.id))

// -------------------------------------------------------------------
// Data
// -------------------------------------------------------------------
const allocations = ref<Allocation[]>([])
const projects = ref<Project[]>([])
const monthsData = ref<MonthRecord[]>([])
const dataLoading = ref(true)

interface MonthRecord {
  id: number
  year: number
  month: number
  month_name: string
  working_days: number
  holidays: number
  total_days: number
  quarter: string
}

// -------------------------------------------------------------------
// Year selector
// -------------------------------------------------------------------
const currentYear = new Date().getFullYear()
const selectedYear = ref(currentYear)
const yearOptions = [currentYear - 1, currentYear, currentYear + 1]

// -------------------------------------------------------------------
// Matrix state
// -------------------------------------------------------------------
interface CellValue {
  fte: number
  bill_rate: number | null
  allocation_id: number | null
}

interface MatrixRow {
  project_id: string
  project_name: string
  months: Record<number, CellValue> // keyed 1..12
  isNew: boolean // added via Add Project dialog, no existing allocations
}

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function getCell(months: Record<number, CellValue>, m: number): CellValue {
  return months[m] ?? { fte: 0, bill_rate: null, allocation_id: null }
}

const matrixRows = ref<MatrixRow[]>([])
const originalValues = ref<Map<string, CellValue>>(new Map()) // key: `${project_id}-${month}`
const deletedAllocations = ref<number[]>([]) // allocation IDs to delete on save

const showBillRates = ref(false)
const saving = ref(false)

// Snackbar
const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref('success')

// Add Project Dialog
const addProjectDialog = ref(false)
const selectedProjectToAdd = ref<string | null>(null)

// -------------------------------------------------------------------
// Fetch
// -------------------------------------------------------------------
async function fetchData() {
  dataLoading.value = true
  try {
    const [allocData, projectsData, months] = await Promise.all([
      get<Allocation[]>(`/allocations/?employee_id=${employeeId.value}`),
      get<Project[]>('/projects/'),
      get<MonthRecord[]>(`/months/?year=${selectedYear.value}`),
    ])
    allocations.value = allocData
    projects.value = projectsData
    monthsData.value = months
    buildMatrix()
  } catch {
    // error handled by useApi
  } finally {
    dataLoading.value = false
  }
}

onMounted(fetchData)
watch(employeeId, fetchData)
watch(selectedYear, fetchData)

// -------------------------------------------------------------------
// Build matrix from raw allocations
// -------------------------------------------------------------------
function buildMatrix() {
  const rows = new Map<string, MatrixRow>()
  deletedAllocations.value = []

  // Filter allocations to the selected year
  const yearAllocations = allocations.value.filter((a) => {
    const date = new Date(a.allocation_date)
    return date.getFullYear() === selectedYear.value
  })

  for (const alloc of yearAllocations) {
    if (!rows.has(alloc.project_id)) {
      const proj = projects.value.find((p) => p.id === alloc.project_id)
      const emptyMonths: Record<number, CellValue> = {}
      for (let m = 1; m <= 12; m++) {
        emptyMonths[m] = { fte: 0, bill_rate: null, allocation_id: null }
      }
      rows.set(alloc.project_id, {
        project_id: alloc.project_id,
        project_name: proj?.name ?? alloc.project_name ?? alloc.project_id,
        months: emptyMonths,
        isNew: false,
      })
    }

    const monthNum = new Date(alloc.allocation_date).getMonth() + 1
    const row = rows.get(alloc.project_id)!
    row.months[monthNum] = {
      fte: alloc.allocated_fte,
      bill_rate: alloc.bill_rate,
      allocation_id: alloc.id,
    }
  }

  matrixRows.value = Array.from(rows.values()).sort((a, b) =>
    a.project_name.localeCompare(b.project_name)
  )

  // Snapshot original values
  originalValues.value = new Map()
  for (const row of matrixRows.value) {
    for (let m = 1; m <= 12; m++) {
      const key = `${row.project_id}-${m}`
      originalValues.value.set(key, { ...getCell(row.months, m) })
    }
  }
}

// -------------------------------------------------------------------
// Change detection
// -------------------------------------------------------------------
const changedCells = computed(() => {
  const changes: { project_id: string; month: number; cell: CellValue; original: CellValue | null }[] = []
  for (const row of matrixRows.value) {
    for (let m = 1; m <= 12; m++) {
      const key = `${row.project_id}-${m}`
      const orig = originalValues.value.get(key)
      const curr = getCell(row.months, m)
      if (!orig) {
        if (curr.fte > 0) {
          changes.push({ project_id: row.project_id, month: m, cell: curr, original: null })
        }
      } else if (curr.fte !== orig.fte || curr.bill_rate !== orig.bill_rate) {
        changes.push({ project_id: row.project_id, month: m, cell: curr, original: orig })
      }
    }
  }
  return changes
})

const unsavedCount = computed(() => changedCells.value.length + deletedAllocations.value.length)
const hasChanges = computed(() => unsavedCount.value > 0)

// -------------------------------------------------------------------
// Cell styling
// -------------------------------------------------------------------
function cellBgColor(fte: number): string {
  if (fte > 1.0) return '#FFCDD2'   // light red
  if (fte >= 0.5) return '#C8E6C9'  // light green
  if (fte > 0) return '#BBDEFB'     // light blue
  return 'transparent'
}

function totalBgColor(total: number): string {
  if (total > 1.0) return '#FFCDD2'
  if (total >= 0.8) return '#C8E6C9'
  if (total > 0) return '#FFF9C4'
  return 'transparent'
}

// -------------------------------------------------------------------
// Monthly totals
// -------------------------------------------------------------------
function monthTotal(month: number): number {
  let sum = 0
  for (const row of matrixRows.value) {
    sum += getCell(row.months, month).fte
  }
  return sum
}

function monthTotalLabel(month: number): string {
  const total = monthTotal(month)
  const target = employee.value?.target_allocation ?? 1.0
  const pct = target > 0 ? Math.round((total / target) * 100) : 0
  return `${total.toFixed(2)} (${pct}%)`
}

// Row totals
function rowTotalFte(row: MatrixRow): number {
  let sum = 0
  for (let m = 1; m <= 12; m++) {
    sum += getCell(row.months, m).fte
  }
  return sum
}

// -------------------------------------------------------------------
// Working days helpers
// -------------------------------------------------------------------
function workingDaysForMonth(month: number): number {
  const rec = monthsData.value.find((m) => m.month === month)
  return rec ? rec.working_days - rec.holidays : 22 // default fallback
}

function totalWorkingDaysInYear(): number {
  let total = 0
  for (let m = 1; m <= 12; m++) {
    total += workingDaysForMonth(m)
  }
  return total
}

// -------------------------------------------------------------------
// KPI computations
// -------------------------------------------------------------------
const targetAllocation = computed(() => employee.value?.target_allocation ?? 1.0)

const possibleHours = computed(() => {
  return targetAllocation.value * totalWorkingDaysInYear() * 8
})

const allocatedHours = computed(() => {
  let total = 0
  for (const row of matrixRows.value) {
    for (let m = 1; m <= 12; m++) {
      total += getCell(row.months, m).fte * workingDaysForMonth(m) * 8
    }
  }
  return total
})

const allocationPct = computed(() => {
  return possibleHours.value > 0 ? (allocatedHours.value / possibleHours.value) * 100 : 0
})

const varianceHours = computed(() => allocatedHours.value - possibleHours.value)

// -------------------------------------------------------------------
// Project breakdown table
// -------------------------------------------------------------------
const breakdownHeaders = [
  { title: 'Project', key: 'project_name', sortable: true },
  { title: 'Total FTE', key: 'total_fte', sortable: true },
  { title: 'Total Hours', key: 'total_hours', sortable: true },
  { title: 'Avg Monthly FTE', key: 'avg_fte', sortable: true },
]

const breakdownItems = computed(() => {
  return matrixRows.value.map((row) => {
    let totalFte = 0
    let totalHours = 0
    let monthsActive = 0
    for (let m = 1; m <= 12; m++) {
      const fte = getCell(row.months, m).fte
      totalFte += fte
      totalHours += fte * workingDaysForMonth(m) * 8
      if (fte > 0) monthsActive++
    }
    return {
      project_id: row.project_id,
      project_name: row.project_name,
      total_fte: totalFte.toFixed(2),
      total_hours: Math.round(totalHours).toLocaleString(),
      avg_fte: monthsActive > 0 ? (totalFte / monthsActive).toFixed(2) : '0.00',
    }
  })
})

// -------------------------------------------------------------------
// Pie chart data
// -------------------------------------------------------------------
const pieData = computed(() => {
  const labels: string[] = []
  const values: number[] = []
  for (const row of matrixRows.value) {
    let hours = 0
    for (let m = 1; m <= 12; m++) {
      hours += getCell(row.months, m).fte * workingDaysForMonth(m) * 8
    }
    if (hours > 0) {
      labels.push(row.project_name)
      values.push(Math.round(hours))
    }
  }
  if (labels.length === 0) return []
  return [
    {
      type: 'pie' as const,
      labels,
      values,
      hole: 0.4,
      textinfo: 'label+percent' as const,
      hovertemplate: '%{label}: %{value} hours (%{percent})<extra></extra>',
    },
  ]
})

const pieLayout = { height: 300, showlegend: true, legend: { orientation: 'h' as const, y: -0.15 } }

// -------------------------------------------------------------------
// Add Project
// -------------------------------------------------------------------
const projectItemsForAdd = computed(() => {
  const existingIds = new Set(matrixRows.value.map((r) => r.project_id))
  return projects.value
    .filter((p) => !existingIds.has(p.id))
    .map((p) => ({
      title: `${p.id} - ${p.name}`,
      value: p.id,
    }))
})

function openAddProjectDialog() {
  selectedProjectToAdd.value = null
  addProjectDialog.value = true
}

function confirmAddProject() {
  if (!selectedProjectToAdd.value) return
  const proj = projects.value.find((p) => p.id === selectedProjectToAdd.value)
  if (!proj) return

  const emptyMonths: Record<number, CellValue> = {}
  for (let m = 1; m <= 12; m++) {
    emptyMonths[m] = { fte: 0, bill_rate: null, allocation_id: null }
  }

  matrixRows.value.push({
    project_id: proj.id,
    project_name: proj.name,
    months: emptyMonths,
    isNew: true,
  })

  addProjectDialog.value = false
}

// -------------------------------------------------------------------
// Remove project row
// -------------------------------------------------------------------
function removeProjectRow(index: number) {
  const row = matrixRows.value[index]
  if (!row) return
  for (let m = 1; m <= 12; m++) {
    const allocId = getCell(row.months, m).allocation_id
    if (allocId !== null) {
      deletedAllocations.value.push(allocId)
    }
  }
  matrixRows.value.splice(index, 1)
}

// -------------------------------------------------------------------
// Save / Discard
// -------------------------------------------------------------------
async function saveChanges() {
  saving.value = true
  try {
    // 1. Delete removed allocations
    const deletePromises = deletedAllocations.value.map((id) =>
      del(`/allocations/${id}`)
    )
    await Promise.all(deletePromises)

    // 2. Upsert changed cells
    const upsertPromises = changedCells.value.map((change) => {
      const allocationDate = `${selectedYear.value}-${String(change.month).padStart(2, '0')}-01`
      const payload: AllocationCreate = {
        project_id: change.project_id,
        employee_id: employeeId.value,
        allocated_fte: change.cell.fte,
        allocation_date: allocationDate,
        bill_rate: change.cell.bill_rate ?? undefined,
      }
      return post<Allocation>('/allocations/', payload)
    })
    await Promise.all(upsertPromises)

    snackbarText.value = `Saved ${changedCells.value.length + deletedAllocations.value.length} changes successfully`
    snackbarColor.value = 'success'
    snackbar.value = true

    // Re-fetch
    await fetchData()
  } catch {
    snackbarText.value = error.value || 'Failed to save changes'
    snackbarColor.value = 'error'
    snackbar.value = true
  } finally {
    saving.value = false
  }
}

function discardChanges() {
  buildMatrix()
}

// -------------------------------------------------------------------
// Format helpers
// -------------------------------------------------------------------
function formatHours(val: number): string {
  return Math.round(val).toLocaleString()
}

function formatVariance(val: number): string {
  const sign = val >= 0 ? '+' : ''
  return `${sign}${Math.round(val).toLocaleString()} hrs`
}
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="dataLoading" type="card, card, table" />

    <template v-else>
      <!-- Error -->
      <v-alert v-if="error" type="error" closable class="mb-4">
        {{ error }}
      </v-alert>

      <!-- Controls Row -->
      <v-row class="mb-3 align-center">
        <v-col cols="auto">
          <v-select
            v-model="selectedYear"
            :items="yearOptions"
            label="Year"
            density="compact"
            hide-details
            style="min-width: 120px"
          />
        </v-col>
        <v-col cols="auto">
          <v-btn
            color="primary"
            size="small"
            prepend-icon="mdi-plus"
            @click="openAddProjectDialog"
          >
            Add Project
          </v-btn>
        </v-col>
        <v-col cols="auto">
          <v-switch
            v-model="showBillRates"
            label="Show Bill Rates"
            density="compact"
            hide-details
            color="primary"
          />
        </v-col>
        <v-spacer />
        <v-col cols="auto" class="d-flex align-center ga-2">
          <v-chip
            v-if="hasChanges"
            color="warning"
            size="small"
            prepend-icon="mdi-pencil"
          >
            {{ unsavedCount }} unsaved change{{ unsavedCount !== 1 ? 's' : '' }}
          </v-chip>
          <v-btn
            v-if="hasChanges"
            variant="text"
            size="small"
            @click="discardChanges"
          >
            Discard
          </v-btn>
          <v-btn
            v-if="hasChanges"
            color="primary"
            size="small"
            :loading="saving"
            prepend-icon="mdi-content-save"
            @click="saveChanges"
          >
            Save Changes
          </v-btn>
        </v-col>
      </v-row>

      <!-- FTE Matrix -->
      <v-card class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold pb-0">
          FTE Matrix - {{ selectedYear }}
        </v-card-title>
        <v-card-text class="pa-0">
          <div class="fte-matrix-wrapper">
            <table class="fte-matrix">
              <thead>
                <tr>
                  <th class="sticky-col project-col">Project</th>
                  <th
                    v-for="(label, idx) in MONTH_LABELS"
                    :key="idx"
                    class="month-col text-center"
                  >
                    {{ label }}
                  </th>
                  <th class="total-col text-center">Total</th>
                  <th class="action-col" />
                </tr>
              </thead>
              <tbody>
                <!-- No data -->
                <tr v-if="matrixRows.length === 0">
                  <td :colspan="15" class="text-center text-medium-emphasis pa-6">
                    No allocations for {{ selectedYear }}. Click "Add Project" to begin.
                  </td>
                </tr>

                <!-- Project rows -->
                <tr
                  v-for="(row, rowIdx) in matrixRows"
                  :key="row.project_id"
                  :class="{ 'alt-row': rowIdx % 2 === 1 }"
                >
                  <td class="sticky-col project-col">
                    <a
                      href="#"
                      class="text-primary text-decoration-none text-caption font-weight-medium"
                      @click.prevent="router.push(`/projects/${row.project_id}`)"
                    >
                      {{ row.project_name }}
                    </a>
                  </td>
                  <td
                    v-for="m in 12"
                    :key="m"
                    class="month-cell"
                    :style="{ backgroundColor: cellBgColor(row.months[m]!.fte) }"
                  >
                    <v-text-field
                      v-model.number="row.months[m]!.fte"
                      type="number"
                      :min="0"
                      :max="2"
                      :step="0.05"
                      density="compact"
                      hide-details
                      variant="plain"
                      class="fte-input"
                    />
                    <div v-if="showBillRates" class="bill-rate-display">
                      <v-text-field
                        v-model.number="row.months[m]!.bill_rate"
                        type="number"
                        :min="0"
                        :step="5"
                        density="compact"
                        hide-details
                        variant="plain"
                        prefix="$"
                        class="bill-rate-input"
                      />
                    </div>
                  </td>
                  <td class="total-cell text-center font-weight-medium">
                    {{ rowTotalFte(row).toFixed(2) }}
                  </td>
                  <td class="action-col">
                    <v-btn
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      color="error"
                      @click="removeProjectRow(rowIdx)"
                    />
                  </td>
                </tr>

                <!-- Totals row -->
                <tr v-if="matrixRows.length > 0" class="totals-row">
                  <td class="sticky-col project-col font-weight-bold">Total FTE</td>
                  <td
                    v-for="m in 12"
                    :key="'total-' + m"
                    class="month-cell text-center font-weight-bold"
                    :style="{ backgroundColor: totalBgColor(monthTotal(m)) }"
                  >
                    {{ monthTotalLabel(m) }}
                  </td>
                  <td class="total-cell text-center font-weight-bold">
                    <!-- Grand total not meaningful as sum of monthly totals -->
                  </td>
                  <td class="action-col" />
                </tr>
              </tbody>
            </table>
          </div>
        </v-card-text>
      </v-card>

      <!-- Allocation Overview -->
      <v-card class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold">
          Allocation Overview - {{ selectedYear }}
        </v-card-title>
        <v-card-text>
          <!-- KPI Cards -->
          <v-row class="mb-4">
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Possible Hours"
                :value="formatHours(possibleHours)"
                :subtitle="`Target: ${(targetAllocation * 100).toFixed(0)}% FTE`"
                icon="mdi-clock-outline"
                color="#1976D2"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Allocated Hours"
                :value="formatHours(allocatedHours)"
                icon="mdi-calendar-check"
                color="#7B1FA2"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Allocation %"
                :value="allocationPct.toFixed(0) + '%'"
                icon="mdi-chart-pie"
                :color="allocationPct > 100 ? '#FF5252' : allocationPct >= 80 ? '#4CAF50' : '#FF9800'"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <KpiCard
                title="Variance"
                :value="formatVariance(varianceHours)"
                icon="mdi-swap-vertical"
                :color="varianceHours > 0 ? '#FF5252' : varianceHours < 0 ? '#FF9800' : '#4CAF50'"
              />
            </v-col>
          </v-row>

          <!-- Project Breakdown + Pie chart -->
          <v-row>
            <v-col cols="12" md="7">
              <v-card variant="outlined">
                <v-card-title class="text-subtitle-2">Project Breakdown</v-card-title>
                <v-card-text class="pa-0">
                  <v-data-table
                    :headers="breakdownHeaders"
                    :items="breakdownItems"
                    density="compact"
                    :items-per-page="-1"
                    hide-default-footer
                    hover
                    no-data-text="No project allocations"
                  >
                    <template #item.project_name="{ item }">
                      <a
                        href="#"
                        class="text-primary text-decoration-none"
                        @click.prevent="router.push(`/projects/${item.project_id}`)"
                      >
                        {{ item.project_name }}
                      </a>
                    </template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="12" md="5">
              <v-card variant="outlined">
                <v-card-title class="text-subtitle-2">Hours by Project</v-card-title>
                <v-card-text>
                  <PlotlyChart
                    :data="pieData"
                    :layout="pieLayout"
                  />
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </template>

    <!-- Add Project Dialog -->
    <v-dialog v-model="addProjectDialog" max-width="500">
      <v-card>
        <v-card-title>Add Project to Matrix</v-card-title>
        <v-card-text>
          <v-autocomplete
            v-model="selectedProjectToAdd"
            :items="projectItemsForAdd"
            item-title="title"
            item-value="value"
            label="Select a project"
            density="compact"
            auto-select-first
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="addProjectDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :disabled="!selectedProjectToAdd"
            @click="confirmAddProject"
          >
            Add
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar
      v-model="snackbar"
      :color="snackbarColor"
      :timeout="3000"
    >
      {{ snackbarText }}
      <template #actions>
        <v-btn variant="text" @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<style scoped>
.fte-matrix-wrapper {
  overflow-x: auto;
  position: relative;
}

.fte-matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
  min-width: 900px;
}

.fte-matrix th,
.fte-matrix td {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  padding: 4px 6px;
  white-space: nowrap;
}

.fte-matrix thead th {
  background: rgb(var(--v-theme-surface));
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
  border-bottom: 2px solid rgba(var(--v-border-color), 0.24);
}

.sticky-col {
  position: sticky;
  left: 0;
  z-index: 3;
  background: rgb(var(--v-theme-surface));
  min-width: 160px;
  max-width: 200px;
}

.project-col {
  padding-left: 12px !important;
}

.month-col {
  min-width: 80px;
  width: 80px;
}

.month-cell {
  padding: 2px 4px !important;
  vertical-align: top;
}

.total-col {
  min-width: 70px;
  font-weight: 600;
}

.total-cell {
  background: rgba(var(--v-theme-surface-variant), 0.3);
  font-weight: 600;
}

.action-col {
  width: 36px;
  min-width: 36px;
  text-align: center;
}

.alt-row {
  background: rgba(var(--v-theme-surface-variant), 0.08);
}

.alt-row .sticky-col {
  background: rgba(var(--v-theme-surface-variant), 0.08);
}

.totals-row {
  border-top: 2px solid rgba(var(--v-border-color), 0.24);
}

.totals-row td {
  font-size: 0.75rem;
}

.totals-row .sticky-col {
  background: rgb(var(--v-theme-surface));
}

.fte-input {
  max-width: 70px;
  font-size: 0.8125rem;
}

.fte-input :deep(input) {
  text-align: center;
  padding: 2px 0;
  min-height: 24px;
}

.fte-input :deep(.v-field__input) {
  padding: 0;
  min-height: 24px;
}

.bill-rate-display {
  border-top: 1px dashed rgba(var(--v-border-color), 0.12);
  margin-top: 2px;
  padding-top: 2px;
}

.bill-rate-input {
  max-width: 70px;
  font-size: 0.6875rem;
  opacity: 0.7;
}

.bill-rate-input :deep(input) {
  text-align: center;
  padding: 1px 0;
  min-height: 20px;
}

.bill-rate-input :deep(.v-field__input) {
  padding: 0;
  min-height: 20px;
}

.bill-rate-input :deep(.v-field__prepend-inner) {
  padding: 0;
  font-size: 0.625rem;
}
</style>
