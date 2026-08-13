import type { Bill } from '../api/types'
import { fmtCurrency, fmtNumber, fmtSignedPct } from './format'

/**
 * Derived metrics over bills.
 *
 * The API sends money and decimals as **strings** to preserve precision, and
 * `consumption`, `unit_price`, `fixed_charges` and `taxes` are all nullable. Parsing
 * happens once here, at the module boundary, so no screen has to remember either fact.
 *
 * A null is not a zero. A bill with no `taxes` is a bill whose tax is unknown, and
 * rendering it as €0.00 would be a claim — and a false one. Every derivation below
 * propagates null rather than substituting zero.
 */

/** A bill with its numbers parsed. Nulls survive; they are information. */
export interface ParsedBill {
  id: string
  periodStart: Date
  periodEnd: Date
  /** Inclusive day count, matching the backend's proration weight. */
  days: number
  consumption: number | null
  unitPrice: number | null
  fixedCharges: number | null
  taxes: number | null
  total: number
  currency: string
  /** How the bill got here — manual entry, the ingest CLI, or Claude extraction. The
   *  recent-bills table shows it, because a figure's provenance changes how much you
   *  should trust it. */
  source: Bill['source']
  providerName: string | null
}

/** Dates arrive as plain `YYYY-MM-DD`. Parsing them as local midnight rather than
 *  letting `new Date('2026-07-01')` mean UTC keeps a period from sliding a day
 *  backwards for anyone west of Greenwich. */
function parseDate(iso: string): Date {
  return new Date(`${iso}T00:00:00`)
}

const MS_PER_DAY = 24 * 60 * 60 * 1000

/** Inclusive, so a 1st-to-31st bill is 31 days and not 30. Rounded because a period
 *  spanning a DST boundary is 23 or 25 hours long, not 24. */
export function inclusiveDays(start: Date, end: Date): number {
  return Math.round((end.getTime() - start.getTime()) / MS_PER_DAY) + 1
}

function num(value: string | null): number | null {
  if (value === null) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function parseBill(bill: Bill): ParsedBill {
  const periodStart = parseDate(bill.period_start)
  const periodEnd = parseDate(bill.period_end)
  return {
    id: bill.id,
    periodStart,
    periodEnd,
    days: inclusiveDays(periodStart, periodEnd),
    consumption: num(bill.consumption),
    unitPrice: num(bill.unit_price),
    fixedCharges: num(bill.fixed_charges),
    taxes: num(bill.taxes),
    total: Number(bill.total_amount),
    currency: bill.currency_code,
    source: bill.source,
    providerName: bill.provider_name,
  }
}

/** `/bills` comes back newest-first; every derivation here reads oldest-first. */
export function parseBills(bills: Bill[]): ParsedBill[] {
  return bills
    .map(parseBill)
    .sort((a, b) => a.periodStart.getTime() - b.periodStart.getTime())
}

/**
 * Effective (all-in) price per kWh — what was actually paid per unit, including fixed
 * charges and tax.
 *
 * This is **not** `bill.unit_price`, which is the contracted tariff. The gap between
 * the two is the entire thesis of the redesign, so the names are kept apart
 * deliberately. Returns null where it cannot be computed rather than Infinity: a bill
 * with no consumption has no meaningful price per unit.
 */
export function effectivePrice(bill: ParsedBill): number | null {
  if (bill.consumption === null || bill.consumption <= 0) return null
  return bill.total / bill.consumption
}

/** Effective price per bill, oldest first, skipping bills it cannot be computed for.
 *  Feeds the sparklines in the rail, the places table and login — per bill rather than
 *  per month because a sparkline is a shape, and one point per bill is the shape the
 *  reader's own statements have. */
export function effectivePriceSeries(bills: ParsedBill[]): number[] {
  return bills.map(effectivePrice).filter((v): v is number => v !== null)
}

/** `consumption × unit_price`. Null if either input is — an energy charge derived from
 *  a missing tariff is a guess, not a figure. */
export function energyCharge(bill: ParsedBill): number | null {
  if (bill.consumption === null || bill.unitPrice === null) return null
  return bill.consumption * bill.unitPrice
}

/** `total ÷ days_in_period`. Normalizes uneven billing periods — a 36-day bill is not
 *  a price increase. */
export function costPerDay(bill: ParsedBill): number {
  return bill.total / bill.days
}

/** Percentage change, or null when there is no honest baseline to measure against. */
export function pctChange(from: number, to: number): number | null {
  if (!Number.isFinite(from) || from === 0) return null
  return ((to - from) / Math.abs(from)) * 100
}

/* ------------------------------------------------------------------ *
 * Monthly bucketing — a port of backend/app/services/series.py
 * ------------------------------------------------------------------ */

/** `ROUND_HALF_UP` at `places`, matching the backend's `Decimal.quantize`. JavaScript's
 *  `toFixed` rounds half-to-even on some values, and `Math.round` is half-up only for
 *  positives, so neither is a substitute. */
export function round(value: number, places: number): number {
  const factor = 10 ** places
  const scaled = value * factor
  /* The epsilon absorbs the representation error that makes 1.005 * 100 come out as
     100.49999999999999, which would otherwise round down. */
  const nudged = scaled + (scaled >= 0 ? 1e-9 : -1e-9)
  return (nudged >= 0 ? Math.floor(nudged + 0.5) : Math.ceil(nudged - 0.5)) / factor
}

export interface MonthBucket {
  /** `YYYY-MM`. */
  period: string
  year: number
  /** 1–12. */
  month: number
  /** Prorated spend, 2dp. Always a number — `total_amount` is required on every bill. */
  cost: number
  /** Prorated consumption, 2dp. **Null**, not zero, when no overlapping bill carried a
   *  consumption figure — the backend drops those months from the metric entirely. */
  kwh: number | null
  /** Consumption-weighted all-in price, 4dp. Null when there is no consumption to
   *  divide by. */
  effective: number | null
  /** Consumption-weighted *contracted* tariff, 4dp. Null when unknown. */
  unitPrice: number | null
  /** Prorated contracted components, 2dp; null when no overlapping bill carried one. */
  energy: number | null
  fixed: number | null
  taxes: number | null
  /** Prorated spend ÷ days in this calendar month, 2dp. */
  perDay: number
  /** Which bills fed this month — a prorated figure needs to be explicable. */
  billIds: string[]
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function periodKey(year: number, month: number): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}`
}

/** Inclusive overlap in days between two closed date ranges; 0 when they miss. */
function overlapDays(aStart: Date, aEnd: Date, bStart: Date, bEnd: Date): number {
  const start = aStart > bStart ? aStart : bStart
  const end = aEnd < bEnd ? aEnd : bEnd
  return end >= start ? inclusiveDays(start, end) : 0
}

interface Accumulator {
  cost: number
  kwh: number
  hasKwh: boolean
  energy: number
  hasEnergy: boolean
  fixed: number
  hasFixed: boolean
  taxes: number
  hasTaxes: boolean
  billIds: string[]
}

/**
 * Prorate every bill across the calendar months it overlaps, weighted by inclusive
 * day count.
 *
 * This has to agree with `backend/app/services/series.py` to the digit. The dashboard
 * derives its months from `/bills` while other views read `/series`, and if the two
 * bucket differently the same month shows two different numbers on one screen.
 *
 * Three details carried over deliberately:
 *
 * - Months with **no overlapping bill are absent**, not zero. Charts should show
 *   honest holes rather than a line dropping to the axis.
 * - `unitPrice` and `effective` are **consumption-weighted averages** over the bucket,
 *   and months with no consumption are dropped from them rather than dividing by zero.
 * - Rounding is applied once, at output: 2dp for money and kWh, 4dp for prices.
 */
export function monthlyBuckets(bills: ParsedBill[]): MonthBucket[] {
  const acc = new Map<string, Accumulator>()

  const bucketFor = (key: string): Accumulator => {
    let existing = acc.get(key)
    if (!existing) {
      existing = {
        cost: 0,
        kwh: 0,
        hasKwh: false,
        energy: 0,
        hasEnergy: false,
        fixed: 0,
        hasFixed: false,
        taxes: 0,
        hasTaxes: false,
        billIds: [],
      }
      acc.set(key, existing)
    }
    return existing
  }

  for (const bill of bills) {
    const energy = energyCharge(bill)
    let year = bill.periodStart.getFullYear()
    let month = bill.periodStart.getMonth() + 1
    const endYear = bill.periodEnd.getFullYear()
    const endMonth = bill.periodEnd.getMonth() + 1

    while (year < endYear || (year === endYear && month <= endMonth)) {
      const monthStart = new Date(year, month - 1, 1)
      const monthEnd = new Date(year, month - 1, daysInMonth(year, month))
      const overlap = overlapDays(
        bill.periodStart,
        bill.periodEnd,
        monthStart,
        monthEnd,
      )
      if (overlap > 0) {
        const share = overlap / bill.days
        const bucket = bucketFor(periodKey(year, month))
        bucket.cost += bill.total * share
        bucket.billIds.push(bill.id)
        if (bill.consumption !== null) {
          bucket.kwh += bill.consumption * share
          bucket.hasKwh = true
        }
        if (energy !== null) {
          bucket.energy += energy * share
          bucket.hasEnergy = true
        }
        if (bill.fixedCharges !== null) {
          bucket.fixed += bill.fixedCharges * share
          bucket.hasFixed = true
        }
        if (bill.taxes !== null) {
          bucket.taxes += bill.taxes * share
          bucket.hasTaxes = true
        }
      }
      if (month === 12) {
        year += 1
        month = 1
      } else {
        month += 1
      }
    }
  }

  return [...acc.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([period, bucket]) => {
      const [year, month] = period.split('-').map(Number)
      const kwh = bucket.hasKwh ? round(bucket.kwh, 2) : null
      /* Weighted averages divide the accumulated totals, not the rounded ones — the
         backend divides Decimals and rounds once, and rounding first would drift. */
      const divisible = bucket.hasKwh && bucket.kwh > 0
      return {
        period,
        year,
        month,
        cost: round(bucket.cost, 2),
        kwh,
        effective: divisible ? round(bucket.cost / bucket.kwh, 4) : null,
        unitPrice:
          divisible && bucket.hasEnergy ? round(bucket.energy / bucket.kwh, 4) : null,
        energy: bucket.hasEnergy ? round(bucket.energy, 2) : null,
        fixed: bucket.hasFixed ? round(bucket.fixed, 2) : null,
        taxes: bucket.hasTaxes ? round(bucket.taxes, 2) : null,
        perDay: round(bucket.cost / daysInMonth(year, month), 2),
        billIds: bucket.billIds,
      }
    })
}

/**
 * Expand to a contiguous month axis, with absent months as null.
 *
 * `monthlyBuckets` omits gaps on purpose; this is the only thing that manufactures
 * nulls, and charts use it so a missing month renders as a break rather than being
 * silently interpolated across.
 */
export function fillMonths(buckets: MonthBucket[]): (MonthBucket | null)[] {
  if (buckets.length === 0) return []
  const out: (MonthBucket | null)[] = []
  const last = buckets[buckets.length - 1]
  const byPeriod = new Map(buckets.map((b) => [b.period, b]))
  let { year, month } = buckets[0]
  for (;;) {
    out.push(byPeriod.get(periodKey(year, month)) ?? null)
    if (year === last.year && month === last.month) break
    if (month === 12) {
      year += 1
      month = 1
    } else {
      month += 1
    }
  }
  return out
}

/* ------------------------------------------------------------------ *
 * Derived metrics
 * ------------------------------------------------------------------ */

/** A change, in the metric's own unit and as a percentage. Null on either side means
 *  there was no counterpart to measure against — which is not the same as no change. */
export interface Delta {
  abs: number | null
  pct: number | null
}

export function delta(
  prior: number | null | undefined,
  current: number | null | undefined,
): Delta {
  if (prior === null || prior === undefined || current === null || current === undefined) {
    return { abs: null, pct: null }
  }
  return { abs: current - prior, pct: pctChange(prior, current) }
}

export interface WindowTotals {
  /** How many months actually contributed. A caller claiming "vs prior 12 mo" needs to
   *  know when it was really eight. */
  months: number
  cost: number
  kwh: number | null
  /** Total cost ÷ total kWh over the whole window — **not** the mean of the monthly
   *  effective prices, which would weight a light month the same as a heavy one. */
  effective: number | null
  perDay: number | null
}

export function windowTotals(buckets: MonthBucket[]): WindowTotals {
  const cost = buckets.reduce((sum, b) => sum + b.cost, 0)
  const withKwh = buckets.filter((b) => b.kwh !== null)
  const kwh = withKwh.length > 0 ? withKwh.reduce((sum, b) => sum + (b.kwh ?? 0), 0) : null
  const days = buckets.reduce((sum, b) => sum + daysInMonth(b.year, b.month), 0)
  return {
    months: buckets.length,
    cost: round(cost, 2),
    kwh: kwh === null ? null : round(kwh, 2),
    effective: kwh !== null && kwh > 0 ? round(cost / kwh, 4) : null,
    perDay: days > 0 ? round(cost / days, 2) : null,
  }
}

export interface TrailingComparison {
  current: WindowTotals
  prior: WindowTotals
  /** True when either window is short of `n` months. */
  partial: boolean
  cost: Delta
  kwh: Delta
  effective: Delta
}

/** The trailing `n` months against the `n` before them. */
export function trailingComparison(buckets: MonthBucket[], n = 12): TrailingComparison {
  const current = buckets.slice(-n)
  const prior = buckets.slice(-2 * n, -n)
  const c = windowTotals(current)
  const p = windowTotals(prior)
  return {
    current: c,
    prior: p,
    partial: c.months < n || p.months < n,
    cost: delta(p.cost, c.cost),
    kwh: delta(p.kwh, c.kwh),
    effective: delta(p.effective, c.effective),
  }
}

/** Same calendar month, prior year. Returns nulls when that month has no counterpart —
 *  never a 0% change, which would read as "measured and unchanged". */
export function yoyDelta(
  buckets: MonthBucket[],
  period: string,
  pick: (bucket: MonthBucket) => number | null,
): Delta {
  const current = buckets.find((b) => b.period === period)
  if (!current) return { abs: null, pct: null }
  const priorPeriod = periodKey(current.year - 1, current.month)
  const prior = buckets.find((b) => b.period === priorPeriod)
  if (!prior) return { abs: null, pct: null }
  return delta(pick(prior), pick(current))
}

export interface Composition {
  energy: number | null
  fixed: number | null
  taxes: number | null
  total: number
  /** Shares of the **summed period total**, not the mean of the monthly shares. */
  shares: { energy: number | null; fixed: number | null; taxes: number | null }
  /** total − (energy + fixed + taxes). Non-zero means adjustments, credits or rounding
   *  on the bill; 3d's arithmetic check and 3f's line items both need it named rather
   *  than silently absorbed. Null when any component is unknown. */
  unexplained: number | null
}

export function composition(
  items: readonly {
    energy: number | null
    fixed: number | null
    taxes: number | null
    total: number
  }[],
): Composition {
  const sum = (pick: (i: (typeof items)[number]) => number | null): number | null => {
    const known = items.filter((i) => pick(i) !== null)
    /* All-or-nothing on purpose: summing only the bills that carry a tax figure and
       presenting it against a total that includes the ones that do not would understate
       the share without saying so. */
    if (known.length !== items.length || items.length === 0) return null
    return round(known.reduce((acc, i) => acc + (pick(i) ?? 0), 0), 2)
  }
  const total = round(items.reduce((acc, i) => acc + i.total, 0), 2)
  const energy = sum((i) => i.energy)
  const fixed = sum((i) => i.fixed)
  const taxes = sum((i) => i.taxes)
  const share = (part: number | null) =>
    part === null || total === 0 ? null : (part / total) * 100
  const parts = [energy, fixed, taxes]
  return {
    energy,
    fixed,
    taxes,
    total,
    shares: { energy: share(energy), fixed: share(fixed), taxes: share(taxes) },
    unexplained: parts.some((p) => p === null)
      ? null
      : round(total - (energy ?? 0) - (fixed ?? 0) - (taxes ?? 0), 2),
  }
}

/** `value ÷ first ÷ 100`. The only honest way to put two currencies on one axis — see
 *  the places table's footer note, which is why this exists at all. */
export function indexToFirst(values: readonly (number | null)[]): (number | null)[] {
  const base = values.find((v) => v !== null && v !== 0)
  if (base === undefined || base === null) return values.map(() => null)
  return values.map((v) => (v === null ? null : (v / base) * 100))
}

export interface ContractRateChange {
  first: number | null
  latest: number | null
  abs: number | null
  pct: number | null
}

/** First to latest **contracted** tariff. Seasonality-free, unlike any comparison of
 *  effective prices — which is the whole reason 2a's scatter read-out quotes it. */
export function contractRateChange(bills: ParsedBill[]): ContractRateChange {
  const priced = bills.filter((b) => b.unitPrice !== null)
  if (priced.length === 0) return { first: null, latest: null, abs: null, pct: null }
  const first = priced[0].unitPrice as number
  const latest = priced[priced.length - 1].unitPrice as number
  return { first, latest, abs: latest - first, pct: pctChange(first, latest) }
}

/** Running `Σ (eff_i − eff_baseline) × kwh_i`, baseline = the first month with a price.
 *  Runs negative through the first winter, which is the point — chart 3 explains why. */
export function cumulativeExcess(
  buckets: MonthBucket[],
): { period: string; value: number }[] {
  const baseline = buckets.find((b) => b.effective !== null)?.effective
  if (baseline === undefined || baseline === null) return []
  let running = 0
  const out: { period: string; value: number }[] = []
  for (const bucket of buckets) {
    if (bucket.effective !== null && bucket.kwh !== null) {
      running += (bucket.effective - baseline) * bucket.kwh
    }
    out.push({ period: bucket.period, value: round(running, 2) })
  }
  return out
}

export interface ForecastPoint {
  period: string
  value: number
  /** Always true. Callers must render forecasts dashed and tinted, never as a solid
   *  series — the estimate is coarse by design and should not read as a measurement. */
  estimated: true
}

/**
 * Latest effective price, carried forward on the trailing 3-month price trend, applied
 * to the same calendar month's consumption a year ago.
 *
 * Coarse by design. It exists to say "on this trajectory, roughly this", and the design
 * requires it to look visually distinct for exactly that reason.
 */
export function forecast(buckets: MonthBucket[], count = 3): ForecastPoint[] {
  const priced = buckets.filter((b) => b.effective !== null)
  if (priced.length < 2) return []
  const latest = priced[priced.length - 1]
  const trendWindow = priced.slice(-4)
  const steps = trendWindow.length - 1
  const drift =
    steps > 0
      ? ((trendWindow[trendWindow.length - 1].effective as number) -
          (trendWindow[0].effective as number)) /
        steps
      : 0

  const out: ForecastPoint[] = []
  let { year, month } = latest
  let price = latest.effective as number
  for (let i = 0; i < count; i++) {
    if (month === 12) {
      year += 1
      month = 1
    } else {
      month += 1
    }
    price += drift
    const lastYear = buckets.find((b) => b.period === periodKey(year - 1, month))
    if (!lastYear || lastYear.kwh === null) break
    out.push({ period: periodKey(year, month), value: round(price * lastYear.kwh, 2), estimated: true })
  }
  return out
}

/* ------------------------------------------------------------------ *
 * Headline selection
 * ------------------------------------------------------------------ */

export type HeadlineKind = 'insufficient' | 'savings' | 'price' | 'consumption' | 'steady'

export interface Headline {
  kind: HeadlineKind
  /** 26px/600 — the finding. */
  finding: string
  /** 13px --ink2 — the arithmetic behind it. */
  explanation: string
}

/**
 * Which story the last two years tell, and the copy for it.
 *
 * The handoff's three branches overlap — spend down 13.9% on flat consumption is both
 * "spend fell" and "a price story" — so the precedence is fixed here rather than left
 * to the screen, and it is tested:
 *
 *   1. not enough history to compare at all
 *   2. spend fell            → savings
 *   3. spend moved, use did not → price
 *   4. both moved together   → consumption
 *   5. neither moved         → steady
 */
export function headline(
  comparison: TrailingComparison,
  context: { currency: string },
): Headline {
  const { currency } = context
  const { current, prior, cost, kwh } = comparison
  const spendPct = cost.pct
  const usePct = kwh.pct

  if (current.months < 2 || prior.months === 0 || spendPct === null) {
    return {
      kind: 'insufficient',
      finding: 'Not enough history yet.',
      explanation:
        'Once a year of bills is in, this compares the last 12 months against the 12 before and says what changed.',
    }
  }

  const spendMoney = fmtCurrency(Math.abs(cost.abs ?? 0), currency, 0)
  const useNow = fmtNumber(current.kwh, 0)
  const window = comparison.partial
    ? `Last ${current.months} months against the ${prior.months} before`
    : 'Last 12 months against the 12 before'

  if (spendPct <= -5) {
    return {
      kind: 'savings',
      finding: `You spent ${fmtSignedPct(spendPct).replace('−', '')} less.`,
      explanation: `${window}: ${spendMoney} less paid, on ${useNow} kWh.`,
    }
  }

  if (Math.abs(spendPct) > 5 && usePct !== null && Math.abs(usePct) < 3) {
    return {
      kind: 'price',
      finding: `Same energy, ${fmtSignedPct(spendPct).replace('+', '')} more money.`,
      explanation: `${window}: ${useNow} kWh both years, ${spendMoney} more paid. The whole difference is unit price.`,
    }
  }

  if (
    usePct !== null &&
    Math.abs(usePct) >= 3 &&
    Math.sign(usePct) === Math.sign(spendPct)
  ) {
    return {
      kind: 'consumption',
      finding:
        usePct > 0 ? 'You used more energy.' : 'You used less energy.',
      explanation: `${window}: consumption ${fmtSignedPct(usePct)}, spend ${fmtSignedPct(spendPct)}. The bill is following the meter.`,
    }
  }

  return {
    kind: 'steady',
    finding: 'Little has changed.',
    explanation: `${window}: spend ${fmtSignedPct(spendPct)}${usePct === null ? '' : `, consumption ${fmtSignedPct(usePct)}`}.`,
  }
}

/** The shape of a place's tariff, derived from its own bills. */
export interface TariffShape {
  /** Typical standing charge per bill. */
  fixedPerBill: number | null
  /** Typical tax rate, as a fraction: 0.19 for 19%. */
  taxRate: number | null
  firstUnitPrice: number | null
  latestUnitPrice: number | null
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

/**
 * The standing charge and tax rate this place is actually billed at.
 *
 * 2a's scatter needs both to draw its model curves. The handoff quotes 5.90 and 1.19,
 * but those are the *demo* tariff's — hardcoding them would draw a curve for someone
 * else's contract on every real account. The median rather than the mean, so one
 * corrected bill or an unusual month does not move the curve.
 */
export function tariffShape(bills: ParsedBill[]): TariffShape {
  const rate = contractRateChange(bills)
  const taxRates: number[] = []
  for (const bill of bills) {
    const energy = energyCharge(bill)
    if (bill.taxes === null || energy === null || bill.fixedCharges === null) continue
    const base = energy + bill.fixedCharges
    if (base > 0) taxRates.push(bill.taxes / base)
  }
  return {
    fixedPerBill: median(
      bills.map((b) => b.fixedCharges).filter((v): v is number => v !== null),
    ),
    taxRate: median(taxRates),
    firstUnitPrice: rate.first,
    latestUnitPrice: rate.latest,
  }
}

/** One cell of 3f's 2×2 comparison grid. */
export interface BillComparison {
  /** What it is measured against — a period, or a label like "12-month average". Null
   *  when no counterpart exists. */
  against: string | null
  /** The counterpart's value, so the reader can see what the percentage is *of*. */
  againstValue: number | null
  delta: Delta
}

export interface BillComparisons {
  previousMonth: BillComparison
  sameMonthLastYear: BillComparison
  twelveMonthAverage: BillComparison
  cheapestMonth: BillComparison
}

const NO_COMPARISON: BillComparison = {
  against: null,
  againstValue: null,
  delta: { abs: null, pct: null },
}

/**
 * Where one month sits against the run of everything else.
 *
 * Every cell distinguishes **"no counterpart"** from **"no change"**. The first bill in
 * an account has no previous month and no year-ago twin, and rendering either as 0%
 * would be a claim the data does not support.
 *
 * "Cheapest" is by **effective price**, not by total: a cheap month with low usage is
 * not a cheap rate, and confusing the two is the misreading this whole redesign exists
 * to correct.
 */
export function billComparisons(
  buckets: MonthBucket[],
  period: string,
): BillComparisons {
  const index = buckets.findIndex((b) => b.period === period)
  if (index < 0) {
    return {
      previousMonth: NO_COMPARISON,
      sameMonthLastYear: NO_COMPARISON,
      twelveMonthAverage: NO_COMPARISON,
      cheapestMonth: NO_COMPARISON,
    }
  }
  const current = buckets[index]
  const value = current.effective

  const against = (other: MonthBucket | undefined, label?: string): BillComparison =>
    !other || other.effective === null || value === null
      ? NO_COMPARISON
      : {
          against: label ?? other.period,
          againstValue: other.effective,
          delta: delta(other.effective, value),
        }

  const previous = index > 0 ? buckets[index - 1] : undefined
  const yearAgo = buckets.find((b) => b.period === periodKey(current.year - 1, current.month))

  /* The twelve months before this one, not the twelve around it — an average that
     includes the month being judged is partly a comparison with itself. */
  const window = buckets.slice(Math.max(0, index - 12), index).filter((b) => b.effective !== null)
  const averageValue =
    window.length === 0
      ? null
      : window.reduce((sum, b) => sum + (b.effective ?? 0), 0) / window.length

  const priced = buckets.filter((b) => b.effective !== null && b.period !== period)
  const cheapest = priced.reduce<MonthBucket | undefined>(
    (best, b) => (!best || (b.effective ?? 0) < (best.effective ?? 0) ? b : best),
    undefined,
  )

  return {
    previousMonth: against(previous),
    sameMonthLastYear: against(yearAgo),
    twelveMonthAverage:
      averageValue === null || value === null
        ? NO_COMPARISON
        : {
            against: `${window.length}-month average`,
            againstValue: round(averageValue, 4),
            delta: delta(averageValue, value),
          },
    cheapestMonth: against(cheapest),
  }
}
