#!/usr/bin/env sh
# Boot script for hosted deploys (Render free tier has no pre-deploy hook and no
# shell access, so migrations and seeding ride on startup).
set -e

# Activate the venv `uv sync` built at build time rather than depending on uv
# being on PATH at runtime.
. .venv/bin/activate

# No-op once already at head, so the cost on each cold-start wake is one query.
alembic upgrade head

# Idempotent (skips when demo@example.com exists). Never let it take the API
# down — a failed seed is a demo-data problem, not an outage.
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed || echo "seed skipped (non-fatal)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
