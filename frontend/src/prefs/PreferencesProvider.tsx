import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type NumberFormat = 'locale' | 'plain'
export type DefaultRange = '12m' | '24m' | 'all'

export interface Preferences {
  numberFormat: NumberFormat
  defaultRange: DefaultRange
}

const DEFAULTS: Preferences = { numberFormat: 'locale', defaultRange: '24m' }

/* Separate from the theme's key on purpose: the theme has to be readable by the
   pre-paint script in index.html before any bundle loads, so it is a bare string that
   cannot half-parse. These are only ever read by React, so JSON is fine. */
const STORAGE_KEY = 'energlens-prefs'

interface PreferencesState {
  prefs: Preferences
  /** Partial merge — callers set one field without restating the rest. */
  setPrefs: (patch: Partial<Preferences>) => void
}

const PreferencesContext = createContext<PreferencesState | null>(null)

function read(): Preferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return DEFAULTS
    const parsed = JSON.parse(stored) as Partial<Preferences>
    return {
      numberFormat:
        parsed.numberFormat === 'plain' || parsed.numberFormat === 'locale'
          ? parsed.numberFormat
          : DEFAULTS.numberFormat,
      defaultRange:
        parsed.defaultRange === '12m' ||
        parsed.defaultRange === '24m' ||
        parsed.defaultRange === 'all'
          ? parsed.defaultRange
          : DEFAULTS.defaultRange,
    }
  } catch {
    /* Unparseable or unavailable storage falls back to the defaults rather than
       throwing on boot. */
    return DEFAULTS
  }
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [prefs, setState] = useState<Preferences>(read)

  const setPrefs = useCallback((patch: Partial<Preferences>) => {
    setState((current) => {
      const next = { ...current, ...patch }
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        /* Not persisting is survivable; refusing to change is not. */
      }
      return next
    })
  }, [])

  const value = useMemo(() => ({ prefs, setPrefs }), [prefs, setPrefs])
  return (
    <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
  )
}

export function usePreferences(): PreferencesState {
  const ctx = useContext(PreferencesContext)
  if (!ctx) throw new Error('usePreferences outside PreferencesProvider')
  return ctx
}
