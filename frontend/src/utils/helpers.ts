/**
 * Format a number as abbreviated currency: $1.2M, $450K, $1,234
 */
export function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`
  }
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

/**
 * Format a number as full currency: $1,234,567
 */
export function formatCurrencyFull(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

/**
 * Format a number as a percentage: 75.2%
 */
export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

/**
 * Format a number as local currency with 2 decimal places: $1,234.56
 * Returns '-' for null/undefined values.
 */
export function formatCurrencyLocal(value: number | null | undefined): string {
  if (value == null) return '-'
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/**
 * Return a hex color based on allocation percentage thresholds.
 * - >120%: red, >100%: orange, >=80%: green, else: blue
 */
export function allocPctColor(v: number | null | undefined): string {
  if (v == null) return '#2196F3'
  if (v > 120) return '#F44336'
  if (v > 100) return '#FF9800'
  if (v >= 80) return '#4CAF50'
  return '#2196F3'
}

/**
 * Return a Vuetify chip color name based on allocation status string.
 */
export function allocStatusColor(s: string): string {
  if (s === 'Over-Allocated') return 'error'
  if (s === 'Fully Allocated' || s === 'On Target') return 'success'
  if (s === 'Under-Allocated') return 'info'
  if (s === 'Warning') return 'warning'
  return 'grey'
}

/**
 * 5-band utilization status thresholds matching the Utilization Band Summary
 * cards on the /employees/utilization_overview page.
 *
 *  Band          Border         Background
 *  >=111% Over   #9C27B0 purple #f3e5f5
 *  97-110% Good  #28A745 green  #e8f5e9
 *  80-96%  Fair  #FFC107 amber  #fff8e1
 *  51-79%  Low   #FD7E14 orange #fff3e0
 *  <=50%   Under #DC3545 red    #ffebee
 */
interface UtilBand { border: string; bg: string }
const UTIL_BANDS: { min: number; band: UtilBand }[] = [
  { min: 111, band: { border: '#9C27B0', bg: '#f3e5f5' } },
  { min: 97,  band: { border: '#28A745', bg: '#e8f5e9' } },
  { min: 80,  band: { border: '#FFC107', bg: '#fff8e1' } },
  { min: 51,  band: { border: '#FD7E14', bg: '#fff3e0' } },
  { min: -Infinity, band: { border: '#DC3545', bg: '#ffebee' } },
]

function _band(v: number | null | undefined): UtilBand {
  if (v == null) return UTIL_BANDS[UTIL_BANDS.length - 1]!.band
  const rounded = Math.round(v)
  for (const { min, band } of UTIL_BANDS) {
    if (rounded >= min) return band
  }
  return UTIL_BANDS[UTIL_BANDS.length - 1]!.band
}

/** Return the border / accent color for a utilization percentage. */
export function utilPctColor(v: number | null | undefined): string {
  return _band(v).border
}

/** Return the light background color for a utilization percentage. */
export function utilPctBgColor(v: number | null | undefined): string {
  return _band(v).bg
}

/**
 * Return Plotly shape objects for utilization band background rectangles.
 * Use in a chart layout's `shapes` array. `yMax` controls the top of the
 * topmost band (default 120 for charts with y-range 0–120).
 */
export function utilBandShapes(yMax = 120): Record<string, unknown>[] {
  return [
    // ≤50% Under (red)
    { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 51, fillcolor: '#DC3545', opacity: 0.08, line: { width: 0 } },
    // 51-79% Low (orange)
    { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 51, y1: 80, fillcolor: '#FD7E14', opacity: 0.08, line: { width: 0 } },
    // 80-96% Fair (amber)
    { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 80, y1: 97, fillcolor: '#FFC107', opacity: 0.08, line: { width: 0 } },
    // 97-110% Good (green)
    { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 97, y1: 111, fillcolor: '#28A745', opacity: 0.08, line: { width: 0 } },
    // >=111% Over (purple)
    { type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 111, y1: yMax, fillcolor: '#9C27B0', opacity: 0.08, line: { width: 0 } },
    // 80% target line
    { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 80, y1: 80, line: { color: '#DC3545', dash: 'dash', width: 1.5 } },
  ]
}

/**
 * Trigger a client-side CSV download from arrays of objects.
 */
export function downloadCsv(rows: Record<string, unknown>[], filename: string): void {
  if (rows.length === 0) return

  const headers = Object.keys(rows[0]!)
  const csvLines = [
    headers.join(','),
    ...rows.map((row) =>
      headers
        .map((h) => {
          const val = row[h]
          const str = val == null ? '' : String(val)
          // Escape quotes and wrap in quotes if contains comma/quote/newline
          if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return `"${str.replace(/"/g, '""')}"`
          }
          return str
        })
        .join(',')
    ),
  ]

  const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
