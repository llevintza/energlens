import { Outlet, useLocation, useParams } from 'react-router-dom'

import { usePlaces } from '../../api/hooks'
import { ErrorBoundary } from '../ErrorBoundary'
import { QueryError } from '../QueryError'
import { PlaceRail } from './PlaceRail'
import { TopBar } from './TopBar'

/**
 * The shell every screen but login renders inside: a 46px top bar over a 236px place
 * rail and the content column.
 */
export function AppShell() {
  const { pathname } = useLocation()
  const { placeId } = useParams()
  const places = usePlaces()

  const list = places.data ?? []
  /* The rail's selection follows the URL where there is one, and otherwise falls back
     to the first place so the rail is never rendered with nothing highlighted. */
  const activePlaceId = placeId ?? list[0]?.id ?? null

  /* An empty rail and a failed rail look identical to a user, and telling them their
     places are gone when the request merely failed is the whole of issue #8. Only a
     query that genuinely succeeded may report emptiness. */
  const isEmpty = places.isSuccess && list.length === 0

  return (
    <div className="shell">
      <TopBar activePlaceId={activePlaceId} />
      <div className="shell-body">
        <PlaceRail places={list} activePlaceId={activePlaceId} isEmpty={isEmpty} />
        <main className="content">
          {places.isError && (
            <QueryError
              error={places.error}
              onRetry={places.refetch}
              isRetrying={places.isFetching}
              title="Could not load your places"
            />
          )}
          {/* Inside the shell, so one page crashing leaves the bar and rail intact and
              the user still has somewhere to go. The `key` resets the boundary on
              navigation — otherwise a caught error would persist and blank out every
              page visited afterwards. */}
          <ErrorBoundary variant="inline" key={pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
