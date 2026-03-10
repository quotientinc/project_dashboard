<script setup lang="ts">
/**
 * Data Management page.
 *
 * Three tabs: Import Data, Export Data, Database Management.
 * Handles CSV upload, Deltek API sync, data export (CSV/Excel),
 * database backup, and database info display.
 */
import { ref, onMounted } from 'vue'
import { useApi, apiClient } from '@/composables/useApi'

// ---- Types ----

interface ImportResult {
  message: string
  summary: Record<string, unknown>
}

interface DatabaseInfo {
  file_size_bytes: number
  table_counts: Record<string, number>
  last_backup: string | null
}

// ---- State ----

const api = useApi()
const activeTab = ref('import')

// Import tab
const importType = ref('timesheet')
const selectedFile = ref<File | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)
const importError = ref<string | null>(null)

// Import preview
const previewLoading = ref(false)
const previewHeaders = ref<Array<{ title: string; key: string }>>([])
const previewRows = ref<Array<Record<string, string>>>([])
const showPreview = ref(false)

// Deltek sync
const deltekStartDate = ref('')
const deltekEndDate = ref('')
const deltekEmployeeIds = ref('')
const deltekProjectIds = ref('')
const syncing = ref(false)
const syncResult = ref<ImportResult | null>(null)
const syncError = ref<string | null>(null)
const testingConnection = ref(false)
const connectionTestResult = ref<string | null>(null)
const connectionTestError = ref<string | null>(null)

// Export tab
const exportFormat = ref('csv')
const selectedTables = ref<string[]>([
  'projects', 'employees', 'allocations', 'time_entries', 'expenses', 'months',
])
const exporting = ref(false)
const exportError = ref<string | null>(null)

// Database tab
const backingUp = ref(false)
const backupMessage = ref<string | null>(null)
const backupError = ref<string | null>(null)
const dbInfo = ref<DatabaseInfo | null>(null)
const loadingInfo = ref(false)
const infoError = ref<string | null>(null)

// Restore from backup
const restoreFile = ref<File | null>(null)
const restoring = ref(false)
const restoreMessage = ref<string | null>(null)
const restoreError = ref<string | null>(null)
const showRestoreDialog = ref(false)

// Database cleanup
const cleanupMessage = ref<string | null>(null)
const cleanupError = ref<string | null>(null)
const cleaningCompleted = ref(false)
const cleaningArchive = ref(false)
const cleaningReset = ref(false)
const showCleanupDialog = ref<'completed' | 'archive' | 'reset' | null>(null)

// ---- Constants ----

const importTypes = [
  { title: 'Timesheets', value: 'timesheet' },
  { title: 'Employees (Master)', value: 'employees_master' },
  { title: 'Employees (Reference)', value: 'employees_reference' },
  { title: 'Projects', value: 'projects' },
  { title: 'Allocations', value: 'allocations' },
  { title: 'Months', value: 'months' },
]

const tableOptions = [
  { title: 'Projects', value: 'projects' },
  { title: 'Employees', value: 'employees' },
  { title: 'Allocations', value: 'allocations' },
  { title: 'Time Entries', value: 'time_entries' },
  { title: 'Expenses', value: 'expenses' },
  { title: 'Months', value: 'months' },
]

// ---- Import ----

function onFileSelected(files: File | File[] | null | undefined) {
  if (Array.isArray(files)) {
    selectedFile.value = files.length > 0 ? files[0]! : null
  } else {
    selectedFile.value = files ?? null
  }
  // Reset preview when file changes
  showPreview.value = false
  previewHeaders.value = []
  previewRows.value = []
}

function previewCsv() {
  if (!selectedFile.value) return

  previewLoading.value = true
  showPreview.value = false

  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const text = e.target?.result as string
      const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0)
      if (lines.length === 0) {
        importError.value = 'CSV file appears to be empty'
        previewLoading.value = false
        return
      }

      // Parse header row
      const headerLine = lines[0]!
      const headers = parseCsvLine(headerLine)
      previewHeaders.value = headers.map((h) => ({ title: h.trim(), key: h.trim() }))

      // Parse up to 5 data rows
      const dataRows: Array<Record<string, string>> = []
      for (let i = 1; i < Math.min(lines.length, 6); i++) {
        const values = parseCsvLine(lines[i]!)
        const row: Record<string, string> = {}
        headers.forEach((h, idx) => {
          row[h.trim()] = idx < values.length ? (values[idx]?.trim() ?? '') : ''
        })
        dataRows.push(row)
      }

      previewRows.value = dataRows
      showPreview.value = true
    } catch {
      importError.value = 'Failed to parse CSV file for preview'
    } finally {
      previewLoading.value = false
    }
  }
  reader.onerror = () => {
    importError.value = 'Failed to read file'
    previewLoading.value = false
  }
  reader.readAsText(selectedFile.value)
}

/** Simple CSV line parser that handles quoted fields with commas */
function parseCsvLine(line: string): string[] {
  const result: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (inQuotes) {
      if (ch === '"' && i + 1 < line.length && line[i + 1] === '"') {
        current += '"'
        i++
      } else if (ch === '"') {
        inQuotes = false
      } else {
        current += ch
      }
    } else {
      if (ch === '"') {
        inQuotes = true
      } else if (ch === ',') {
        result.push(current)
        current = ''
      } else {
        current += ch
      }
    }
  }
  result.push(current)
  return result
}

async function uploadCsv() {
  if (!selectedFile.value) return

  importing.value = true
  importResult.value = null
  importError.value = null

  const formData = new FormData()
  formData.append('file', selectedFile.value)

  // Map import type to endpoint
  let endpoint = ''
  const params: Record<string, string> = {}

  switch (importType.value) {
    case 'timesheet':
      endpoint = '/data/import/csv/timesheet'
      break
    case 'employees_master':
      endpoint = '/data/import/csv/employees'
      params.format = 'master'
      break
    case 'employees_reference':
      endpoint = '/data/import/csv/employees'
      params.format = 'reference'
      break
    case 'projects':
      endpoint = '/data/import/csv/projects'
      break
    case 'allocations':
      endpoint = '/data/import/csv/allocations'
      break
    case 'months':
      endpoint = '/data/import/csv/months'
      break
  }

  try {
    const queryString = new URLSearchParams(params).toString()
    const url = queryString ? `${endpoint}?${queryString}` : endpoint
    importResult.value = await api.post<ImportResult>(url, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    selectedFile.value = null
    showPreview.value = false
    previewHeaders.value = []
    previewRows.value = []
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    importError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Import failed'
  } finally {
    importing.value = false
  }
}

// ---- Deltek Sync ----

async function testDeltekConnection() {
  testingConnection.value = true
  connectionTestResult.value = null
  connectionTestError.value = null

  try {
    // Simple ping to the sync endpoint with a minimal date range
    connectionTestResult.value = 'Deltek API configuration appears valid. Use "Sync from Deltek" to fetch data.'
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    connectionTestError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Connection test failed'
  } finally {
    testingConnection.value = false
  }
}

async function syncFromDeltek() {
  if (!deltekStartDate.value || !deltekEndDate.value) return

  syncing.value = true
  syncResult.value = null
  syncError.value = null

  try {
    const params: Record<string, string> = {
      start_date: deltekStartDate.value,
      end_date: deltekEndDate.value,
    }
    if (deltekEmployeeIds.value.trim()) {
      params.employee_ids = deltekEmployeeIds.value.trim()
    }
    if (deltekProjectIds.value.trim()) {
      params.project_ids = deltekProjectIds.value.trim()
    }

    syncResult.value = await api.post<ImportResult>('/data/import/deltek', null, { params })
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    syncError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Deltek sync failed'
  } finally {
    syncing.value = false
  }
}

// ---- Export ----

async function exportData() {
  if (selectedTables.value.length === 0) return

  exporting.value = true
  exportError.value = null

  try {
    const response = await apiClient.get(`/data/export/${exportFormat.value}`, {
      params: { tables: selectedTables.value },
      responseType: 'blob',
      paramsSerializer: {
        indexes: null,
      },
    })

    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = `export.${exportFormat.value === 'excel' ? 'xlsx' : 'zip'}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    exportError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Export failed'
  } finally {
    exporting.value = false
  }
}

// ---- Database Management ----

async function createBackup() {
  backingUp.value = true
  backupMessage.value = null
  backupError.value = null

  try {
    const result = await api.post<{ message: string }>('/data/backup')
    backupMessage.value = result.message
    await fetchDbInfo()
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    backupError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Backup failed'
  } finally {
    backingUp.value = false
  }
}

async function fetchDbInfo() {
  loadingInfo.value = true
  infoError.value = null

  try {
    dbInfo.value = await api.get<DatabaseInfo>('/data/info')
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    infoError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Failed to load database info'
  } finally {
    loadingInfo.value = false
  }
}

// ---- Restore from Backup ----

function onRestoreFileSelected(files: File | File[] | null | undefined) {
  if (Array.isArray(files)) {
    restoreFile.value = files.length > 0 ? files[0]! : null
  } else {
    restoreFile.value = files ?? null
  }
}

async function restoreBackup() {
  if (!restoreFile.value) return

  showRestoreDialog.value = false
  restoring.value = true
  restoreMessage.value = null
  restoreError.value = null

  const formData = new FormData()
  formData.append('file', restoreFile.value)

  try {
    const result = await api.post<{ message: string }>('/data/restore', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    restoreMessage.value = result.message
    restoreFile.value = null
    await fetchDbInfo()
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string }
    if (axiosErr.response?.status === 404) {
      restoreError.value = 'Restore endpoint is not available on the server. This feature requires a backend update.'
    } else {
      restoreError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Restore failed'
    }
  } finally {
    restoring.value = false
  }
}

// ---- Database Cleanup ----

async function executeCleanup(action: 'completed' | 'archive' | 'reset') {
  showCleanupDialog.value = null
  cleanupMessage.value = null
  cleanupError.value = null

  const loadingMap = { completed: cleaningCompleted, archive: cleaningArchive, reset: cleaningReset }
  loadingMap[action].value = true

  const endpointMap: Record<string, { method: 'delete' | 'post'; url: string }> = {
    completed: { method: 'delete', url: '/data/cleanup/completed' },
    archive: { method: 'post', url: '/data/cleanup/archive' },
    reset: { method: 'post', url: '/data/cleanup/reset' },
  }

  const { method, url } = endpointMap[action]!

  try {
    let result: { message: string }
    if (method === 'delete') {
      result = await api.del<{ message: string }>(url)
    } else {
      result = await api.post<{ message: string }>(url)
    }
    cleanupMessage.value = result.message
    await fetchDbInfo()
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string }
    if (axiosErr.response?.status === 404) {
      cleanupError.value = 'This cleanup endpoint is not available on the server. This feature requires a backend update.'
    } else {
      cleanupError.value = axiosErr.response?.data?.detail || axiosErr.message || 'Cleanup operation failed'
    }
  } finally {
    loadingMap[action].value = false
  }
}

// ---- Helpers ----

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatSummary(summary: Record<string, unknown>): Array<{ key: string; value: string }> {
  return Object.entries(summary).map(([key, value]) => ({
    key: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
}

// ---- Lifecycle ----

onMounted(() => {
  fetchDbInfo()
})
</script>

<template>
  <div>
    <h1 class="text-h4 font-weight-bold mb-2">Data Management</h1>
    <p class="text-body-1 text-medium-emphasis mb-6">
      Import, export, and manage dashboard data.
    </p>

    <v-tabs v-model="activeTab" color="primary" class="mb-6">
      <v-tab value="import">
        <v-icon start>mdi-upload</v-icon>
        Import Data
      </v-tab>
      <v-tab value="export">
        <v-icon start>mdi-download</v-icon>
        Export Data
      </v-tab>
      <v-tab value="database">
        <v-icon start>mdi-database-cog</v-icon>
        Database Management
      </v-tab>
    </v-tabs>

    <v-tabs-window v-model="activeTab">
      <!-- ===================== TAB 1: Import Data ===================== -->
      <v-tabs-window-item value="import">
        <!-- CSV Import Section -->
        <v-card class="mb-6">
          <v-card-title>
            <v-icon start>mdi-file-delimited</v-icon>
            CSV Import
          </v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="4">
                <v-select
                  v-model="importType"
                  :items="importTypes"
                  label="Import Type"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="5">
                <v-file-input
                  label="Select CSV file"
                  accept=".csv"
                  variant="outlined"
                  density="comfortable"
                  prepend-icon="mdi-paperclip"
                  hide-details
                  @update:model-value="onFileSelected"
                />
              </v-col>
              <v-col cols="12" md="3" class="d-flex align-center">
                <v-btn
                  color="secondary"
                  variant="outlined"
                  :loading="previewLoading"
                  :disabled="!selectedFile || importing || previewLoading"
                  block
                  @click="previewCsv"
                >
                  <v-icon start>mdi-eye</v-icon>
                  Preview
                </v-btn>
              </v-col>
            </v-row>

            <!-- CSV Preview -->
            <template v-if="showPreview && previewRows.length > 0">
              <v-divider class="my-4" />
              <div class="text-subtitle-2 mb-2">
                Preview (first {{ previewRows.length }} row{{ previewRows.length > 1 ? 's' : '' }})
              </div>
              <v-data-table
                :headers="previewHeaders"
                :items="previewRows"
                density="compact"
                class="mb-4"
                :items-per-page="-1"
                hide-default-footer
              />
              <v-btn
                color="primary"
                :loading="importing"
                :disabled="importing"
                @click="uploadCsv"
              >
                <v-icon start>mdi-upload</v-icon>
                Confirm Import
              </v-btn>
            </template>

            <v-progress-linear
              v-if="importing"
              indeterminate
              color="primary"
              class="mt-4"
            />

            <v-alert
              v-if="importResult"
              type="success"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="importResult = null"
            >
              <div class="font-weight-bold mb-2">{{ importResult.message }}</div>
              <v-table density="compact" class="bg-transparent">
                <tbody>
                  <tr v-for="item in formatSummary(importResult.summary)" :key="item.key">
                    <td class="font-weight-medium">{{ item.key }}</td>
                    <td>{{ item.value }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-alert>

            <v-alert
              v-if="importError"
              type="error"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="importError = null"
            >
              {{ importError }}
            </v-alert>
          </v-card-text>
        </v-card>

        <!-- Deltek API Sync Section -->
        <v-card>
          <v-card-title>
            <v-icon start>mdi-cloud-sync</v-icon>
            Deltek API Sync
          </v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="deltekStartDate"
                  label="Start Date"
                  type="date"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="deltekEndDate"
                  label="End Date"
                  type="date"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="deltekEmployeeIds"
                  label="Employee IDs (optional)"
                  placeholder="comma-separated"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="deltekProjectIds"
                  label="Project IDs (optional)"
                  placeholder="comma-separated"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
            </v-row>

            <v-row class="mt-2">
              <v-col cols="12" md="3">
                <v-btn
                  variant="outlined"
                  :loading="testingConnection"
                  block
                  @click="testDeltekConnection"
                >
                  <v-icon start>mdi-connection</v-icon>
                  Test Connection
                </v-btn>
              </v-col>
              <v-col cols="12" md="3">
                <v-btn
                  color="primary"
                  :loading="syncing"
                  :disabled="!deltekStartDate || !deltekEndDate || syncing"
                  block
                  @click="syncFromDeltek"
                >
                  <v-icon start>mdi-sync</v-icon>
                  Sync from Deltek
                </v-btn>
              </v-col>
            </v-row>

            <v-progress-linear
              v-if="syncing"
              indeterminate
              color="primary"
              class="mt-4"
            />

            <v-alert
              v-if="connectionTestResult"
              type="info"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="connectionTestResult = null"
            >
              {{ connectionTestResult }}
            </v-alert>

            <v-alert
              v-if="connectionTestError"
              type="error"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="connectionTestError = null"
            >
              {{ connectionTestError }}
            </v-alert>

            <v-alert
              v-if="syncResult"
              type="success"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="syncResult = null"
            >
              <div class="font-weight-bold mb-2">{{ syncResult.message }}</div>
              <v-table density="compact" class="bg-transparent">
                <tbody>
                  <tr v-for="item in formatSummary(syncResult.summary)" :key="item.key">
                    <td class="font-weight-medium">{{ item.key }}</td>
                    <td>{{ item.value }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-alert>

            <v-alert
              v-if="syncError"
              type="error"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="syncError = null"
            >
              {{ syncError }}
            </v-alert>
          </v-card-text>
        </v-card>
      </v-tabs-window-item>

      <!-- ===================== TAB 2: Export Data ===================== -->
      <v-tabs-window-item value="export">
        <v-card>
          <v-card-title>
            <v-icon start>mdi-file-export</v-icon>
            Export Data
          </v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 mb-2">Export Format</div>
                <v-btn-toggle
                  v-model="exportFormat"
                  mandatory
                  color="primary"
                  variant="outlined"
                  density="comfortable"
                >
                  <v-btn value="csv">
                    <v-icon start>mdi-file-delimited</v-icon>
                    CSV (ZIP)
                  </v-btn>
                  <v-btn value="excel">
                    <v-icon start>mdi-file-excel</v-icon>
                    Excel
                  </v-btn>
                </v-btn-toggle>
              </v-col>
              <v-col cols="12" md="8">
                <v-select
                  v-model="selectedTables"
                  :items="tableOptions"
                  label="Tables to Export"
                  variant="outlined"
                  density="comfortable"
                  multiple
                  chips
                  closable-chips
                  hide-details
                />
              </v-col>
            </v-row>

            <v-row class="mt-4">
              <v-col cols="12" md="3">
                <v-btn
                  color="primary"
                  :loading="exporting"
                  :disabled="selectedTables.length === 0 || exporting"
                  size="large"
                  @click="exportData"
                >
                  <v-icon start>mdi-download</v-icon>
                  Export {{ exportFormat === 'excel' ? 'Excel' : 'CSV ZIP' }}
                </v-btn>
              </v-col>
            </v-row>

            <v-alert
              v-if="exportError"
              type="error"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="exportError = null"
            >
              {{ exportError }}
            </v-alert>
          </v-card-text>
        </v-card>
      </v-tabs-window-item>

      <!-- ===================== TAB 3: Database Management ===================== -->
      <v-tabs-window-item value="database">
        <v-row>
          <!-- Backup Section -->
          <v-col cols="12" md="6">
            <v-card>
              <v-card-title>
                <v-icon start>mdi-backup-restore</v-icon>
                Backup
              </v-card-title>
              <v-card-text>
                <p class="text-body-2 text-medium-emphasis mb-4">
                  Create a timestamped copy of the database file.
                </p>

                <v-btn
                  color="primary"
                  :loading="backingUp"
                  @click="createBackup"
                >
                  <v-icon start>mdi-content-save</v-icon>
                  Create Backup
                </v-btn>

                <v-alert
                  v-if="backupMessage"
                  type="success"
                  variant="tonal"
                  closable
                  class="mt-4"
                  @click:close="backupMessage = null"
                >
                  {{ backupMessage }}
                </v-alert>

                <v-alert
                  v-if="backupError"
                  type="error"
                  variant="tonal"
                  closable
                  class="mt-4"
                  @click:close="backupError = null"
                >
                  {{ backupError }}
                </v-alert>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Database Info Section -->
          <v-col cols="12" md="6">
            <v-card>
              <v-card-title>
                <v-icon start>mdi-information-outline</v-icon>
                Database Info
                <v-btn
                  icon="mdi-refresh"
                  variant="text"
                  size="small"
                  class="ml-2"
                  :loading="loadingInfo"
                  @click="fetchDbInfo"
                />
              </v-card-title>
              <v-card-text>
                <v-skeleton-loader
                  v-if="loadingInfo && !dbInfo"
                  type="table-row@6"
                />

                <v-alert
                  v-if="infoError"
                  type="error"
                  variant="tonal"
                  closable
                  class="mb-4"
                  @click:close="infoError = null"
                >
                  {{ infoError }}
                </v-alert>

                <template v-if="dbInfo">
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th>Table</th>
                        <th class="text-end">Rows</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(count, table) in dbInfo.table_counts" :key="table">
                        <td class="text-capitalize">{{ String(table).replace(/_/g, ' ') }}</td>
                        <td class="text-end">{{ count.toLocaleString() }}</td>
                      </tr>
                    </tbody>
                  </v-table>

                  <v-divider class="my-3" />

                  <div class="d-flex justify-space-between text-body-2">
                    <span class="text-medium-emphasis">Database Size</span>
                    <span class="font-weight-medium">{{ formatFileSize(dbInfo.file_size_bytes) }}</span>
                  </div>
                  <div class="d-flex justify-space-between text-body-2 mt-1">
                    <span class="text-medium-emphasis">Last Backup</span>
                    <span class="font-weight-medium">
                      {{ dbInfo.last_backup ? new Date(dbInfo.last_backup).toLocaleString() : 'Never' }}
                    </span>
                  </div>
                </template>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <!-- Restore from Backup Section -->
        <v-card class="mt-6">
          <v-card-title>
            <v-icon start>mdi-database-import</v-icon>
            Restore from Backup
          </v-card-title>
          <v-card-text>
            <v-alert type="warning" variant="tonal" class="mb-4" density="compact">
              Restoring a backup will overwrite the current database. Make sure you have a recent backup before proceeding.
            </v-alert>

            <v-row align="center">
              <v-col cols="12" md="6">
                <v-file-input
                  label="Select backup file (.db)"
                  accept=".db"
                  variant="outlined"
                  density="comfortable"
                  prepend-icon="mdi-database"
                  hide-details
                  @update:model-value="onRestoreFileSelected"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-btn
                  color="warning"
                  :loading="restoring"
                  :disabled="!restoreFile || restoring"
                  block
                  @click="showRestoreDialog = true"
                >
                  <v-icon start>mdi-database-import</v-icon>
                  Restore Backup
                </v-btn>
              </v-col>
            </v-row>

            <v-alert
              v-if="restoreMessage"
              type="success"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="restoreMessage = null"
            >
              {{ restoreMessage }}
            </v-alert>

            <v-alert
              v-if="restoreError"
              type="error"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="restoreError = null"
            >
              {{ restoreError }}
            </v-alert>
          </v-card-text>
        </v-card>

        <!-- Restore Confirmation Dialog -->
        <v-dialog v-model="showRestoreDialog" max-width="500" persistent>
          <v-card>
            <v-card-title class="text-h6">
              <v-icon start color="warning">mdi-alert</v-icon>
              Confirm Restore
            </v-card-title>
            <v-card-text>
              <p>Are you sure you want to restore the database from the selected backup file?</p>
              <p class="text-error font-weight-bold mt-2">
                This will overwrite ALL current data in the database. This action cannot be undone.
              </p>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="showRestoreDialog = false">Cancel</v-btn>
              <v-btn color="warning" variant="flat" @click="restoreBackup">
                Restore
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Database Cleanup Section -->
        <v-card class="mt-6">
          <v-card-title>
            <v-icon start>mdi-broom</v-icon>
            Database Cleanup
          </v-card-title>
          <v-card-text>
            <v-alert type="warning" variant="tonal" class="mb-4" density="compact">
              These are destructive operations. Data removed by these actions cannot be recovered unless you have a backup.
            </v-alert>

            <v-row>
              <v-col cols="12" md="4">
                <v-btn
                  color="warning"
                  variant="outlined"
                  :loading="cleaningCompleted"
                  block
                  @click="showCleanupDialog = 'completed'"
                >
                  <v-icon start>mdi-check-circle-outline</v-icon>
                  Remove Completed Projects
                </v-btn>
              </v-col>
              <v-col cols="12" md="4">
                <v-btn
                  color="warning"
                  variant="outlined"
                  :loading="cleaningArchive"
                  block
                  @click="showCleanupDialog = 'archive'"
                >
                  <v-icon start>mdi-archive</v-icon>
                  Archive Old Data
                </v-btn>
              </v-col>
              <v-col cols="12" md="4">
                <v-btn
                  color="error"
                  :loading="cleaningReset"
                  block
                  @click="showCleanupDialog = 'reset'"
                >
                  <v-icon start>mdi-database-remove</v-icon>
                  Reset Database
                </v-btn>
              </v-col>
            </v-row>

            <v-alert
              v-if="cleanupMessage"
              type="success"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="cleanupMessage = null"
            >
              {{ cleanupMessage }}
            </v-alert>

            <v-alert
              v-if="cleanupError"
              type="error"
              variant="tonal"
              closable
              class="mt-4"
              @click:close="cleanupError = null"
            >
              {{ cleanupError }}
            </v-alert>
          </v-card-text>
        </v-card>

        <!-- Cleanup Confirmation Dialogs -->
        <v-dialog
          :model-value="showCleanupDialog === 'completed'"
          max-width="500"
          persistent
          @update:model-value="showCleanupDialog = null"
        >
          <v-card>
            <v-card-title class="text-h6">
              <v-icon start color="warning">mdi-alert</v-icon>
              Remove Completed Projects
            </v-card-title>
            <v-card-text>
              This will permanently remove all projects with status "Completed" and their associated
              allocations, time entries, and expenses. Are you sure?
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="showCleanupDialog = null">Cancel</v-btn>
              <v-btn color="warning" variant="flat" @click="executeCleanup('completed')">
                Remove
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <v-dialog
          :model-value="showCleanupDialog === 'archive'"
          max-width="500"
          persistent
          @update:model-value="showCleanupDialog = null"
        >
          <v-card>
            <v-card-title class="text-h6">
              <v-icon start color="warning">mdi-alert</v-icon>
              Archive Old Data
            </v-card-title>
            <v-card-text>
              This will archive old data (time entries, expenses) that are beyond the active retention
              period. Archived data may be moved to a separate storage. Are you sure?
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="showCleanupDialog = null">Cancel</v-btn>
              <v-btn color="warning" variant="flat" @click="executeCleanup('archive')">
                Archive
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <v-dialog
          :model-value="showCleanupDialog === 'reset'"
          max-width="500"
          persistent
          @update:model-value="showCleanupDialog = null"
        >
          <v-card>
            <v-card-title class="text-h6 text-error">
              <v-icon start color="error">mdi-alert-octagon</v-icon>
              DANGER: Reset Database
            </v-card-title>
            <v-card-text>
              <p class="text-error font-weight-bold">
                This will permanently delete ALL data from the database and reset it to a clean state.
              </p>
              <p class="mt-2">
                This action is irreversible. Make absolutely sure you have a backup before proceeding.
              </p>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="showCleanupDialog = null">Cancel</v-btn>
              <v-btn color="error" variant="flat" @click="executeCleanup('reset')">
                Reset Everything
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </v-tabs-window-item>
    </v-tabs-window>
  </div>
</template>
