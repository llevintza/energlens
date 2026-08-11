export function fmtCurrency(
  value: number | string | null | undefined,
  currency: string,
  maximumFractionDigits = 2,
): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return '—'
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits,
  }).format(n)
}

export function fmtNumber(
  value: number | string | null | undefined,
  maximumFractionDigits = 1,
): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(n)
}

/** "2026-03" → "Mar 2026" */
export function fmtMonth(period: string): string {
  const [year, month] = period.split('-').map(Number)
  if (!year || !month) return period
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  })
}

/** "2026-03" → "Mar" / "Jan 26" (short axis tick, year only on January) */
export function fmtMonthTick(period: string): string {
  const [year, month] = period.split('-').map(Number)
  if (!year || !month) return period
  const d = new Date(year, month - 1, 1)
  if (month === 1) {
    return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
  }
  return d.toLocaleDateString(undefined, { month: 'short' })
}

/** "2026-03-31" → "31 Mar 2026" */
export function fmtDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** Period label for either granularity ("2026-03" or "2026-03-31"). */
export function fmtPeriod(period: string): string {
  return period.length === 7 ? fmtMonth(period) : fmtDate(period)
}

export function fmtPeriodTick(period: string): string {
  if (period.length === 7) return fmtMonthTick(period)
  const d = new Date(`${period}T00:00:00`)
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
