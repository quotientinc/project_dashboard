<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tabs = [
  { title: 'Employee List', value: 'list', path: '/employees' },
  { title: 'Allocation Overview', value: 'allocation_overview', path: '/employees/allocation_overview' },
  { title: 'Utilization Overview', value: 'utilization_overview', path: '/employees/utilization_overview' },
]

const currentTab = computed(() => {
  const path = route.path.replace(/\/$/, '')
  const tab = tabs.find(t => t.path === path)
  return tab?.value ?? 'list'
})

function navigateTab(value: string) {
  const tab = tabs.find(t => t.value === value)
  if (tab && route.path !== tab.path) {
    router.push(tab.path)
  }
}
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4">Employees</h1>
      <v-btn color="primary" prepend-icon="mdi-plus">Add Employee</v-btn>
    </div>

    <v-tabs :model-value="currentTab" color="primary" class="mb-4">
      <v-tab
        v-for="tab in tabs"
        :key="tab.value"
        :value="tab.value"
        @click="navigateTab(tab.value)"
      >
        {{ tab.title }}
      </v-tab>
    </v-tabs>

    <router-view />
  </div>
</template>
