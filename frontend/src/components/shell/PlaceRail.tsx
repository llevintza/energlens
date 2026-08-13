import { Link, useNavigate } from 'react-router-dom'
import { useBills } from '../../api/hooks'
import type { Place } from '../../api/types'
import { effectivePriceSeries, parseBills, pctChange } from '../../lib/metrics'
import { Sparkline } from '../charts/Sparkline'
import { DeltaChip } from '../ui/DeltaChip'

interface Props {
  places: Place[]
  activePlaceId: string | null
  /** True only when the query genuinely succeeded and returned nothing. A failed
   *  request must never reach here — see QueryError in the content column. */
  isEmpty: boolean
}

/** The active row's price trend. Only the active place is fetched: the design shows
 *  one sparkline, and `usePlaces` + one bills request per place would be a lot of
 *  round trips for decoration. 3c needs one per row and fans out deliberately. */
function ActiveTrend({ placeId }: { placeId: string }) {
  const bills = useBills(placeId)
  if (!bills.data || bills.data.length < 2) return null
  const series = effectivePriceSeries(parseBills(bills.data))
  if (series.length < 2) return null
  const change = pctChange(series[0], series[series.length - 1])
  return (
    <span className="rail-meta">
      <Sparkline
        values={series}
        width={128}
        height={26}
        label="All-in price per kWh over time"
      />
      <DeltaChip value={change} />
    </span>
  )
}

export function PlaceRail({ places, activePlaceId, isEmpty }: Props) {
  const navigate = useNavigate()

  return (
    <nav className="rail" aria-label="Places">
      <div className="rail-label">PLACES</div>

      {/* Below 900px the rail is a place picker rather than a list. Both are rendered
          and CSS chooses, so switching viewport never loses the selection. */}
      <select
        className="rail-picker"
        aria-label="Select a place"
        value={activePlaceId ?? ''}
        onChange={(event) => navigate(`/places/${event.target.value}`)}
      >
        {!activePlaceId && <option value="">Choose a place…</option>}
        {places.map((place) => (
          <option key={place.id} value={place.id}>
            {place.name}
          </option>
        ))}
      </select>

      <div className="rail-rows">
        {isEmpty ? (
          /* 3b keeps the rail rather than letting it vanish — a new user should still
             see where places are going to live. */
          <div className="rail-empty">Nothing here yet</div>
        ) : (
          places.map((place) => {
            const active = place.id === activePlaceId
            return (
              <Link
                key={place.id}
                to={`/places/${place.id}`}
                className={`rail-row${active ? ' active' : ''}`}
                aria-current={active ? 'page' : undefined}
                title={place.name}
              >
                <span className="rail-name">{place.name}</span>
                {active && <ActiveTrend placeId={place.id} />}
              </Link>
            )
          })
        )}
      </div>

      <div className="rail-divider" />
      <Link className="rail-link" to="/places">
        + <span className="label-long">Add place</span>
      </Link>
      <Link className="rail-link muted" to="/places">
        <span className="label-long">Manage places</span>
        <span className="label-short" aria-hidden="true">
          ⚙
        </span>
      </Link>
    </nav>
  )
}
