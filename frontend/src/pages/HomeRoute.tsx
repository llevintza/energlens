import { Navigate } from 'react-router-dom'

import { usePlaces } from '../api/hooks'
import { QueryError } from '../components/QueryError'
import { FirstRunPage } from './FirstRunPage'

/**
 * `/` is not a screen in the redesign — the dashboard belongs to a place. This resolves
 * it to the first one.
 *
 * The ordering here is the #8 bug in miniature: a failed places query must surface as an
 * error, never as "you have no places yet". Only a query that genuinely succeeded and
 * returned nothing may fall through to the first-run state, which #20 builds.
 */
export function HomeRoute() {
  const places = usePlaces()

  if (places.isError) {
    return (
      <QueryError
        error={places.error}
        onRetry={places.refetch}
        isRetrying={places.isFetching}
        title="Could not load your places"
      />
    )
  }

  if (places.isPending) return <div className="skeleton" style={{ height: 236 }} />

  const first = places.data?.[0]
  /* Only a query that genuinely succeeded and came back empty reaches first run. */
  if (!first) return <FirstRunPage />

  return <Navigate to={`/places/${first.id}`} replace />
}
