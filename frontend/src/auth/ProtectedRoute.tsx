import { Navigate, Outlet } from 'react-router-dom'

import { QueryError } from '../components/QueryError'
import { useAuth } from './AuthContext'

export function ProtectedRoute() {
  const { user, loading, bootError, retryBoot } = useAuth()

  if (loading) return <div className="empty">Loading…</div>
  if (user) return <Outlet />

  // No user *and* a boot error means we never found out whether the session is
  // valid — the API did not answer. Redirecting to /login here would read as
  // "you have been signed out", which is a lie during a cold start, and the
  // login form would fail for the same reason. Say what happened and offer the
  // one action that can fix it. A rejected token is not this case: `api()`
  // clears it on a 401 and the redirect below is then correct.
  if (bootError) {
    return (
      <div className="page-body">
        <QueryError error={bootError} onRetry={retryBoot} />
      </div>
    )
  }

  return <Navigate to="/login" replace />
}
