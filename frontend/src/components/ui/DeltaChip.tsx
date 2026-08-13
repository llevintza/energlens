import { fmtSignedPct } from '../../lib/format'

interface Props {
  /** Percentage change. Null when there is no counterpart to compare against. */
  value: number | null | undefined
  /** Shown instead of a delta when `value` is null. "—" by default. */
  fallback?: string
  className?: string
}

/**
 * A signed percentage, coloured by direction.
 *
 * `--up` and `--down` are directions, not verdicts — the palette does not know whether
 * a rise is good news, and for a bill it usually is not. Anything that rounds to 0.0%
 * is `--ink4`: if it prints as flat it should read as flat, rather than being tinted by
 * a sign the reader cannot see.
 */
export function DeltaChip({ value, fallback = '—', className }: Props) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return <span className={`delta flat${className ? ` ${className}` : ''}`}>{fallback}</span>
  }
  const direction = Math.abs(value) < 0.05 ? 'flat' : value > 0 ? 'up' : 'down'
  return (
    <span className={`delta ${direction}${className ? ` ${className}` : ''}`}>
      {fmtSignedPct(value)}
    </span>
  )
}
