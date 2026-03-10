import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useFiltersStore = defineStore('filters', () => {
  // State
  const startDate = ref<string>(getDefaultStartDate())
  const endDate = ref<string>(getDefaultEndDate())
  const selectedProjects = ref<string[]>([])
  const selectedStatuses = ref<string[]>(['Active'])
  const selectedDepartments = ref<string[]>([])

  // Getters
  const formattedStartDate = computed(() => {
    return startDate.value
  })

  const formattedEndDate = computed(() => {
    return endDate.value
  })

  const hasActiveFilters = computed(() => {
    return (
      selectedProjects.value.length > 0 ||
      selectedStatuses.value.length > 0 ||
      selectedDepartments.value.length > 0
    )
  })

  // Actions
  function setDateRange(start: string, end: string) {
    startDate.value = start
    endDate.value = end
  }

  function setSelectedProjects(projects: string[]) {
    selectedProjects.value = projects
  }

  function setSelectedStatuses(statuses: string[]) {
    selectedStatuses.value = statuses
  }

  function setSelectedDepartments(departments: string[]) {
    selectedDepartments.value = departments
  }

  function resetFilters() {
    startDate.value = getDefaultStartDate()
    endDate.value = getDefaultEndDate()
    selectedProjects.value = []
    selectedStatuses.value = ['Active']
    selectedDepartments.value = []
  }

  return {
    startDate,
    endDate,
    selectedProjects,
    selectedStatuses,
    selectedDepartments,
    formattedStartDate,
    formattedEndDate,
    hasActiveFilters,
    setDateRange,
    setSelectedProjects,
    setSelectedStatuses,
    setSelectedDepartments,
    resetFilters,
  }
})

function getDefaultStartDate(): string {
  const now = new Date()
  const sixMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 6, now.getDate())
  return sixMonthsAgo.toISOString().split('T')[0] as string
}

function getDefaultEndDate(): string {
  const now = new Date()
  const sixMonthsAhead = new Date(now.getFullYear(), now.getMonth() + 6, now.getDate())
  return sixMonthsAhead.toISOString().split('T')[0] as string
}
