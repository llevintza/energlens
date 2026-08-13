import { useMemo, useState, type ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { useCompare, usePlaces } from '../api/hooks'
import type { Granularity } from '../api/types'
import { CompareChart } from '../components/charts/CompareChart'
import { PlaceCharts, SummaryTiles } from '../components/charts/PlaceCharts'
import { MAX_COMPARE_SERIES } from '../components/charts/chartTheme'
import { QueryError } from '../components/QueryError'
import { fmtNumber } from '../lib/format'

type RangeKey = '12m' | '24m' | 'all'

function rangeFrom(key: RangeKey): string | undefined {
  if (key === 'all') return undefined
  const months = key === '12m' ? 12 : 24
  const now = new Date()
  const d = new Date(now.getFullYear(), now.getMonth() - (months - 1), 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/**
 * Loading / failed / ready for one chart panel.
 *
 * The error branch comes first on purpose. Gating on `data` alone — as this
 * did — leaves "Loading…" on screen permanently once a query has errored,
 * because `data` stays undefined and nothing ever sets it.
 */
function ChartPanel<T>({
  query,
  children,
}: {
  query: UseQueryResult<T>
  children: (data: T) => ReactNode
}) {
  if (query.isError) {
    return (
      <QueryError
        compact
        error={query.error}
        onRetry={query.refetch}
        isRetrying={query.isFetching}
      />
    )
  }
  if (!query.data) return <div className="empty">Loading…</div>
  return <>{children(query.data)}</>
}

function ComparePanel({
  from,
  colorIndex,
}: {
  from?: string
  colorIndex: (placeId: string) => number
}) {
  const consumption = useCompare({ metric: 'consumption', from })
  const cost = useCompare({ metric: 'cost', from })

  const costSeries = (cost.data?.series ?? []).slice(0, MAX_COMPARE_SERIES)
  const currencies = new Set(costSeries.map((s) => s.currency_code))
  const mixedCurrencies = currencies.size > 1

  return (
    <div className="chart-grid">
      <div className="card">
        <h2>Consumption per month (kWh)</h2>
        <ChartPanel query={consumption}>
          {(data) => (
            <CompareChart
              series={data.series.slice(0, MAX_COMPARE_SERIES)}
              colorIndex={colorIndex}
              formatValue={(v) => `${fmtNumber(v)} kWh`}
            />
          )}
        </ChartPanel>
      </div>
      <div className="card">
        <h2>Cost per month</h2>
        {mixedCurrencies && (
          <div className="card-sub">
            Each line is in its own currency (no conversion applied) — compare
            trends, not absolute heights.
          </div>
        )}
        <ChartPanel query={cost}>
          {() => (
            <CompareChart
              series={costSeries}
              colorIndex={colorIndex}
              labelFor={(s) => `${s.place_name} (${s.currency_code})`}
              formatValue={(v) => fmtNumber(v, 2)}
            />
          )}
        </ChartPanel>
      </div>
    </div>
  )
}

export function DashboardPage() {
  const {
    data: places,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = usePlaces()
  const [selected, setSelected] = useState<string | 'all'>('all')
  const [range, setRange] = useState<RangeKey>('24m')
  const [granularity, setGranularity] = useState<Granularity>('month')

  // Series color follows the place's stable position in the full list.
  const colorIndex = useMemo(() => {
    const order = new Map((places ?? []).map((p, i) => [p.id, i]))
    return (placeId: string) => order.get(placeId) ?? 0
  }, [places])

  if (isLoading) return <div className="empty">Loading…</div>

  // Ahead of the welcome screen below, which would otherwise greet a user with
  // two years of bills as though they had just signed up.
  if (isError) {
    return (
      <QueryError error={error} onRetry={refetch} isRetrying={isFetching} />
    )
  }

  if (!places || places.length === 0) {
    return (
      <div className="card empty">
        Welcome! Start by <Link to="/places">adding a place</Link> — then add or
        import its electricity bills to see the charts.
      </div>
    )
  }

  const from = rangeFrom(range)
  const singlePlace =
    selected === 'all' ? (places.length === 1 ? places[0] : null) : places.find((p) => p.id === selected)
  const tooManyForCompare = places.length > MAX_COMPARE_SERIES

  return (
    <>
      <div className="page-title">
        <h1>Dashboard</h1>
        <span className="sub">how your energy use and spend evolve</span>
      </div>

      <div className="filter-row">
        {places.length > 1 && (
          <div className="seg">
            <button
              className={selected === 'all' ? 'on' : ''}
              onClick={() => setSelected('all')}
            >
              Compare
            </button>
            {places.map((p) => (
              <button
                key={p.id}
                className={selected === p.id ? 'on' : ''}
                onClick={() => setSelected(p.id)}
              >
                {p.name}
              </button>
            ))}
          </div>
        )}
        <div className="seg">
          {(['12m', '24m', 'all'] as const).map((k) => (
            <button
              key={k}
              className={range === k ? 'on' : ''}
              onClick={() => setRange(k)}
            >
              {k === 'all' ? 'All time' : `Last ${k.replace('m', ' months')}`}
            </button>
          ))}
        </div>
        {singlePlace && (
          <div className="seg">
            {(['month', 'bill'] as const).map((g) => (
              <button
                key={g}
                className={granularity === g ? 'on' : ''}
                onClick={() => setGranularity(g)}
              >
                {g === 'month' ? 'Monthly' : 'Per bill'}
              </button>
            ))}
          </div>
        )}
      </div>

      {singlePlace ? (
        <>
          <SummaryTiles place={singlePlace} />
          <PlaceCharts place={singlePlace} granularity={granularity} from={from} />
        </>
      ) : (
        <>
          {tooManyForCompare && (
            <p className="note">
              Comparing the first {MAX_COMPARE_SERIES} places — select a place
              above to see the rest.
            </p>
          )}
          <ComparePanel from={from} colorIndex={colorIndex} />
        </>
      )}
    </>
  )
}
