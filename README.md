# ⚡ Energlens

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

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, and
PostgreSQL — either Docker or, without Docker, Homebrew Postgres
(`brew install postgresql@16`), which `make db-up` will set up in a
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
make typecheck                 # the frontend has no test runner
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

Re-runs skip already-uploaded periods (the API returns 409 for duplicates) and
never re-pay extraction for unchanged files. Extraction uses Claude
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

- **Frontend — GitHub Pages** via `.github/workflows/deploy-frontend.yml`. Set
  the repository variable `API_URL` to your hosted backend (the build *fails*
  if it is unset, rather than shipping a bundle pointed at localhost), and
  `OAUTH_PROVIDERS` only once the OAuth apps exist. The base path is read from
  `actions/configure-pages` (`base_path` → `VITE_BASE`) rather than hardcoded,
  so it picks up the repo name and becomes `/` behind a custom domain.
  `postbuild` copies `index.html` → `404.html` for SPA deep links.

  Both `API_URL` and the base path are resolved at **build** time, and the
  workflow only triggers on pushes under `frontend/**`. Renaming the repo,
  adding a custom domain, or changing `API_URL` therefore does not redeploy on
  its own — the live bundle keeps the old values until you re-run the workflow
  via `workflow_dispatch`.

- **Backend — Render free web service** via `render.yaml` (Blueprint → point it
  at this repo). Paste the Neon `DATABASE_URL` in the dashboard. `CORS_ORIGINS`
  and `FRONTEND_URL` are pinned to this repo's Pages origin and do **not**
  follow the frontend's base path — edit both if you fork, rename, or add a
  domain, or the browser will block every API call. `backend/start.sh` runs
  `alembic upgrade head` and, when `SEED_DEMO=true`, the demo seeder on each
  boot — both idempotent. Free services sleep after 15 min idle, so the first
  request back takes 30–60s; `plan: starter` ($7/mo) makes it always-on with no
  other change.

  Note that `SEED_DEMO=true` creates a shared account with credentials
  committed to this repo, and the authenticated API allows writes — anyone who
  finds the demo can modify its data, and re-seeding will not restore it.

- **DB — Neon free Postgres** (0.5 GB, scale-to-zero). Two DSN gotchas: use the
  **direct** endpoint, not `-pooler` (pgbouncer's transaction mode breaks
  asyncpg's prepared-statement cache), and write `?ssl=require`, not
  `?sslmode=require` (`sslmode` is libpq-only; asyncpg raises on it):

  ```
  postgresql+asyncpg://<user>:<pass>@ep-xxxx.eu-central-1.aws.neon.tech/energlens?ssl=require
  ```

- **Later, AWS** — `pg_dump | pg_restore` into RDS, swap `DATABASE_URL`,
  `alembic upgrade head`. Nothing else changes.

## Project layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite
frontend/   Vite + React SPA (src/api, src/auth, src/pages, src/components)
ingest/     energlens-ingest CLI (Claude PDF extraction → API upload)
scripts/    pgdev.sh — local Postgres without Docker
docs/design/  UI redesign handoff — open the .dc.html files in a browser
```

`docs/design/README.md` is the spec for the front-end redesign: tokens, screen
frames (2a, 2b, 3a–3g), a chart catalogue, and the derived metrics behind every
figure. The two `.dc.html` files are scrollable prototype canvases and need
`support.js` beside them; they open directly, with no build step or server.

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
