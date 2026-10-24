import { createContext, useContext } from 'react'

import type { ResolvedTheme, ThemeChoice } from './ThemeProvider'

/* Apart from ThemeProvider so that file exports only a component, which is what
   React Fast Refresh needs to hot-swap it in place. */

export interface ThemeState {
  /** The persisted choice, including 'system'. */
  choice: ThemeChoice
  /** The choice resolved against the OS. What is on <html data-theme>. */
  resolved: ResolvedTheme
  setChoice: (choice: ThemeChoice) => void
}

export const ThemeContext = createContext<ThemeState | null>(null)

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}
