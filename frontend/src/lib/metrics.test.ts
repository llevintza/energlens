import { describe, expect, it } from 'vitest'

import type { Bill } from '../api/types'
import { MAIN_RESIDENCE, SECOND_HOME, seedBillsNewestFirst } from './fixtures'
import {
  composition,
  contractRateChange,
  cumulativeExcess,
  costPerDay,
  effectivePrice,
  fillMonths,
  headline,
  indexToFirst,
  monthlyBuckets,
  parseBills,
  trailingComparison,
  windowTotals,
  yoyDelta,
} from './metrics'

const main = () => parseBills(seedBillsNewestFirst(MAIN_RESIDENCE))
const second = () => parseBills(seedBillsNewestFirst(SECOND_HOME))

/** A bill with only the fields the API guarantees. */
function bill(over: Partial<Bill> & Pick<Bill, 'period_start' | 'period_end' | 'total_amount'>): Bill {
  return {
    id: 'b',
    place_id: 'p',
    utility_type: 'electricity',
    consumption: null,
    unit: 'kWh',
    unit_price: null,
    fixed_charges: null,
    taxes: null,
    currency_code: 'EUR',
    provider_name: null,
    raw_file_ref: null,
    source: 'manual',
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  } as Bill
}

describe('parsing', () => {
  it('sorts oldest first, whatever order the API returned', () => {
    const bills = main()
    expect(bills[0].periodStart.getFullYear()).toBe(2024)
    expect(bills[bills.length - 1].periodEnd.getFullYear()).toBe(2026)
  })

  it('counts days inclusively, so a full month is its own length', () => {
    const [b] = parseBills([
      bill({ period_start: '2026-07-01', period_end: '2026-07-31', total_amount: '10' }),
    ])
    expect(b.days).toBe(31)
  })

  it('keeps a missing figure missing rather than calling it zero', () => {
    const [b] = parseBills([
      bill({ period_start: '2026-07-01', period_end: '2026-07-31', total_amount: '46.17' }),
    ])
    expect(b.consumption).toBeNull()
    expect(b.taxes).toBeNull()
    // The distinction the whole module turns on: unknown tax is not €0.00 of tax.
    expect(b.taxes).not.toBe(0)
  })

  it('yields no effective price for a bill with no consumption, not Infinity', () => {
    const [b] = parseBills([
      bill({ period_start: '2026-07-01', period_end: '2026-07-31', total_amount: '46.17' }),
    ])
    expect(effectivePrice(b)).toBeNull()
  })

  it('yields no effective price for zero consumption either', () => {
    const [b] = parseBills([
      bill({
        period_start: '2026-07-01',
        period_end: '2026-07-31',
        total_amount: '46.17',
        consumption: '0',
      }),
    ])
    expect(effectivePrice(b)).toBeNull()
  })
})

describe('the handoff figures', () => {
  // If any of these disagree with the implementation, the implementation is wrong:
  // they are quoted in docs/design/README.md and drawn into the prototypes.

  it('holds consumption flat at 3,060 kWh across both 12-month windows', () => {
    const cmp = trailingComparison(monthlyBuckets(main()))
    expect(cmp.current.kwh).toBeCloseTo(3060, 1)
    expect(cmp.prior.kwh).toBeCloseTo(3060, 1)
    expect(cmp.kwh.pct).toBeCloseTo(0, 6)
  })

  it('shows spend rising €691 → €787, +13.9%', () => {
    const cmp = trailingComparison(monthlyBuckets(main()))
    expect(cmp.prior.cost).toBeCloseTo(691.24, 2)
    expect(cmp.current.cost).toBeCloseTo(787.37, 2)
    expect(cmp.cost.pct).toBeCloseTo(13.9, 1)
    expect(Math.round(cmp.cost.abs ?? 0)).toBe(96)
  })

  it('shows effective price rising €0.2251 → €0.2886, +28.2%', () => {
    // Measured first month against latest — which is what the handoff's
    // "ALL-IN €/kWh … since Aug 2024" KPI quotes, and what the rail sparkline's delta
    // chip shows. It is NOT the ratio of the two trailing-12 averages: those are
    // €0.2259 → €0.2573 (asserted below), because averaging over a window pulls both
    // ends toward the middle of the seasonal cycle.
    const buckets = monthlyBuckets(main())
    const first = buckets[0].effective as number
    const latest = buckets[buckets.length - 1].effective as number
    expect(first).toBeCloseTo(0.2251, 4)
    expect(latest).toBeCloseTo(0.2886, 4)
    expect(((latest - first) / first) * 100).toBeCloseTo(28.2, 1)
  })

  it('averages the two windows to €0.2259 and €0.2573, which is a different question', () => {
    // Kept explicit so nobody "fixes" the window average into the KPI's figure. Both
    // are right; they answer "what did a kWh cost me over the year" and "what does a
    // kWh cost me now against when I started".
    const cmp = trailingComparison(monthlyBuckets(main()))
    expect(cmp.prior.effective).toBeCloseTo(0.2259, 4)
    expect(cmp.current.effective).toBeCloseTo(0.2573, 4)
  })

  it('puts the last bill at €46.17 and €0.2886 all-in', () => {
    const bills = main()
    const last = bills[bills.length - 1]
    expect(last.total).toBeCloseTo(46.17, 2)
    expect(effectivePrice(last)).toBeCloseTo(0.2886, 4)
    // July is the seasonal trough: 160 kWh, 31 days.
    expect(last.consumption).toBeCloseTo(160, 1)
    expect(costPerDay(last)).toBeCloseTo(1.49, 2)
  })

  it('puts the contract rate change at +€0.0506, €0.1550 → €0.2056', () => {
    const change = contractRateChange(main())
    expect(change.first).toBeCloseTo(0.155, 4)
    expect(change.latest).toBeCloseTo(0.2056, 4)
    expect(change.abs).toBeCloseTo(0.0506, 4)
  })

  it('ends cumulative excess near €101, averaging about €4.20 a month', () => {
    const excess = cumulativeExcess(monthlyBuckets(main()))
    const final = excess[excess.length - 1].value
    expect(final).toBeGreaterThan(95)
    expect(final).toBeLessThan(107)
    expect(final / excess.length).toBeCloseTo(4.2, 0)
  })

  it('runs negative through the first winter, which chart 3 exists to explain', () => {
    const excess = cumulativeExcess(monthlyBuckets(main()))
    expect(Math.min(...excess.map((e) => e.value))).toBeLessThan(0)
  })
})

describe('monthly bucketing', () => {
  it('gives calendar-month bills one bucket each, unprorated', () => {
    const buckets = monthlyBuckets(main())
    expect(buckets).toHaveLength(24)
    expect(buckets[0].period).toBe('2024-08')
    expect(buckets[23].period).toBe('2026-07')
    expect(buckets[23].cost).toBeCloseTo(46.17, 2)
  })

  it('spreads a 15th-to-14th bill across the two months it touches', () => {
    // The second seeded place bills on this cycle precisely so this path is exercised.
    const buckets = monthlyBuckets(second())
    expect(buckets.length).toBeGreaterThan(24)
    expect(buckets[0].billIds).toHaveLength(1)
    // Every interior month is fed by exactly two bills.
    expect(buckets[5].billIds).toHaveLength(2)
  })

  it('weights proration by inclusive day count', () => {
    // 1 Jan – 10 Feb is 41 days: 31 in January, 10 in February.
    const bills = parseBills([
      bill({
        period_start: '2026-01-01',
        period_end: '2026-02-10',
        total_amount: '410',
        consumption: '410',
      }),
    ])
    const [jan, feb] = monthlyBuckets(bills)
    expect(jan.cost).toBeCloseTo(410 * (31 / 41), 2)
    expect(feb.cost).toBeCloseTo(410 * (10 / 41), 2)
    expect(jan.cost + feb.cost).toBeCloseTo(410, 2)
  })

  it('spans three months when a bill is long enough to', () => {
    const bills = parseBills([
      bill({ period_start: '2026-01-20', period_end: '2026-03-05', total_amount: '100' }),
    ])
    expect(monthlyBuckets(bills).map((b) => b.period)).toEqual([
      '2026-01',
      '2026-02',
      '2026-03',
    ])
  })

  it('omits a month with no bill rather than showing it as zero', () => {
    const bills = parseBills([
      bill({ period_start: '2026-01-01', period_end: '2026-01-31', total_amount: '50' }),
      bill({ period_start: '2026-03-01', period_end: '2026-03-31', total_amount: '60' }),
    ])
    const buckets = monthlyBuckets(bills)
    expect(buckets.map((b) => b.period)).toEqual(['2026-01', '2026-03'])
    // A chart that wants a continuous axis asks for the hole explicitly.
    expect(fillMonths(buckets).map((b) => b?.period ?? null)).toEqual([
      '2026-01',
      null,
      '2026-03',
    ])
  })

  it('leaves kWh null for a month whose bills carried no consumption', () => {
    const bills = parseBills([
      bill({ period_start: '2026-01-01', period_end: '2026-01-31', total_amount: '50' }),
    ])
    const [jan] = monthlyBuckets(bills)
    expect(jan.cost).toBe(50)
    expect(jan.kwh).toBeNull()
    expect(jan.effective).toBeNull()
  })

  it('weights the effective price by consumption, not by month', () => {
    // A heavy cheap month and a light dear month: the average must lean to the heavy one.
    const bills = parseBills([
      bill({
        period_start: '2026-01-01',
        period_end: '2026-01-31',
        total_amount: '100',
        consumption: '1000',
      }),
      bill({
        period_start: '2026-02-01',
        period_end: '2026-02-28',
        total_amount: '100',
        consumption: '100',
      }),
    ])
    const totals = windowTotals(monthlyBuckets(bills))
    expect(totals.effective).toBeCloseTo(200 / 1100, 4)
    // The unweighted mean of 0.10 and 1.00 would be 0.55 — nowhere near.
    expect(totals.effective).toBeLessThan(0.3)
  })
})

describe('windows and comparisons', () => {
  it('reports a short history as partial rather than inventing a prior year', () => {
    const bills = parseBills(
      seedBillsNewestFirst(MAIN_RESIDENCE, { months: 7, endYear: 2026, endMonth: 7 }),
    )
    const cmp = trailingComparison(monthlyBuckets(bills))
    expect(cmp.partial).toBe(true)
    expect(cmp.current.months).toBe(7)
    expect(cmp.prior.months).toBe(0)
  })

  it('gives no year-on-year delta where there is no counterpart month', () => {
    const buckets = monthlyBuckets(main())
    expect(yoyDelta(buckets, '2024-08', (b) => b.cost)).toEqual({ abs: null, pct: null })
    const known = yoyDelta(buckets, '2026-07', (b) => b.cost)
    expect(known.pct).toBeCloseTo(12.2, 1)
  })

  it('indexes to the first month so two currencies can share an axis', () => {
    const a = monthlyBuckets(main()).map((b) => b.cost)
    const b = monthlyBuckets(second()).map((x) => x.cost)
    expect(indexToFirst(a)[0]).toBe(100)
    expect(indexToFirst(b)[0]).toBe(100)
  })

  it('takes composition shares of the summed total, not the mean of monthly shares', () => {
    const bills = main()
    const c = composition(
      bills.map((b) => ({
        energy: b.consumption !== null && b.unitPrice !== null ? b.consumption * b.unitPrice : null,
        fixed: b.fixedCharges,
        taxes: b.taxes,
        total: b.total,
      })),
    )
    const shares = [c.shares.energy, c.shares.fixed, c.shares.taxes] as number[]
    expect(shares.reduce((s, v) => s + v, 0)).toBeCloseTo(100, 0)
    expect(Math.abs(c.unexplained ?? 99)).toBeLessThan(0.5)
  })

  it('refuses a composition share when a component is unknown', () => {
    const c = composition([
      { energy: 10, fixed: 2, taxes: null, total: 15 },
      { energy: 10, fixed: 2, taxes: 3, total: 15 },
    ])
    expect(c.taxes).toBeNull()
    expect(c.shares.taxes).toBeNull()
    expect(c.unexplained).toBeNull()
  })
})

describe('headline selection', () => {
  const ctx = { currency: 'EUR' }

  it('reads the demo data as a price story', () => {
    const h = headline(trailingComparison(monthlyBuckets(main())), ctx)
    expect(h.kind).toBe('price')
    expect(h.finding).toBe('Same energy, 13.9% more money.')
    expect(h.explanation).toContain('3,060 kWh both years')
    expect(h.explanation).toContain('The whole difference is unit price.')
  })

  it('switches branch for a consumption-led series', () => {
    // Same tariff throughout, consumption climbing: the meter is the story.
    const rising = Array.from({ length: 24 }, (_, i) =>
      bill({
        period_start: `20${24 + Math.floor((7 + i) / 12)}-${String(((7 + i) % 12) + 1).padStart(2, '0')}-01`,
        period_end: `20${24 + Math.floor((7 + i) / 12)}-${String(((7 + i) % 12) + 1).padStart(2, '0')}-28`,
        total_amount: String(100 + i * 10),
        consumption: String(500 + i * 50),
        unit_price: '0.20',
      }),
    )
    const h = headline(trailingComparison(monthlyBuckets(parseBills(rising))), ctx)
    expect(h.kind).toBe('consumption')
    expect(h.finding).toBe('You used more energy.')
  })

  it('switches branch when spend fell', () => {
    const falling = Array.from({ length: 24 }, (_, i) =>
      bill({
        period_start: `20${24 + Math.floor((7 + i) / 12)}-${String(((7 + i) % 12) + 1).padStart(2, '0')}-01`,
        period_end: `20${24 + Math.floor((7 + i) / 12)}-${String(((7 + i) % 12) + 1).padStart(2, '0')}-28`,
        total_amount: String(300 - i * 5),
        consumption: '500',
        unit_price: '0.20',
      }),
    )
    const h = headline(trailingComparison(monthlyBuckets(parseBills(falling))), ctx)
    expect(h.kind).toBe('savings')
  })

  it('declines to compare when there is barely any history', () => {
    const bills = parseBills([
      bill({ period_start: '2026-07-01', period_end: '2026-07-31', total_amount: '46.17' }),
    ])
    const h = headline(trailingComparison(monthlyBuckets(bills)), ctx)
    expect(h.kind).toBe('insufficient')
  })
})
