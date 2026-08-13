import type { ReactNode } from 'react'
import { QueryError } from '../QueryError'

export type ChartStatus = 'pending' | 'error' | 'empty' | 'ready'

interface Props {
  /** The design height for this chart. Held in every state so nothing reflows. */
  height: number
  title?: string
  subtitle?: string
  /** Right-aligned controls on the title line. */
  actions?: ReactNode
  status: ChartStatus
  error?: unknown
  onRetry?: () => void
  isRetrying?: boolean
  emptyMessage?: string
  emptyAction?: ReactNode
  children: ReactNode
}

/**
 * The four states every chart in the redesign shares, in one place.
 *
 * `docs/design/README.md` imposes these on every chart across five separate issues, so
 * they are a component rather than a convention: one implementation, or five
 * interpretations plus a round of review comments on each.
 *
 * The ordering matters and is the fix path for issue #8: **error is checked before
 * empty**. A failed request that falls through to an empty state tells the user their
 * data is gone, which is both alarming and false.
 */
export function ChartFrame({
  height,
  title,
  subtitle,
  actions,
  status,
  error,
  onRetry,
  isRetrying,
  emptyMessage = 'No bills in this range yet.',
  emptyAction,
  children,
}: Props) {
  return (
    <section className="chart-frame">
      {(title || subtitle || actions) && (
        <div className="chart-frame-head">
          {title && <h2 className="chart-frame-title">{title}</h2>}
          {subtitle && <p className="chart-frame-sub">{subtitle}</p>}
          {actions}
        </div>
      )}

      {/* Above the panel, inline, never a modal — the message belongs beside the thing
          that failed, and the chart's space is held so the page does not jump. */}
      {status === 'error' && (
        <QueryError
          error={error}
          onRetry={onRetry}
          isRetrying={isRetrying}
          compact
          title={title ? `Could not load ${title.toLowerCase()}` : undefined}
        />
      )}

      {status === 'pending' && <div className="skeleton" style={{ height }} />}

      {status === 'empty' && (
        <div className="empty-panel" style={{ height }}>
          <span>{emptyMessage}</span>
          {emptyAction}
        </div>
      )}

      {status === 'ready' && <div className="chart-frame-body">{children}</div>}
    </section>
  )
}

/** Resolve a TanStack Query into a chart status, with the error-before-empty ordering
 *  applied once so no caller has to remember it. */
export function chartStatus(
  query: { isError: boolean; isPending: boolean },
  hasData: boolean,
): ChartStatus {
  if (query.isError) return 'error'
  if (query.isPending) return 'pending'
  return hasData ? 'ready' : 'empty'
}
