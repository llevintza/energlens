import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { ErrorBoundary } from './ErrorBoundary'

export function Layout() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  return (
    <>
      <nav className="topnav">
        <span className="brand">⚡ Energlens</span>
        <NavLink
          to="/"
          end
          className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}
        >
          Dashboard
        </NavLink>
        <NavLink
          to="/places"
          className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}
        >
          Places
        </NavLink>
        <span className="spacer" />
        <span className="who">{user?.email}</span>
        <button className="btn small" onClick={logout}>
          Log out
        </button>
      </nav>
      <main className="page-body">
        {/* Inside the shell, so one page crashing leaves the nav above intact
            and the user still has somewhere to go. The `key` resets the
            boundary on navigation — otherwise a caught error would persist and
            blank out every page visited afterwards. */}
        <ErrorBoundary variant="inline" key={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </>
  )
}
