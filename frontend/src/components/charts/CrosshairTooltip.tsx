import type { CSSProperties } from 'react'

import { fmtSignedPct } from '../../lib/format'
import type { ChartTokens } from './chartTheme'

export interface CrosshairRow {
  label: string
  color: string
  /** Already formatted — the tooltip does not know a currency from a kWh. */
  value: string
  /** Change against the same month last year. Null means no counterpart exists, which
   *  renders as nothing rather than as 0%. */
  yoy?: number | null
}

/** Structural, rather than Recharts' generic `TooltipContentProps`. Those generics are
 *  inferred from each chart's data and do not unify across a ComposedChart with a bar
 *  and two lines, so naming the three fields actually read here keeps the component
 *  usable from every chart in the epic. Recharts injects them when it clones the
 *  element passed to `content`. */
export interface CrosshairProps {
  active?: boolean
  payload?: readonly unknown[]
  label?: unknown
}

/**
 * One shared crosshair tooltip per chart, listing every series at the hovered month
 * with its value and year-on-year delta.
 *
 * Deliberately not one tooltip per series: the question a reader has at a given month
 * is "what happened here", and answering it three times in three boxes makes them do
 * the joining themselves.
 */
export function makeCrosshairTooltip(
  tokens: ChartTokens,
  buildRows: (payload: readonly unknown[], label: string) => CrosshairRow[],
) {
  const box: CSSProperties = {
    background: tokens.panel,
    border: `1px solid ${tokens.rule}`,
    borderRadius: 8,
    padding: '8px 10px',
    fontSize: 12.5,
    /* Tinted from the accent rather than plain black: a black shadow is invisible on
       the dark panel and muddy on the light one. */
    boxShadow: `0 2px 10px rgba(${tokens.accRgb}, 0.14)`,
  }

  return function CrosshairTooltip({ active, payload, label }: CrosshairProps) {
    if (!active || !payload || payload.length === 0) return null
    const rows = buildRows(payload, String(label ?? ''))
    if (rows.length === 0) return null

    return (
      <div style={box} role="tooltip">
        <div
          style={{
            color: tokens.ink4,
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.08em',
            marginBottom: 5,
          }}
        >
          {String(label ?? '').toUpperCase()}
        </div>
        {rows.map((row) => (
          <div
            key={row.label}
            style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 3 }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: row.color,
                flex: 'none',
              }}
            />
            <span style={{ color: tokens.ink2, flex: 1 }}>{row.label}</span>
            <span
              style={{
                color: tokens.ink,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {row.value}
            </span>
            {row.yoy !== undefined && row.yoy !== null && (
              <span
                style={{
                  color: Math.abs(row.yoy) < 0.05 ? tokens.ink4 : row.yoy > 0 ? tokens.up : tokens.down,
                  fontFamily: 'var(--font-mono)',
                  fontVariantNumeric: 'tabular-nums',
                  fontSize: 11,
                }}
              >
                {fmtSignedPct(row.yoy)}
              </span>
            )}
          </div>
        ))}
      </div>
    )
  }
}
