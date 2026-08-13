/* Decimals are fixed, not maximums: the handoff asks for €0.2886 in a column of
   effective prices, and a "maximum" would render an exact €0.2500 as €0.25 and break
   the alignment tabular-nums exists to hold. Callers pass the count the handoff
   specifies — 0 for KPI totals and headlines, 2 in tables and bill figures, 4 for
   effective price. */
export function fmtCurrency(
  value: number | string | null | undefined,
  currency: string,
  fractionDigits = 2,
): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return '—'
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(n)
}

export function fmtNumber(
  value: number | string | null | undefined,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return '—'
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(n)
}

/**
 * A signed percentage, one decimal, with a **true minus sign** (U+2212) rather than a
 * hyphen — the handoff calls this out because a hyphen renders visibly shorter and
 * higher than the plus it is meant to pair with, so a column of deltas looks ragged.
 */
export function fmtSignedPct(
  value: number | null | undefined,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const magnitude = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(Math.abs(value))
  /* Signed on both sides: "+0.0%" and "−0.0%" both read as measured-and-flat, where a
     bare "0.0%" reads as not-measured. */
  return `${value < 0 ? '−' : '+'}${magnitude}%`
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

const MONTHS_SHORT = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

/**
 * `"2026-03"` → `"MAR"`, and `"2026-01"` → `"JAN '26"`.
 *
 * Uppercase mono for axis ticks. The year appears only in January, which is enough to
 * anchor a 24-month axis without repeating "2026" twelve times — and it is where the
 * reader is already looking for a boundary.
 */
export function fmtMonthTickMono(period: string): string {
  const [year, month] = period.split('-')
  const index = Number(month) - 1
  const name = MONTHS_SHORT[index] ?? period
  return index === 0 ? `${name} '${year.slice(2)}` : name
}
