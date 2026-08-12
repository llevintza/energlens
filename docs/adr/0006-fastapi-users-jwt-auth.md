# 0006. Authenticate with fastapi-users and stateless JWTs

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** llevintza
- **Landed in:** PR #1 (`81b373b`)
- **Related:** [ADR-0003](0003-fastapi-async-sqlalchemy-asyncpg.md), [ADR-0010](0010-frontend-hosting-github-pages.md), issue #9

## Context

The SPA is served from `llevintza.github.io` and the API from `onrender.com` — **two
different registrable domains**. That single fact drives almost everything here:
cookie-based sessions across those origins would need `SameSite=None; Secure`
third-party cookies, which browsers are actively removing.

Requirements: email/password now, Google/GitHub OAuth later without redesigning, and
no session store (Render free has no Redis and one instance).

## Decision

**fastapi-users v15** with a **stateless JWT** strategy, delivered two ways from one
signing configuration ([`backend/app/auth/backend.py`](../../backend/app/auth/backend.py)):

| Backend | Transport | Used by |
| --- | --- | --- |
| `auth_backend` | `BearerTransport` | Password login — token in the JSON body |
| `oauth_redirect_backend` | `OAuthRedirectTransport` | OAuth — token in the redirect URL fragment |

The SPA stores the token in `localStorage` under `et_token` and sends
`Authorization: Bearer`.

Three constraints are non-obvious and each breaks the flow if changed:

- **OAuth starts with a top-level navigation, not `fetch`.** fastapi-users v15
  requires the CSRF cookie to be first-party; an XHR cannot produce that. Hence the
  custom `/auth/{provider}/login` endpoint that 302s the browser.
- **The token returns in the URL *fragment*, not the query string.** Fragments are
  never transmitted to servers or written to access logs. The SPA calls
  `history.replaceState` before anything else to scrub it from the address bar.
- **`FRONTEND_URL` must include the `/energlens` base path** (the transport appends
  `/auth/callback#access_token=…`), while `CORS_ORIGINS` must be the bare origin.
  Different values, different jobs.

## Consequences

### What this buys

- **No session store**, so no Redis and no sticky sessions — the API stays trivially
  restartable, which matters on a tier that sleeps.
- **Cross-origin works without third-party cookies**, which is future-proof against
  browser policy rather than fighting it.
- Registration, login, password hashing, user CRUD and OAuth association come from a
  maintained library rather than hand-rolled auth.
- `associate_by_email=True` means signing in with Google after registering by password
  links to the same account instead of creating a duplicate.

### What this costs

- **Tokens cannot be revoked.** A stateless JWT is valid until it expires — currently
  **7 days** (`jwt_lifetime_seconds`). There is no logout-everywhere, and a leaked
  token is usable for up to a week. This is the single largest security trade-off in
  the system.
- **`localStorage` is readable by any JavaScript on the origin**, so an XSS becomes a
  token theft. `httpOnly` cookies would prevent that but reintroduce the third-party
  cookie problem. Mitigation is React's default escaping plus no `dangerouslySetInnerHTML`
  anywhere.
- **Rotating `JWT_SECRET` logs everyone out.** Render generates it once
  (`generateValue: true`); recreating the service generates a new one.
- fastapi-users owns the user table shape; deviating means overriding its models.
- **OAuth is configured but not live** — routes are *absent*, not merely disabled,
  when a client id/secret pair is empty. Tracked in issue #9.

## Limitations

| Limit | Value | Consequence |
| --- | --- | --- |
| Token lifetime | 7 days | Long window for a stolen token |
| Revocation | none | Cannot force logout |
| Refresh tokens | not implemented | Users re-login weekly |
| Rate limiting | **none anywhere** | Login is brute-forceable; relevant to [ADR-0015](0015-demo-seed-in-production.md) |
| Password rules | fastapi-users defaults | No complexity policy of our own |
| MFA | none | — |
| Email verification | `is_verified` exists, unused | Seeded/registered users are verified by default |

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Server-side sessions + cookies** | Needs `SameSite=None` third-party cookies across two domains — being deprecated by browsers — plus a session store the free tier lacks |
| **Auth0 / Clerk / Supabase Auth** | Removes the revocation and MFA gaps outright, but adds a vendor, a signup, and a cost cliff; disproportionate for a single-user tracker |
| **Hand-rolled JWT auth** | The library's value is the OAuth association and user CRUD, which is exactly the part that is easy to get subtly wrong |
| **Short-lived access + refresh tokens** | The correct fix for the revocation gap. Deferred, not rejected — see triggers |
| **`httpOnly` cookie on a shared parent domain** | Requires a custom domain covering both frontend and API; reconsider if one is bought |

## Revisit when

- [ ] **Real financial data is stored** → a 7-day non-revocable token is
      disproportionate. Shorten the lifetime and add refresh tokens.
- [ ] **A second user exists** → revocation stops being theoretical.
- [ ] **Any XSS is found**, or a dependency with a known XSS lands → `localStorage`
      storage becomes an active liability.
- [ ] **A custom domain is acquired** → `httpOnly` `SameSite=Lax` cookies on a shared
      parent domain become possible, which is strictly better than `localStorage`.
- [ ] **Rate limiting is added** → revisit whether login throttling is sufficient.
- [ ] **MFA or SSO is required.**

## Migration path

- **To shorter tokens + refresh:** fastapi-users supports a refresh flow; the SPA's
  `AuthContext` is the only client-side change, and `client.ts` already centralises
  401 handling.
- **To cookie-based sessions:** requires a shared parent domain first; the transport
  is swappable at `auth_backend` without touching routers.
- **To a managed provider:** the `User` model would keep its shape; `fastapi_users`
  dependencies would be replaced by a token-verification dependency. The blast radius
  is `app/auth/` plus one dependency in each router.
