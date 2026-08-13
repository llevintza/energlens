import { useQueries } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { useCreatePlace, useDeletePlace, usePlaces, useUpdatePlace } from '../api/hooks'
import type { Bill, Place, PlaceInput } from '../api/types'
import { Sparkline } from '../components/charts/Sparkline'
import { PlaceForm } from '../components/PlaceForm'
import { QueryError } from '../components/QueryError'
import { Drawer } from '../components/ui/Drawer'
import { DeltaChip } from '../components/ui/DeltaChip'
import { fmtCurrency, fmtDate } from '../lib/format'
import { effectivePriceSeries, parseBills, pctChange } from '../lib/metrics'

/** One row's derived figures. Kept beside the row so a failed fetch degrades that row
 *  rather than the table. */
function PlaceRow({
  place,
  bills,
  onEdit,
  onDelete,
}: {
  place: Place
  bills: { data?: Bill[]; isError: boolean; isPending: boolean }
  onEdit: () => void
  onDelete: () => void
}) {
  const parsed = parseBills(bills.data ?? [])
  const spark = effectivePriceSeries(parsed)
  const last = parsed[parsed.length - 1]
  const allIn = last && last.consumption ? last.total / last.consumption : null
  const trend = spark.length > 1 ? pctChange(spark[0], spark[spark.length - 1]) : null

  return (
    <tr>
      <td>
        <Link to={`/places/${place.id}`} className="places-name">
          {place.name}
        </Link>
        <div className="places-addr">
          {place.address_line1}
          <br />
          {[place.postal_code, place.city].filter(Boolean).join(' ')}
        </div>
      </td>
      <td className="num">{place.currency_code}</td>
      <td className="num">{bills.isPending ? '…' : (bills.data?.length ?? '—')}</td>
      <td className="num">
        {bills.isError ? '—' : fmtCurrency(last?.total, place.currency_code, 2)}
      </td>
      <td className="num">
        {bills.isError ? '—' : fmtCurrency(allIn, place.currency_code, 4)}
      </td>
      <td className="places-trend">
        {bills.isError ? (
          /* One row's failure is one row's failure. The table, and every other place in
             it, stays readable. */
          <span className="places-row-error">Could not load bills</span>
        ) : spark.length > 1 ? (
          <>
            <Sparkline values={spark} width={108} height={26} label={`${place.name} price trend`} />
            <DeltaChip value={trend} />
            <span className="places-span">
              {parsed[0] && last
                ? `${fmtDate(parsed[0].periodStart.toISOString().slice(0, 10))} – ${fmtDate(last.periodEnd.toISOString().slice(0, 10))}`
                : ''}
            </span>
          </>
        ) : (
          <span className="places-span">Not enough bills yet</span>
        )}
      </td>
      <td className="places-actions">
        <Link className="btn small" to={`/places/${place.id}`}>
          Open
        </Link>
        <button type="button" className="btn small" onClick={onEdit}>
          Edit
        </button>
        <button type="button" className="btn small danger" onClick={onDelete}>
          Delete
        </button>
      </td>
    </tr>
  )
}

/**
 * 3c — places as a table, not cards.
 *
 * Cards make the one thing worth having several places for impossible: comparing them
 * row to row. The per-row sparkline is the one place a fan-out is justified, because
 * this is the view the user asked for — `useQueries` over `/bills`, one request per
 * place, each degrading independently.
 */
export function PlacesPage() {
  const places = usePlaces()
  const createPlace = useCreatePlace()
  const deletePlace = useDeletePlace()

  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Place | null>(null)

  const list = places.data ?? []
  const billQueries = useQueries({
    queries: list.map((place) => ({
      queryKey: ['bills', place.id],
      queryFn: () => api<Bill[]>(`/places/${place.id}/bills`),
      staleTime: 30_000,
    })),
  })

  const updatePlace = useUpdatePlace(editing?.id ?? '')

  return (
    <>
      <div className="places-head">
        <h1>Places</h1>
        <button type="button" className="btn primary" onClick={() => setAdding(true)}>
          Add place
        </button>
      </div>

      {deletePlace.isError && (
        <QueryError
          error={deletePlace.error}
          onRetry={() =>
            deletePlace.variables && deletePlace.mutate(deletePlace.variables)
          }
          isRetrying={deletePlace.isPending}
          title="Could not delete that place"
        />
      )}

      {places.isError ? (
        <QueryError
          error={places.error}
          onRetry={places.refetch}
          isRetrying={places.isFetching}
          title="Could not load your places"
        />
      ) : places.isPending ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : list.length === 0 ? (
        <div className="empty-panel" style={{ height: 160 }}>
          <span>No places yet.</span>
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            Add your first place
          </button>
        </div>
      ) : (
        <>
          <table className="places">
            <thead>
              <tr>
                <th>Place</th>
                <th className="num">Currency</th>
                <th className="num">Bills</th>
                <th className="num">Last bill</th>
                <th className="num">All-in /kWh</th>
                <th>Price trend</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((place, i) => (
                <PlaceRow
                  key={place.id}
                  place={place}
                  bills={billQueries[i] ?? { isError: false, isPending: true }}
                  onEdit={() => setEditing(place)}
                  onDelete={() => {
                    if (
                      window.confirm(
                        `Delete ${place.name}? Its bills go with it, and that cannot be undone.`,
                      )
                    ) {
                      deletePlace.mutate(place.id)
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
          {/* Load-bearing, not decoration: it is the rule that stops the app inventing
              an exchange rate, and it is why the compare views index to the first month
              rather than summing. */}
          <p className="places-footnote">
            Totals are never added across places — {currencyList(list)} stay separate.
          </p>
        </>
      )}

      <Drawer open={adding} onClose={() => setAdding(false)} title="Add place">
        <PlaceForm
          submitLabel="Add place"
          onCancel={() => setAdding(false)}
          onSubmit={async (values: PlaceInput) => {
            await createPlace.mutateAsync(values)
            setAdding(false)
          }}
        />
      </Drawer>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={`Edit ${editing?.name ?? 'place'}`}
      >
        {editing && (
          <PlaceForm
            initial={editing}
            submitLabel="Save changes"
            billCount={billQueries[list.findIndex((p) => p.id === editing.id)]?.data?.length}
            onCancel={() => setEditing(null)}
            onSubmit={async (values: PlaceInput) => {
              await updatePlace.mutateAsync(values)
              setEditing(null)
            }}
          />
        )}
      </Drawer>
    </>
  )
}

function currencyList(places: Place[]): string {
  const codes = [...new Set(places.map((p) => p.currency_code))]
  if (codes.length <= 1) return codes[0] ?? 'currencies'
  if (codes.length === 2) return `${codes[0]} and ${codes[1]}`
  return `${codes.slice(0, -1).join(', ')} and ${codes[codes.length - 1]}`
}
