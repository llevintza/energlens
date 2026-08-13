import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { paddedDomain, zeroBasedDomain } from '../../lib/axis'
import { fmtCurrency, fmtMonthTickMono, fmtNumber } from '../../lib/format'
import type { MonthBucket } from '../../lib/metrics'
import { yoyDelta } from '../../lib/metrics'
import { useChartTokens } from './chartTheme'
import { makeCrosshairTooltip } from './CrosshairTooltip'

interface Props {
  buckets: MonthBucket[]
  currency: string
  height?: number
}

/**
 * Chart 1 — price against consumption, on two axes.
 *
 * kWh as bars on the left, effective all-in €/kWh as a solid line on the right, and the
 * **contracted** tariff as a dashed line on the same right axis. The widening gap
 * between the two lines is fixed charges and tax, and it is the reason the chart is
 * drawn this way at all — see the subtitle the dashboard passes in.
 *
 * The contracted price comes from `bill.unit_price` and exists nowhere in `/series`,
 * which is why this page derives from `/bills`.
 */
export function HeroPriceUse({ buckets, currency, height = 236 }: Props) {
  const tokens = useChartTokens()

  const rows = buckets.map((b) => ({
    period: b.period,
    kwh: b.kwh,
    effective: b.effective,
    unitPrice: b.unitPrice,
  }))

  const left = zeroBasedDomain(rows.map((r) => r.kwh), 4)
  /* Both price series share the right axis, so the domain has to see both — scaling to
     the effective price alone would push the contracted line off the bottom. */
  const right = paddedDomain(
    [...rows.map((r) => r.effective), ...rows.map((r) => r.unitPrice)],
    4,
  )

  const axis = {
    tick: { fill: tokens.ink4, fontSize: 10, fontFamily: 'var(--font-mono)' },
    tickLine: false,
    axisLine: { stroke: tokens.axis },
  }

  const Tip = makeCrosshairTooltip(tokens, (payload, label) => {
    const bucket = buckets.find((b) => b.period === label)
    if (!bucket) return []
    void payload
    return [
      {
        label: 'Used',
        color: tokens.barfill,
        value: bucket.kwh === null ? '—' : `${fmtNumber(bucket.kwh, 0)} kWh`,
        yoy: yoyDelta(buckets, label, (b) => b.kwh).pct,
      },
      {
        label: 'All-in price',
        color: tokens.acc,
        value: fmtCurrency(bucket.effective, currency, 4),
        yoy: yoyDelta(buckets, label, (b) => b.effective).pct,
      },
      {
        label: 'Contract price',
        color: tokens.amber,
        value: fmtCurrency(bucket.unitPrice, currency, 4),
        yoy: yoyDelta(buckets, label, (b) => b.unitPrice).pct,
      },
    ]
  })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={tokens.grid} />
        <XAxis dataKey="period" tickFormatter={fmtMonthTickMono} {...axis} />
        <YAxis
          yAxisId="kwh"
          width={44}
          domain={[left.min, left.max]}
          ticks={left.ticks}
          tickFormatter={(v: number) => fmtNumber(v, 0)}
          {...axis}
          axisLine={false}
        />
        <YAxis
          yAxisId="price"
          orientation="right"
          width={52}
          domain={[right.min, right.max]}
          ticks={right.ticks}
          tickFormatter={(v: number) => fmtCurrency(v, currency, 2)}
          {...axis}
          axisLine={false}
        />
        {/* An element, not a function: Recharts clones it and injects active/payload/
            label, which avoids having to satisfy its per-chart generic inference. The
            tooltip renders its own heading, so no labelFormatter is needed. */}
        <Tooltip content={<Tip />} cursor={{ fill: tokens.rule }} />
        <Bar
          yAxisId="kwh"
          dataKey="kwh"
          fill={tokens.barfill}
          maxBarSize={22}
          barSize={undefined}
          isAnimationActive={false}
        />
        {/* connectNulls stays false on both lines: a month with no bill is a hole in the
            record, and bridging it would draw a price that was never charged. */}
        <Line
          yAxisId="price"
          dataKey="effective"
          stroke={tokens.acc}
          strokeWidth={2.25}
          dot={{ r: 2.4, fill: tokens.acc, strokeWidth: 0 }}
          activeDot={{ r: 4 }}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          yAxisId="price"
          dataKey="unitPrice"
          stroke={tokens.amber}
          strokeWidth={1.75}
          strokeDasharray="4 3"
          dot={false}
          activeDot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
