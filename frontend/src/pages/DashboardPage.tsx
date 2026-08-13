import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useBills, useCreateBill, usePlace } from '../api/hooks'
import { usePreferences } from '../prefs/PreferencesProvider'
import { ChartFrame, chartStatus } from '../components/charts/ChartFrame'
import { HeroPriceUse } from '../components/charts/HeroPriceUse'
import { RateEvidence } from '../components/charts/RateEvidence'
import { BillForm } from '../components/BillForm'
import { QueryError } from '../components/QueryError'
import { Drawer } from '../components/ui/Drawer'
import { DeltaChip } from '../components/ui/DeltaChip'
import { Segmented } from '../components/ui/Segmented'
import { StatCell } from '../components/ui/StatCell'
import {
  fmtCurrency,
  fmtNumber,
  fmtPeriod,
} from '../lib/format'
import type { MonthBucket, ParsedBill } from '../lib/metrics'
import {
  contractRateChange,
  costPerDay,
  effectivePrice,
  energyCharge,
  headline,
  monthlyBuckets,
  parseBills,
  pctChange,
  tariffShape,
  trailingComparison,
  yoyDelta,
} from '../lib/metrics'

type RangeKey = '12m' | '24m' | 'all'
type Granularity = 'month' | 'bill'

const RANGE_MONTHS: Record<RangeKey, number | null> = { '12m': 12, '24m': 24, all: null }

/**
 * Per-bill points, shaped like buckets so the hero chart has one input.
 *
 * Keyed by `period_end`, so two bills in one month stay two points — which is the whole
 * reason someone switches to PER BILL. Year-on-year lookups return nothing here, and
 * that is honest: a bill has no guaranteed counterpart a year earlier the way a
 * calendar month does.
 */
function billsAsPoints(bills: ParsedBill[]): MonthBucket[] {
  return bills.map((bill) => ({
    period: bill.periodEnd.toISOString().slice(0, 10),
    year: bill.periodEnd.getFullYear(),
    month: bill.periodEnd.getMonth() + 1,
    cost: bill.total,
    kwh: bill.consumption,
    effective: effectivePrice(bill),
    unitPrice: bill.unitPrice,
    energy: energyCharge(bill),
    fixed: bill.fixedCharges,
    taxes: bill.taxes,
    perDay: costPerDay(bill),
    billIds: [bill.id],
  }))
}

export function DashboardPage() {
  const { placeId } = useParams()
  const place = usePlace(placeId)
  const bills = useBills(placeId)
  const createBill = useCreateBill(placeId ?? '')

  /* Seeded from the persisted preference, then local — changing the range here is a
     look at this place, not a new default for every place. */
  const { prefs } = usePreferences()
  const [range, setRange] = useState<RangeKey>(prefs.defaultRange)
  const [granularity, setGranularity] = useState<Granularity>('month')
  const [addingBill, setAddingBill] = useState(false)

  const parsed = useMemo(() => parseBills(bills.data ?? []), [bills.data])
  const allBuckets = useMemo(() => monthlyBuckets(parsed), [parsed])

  /* The range control is an instant client-side refilter. All the bills are already
     loaded, so 12M is a slice of what is in memory, not another request. */
  const months = RANGE_MONTHS[range]
  const buckets = months === null ? allBuckets : allBuckets.slice(-months)
  const billsInRange = useMemo(() => {
    if (months === null) return parsed
    const earliest = buckets[0]?.period
    return earliest === undefined
      ? parsed
      : parsed.filter(
          (b) =>
            `${b.periodEnd.getFullYear()}-${String(b.periodEnd.getMonth() + 1).padStart(2, '0')}` >=
            earliest,
        )
  }, [parsed, buckets, months])

  const comparison = useMemo(() => trailingComparison(allBuckets), [allBuckets])
  const currency = place.data?.currency_code ?? parsed[0]?.currency ?? 'EUR'
  const finding = useMemo(
    () => headline(comparison, { currency }),
    [comparison, currency],
  )
  const tariff = useMemo(() => tariffShape(parsed), [parsed])
  const rate = useMemo(() => contractRateChange(parsed), [parsed])

  const heroRows = granularity === 'month' ? buckets : billsAsPoints(billsInRange)
  const status = chartStatus(bills, buckets.length > 0)

  const lastBill = parsed[parsed.length - 1]
  const firstBucket = allBuckets[0]
  const latestBucket = allBuckets[allBuckets.length - 1]

  const lastBillYoy = lastBill
    ? yoyDelta(
        allBuckets,
        `${lastBill.periodEnd.getFullYear()}-${String(lastBill.periodEnd.getMonth() + 1).padStart(2, '0')}`,
        (b) => b.cost,
      )
    : { abs: null, pct: null }

  /* "since <first month>" — measured against the very first month on record, which is
     what the handoff's ALL-IN KPI quotes. Not the ratio of the two window averages. */
  const allInSinceStart =
    firstBucket?.effective != null && latestBucket?.effective != null
      ? pctChange(firstBucket.effective, latestBucket.effective)
      : null

  const recent = [...parsed].reverse().slice(0, 5)

  if (place.isError) {
    return (
      <QueryError
        error={place.error}
        onRetry={place.refetch}
        isRetrying={place.isFetching}
        title="Could not load this place"
      />
    )
  }

  return (
    <>
      {/* 1 — Header */}
      <section className="dash-section">
        <div className="dash-head">
          <div>
            <h1 className="dash-title">{place.data?.name ?? 'Loading…'}</h1>
            <div className="dash-meta">
              {[
                place.data?.address_line1,
                place.data?.city,
                parsed[0] ? `${parsed.length} bills` : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </div>
          </div>
          <div className="dash-head-controls">
            <Segmented
              ariaLabel="Range"
              monoLabels
              options={[
                { value: '12m', label: '12M' },
                { value: '24m', label: '24M' },
                { value: 'all', label: 'ALL' },
              ]}
              value={range}
              onChange={setRange}
            />
            <Segmented
              ariaLabel="Granularity"
              monoLabels
              options={[
                { value: 'month', label: 'MONTHLY' },
                { value: 'bill', label: 'PER BILL' },
              ]}
              value={granularity}
              onChange={setGranularity}
            />
          </div>
        </div>
      </section>

      {/* 2 — Headline. Generated from the data, not written into the page. */}
      <section className="dash-section">
        <div className="dash-headline">
          <p className="dash-finding">{finding.finding}</p>
          <p className="dash-explanation">{finding.explanation}</p>
        </div>
      </section>

      {/* 3 — KPI row */}
      <section className="dash-section">
        <div className="kpi-row">
          <StatCell
            label="Last bill"
            value={fmtCurrency(lastBill?.total, currency, 2)}
            delta={lastBillYoy.pct}
            note={
              lastBill
                ? `vs ${fmtPeriod(`${lastBill.periodEnd.getFullYear() - 1}-${String(lastBill.periodEnd.getMonth() + 1).padStart(2, '0')}`)}`
                : undefined
            }
          />
          <StatCell
            label="All-in €/kWh"
            value={fmtCurrency(latestBucket?.effective, currency, 4)}
            delta={allInSinceStart}
            note={firstBucket ? `since ${fmtPeriod(firstBucket.period)}` : undefined}
          />
          <StatCell
            label="12-mo spend"
            value={fmtCurrency(comparison.current.cost, currency, 0)}
            delta={comparison.cost.pct}
            note={comparison.partial ? `over ${comparison.current.months} mo` : 'vs prior 12 mo'}
          />
          <StatCell
            label="12-mo use"
            value={fmtNumber(comparison.current.kwh, 0)}
            delta={comparison.kwh.pct}
            note={
              comparison.kwh.pct !== null && Math.abs(comparison.kwh.pct) < 0.05
                ? 'kWh, unchanged'
                : 'kWh'
            }
          />
          <StatCell
            label="Cost per day"
            value={fmtCurrency(lastBill ? costPerDay(lastBill) : null, currency, 2)}
            delta={lastBillYoy.pct}
            note="period-normalized"
          />
        </div>
      </section>

      {/* 4 — Hero */}
      <section className="dash-section">
        <ChartFrame
          height={236}
          title="Price against consumption"
          subtitle="Bars are kWh. The solid line is what you actually paid per kWh; the dashed line is your contracted rate. The gap between them is fixed charges and tax, and it widens."
          status={status}
          error={bills.error}
          onRetry={bills.refetch}
          isRetrying={bills.isFetching}
          emptyMessage="No bills yet — add one to see how price and consumption move."
          emptyAction={
            placeId && (
              <button type="button" className="btn small" onClick={() => setAddingBill(true)}>
                Add bill
              </button>
            )
          }
        >
          <HeroPriceUse buckets={heroRows} currency={currency} />
        </ChartFrame>
      </section>

      {/* 5 — Is the rise real? */}
      <section className="dash-section">
        <ChartFrame
          height={232}
          title="Is the rise real?"
          status={status}
          error={bills.error}
          onRetry={bills.refetch}
          emptyMessage="Not enough bills yet to separate rate from usage."
        >
          <div className="evidence">
            <RateEvidence bills={billsInRange} tariff={tariff} currency={currency} />
            <div>
              <div className="evidence-eyebrow">Contract rate, seasonality removed</div>
              <div className="evidence-figure">
                {rate.abs === null
                  ? '—'
                  : `${rate.abs >= 0 ? '+' : '−'}${fmtCurrency(Math.abs(rate.abs), currency, 4)}`}
              </div>
              <div className="evidence-range">
                {fmtCurrency(rate.first, currency, 4)} → {fmtCurrency(rate.latest, currency, 4)} per kWh
              </div>
              <p className="evidence-body">
                Each dot is one bill: what you used, against what it worked out at per
                kWh. The dashed curves are what your tariff implies at each level of
                use. If the rise were down to lighter usage, the dots would slide along
                one curve — instead they sit off the lower one and onto the upper one at
                every level, which makes it a rate change.
              </p>
            </div>
          </div>
        </ChartFrame>
      </section>

      {/* 6 — Compare entry */}
      <section className="dash-section">
        <div className="compare-entry">
          <div>
            <h2>Compare</h2>
            <p>Eight metrics against four ways of slicing time, on one screen.</p>
          </div>
          <Link className="btn" to={`/places/${placeId}/compare`} style={{ marginLeft: 'auto' }}>
            Open Compare →
          </Link>
        </div>
      </section>

      {/* 7 — Recent bills */}
      <section className="dash-section">
        <div className="bills-head">
          <h2>Recent bills</h2>
          <div className="bills-head-actions">
            <button type="button" className="btn small" onClick={() => setAddingBill(true)}>
              Add bill
            </button>
            <Link className="btn small" to={`/places/${placeId}/manage`}>
              All {parsed.length} bills →
            </Link>
          </div>
        </div>
        {bills.isError ? (
          <QueryError error={bills.error} onRetry={bills.refetch} compact />
        ) : recent.length === 0 ? (
          <div className="empty-panel" style={{ height: 120 }}>
            <span>No bills recorded yet.</span>
          </div>
        ) : (
          <table className="bills">
            <thead>
              <tr>
                <th>Period</th>
                <th className="num">kWh</th>
                <th className="num">€/kWh eff</th>
                <th className="num">Energy</th>
                <th className="num">Fixed</th>
                <th className="num">Taxes</th>
                <th className="num">Total</th>
                <th className="num">vs last yr</th>
                <th>Src</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((bill) => {
                const period = `${bill.periodEnd.getFullYear()}-${String(bill.periodEnd.getMonth() + 1).padStart(2, '0')}`
                return (
                  <tr key={bill.id}>
                    <td data-label="Period">
                      <Link to={`/places/${placeId}/bills/${bill.id}`}>
                        {fmtPeriod(period)}
                      </Link>
                    </td>
                    <td className="num" data-label="kWh">
                      {fmtNumber(bill.consumption, 1)}
                    </td>
                    <td className="num" data-label="Effective">
                      {fmtCurrency(effectivePrice(bill), currency, 4)}
                    </td>
                    <td className="num hide-sm" data-label="Energy">
                      {fmtCurrency(energyCharge(bill), currency, 2)}
                    </td>
                    <td className="num hide-sm" data-label="Fixed">
                      {fmtCurrency(bill.fixedCharges, currency, 2)}
                    </td>
                    <td className="num hide-sm" data-label="Taxes">
                      {fmtCurrency(bill.taxes, currency, 2)}
                    </td>
                    <td className="num total" data-label="Total">
                      {fmtCurrency(bill.total, currency, 2)}
                    </td>
                    <td className="num hide-sm" data-label="vs last year">
                      <DeltaChip value={yoyDelta(allBuckets, period, (b) => b.cost).pct} />
                    </td>
                    <td className="hide-sm" data-label="Source">
                      {bill.source}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* 3d — a drawer over the page you were on, so adding a bill never loses the
          dashboard you were reading. */}
      <Drawer open={addingBill} onClose={() => setAddingBill(false)} title="Add bill">
        <BillForm
          currency={currency}
          onCancel={() => setAddingBill(false)}
          onSubmit={async (values) => {
            await createBill.mutateAsync(values)
            setAddingBill(false)
          }}
        />
      </Drawer>
    </>
  )
}
