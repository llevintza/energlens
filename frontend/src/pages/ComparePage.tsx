import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useBills, usePlace } from '../api/hooks'
import { ChartFrame, chartStatus } from '../components/charts/ChartFrame'
import { useChartTokens } from '../components/charts/chartTheme'
import { CompareChart } from '../components/charts/CompareChart'
import { MixArea } from '../components/charts/MixArea'
import { MetricPicker } from '../components/compare/MetricPicker'
import { DeltaChip } from '../components/ui/DeltaChip'
import { Segmented } from '../components/ui/Segmented'
import type { MetricDescriptor, MetricId, ModeId } from '../lib/compare'
import { METRICS, METRIC_BY_ID, MODES, MODE_BY_ID, toCsv } from '../lib/compare'
import { fmtSignedPct } from '../lib/format'
import type { MonthBucket } from '../lib/metrics'
import { monthlyBuckets, parseBills, pctChange, yoyDelta } from '../lib/metrics'

type RangeKey = '12m' | '24m' | 'all'
const RANGE_MONTHS: Record<RangeKey, number | null> = { '12m': 12, '24m': 24, all: null }
const MONTH_CHIPS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
const MONTH_NAMES = [
  'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
  'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC',
]

export function ComparePage() {
  const { placeId } = useParams()
  const place = usePlace(placeId)
  const bills = useBills(placeId)
  const tokens = useChartTokens()

  const [metricId, setMetricId] = useState<MetricId>('total')
  const [modeId, setModeId] = useState<ModeId>('yoy')
  const [range, setRange] = useState<RangeKey>('24m')
  const [sameMonth, setSameMonth] = useState(1)
  const [excludedYears, setExcludedYears] = useState<number[]>([])

  const parsed = useMemo(() => parseBills(bills.data ?? []), [bills.data])
  const allBuckets = useMemo(() => monthlyBuckets(parsed), [parsed])
  const months = RANGE_MONTHS[range]
  const buckets = months === null ? allBuckets : allBuckets.slice(-months)

  const currency = place.data?.currency_code ?? parsed[0]?.currency ?? 'EUR'
  const format = useMemo(() => ({ currency }), [currency])
  const metric = METRIC_BY_ID[metricId]
  const mode = MODE_BY_ID[modeId]
  const isMix = metric.view === 'mix'

  const availableYears = useMemo(
    () => [...new Set(buckets.map((b) => b.year))].sort(),
    [buckets],
  )
  const selectedYears = availableYears.filter((y) => !excludedYears.includes(y))

  const data = useMemo(
    () =>
      isMix
        ? null
        : mode.build({
            buckets,
            metric,
            tokens,
            format,
            years: selectedYears,
            month: sameMonth,
          }),
    [isMix, mode, buckets, metric, tokens, format, selectedYears, sameMonth],
  )

  /* The ribbon always reads total cost under `mix`, because a composition has no single
     value to compare year on year. Its title says so rather than quietly switching. */
  const ribbonMetric = isMix ? METRIC_BY_ID.total : metric
  const ribbon = useMemo(() => {
    const last12 = allBuckets.slice(-12)
    return last12.map((bucket) => ({
      label: MONTH_NAMES[bucket.month - 1],
      pct: yoyDelta(allBuckets, bucket.period, ribbonMetric.select).pct,
    }))
  }, [allBuckets, ribbonMetric])
  const ribbonPeak = Math.max(1, ...ribbon.map((r) => Math.abs(r.pct ?? 0)))

  const status = chartStatus(bills, buckets.length > 0)

  const exportCsv = () => {
    if (!data) return
    const blob = new Blob([toCsv(data, metric, mode)], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${place.data?.name ?? 'place'}-${metric.id}-${mode.id}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <section className="dash-section">
        <div className="dash-head">
          <div>
            <Link className="compare-crumb" to={`/places/${placeId}`}>
              ← {(place.data?.name ?? 'Place').toUpperCase()} · COMPARE
            </Link>
            <h1 className="dash-title">{metric.label}</h1>
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
            <button type="button" className="btn small" onClick={exportCsv} disabled={!data}>
              Export CSV
            </button>
          </div>
        </div>
      </section>

      {/* The tile row IS the small-multiples view: eight metrics, each drawn under the
          currently selected mode, so switching mode redraws all eight. */}
      <section className="dash-section">
        <div className="tile-strip">
          {METRICS.map((m) => {
            const { value, delta } = tileFigures(m, allBuckets)
            const tileData =
              m.view === 'mix'
                ? null
                : mode.build({
                    buckets,
                    metric: m,
                    tokens,
                    format,
                    years: selectedYears,
                    month: sameMonth,
                    density: 'mini',
                  })
            return (
              <button
                key={m.id}
                type="button"
                className={`metric-tile${m.id === metricId ? ' selected' : ''}`}
                aria-pressed={m.id === metricId}
                onClick={() => setMetricId(m.id)}
              >
                <span className="metric-tile-short">{m.short}</span>
                <span className="metric-tile-value">
                  {value === null
                    ? '—'
                    : m.id === 'mix'
                      ? `${Math.round(value)}%`
                      : m.big(value, format)}
                </span>
                <DeltaChip value={delta} />
                <span className="metric-tile-mini" aria-hidden="true">
                  {tileData ? (
                    <CompareChart
                      data={tileData}
                      metric={m}
                      format={format}
                      height={40}
                      mini
                    />
                  ) : (
                    <MixArea buckets={buckets} format={format} height={40} mini />
                  )}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* Control row — the picker and the tiles are two views of one piece of state. */}
      <section className="dash-section">
        <div className="compare-controls">
          <MetricPicker value={metricId} onChange={setMetricId} />
          <Segmented
            ariaLabel="Comparison mode"
            options={MODES.map((m) => ({ value: m.id, label: m.label }))}
            value={modeId}
            onChange={setModeId}
            disabled={isMix}
          />
          {modeId === 'same' && !isMix && (
            <div className="month-chips" role="group" aria-label="Month">
              {MONTH_CHIPS.map((chip, i) => (
                <button
                  key={i}
                  type="button"
                  aria-pressed={sameMonth === i + 1}
                  aria-label={MONTH_NAMES[i]}
                  onClick={() => setSameMonth(i + 1)}
                >
                  {chip}
                </button>
              ))}
            </div>
          )}
          {modeId === 'years' && !isMix && (
            <div className="year-chips" role="group" aria-label="Years">
              {availableYears.map((year) => (
                <button
                  key={year}
                  type="button"
                  aria-pressed={selectedYears.includes(year)}
                  /* At least one year has to stay on, or there is nothing to draw. */
                  disabled={selectedYears.length === 1 && selectedYears.includes(year)}
                  onClick={() =>
                    setExcludedYears((current) =>
                      current.includes(year)
                        ? current.filter((y) => y !== year)
                        : [...current, year],
                    )
                  }
                >
                  {year}
                </button>
              ))}
            </div>
          )}
        </div>
        {isMix && (
          <p className="compare-caption">
            Composition is always read over time — the comparison modes do not apply to it.
          </p>
        )}
      </section>

      <section className="dash-section">
        <ChartFrame
          height={300}
          status={status}
          error={bills.error}
          onRetry={bills.refetch}
          isRetrying={bills.isFetching}
          subtitle={isMix ? undefined : data?.note}
          emptyMessage="No bills in this range yet."
        >
          {isMix ? (
            <MixArea buckets={buckets} format={format} height={300} />
          ) : data ? (
            <CompareChart
              data={data}
              metric={metric}
              format={format}
              height={300}
              labelEvery={modeId === 'mom' ? 3 : modeId === 'yoy' ? 2 : 1}
            />
          ) : null}
        </ChartFrame>
        {!isMix && data && data.legend.length > 0 && (
          <div className="compare-legend">
            {data.legend.map((item) => (
              <span key={item.label}>
                <i style={{ background: item.color }} aria-hidden="true" />
                {item.label}
              </span>
            ))}
          </div>
        )}
        {isMix && <p className="compare-caption">{buildMixNote()}</p>}
      </section>

      {/* Delta ribbon — a fixed reference strip, present in every mode. */}
      <section className="dash-section">
        <h2 className="ribbon-title">
          Δ {ribbonMetric.label.toLowerCase()} vs same month last year
          {isMix && ' (composition has no single value to compare)'}
        </h2>
        <div className="ribbon">
          {ribbon.map((column) => {
            const magnitude = Math.abs(column.pct ?? 0)
            const barHeight = Math.max(2, Math.round((magnitude / ribbonPeak) * 26))
            const rising = (column.pct ?? 0) >= 0
            return (
              <div key={column.label} className="ribbon-col">
                <span
                  className={`ribbon-pct ${column.pct === null ? 'flat' : rising ? 'up' : 'down'}`}
                >
                  {column.pct === null ? '—' : fmtSignedPct(column.pct)}
                </span>
                <span
                  className="ribbon-bar"
                  style={{
                    height: barHeight,
                    background: rising ? tokens.up : tokens.down,
                    opacity: column.pct === null ? 0.2 : 0.75,
                  }}
                />
                <span className="ribbon-month">{column.label}</span>
              </div>
            )
          })}
        </div>
      </section>
    </>
  )
}

/**
 * The headline figure on a tile, and its trailing-12 change.
 *
 * Which one is right depends on the metric. A **rate** — all-in price, contract price,
 * cost per day — is a level, so the tile shows the latest month; summing twelve months
 * of €/kWh would be a meaningless number. A **quantity** — cost, kWh, energy, taxes —
 * is a flow, so the tile shows the twelve-month total. `mix` is neither: it shows what
 * share of the bill is energy, and its delta is in percentage points, not percent.
 */
function tileFigures(
  metric: MetricDescriptor,
  buckets: MonthBucket[],
): { value: number | null; delta: number | null } {
  const current = buckets.slice(-12)
  const prior = buckets.slice(-24, -12)
  if (current.length === 0) return { value: null, delta: null }

  const sum = (window: MonthBucket[], pick: (b: MonthBucket) => number | null) => {
    const known = window.map(pick).filter((v): v is number => v !== null)
    return known.length === 0 ? null : known.reduce((a, b) => a + b, 0)
  }

  if (metric.id === 'mix') {
    const share = (window: MonthBucket[]) => {
      const energy = sum(window, (b) => b.energy)
      const cost = sum(window, (b) => b.cost)
      return energy === null || cost === null || cost === 0 ? null : (energy / cost) * 100
    }
    const now = share(current)
    const before = share(prior)
    return {
      value: now,
      /* Points, not percent: a share moving 62% → 64% moved two points. */
      delta: now === null || before === null ? null : now - before,
    }
  }

  const isRate = metric.id === 'eff' || metric.id === 'price' || metric.id === 'perDay'
  if (isRate) {
    const latest = [...current].reverse().find((b) => metric.select(b) !== null)
    const yearAgo = [...prior].reverse().find((b) => metric.select(b) !== null)
    const now = latest ? metric.select(latest) : null
    const before = yearAgo ? metric.select(yearAgo) : null
    return {
      value: now,
      delta: now === null || before === null ? null : pctChange(before, now),
    }
  }

  const now = sum(current, metric.select)
  const before = sum(prior, metric.select)
  return {
    value: now,
    delta: now === null || before === null ? null : pctChange(before, now),
  }
}

function buildMixNote(): string {
  return 'Every component divided by the kWh it was spread over. The standing-charge band swells in light months, which is why cutting consumption raises your headline price per unit.'
}
