import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useEmployeesStore = defineStore('employees', () => {
  // -----------------------------------------------------------------------
  // Tab 1: Employee List filters
  // -----------------------------------------------------------------------
  const selectedBillableStatus = ref('All')
  const selectedPayType = ref('All')
  const searchTerm = ref('')
  const employeeListSortBy = ref<{ key: string; order: 'asc' | 'desc' }[]>([])

  // -----------------------------------------------------------------------
  // Tab 2: Allocation Overview filters
  // -----------------------------------------------------------------------
  const allocYear = ref(new Date().getFullYear())
  const allocMonth = ref(new Date().getMonth() + 1)
  const allocStatusFilter = ref<string[]>([])
  const allocSearchTerm = ref('')

  // -----------------------------------------------------------------------
  // Tab 3: Utilization Overview filters
  // -----------------------------------------------------------------------
  const utilYear = ref(new Date().getFullYear())
  const utilTimeFrameType = ref('YTD')
  const selectedMonth = ref(getMonthName(new Date().getMonth()))
  const selectedQuarter = ref(`Q${Math.ceil((new Date().getMonth() + 1) / 3)}`)
  const fyType = ref('Company')
  const includeProjectedHours = ref(true)
  const utilBandFilter = ref<string[]>([])
  const utilSearchTerm = ref('')
  const utilTableSortBy = ref<{ key: string; order: 'asc' | 'desc' }[]>([])

  return {
    // Tab 1
    selectedBillableStatus,
    selectedPayType,
    searchTerm,
    employeeListSortBy,
    // Tab 2
    allocYear,
    allocMonth,
    allocStatusFilter,
    allocSearchTerm,
    // Tab 3
    utilYear,
    utilTimeFrameType,
    selectedMonth,
    selectedQuarter,
    fyType,
    includeProjectedHours,
    utilBandFilter,
    utilSearchTerm,
    utilTableSortBy,
  }
})

function getMonthName(index: number): string {
  return [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ][index]
}