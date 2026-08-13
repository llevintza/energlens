import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { FormatContext } from '../../lib/compare'
import { buildMix } from '../../lib/compare'
import { fmtCurrency } from '../../lib/format'
import type { MonthBucket } from '../../lib/metrics'
import { useChartTokens } from './chartTheme'
import { makeCrosshairTooltip } from './CrosshairTooltip'

interface Props {
  buckets: MonthBucket[]
  format: FormatContext
  height: number
  mini?: boolean
}

/**
 * Chart 3 — the €/kWh decomposition, stacked.
 *
 * Three bands sharing a stack: the contracted tariff, the standing charge spread over
 * the kWh it was charged against, and tax on both. The total line on top is the
 * effective price.
 *
 * The reason this is worth a chart rather than a sentence: the standing-charge band
 * visibly swells every summer, because the same fixed fee divided by fewer kWh is a
 * bigger number per unit. That is why cutting consumption *raises* the headline price
 * per kWh — which reads as a tariff rise if you only ever see the headline.
 */
export function MixArea({ buckets, format, height, mini }: Props) {
  const tokens = useChartTokens()
  const { rows, domain } = buildMix(buckets)

  const axis = {
    tick: { fill: tokens.ink4, fontSize: 10, fontFamily: 'var(--font-mono)' },
    tickLine: false,
    axisLine: { stroke: tokens.axis },
  }

  const Tip = makeCrosshairTooltip(tokens, (_payload, label) => {
    const row = rows.find((r) => r.x === label)
    if (!row) return []
    const total = (row.energy ?? 0) + (row.standing ?? 0) + (row.tax ?? 0)
    return [
      { label: 'Energy', color: tokens.acc, value: fmtCurrency(row.energy, format.currency, 4) },
      { label: 'Standing', color: tokens.amber, value: fmtCurrency(row.standing, format.currency, 4) },
      { label: 'Tax', color: tokens.barfill, value: fmtCurrency(row.tax, format.currency, 4) },
      { label: 'All-in', color: tokens.ink, value: fmtCurrency(total, format.currency, 4) },
    ]
  })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart
        data={rows.map((r) => ({
          ...r,
          total: r.energy === null ? null : (r.energy ?? 0) + (r.standing ?? 0) + (r.tax ?? 0),
        }))}
        margin={mini ? { top: 2, right: 2, left: 2, bottom: 2 } : { top: 12, right: 16, left: 0, bottom: 4 }}
      >
        {!mini && <CartesianGrid vertical={false} stroke={tokens.grid} />}
        {!mini && <XAxis dataKey="x" interval={3} {...axis} />}
        {mini && <XAxis dataKey="x" hide />}
        {!mini && (
          <YAxis
            width={56}
            domain={[domain.min, domain.max]}
            ticks={domain.ticks}
            tickFormatter={(v: number) => fmtCurrency(v, format.currency, 2)}
            {...axis}
            axisLine={false}
          />
        )}
        {mini && <YAxis hide domain={[domain.min, domain.max]} />}
        {!mini && <Tooltip content={<Tip />} cursor={{ stroke: tokens.axis }} />}
        <Area dataKey="energy" stackId="mix" stroke="none" fill={tokens.acc} isAnimationActive={false} />
        <Area dataKey="standing" stackId="mix" stroke="none" fill={tokens.amber} isAnimationActive={false} />
        <Area dataKey="tax" stackId="mix" stroke="none" fill={tokens.barfill} isAnimationActive={false} />
        <Line
          dataKey="total"
          stroke={tokens.ink}
          strokeWidth={mini ? 1 : 1.6}
          dot={false}
          activeDot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
