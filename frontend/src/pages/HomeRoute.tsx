import { Navigate } from 'react-router-dom'

import { usePlaces } from '../api/hooks'
import { QueryError } from '../components/QueryError'

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
  if (!first) {
    /* Stands in until #20 replaces it with the designed first-run screen. */
    return (
      <div className="empty-panel" style={{ height: 200 }}>
        <span>No places yet. Add one to start tracking bills.</span>
        <Navigate to="/places" replace />
      </div>
    )
  }

  return <Navigate to={`/places/${first.id}`} replace />
}
