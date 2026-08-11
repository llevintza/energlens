import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from './AuthContext'

export function OAuthCallbackPage() {
  const { loginWithToken } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const params = new URLSearchParams(window.location.hash.slice(1))
    const token = params.get('access_token')
    // Scrub the token from the address bar/history before anything else.
    history.replaceState(null, '', window.location.pathname)

    if (!token) {
      setError('No token in callback URL')
      return
    }
    loginWithToken(token)
      .then(() => navigate('/', { replace: true }))
      .catch(() => setError('Login failed — please try again'))
  }, [loginWithToken, navigate])

  if (error) {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>Sign-in problem</h1>
          <p className="auth-sub">{error}</p>
          <Link to="/login">Back to login</Link>
        </div>
      </div>
    )
  }
  return <div className="empty">Signing you in…</div>
}
