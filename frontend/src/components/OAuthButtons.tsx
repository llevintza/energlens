import { API_URL } from '../api/client'

// Comma-separated list, e.g. VITE_OAUTH_PROVIDERS=google,github.
// Leave unset until the OAuth apps are configured on the API.
const PROVIDERS = (import.meta.env.VITE_OAUTH_PROVIDERS ?? '')
  .split(',')
  .map((p: string) => p.trim())
  .filter(Boolean)

const LABELS: Record<string, string> = {
  google: 'Continue with Google',
  github: 'Continue with GitHub',
}

export function OAuthButtons() {
  if (PROVIDERS.length === 0) return null
  return (
    <>
      <div className="auth-divider">or</div>
      <div className="oauth-row">
        {PROVIDERS.map((provider: string) => (
          <button
            key={provider}
            type="button"
            className="btn"
            onClick={() => {
              // Full-page navigation (not fetch) so the API can set its CSRF
              // cookie first-party before redirecting to the provider.
              window.location.href = `${API_URL}/auth/${provider}/login`
            }}
          >
            {LABELS[provider] ?? `Continue with ${provider}`}
          </button>
        ))}
      </div>
    </>
  )
}
