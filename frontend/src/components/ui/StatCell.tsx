import type { ReactNode } from 'react'
import { DeltaChip } from './DeltaChip'

interface Props {
  /** 10px mono, 0.1em tracking, uppercase. */
  label: string
  /** Pre-formatted by lib/format — the cell does not know a currency from a kWh, and
   *  the decimal rules differ per row (€787 with none, €0.2886 with four). */
  value: ReactNode
  /** 21px on 2a's KPI row, 19px on 3f's comparison grid. */
  valueSize?: number
  delta?: number | null
  /** Null delta renders this instead, so a missing counterpart never reads as 0%. */
  deltaFallback?: string
  /** 11px --ink4 — what the delta is measured against. */
  note?: string
}

/** One figure with its label, change and comparison note. */
export function StatCell({
  label,
  value,
  valueSize = 21,
  delta,
  deltaFallback,
  note,
}: Props) {
  return (
    <div className="stat-cell">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ fontSize: valueSize }}>
        {value}
      </div>
      <div className="stat-foot">
        {delta !== undefined && <DeltaChip value={delta} fallback={deltaFallback ?? '—'} />}
        {note && <span className="stat-note">{note}</span>}
      </div>
    </div>
  )
}
