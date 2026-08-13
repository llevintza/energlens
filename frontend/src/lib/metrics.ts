import type { Bill } from '../api/types'

/**
 * Derived metrics over bills.
 *
 * The API sends money and decimals as **strings** to preserve precision, and
 * `consumption`, `unit_price`, `fixed_charges` and `taxes` are all nullable. Parsing
 * happens once here, at the module boundary, so no screen has to remember either fact.
 *
 * A null is not a zero. A bill with no `taxes` is a bill whose tax is unknown, and
 * rendering it as €0.00 would be a claim — and a false one.
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
}

/** Dates arrive as plain `YYYY-MM-DD`. Parsing them as local midnight rather than
 *  letting `new Date('2026-07-01')` mean UTC keeps a period from sliding a day
 *  backwards for anyone west of Greenwich. */
function parseDate(iso: string): Date {
  return new Date(`${iso}T00:00:00`)
}

const MS_PER_DAY = 24 * 60 * 60 * 1000

/** Inclusive, so a 1st-to-31st bill is 31 days and not 30. */
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
 *  Feeds the sparklines in the rail, the places table and login. */
export function effectivePriceSeries(bills: ParsedBill[]): number[] {
  return bills
    .map(effectivePrice)
    .filter((v): v is number => v !== null)
}

/** Percentage change, or null when there is no honest baseline to measure against. */
export function pctChange(from: number, to: number): number | null {
  if (!Number.isFinite(from) || from === 0) return null
  return ((to - from) / Math.abs(from)) * 100
}
