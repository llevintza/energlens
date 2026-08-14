# ⚡ Energlens

[![Backend CI](https://github.com/llevintza/energlens/actions/workflows/backend-ci.yml/badge.svg?branch=main)](https://github.com/llevintza/energlens/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/llevintza/energlens/actions/workflows/frontend-ci.yml/badge.svg?branch=main)](https://github.com/llevintza/energlens/actions/workflows/frontend-ci.yml)
[![Deploy](https://github.com/llevintza/energlens/actions/workflows/deploy-frontend.yml/badge.svg?branch=main)](https://github.com/llevintza/energlens/actions/workflows/deploy-frontend.yml)
[![Live site](https://github.com/llevintza/energlens/actions/workflows/pages-smoke.yml/badge.svg?branch=main)](https://github.com/llevintza/energlens/actions/workflows/pages-smoke.yml)

Track the evolution of electricity bills across your properties — consumption
(kWh), cost, and effective price per kWh over time, with charts your utility
provider doesn't give you.

- **Backend** — FastAPI + SQLAlchemy (async) + PostgreSQL, JWT auth
  (email/password + optional Google/GitHub OAuth), Alembic migrations.
- **Frontend** — React + TypeScript + Vite SPA with Recharts dashboards,
  deployable to GitHub Pages.
- **Ingest** — a CLI that extracts data from bill PDFs with Claude and uploads
  it through the API.

## Quick start (local)

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+ (the
version in `.nvmrc` — `nvm use` picks it up, and `npm ci` refuses to install on
anything older), and PostgreSQL — either Docker or, without Docker, Homebrew
Postgres (`brew install postgresql@16`), which `make db-up` will set up in a
project-local `.pgdata/` on first run.

```sh
make setup       # .env from .env.example, uv sync, npm ci
make db-up       # starts Postgres and creates both databases
make migrate
make seed        # demo@example.com / demo1234 with 2 years of data
```

Then, in two terminals:

```sh
make dev-api     # http://localhost:8000, docs at /docs
make dev-web     # http://localhost:5173
```

`make help` lists every target. The underlying tools are still `uv`, `npm`,
`alembic` and `scripts/pgdev.sh` — `make` just removes the need to know which
one a given job uses, and which directory to be in.

Log in as `demo@example.com` / `demo1234` to see seeded charts, or register
your own account.

### Migrating a pre-rename setup

The databases used to be called `energy_tracker` / `energy_tracker_test`. If
you set the project up before the rename, the new defaults point at databases
your cluster doesn't have yet, and `alembic upgrade head` fails with
`InvalidCatalogNameError: database "energlens" does not exist`. Pick one:

```sh
# Keep your existing bills — rename the databases in place (no connections open)
psql -h localhost -U energy -d postgres \
  -c 'ALTER DATABASE energy_tracker RENAME TO energlens' \
  -c 'ALTER DATABASE energy_tracker_test RENAME TO energlens_test'

# Or start fresh — creates whatever is missing, leaves the old ones untouched
scripts/pgdev.sh init
```

On Docker, `POSTGRES_DB` only takes effect when the volume is empty, so an
existing `pgdata` volume needs the same `ALTER DATABASE` (run it inside the
container with `docker compose exec db psql -U energy -d postgres -c ...`) or
`docker compose down -v`, **which deletes the volume and every bill in it**.

Also update the `DATABASE_URL` in your gitignored `.env` — it is read in
preference to the new default in `backend/app/config.py`, so a stale copy
silently keeps the app on the old database while the test suite uses the new
one.

## Tests

```sh
make check                     # everything CI runs — the gate before a PR
```

Or one suite at a time:

```sh
make test-backend              # pytest; PYTEST_ARGS="-k currency" to narrow
make test-ingest               # never calls a paid API
make test-frontend             # vitest, after tsc -b
make typecheck                 # just the frontend typecheck
```

`make test-backend` needs the `energlens_test` database. If it is missing, or
Postgres is not running, or the databases still carry their pre-rename names,
the preflight in `scripts/db.sh` says which of those it is and gives the exact
command to fix it — `make db-up` and `make db-ensure` cover almost every case.

## Importing your real bills

```sh
cd ingest && uv sync
export ANTHROPIC_API_KEY=sk-ant-...
export ENERGLENS_EMAIL=you@example.com ENERGLENS_PASSWORD=...

# 1. Extract + review (results cached by file hash in extracted.jsonl)
uv run energlens-ingest extract --dir ~/bills/main-residence

# 2. Upload the reviewed cache to a place (UUID from the UI or GET /places)
uv run energlens-ingest upload --cache extracted.jsonl --place-id <uuid>

# ...or do both at once
uv run energlens-ingest run --dir ~/bills/main-residence --place-id <uuid>
```

`--dry-run` on `extract` previews what is already cached without calling
Claude, so it never costs anything. The CLI reads `ENERGLENS_TOKEN` or
`ENERGLENS_EMAIL`/`ENERGLENS_PASSWORD`, and `ENERGLENS_API_URL` (default
`http://localhost:8000`); the older `ET_*` names still work.

Re-runs skip already-uploaded bills (the API returns 409 for duplicates) and
never re-pay extraction for unchanged files. A duplicate is decided by the
provider's invoice number when the bill carries one, and by
`(place, utility type, period)` when it does not — which is every bill this CLI
sends today, so its re-run behaviour is unchanged. The period is not identity: a
`Stornare` reverses an invoice and reprints its period, and both have to fit. Extraction uses Claude
(`claude-opus-5`, roughly 1–2¢ per bill); a large backlog can be moved to the
Batches API for 50% off.

Manual entry is always available in the UI (place page → “Add bill”).

## OAuth setup (optional)

Email/password works out of the box. To enable Google/GitHub login:

1. Create an OAuth app per provider (one per environment).
   Callback URL: `http://localhost:8000/auth/google/callback` (resp. `github`)
   for dev; your hosted API origin in production.
2. Set `GOOGLE_CLIENT_ID/SECRET` and/or `GITHUB_CLIENT_ID/SECRET` in `.env` —
   the routes only mount when configured.
3. Set `VITE_OAUTH_PROVIDERS=google,github` for the frontend build so the
   buttons appear.

The SPA sends the browser to `{API}/auth/{provider}/login` (top-level
navigation, so the CSRF cookie is first-party), and the callback 302s back to
`{FRONTEND_URL}/auth/callback#access_token=...` with the token in the URL
fragment.

## GitHub MCP server (agent harnesses)

The `github` MCP server is configured at **project scope and committed**, so any
contributor gets it on clone. It authenticates with your own GitHub token, read
from `GITHUB_MCP_PAT` — no secret is in the repo, only the variable name.

The bridge is `direnv`: `.envrc` is committed and secret-free, loads your
gitignored `.env`, and exports it. Because that happens at the shell level, every
harness launched from this directory inherits it identically.

```sh
gh auth login                # or set GITHUB_MCP_PAT in .env — see below
cp .env.example .env
direnv allow                 # one-time, per clone
```

Authenticate before `direnv allow`. `.envrc` reads the `gh` keyring at the moment
it evaluates, so logging in afterwards leaves the exported token empty until you
run `direnv reload` or open a new shell. Editing `.env` reloads automatically,
because direnv watches that file.

If `GITHUB_MCP_PAT` ends up unset, `.envrc` says so on entering the directory,
before any harness starts. Without `direnv`, reproduce both halves — sourcing
`.env` on its own exports the blank placeholder and skips the keyring fallback:

```sh
set -a; . ./.env; set +a
: "${GITHUB_MCP_PAT:=$(gh auth token 2>/dev/null)}"; export GITHUB_MCP_PAT
```

Tokens are minted at <https://github.com/settings/personal-access-tokens>. A
fine-grained PAT needs **Contents: Read and write**, plus **Workflows: Read and
write** to edit files under `.github/workflows/`. On a classic PAT those are the
`repo` and `workflow` scopes — `workflow` is classic-only and is not offered in
the fine-grained UI.

| Harness | Committed config | Notes |
| --- | --- | --- |
| Claude Code | `.mcp.json` | approve once when prompted |
| Copilot CLI | `.mcp.json` | |
| Cursor | `.cursor/mcp.json` | uses `${env:VAR}`, not `${VAR}` |
| Gemini CLI | `.gemini/settings.json` | |
| Codex | `.codex/config.toml` | project must be trusted |

**Muse Code** resolves settings only from the user-level file, so it can't be
committed. Add this to `~/.config/muse/settings.json` yourself:

```json
{
  "schema_version": 1,
  "mcp_servers": {
    "github": {
      "transport": "streamable_http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

`schema_version` is required — Muse fails to start without it.

## Deployment

Live at <https://llevintza.github.io/energlens/>. Total cost on the tiers below:
**$0/month**.

> **Why these providers, what they cost us, and how to move off them** —
> [`docs/adr/`](docs/adr/). Each record ends with explicit revisit triggers and a
> migration path. [`docs/architecture.md`](docs/architecture.md) has the system
> diagrams.

### First deploy, in order

The pieces below are order-dependent — the frontend build bakes in a backend URL
that does not exist yet, so doing this out of order ships a green build pointed
at nothing.

1. **Neon** — create a project, and **put it in the same region as
   `render.yaml`'s `region:`** (currently AWS `us-east-2` / Render `ohio`). A
   split costs ~100ms per *query*, not per request, so a dashboard page issuing
   several sequential queries pays it several times over. On the connection-string
   widget, turn **Connection pooling off** before copying, then rewrite the
   string. Every one of these fails at runtime, not at paste time:

   | Neon gives you | Rewrite to | Why |
   | --- | --- | --- |
   | `postgresql://` | `postgresql+asyncpg://` | SQLAlchemy driver selection |
   | `ep-xxx-pooler.c-N.<region>…` | delete **only** `-pooler` | pgbouncer's transaction mode breaks asyncpg's prepared-statement cache |
   | `?sslmode=require&channel_binding=require` | `?ssl=require` | both are libpq-only; asyncpg raises on them |

   On the middle row: delete the `-pooler` suffix and **nothing else**. The `c-N`
   segment looks like a region prefix but is part of the endpoint identity, and
   Neon routes by SNI — strip it and the host still resolves, still accepts a TLS
   connection, and then fails with `InvalidPasswordError`, which reads like a bad
   credential rather than a bad hostname. The result:

   ```
   postgresql+asyncpg://<user>:<pass>@ep-xxx.c-N.us-east-2.aws.neon.tech/neondb?ssl=require
   ```

   Neon's default database is `neondb`; keeping that name is fine, nothing in the
   deployed code requires `energlens`. A `%` in the generated password is safe —
   `alembic/env.py` escapes it before ConfigParser sees it.

2. **Render** — New → Blueprint → this repo, branch `main`. It reads `render.yaml`
   and prompts for `DATABASE_URL`, the only variable marked `sync: false`; paste
   the rewritten DSN. `JWT_SECRET` is generated for you. Watch the first deploy
   log for `uv sync --locked` → `alembic upgrade head` → the seed → uvicorn.
   `start.sh` runs under `set -e`, so a broken DSN aborts the boot *there*, with a
   real error — that, not the health check, is what catches a bad connection
   string.

3. **Point the frontend at it.** Render assigns `<service-name>.onrender.com`, but
   appends a suffix if the name is taken, so read the hostname off the service
   page rather than assuming it. Because `*.onrender.com` is a wildcard, a wrong
   guess returns a convincing 404 instead of failing to resolve. Both commands are
   required — `API_URL` is inlined at build time, and the workflow's `frontend/**`
   path filter means setting the variable triggers no deploy on its own:

   ```sh
   gh variable set API_URL --body https://<actual-host>
   make api-preflight                       # proves an Energlens API actually answers there
   gh workflow run "Deploy frontend to GitHub Pages"
   ```

   `make api-preflight` with no arguments reads the repository variable you just
   set and probes `<API_URL>/health` — the same check the deploy runs, so a wrong
   hostname is caught here rather than after a two-minute build.

4. **Verify.** The deploy already proved `/health` answers, so this step is about
   the database and the browser-level path no server-side probe covers. Allow
   30–60s for the free tier's cold start:

   ```sh
   H=https://<actual-host>
   curl -sS --max-time 90 "$H/health"     # {"status":"ok"} — the process is up
   curl -sS --max-time 90 "$H/health/db"  # {"status":"ok","database":"ok"} — Neon is reachable
   ```

   A 404 with an `x-render-routing: no-server` header means no service claims that
   hostname — you have the wrong one. Then check the published frontend and
   register an account through the live UI, adding a place — that is what actually
   exercises CORS and JWT cross-origin:

   ```sh
   make smoke-web    # the page loads and its bundle resolves under the right base
   ```

   `make smoke-web` is the same check the deploy runs, so it reproduces a red
   `smoke` job locally without redeploying anything. It reads the site's URL from
   the Pages API; pass `URL=…` to point it elsewhere.

### How the pieces fit

- **Frontend — GitHub Pages** via `.github/workflows/deploy-frontend.yml`. Set
  the repository variable `API_URL` to your hosted backend (the build *fails* if
  it is unset, malformed, or if nothing serves `{"status":"ok"}` at
  `<API_URL>/health` — `scripts/api.sh preflight`, also `make api-preflight`),
  and `OAUTH_PROVIDERS` only once the OAuth apps exist. The base path is read from
  `actions/configure-pages` (`base_path` → `VITE_BASE`) rather than hardcoded,
  so it picks up the repo name and becomes `/` behind a custom domain.
  `postbuild` copies `index.html` → `404.html` for SPA deep links.

  Both `API_URL` and the base path are resolved at **build** time, and the
  workflow only triggers on pushes under `frontend/**`. Renaming the repo,
  adding a custom domain, or changing `API_URL` therefore does not redeploy on
  its own — the live bundle keeps the old values until you re-run the workflow
  via `workflow_dispatch`.

  **The deploy is not gated by a required status check, and cannot be.** The
  `protect-main` ruleset requires `backend-tests` and `frontend-build`; both run
  on the pull request, while `deploy-frontend.yml` runs on push to `main` — after
  the PR is gone, with nothing left to block. Worse, `frontend-build` compiles
  with `VITE_BASE` and `VITE_API_URL` unset, so it is green on exactly the
  configuration the deploy refuses to ship. A red deploy on `main` therefore
  blocks nothing, and once went unnoticed for five hours. Three things report it
  now, none of them a gate: the `smoke` job fails the deploy run when the
  published site does not load, the badges above go red, and `scripts/ci-alert.sh`
  files an issue that closes itself on the next green run. `Pages smoke test`
  re-checks the live site daily, which is what catches the *frontend* half of the
  build-time-config drift described above — the backend half is `make api-smoke`
  / `api-smoke.yml` (OpenAPI contract, not only `/health`). See
  [ADR-0017](docs/adr/0017-verify-the-pages-deploy.md) and
  [ADR-0019](docs/adr/0019-verify-the-api-deploy.md).

- **Backend — Render free web service** via `render.yaml` (Blueprint → point it
  at this repo, branch `main`, `autoDeployTrigger: commit`). Paste the Neon
  `DATABASE_URL` in the dashboard. `CORS_ORIGINS`
  and `FRONTEND_URL` are pinned to this repo's Pages origin and do **not**
  follow the frontend's base path — edit both if you fork, rename, or add a
  domain, or the browser will block every API call. `backend/start.sh` runs
  `alembic upgrade head` and, when `SEED_DEMO=true`, the demo seeder on each
  boot — both idempotent. Free services sleep after 15 min idle, so the first
  request back takes 30–60s; `plan: starter` ($7/mo) makes it always-on with no
  other change.

  After a `backend/` merge, `api-smoke.yml` polls the live host until OpenAPI
  shows the expected surface (`make api-smoke` locally). A green `/health` on a
  stale revision is not enough — that was issue #48.

  Note that `SEED_DEMO=true` creates a shared account with credentials
  committed to this repo, and the authenticated API allows writes — anyone who
  finds the demo can modify its data, and re-seeding will not restore it.

  Two health endpoints, deliberately split. `/health` is `healthCheckPath` and
  stays a static `{"status":"ok"}`: the platform polls it, so a database
  round-trip there would pay a Neon cold start on every probe and let a suspended
  database read as a dead process. `/health/db` does the `SELECT 1` and answers
  **503** when Postgres is unreachable — so a green health check plus a red
  `/health/db` is precisely "the API is up, the database is not".

- **DB — Neon free Postgres** (0.5 GB, scale-to-zero). The connection string
  needs rewriting before it works with asyncpg, and its region has to match
  `render.yaml`'s — see step 1 of the runbook above.

- **Later, AWS** — `pg_dump | pg_restore` into RDS, swap `DATABASE_URL`,
  `alembic upgrade head`. Nothing else changes.

## Project layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite
frontend/   Vite + React SPA (src/api, src/auth, src/pages, src/components)
ingest/     energlens-ingest CLI (Claude PDF extraction → API upload)
scripts/    db.sh + pgdev.sh — local Postgres without Docker
            api.sh — preflight / smoke for the *deployed* API (make api-preflight, make api-smoke)
```

Design notes worth knowing:

- Bills are stored as the periods they cover; monthly chart series are derived
  by prorating each bill across calendar months by day overlap. The
  “effective price” series is total paid ÷ kWh — the number that actually
  tracks what electricity costs you.
- Each bill snapshots the place's currency at creation, so changing a place's
  currency never rewrites history. No FX conversion is applied anywhere.
- `(place_id, utility_type, period_start, period_end)` is unique — importers
  are idempotent by construction.
- The schema is ready for gas/water later (`utility_type` + `unit` columns).
