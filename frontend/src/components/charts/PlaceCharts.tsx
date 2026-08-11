import { useSeries, useSummary } from '../../api/hooks'
import type { Granularity, Metric, Place } from '../../api/types'
import { fmtCurrency, fmtDate, fmtNumber } from '../../lib/format'
import { SeriesChart } from './SeriesChart'

interface Props {
  place: Place
  granularity: Granularity
  from?: string
  to?: string
}

const METRICS: { metric: Metric; title: (c: string) => string; kind: 'bar' | 'line' }[] = [
  { metric: 'cost', title: (c) => `Cost per month (${c})`, kind: 'line' },
  { metric: 'consumption', title: () => 'Consumption per month (kWh)', kind: 'bar' },
  {
    metric: 'unit_price',
    title: (c) => `Effective price (${c}/kWh — total paid ÷ kWh)`,
    kind: 'line',
  },
]

export function SummaryTiles({ place }: { place: Place }) {
  const { data: summary } = useSummary(place.id)
  if (!summary || summary.bill_count === 0) return null
  const currency = summary.currency_code
  return (
    <div className="tile-row">
      <div className="tile">
        <div className="tile-label">Total cost</div>
        <div className="tile-value">
          {fmtCurrency(summary.total_cost, currency, 0)}
        </div>
        <div className="tile-note">{summary.bill_count} bills</div>
      </div>
      <div className="tile">
        <div className="tile-label">Total consumption</div>
        <div className="tile-value">
          {fmtNumber(summary.total_consumption, 0)} kWh
        </div>
      </div>
      <div className="tile">
        <div className="tile-label">Avg effective price</div>
        <div className="tile-value">
          {fmtCurrency(summary.avg_effective_unit_price, currency, 4)}
        </div>
        <div className="tile-note">per kWh, all-in</div>
      </div>
      <div className="tile">
        <div className="tile-label">Last bill</div>
        <div className="tile-value">
          {fmtCurrency(summary.last_bill_total, currency)}
        </div>
        <div className="tile-note">
          {summary.last_bill_consumption
            ? `${fmtNumber(summary.last_bill_consumption, 0)} kWh · `
            : ''}
          {summary.last_period_end ? `to ${fmtDate(summary.last_period_end)}` : ''}
        </div>
      </div>
    </div>
  )
}

function MetricChart({
  place,
  metric,
  kind,
  title,
  granularity,
  from,
  to,
}: {
  place: Place
  metric: Metric
  kind: 'bar' | 'line'
  title: string
  granularity: Granularity
  from?: string
  to?: string
}) {
  const { data, isLoading } = useSeries(place.id, {
    metric,
    granularity,
    from,
    to,
  })
  const currency = place.currency_code
  const formatValue =
    metric === 'consumption'
      ? (v: number) => `${fmtNumber(v)} kWh`
      : (v: number) => fmtCurrency(v, currency, metric === 'unit_price' ? 4 : 2)

  return (
    <div className="card">
      <h2>{title}</h2>
      {granularity === 'bill' && (
        <div className="card-sub">one point per bill, plotted at period end</div>
      )}
      {isLoading || !data ? (
        <div className="empty">Loading…</div>
      ) : (
        <SeriesChart
          points={data.points}
          kind={kind}
          formatValue={formatValue}
          billGranularity={granularity === 'bill'}
        />
      )}
    </div>
  )
}

export function PlaceCharts({ place, granularity, from, to }: Props) {
  return (
    <div className="chart-grid">
      {METRICS.map(({ metric, title, kind }) => (
        <MetricChart
          key={metric}
          place={place}
          metric={metric}
          kind={granularity === 'bill' && kind === 'bar' ? 'bar' : kind}
          title={title(place.currency_code)}
          granularity={granularity}
          from={from}
          to={to}
        />
      ))}
    </div>
  )
}
