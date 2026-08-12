import { describeError } from '../lib/errors'

interface Props {
  error: unknown
  /** Usually a query's `refetch`. Omitted when there is nothing to retry. */
  onRetry?: () => void
  isRetrying?: boolean
  /** Tighter variant for use inside a card that already has a heading. */
  compact?: boolean
  /** Overrides the mapped title — for a 404 the caller can name the thing. */
  title?: string
}

/**
 * The single place failure copy is written.
 *
 * Rendered inline where the data would have been, so a failed request can
 * never be mistaken for an empty account. Pages decide *where* it goes; what
 * it says comes from `describeError` so the wording cannot drift between them.
 */
export function QueryError({
  error,
  onRetry,
  isRetrying,
  compact,
  title,
}: Props) {
  const { title: mappedTitle, detail, canRetry } = describeError(error)

  return (
    <div className={`query-error${compact ? ' compact' : ''}`} role="alert">
      <div className="query-error-title">{title ?? mappedTitle}</div>
      <div className="query-error-detail">{detail}</div>
      {canRetry && onRetry && (
        <button className="btn small" onClick={onRetry} disabled={isRetrying}>
          {isRetrying ? 'Retrying…' : 'Retry'}
        </button>
      )}
    </div>
  )
}
