import type { CSSProperties } from 'react'
import type { TooltipContentProps } from 'recharts'

import { fmtPeriod } from '../../lib/format'
import type { ChartTokens } from './tokens'

export function makeTooltip(
  tokens: ChartTokens,
  formatValue: (value: number) => string,
) {
  const box: CSSProperties = {
    background: tokens.surface,
    border: `1px solid ${tokens.border}`,
    borderRadius: 8,
    padding: '8px 10px',
    fontSize: 13,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
  }
  return function ChartTooltip({ active, label, payload }: TooltipContentProps) {
    if (!active || !payload || payload.length === 0) return null
    const rows = payload.filter(
      (p) => p.value !== null && p.value !== undefined,
    )
    if (rows.length === 0) return null
    return (
      <div style={box}>
        <div style={{ color: tokens.inkSecondary, marginBottom: 2 }}>
          {fmtPeriod(String(label))}
        </div>
        {rows.map((row, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {rows.length > 1 && (
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 4,
                  background: row.color,
                  display: 'inline-block',
                }}
              />
            )}
            {rows.length > 1 && (
              <span style={{ color: tokens.inkSecondary }}>{row.name}</span>
            )}
            <span style={{ color: tokens.ink, fontWeight: 600 }}>
              {formatValue(Number(row.value))}
            </span>
          </div>
        ))}
      </div>
    )
  }
}
