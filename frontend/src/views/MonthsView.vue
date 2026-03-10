<script setup lang="ts">
/**
 * Months calendar management page.
 *
 * Displays a 4x3 grid of month cards grouped by year, with editing
 * capabilities for working days and holidays. Supports generating
 * all 12 months for a new year.
 */
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'

// ---- Types ----

interface MonthRecord {
  id: number
  year: number
  month: number
  month_name: string
  quarter: string
  total_days: number
  working_days: number
  holidays: number
  created_at: string | null
  updated_at: string | null
}

// ---- State ----

const api = useApi()

const months = ref<MonthRecord[]>([])
const loading = ref(true)
const errorMessage = ref<string | null>(null)

// Year navigation
const selectedYear = ref(new Date().getFullYear())
const availableYears = computed(() => {
  const years = [...new Set(months.value.map((m) => m.year))].sort((a, b) => b - a)
  if (!years.includes(selectedYear.value)) {
    years.push(selectedYear.value)
    years.sort((a, b) => b - a)
  }
  return years
})

// Filtered months for selected year
const filteredMonths = computed(() => {
  return months.value
    .filter((m) => m.year === selectedYear.value)
    .sort((a, b) => a.month - b.month)
})

// Edit dialog
const editDialog = ref(false)
const editingMonth = ref<MonthRecord | null>(null)
const editForm = ref({
  working_days: 0,
  holidays: 0,
})
const saving = ref(false)
const saveError = ref<string | null>(null)

// Add/Generate year dialog
const addDialog = ref(false)
const generateYear = ref(new Date().getFullYear())
const copyHolidays = ref(false)
const generating = ref(false)
const generateError = ref<string | null>(null)

// Delete confirmation
const deleteDialog = ref(false)
const deletingMonth = ref<MonthRecord | null>(null)
const deleting = ref(false)

// ---- Data fetching ----

async function fetchMonths() {
  loading.value = true
  errorMessage.value = null

  try {
    months.value = await api.get<MonthRecord[]>('/months/')
    // Auto-select the most recent year if current year has no data
    if (filteredMonths.value.length === 0 && availableYears.value.length > 0) {
      selectedYear.value = availableYears.value[0] ?? selectedYear.value
    }
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    errorMessage.value = axiosErr.response?.data?.detail || axiosErr.message || 'Failed to load months'
  } finally {
    loading.value = false
  }
}

// ---- Edit month ----

function openEditDialog(month: MonthRecord) {
  editingMonth.value = { ...month }
  editForm.value = {
    working_days: month.working_days,
    holidays: month.holidays,
  }
  saveError.value = null
  editDialog.value = true
}

async function saveMonth() {
  if (!editingMonth.value) return

  saving.value = true
  saveError.value = null

  try {
    await api.put(`/months/${editingMonth.value.id}`, {
      working_days: editForm.value.working_days,
      holidays: editForm.value.holidays,
    })
    editDialog.value = false
    await fetchMonths()
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    saveError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Failed to save'
  } finally {
    saving.value = false
  }
}

// ---- Generate year ----

function openAddDialog() {
  generateYear.value = new Date().getFullYear()
  copyHolidays.value = false
  generateError.value = null
  addDialog.value = true
}

async function submitGenerateYear() {
  generating.value = true
  generateError.value = null

  try {
    await api.post('/months/generate-year', {
      year: generateYear.value,
      copy_holidays_from_previous: copyHolidays.value,
    })
    addDialog.value = false
    selectedYear.value = generateYear.value
    await fetchMonths()
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    generateError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Failed to generate year'
  } finally {
    generating.value = false
  }
}

// ---- Delete month ----

function openDeleteDialog(month: MonthRecord) {
  deletingMonth.value = month
  deleteDialog.value = true
}

async function confirmDelete() {
  if (!deletingMonth.value) return

  deleting.value = true
  try {
    await api.del(`/months/${deletingMonth.value.id}`)
    deleteDialog.value = false
    await fetchMonths()
  } catch {
    errorMessage.value = 'Failed to delete month'
  } finally {
    deleting.value = false
  }
}

// ---- Helpers ----

function quarterColor(quarter: string): string {
  const map: Record<string, string> = {
    Q1: 'blue',
    Q2: 'green',
    Q3: 'orange',
    Q4: 'purple',
  }
  return map[quarter] || 'grey'
}

function netWorkingDays(month: MonthRecord): number {
  return month.working_days - month.holidays
}

// ---- Lifecycle ----

onMounted(() => {
  fetchMonths()
})
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold mb-1">Months</h1>
        <p class="text-body-1 text-medium-emphasis ma-0">
          Monthly calendar with working days and holiday configuration.
        </p>
      </div>
      <v-btn
        color="primary"
        @click="openAddDialog"
      >
        <v-icon start>mdi-plus</v-icon>
        Generate Year
      </v-btn>
    </div>

    <!-- Error banner -->
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      closable
      class="mb-4"
      @click:close="errorMessage = null"
    >
      {{ errorMessage }}
    </v-alert>

    <!-- Year navigation -->
    <v-card class="mb-6 pa-3">
      <div class="d-flex align-center justify-center ga-3">
        <v-btn
          icon="mdi-chevron-left"
          variant="text"
          @click="selectedYear--"
        />
        <v-btn-toggle
          v-model="selectedYear"
          mandatory
          color="primary"
          density="comfortable"
          variant="outlined"
        >
          <v-btn
            v-for="year in availableYears"
            :key="year"
            :value="year"
          >
            {{ year }}
          </v-btn>
        </v-btn-toggle>
        <v-btn
          icon="mdi-chevron-right"
          variant="text"
          @click="selectedYear++"
        />
      </div>
    </v-card>

    <!-- Loading skeleton -->
    <v-row v-if="loading">
      <v-col
        v-for="n in 12"
        :key="n"
        cols="12"
        sm="6"
        md="4"
        lg="3"
      >
        <v-skeleton-loader type="card" />
      </v-col>
    </v-row>

    <!-- Empty state -->
    <v-card
      v-else-if="filteredMonths.length === 0"
      class="pa-8 text-center text-medium-emphasis"
    >
      <v-icon size="48" class="mb-4">mdi-calendar-blank</v-icon>
      <div class="text-h6 mb-2">No months for {{ selectedYear }}</div>
      <div class="text-body-2 mb-4">
        Click "Generate Year" to create all 12 months with calculated working days.
      </div>
      <v-btn color="primary" @click="openAddDialog">
        <v-icon start>mdi-plus</v-icon>
        Generate {{ selectedYear }}
      </v-btn>
    </v-card>

    <!-- Month cards grid -->
    <v-row v-else>
      <v-col
        v-for="month in filteredMonths"
        :key="month.id"
        cols="12"
        sm="6"
        md="4"
        lg="3"
      >
        <v-card class="h-100" hover @click="openEditDialog(month)">
          <v-card-title class="d-flex align-center justify-space-between pb-1">
            <span class="text-h6">{{ month.month_name }}</span>
            <v-chip
              :color="quarterColor(month.quarter)"
              size="small"
              variant="tonal"
            >
              {{ month.quarter }}
            </v-chip>
          </v-card-title>

          <v-card-text>
            <div class="d-flex justify-space-between text-body-2 mb-1">
              <span class="text-medium-emphasis">Total Days</span>
              <span class="font-weight-medium">{{ month.total_days }}</span>
            </div>
            <div class="d-flex justify-space-between text-body-2 mb-1">
              <span class="text-medium-emphasis">Weekdays</span>
              <span class="font-weight-medium">{{ month.working_days }}</span>
            </div>
            <div class="d-flex justify-space-between text-body-2 mb-1">
              <span class="text-medium-emphasis">Holidays</span>
              <span class="font-weight-medium">{{ month.holidays }}</span>
            </div>

            <v-divider class="my-2" />

            <div class="d-flex justify-space-between text-body-2">
              <span class="text-medium-emphasis">Net Working Days</span>
              <v-chip
                color="primary"
                size="small"
                variant="tonal"
              >
                {{ netWorkingDays(month) }}
              </v-chip>
            </div>
          </v-card-text>

          <v-card-actions>
            <v-spacer />
            <v-btn
              icon="mdi-pencil"
              variant="text"
              size="small"
              @click.stop="openEditDialog(month)"
            />
            <v-btn
              icon="mdi-delete"
              variant="text"
              size="small"
              color="error"
              @click.stop="openDeleteDialog(month)"
            />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Summary row -->
    <v-card v-if="filteredMonths.length > 0" class="mt-6 pa-4">
      <v-row>
        <v-col cols="12" sm="4" class="text-center">
          <div class="text-h5 font-weight-bold">
            {{ filteredMonths.reduce((s, m) => s + m.working_days, 0) }}
          </div>
          <div class="text-body-2 text-medium-emphasis">Total Weekdays</div>
        </v-col>
        <v-col cols="12" sm="4" class="text-center">
          <div class="text-h5 font-weight-bold">
            {{ filteredMonths.reduce((s, m) => s + m.holidays, 0) }}
          </div>
          <div class="text-body-2 text-medium-emphasis">Total Holidays</div>
        </v-col>
        <v-col cols="12" sm="4" class="text-center">
          <div class="text-h5 font-weight-bold primary--text">
            {{ filteredMonths.reduce((s, m) => s + netWorkingDays(m), 0) }}
          </div>
          <div class="text-body-2 text-medium-emphasis">Net Working Days</div>
        </v-col>
      </v-row>
    </v-card>

    <!-- =================== Edit Month Dialog =================== -->
    <v-dialog v-model="editDialog" max-width="450" persistent>
      <v-card v-if="editingMonth">
        <v-card-title>
          <v-icon start>mdi-pencil</v-icon>
          Edit {{ editingMonth.month_name }} {{ editingMonth.year }}
        </v-card-title>
        <v-card-text>
          <div class="d-flex justify-space-between text-body-2 mb-4">
            <span class="text-medium-emphasis">Total Days</span>
            <span class="font-weight-medium">{{ editingMonth.total_days }}</span>
          </div>

          <v-text-field
            v-model.number="editForm.working_days"
            label="Weekdays (Mon-Fri)"
            type="number"
            :min="0"
            :max="editingMonth.total_days"
            variant="outlined"
            density="comfortable"
            class="mb-3"
          />

          <v-text-field
            v-model.number="editForm.holidays"
            label="Holidays"
            type="number"
            :min="0"
            :max="editForm.working_days"
            variant="outlined"
            density="comfortable"
          />

          <div class="d-flex justify-space-between text-body-2 mt-3">
            <span class="text-medium-emphasis">Net Working Days</span>
            <v-chip color="primary" size="small" variant="tonal">
              {{ editForm.working_days - editForm.holidays }}
            </v-chip>
          </div>

          <v-alert
            v-if="saveError"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            {{ saveError }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="saving"
            @click="saveMonth"
          >
            Save
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- =================== Generate Year Dialog =================== -->
    <v-dialog v-model="addDialog" max-width="450" persistent>
      <v-card>
        <v-card-title>
          <v-icon start>mdi-calendar-plus</v-icon>
          Generate Year
        </v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Automatically generate all 12 months for a year with calculated weekdays.
          </p>

          <v-text-field
            v-model.number="generateYear"
            label="Year"
            type="number"
            :min="2020"
            :max="2050"
            variant="outlined"
            density="comfortable"
            class="mb-3"
          />

          <v-checkbox
            v-model="copyHolidays"
            label="Copy holidays from previous year"
            density="comfortable"
            hide-details
          />

          <v-alert
            v-if="generateError"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            {{ generateError }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="addDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="generating"
            @click="submitGenerateYear"
          >
            Generate
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- =================== Delete Confirmation Dialog =================== -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card v-if="deletingMonth">
        <v-card-title>Confirm Delete</v-card-title>
        <v-card-text>
          Are you sure you want to delete
          <strong>{{ deletingMonth.month_name }} {{ deletingMonth.year }}</strong>?
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn
            color="error"
            :loading="deleting"
            @click="confirmDelete"
          >
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
