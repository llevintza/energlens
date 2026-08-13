import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { SeriesPoint } from '../../api/types'
import { fmtPeriodTick } from '../../lib/format'
import { makeTooltip } from './ChartTooltip'
import { monthRows } from './fill'
import { useChartTokens } from './chartTheme'

interface Props {
  points: SeriesPoint[]
  kind: 'bar' | 'line'
  color?: string
  formatValue: (value: number) => string
  /** true when periods are per-bill dates rather than months */
  billGranularity?: boolean
  height?: number
}

export function SeriesChart({
  points,
  kind,
  color,
  formatValue,
  billGranularity = false,
  height = 240,
}: Props) {
  const tokens = useChartTokens()
  const stroke = color ?? tokens.series[0]
  const data = billGranularity
    ? points.map((p) => ({ period: p.period, value: p.value }))
    : monthRows(points)

  if (points.length === 0) {
    return <div className="empty">No data yet for this range</div>
  }

  const axisProps = {
    tick: { fill: tokens.ink4, fontSize: 12 },
    tickLine: false,
    axisLine: { stroke: tokens.axis },
  }
  const tooltip = (
    <Tooltip
      content={makeTooltip(tokens, formatValue)}
      cursor={
        kind === 'bar'
          ? { fill: tokens.rule }
          : { stroke: tokens.axis, strokeWidth: 1 }
      }
    />
  )

  return (
    <ResponsiveContainer width="100%" height={height}>
      {kind === 'bar' ? (
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={tokens.grid} />
          <XAxis dataKey="period" tickFormatter={fmtPeriodTick} {...axisProps} />
          <YAxis width={44} {...axisProps} axisLine={false} />
          {tooltip}
          <Bar
            dataKey="value"
            fill={stroke}
            radius={[4, 4, 0, 0]}
            maxBarSize={26}
          />
        </BarChart>
      ) : (
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={tokens.grid} />
          <XAxis dataKey="period" tickFormatter={fmtPeriodTick} {...axisProps} />
          <YAxis width={44} {...axisProps} axisLine={false} />
          {tooltip}
          <Line
            dataKey="value"
            stroke={stroke}
            strokeWidth={2}
            connectNulls={false}
            dot={{ r: 3, fill: stroke, stroke: tokens.panel, strokeWidth: 2 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      )}
    </ResponsiveContainer>
  )
}
