import { Link, useLocation } from 'react-router-dom'

export function NotFoundPage() {
  const { pathname } = useLocation()

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>Page not found</h1>
        <p className="auth-sub">
          Nothing is routed at <code>{pathname}</code>.
        </p>
        <p className="auth-alt">
          <Link to="/">Go to the dashboard</Link>
        </p>
      </div>
    </div>
  )
}
