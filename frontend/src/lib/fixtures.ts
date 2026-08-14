import type { Bill } from '../api/types'
import { round } from './metrics'

/**
 * The demo series, replayed in TypeScript.
 *
 * `backend/app/seed.py` generates exactly this, and the design prototypes are drawn
 * with it, so it is the fixture that lets a test assert the handoff's own figures
 * rather than whatever the code currently produces.
 *
 * **The window is pinned deliberately.** `seed.py` counts 24 months back from *last
 * month*, so it reproduces the handoff only for as long as "last month" is July 2026.
 * The kWh totals are stable either way — each calendar month appears exactly once per
 * 12-month window, so both windows are always 3,060 kWh — but spend is not, because
 * which calendar month pairs with which price index shifts: €787.37 for a July-2026
 * end, €784.77 for August. Deriving the fixture from `new Date()` would therefore make
 * every currency assertion below start failing in September for no reason.
 *
 * Bills are emitted in API shape — money as strings, ISO dates — so that tests
 * exercise the parse boundary rather than stepping around it.
 */

export interface SeedParams {
  baseKwh: number
  winterExtraKwh: number
  startPrice: number
  priceStep: number
  fixed: number
  currency: string
  /** 0 = calendar-month periods. 15 = 15th-to-14th, which is what makes the second
   *  place exercise the cross-month proration path. */
  dayOffset: 0 | 15
}

/** `Main Residence` in seed.py — EUR, calendar months. */
export const MAIN_RESIDENCE: SeedParams = {
  baseKwh: 160,
  winterExtraKwh: 190,
  startPrice: 0.155,
  priceStep: 0.0022,
  fixed: 5.9,
  currency: 'EUR',
  dayOffset: 0,
}

/** `Second Home` in seed.py — RON, periods that straddle month boundaries. */
export const SECOND_HOME: SeedParams = {
  baseKwh: 45,
  winterExtraKwh: 90,
  startPrice: 0.65,
  priceStep: 0.008,
  fixed: 12.0,
  currency: 'RON',
  dayOffset: 15,
}

/** The window the handoff's figures were measured over. */
export const SEED_END_YEAR = 2026
export const SEED_END_MONTH = 7
export const SEED_MONTHS = 24

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function iso(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function addDays(year: number, month: number, day: number, days: number): string {
  const d = new Date(year, month - 1, day + days)
  return iso(d.getFullYear(), d.getMonth() + 1, d.getDate())
}

/** The `n` months ending at (endYear, endMonth), oldest first. */
function monthsEndingAt(n: number, endYear: number, endMonth: number): [number, number][] {
  const out: [number, number][] = []
  let year = endYear
  let month = endMonth
  for (let i = 0; i < n; i++) {
    out.push([year, month])
    if (month === 1) {
      year -= 1
      month = 12
    } else {
      month -= 1
    }
  }
  return out.reverse()
}

/**
 * Generate the seeded bills for one place.
 *
 * ```
 * kwh_i   = base + winter × (1 + cos(2π(month−1)/12)) / 2
 * price_i = start + step × i                    (i = 0…23, oldest first)
 * taxes_i = (kwh_i × price_i + fixed) × 0.19
 * total_i = kwh_i × price_i + fixed + taxes_i
 * ```
 */
export function seedBills(
  params: SeedParams,
  options: { placeId?: string; months?: number; endYear?: number; endMonth?: number } = {},
): Bill[] {
  const {
    placeId = 'place-1',
    months = SEED_MONTHS,
    endYear = SEED_END_YEAR,
    endMonth = SEED_END_MONTH,
  } = options

  return monthsEndingAt(months, endYear, endMonth).map(([year, month], i) => {
    const seasonal = (1 + Math.cos((2 * Math.PI * (month - 1)) / 12)) / 2
    const kwh = round(params.baseKwh + params.winterExtraKwh * seasonal, 1)
    const price = round(params.startPrice + params.priceStep * i, 4)
    const energy = kwh * price
    const subtotal = energy + params.fixed
    const taxes = subtotal * 0.19
    const total = round(subtotal + taxes, 2)

    const periodStart =
      params.dayOffset === 0 ? iso(year, month, 1) : iso(year, month, 15)
    const periodEnd =
      params.dayOffset === 0
        ? iso(year, month, daysInMonth(year, month))
        : addDays(year, month, 15, daysInMonth(year, month) - 1)

    return {
      id: `${placeId}-bill-${i}`,
      place_id: placeId,
      utility_type: 'electricity',
      period_start: periodStart,
      period_end: periodEnd,
      consumption: kwh.toFixed(3),
      unit: 'kWh',
      unit_price: price.toFixed(6),
      fixed_charges: round(params.fixed, 2).toFixed(2),
      taxes: round(taxes, 2).toFixed(2),
      total_amount: total.toFixed(2),
      currency_code: params.currency,
      provider_name: null,
      raw_file_ref: null,
      source: 'script',
      notes: null,
      // seed.py writes none of the invoice fields — the seed is generated, not
      // extracted from a PDF — so the fixture carries what the API returns.
      provider_invoice_series: null,
      provider_invoice_number: null,
      issued_on: null,
      due_on: null,
      net_amount: null,
      vat_base: null,
      vat_rate: null,
      vat_amount: null,
      balance_brought_forward: null,
      total_due: total.toFixed(2),
      read_method: null,
      document_type: 'invoice',
      corrects_bill_id: null,
      customer_code: null,
      provider_tax_id: null,
      document_id: null,
      created_at: `${periodEnd}T00:00:00Z`,
      updated_at: `${periodEnd}T00:00:00Z`,
    } satisfies Bill
  })
}

/** `/bills` returns newest-first; anything reading a fixture should have to sort. */
export function seedBillsNewestFirst(
  params: SeedParams,
  options?: Parameters<typeof seedBills>[1],
): Bill[] {
  return seedBills(params, options).slice().reverse()
}
