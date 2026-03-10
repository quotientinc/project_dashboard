<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import type { Project, ProjectUpdate } from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'

const route = useRoute()
const { put, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)

// Inject project data from parent ProjectDetailView to avoid duplicate API calls
const projectContext = inject(PROJECT_CONTEXT_KEY)!
const project = projectContext.project

const saving = ref(false)
const snackbar = ref(false)
const snackbarMessage = ref('')
const snackbarColor = ref('success')
const formRef = ref()

// Form fields
const form = ref<ProjectUpdate>({
  name: '',
  description: '',
  client: '',
  project_manager: '',
  status: '',
  start_date: '',
  end_date: '',
  quoted_value: 0,
  awarded_value: 0,
  billable: 0,
})

const statusOptions = ['Active', 'Future', 'On Hold', 'Completed', 'Cancelled']

function resetForm(data: Project) {
  form.value = {
    name: data.name ?? '',
    description: data.description ?? '',
    client: data.client ?? '',
    project_manager: data.project_manager ?? '',
    status: data.status ?? '',
    start_date: data.start_date ?? '',
    end_date: data.end_date ?? '',
    quoted_value: data.quoted_value ?? 0,
    awarded_value: data.awarded_value ?? 0,
    billable: data.billable ?? 0,
  }
}

function initForm() {
  if (project.value) {
    resetForm(project.value)
  }
}

function onCancel() {
  if (project.value) {
    resetForm(project.value)
  }
}

async function onSave() {
  const { valid } = await formRef.value.validate()
  if (!valid) return

  saving.value = true
  try {
    const updated = await put<Project>(`/projects/${encodeURIComponent(projectId.value)}`, form.value)
    project.value = updated
    resetForm(updated)
    // Refresh parent project data so other tabs see updated values
    await projectContext.refreshProject()
    snackbarMessage.value = 'Project updated successfully.'
    snackbarColor.value = 'success'
    snackbar.value = true
  } catch (err) {
    snackbarMessage.value = error.value ?? 'Failed to update project.'
    snackbarColor.value = 'error'
    snackbar.value = true
  } finally {
    saving.value = false
  }
}

// Initialize form when project data is available
watch(project, (newVal) => {
  if (newVal) resetForm(newVal)
}, { immediate: true })

// Re-initialize when switching projects
watch(projectId, initForm)
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading && !project" type="card" />

    <!-- Error -->
    <v-alert v-else-if="error && !project" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Form -->
    <v-card v-else-if="project" class="pa-6">
      <v-card-title class="text-subtitle-1 font-weight-bold px-0 mb-4">
        Edit Project
      </v-card-title>

      <v-form ref="formRef" @submit.prevent="onSave">
        <v-row>
          <!-- Left column -->
          <v-col cols="12" md="6">
            <v-text-field
              v-model="form.name"
              label="Project Name *"
              :rules="[v => !!v || 'Name is required']"
              class="mb-2"
            />
            <v-textarea
              v-model="form.description"
              label="Description"
              rows="3"
              variant="outlined"
              class="mb-2"
            />
            <v-text-field
              v-model="form.client"
              label="Client *"
              :rules="[v => !!v || 'Client is required']"
              class="mb-2"
            />
            <v-text-field
              v-model="form.project_manager"
              label="Project Manager *"
              :rules="[v => !!v || 'Project Manager is required']"
              class="mb-2"
            />
          </v-col>

          <!-- Right column -->
          <v-col cols="12" md="6">
            <v-select
              v-model="form.status"
              label="Status"
              :items="statusOptions"
              class="mb-2"
            />
            <v-row>
              <v-col cols="6">
                <v-text-field
                  v-model="form.start_date"
                  label="Start Date"
                  type="date"
                  class="mb-2"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="form.end_date"
                  label="End Date"
                  type="date"
                  :rules="[v => !v || !form.start_date || v >= form.start_date || 'End date must be on or after start date']"
                  class="mb-2"
                />
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="6">
                <v-text-field
                  v-model.number="form.quoted_value"
                  label="Quoted Value"
                  type="number"
                  prefix="$"
                  :min="0"
                  class="mb-2"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model.number="form.awarded_value"
                  label="Awarded Value"
                  type="number"
                  prefix="$"
                  :min="0"
                  class="mb-2"
                />
              </v-col>
            </v-row>
            <v-checkbox
              v-model="form.billable"
              label="Billable Project"
              :true-value="1"
              :false-value="0"
              hide-details
            />
          </v-col>
        </v-row>

        <!-- Actions -->
        <v-divider class="my-4" />
        <div class="d-flex ga-3">
          <v-btn
            type="submit"
            color="primary"
            :loading="saving"
            prepend-icon="mdi-content-save"
          >
            Save Changes
          </v-btn>
          <v-btn
            variant="outlined"
            @click="onCancel"
            :disabled="saving"
          >
            Cancel
          </v-btn>
        </div>
      </v-form>
    </v-card>

    <!-- Snackbar -->
    <v-snackbar
      v-model="snackbar"
      :color="snackbarColor"
      :timeout="4000"
      location="bottom right"
    >
      {{ snackbarMessage }}
      <template #actions>
        <v-btn variant="text" @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>
