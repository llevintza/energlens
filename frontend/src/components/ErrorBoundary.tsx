import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  /**
   * `page` fills the viewport — for the outermost boundary, which sits above
   * the router and so has no shell to preserve. `inline` renders inside an
   * existing shell, leaving the nav usable so there is a way out.
   */
  variant?: 'page' | 'inline'
}

interface State {
  error: Error | null
}

/**
 * Stops a render-time throw from unmounting the tree to a blank page.
 *
 * A class is the only way to do this in React: the app uses the declarative
 * `<BrowserRouter>`/`<Routes>` API rather than a data router, so Router's
 * `errorElement` is not available.
 */
export class ErrorBoundary extends Component<Props, State> {
  // A class field, not a constructor parameter property — `erasableSyntaxOnly`
  // in tsconfig.app.json rejects the shorthand form.
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The only record of what actually happened — the fallback below stays
    // deliberately vague, since a stack trace is not user-facing copy.
    console.error('Render failed:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    const reload = () => window.location.reload()

    if (this.props.variant === 'inline') {
      return (
        <div className="card">
          <div className="query-error" role="alert">
            <div className="query-error-title">This page failed to load</div>
            <div className="query-error-detail">
              Something went wrong while rendering it. Your data is safe — use
              the navigation above to go elsewhere, or reload to try again.
            </div>
            <button className="btn small" onClick={reload}>
              Reload
            </button>
          </div>
        </div>
      )
    }

    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>Something broke</h1>
          <p className="auth-sub">
            Energlens hit an error it could not recover from. Your data is safe
            — nothing was being saved.
          </p>
          <button className="btn primary" onClick={reload}>
            Reload the page
          </button>
        </div>
      </div>
    )
  }
}
