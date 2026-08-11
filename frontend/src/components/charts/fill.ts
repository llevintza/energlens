import type { CompareSeries, SeriesPoint } from '../../api/types'

export interface ChartRow {
  period: string
  [key: string]: string | number | null
}

function nextMonth(period: string): string {
  const [year, month] = period.split('-').map(Number)
  return month === 12
    ? `${year + 1}-01`
    : `${year}-${String(month + 1).padStart(2, '0')}`
}

/** Expand "YYYY-MM" points to a contiguous month axis, missing months = null,
 * so line charts show honest gaps instead of interpolating across them. */
export function monthRows(points: SeriesPoint[], key = 'value'): ChartRow[] {
  if (points.length === 0) return []
  const byPeriod = new Map(points.map((p) => [p.period, p.value]))
  const rows: ChartRow[] = []
  const last = points[points.length - 1].period
  for (let m = points[0].period; m <= last; m = nextMonth(m)) {
    rows.push({ period: m, [key]: byPeriod.get(m) ?? null })
  }
  return rows
}

/** One row per month across the union of all series' ranges. */
export function compareRows(series: CompareSeries[]): ChartRow[] {
  const withData = series.filter((s) => s.points.length > 0)
  if (withData.length === 0) return []
  const first = withData.map((s) => s.points[0].period).sort()[0]
  const last = withData
    .map((s) => s.points[s.points.length - 1].period)
    .sort()
    .at(-1)!
  const maps = withData.map(
    (s) => new Map(s.points.map((p) => [p.period, p.value])),
  )
  const rows: ChartRow[] = []
  for (let m = first; m <= last; m = nextMonth(m)) {
    const row: ChartRow = { period: m }
    withData.forEach((s, i) => {
      row[s.place_id] = maps[i].get(m) ?? null
    })
    rows.push(row)
  }
  return rows
}
