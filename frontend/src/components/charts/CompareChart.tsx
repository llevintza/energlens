import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { CompareData, FormatContext, MetricDescriptor } from '../../lib/compare'
import { useChartTokens } from './chartTheme'
import { makeCrosshairTooltip } from './CrosshairTooltip'

interface Props {
  data: CompareData
  metric: MetricDescriptor
  format: FormatContext
  height: number
  /** Miniatures drop every axis, grid line and tooltip — they are a shape, not a chart. */
  mini?: boolean
  /** Show only every nth x label. 2 for yoy, 3 for mom, per the handoff. */
  labelEvery?: number
}

/**
 * One renderer for all four comparison modes.
 *
 * `lib/compare.ts` decides what the series are and what colour they take; this decides
 * only how they are drawn. Keeping the split there is what stops eight metrics × four
 * modes turning into thirty-two chart components.
 */
export function CompareChart({
  data,
  metric,
  format,
  height,
  mini,
  labelEvery = 1,
}: Props) {
  const tokens = useChartTokens()

  const axis = {
    tick: { fill: tokens.ink4, fontSize: 10, fontFamily: 'var(--font-mono)' },
    tickLine: false,
    axisLine: { stroke: tokens.axis },
  }

  const xTicks = data.rows
    .map((row, i) => (i % labelEvery === 0 ? (row[data.xKey] as string) : null))
    .filter((v): v is string => v !== null)

  const Tip = makeCrosshairTooltip(tokens, (_payload, label) => {
    const row = data.rows.find((r) => r[data.xKey] === label)
    if (!row) return []
    return data.series.map((s) => ({
      label: s.label,
      color: s.color,
      value:
        typeof row[s.key] === 'number'
          ? metric.full(row[s.key] as number, format)
          : '—',
    }))
  })

  const margin = mini
    ? { top: 2, right: 2, left: 2, bottom: 2 }
    : { top: 12, right: 16, left: 0, bottom: 4 }

  if (data.chart === 'bar') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data.rows} margin={margin}>
          {!mini && <CartesianGrid vertical={false} stroke={tokens.grid} />}
          {!mini && (
            <XAxis dataKey={data.xKey} ticks={xTicks} interval={0} {...axis} />
          )}
          {!mini && (
            <YAxis
              width={56}
              domain={[data.domain.min, data.domain.max]}
              ticks={data.domain.ticks}
              tickFormatter={(v: number) => metric.tick(v, format)}
              {...axis}
              axisLine={false}
            />
          )}
          {mini && <XAxis dataKey={data.xKey} hide />}
          {mini && <YAxis hide domain={[data.domain.min, data.domain.max]} />}
          {data.zeroLine && <ReferenceLine y={0} stroke={tokens.axis} />}
          {!mini && <Tooltip content={<Tip />} cursor={{ fill: tokens.rule }} />}
          <Bar dataKey={data.series[0].key} isAnimationActive={false} maxBarSize={mini ? 6 : 26}>
            {data.cellColors?.map((color, i) => <Cell key={i} fill={color} />) ??
              data.rows.map((_, i) => <Cell key={i} fill={tokens.acc} />)}
            {data.valueLabels && (
              <LabelList
                dataKey={data.series[0].key}
                position="top"
                formatter={(v) => (typeof v === 'number' ? metric.big(v, format) : '')}
                style={{
                  fill: tokens.ink2,
                  fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                }}
              />
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  /* Line modes. The yoy band is an Area over a [lower, upper] tuple, which is how
     Recharts draws a range — a second filled Area would paint over the lines. */
  const rows = data.band
    ? data.rows.map((row) => ({
        ...row,
        __band:
          typeof row[data.band!.lowerKey] === 'number' &&
          typeof row[data.band!.upperKey] === 'number'
            ? [row[data.band!.lowerKey] as number, row[data.band!.upperKey] as number]
            : null,
      }))
    : data.rows

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={margin}>
        {!mini && <CartesianGrid vertical={false} stroke={tokens.grid} />}
        {!mini && <XAxis dataKey={data.xKey} ticks={xTicks} interval={0} {...axis} />}
        {!mini && (
          <YAxis
            width={56}
            domain={[data.domain.min, data.domain.max]}
            ticks={data.domain.ticks}
            tickFormatter={(v: number) => metric.tick(v, format)}
            {...axis}
            axisLine={false}
          />
        )}
        {mini && <XAxis dataKey={data.xKey} hide />}
        {mini && <YAxis hide domain={[data.domain.min, data.domain.max]} />}
        {data.band && (
          <Area
            dataKey="__band"
            fill={data.band.fill}
            stroke="none"
            isAnimationActive={false}
            activeDot={false}
            legendType="none"
          />
        )}
        {!mini && <Tooltip content={<Tip />} cursor={{ stroke: tokens.axis }} />}
        {data.series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            stroke={s.color}
            strokeWidth={s.strokeWidth}
            strokeDasharray={s.dashed ? '4 3' : undefined}
            dot={s.dotRadius === false ? false : { r: s.dotRadius ?? 2.4, fill: s.color, strokeWidth: 0 }}
            activeDot={mini ? false : { r: 4 }}
            /* Never bridge a gap: a partial year must stop where the data stops. */
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
