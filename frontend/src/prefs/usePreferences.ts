import { createContext, useContext } from 'react'

import type { Preferences } from './PreferencesProvider'

/* Apart from PreferencesProvider so that file exports only a component, which is
   what React Fast Refresh needs to hot-swap it in place. */

export interface PreferencesState {
  prefs: Preferences
  /** Partial merge — callers set one field without restating the rest. */
  setPrefs: (patch: Partial<Preferences>) => void
}

export const PreferencesContext = createContext<PreferencesState | null>(null)

export function usePreferences(): PreferencesState {
  const ctx = useContext(PreferencesContext)
  if (!ctx) throw new Error('usePreferences outside PreferencesProvider')
  return ctx
}
