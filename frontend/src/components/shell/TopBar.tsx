import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { useTheme } from '../../theme/ThemeProvider'
import { Segmented } from '../ui/Segmented'

interface Props {
  /** The place an "Add bill" action would land on. Null when there are none yet. */
  activePlaceId: string | null
}

export function TopBar({ activePlaceId }: Props) {
  const { user, logout } = useAuth()
  const { choice, resolved, setChoice } = useTheme()

  return (
    <header className="topbar">
      <Link to="/" className="wordmark">
        ⚡ Energlens
      </Link>
      <span className="spacer" />

      {/* Two segments here; SYSTEM is the third state and lives in 3g settings. Both
          write the same persisted choice. Under SYSTEM neither segment is "the
          choice", so the resolved theme is shown as active — the switch reflects what
          is on screen, and touching it commits to that value explicitly. */}
      <Segmented
        ariaLabel="Theme"
        monoLabels
        options={[
          { value: 'light', label: 'LIGHT' },
          { value: 'dark', label: 'DARK' },
        ]}
        value={choice === 'system' ? resolved : choice}
        onChange={setChoice}
      />

      {/* The handoff's slot here reads "Import bills", but PDF import has no API to
          call — it is deferred to #24 along with the whole 3e screen. Rather than
          ship a button that does nothing, this is the one bill path that does exist
          today: manual entry against the current place. #21 turns it into the
          Add-bill drawer; #24 can then widen it back to import. */}
      {activePlaceId && (
        <Link className="btn small" to={`/places/${activePlaceId}/manage`}>
          Add bill
        </Link>
      )}

      <span className="who">{user?.email}</span>
      <span className="avatar" aria-hidden="true">
        {user?.email?.[0] ?? '?'}
      </span>
      <button type="button" className="btn small" onClick={logout}>
        Sign out
      </button>
    </header>
  )
}
