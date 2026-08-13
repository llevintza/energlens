import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Bar, BarChart, Cell, ResponsiveContainer, YAxis } from 'recharts'

import { useBills, usePlace } from '../api/hooks'
import { useChartTokens } from '../components/charts/chartTheme'
import { QueryError } from '../components/QueryError'
import { DeltaChip } from '../components/ui/DeltaChip'
import { zeroBasedDomain } from '../lib/axis'
import { fmtCurrency, fmtDate, fmtNumber, fmtPeriod } from '../lib/format'
import type { BillComparison, ParsedBill } from '../lib/metrics'
import {
  billComparisons,
  effectivePrice,
  energyCharge,
  monthlyBuckets,
  parseBills,
} from '../lib/metrics'

function periodOf(bill: ParsedBill): string {
  return `${bill.periodEnd.getFullYear()}-${String(bill.periodEnd.getMonth() + 1).padStart(2, '0')}`
}

/** One cell of the 2×2. A missing counterpart says so instead of showing 0%. */
function ComparisonCell({
  label,
  comparison,
  currency,
}: {
  label: string
  comparison: BillComparison
  currency: string
}) {
  return (
    <div className="cmp-cell">
      <div className="cmp-label">{label}</div>
      {comparison.against === null ? (
        <>
          <div className="cmp-value cmp-none">—</div>
          <div className="cmp-against">No comparison available</div>
        </>
      ) : (
        <>
          <div className="cmp-value">
            <DeltaChip value={comparison.delta.pct} className="cmp-delta" />
          </div>
          <div className="cmp-against">
            vs {fmtCurrency(comparison.againstValue, currency, 4)}
            {' · '}
            {comparison.against.includes('average')
              ? comparison.against
              : fmtPeriod(comparison.against)}
          </div>
        </>
      )}
    </div>
  )
}

/**
 * 3f — one bill.
 *
 * The left column is what the provider told you; the right is the part they leave out.
 * Keeping that split in view is what makes the screen worth having: a bill on its own is
 * a number, and a bill inside two years of bills is information.
 */
export function BillDetailPage() {
  const { placeId, billId } = useParams()
  const place = usePlace(placeId)
  const bills = useBills(placeId)
  const tokens = useChartTokens()

  const parsed = useMemo(() => parseBills(bills.data ?? []), [bills.data])
  const buckets = useMemo(() => monthlyBuckets(parsed), [parsed])
  const bill = parsed.find((b) => b.id === billId)
  const currency = place.data?.currency_code ?? bill?.currency ?? 'EUR'

  if (bills.isError) {
    return (
      <QueryError
        error={bills.error}
        onRetry={bills.refetch}
        isRetrying={bills.isFetching}
        title="Could not load this bill"
      />
    )
  }
  if (bills.isPending) return <div className="skeleton" style={{ height: 320 }} />
  if (!bill) {
    return (
      <div className="empty-panel" style={{ height: 160 }}>
        <span>That bill is not in this place.</span>
        <Link className="btn small" to={`/places/${placeId}`}>
          Back to the dashboard
        </Link>
      </div>
    )
  }

  const period = periodOf(bill)
  const energy = energyCharge(bill)
  const effective = effectivePrice(bill)
  const comparisons = billComparisons(buckets, period)

  /* Subtotal is only meaningful when both halves are known. A "subtotal" that silently
     treats an unknown standing charge as zero is a number the provider never printed. */
  const subtotal = energy !== null && bill.fixedCharges !== null ? energy + bill.fixedCharges : null

  const composition =
    energy !== null && bill.fixedCharges !== null && bill.taxes !== null
      ? [
          { label: 'Energy', value: energy, color: tokens.acc },
          { label: 'Fixed', value: bill.fixedCharges, color: tokens.amber },
          { label: 'Taxes', value: bill.taxes, color: tokens.barfill },
        ]
      : null

  const runRows = parsed.map((b) => ({
    id: b.id,
    period: periodOf(b),
    total: b.total,
  }))
  const yearAgoPeriod = `${bill.periodEnd.getFullYear() - 1}-${String(bill.periodEnd.getMonth() + 1).padStart(2, '0')}`
  const hasYearAgo = runRows.some((r) => r.period === yearAgoPeriod)
  const runDomain = zeroBasedDomain(runRows.map((r) => r.total), 3)

  return (
    <>
      <section className="dash-section">
        <Link className="compare-crumb" to={`/places/${placeId}`}>
          ← {(place.data?.name ?? 'Place').toUpperCase()} · BILL
        </Link>
        <h1 className="dash-title">{fmtPeriod(period)}</h1>
        <div className="dash-meta">
          {fmtDate(bill.periodStart.toISOString().slice(0, 10))} –{' '}
          {fmtDate(bill.periodEnd.toISOString().slice(0, 10))} · {bill.days} days ·{' '}
          {bill.source}
        </div>
      </section>

      <div className="bill-grid">
        {/* Left — what the provider told you. */}
        <section className="dash-section">
          <div className="bill-figures">
            <div>
              <div className="stat-label">Total</div>
              <div className="bill-figure">{fmtCurrency(bill.total, currency, 2)}</div>
            </div>
            <div>
              <div className="stat-label">Used</div>
              <div className="bill-figure">
                {bill.consumption === null ? '—' : `${fmtNumber(bill.consumption, 1)}`}
              </div>
            </div>
            <div>
              <div className="stat-label">All-in</div>
              <div className="bill-figure">{fmtCurrency(effective, currency, 4)}</div>
            </div>
          </div>

          <table className="line-items">
            <tbody>
              <tr>
                <th>
                  Energy
                  {/* Showing the derivation is the point: it is how a reader checks a
                      bill instead of trusting it. */}
                  {bill.consumption !== null && bill.unitPrice !== null && (
                    <span className="line-derivation">
                      {fmtNumber(bill.consumption, 1)} kWh ×{' '}
                      {fmtCurrency(bill.unitPrice, currency, 4)}
                    </span>
                  )}
                </th>
                <td className="num">{fmtCurrency(energy, currency, 2)}</td>
              </tr>
              <tr>
                <th>Fixed charges</th>
                <td className="num">{fmtCurrency(bill.fixedCharges, currency, 2)}</td>
              </tr>
              <tr className="line-subtotal">
                <th>Subtotal</th>
                <td className="num">{fmtCurrency(subtotal, currency, 2)}</td>
              </tr>
              <tr>
                <th>Taxes</th>
                <td className="num">{fmtCurrency(bill.taxes, currency, 2)}</td>
              </tr>
              <tr className="line-total">
                <th>Total</th>
                <td className="num">{fmtCurrency(bill.total, currency, 2)}</td>
              </tr>
            </tbody>
          </table>

          {composition ? (
            <>
              <div className="composition-bar" aria-hidden="true">
                {composition.map((part) => (
                  <span
                    key={part.label}
                    style={{
                      flex: `${Math.max(0, part.value)} 0 0`,
                      background: part.color,
                    }}
                  />
                ))}
              </div>
              <div className="composition-legend">
                {composition.map((part) => (
                  <span key={part.label}>
                    <i style={{ background: part.color }} aria-hidden="true" />
                    {part.label} {fmtCurrency(part.value, currency, 2)}
                  </span>
                ))}
              </div>
            </>
          ) : (
            /* A manually entered bill with only a total is a bill with an unknown
               breakdown, not one made entirely of energy. €0.00 of tax is a claim. */
            <p className="bill-unknown">
              This bill has no breakdown recorded, so how the total splits between energy,
              standing charges and tax is unknown.
            </p>
          )}
        </section>

        {/* Right — what they leave out. */}
        <section className="dash-section">
          <div className="cmp-grid">
            <ComparisonCell
              label="vs previous month"
              comparison={comparisons.previousMonth}
              currency={currency}
            />
            <ComparisonCell
              label="vs same month last year"
              comparison={comparisons.sameMonthLastYear}
              currency={currency}
            />
            <ComparisonCell
              label="vs 12-month average"
              comparison={comparisons.twelveMonthAverage}
              currency={currency}
            />
            <ComparisonCell
              label="vs cheapest month"
              comparison={comparisons.cheapestMonth}
              currency={currency}
            />
          </div>

          <h2 className="bill-run-title">This bill in the run of {runRows.length}</h2>
          <ResponsiveContainer width="100%" height={86}>
            <BarChart data={runRows} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
              <YAxis hide domain={[runDomain.min, runDomain.max]} />
              <Bar dataKey="total" isAnimationActive={false}>
                {runRows.map((row) => (
                  <Cell
                    key={row.id}
                    fill={
                      row.id === bill.id
                        ? tokens.acc
                        : row.period === yearAgoPeriod
                          ? tokens.amber
                          : tokens.barfill
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="composition-legend">
            <span>
              <i style={{ background: tokens.acc }} aria-hidden="true" />
              This bill
            </span>
            {hasYearAgo ? (
              <span>
                <i style={{ background: tokens.amber }} aria-hidden="true" />
                {fmtPeriod(yearAgoPeriod)}
              </span>
            ) : (
              <span className="cmp-none">No bill from a year earlier</span>
            )}
          </div>

          <p className="bill-reading">{reading(comparisons, effective, currency)}</p>
        </section>
      </div>
    </>
  )
}

/** One sentence on what the numbers say — the thing a provider's PDF never offers. */
function reading(
  comparisons: ReturnType<typeof billComparisons>,
  effective: number | null,
  currency: string,
): string {
  if (effective === null) {
    return 'Without a consumption figure this bill cannot be compared on price — add the kWh and the comparisons above fill in.'
  }
  const yoy = comparisons.sameMonthLastYear.delta.pct
  const avg = comparisons.twelveMonthAverage.delta.pct
  const price = fmtCurrency(effective, currency, 4)

  if (yoy === null && avg === null) {
    return `At ${price} per kWh, this is the start of the record — later bills get measured against it.`
  }
  if (yoy !== null && Math.abs(yoy) >= 5) {
    return `At ${price} per kWh, this month cost ${Math.abs(yoy).toFixed(1)}% ${yoy > 0 ? 'more' : 'less'} per unit than the same month a year ago — a like-for-like comparison, since the season is the same.`
  }
  if (avg !== null && Math.abs(avg) >= 5) {
    return `At ${price} per kWh, this month is ${Math.abs(avg).toFixed(1)}% ${avg > 0 ? 'above' : 'below'} the twelve months before it.`
  }
  return `At ${price} per kWh, this month is in line with what came before it.`
}
