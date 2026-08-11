import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function Layout() {
  const { user, logout } = useAuth()
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
        <Outlet />
      </main>
    </>
  )
}
