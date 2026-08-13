import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'

/** What the user picked. SYSTEM is a real choice, not the absence of one. */
export type ThemeChoice = 'light' | 'dark' | 'system'
/** What that resolves to right now — the only thing tokens.css understands. */
export type ResolvedTheme = 'light' | 'dark'

/* Keep in step with the pre-paint script in index.html, which has to duplicate this
   resolution because it runs before any module can. */
const STORAGE_KEY = 'energlens-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

interface ThemeState {
  /** The persisted choice, including 'system'. */
  choice: ThemeChoice
  /** The choice resolved against the OS. What is on <html data-theme>. */
  resolved: ResolvedTheme
  setChoice: (choice: ThemeChoice) => void
}

const ThemeContext = createContext<ThemeState | null>(null)

function readChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored
    }
  } catch {
    /* Private mode, or cookies blocked. Fall through to the default. */
  }
  return 'system'
}

function systemTheme(): ResolvedTheme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

function resolve(choice: ThemeChoice): ResolvedTheme {
  return choice === 'system' ? systemTheme() : choice
}

/**
 * Write the attribute the tokens key off.
 *
 * Called imperatively at the moment the theme changes, *before* the React state
 * update that re-renders the tree. The order matters: chart colours are read out of
 * the computed style during render (see components/charts/chartTheme.ts), so if the
 * attribute were only set afterwards in an effect, every chart would read the outgoing
 * palette and keep it until something else re-rendered it.
 */
function applyTheme(resolved: ResolvedTheme): void {
  document.documentElement.dataset.theme = resolved
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readChoice)
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolve(readChoice()))

  /* Under SYSTEM, follow the OS live. Reading the media query once at boot would leave
     a user who flips their OS theme staring at the wrong palette until they reload.
     Note this subscribes but does not set state on mount: an unconditional state
     update here would add a second render on every page load, which is enough to
     orphan Recharts' entry animation and leave charts drawn at 3% of their length. */
  useEffect(() => {
    if (choice !== 'system') return
    const mq = window.matchMedia(DARK_QUERY)
    const update = () => {
      const next: ResolvedTheme = mq.matches ? 'dark' : 'light'
      applyTheme(next)
      setResolved(next)
    }
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [choice])

  /* The pre-paint script already set the attribute for the first render. Re-assert it
     once on mount so a divergence between the two shows up as a flash rather than as a
     wrong theme, and never touch state here. */
  useEffect(() => {
    applyTheme(resolved)
  }, [resolved])

  const setChoice = useCallback((next: ThemeChoice) => {
    const nextResolved = resolve(next)
    applyTheme(nextResolved)
    setResolved(nextResolved)
    setChoiceState(next)
    try {
      /* Persist the choice, not the resolved value — storing 'dark' for someone who
         picked SYSTEM would freeze them out of ever following the OS again. */
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* Not persisting is survivable; refusing to switch is not. */
    }
  }, [])

  const value = useMemo(
    () => ({ choice, resolved, setChoice }),
    [choice, resolved, setChoice],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}
