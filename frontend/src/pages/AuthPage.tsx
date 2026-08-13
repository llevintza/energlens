import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Sparkline } from '../components/charts/Sparkline'
import { OAuthButtons, hasOAuthProviders } from '../components/OAuthButtons'
import { Segmented } from '../components/ui/Segmented'
import { fmtSignedPct } from '../lib/format'
import { MAIN_RESIDENCE, seedBills } from '../lib/fixtures'
import { effectivePriceSeries, parseBills, pctChange } from '../lib/metrics'
import { useTheme } from '../theme/ThemeProvider'

type Mode = 'signin' | 'register'

interface FormValues {
  email: string
  password: string
}

/**
 * 3a — the only screen without the shell.
 *
 * `/login` and `/register` both mount this; the path sets the initial mode and the
 * toggle switches without navigating. Keeping both routes matters because they are
 * linked from elsewhere and people bookmark them.
 */
export function AuthPage() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { user, login, register: registerAccount } = useAuth()
  const { choice, resolved, setChoice } = useTheme()

  const [mode, setMode] = useState<Mode>(
    pathname === '/register' ? 'register' : 'signin',
  )
  const [failure, setFailure] = useState<string | null>(null)

  const form = useForm<FormValues>({ defaultValues: { email: '', password: '' } })
  const { formState } = form

  /* Keep the URL honest when the toggle moves, without a navigation — the form state
     and anything typed into it survive. */
  useEffect(() => {
    const target = mode === 'register' ? '/register' : '/login'
    if (pathname !== target) navigate(target, { replace: true })
  }, [mode, pathname, navigate])

  /* The demo account's real price line, generated rather than fetched: it has to render
     before anyone is authenticated, and these are computed numbers, so shipping them in
     the bundle cannot leak anything. */
  const { spark, change } = useMemo(() => {
    const values = effectivePriceSeries(parseBills(seedBills(MAIN_RESIDENCE)))
    return {
      spark: values,
      change: values.length > 1 ? pctChange(values[0], values[values.length - 1]) : null,
    }
  }, [])

  if (user) return <Navigate to="/" replace />

  const onSubmit = form.handleSubmit(async (values) => {
    setFailure(null)
    try {
      if (mode === 'register') {
        await registerAccount(values.email, values.password)
      } else {
        await login(values.email, values.password)
      }
      navigate('/', { replace: true })
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        setFailure(
          mode === 'register'
            ? 'An account with this email already exists.'
            : 'Wrong email or password.',
        )
      } else {
        setFailure(
          mode === 'register'
            ? 'Could not create the account — is the API running?'
            : 'Could not sign in — is the API running?',
        )
      }
    }
  })

  return (
    <div className="auth-page">
      <div className="auth-split">
        <aside className="auth-aside">
          <div className="auth-wordmark">⚡ Energlens</div>
          <div className="auth-tagline">Electricity, over time</div>
          <div style={{ flex: 1, minHeight: 24 }} />
          <p className="auth-pitch">
            Your provider shows you one bill at a time. This shows you the line.
          </p>
          <div style={{ marginTop: 20 }}>
            <Sparkline
              values={spark}
              width={300}
              height={90}
              strokeWidth={2}
              label="All-in price per kWh over two years"
            />
          </div>
          <div className="auth-spark-caption">
            All-in price per kWh, Aug 2024 to Jul 2026 —{' '}
            {change === null ? 'over two years' : `up ${fmtSignedPct(change).replace('+', '')}`}
          </div>
        </aside>

        <main className="auth-main">
          <div className="auth-main-head">
            <Segmented
              ariaLabel="Sign in or create an account"
              options={[
                { value: 'signin', label: 'Sign in' },
                { value: 'register', label: 'Create account' },
              ]}
              value={mode}
              onChange={(next) => {
                setMode(next)
                setFailure(null)
              }}
            />
            <span style={{ flex: 1 }} />
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
          </div>

          <form onSubmit={onSubmit} noValidate>
            <div className="auth-field">
              <label htmlFor="auth-email">Email</label>
              <input
                id="auth-email"
                type="email"
                autoComplete="email"
                {...form.register('email', { required: 'Email is required' })}
              />
              {formState.errors.email && (
                <span className="err">{formState.errors.email.message}</span>
              )}
            </div>

            <div className="auth-field">
              <label htmlFor="auth-password">Password</label>
              <input
                id="auth-password"
                type="password"
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                {...form.register('password', {
                  required: 'Password is required',
                  minLength:
                    mode === 'register'
                      ? { value: 8, message: 'At least 8 characters' }
                      : undefined,
                })}
              />
              {formState.errors.password && (
                <span className="err">{formState.errors.password.message}</span>
              )}
            </div>

            {failure && (
              <p className="auth-error" role="alert">
                {failure}
              </p>
            )}

            <button type="submit" className="auth-submit" disabled={formState.isSubmitting}>
              {formState.isSubmitting
                ? 'Working…'
                : mode === 'register'
                  ? 'Create account'
                  : 'Sign in'}
            </button>
          </form>

          {/* The divider belongs to the buttons. With no provider configured — which is
              the live site's default — both disappear together rather than leaving a
              rule with nothing under it. */}
          {hasOAuthProviders && (
            <>
              <div className="auth-or">OR</div>
              <OAuthButtons />
            </>
          )}

          <div style={{ flex: 1 }} />
          <p className="auth-reassurance">
            Bills stay in your account. Nothing is shared with a provider.
          </p>
        </main>
      </div>
    </div>
  )
}
