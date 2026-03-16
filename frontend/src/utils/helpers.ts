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
 * Return a hex color based on utilization percentage thresholds.
 * - >=80%: green, >=60%: orange, else: red
 */
export function utilPctColor(v: number | null | undefined): string {
  if (v == null) return '#F44336'
  if (v >= 80) return '#4CAF50'
  if (v >= 60) return '#FF9800'
  return '#F44336'
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
