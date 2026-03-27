<script lang="ts">
// Defaults must be in a plain <script> block because defineProps is hoisted
// and cannot reference variables declared inside <script setup>.
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
</script>

<script setup lang="ts">
import { computed } from 'vue'

// ---------------------------------------------------------------------------
// Props (v-model pattern)
// ---------------------------------------------------------------------------
const props = withDefaults(defineProps<{
  year: number
  timeFrameType: 'Monthly' | 'Quarterly' | 'QTD' | 'YTD'
  selectedMonth: string
  selectedQuarter: string
  fyType: 'Company' | 'Gov'
  includeProjectedHours: boolean
}>(), {
  year: () => new Date().getFullYear(),
  timeFrameType: 'YTD',
  selectedMonth: () => MONTH_NAMES[new Date().getMonth()]!,
  selectedQuarter: () => `Q${Math.ceil((new Date().getMonth() + 1) / 3)}`,
  fyType: 'Company',
  includeProjectedHours: true,
})

// ---------------------------------------------------------------------------
// Emits
// ---------------------------------------------------------------------------
const emit = defineEmits<{
  'update:year': [value: number]
  'update:timeFrameType': [value: string]
  'update:selectedMonth': [value: string]
  'update:selectedQuarter': [value: string]
  'update:fyType': [value: 'Company' | 'Gov']
  'update:includeProjectedHours': [value: boolean]
}>()

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const now = new Date()

const monthNames = MONTH_NAMES

const yearOptions = computed(() => {
  const y = now.getFullYear()
  return [y - 1, y, y + 1]
})

// Gov quarter mapping: Company Q1 (Jan-Mar) = Gov Q2, etc.
const govQuarterMap: Record<string, string> = { Q1: 'q2', Q2: 'q3', Q3: 'q4', Q4: 'q1' }

// ---------------------------------------------------------------------------
// Computed outputs (exposed to parent via defineExpose)
// ---------------------------------------------------------------------------

/**
 * The API `time_frame` param string derived from the current filter selections.
 */
const timeFrame = computed(() => {
  switch (props.timeFrameType) {
    case 'Monthly':
      return props.selectedMonth.toLowerCase()
    case 'Quarterly':
      if (props.fyType === 'Gov') {
        return govQuarterMap[props.selectedQuarter] ?? props.selectedQuarter.toLowerCase()
      }
      return props.selectedQuarter.toLowerCase()
    case 'QTD':
      return props.fyType === 'Gov' ? 'qtd_gov' : 'qtd_company'
    case 'YTD':
      return props.fyType === 'Gov' ? 'ytd_gov' : 'ytd_company'
    default:
      return 'ytd_company'
  }
})

/**
 * Resolved date range `{ startDate, endDate }` for the current filter state.
 */
const dateRange = computed(() => {
  const year = props.year
  switch (props.timeFrameType) {
    case 'Monthly': {
      const monthIndex = monthNames.indexOf(props.selectedMonth)
      const lastDay = new Date(year, monthIndex + 1, 0).getDate()
      return {
        startDate: `${year}-${String(monthIndex + 1).padStart(2, '0')}-01`,
        endDate: `${year}-${String(monthIndex + 1).padStart(2, '0')}-${lastDay}`,
      }
    }
    case 'Quarterly': {
      const q = parseInt(props.selectedQuarter.slice(1))
      const startMonth = (q - 1) * 3 + 1
      const endMonth = q * 3
      const lastDay = new Date(year, endMonth, 0).getDate()
      return {
        startDate: `${year}-${String(startMonth).padStart(2, '0')}-01`,
        endDate: `${year}-${String(endMonth).padStart(2, '0')}-${lastDay}`,
      }
    }
    case 'QTD': {
      const currentQ = Math.ceil((now.getMonth() + 1) / 3)
      const qStart = (currentQ - 1) * 3 + 1
      return {
        startDate: `${year}-${String(qStart).padStart(2, '0')}-01`,
        endDate: now.toISOString().slice(0, 10),
      }
    }
    case 'YTD':
    default: {
      const endDate = year === now.getFullYear() ? now.toISOString().slice(0, 10) : `${year}-12-31`
      if (props.fyType === 'Gov') {
        return { startDate: `${year - 1}-10-01`, endDate: `${year}-09-30` }
      }
      return { startDate: `${year}-01-01`, endDate }
    }
  }
})

/**
 * Formatted period label such as "January 2026" or "January 2026 – March 2026".
 */
const periodLabel = computed(() => {
  const { startDate, endDate } = dateRange.value
  const start = new Date(startDate + 'T00:00:00')
  const end = new Date(endDate + 'T00:00:00')
  const startLabel = `${monthNames[start.getMonth()]} ${start.getFullYear()}`
  const endLabel = `${monthNames[end.getMonth()]} ${end.getFullYear()}`
  return startLabel === endLabel ? startLabel : `${startLabel} \u2013 ${endLabel}`
})

// ---------------------------------------------------------------------------
// Expose computed outputs so parents can access them via template ref
// ---------------------------------------------------------------------------
defineExpose({ timeFrame, dateRange, periodLabel })
</script>

<template>
  <v-row align="center">
    <v-col cols="2">
      <v-select
        :model-value="year"
        @update:model-value="emit('update:year', $event)"
        :items="yearOptions"
        label="Year"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="2">
      <v-select
        :model-value="timeFrameType"
        @update:model-value="emit('update:timeFrameType', $event)"
        :items="['Monthly', 'Quarterly', 'QTD', 'YTD']"
        label="Time Frame"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="2" v-if="timeFrameType === 'Monthly'">
      <v-select
        :model-value="selectedMonth"
        @update:model-value="emit('update:selectedMonth', $event)"
        :items="monthNames"
        label="Month"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="2" v-if="timeFrameType === 'Quarterly'">
      <v-select
        :model-value="selectedQuarter"
        @update:model-value="emit('update:selectedQuarter', $event)"
        :items="['Q1','Q2','Q3','Q4']"
        label="Quarter"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="2" v-if="['Quarterly','QTD','YTD'].includes(timeFrameType)">
      <v-radio-group
        :model-value="fyType"
        @update:model-value="emit('update:fyType', $event as 'Company' | 'Gov')"
        inline
        hide-details
        density="compact"
        label="FY Type"
      >
        <v-radio label="Company" value="Company" />
        <v-radio label="Gov" value="Gov" />
      </v-radio-group>
    </v-col>
    <v-col cols="2">
      <v-checkbox
        :model-value="includeProjectedHours"
        @update:model-value="emit('update:includeProjectedHours', $event as boolean)"
        label="Include projected hours"
        density="compact"
        hide-details
      />
    </v-col>
  </v-row>
</template>
