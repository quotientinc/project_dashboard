<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useApi } from '@/composables/useApi'
import { useEmployeesStore } from '@/stores/employees'
import { utilPctColor, utilBandShapes, downloadCsv } from '@/utils/helpers'
import KpiCard from '@/components/KpiCard.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import UtilizationFilters from '@/components/UtilizationFilters.vue'
import type { DetailedUtilizationEntry, TimeEntry } from '@/types'

const { get } = useApi()

// ---------------------------------------------------------------------------
// Pinia store -- persists filter/sort state across navigation
// ---------------------------------------------------------------------------
const store = useEmployeesStore()
const {
  utilYear, utilTimeFrameType, selectedMonth, selectedQuarter, fyType,
  includeProjectedHours, utilBandFilter, utilSearchTerm, utilTableSortBy,
} = storeToRefs(store)

// ---------------------------------------------------------------------------
// Local state
// ---------------------------------------------------------------------------
const utilData = ref<DetailedUtilizationEntry[]>([])
const utilLoading = ref(false)
const showTimeFrameDefs = ref<number | undefined>(undefined)
const selectedUtilEmployee = ref<string | null>(null)

// Dialog state
const utilDialogOpen = ref(false)
const utilDialogEmployee = ref<DetailedUtilizationEntry | null>(null)
const dialogTimeEntries = ref<TimeEntry[]>([])
const dialogLoading = ref(false)

// Template ref for UtilizationFilters component
const filtersRef = ref<InstanceType<typeof UtilizationFilters> | null>(null)

// ---------------------------------------------------------------------------
// YTD data (parallel fetch, merged into main data)
// ---------------------------------------------------------------------------
const ytdData = ref<DetailedUtilizationEntry[]>([])

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function fetchUtilizationData() {
  utilLoading.value = true
  const timeFrame = filtersRef.value?.timeFrame ?? 'ytd_company'
  const year = utilYear.value
  const projected = includeProjectedHours.value
  try {
    const [mainResult, ytdResult] = await Promise.all([
      get<DetailedUtilizationEntry[]>(
        `/analytics/utilization/detailed?year=${year}&time_frame=${timeFrame}&include_projected=${projected}`
      ),
      // Always fetch YTD (Company) in parallel for the YTD columns
      timeFrame === 'ytd_company'
        ? Promise.resolve(null)
        : get<DetailedUtilizationEntry[]>(
            `/analytics/utilization/detailed?year=${year}&time_frame=ytd_company&include_projected=${projected}`
          ),
    ])
    utilData.value = mainResult
    ytdData.value = ytdResult ?? []
  } catch {
    // error handled by useApi
  } finally {
    utilLoading.value = false
  }
}

// Build a lookup map: employee_id → YTD entry for quick access in table
const ytdMap = computed(() => {
  const map = new Map<number, DetailedUtilizationEntry>()
  for (const entry of ytdData.value) {
    map.set(entry.employee_id, entry)
  }
  return map
})

onMounted(fetchUtilizationData)
watch(
  [utilYear, utilTimeFrameType, selectedMonth, selectedQuarter, fyType, includeProjectedHours],
  fetchUtilizationData,
  { flush: 'post' },
)

// ---------------------------------------------------------------------------
// Utilization band filter options
// ---------------------------------------------------------------------------
const utilBandOptions = [
  { label: '\u2265111% Over', min: 111, max: Infinity },
  { label: '97-110% Good', min: 97, max: 111 },
  { label: '80-96% Fair', min: 80, max: 97 },
  { label: '51-79% Low', min: 51, max: 80 },
  { label: '\u226450% Under', min: 0, max: 51 },
]

// ---------------------------------------------------------------------------
// Filtered data
// ---------------------------------------------------------------------------
const filteredUtilData = computed(() => {
  let result = utilData.value

  if (utilBandFilter.value.length > 0) {
    result = result.filter(e => {
      const pct = Math.round(e.utilization_pct ?? 0)
      return utilBandFilter.value.some(label => {
        const band = utilBandOptions.find(b => b.label === label)
        if (!band) return false
        return pct >= band.min && pct < band.max
      })
    })
  }

  if (utilSearchTerm.value) {
    const term = utilSearchTerm.value.toLowerCase()
    result = result.filter(e => (e.employee_name ?? '').toLowerCase().includes(term))
  }

  return result
})

// ---------------------------------------------------------------------------
// Merge YTD fields into filtered data for table display
// ---------------------------------------------------------------------------
const filteredUtilDataWithYtd = computed(() => {
  const tf = filtersRef.value?.timeFrame ?? ''
  const isYtdCompany = tf === 'ytd_company'
  return filteredUtilData.value.map(e => {
    if (isYtdCompany) {
      // When already viewing YTD Company, main data IS the YTD data
      const available = Math.max((e.possible_hours ?? 0) - (e.pto_hours ?? 0), 0)
      return {
        ...e,
        ytd_possible_hours: e.possible_hours,
        ytd_actual_billable_hours: e.effective_billable_hours ?? e.actual_billable_hours,
        ytd_pto_hours: e.pto_hours,
        ytd_utilization_pct: available > 0
          ? ((e.effective_billable_hours ?? e.actual_billable_hours) / available * 100)
          : 0,
      }
    }
    const ytd = ytdMap.value.get(e.employee_id)
    if (!ytd) return { ...e, ytd_possible_hours: 0, ytd_actual_billable_hours: 0, ytd_pto_hours: 0, ytd_utilization_pct: 0 }
    const ytdAvailable = Math.max((ytd.possible_hours ?? 0) - (ytd.pto_hours ?? 0), 0)
    return {
      ...e,
      ytd_possible_hours: ytd.possible_hours,
      ytd_actual_billable_hours: ytd.effective_billable_hours ?? ytd.actual_billable_hours,
      ytd_pto_hours: ytd.pto_hours,
      ytd_utilization_pct: ytdAvailable > 0
        ? ((ytd.effective_billable_hours ?? ytd.actual_billable_hours) / ytdAvailable * 100)
        : 0,
    }
  })
})

// ---------------------------------------------------------------------------
// KPI computeds
// ---------------------------------------------------------------------------
const utilTotalEmployees = computed(() => filteredUtilData.value.length)
const utilAvgUtilization = computed(() => {
  const vals = filteredUtilData.value
    .map((e) => e.utilization_pct)
    .filter((v): v is number => v != null)
  if (vals.length === 0) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
})
const utilOverTarget = computed(() => filteredUtilData.value.filter((e) => (e.utilization_pct ?? 0) >= 80).length)
const utilUnderTarget = computed(() => filteredUtilData.value.filter((e) => (e.utilization_pct ?? 0) < 80).length)
const utilPtoHours = computed(() => filteredUtilData.value.reduce((sum, e) => sum + (e.pto_hours ?? 0), 0))
const utilTotalPossibleHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.possible_hours ?? 0), 0))
const utilTotalActualHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.actual_hours ?? 0), 0))
const utilTotalBillableHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.actual_billable_hours ?? 0), 0))
const utilTotalProjectedMissingHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.projected_hours ?? 0), 0))
const utilTotalEffectiveBillableHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.effective_billable_hours ?? 0), 0))
const utilTotalHolidayHrs = computed(() => filteredUtilData.value.reduce((s, e) => s + (e.holiday_hours ?? 0), 0))

// ---------------------------------------------------------------------------
// Utilization band summary cards
// ---------------------------------------------------------------------------
const utilBandSummary = computed(() => {
  const data = filteredUtilData.value
  const bands = [
    { label: '111%+', icon: '\uD83D\uDFE3', borderColor: '#9C27B0', bgRgba: 'rgba(156, 39, 176, 0.12)', min: 111, max: Infinity, employees: [] as { name: string; pct: number }[] },
    { label: '97% - 110%', icon: '\uD83D\uDFE2', borderColor: '#28a745', bgRgba: 'rgba(40, 167, 69, 0.12)', min: 97, max: 111, employees: [] as { name: string; pct: number }[] },
    { label: '80% - 96%', icon: '\uD83D\uDFE1', borderColor: '#ffc107', bgRgba: 'rgba(255, 193, 7, 0.12)', min: 80, max: 97, employees: [] as { name: string; pct: number }[] },
    { label: '51% - 79%', icon: '\uD83D\uDFE0', borderColor: '#fd7e14', bgRgba: 'rgba(253, 126, 20, 0.12)', min: 51, max: 80, employees: [] as { name: string; pct: number }[] },
    { label: '\u2264 50%', icon: '\uD83D\uDD34', borderColor: '#dc3545', bgRgba: 'rgba(220, 53, 69, 0.12)', min: 0, max: 51, employees: [] as { name: string; pct: number }[] },
  ]

  for (const emp of data) {
    const pct = Math.round(emp.utilization_pct ?? 0)
    for (const band of bands) {
      if (pct >= band.min && (band.max === Infinity ? true : pct < band.max)) {
        band.employees.push({ name: emp.employee_name, pct: Math.round(emp.utilization_pct ?? 0) })
        break
      }
    }
  }

  // Sort employees within each band by pct descending
  for (const band of bands) {
    band.employees.sort((a, b) => b.pct - a.pct)
  }

  return bands
})

// ---------------------------------------------------------------------------
// Employee options for individual chart selector
// ---------------------------------------------------------------------------
const utilEmployeeOptions = computed(() => {
  return filteredUtilData.value
    .filter(e => e.monthly_breakdown && e.monthly_breakdown.length > 0)
    .map(e => ({ title: e.employee_name, value: e.employee_name }))
    .sort((a, b) => a.title.localeCompare(b.title))
})

// ---------------------------------------------------------------------------
// Individual employee utilization chart
// ---------------------------------------------------------------------------
const selectedEmployeeChartData = computed(() => {
  if (!selectedUtilEmployee.value) return []
  const emp = filteredUtilData.value.find(e => e.employee_name === selectedUtilEmployee.value)
  if (!emp?.monthly_breakdown?.length) return []

  const traces = [
    {
      type: 'bar' as const,
      name: 'Actual Billable Hours',
      x: emp.monthly_breakdown.map(m => m.month),
      y: emp.monthly_breakdown.map(m => m.actual_billable_hours ?? 0),
      marker: { color: '#4CAF50' },
    },
    {
      type: 'bar' as const,
      name: 'Possible Hours',
      x: emp.monthly_breakdown.map(m => m.month),
      y: emp.monthly_breakdown.map(m => m.possible_hours ?? 0),
      marker: { color: '#E0E0E0' },
    },
  ]

  if (includeProjectedHours.value) {
    traces.push({
      type: 'bar' as const,
      name: 'Projected Hours',
      x: emp.monthly_breakdown.map(m => m.month),
      y: emp.monthly_breakdown.map(m => m.projected_hours ?? 0),
      marker: { color: '#2196F3' },
    })
  }

  return traces
})

const selectedEmployeeChartLayout = {
  height: 350,
  margin: { t: 20, r: 20, b: 60, l: 50 },
  barmode: 'group' as const,
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  legend: { orientation: 'h' as const, y: -0.3 },
}

// ---------------------------------------------------------------------------
// Planned vs Actual bar chart (all employees)
// ---------------------------------------------------------------------------
const plannedVsActualData = computed(() => {
  const data = filteredUtilData.value
  if (data.length === 0) return []

  const sorted = [...data].sort((a, b) => (b.actual_billable_hours ?? 0) - (a.actual_billable_hours ?? 0)).slice(0, 20)

  const traces = [
    {
      type: 'bar' as const,
      name: 'Actual Billable Hours',
      x: sorted.map(e => e.employee_name),
      y: sorted.map(e => e.actual_billable_hours ?? 0),
      marker: { color: '#4CAF50' },
    },
    {
      type: 'bar' as const,
      name: 'Possible Hours',
      x: sorted.map(e => e.employee_name),
      y: sorted.map(e => e.possible_hours ?? 0),
      marker: { color: '#E0E0E0' },
    },
  ]

  if (includeProjectedHours.value) {
    traces.push({
      type: 'bar' as const,
      name: 'Projected Hours',
      x: sorted.map(e => e.employee_name),
      y: sorted.map(e => e.projected_hours ?? 0),
      marker: { color: '#2196F3' },
    })
  }

  return traces
})

const plannedVsActualLayout = {
  height: 400,
  margin: { t: 20, r: 20, b: 120, l: 50 },
  barmode: 'group' as const,
  xaxis: { tickangle: -45 },
  yaxis: { title: { text: 'Hours' } },
  legend: { orientation: 'h' as const, y: -0.4 },
}

// ---------------------------------------------------------------------------
// v-data-table headers for Utilization Overview
// ---------------------------------------------------------------------------
const utilHeaders = [
  { title: 'Employee', key: 'employee_name', minWidth: '160px' },
  { title: 'Possible Billable Hrs', key: 'possible_hours', minWidth: '140px', align: 'end' as const },
  { title: 'Actual Hrs', key: 'actual_hours', minWidth: '100px', align: 'end' as const },
  { title: 'Actual Billable Hrs', key: 'actual_billable_hours', minWidth: '130px', align: 'end' as const },
  { title: 'Projected Missing Hrs', key: 'projected_hours', minWidth: '140px', align: 'end' as const },
  { title: 'Effective Billable Hrs', key: 'effective_billable_hours', minWidth: '150px', align: 'end' as const },
  { title: 'PTO Hrs', key: 'pto_hours', minWidth: '90px', align: 'end' as const },
  { title: 'Holiday Hrs', key: 'holiday_hours', minWidth: '100px', align: 'end' as const },
  { title: 'Other Non-billable Hrs', key: 'other_nonbillable_hours', minWidth: '150px', align: 'end' as const },
  { title: 'Billable Utilization %', key: 'utilization_pct', minWidth: '140px', align: 'end' as const },
  { title: 'Status', key: 'status', minWidth: '100px' },
  { title: 'YTD Possible Billable Hrs', key: 'ytd_possible_hours', minWidth: '160px', align: 'end' as const },
  { title: 'YTD Actual Billable Hrs', key: 'ytd_actual_billable_hours', minWidth: '160px', align: 'end' as const },
  { title: 'YTD Billable Utilization %', key: 'ytd_utilization_pct', minWidth: '170px', align: 'end' as const },
]

// ---------------------------------------------------------------------------
// Cumulative utilization chart - line per employee (top 10 by hours)
// ---------------------------------------------------------------------------
const utilChartData = computed(() => {
  if (filteredUtilData.value.length === 0) return []

  // Pick top 10 employees by actual hours for readability
  const sorted = [...filteredUtilData.value]
    .filter((e) => e.monthly_breakdown && e.monthly_breakdown.length > 0)
    .sort((a, b) => b.actual_hours - a.actual_hours)
    .slice(0, 10)

  const traces = sorted.map((emp) => ({
    type: 'scatter' as const,
    mode: 'lines+markers' as const,
    name: emp.employee_name,
    x: emp.monthly_breakdown.map((m) => m.month),
    y: emp.monthly_breakdown.map((m) => m.utilization_pct ?? 0),
  }))

  return traces
})

const utilChartLayout = computed(() => ({
  height: 400,
  margin: { t: 20, r: 20, b: 60, l: 50 },
  xaxis: { title: { text: 'Month' }, tickangle: -45 },
  yaxis: { title: { text: 'Utilization %' }, range: [0, 120] },
  legend: { orientation: 'h' as const, y: -0.3 },
  shapes: utilBandShapes(120),
}))

// ---------------------------------------------------------------------------
// Dialog: row click handler
// ---------------------------------------------------------------------------
async function onUtilRowClicked(item: DetailedUtilizationEntry) {
  utilDialogEmployee.value = item
  utilDialogOpen.value = true
  dialogLoading.value = true
  try {
    const dr = filtersRef.value?.dateRange
    dialogTimeEntries.value = await get<TimeEntry[]>('/time-entries/', {
      params: {
        employee_id: item.employee_id,
        start_date: dr?.startDate ?? '',
        end_date: dr?.endDate ?? '',
      },
    })
  } catch {
    dialogTimeEntries.value = []
  } finally {
    dialogLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Dialog: Streamlit-style step cards and variable reference table (HTML)
// ---------------------------------------------------------------------------
// Badge colors using rgba so they work on both light and dark surfaces
const badgeColors: Record<string, string> = {
  workdays: 'rgba(59, 130, 246, 0.15)',    // blue
  holidays: 'rgba(59, 130, 246, 0.15)',    // blue
  daily_hrs: 'rgba(59, 130, 246, 0.15)',   // blue
  fte: 'rgba(59, 130, 246, 0.15)',         // blue
  proration: 'rgba(59, 130, 246, 0.15)',   // blue
  possible: 'rgba(99, 102, 241, 0.15)',    // indigo
  pto: 'rgba(245, 158, 11, 0.15)',         // amber
  available: 'rgba(16, 185, 129, 0.15)',   // green
  actual_billable: 'rgba(139, 92, 246, 0.15)', // purple
  projected: 'rgba(236, 72, 153, 0.15)',   // pink
  effective: 'rgba(14, 165, 233, 0.15)',   // sky
  utilization: 'rgba(234, 179, 8, 0.15)',  // yellow
}

const defaultBadgeBg = 'rgba(100, 116, 139, 0.1)'

function badge(colorKey: string, label: string, value: string): string {
  return `<span style="display:inline-block;padding:2px 8px;border-radius:4px;margin:0 2px;font-size:14px;background:${badgeColors[colorKey] ?? defaultBadgeBg}">${label} <strong>${value}</strong></span>`
}

function resultBadge(colorKey: string, value: string): string {
  return `<span style="display:inline-block;padding:2px 8px;border-radius:4px;margin:0 2px;font-size:14px;background:${badgeColors[colorKey] ?? defaultBadgeBg};font-weight:700">${value}</span>`
}

function stepCard(accentColor: string, stepLabel: string, formulaHtml: string): string {
  return `<div style="margin-bottom:10px;padding:10px 14px;background:rgba(100, 116, 139, 0.06);border-radius:8px;border-left:3px solid ${accentColor};">
    <div style="font-size:12px;opacity:0.6;margin-bottom:4px;">${stepLabel}</div>
    <div style="line-height:1.8;">${formulaHtml}</div>
  </div>`
}

const dialogCalculationHtml = computed(() => {
  const emp = utilDialogEmployee.value
  if (!emp) return ''

  const workdays = emp.workdays_total ?? 0
  const holidays = emp.holidays_total ?? 0
  const possible = emp.possible_hours ?? 0
  const pto = emp.pto_hours ?? 0
  const available = Math.max(possible - pto, 0)
  const actualBillable = emp.actual_billable_hours ?? 0
  const projectedMissing = emp.projected_hours ?? 0
  const effectiveBillable = emp.effective_billable_hours ?? 0
  const utilPct = emp.utilization_pct ?? 0
  const ftePct = (emp.target_allocation ?? 1) - (emp.overhead_allocation ?? 0)
  const proration = emp.employment_proration ?? 1

  // Step 1: Possible Billable Hours
  const step1 = stepCard('#6366f1',
    'Step 1: Possible Billable Hours',
    `(${badge('workdays', 'Workdays', String(workdays))} &minus; ${badge('holidays', 'Holidays', String(holidays))}) &times; ${badge('daily_hrs', 'Daily Hrs', '8.0')} &times; ${badge('fte', 'FTE%', ftePct.toFixed(2))} &times; ${badge('proration', 'Proration', proration.toFixed(2))} = ${resultBadge('possible', possible.toFixed(1))}`
  )

  // Step 2: Available Work Hours
  const step2 = stepCard('#22c55e',
    'Step 2: Available Work Hours',
    `${badge('possible', 'Possible Billable Hrs', possible.toFixed(1))} &minus; ${badge('pto', 'PTO Hours', pto.toFixed(1))} = ${resultBadge('available', available.toFixed(1))}`
  )

  // Step 3: Effective Billable Hours
  const step3 = stepCard('#a855f7',
    'Step 3: Effective Billable Hours',
    `${badge('actual_billable', 'Actual Billable Hrs', actualBillable.toFixed(1))} + ${badge('projected', 'Projected Missing Hrs', projectedMissing.toFixed(1))} = ${resultBadge('effective', effectiveBillable.toFixed(1))}`
  )

  // Step 4: Billable Utilization %
  const step4Formula = available > 0
    ? `${badge('effective', 'Effective Billable Hrs', effectiveBillable.toFixed(1))} &divide; ${badge('available', 'Available Work Hrs', available.toFixed(1))} &times; 100 = ${resultBadge('utilization', utilPct.toFixed(1) + '%')}`
    : `${badge('effective', 'Effective Billable Hrs', effectiveBillable.toFixed(1))} &divide; ${badge('available', 'Available Work Hrs', available.toFixed(1))} &times; 100 = ${resultBadge('utilization', 'N/A')}`
  const step4 = stepCard('#eab308',
    'Step 4: Billable Utilization %',
    step4Formula
  )

  return step1 + step2 + step3 + step4
})

const dialogVariableTableHtml = computed(() => {
  const emp = utilDialogEmployee.value
  if (!emp) return ''

  const workdays = emp.workdays_total ?? 0
  const holidays = emp.holidays_total ?? 0
  const possible = emp.possible_hours ?? 0
  const pto = emp.pto_hours ?? 0
  const available = Math.max(possible - pto, 0)
  const actualBillable = emp.actual_billable_hours ?? 0
  const projectedMissing = emp.projected_hours ?? 0
  const effectiveBillable = emp.effective_billable_hours ?? 0
  const utilPct = emp.utilization_pct ?? 0
  const ftePct = (emp.target_allocation ?? 1) - (emp.overhead_allocation ?? 0)
  const proration = emp.employment_proration ?? 1

  type VarRow = { variable: string; value: string; definition: string; source: string; colorKey: string; highlight?: boolean }
  const rows: VarRow[] = [
    { variable: 'Workdays in Period', value: String(workdays), definition: 'Total scheduled working days', source: 'months table', colorKey: 'workdays' },
    { variable: 'Holiday Days', value: String(holidays), definition: 'Company holidays in period', source: 'months table', colorKey: 'holidays' },
    { variable: 'Daily Scheduled Hours', value: '8.0', definition: 'Standard hours per day', source: 'Constant', colorKey: 'daily_hrs' },
    { variable: 'FTE %', value: ftePct.toFixed(2), definition: 'target_allocation - overhead_allocation', source: 'employees table', colorKey: 'fte' },
    { variable: 'Employment Proration', value: proration.toFixed(2), definition: 'Proportion of period employed', source: 'Calculated from hire/term dates', colorKey: 'proration' },
    { variable: 'Possible Billable Hrs', value: possible.toFixed(1), definition: '(Workdays-Holidays) x 8 x FTE% x Proration', source: 'Calculated', colorKey: 'possible' },
    { variable: 'PTO Hours', value: pto.toFixed(1), definition: 'Approved PTO time', source: 'time_entries (FRINGE.PTO)', colorKey: 'pto' },
    { variable: 'Available Work Hours', value: available.toFixed(1), definition: 'Possible Billable Hrs - PTO Hours', source: 'Calculated', colorKey: 'available' },
    { variable: 'Actual Billable Hours', value: actualBillable.toFixed(1), definition: 'Billable hours logged', source: 'time_entries (billable=1)', colorKey: 'actual_billable' },
    { variable: 'Projected Missing Hrs', value: projectedMissing.toFixed(1), definition: 'Projected hours for missing days from last timesheet entry to end of month', source: 'projected_hours x (missing_days / available_days)', colorKey: 'projected' },
    { variable: 'Effective Billable Hrs', value: effectiveBillable.toFixed(1), definition: 'Actual Billable + Projected Missing', source: 'Calculated', colorKey: 'effective' },
    { variable: 'Billable Utilization %', value: utilPct.toFixed(1) + '%', definition: 'Effective Billable / Available x 100', source: 'Final Result', colorKey: 'utilization', highlight: true },
  ]

  const borderColor = 'rgba(100, 116, 139, 0.2)'
  const thStyle = `background:rgba(100, 116, 139, 0.08);padding:8px 12px;text-align:left;border-bottom:2px solid ${borderColor};font-weight:600;`
  const tdBase = `padding:6px 12px;border-bottom:1px solid ${borderColor};font-size:14px;`

  let html = `<table style="width:100%;border-collapse:collapse;font-size:14px;">
    <tr>
      <th style="${thStyle}">Variable</th>
      <th style="${thStyle}">Value</th>
      <th style="${thStyle}">Definition</th>
      <th style="${thStyle}">Source</th>
    </tr>`

  for (const r of rows) {
    const bg = badgeColors[r.colorKey] ?? defaultBadgeBg
    if (r.highlight) {
      const rowStyle = `background:${bg};font-weight:700;`
      html += `<tr>
        <td style="${tdBase}${rowStyle}">${r.variable}</td>
        <td style="${tdBase}${rowStyle}">${r.value}</td>
        <td style="${tdBase}${rowStyle}">${r.definition}</td>
        <td style="${tdBase}${rowStyle}">${r.source}</td>
      </tr>`
    } else {
      html += `<tr>
        <td style="${tdBase}background:${bg};">${r.variable}</td>
        <td style="${tdBase}background:${bg};font-weight:600;">${r.value}</td>
        <td style="${tdBase}">${r.definition}</td>
        <td style="${tdBase}">${r.source}</td>
      </tr>`
    }
  }

  html += '</table>'
  return html
})

// ---------------------------------------------------------------------------
// Dialog: hours by project (aggregated from time entries)
// ---------------------------------------------------------------------------
const dialogHoursByProject = computed(() => {
  if (!dialogTimeEntries.value.length) return []

  const projectMap = new Map<string, {
    project_id: string; project_name: string
    billable_hrs: number; nonbillable_hrs: number; total_hrs: number; amount: number
  }>()

  for (const te of dialogTimeEntries.value) {
    const key = te.project_id
    const existing = projectMap.get(key) ?? {
      project_id: te.project_id,
      project_name: te.project_name ?? te.project_id,
      billable_hrs: 0, nonbillable_hrs: 0, total_hrs: 0, amount: 0,
    }
    existing.total_hrs += te.hours
    if (te.billable === 1) {
      existing.billable_hrs += te.hours
    } else {
      existing.nonbillable_hrs += te.hours
    }
    existing.amount += te.hours * (te.hourly_rate ?? 0)
    projectMap.set(key, existing)
  }

  const totalHrs = Array.from(projectMap.values()).reduce((s, p) => s + p.total_hrs, 0)
  return Array.from(projectMap.values())
    .map(p => ({ ...p, pct_of_total: totalHrs > 0 ? (p.total_hrs / totalHrs * 100) : 0 }))
    .sort((a, b) => b.total_hrs - a.total_hrs)
})

// ---------------------------------------------------------------------------
// Dialog: formatted timesheet entries
// ---------------------------------------------------------------------------
const dialogTimesheetEntries = computed(() => {
  return dialogTimeEntries.value
    .map(te => ({
      ...te,
      billable_label: te.billable === 1 ? 'Yes' : 'No',
      bill_rate_display: te.hourly_rate ?? 0,
      amount: te.hours * (te.hourly_rate ?? 0),
    }))
    .sort((a, b) => a.date.localeCompare(b.date))
})

// ---------------------------------------------------------------------------
// Export CSV
// ---------------------------------------------------------------------------
function exportUtilCsv() {
  const rows = filteredUtilData.value.map((e) => ({
    Employee: e.employee_name,
    'Possible Billable Hrs': e.possible_hours,
    'Actual Hrs': e.actual_hours,
    'Actual Billable Hrs': e.actual_billable_hours,
    'Projected Missing Hrs': e.projected_hours,
    'Effective Billable Hrs': e.effective_billable_hours ?? '',
    'PTO Hrs': e.pto_hours,
    'Holiday Hrs': e.holiday_hours,
    'Other Non-billable Hrs': e.other_nonbillable_hours ?? '',
    'Billable Utilization %': e.utilization_pct ?? '',
    Status: e.status ?? '',
  }))
  downloadCsv(rows, `utilization_overview_${utilYear.value}_${filtersRef.value?.timeFrame ?? 'ytd_company'}.csv`)
}
</script>

<template>
  <div>
    <!-- Controls -->
    <UtilizationFilters
      ref="filtersRef"
      v-model:year="utilYear"
      v-model:time-frame-type="utilTimeFrameType"
      v-model:selected-month="selectedMonth"
      v-model:selected-quarter="selectedQuarter"
      v-model:fy-type="fyType"
      v-model:include-projected-hours="includeProjectedHours"
      class="mb-4"
    />

    <!-- Utilization Filters -->
    <v-row class="mb-2">
      <v-col cols="12" md="6">
        <div class="d-flex flex-wrap ga-2 align-center">
          <span class="text-caption text-medium-emphasis mr-1">Filter by band:</span>
          <v-chip
            v-for="band in utilBandOptions"
            :key="band.label"
            :color="utilBandFilter.includes(band.label) ? 'primary' : undefined"
            :variant="utilBandFilter.includes(band.label) ? 'flat' : 'outlined'"
            size="small"
            @click="
              utilBandFilter.includes(band.label)
                ? utilBandFilter = utilBandFilter.filter(b => b !== band.label)
                : utilBandFilter = [...utilBandFilter, band.label]
            "
          >
            {{ band.label }}
          </v-chip>
          <v-chip
            v-if="utilBandFilter.length > 0"
            color="grey"
            variant="text"
            size="small"
            @click="utilBandFilter = []"
          >
            Clear
          </v-chip>
        </div>
      </v-col>
      <v-col cols="12" md="3">
        <v-text-field
          v-model="utilSearchTerm"
          prepend-inner-icon="mdi-magnify"
          label="Search by name..."
          clearable
          density="compact"
          hide-details
          @click:clear="utilSearchTerm = ''"
        />
      </v-col>
    </v-row>

    <!-- Time Frame Definitions -->
    <v-expansion-panels v-model="showTimeFrameDefs" class="mb-4">
      <v-expansion-panel>
        <v-expansion-panel-title class="text-subtitle-2">
          Time Frame Definitions
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-list density="compact">
            <v-list-item>
              <strong>Current Month</strong>: The current calendar month
            </v-list-item>
            <v-list-item>
              <strong>YTD (Company)</strong>: Jan 1 through today (company fiscal year)
            </v-list-item>
            <v-list-item>
              <strong>YTD (Gov)</strong>: Oct 1 through today (government fiscal year)
            </v-list-item>
            <v-list-item>
              <strong>QTD (Company)</strong>: Current company quarter to date
            </v-list-item>
            <v-list-item>
              <strong>QTD (Gov)</strong>: Current government quarter to date
            </v-list-item>
            <v-list-item>
              <strong>Q1-Q4</strong>: Specific quarters of the selected year
            </v-list-item>
            <v-list-item>
              <strong>Monthly</strong>: Select a specific month of the selected year
            </v-list-item>
          </v-list>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <!-- KPI Cards - Row 1 -->
    <v-row class="mb-2">
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Employees"
          :value="String(utilTotalEmployees)"
          icon="mdi-account-group"
          color="#1976D2"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Avg Utilization"
          :value="utilAvgUtilization.toFixed(1) + '%'"
          icon="mdi-chart-line"
          :color="utilPctColor(utilAvgUtilization)"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Over Target (&ge;80%)"
          :value="String(utilOverTarget)"
          icon="mdi-arrow-up-bold"
          color="#4CAF50"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Under Target (&lt;80%)"
          :value="String(utilUnderTarget)"
          icon="mdi-arrow-down-bold"
          color="#F44336"
          :loading="utilLoading"
        />
      </v-col>
    </v-row>

    <!-- KPI Cards - Row 2 -->
    <v-row class="mb-2">
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Possible Hrs"
          :value="utilTotalPossibleHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-clock-outline"
          color="#1976D2"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Actual Hrs"
          :value="utilTotalActualHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-clock-check-outline"
          color="#2196F3"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Billable Hrs"
          :value="utilTotalBillableHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-currency-usd"
          color="#4CAF50"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Projected Missing Hrs"
          :value="utilTotalProjectedMissingHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-clock-alert-outline"
          color="#FF9800"
          :loading="utilLoading"
        />
      </v-col>
    </v-row>

    <!-- KPI Cards - Row 3 -->
    <v-row class="mb-4">
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Effective Billable Hrs"
          :value="utilTotalEffectiveBillableHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-check-circle-outline"
          color="#4CAF50"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total PTO Hrs"
          :value="utilPtoHours.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-beach"
          color="#FF9800"
          :loading="utilLoading"
        />
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <KpiCard
          title="Total Holiday Hrs"
          :value="utilTotalHolidayHrs.toFixed(1).replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
          icon="mdi-calendar-star"
          color="#9C27B0"
          :loading="utilLoading"
        />
      </v-col>
    </v-row>

    <!-- Utilization Band Summary Cards -->
    <v-row class="mb-4" v-if="!utilLoading" align="start">
      <v-col v-for="band in utilBandSummary" :key="band.label" cols="12" sm="6" md style="min-width: 0">
        <div
          :style="{
            backgroundColor: band.bgRgba,
            padding: '15px',
            borderRadius: '10px',
            borderLeft: '5px solid ' + band.borderColor,
          }"
        >
          <div class="d-flex align-center mb-2">
            <span style="font-size: 24px; margin-right: 8px">{{ band.icon }}</span>
            <span style="font-size: 18px; font-weight: bold">{{ band.label }}</span>
          </div>
          <div style="font-size: 28px; font-weight: bold; margin-bottom: 5px">
            {{ band.employees.length }} Employees
          </div>
          <div class="text-medium-emphasis" style="font-size: 13px;">
            <template v-if="band.employees.length > 0">
              <div v-for="emp in band.employees" :key="emp.name">
                {{ emp.name }} ({{ emp.pct }}%)
              </div>
            </template>
            <em v-else>None</em>
          </div>
        </div>
      </v-col>
    </v-row>

    <!-- Loading skeleton -->
    <v-skeleton-loader v-if="utilLoading" type="table" class="mb-4" />

    <!-- Data Table -->
    <v-card v-else class="mb-4">
      <v-card-text class="pa-0">
        <div class="d-flex align-center justify-space-between pa-3 pb-0">
          <div class="d-flex align-center ga-2">
            <div class="text-caption text-medium-emphasis">
              {{ filteredUtilData.length }} of {{ utilData.length }} employees &mdash; Click a row to view details
            </div>
            <v-menu location="bottom start" :close-on-content-click="false" max-width="720">
              <template v-slot:activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" variant="text" size="small" prepend-icon="mdi-information-outline" color="primary">
                  Logic for Utilization Table
                </v-btn>
              </template>
              <v-card class="pa-4">
                <v-card-title class="text-subtitle-1 font-weight-bold pa-0 mb-2">
                  Logic for Utilization Table
                </v-card-title>
                <v-card-text class="pa-0 text-body-2">
                  <p class="mb-2">For each employee in the utilization table:</p>
                  <v-table density="compact" class="mb-3 text-caption">
                    <thead>
                      <tr>
                        <th style="min-width:160px">Column</th>
                        <th style="min-width:180px">Source</th>
                        <th>Calculation</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Employee</td>
                        <td>employees_df['name']</td>
                        <td>Direct from employees table</td>
                      </tr>
                      <tr>
                        <td>Possible Billable Hrs</td>
                        <td>metrics['possible']</td>
                        <td>(working_days &minus; holidays) &times; (target_allocation &minus; overhead_allocation) &times; 8</td>
                      </tr>
                      <tr>
                        <td>Actual Hrs</td>
                        <td>metrics['actuals']</td>
                        <td>Sum of ALL hours logged (billable + non-billable)</td>
                      </tr>
                      <tr>
                        <td>Actual Billable Hrs</td>
                        <td>metrics['actuals']</td>
                        <td>Sum of hours where billable=1</td>
                      </tr>
                      <tr>
                        <td>Projected Missing Hrs</td>
                        <td>Calculated (current month only)</td>
                        <td>projected_hours &times; (missing_working_days / available_working_days)</td>
                      </tr>
                      <tr>
                        <td>Effective Billable Hrs</td>
                        <td>Calculated</td>
                        <td>actual_billable_hours + projected_missing_hours</td>
                      </tr>
                      <tr>
                        <td>PTO Hrs</td>
                        <td>time_entries (FRINGE.PTO)</td>
                        <td>Sum of hours from time_entries for PTO project</td>
                      </tr>
                      <tr>
                        <td>Holiday Hrs</td>
                        <td>time_entries (FRINGE.HOL)</td>
                        <td>Sum of hours for Holiday project (for reference; not in denominator)</td>
                      </tr>
                      <tr>
                        <td>Other Non-billable Hrs</td>
                        <td>Calculated</td>
                        <td>(actual_hours &minus; actual_billable_hours) &minus; pto_hours</td>
                      </tr>
                      <tr>
                        <td>Billable Utilization %</td>
                        <td>Calculated</td>
                        <td>(effective_billable_hours / (possible_hours &minus; pto_hours)) &times; 100</td>
                      </tr>
                      <tr>
                        <td>Status</td>
                        <td>Calculated</td>
                        <td>&ge;111% Over, 97-110% Good, 80-96% Fair, 51-79% Low, &le;50% Under</td>
                      </tr>
                      <tr class="bg-surface-variant">
                        <td>YTD Possible Billable Hrs</td>
                        <td>ytd_metrics['possible']</td>
                        <td>Sum of possible hours from Jan 1 to end of selected month</td>
                      </tr>
                      <tr class="bg-surface-variant">
                        <td>YTD Actual Billable Hrs</td>
                        <td>ytd_metrics['actuals']</td>
                        <td>Sum of actual billable hours from Jan 1 to end of selected month</td>
                      </tr>
                      <tr class="bg-surface-variant">
                        <td>YTD Billable Utilization %</td>
                        <td>Calculated</td>
                        <td>(ytd_actual_billable_hours / (ytd_possible_hours &minus; ytd_pto_hours)) &times; 100</td>
                      </tr>
                    </tbody>
                  </v-table>
                  <p class="mb-1 font-weight-medium">Notes:</p>
                  <ul class="text-caption" style="padding-left: 20px;">
                    <li>Possible hours use (working_days &minus; holidays) from the months table as the authoritative holiday source.</li>
                    <li>For the current month, missing billable hours are projected using allocation FTE data from the employee's last timesheet entry through end of month.</li>
                    <li>Effective Billable Hrs = Actual Billable + Projected Missing.</li>
                    <li>Use the "Include projected hours" toggle to switch between projected and actual-only views.</li>
                    <li>Possible hours are adjusted for employees hired or terminated mid-month (employment proration).</li>
                    <li>Billable Utilization % uses available hours (possible &minus; PTO) as the denominator.</li>
                    <li>Click on any row to view project-level breakdown.</li>
                    <li>YTD columns show cumulative data from January 1st through the end of the selected month.</li>
                  </ul>
                </v-card-text>
              </v-card>
            </v-menu>
          </div>
          <v-btn
            variant="outlined"
            size="small"
            prepend-icon="mdi-download"
            @click="exportUtilCsv"
            :disabled="filteredUtilData.length === 0"
          >
            Export CSV
          </v-btn>
        </div>
        <v-data-table
          :headers="utilHeaders"
          :items="filteredUtilDataWithYtd"
          v-model:sort-by="utilTableSortBy"
          density="compact"
          hover
          class="cursor-pointer"
          items-per-page="25"
          @click:row="(_e: Event, { item }: { item: any }) => onUtilRowClicked(item)"
        >
          <template #item.possible_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.actual_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.actual_billable_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.projected_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.effective_billable_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.pto_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.holiday_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.other_nonbillable_hours="{ value }">
            {{ value != null ? value.toFixed(1) : '-' }}
          </template>
          <template #item.utilization_pct="{ value }">
            <v-chip
              v-if="value != null"
              :color="utilPctColor(value)"
              size="small"
              label
              variant="tonal"
            >
              {{ value.toFixed(1) }}%
            </v-chip>
            <span v-else>-</span>
          </template>
          <template #item.status="{ value }">
            {{ value ?? '-' }}
          </template>
          <template #item.ytd_possible_hours="{ value }">
            <span class="text-medium-emphasis">
              {{ value != null ? value.toFixed(1) : '-' }}
            </span>
          </template>
          <template #item.ytd_actual_billable_hours="{ value }">
            <span class="text-medium-emphasis">
              {{ value != null ? value.toFixed(1) : '-' }}
            </span>
          </template>
          <template #item.ytd_utilization_pct="{ value }">
            <v-chip
              v-if="value != null"
              :color="utilPctColor(value)"
              size="small"
              label
              variant="tonal"
            >
              {{ value.toFixed(1) }}%
            </v-chip>
            <span v-else>-</span>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Cumulative Utilization Chart -->
    <v-card v-if="!utilLoading && utilChartData.length > 0" class="mb-4">
      <v-card-title class="text-subtitle-1 font-weight-medium">
        Cumulative Utilization by Month (Top 10)
      </v-card-title>
      <v-card-text>
        <PlotlyChart :data="utilChartData" :layout="utilChartLayout" />
      </v-card-text>
    </v-card>

    <!-- Planned vs Actual Billable Hours -->
    <v-card v-if="!utilLoading && plannedVsActualData.length > 0" class="mb-4">
      <v-card-title class="text-subtitle-1 font-weight-medium">
        Planned vs Actual Billable Hours (Top 20)
      </v-card-title>
      <v-card-text>
        <PlotlyChart :data="plannedVsActualData" :layout="plannedVsActualLayout" />
      </v-card-text>
    </v-card>

    <!-- Individual Employee Utilization -->
    <v-card v-if="!utilLoading && utilEmployeeOptions.length > 0" class="mb-4">
      <v-card-title class="text-subtitle-1 font-weight-medium">
        Individual Employee Utilization
      </v-card-title>
      <v-card-text>
        <v-select
          v-model="selectedUtilEmployee"
          label="Select employee"
          :items="utilEmployeeOptions"
          item-title="title"
          item-value="value"
          clearable
          density="compact"
          class="mb-4"
          style="max-width: 400px;"
        />
        <PlotlyChart
          v-if="selectedEmployeeChartData.length > 0"
          :data="selectedEmployeeChartData"
          :layout="selectedEmployeeChartLayout"
        />
        <v-alert v-else-if="selectedUtilEmployee" type="info" variant="tonal" density="compact">
          No monthly breakdown data available for this employee.
        </v-alert>
      </v-card-text>
    </v-card>
    <!-- Utilization Detail Dialog -->
    <v-dialog v-model="utilDialogOpen" max-width="1100" scrollable>
      <v-card v-if="utilDialogEmployee">
        <v-card-title class="d-flex align-center justify-space-between">
          <span>Employee Timesheet &amp; Utilization Detail</span>
          <v-btn icon="mdi-close" variant="text" @click="utilDialogOpen = false" />
        </v-card-title>

        <v-card-text>
          <!-- Employee Name & Period -->
          <div class="text-h5 font-weight-bold mb-1">
            {{ utilDialogEmployee.employee_name }}
            <v-chip
              class="ml-2"
              :color="utilPctColor(utilDialogEmployee.utilization_pct)"
              variant="tonal"
              size="small"
            >
              {{ (utilDialogEmployee.utilization_pct ?? 0).toFixed(1) }}%
            </v-chip>
            <v-chip v-if="utilDialogEmployee.status" class="ml-1" size="small" variant="flat">
              {{ utilDialogEmployee.status }}
            </v-chip>
          </div>
          <div class="text-caption text-medium-emphasis mb-4">
            {{ filtersRef?.periodLabel ?? '' }}
          </div>

          <!-- Section 1: Calculation Breakdown -->
          <div class="text-h6 mb-3">Billable Utilization Calculation</div>

          <!-- Streamlit-style Step Cards -->
          <div v-html="dialogCalculationHtml" class="mb-4"></div>

          <!-- Multi-month note -->
          <div
            v-if="utilTimeFrameType !== 'Monthly'"
            class="text-caption text-medium-emphasis mb-4"
            style="font-style: italic;"
          >
            Note: For multi-month periods, possible hours are calculated per-month with per-month proration, then summed. The single proration factor shown above is an approximate overall value.
          </div>

          <!-- Variable Reference Table (always visible) -->
          <div class="text-subtitle-1 font-weight-medium mb-2">Variable Reference</div>
          <div v-html="dialogVariableTableHtml" class="mb-6"></div>

          <!-- Section 2: Hours by Project -->
          <div class="text-h6 mb-3">Hours by Project</div>
          <v-data-table
            :items="dialogHoursByProject"
            :headers="[
              { title: 'Project Code', key: 'project_id' },
              { title: 'Project', key: 'project_name' },
              { title: 'Billable Hrs', key: 'billable_hrs', align: 'end' as const },
              { title: 'Non-billable Hrs', key: 'nonbillable_hrs', align: 'end' as const },
              { title: 'Total Hrs', key: 'total_hrs', align: 'end' as const },
              { title: 'Amount', key: 'amount', align: 'end' as const },
              { title: '% of Total', key: 'pct_of_total', align: 'end' as const },
            ]"
            :loading="dialogLoading"
            density="compact"
            :items-per-page="-1"
            hide-default-footer
            class="mb-6"
          >
            <template #item.billable_hrs="{ value }">{{ value.toFixed(1) }}</template>
            <template #item.nonbillable_hrs="{ value }">{{ value.toFixed(1) }}</template>
            <template #item.total_hrs="{ value }">{{ value.toFixed(1) }}</template>
            <template #item.amount="{ value }">${{ value.toFixed(2) }}</template>
            <template #item.pct_of_total="{ value }">{{ value.toFixed(1) }}%</template>
          </v-data-table>

          <!-- Section 3: Timesheet Entries -->
          <div class="text-h6 mb-3">Timesheet Entries</div>
          <v-data-table
            :items="dialogTimesheetEntries"
            :headers="[
              { title: 'Date', key: 'date' },
              { title: 'Project Code', key: 'project_id' },
              { title: 'Project', key: 'project_name' },
              { title: 'Hours', key: 'hours', align: 'end' as const },
              { title: 'Billable', key: 'billable_label' },
              { title: 'Bill Rate', key: 'bill_rate_display', align: 'end' as const },
              { title: 'Amount', key: 'amount', align: 'end' as const },
              { title: 'Description', key: 'description' },
            ]"
            :loading="dialogLoading"
            density="compact"
            :items-per-page="25"
          >
            <template #item.hours="{ value }">{{ value.toFixed(2) }}</template>
            <template #item.bill_rate_display="{ value }">
              {{ value ? '$' + value.toFixed(2) : '-' }}
            </template>
            <template #item.amount="{ value }">${{ value.toFixed(2) }}</template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>
