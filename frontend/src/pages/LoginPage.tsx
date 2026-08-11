import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { OAuthButtons } from '../components/OAuthButtons'

interface FormValues {
  email: string
  password: string
}

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>()

  if (!loading && user) return <Navigate to="/" replace />

  const onSubmit = async (values: FormValues) => {
    setError(null)
    try {
      await login(values.email, values.password)
      navigate('/', { replace: true })
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 400
          ? 'Wrong email or password'
          : 'Login failed — is the API running?',
      )
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>⚡ Energy Tracker</h1>
        <p className="auth-sub">Sign in to your account</p>
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              {...register('email', { required: 'Email is required' })}
            />
            {errors.email && <span className="err">{errors.email.message}</span>}
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register('password', { required: 'Password is required' })}
            />
            {errors.password && (
              <span className="err">{errors.password.message}</span>
            )}
          </div>
          {error && <div className="form-error">{error}</div>}
          <button className="btn primary" disabled={isSubmitting}>
            Sign in
          </button>
        </form>
        <OAuthButtons />
        <p className="auth-alt">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  )
}
