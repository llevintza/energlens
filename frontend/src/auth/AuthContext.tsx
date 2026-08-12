import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'

import {
  ApiError,
  api,
  getToken,
  setToken,
  setUnauthorizedHandler,
} from '../api/client'
import type { User } from '../api/types'

interface AuthState {
  user: User | null
  loading: boolean
  /**
   * Set when the stored token could not be checked because the API could not
   * be reached — as opposed to being checked and rejected, which clears the
   * token and leaves this null.
   */
  bootError: unknown
  retryBoot: () => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  loginWithToken: (token: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [bootError, setBootError] = useState<unknown>(null)
  const [bootAttempt, setBootAttempt] = useState(0)
  const qc = useQueryClient()

  const retryBoot = useCallback(() => setBootAttempt((n) => n + 1), [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    // Without this, a logout that follows a failed boot would leave the stale
    // error on screen instead of returning to the login form.
    setBootError(null)
    qc.clear()
  }, [qc])

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    setLoading(true)
    setBootError(null)
    api<User>('/users/me')
      .then(setUser)
      .catch((e: unknown) => {
        // A 401 is the one answer that means the token is genuinely no good;
        // `api()` has already cleared it, and the login redirect is correct.
        // Everything else — a rejected fetch, a 500, a cold start — means we
        // never found out. Record it rather than discarding a valid
        // credential, which would log the user out and send them to a login
        // form that cannot work either.
        if (e instanceof ApiError && e.status === 401) return
        setBootError(e)
      })
      .finally(() => setLoading(false))
  }, [bootAttempt])

  const loginWithToken = useCallback(async (token: string) => {
    setToken(token)
    const me = await api<User>('/users/me')
    setBootError(null)
    setUser(me)
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await api<{ access_token: string }>('/auth/jwt/login', {
        form: { username: email, password },
      })
      await loginWithToken(result.access_token)
    },
    [loginWithToken],
  )

  const register = useCallback(
    async (email: string, password: string) => {
      await api<User>('/auth/register', { body: { email, password } })
      await login(email, password)
    },
    [login],
  )

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        bootError,
        retryBoot,
        login,
        register,
        loginWithToken,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
