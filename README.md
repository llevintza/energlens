# ⚡ Energy Tracker

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
PostgreSQL — either Docker (`docker compose up -d`) or, without Docker,
Homebrew Postgres with a project-local data dir:

```sh
brew install postgresql@16
scripts/pgdev.sh init        # one-time: creates .pgdata + energy_tracker DBs
scripts/pgdev.sh start       # later sessions
```

Then:

```sh
cp .env.example .env         # adjust JWT_SECRET at minimum

# Backend (http://localhost:8000, docs at /docs)
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seed    # demo@example.com / demo1234 with 2 years of data
uv run uvicorn app.main:app --reload

# Frontend (http://localhost:5173)
cd ../frontend
npm install
npm run dev
```

Log in as `demo@example.com` / `demo1234` to see seeded charts, or register
your own account.

## Tests

```sh
cd backend && uv run pytest    # needs the energy_tracker_test DB (pgdev init creates it)
cd ingest  && uv run pytest
cd frontend && npx tsc -b      # typecheck
```

## Importing your real bills

```sh
cd ingest && uv sync
export ANTHROPIC_API_KEY=sk-ant-...
export ET_EMAIL=you@example.com ET_PASSWORD=...

# 1. Extract + review (no upload, results cached by file hash in extracted.jsonl)
uv run energy-ingest extract --dir ~/bills/main-residence --dry-run

# 2. Upload to a place (get the place UUID from the UI or GET /places)
uv run energy-ingest run --dir ~/bills/main-residence --place-id <uuid>
```

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

## Deployment

- **Frontend** — GitHub Pages via `.github/workflows/deploy-frontend.yml`.
  Set repository variables `API_URL` (your hosted backend) and optionally
  `OAUTH_PROVIDERS`. The build uses base path `/energy-tracker/` and copies
  `index.html` → `404.html` for SPA deep links.
- **Backend + DB, cheap tier** — Neon (free Postgres) + Render free web
  service or a small Fly.io machine. Point `DATABASE_URL` at Neon, run
  `alembic upgrade head`, add your Pages origin to `CORS_ORIGINS`.
- **Later, AWS** — `pg_dump | pg_restore` into RDS, swap `DATABASE_URL`,
  `alembic upgrade head`. Nothing else changes.

## Project layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite
frontend/   Vite + React SPA (src/api, src/auth, src/pages, src/components)
ingest/     energy-ingest CLI (Claude PDF extraction → API upload)
scripts/    pgdev.sh — local Postgres without Docker
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
