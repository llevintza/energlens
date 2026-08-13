import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  XAxis,
  YAxis,
} from 'recharts'

import { paddedDomain, zeroBasedDomain } from '../../lib/axis'
import { fmtCurrency, fmtNumber } from '../../lib/format'
import type { ParsedBill } from '../../lib/metrics'
import { effectivePrice } from '../../lib/metrics'
import type { TariffShape } from '../../lib/metrics'
import { alpha, useChartTokens } from './chartTheme'

interface Props {
  bills: ParsedBill[]
  tariff: TariffShape
  currency: string
  height?: number
}

/**
 * Chart 2 — effective price against consumption, as a scatter with two model curves.
 *
 * The argument: each point is one bill, placed by how much was used and what it worked
 * out at per kWh. The two dashed curves are what the tariff *implies* the effective
 * price should be at each consumption level — `eff(k) = (1 + tax) × (p + fixed ÷ k)` —
 * drawn for the first contracted price and the latest.
 *
 * If the rise were lighter usage, the points would slide left along one curve. Instead
 * they sit off the lower curve and onto the upper one **at every consumption level**,
 * which is what makes it a rate change. A version of this chart that does not make that
 * visible has missed the point.
 *
 * The tariff constants are derived from the place's own bills, not hardcoded — the
 * handoff's 1.19 and 5.90 are the demo tariff's, and would be wrong for anyone else.
 */
export function RateEvidence({ bills, tariff, currency, height = 232 }: Props) {
  const tokens = useChartTokens()

  const points = bills
    .map((bill, i) => {
      const eff = effectivePrice(bill)
      if (eff === null || bill.consumption === null) return null
      return {
        kwh: bill.consumption,
        eff,
        /* Alpha ramped 0.22 → 1.00 by recency, so the direction of travel is legible
           without a legend: the faint points are two years ago. */
        fill: alpha(tokens.accRgb, 0.22 + (i / Math.max(1, bills.length - 1)) * 0.78),
        r: i === bills.length - 1 ? 5 : 4,
      }
    })
    .filter((p): p is NonNullable<typeof p> => p !== null)

  const kwhValues = points.map((p) => p.kwh)
  const xDomain = zeroBasedDomain(kwhValues, 4)
  /* The scatter reads better on a domain that hugs the data rather than starting at
     zero, so the x-axis is taken from the observed range with a margin. */
  const kMin = Math.max(0, Math.min(...kwhValues) * 0.9)
  const kMax = Math.max(...kwhValues) * 1.06

  const curveFor = (price: number | null) => {
    if (price === null || tariff.fixedPerBill === null || tariff.taxRate === null) return []
    const out: { kwh: number; model: number }[] = []
    const step = Math.max(1, (kMax - kMin) / 40)
    for (let k = kMin + step; k <= kMax; k += step) {
      out.push({ kwh: k, model: (1 + tariff.taxRate) * (price + tariff.fixedPerBill / k) })
    }
    return out
  }

  const oldCurve = curveFor(tariff.firstUnitPrice)
  const newCurve = curveFor(tariff.latestUnitPrice)
  const yDomain = paddedDomain(
    [...points.map((p) => p.eff), ...oldCurve.map((c) => c.model), ...newCurve.map((c) => c.model)],
    3,
  )

  const axis = {
    tick: { fill: tokens.ink4, fontSize: 10, fontFamily: 'var(--font-mono)' },
    tickLine: false,
    axisLine: { stroke: tokens.axis },
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart margin={{ top: 12, right: 14, left: 0, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={tokens.grid} />
        <XAxis
          type="number"
          dataKey="kwh"
          domain={[Math.floor(kMin), Math.ceil(kMax)]}
          ticks={xDomain.ticks.filter((t) => t >= kMin && t <= kMax)}
          tickFormatter={(v: number) => fmtNumber(v, 0)}
          {...axis}
        />
        <YAxis
          type="number"
          dataKey="eff"
          width={52}
          domain={[yDomain.min, yDomain.max]}
          ticks={yDomain.ticks}
          tickFormatter={(v: number) => fmtCurrency(v, currency, 2)}
          {...axis}
          axisLine={false}
        />
        {/* Model curves first, so the bills draw on top of them. */}
        <Line
          data={oldCurve}
          dataKey="model"
          stroke={tokens.ink4}
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          activeDot={false}
          isAnimationActive={false}
          legendType="none"
        />
        <Line
          data={newCurve}
          dataKey="model"
          stroke={tokens.amber}
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          activeDot={false}
          isAnimationActive={false}
          legendType="none"
        />
        <Scatter
          data={points}
          dataKey="eff"
          isAnimationActive={false}
          shape={(props: { cx?: number; cy?: number; payload?: (typeof points)[number] }) => (
            <circle
              cx={props.cx}
              cy={props.cy}
              r={props.payload?.r ?? 4}
              fill={props.payload?.fill ?? tokens.acc}
            />
          )}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
