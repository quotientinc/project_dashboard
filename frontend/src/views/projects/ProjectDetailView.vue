<script setup lang="ts">
import { ref, computed, onMounted, watch, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import type { Project } from '@/types'
import { PROJECT_CONTEXT_KEY } from '@/types'

const route = useRoute()
const router = useRouter()
const { get, loading, error } = useApi()

const projectId = computed(() => route.params.id as string)
const project = ref<Project | null>(null)
const allProjects = ref<Project[]>([])

// Provide project data to child tab components to avoid duplicate API calls
provide(PROJECT_CONTEXT_KEY, {
  project,
  loading,
  error,
  refreshProject: fetchProjectOnly,
})

// For the project switcher autocomplete
const switcherValue = ref<string | null>(null)
const projectItems = computed(() =>
  allProjects.value.map((p) => ({
    title: `${p.id} - ${p.name}`,
    value: p.id,
  }))
)

async function fetchProjectOnly() {
  try {
    const projectData = await get<Project>(`/projects/${encodeURIComponent(projectId.value)}`)
    project.value = projectData
    switcherValue.value = projectData.id
  } catch {
    // error handled by useApi
  }
}

async function fetchProject() {
  try {
    const [projectData, projectsList] = await Promise.all([
      get<Project>(`/projects/${encodeURIComponent(projectId.value)}`),
      get<Project[]>('/projects/'),
    ])
    project.value = projectData
    allProjects.value = projectsList
    switcherValue.value = projectData.id
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchProject)

// Re-fetch when projectId changes (via project switcher)
watch(projectId, fetchProject)

function onProjectSwitch(newId: string | null) {
  if (newId && newId !== projectId.value) {
    // Navigate to the new project, preserving the current tab
    const pathSegments = route.path.split('/')
    const currentTab = pathSegments[pathSegments.length - 1] || 'overview'
    router.push({ name: `project-${currentTab}`, params: { id: newId } })
  }
}

// Tab navigation
const tabs = [
  { title: 'Overview', value: 'overview', icon: 'mdi-information-outline' },
  { title: 'Performance', value: 'performance', icon: 'mdi-chart-line' },
  { title: 'Team', value: 'team', icon: 'mdi-account-group-outline' },
  { title: 'Budget', value: 'budget', icon: 'mdi-currency-usd' },
  { title: 'Planner', value: 'planner', icon: 'mdi-calculator-variant' },
  { title: 'Timeline', value: 'timeline', icon: 'mdi-timeline' },
  { title: 'Review', value: 'review', icon: 'mdi-clipboard-check-outline' },
  { title: 'Analytics', value: 'analytics', icon: 'mdi-chart-bar' },
  { title: 'Edit', value: 'edit', icon: 'mdi-pencil-outline' },
]

const currentTab = computed(() => {
  const pathSegments = route.path.split('/')
  return pathSegments[pathSegments.length - 1] || 'overview'
})

function navigateTab(tab: string) {
  router.push({ name: `project-${tab}`, params: { id: projectId.value } })
}

// Status chip color
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
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading && !project" type="card, heading, card" />

    <!-- Error -->
    <v-alert v-else-if="error && !project" type="error" class="mb-4">
      {{ error }}
      <template #append>
        <v-btn variant="text" @click="router.push('/projects')">Back to Projects</v-btn>
      </template>
    </v-alert>

    <!-- Content -->
    <template v-else-if="project">
      <!-- Header -->
      <div class="d-flex align-center mb-2">
        <v-btn
          icon="mdi-arrow-left"
          variant="text"
          size="small"
          @click="router.push('/projects')"
          aria-label="Back to projects"
        />
        <div class="ml-3 flex-grow-1">
          <div class="d-flex align-center flex-wrap ga-2">
            <h1 class="text-h5 font-weight-bold">{{ project.name }}</h1>
            <v-chip
              :color="statusColor(project.status)"
              size="small"
              label
            >
              {{ project.status }}
            </v-chip>
          </div>
          <div class="text-body-2 text-medium-emphasis mt-1">
            <span>{{ project.id }}</span>
            <span v-if="project.client" class="ml-3">Client: {{ project.client }}</span>
            <span v-if="project.project_manager" class="ml-3">PM: {{ project.project_manager }}</span>
          </div>
        </div>

        <!-- Project Switcher -->
        <v-autocomplete
          v-model="switcherValue"
          :items="projectItems"
          item-title="title"
          item-value="value"
          label="Switch project"
          density="compact"
          variant="outlined"
          hide-details
          style="max-width: 350px;"
          class="ml-4"
          @update:model-value="onProjectSwitch"
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
