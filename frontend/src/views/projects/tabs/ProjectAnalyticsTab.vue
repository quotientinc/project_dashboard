<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'
import { formatCurrencyFull } from '@/utils/helpers'
import PlotlyChart from '@/components/PlotlyChart.vue'
import type { Project } from '@/types'
import type Plotly from 'plotly.js-dist-min'

const { get, loading, error } = useApi()

const allProjects = ref<Project[]>([])
const selectedProjectIds = ref<string[]>([])

async function fetchProjects() {
  try {
    allProjects.value = await get<Project[]>('/projects/')
    // Default: first 5 active projects
    const active = allProjects.value.filter((p) => p.status === 'Active')
    const defaults = active.length > 0 ? active : allProjects.value
    selectedProjectIds.value = defaults.slice(0, 5).map((p) => p.id)
  } catch {
    // error handled by useApi
  }
}

onMounted(fetchProjects)

const projectItems = computed(() =>
  allProjects.value.map((p) => ({
    title: `${p.id} - ${p.name}`,
    value: p.id,
  }))
)

const selectedProjects = computed(() =>
  allProjects.value.filter((p) => selectedProjectIds.value.includes(p.id))
)

// --- Budget Comparison Chart ---
const budgetComparisonData = computed<Plotly.Data[]>(() => {
  const projects = selectedProjects.value
  if (projects.length === 0) return []

  const names = projects.map((p) => p.name)
  const quoted = projects.map((p) => p.quoted_value ?? 0)
  const awarded = projects.map((p) => p.awarded_value ?? 0)
  const used = projects.map((p) => p.budget_used ?? 0)

  return [
    {
      x: names,
      y: quoted,
      type: 'bar' as const,
      name: 'Quoted Value',
      marker: { color: '#1976D2' },
    },
    {
      x: names,
      y: awarded,
      type: 'bar' as const,
      name: 'Awarded Value',
      marker: { color: '#4CAF50' },
    },
    {
      x: names,
      y: used,
      type: 'bar' as const,
      name: 'Budget Used / Accrued',
      marker: { color: '#FF9800' },
    },
  ]
})

const budgetComparisonLayout = computed<Partial<Plotly.Layout>>(() => ({
  barmode: 'group' as const,
  xaxis: { title: { text: 'Project' }, tickangle: -30 },
  yaxis: { title: { text: 'Amount ($)' } },
  legend: { orientation: 'h' as const, y: -0.3 },
  height: 450,
}))
</script>

<template>
  <div>
    <!-- Loading -->
    <v-skeleton-loader v-if="loading && allProjects.length === 0" type="card, image" />

    <!-- Error -->
    <v-alert v-else-if="error && allProjects.length === 0" type="error" closable class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Content -->
    <template v-else>
      <!-- Project Selector -->
      <v-card class="mb-4 pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Multi-Project Comparison</div>
        <v-autocomplete
          v-model="selectedProjectIds"
          :items="projectItems"
          item-title="title"
          item-value="value"
          label="Select projects to compare"
          multiple
          chips
          closable-chips
          density="compact"
          variant="outlined"
          hide-details
          class="mb-4"
        />
      </v-card>

      <!-- Budget Comparison Chart -->
      <v-card class="pa-4">
        <div class="text-subtitle-1 font-weight-bold mb-3">Budget Comparison</div>
        <v-alert
          v-if="selectedProjects.length === 0"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          Select at least one project above to see the comparison.
        </v-alert>
        <template v-else>
          <PlotlyChart
            :data="budgetComparisonData"
            :layout="budgetComparisonLayout"
            :loading="loading"
          />

          <!-- Summary Table -->
          <v-data-table
            :headers="[
              { title: 'Project', key: 'name' },
              { title: 'Quoted Value', key: 'quoted_value', align: 'end' },
              { title: 'Awarded Value', key: 'awarded_value', align: 'end' },
              { title: 'Budget Used', key: 'budget_used', align: 'end' },
              { title: 'Remaining', key: 'remaining', align: 'end' },
            ]"
            :items="selectedProjects"
            density="compact"
            :items-per-page="-1"
            hide-default-footer
            class="mt-4"
          >
            <template #item.name="{ item }">
              <router-link
                :to="`/projects/${item.id}/overview`"
                class="text-primary text-decoration-none"
              >
                {{ item.name }}
              </router-link>
            </template>
            <template #item.quoted_value="{ item }">
              {{ formatCurrencyFull(item.quoted_value ?? 0) }}
            </template>
            <template #item.awarded_value="{ item }">
              {{ formatCurrencyFull(item.awarded_value ?? 0) }}
            </template>
            <template #item.budget_used="{ item }">
              {{ formatCurrencyFull(item.budget_used ?? 0) }}
            </template>
            <template #item.remaining="{ item }">
              <span :class="((item.quoted_value ?? 0) - (item.budget_used ?? 0)) < 0 ? 'text-error' : 'text-success'">
                {{ formatCurrencyFull((item.quoted_value ?? 0) - (item.budget_used ?? 0)) }}
              </span>
            </template>
          </v-data-table>
        </template>
      </v-card>
    </template>
  </div>
</template>
