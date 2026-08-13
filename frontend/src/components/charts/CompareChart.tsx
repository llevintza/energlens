import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { CompareSeries } from '../../api/types'
import { fmtPeriodTick } from '../../lib/format'
import { makeTooltip } from './ChartTooltip'
import { compareRows } from './fill'
import { useChartTokens } from './chartTheme'

interface Props {
  series: CompareSeries[]
  /** stable slot index per place id (position in the full place list) */
  colorIndex: (placeId: string) => number
  labelFor?: (s: CompareSeries) => string
  formatValue: (value: number) => string
  height?: number
}

export function CompareChart({
  series,
  colorIndex,
  labelFor,
  formatValue,
  height = 260,
}: Props) {
  const tokens = useChartTokens()
  const data = compareRows(series)

  if (data.length === 0) {
    return <div className="empty">No data yet for this range</div>
  }

  const axisProps = {
    tick: { fill: tokens.ink4, fontSize: 12 },
    tickLine: false,
    axisLine: { stroke: tokens.axis },
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={tokens.grid} />
        <XAxis dataKey="period" tickFormatter={fmtPeriodTick} {...axisProps} />
        <YAxis width={44} {...axisProps} axisLine={false} />
        <Tooltip
          content={makeTooltip(tokens, formatValue)}
          cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 13, color: tokens.ink2 }}
        />
        {series.map((s) => {
          const color =
            tokens.series[colorIndex(s.place_id)] ?? tokens.series[0]
          return (
            <Line
              key={s.place_id}
              dataKey={s.place_id}
              name={labelFor ? labelFor(s) : s.place_name}
              stroke={color}
              strokeWidth={2}
              connectNulls={false}
              dot={{ r: 3, fill: color, stroke: tokens.panel, strokeWidth: 2 }}
              activeDot={{ r: 5 }}
            />
          )
        })}
      </LineChart>
    </ResponsiveContainer>
  )
}
