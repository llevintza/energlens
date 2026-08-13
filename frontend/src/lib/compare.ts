import type { ChartTokens } from '../components/charts/chartTheme'
import { alpha } from '../components/charts/chartTheme'
import type { Domain } from './axis'
import { paddedDomain, symmetricDomain, zeroBasedDomain } from './axis'
import { fmtCurrency, fmtNumber } from './format'
import type { MonthBucket } from './metrics'
import { pctChange } from './metrics'

/**
 * The compare engine: eight metrics against four ways of slicing time.
 *
 * Written as two descriptor tables rather than 32 branches, so a mode is implemented
 * once and works for every metric — which is also what makes "switching mode re-renders
 * all eight tile miniatures" a `map` instead of a second implementation.
 *
 * `build()` returns **data and colours, never pixels**. That is what lets the 119×40
 * miniature and the full-size chart share one code path.
 */

export type MetricId =
  | 'total'
  | 'kwh'
  | 'eff'
  | 'price'
  | 'energy'
  | 'taxes'
  | 'perDay'
  | 'mix'

export type ModeId = 'yoy' | 'years' | 'mom' | 'same'

export interface FormatContext {
  currency: string
}

export interface MetricDescriptor {
  id: MetricId
  /** Dropdown and page title. */
  label: string
  /** Tile eyebrow, 10px mono. */
  short: string
  /** Null means the metric has no value that month — charts must gap, not zero. */
  select: (bucket: MonthBucket) => number | null
  /** Zero-based where the size of the quantity is the point; padded for prices, where
   *  a zero baseline flattens the movement that *is* the point. */
  axis: 'zero' | 'padded'
  /** Tables and tooltips. */
  full: (value: number, ctx: FormatContext) => string
  /** Tiles and bar labels — 0 decimals on money, per the handoff. */
  big: (value: number, ctx: FormatContext) => string
  /** Axis ticks — 2 decimals on prices, not 4. */
  tick: (value: number, ctx: FormatContext) => string
  /** `mix` is a view, not a metric: the comparison modes do not apply to it. */
  view?: 'mix'
}

const money2 = (v: number, c: FormatContext) => fmtCurrency(v, c.currency, 2)
const money0 = (v: number, c: FormatContext) => fmtCurrency(v, c.currency, 0)
const price4 = (v: number, c: FormatContext) => fmtCurrency(v, c.currency, 4)
const price2 = (v: number, c: FormatContext) => fmtCurrency(v, c.currency, 2)

export const METRICS: readonly MetricDescriptor[] = [
  {
    id: 'total',
    label: 'Total cost',
    short: 'COST',
    select: (b) => b.cost,
    axis: 'zero',
    full: money2,
    big: money0,
    tick: money0,
  },
  {
    id: 'kwh',
    label: 'Consumption',
    short: 'kWh',
    select: (b) => b.kwh,
    axis: 'zero',
    full: (v) => `${fmtNumber(v, 1)} kWh`,
    big: (v) => fmtNumber(v, 0),
    tick: (v) => fmtNumber(v, 0),
  },
  {
    id: 'eff',
    label: 'All-in price',
    short: '€/kWh',
    select: (b) => b.effective,
    axis: 'padded',
    full: price4,
    big: price4,
    tick: price2,
  },
  {
    id: 'price',
    label: 'Contract price',
    short: 'UNIT',
    select: (b) => b.unitPrice,
    axis: 'padded',
    full: price4,
    big: price4,
    tick: price2,
  },
  {
    id: 'energy',
    label: 'Energy charge',
    short: 'ENERGY',
    select: (b) => b.energy,
    axis: 'zero',
    full: money2,
    big: money0,
    tick: money0,
  },
  {
    id: 'taxes',
    label: 'Taxes',
    short: 'TAX',
    select: (b) => b.taxes,
    axis: 'zero',
    full: money2,
    big: money0,
    tick: money0,
  },
  {
    id: 'perDay',
    label: 'Cost per day',
    short: '€/DAY',
    select: (b) => b.perDay,
    axis: 'zero',
    full: money2,
    big: money2,
    tick: (v, c) => fmtCurrency(v, c.currency, 1),
  },
  {
    id: 'mix',
    label: 'Bill composition',
    short: 'MIX',
    select: (b) => b.cost,
    axis: 'zero',
    full: money2,
    big: money2,
    tick: price2,
    view: 'mix',
  },
]

export const METRIC_BY_ID = Object.fromEntries(
  METRICS.map((m) => [m.id, m]),
) as Record<MetricId, MetricDescriptor>

export interface SeriesSpec {
  key: string
  label: string
  color: string
  strokeWidth: number
  dashed?: boolean
  dotRadius?: number | false
}

export interface CompareData {
  /** Which composition the screen mounts. Two components cover all four modes. */
  chart: 'line' | 'bar'
  /** `number[]` is here for the year-over-year band, which Recharts draws from a
   *  [lower, upper] tuple on a single key. */
  rows: Record<string, string | number | number[] | null>[]
  xKey: string
  series: SeriesSpec[]
  domain: Domain
  /** yoy only — the filled band between this year and last. */
  band?: { upperKey: string; lowerKey: string; fill: string }
  /** mom only — a centred zero line. */
  zeroLine?: boolean
  /** same only — the value printed above each bar. */
  valueLabels?: boolean
  /** Per-bar colours, for the modes where a bar's colour carries meaning. */
  cellColors?: string[]
  legend: { label: string; color: string }[]
  note: string
}

export interface CompareInput {
  /** Already range-sliced by the caller: 12M is a slice, not a refetch. */
  buckets: MonthBucket[]
  metric: MetricDescriptor
  tokens: ChartTokens
  format: FormatContext
  /** `years` mode — which years the chips have enabled. */
  years?: number[]
  /** `same` mode — 1–12. */
  month?: number
  /** Miniatures drop axes and labels; the pixels stay in the component. */
  density?: 'full' | 'mini'
}

const MONTH_LABELS = [
  'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
  'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
]

function domainFor(
  metric: MetricDescriptor,
  values: (number | null)[],
  ticks: number,
): Domain {
  return metric.axis === 'zero'
    ? zeroBasedDomain(values, ticks)
    : paddedDomain(values, ticks)
}

export interface ModeDescriptor {
  id: ModeId
  label: string
  hint: string
  build: (input: CompareInput) => CompareData
}

/** Trailing 12 against the 12 before, aligned by position rather than by date — the
 *  comparison a reader means when they say "this year against last". */
function buildYoy(input: CompareInput): CompareData {
  const { buckets, metric, tokens, density } = input
  const current = buckets.slice(-12)
  const prior = buckets.slice(-24, -12)
  const ticks = density === 'mini' ? 2 : 4

  const rows = current.map((bucket, i) => ({
    x: MONTH_LABELS[bucket.month - 1],
    current: metric.select(bucket),
    prior: prior[i] ? metric.select(prior[i]) : null,
  }))

  const values = rows.flatMap((r) => [r.current, r.prior])
  return {
    chart: 'line',
    rows,
    xKey: 'x',
    domain: domainFor(metric, values, ticks),
    band: { upperKey: 'current', lowerKey: 'prior', fill: alpha(tokens.accRgb, 0.11) },
    series: [
      {
        key: 'prior',
        label: 'Previous 12 months',
        color: tokens.ink4,
        strokeWidth: density === 'mini' ? 1.2 : 2,
        dotRadius: false,
      },
      {
        key: 'current',
        label: 'Last 12 months',
        color: tokens.acc,
        strokeWidth: density === 'mini' ? 1.5 : 2.4,
        dotRadius: density === 'mini' ? false : 2.8,
      },
    ],
    legend: [
      { label: 'Last 12 months', color: tokens.acc },
      { label: 'The 12 before', color: tokens.ink4 },
    ],
    note: 'The shaded area is the gap between the two years.',
  }
}

/** Every selected year on a shared Jan–Dec axis. */
function buildYears(input: CompareInput): CompareData {
  const { buckets, metric, tokens, years, density } = input
  const available = [...new Set(buckets.map((b) => b.year))].sort()
  const selected = (years && years.length > 0 ? years : available).filter((y) =>
    available.includes(y),
  )

  const palette = [tokens.ink4, tokens.amber, tokens.acc]
  const colorFor = (year: number) => {
    const rank = selected.indexOf(year)
    /* Newest year takes the accent, regardless of how many are selected. */
    return palette[Math.max(0, palette.length - selected.length + rank)] ?? tokens.ink4
  }

  const rows = MONTH_LABELS.map((label, i) => {
    const row: Record<string, string | number | number[] | null> = { x: label }
    for (const year of selected) {
      const bucket = buckets.find((b) => b.year === year && b.month === i + 1)
      /* Partial years stop where the data stops. A missing month is null, and
         connectNulls stays false downstream, so nothing is interpolated across. */
      row[`y${year}`] = bucket ? metric.select(bucket) : null
    }
    return row
  })

  const counts = new Map(
    selected.map((year) => [year, buckets.filter((b) => b.year === year).length]),
  )

  const values = rows.flatMap((r) =>
    selected.map((y) => r[`y${y}`] as number | null),
  )

  return {
    chart: 'line',
    rows,
    xKey: 'x',
    domain: domainFor(metric, values, density === 'mini' ? 2 : 4),
    series: selected.map((year) => ({
      key: `y${year}`,
      label: String(year),
      color: colorFor(year),
      strokeWidth: density === 'mini' ? 1.3 : year === Math.max(...selected) ? 2.4 : 2,
      dotRadius: false,
    })),
    legend: selected.map((year) => ({
      label: `${year}${(counts.get(year) ?? 0) < 12 ? ` (${counts.get(year)} mo)` : ''}`,
      color: colorFor(year),
    })),
    note: 'Partial years stop where the data does — no interpolation.',
  }
}

/** Percent change from each month to the next, as diverging bars. */
function buildMom(input: CompareInput): CompareData {
  const { buckets, metric, tokens, density } = input
  const rows: Record<string, string | number | number[] | null>[] = []
  for (let i = 1; i < buckets.length; i++) {
    const previous = metric.select(buckets[i - 1])
    const current = metric.select(buckets[i])
    rows.push({
      x: MONTH_LABELS[buckets[i].month - 1],
      change:
        previous === null || current === null ? null : pctChange(previous, current),
    })
  }
  const values = rows.map((r) => r.change as number | null)
  return {
    chart: 'bar',
    rows,
    xKey: 'x',
    domain: symmetricDomain(values, density === 'mini' ? 2 : 4),
    zeroLine: true,
    /* Colour carries the direction, so the reader does not have to read the sign. */
    cellColors: values.map((v) => ((v ?? 0) >= 0 ? tokens.up : tokens.down)),
    series: [{ key: 'change', label: 'Change', color: tokens.acc, strokeWidth: 0 }],
    legend: [
      { label: 'Increase', color: tokens.up },
      { label: 'Decrease', color: tokens.down },
    ],
    note: 'Percent change from the month before.',
  }
}

/** One month, isolated across every year on record. */
function buildSame(input: CompareInput): CompareData {
  const { buckets, metric, tokens, month = 1, density } = input
  const matching = buckets.filter((b) => b.month === month)
  const rows = matching.map((bucket) => ({
    x: String(bucket.year),
    value: metric.select(bucket),
  }))
  const latest = matching.length > 0 ? Math.max(...matching.map((b) => b.year)) : null
  return {
    chart: 'bar',
    rows,
    xKey: 'x',
    domain: domainFor(metric, rows.map((r) => r.value), density === 'mini' ? 2 : 4),
    valueLabels: density !== 'mini',
    cellColors: matching.map((b) => (b.year === latest ? tokens.acc : tokens.acc2)),
    series: [{ key: 'value', label: 'Value', color: tokens.acc, strokeWidth: 0 }],
    legend: [],
    note: `${MONTH_LABELS[month - 1]} in each year on record.`,
  }
}

export const MODES: readonly ModeDescriptor[] = [
  {
    id: 'yoy',
    label: 'Year over year',
    hint: 'trailing 12 months against the 12 before, aligned by month',
    build: buildYoy,
  },
  {
    id: 'years',
    label: 'Years overlaid',
    hint: 'every year on a shared Jan–Dec axis',
    build: buildYears,
  },
  {
    id: 'mom',
    label: 'Month over month',
    hint: 'change from each month to the next',
    build: buildMom,
  },
  {
    id: 'same',
    label: 'Same month, each year',
    hint: 'one month isolated across every year on record',
    build: buildSame,
  },
]

export const MODE_BY_ID = Object.fromEntries(
  MODES.map((m) => [m.id, m]),
) as Record<ModeId, ModeDescriptor>

/* ------------------------------------------------------------------ *
 * mix — a view, not a metric
 * ------------------------------------------------------------------ */

export interface MixRow {
  x: string
  /** Contracted tariff per kWh. */
  energy: number | null
  /** Standing charge spread over the kWh it was charged against. */
  standing: number | null
  /** Tax on both of the above. */
  tax: number | null
}

/**
 * The €/kWh decomposition — every component divided by the kWh it was spread over.
 *
 * This earns its place on the page: the standing-charge band visibly swells in light
 * months, which is why cutting consumption *raises* the headline price per unit. That
 * is counter-intuitive enough that showing it beats asserting it.
 */
export function buildMix(buckets: MonthBucket[]): {
  rows: MixRow[]
  domain: Domain
  note: string
} {
  const rows: MixRow[] = buckets.map((bucket) => {
    const kwh = bucket.kwh
    if (kwh === null || kwh <= 0) {
      return { x: MONTH_LABELS[bucket.month - 1], energy: null, standing: null, tax: null }
    }
    const energy = bucket.unitPrice
    const standing = bucket.fixed === null ? null : bucket.fixed / kwh
    const tax = bucket.taxes === null ? null : bucket.taxes / kwh
    return { x: MONTH_LABELS[bucket.month - 1], energy, standing, tax }
  })

  const totals = rows.map((r) =>
    r.energy === null ? null : (r.energy ?? 0) + (r.standing ?? 0) + (r.tax ?? 0),
  )

  return {
    rows,
    domain: zeroBasedDomain(totals, 4),
    note: 'Every component divided by the kWh it was spread over. The standing-charge band swells in light months, which is why cutting consumption raises your headline price per unit.',
  }
}

/** CSV of whatever is currently on screen. */
export function toCsv(
  data: CompareData,
  metric: MetricDescriptor,
  mode: ModeDescriptor,
): string {
  const columns = data.series.map((s) => s.key)
  const header = [mode.label, ...data.series.map((s) => s.label)]
  const lines = [
    `# ${metric.label} — ${mode.label}`,
    header.map((h) => `"${h.replace(/"/g, '""')}"`).join(','),
    ...data.rows.map((row) =>
      [row[data.xKey], ...columns.map((c) => row[c])]
        .map((v) => (v === null || v === undefined ? '' : String(v)))
        .join(','),
    ),
  ]
  return lines.join('\n')
}
