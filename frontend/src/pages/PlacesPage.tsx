import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useCreatePlace, useDeletePlace, usePlaces } from '../api/hooks'
import type { Place } from '../api/types'
import { PlaceForm } from '../components/PlaceForm'
import { QueryError } from '../components/QueryError'

function formatAddress(place: Place): string {
  return [
    place.address_line1,
    place.address_line2,
    `${place.postal_code} ${place.city}`,
    [place.region, place.country_code].filter(Boolean).join(', '),
  ]
    .filter(Boolean)
    .join('\n')
}

export function PlacesPage() {
  const {
    data: places,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = usePlaces()
  const createPlace = useCreatePlace()
  const deletePlace = useDeletePlace()
  const [adding, setAdding] = useState(false)

  return (
    <>
      <div className="page-title">
        <h1>Places</h1>
        <span className="sub">the properties whose bills you track</span>
        <span style={{ flex: 1 }} />
        {!adding && (
          <button className="btn primary" onClick={() => setAdding(true)}>
            Add place
          </button>
        )}
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>New place</h2>
          <PlaceForm
            onSubmit={async (data) => {
              await createPlace.mutateAsync(data)
              setAdding(false)
            }}
            onCancel={() => setAdding(false)}
            submitLabel="Create place"
          />
        </div>
      )}

      {/* Surfaced here rather than swallowed: `.mutate` has no caller waiting
          on it, so without this a failed delete leaves the row in place and
          says nothing at all. */}
      {deletePlace.isError && (
        <div style={{ marginBottom: 16 }}>
          <QueryError
            error={deletePlace.error}
            title="Could not delete that place"
            // A genuine retry, not a dismiss: `variables` still holds the id
            // the failed call was given.
            onRetry={() => deletePlace.mutate(deletePlace.variables)}
            isRetrying={deletePlace.isPending}
          />
        </div>
      )}

      {isLoading ? (
        <div className="empty">Loading…</div>
      ) : isError ? (
        // Before the empty-state branch, never after: `places` is undefined on
        // failure too, so the order is what stops "we could not load this"
        // from being reported as "you have no places".
        <QueryError error={error} onRetry={refetch} isRetrying={isFetching} />
      ) : !places || places.length === 0 ? (
        !adding && (
          <div className="card empty">
            No places yet. Add your first place to start tracking bills.
          </div>
        )
      ) : (
        <div className="place-grid">
          {places.map((place) => (
            <div key={place.id} className="card place-card">
              <h3>
                <Link to={`/places/${place.id}`}>{place.name}</Link>
              </h3>
              <div className="addr">{formatAddress(place)}</div>
              <div className="meta">Billed in {place.currency_code}</div>
              <div className="row-actions">
                <Link to={`/places/${place.id}`} className="btn small">
                  Open
                </Link>
                <button
                  className="btn small danger"
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete "${place.name}" and all of its bills? This cannot be undone.`,
                      )
                    ) {
                      deletePlace.mutate(place.id)
                    }
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
