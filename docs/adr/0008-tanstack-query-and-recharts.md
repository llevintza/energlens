# 0008. TanStack Query for server state, Recharts for visualisation

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** llevintza
- **Landed in:** PR #1 (`81b373b`)
- **Related:** [ADR-0007](0007-react-vite-spa.md), issue #8

## Context

Essentially all state in this app is **server** state: places, bills, derived monthly
series. There is almost no client-only state beyond form drafts and the auth token.
Reaching for a general-purpose store (Redux, Zustand) would mean hand-writing caching,
refetching and invalidation that a data-fetching library already does correctly.

The core UI is a set of time-series charts: consumption and cost per month, across
two properties in two currencies.

## Decision

**TanStack Query v5** for all server state, **Recharts 3** for charts, and a
hand-rolled `fetch` wrapper in [`src/api/client.ts`](../../frontend/src/api/client.ts)
rather than axios.

The client wrapper is ~70 lines and does exactly four things: prefix `API_URL`, attach
the bearer token, encode form vs JSON bodies, and centralise 401 handling (clear the
token, fire the unauthorized handler). That is the whole reason axios was unnecessary.

## Consequences

### What this buys

- **Caching, deduplication, background refetch and invalidation** without writing any
  of it — the correct default for data that lives on a server.
- No global store to maintain, and no reducers describing data the API already owns.
- Recharts is declarative React components, so charts compose like the rest of the UI.
- One `fetch` wrapper, no HTTP dependency, and 401 handled in exactly one place.

### What this costs

- **Recharts is the bulk of the bundle.** Total build is ~714 KB raw / ~212 KB
  gzipped, past Vite's 500 KB warning. For a dashboard behind a login this is
  acceptable; on a public page it would not be.
- **TanStack Query's error state is available but unused.** No page reads `isError`,
  so a failed request renders the empty state — "No places yet", "Place not found" —
  which is actively misleading during an outage. This is issue #8, and it is a
  consequence of the choice not being followed through, not of the choice itself.
- Recharts' TypeScript types are loose in places; some chart props need casts.
- A hand-rolled client means retries, timeouts and interceptors are ours to add if
  ever needed.

## Limitations

- No SSR/streaming integration (irrelevant — [ADR-0007](0007-react-vite-spa.md)).
- Recharts renders SVG, so very large series degrade; irrelevant at 24 points per
  place, relevant if daily readings arrive.
- No chart accessibility layer beyond what Recharts provides by default.
- The `fetch` wrapper has no timeout, so a hung request hangs the query until the
  browser gives up — worth adding given the free tier's 30–60s cold starts.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Redux Toolkit (+ RTK Query)** | RTK Query is a genuine peer; the rest of Redux is unnecessary when there is no client state to manage |
| **SWR** | Very close and lighter; TanStack Query chosen for richer mutation and invalidation APIs |
| **Plain `useEffect` + `useState`** | Means hand-writing caching, dedup and refetch — the exact bugs the library exists to prevent |
| **axios** | Interceptors and instances are nice, but ~15 KB for four behaviours we implement in 70 lines |
| **Chart.js / ECharts** | Smaller (Chart.js) or far more capable (ECharts), but imperative canvas APIs that fit React poorly |
| **visx / D3 directly** | Maximum control and minimum bundle, at a large authoring cost for standard line and bar charts |
| **Nivo** | Comparable to Recharts, similar bundle weight, no decisive advantage |

## Revisit when

- [ ] **Bundle size becomes a real problem** → lazy-load the chart routes first
      (`React.lazy`), which removes Recharts from the initial bundle. Only then
      consider swapping the library.
- [ ] **Issue #8 is addressed** → surfacing `isError` is a change in how the app uses
      TanStack Query, not a reason to replace it.
- [ ] **Data density grows** (daily or interval readings) → SVG rendering becomes the
      bottleneck; canvas-based ECharts or visx becomes justified.
- [ ] **Offline support or optimistic mutations become important** → TanStack Query
      supports both; the decision holds, the usage deepens.
- [ ] **Request timeouts are needed** for cold starts → add to the wrapper rather than
      adopting axios.

## Migration path

TanStack Query usage is confined to hooks in `src/api/`; swapping to SWR would be
mechanical. Recharts is confined to chart components, so replacing it touches only
those files — the data shaping in `services/series.py` and the API contract are
unaffected either way.
