import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { OAuthButtons } from '../components/OAuthButtons'

interface FormValues {
  email: string
  password: string
  confirm: string
}

export function RegisterPage() {
  const { register: signup } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>()

  const onSubmit = async (values: FormValues) => {
    setError(null)
    try {
      await signup(values.email, values.password)
      navigate('/', { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        setError('An account with this email already exists')
      } else {
        setError('Registration failed — is the API running?')
      }
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>Create account</h1>
        <p className="auth-sub">Track energy bills across your places</p>
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
              autoComplete="new-password"
              {...register('password', {
                required: 'Password is required',
                minLength: { value: 8, message: 'At least 8 characters' },
              })}
            />
            {errors.password && (
              <span className="err">{errors.password.message}</span>
            )}
          </div>
          <div className="field">
            <label htmlFor="confirm">Repeat password</label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              {...register('confirm', {
                validate: (v) =>
                  v === watch('password') || 'Passwords do not match',
              })}
            />
            {errors.confirm && (
              <span className="err">{errors.confirm.message}</span>
            )}
          </div>
          {error && <div className="form-error">{error}</div>}
          <button className="btn primary" disabled={isSubmitting}>
            Create account
          </button>
        </form>
        <OAuthButtons />
        <p className="auth-alt">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
