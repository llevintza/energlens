import { Line, LineChart, YAxis } from 'recharts'
import { useChartTokens } from './chartTheme'

interface Props {
  values: number[]
  width: number
  height: number
  /** Defaults to `--acc`. */
  color?: string
  strokeWidth?: number
  /** Announced to screen readers, since the line itself says nothing to them. */
  label?: string
}

/**
 * Chart 9 — a line in a fixed-size box. No axes, no grid, no tooltip.
 *
 * The domain is pinned to the data's own range: the default `[0, dataMax]` would flatten
 * a price series that only ever moves between €0.22 and €0.29 into a straight line,
 * which is the opposite of what a sparkline is for.
 */
export function Sparkline({
  values,
  width,
  height,
  color,
  strokeWidth = 1.5,
  label,
}: Props) {
  const tokens = useChartTokens()
  if (values.length < 2) {
    /* One point is not a trend. Hold the space so the row does not reflow when a
       second bill arrives. */
    return <div style={{ width, height }} aria-hidden="true" />
  }
  const data = values.map((v, i) => ({ i, v }))
  return (
    <div role={label ? 'img' : undefined} aria-label={label}>
      <LineChart
        width={width}
        height={height}
        data={data}
        margin={{ top: 2, right: 1, bottom: 2, left: 1 }}
      >
        <YAxis hide domain={['dataMin', 'dataMax']} />
        <Line
          type="linear"
          dataKey="v"
          stroke={color ?? tokens.acc}
          strokeWidth={strokeWidth}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </div>
  )
}
