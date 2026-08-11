import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { api, getToken, setToken, setUnauthorizedHandler } from '../api/client'
import type { User } from '../api/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  loginWithToken: (token: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const qc = useQueryClient()

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
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
    api<User>('/users/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  const loginWithToken = useCallback(async (token: string) => {
    setToken(token)
    const me = await api<User>('/users/me')
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
      value={{ user, loading, login, register, loginWithToken, logout }}
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
