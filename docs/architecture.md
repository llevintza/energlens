# Energlens architecture

The system view. Individual choices and their justifications live in
[`docs/adr/`](adr/) — this page is the map those decisions apply to.

Everything here reflects the deployment as it actually runs, verified end to end
on 2026-08-11.

---

## Deployment topology

Three hosted components, no servers of our own, **$0/month** at current tiers.

```mermaid
flowchart TB
    subgraph client["Browser"]
        SPA["React SPA<br/>base path /energlens/"]
    end

    subgraph gh["GitHub"]
        Pages["GitHub Pages<br/>static bundle, global CDN<br/>llevintza.github.io/energlens"]
        Actions["Actions<br/>backend-tests · frontend-build<br/>deploy-frontend"]
        Repo[("Repository<br/>llevintza/energlens")]
    end

    subgraph render["Render · region ohio · free tier"]
        API["FastAPI on uvicorn<br/>512 MB · sleeps after 15 min idle<br/>energlens-api.onrender.com"]
    end

    subgraph neon["Neon · AWS us-east-2 · free tier"]
        PG[("PostgreSQL 18<br/>0.5 GB · scale-to-zero")]
    end

    SPA -- "GET the bundle" --> Pages
    SPA -- "XHR + Bearer JWT<br/>CORS: llevintza.github.io" --> API
    API -- "asyncpg over TLS<br/>pool_pre_ping" --> PG
    Repo --> Actions
    Actions -- "upload-pages-artifact" --> Pages
    Repo -- "auto-deploy on push to main" --> API

    classDef ext fill:#f6f8fa,stroke:#6a737d,color:#24292e
    class Pages,Actions,Repo,API,PG ext
```

**The two hops that constrain everything else.** The browser→API hop crosses the
public internet and is therefore subject to CORS and cold starts; the API→database
hop happens per query, which is why the two must sit in the same region
([ADR-0013](adr/0013-co-locate-api-and-database-region.md)).

| Component | Provider | Tier | Hard limits |
| --- | --- | --- | --- |
| SPA | GitHub Pages | free | 1 GB site, 100 GB/mo bandwidth, public repo |
| API | Render web service | free | 512 MB RAM, sleeps after 15 min idle, 30–60s cold start |
| Database | Neon | free | 0.5 GB storage, scale-to-zero after ~5 min |

---

## Request lifecycle

What happens on a cold system, including the two sleep behaviours that make the
first request slow but not broken.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant P as GitHub Pages
    participant R as Render
    participant N as Neon

    B->>P: GET /energlens/
    P-->>B: index.html + bundle (API_URL inlined at build time)
    Note over B: AuthContext finds no token<br/>renders /login without any network call

    B->>R: POST /auth/jwt/login (form-encoded)
    Note over R: cold? 30–60s spin-up<br/>start.sh already ran migrations at boot
    R->>N: SELECT … FROM "user"
    Note over N: idle? scale-to-zero wake<br/>pool_pre_ping reconnects transparently
    N-->>R: row
    R-->>B: {"access_token": "…"} + CORS headers

    B->>R: GET /places (Authorization: Bearer …)
    R->>N: SELECT … FROM places
    N-->>R: rows
    R-->>B: JSON
```

`pool_pre_ping=True` ([`backend/app/db.py`](../backend/app/db.py)) is what makes step 8
survive: Neon drops the server side of pooled connections while the process stays
alive, so without a liveness check the first query after an idle gap fails with
`ConnectionDoesNotExistError` instead of reconnecting.

---

## Authentication

Two token deliveries, one JWT strategy
([`backend/app/auth/backend.py`](../backend/app/auth/backend.py)).

```mermaid
flowchart LR
    subgraph pw["Password — Bearer transport"]
        A1["POST /auth/jwt/login<br/>username + password, form-encoded"] --> A2["access_token in body"]
        A2 --> A3["localStorage 'et_token'<br/>→ Authorization: Bearer"]
    end

    subgraph oa["OAuth — redirect transport"]
        B1["Top-level navigation to<br/>{API}/auth/{provider}/login"] --> B2["Provider consent"]
        B2 --> B3["{API}/auth/{provider}/callback"]
        B3 --> B4["302 → {FRONTEND_URL}/auth/callback<br/>#access_token=…"]
        B4 --> B5["SPA reads the fragment,<br/>scrubs it from history"]
    end
```

Three non-obvious constraints, each of which breaks the flow if violated:

- **The OAuth start is a top-level navigation, not `fetch`.** fastapi-users v15
  requires the CSRF cookie to be first-party, which an XHR cannot achieve.
- **The token comes back in the URL *fragment*, not the query string.** Fragments
  are never sent to the server or written to server logs. The SPA calls
  `history.replaceState` before doing anything else
  ([`OAuthCallbackPage.tsx`](../frontend/src/auth/OAuthCallbackPage.tsx)).
- **`FRONTEND_URL` must include the `/energlens` base path**, while `CORS_ORIGINS`
  must be the bare origin. They are different values for a reason, and swapping
  them silently breaks either CORS or the OAuth redirect.

`--forwarded-allow-ips '*'` in [`backend/start.sh`](../backend/start.sh) exists for this
flow: Render's TLS proxy connects from a non-loopback address, and without trusting
it `request.url_for` builds `http://` URLs, failing OAuth with `redirect_uri_mismatch`.

---

## Data model

```mermaid
erDiagram
    user ||--o{ oauth_account : "has"
    user ||--o{ places : "owns"
    places ||--o{ bills : "accumulates"

    user {
        uuid id PK
        string email UK
        string hashed_password
        bool is_active
        bool is_verified
    }
    places {
        uuid id PK
        uuid user_id FK "ON DELETE CASCADE"
        string name
        string city
        string country_code
        string currency_code "snapshotted onto each bill"
    }
    bills {
        uuid id PK
        uuid place_id FK "ON DELETE CASCADE"
        enum utility_type
        date period_start
        date period_end
        numeric consumption
        numeric total_cost
        enum source "manual / script / pdf"
    }
```

**`UNIQUE (place_id, utility_type, period_start, period_end)`** on `bills` is what
makes ingestion idempotent — re-importing the same PDF conflicts instead of
duplicating. Monthly series are *derived* from these periods by day-overlap
proration ([`backend/app/services/series.py`](../backend/app/services/series.py)) rather
than stored, because real bills do not align to calendar months.

---

## Delivery pipeline

```mermaid
flowchart LR
    PR["Pull request"] --> CI{"Required checks"}
    CI -->|backend-tests| T1["lock-check · migrate-check<br/>pytest backend + ingest"]
    CI -->|frontend-build| T2["tsc -b · vite build"]
    T1 & T2 --> M["Squash-merge to main<br/>(protect-main ruleset)"]
    M --> D1["Render auto-deploy<br/>alembic upgrade head → seed → uvicorn"]
    M -.->|"only if frontend/** changed"| D2["deploy-frontend.yml<br/>→ GitHub Pages"]
```

`make check` is defined as the union of the two required jobs, so the local gate and
CI cannot disagree ([ADR-0002](adr/0002-monorepo-with-make-as-command-surface.md)).

**The dotted edge is a real trap.** `deploy-frontend.yml` has a `paths` filter of
`frontend/**`, and `API_URL` is inlined into the bundle at *build* time. Changing the
`API_URL` repository variable therefore triggers no deploy at all — it needs an
explicit `gh workflow run`. This is tracked in
[#11](https://github.com/llevintza/energlens/issues/11).

---

## Boot sequence

Render's free tier has no pre-deploy hook and no shell access, so schema management
rides on process startup ([`backend/start.sh`](../backend/start.sh)).

```mermaid
flowchart TB
    S["Container start"] --> V{"DATABASE_URL set?"}
    V -->|no| F["exit 1 — names the variable"]
    V -->|yes| MIG["alembic upgrade head"]
    MIG -->|fails| F2["boot aborts under set -e<br/>← this is what catches a bad DSN"]
    MIG -->|"ok — no-op when current"| SD{"SEED_DEMO=true?"}
    SD -->|yes| SEED["python -m app.seed<br/>failure tolerated, logged loudly"]
    SD -->|no| U
    SEED --> U["uvicorn --forwarded-allow-ips '*'"]
```

A bad connection string is caught **here**, not by the health check — `/health` is
deliberately static ([ADR-0014](adr/0014-split-liveness-and-readiness-health-checks.md)).

---

## Environments

| | Local | CI | Production |
| --- | --- | --- | --- |
| Database | `energlens` (local PG) | `energlens_test` (service container) | Neon `neondb` |
| Schema built by | Alembic or `create_all` | `create_all`, plus Alembic in `migrate-check` | Alembic only |
| Config source | `.env` via direnv | workflow `env` | Render env vars |
| Secrets | gitignored `.env` | repo variables | Render dashboard |

Three local databases exist for a reason — see
[ADR-0005](adr/0005-alembic-migrations-and-three-databases.md). The short version:
checking migrations against the *test* database would compare the models with
themselves and never detect drift.
