# 0007. A React 19 + Vite single-page app, no SSR

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** llevintza
- **Landed in:** PR #1 (`81b373b`)
- **Related:** [ADR-0008](0008-tanstack-query-and-recharts.md), [ADR-0010](0010-frontend-hosting-github-pages.md)

## Context

The frontend is an authenticated dashboard: charts, forms, and a couple of list
views. Every page requires a login, so **there is nothing for a search engine to
index and nothing to server-render**. The hosting target is a static CDN
([ADR-0010](0010-frontend-hosting-github-pages.md)), which cannot run server code at all.

## Decision

**React 19 + Vite 8 + TypeScript**, built to static files, with `react-router-dom` for
client-side routing and `react-hook-form` for forms. No SSR, no meta-framework.

Configuration reaches the bundle through exactly one mechanism — Vite's
`import.meta.env` with `VITE_` prefixes — and is inlined at build time:

| Variable | Source | Consumed by |
| --- | --- | --- |
| `VITE_API_URL` | repo variable `API_URL` | `src/api/client.ts` |
| `VITE_BASE` | `actions/configure-pages` | `vite.config.ts` → `base` |
| `VITE_OAUTH_PROVIDERS` | repo variable `OAUTH_PROVIDERS` | `components/OAuthButtons.tsx` |

Two small details in `client.ts` are deliberate and worth keeping:

```ts
// `||`, not `??`: an unset GitHub Actions variable expands to an empty string,
// which `??` would keep and then blow up in `new URL('' + path)`.
export const API_URL: string = (
  import.meta.env.VITE_API_URL || 'http://localhost:8000'
).replace(/\/+$/, '')
```

The trailing-slash strip prevents `//places`; the `||` handles the empty-string case
that `??` does not.

## Consequences

### What this buys

- **Deployable to any static host**, which keeps hosting a commodity decision.
- **The SPA renders with the backend down.** `AuthContext` skips the network when
  `localStorage` holds no token, so a visitor always reaches `/login` — the site is
  never blank because the API is asleep. This mattered during the period when no
  backend existed at all.
- Vite's dev server is fast, and `tsc -b` is the type gate in CI.
- Type safety across the API boundary, hand-maintained but checked.

### What this costs

- **Build-time configuration is a genuine footgun.** `API_URL` is baked into the
  bundle. Combined with the workflow's `frontend/**` paths filter, changing the
  variable deploys nothing — the old value stays live until someone re-dispatches the
  workflow by hand. This has caused two separate incidents (issues #10, #11).
- **No SSR means no SEO and a blank first paint** until JS loads. Irrelevant for an
  authenticated dashboard, disqualifying if a marketing page is ever added.
- **A single large bundle** — currently ~714 KB raw / ~212 KB gzipped, over Vite's
  500 KB warning threshold. Recharts dominates it. No code splitting yet.
- SPA deep links need the `404.html` copy trick on Pages.

## Limitations

- Bundle size will keep growing without route-level code splitting.
- No error boundary anywhere, and no page reads `isError` — so a failed request
  currently renders "No places yet" rather than an error. Tracked in issue #8.
- No test runner for the frontend; `tsc -b` is the only gate. There are no component
  tests.
- React 19 + TypeScript 6 + Vite 8 are all recent majors; the ecosystem around them
  moves fast.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Next.js** | SSR/SSG is the main draw and this app needs neither; static export would give up most of it while adding a heavier toolchain and pushing toward Vercel |
| **Remix / React Router 7 framework mode** | Server-first data loading, but requires a server the static host cannot provide |
| **Astro** | Excellent for content sites; this is an authenticated app with no static content |
| **SvelteKit / Vue** | Smaller bundles and arguably nicer ergonomics; React chosen for familiarity and ecosystem depth |
| **Server-rendered templates from FastAPI** | One origin, no CORS, no bundle — but loses the CDN and couples the UI to a dyno that sleeps |

## Revisit when

- [ ] **A public marketing or landing page is wanted** → SSR/SSG becomes relevant, and
      this ADR reopens together with [ADR-0010](0010-frontend-hosting-github-pages.md).
- [ ] **Bundle size affects load time on mobile** → route-level `React.lazy` splitting
      first, then reconsider Recharts ([ADR-0008](0008-tanstack-query-and-recharts.md)).
- [ ] **Runtime configuration is needed** (per-environment API URL without a rebuild)
      → serve a `config.json` fetched at boot instead of inlining, which also fixes
      the issue #11 class of problem.
- [ ] **The frontend needs real tests** → Vitest + Testing Library; the absence of any
      test runner is the largest quality gap in the repo.

## Migration path

The app is standard React with no framework-specific APIs, so a move to Next.js or
Remix would be mechanical for routing and incremental for data fetching (TanStack
Query has documented paths to both). The genuinely portable parts are `src/api/`,
`src/auth/` and the components; the router configuration is what changes.
