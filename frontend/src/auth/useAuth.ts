import { createContext, useContext } from 'react'

import type { User } from '../api/types'

/* Apart from AuthProvider so that file exports only a component, which is what
   React Fast Refresh needs to hot-swap it in place. */

export interface AuthState {
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

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
