#!/usr/bin/env sh
# Boot script for hosted deploys (Render free tier has no pre-deploy hook and no
# shell access, so migrations and seeding ride on startup).
set -e

# Activate the venv `uv sync` built at build time rather than depending on uv
# being on PATH at runtime.
. .venv/bin/activate

# Fail with a message that names the variable. Without this the app falls back
# to its localhost default and the first symptom is a ConnectionRefusedError
# against 127.0.0.1:5432, which reads like a networking or SSL problem.
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set — set it on the service before deploying." >&2
  exit 1
fi

# No-op once already at head, so the cost on each cold-start wake is one query.
alembic upgrade head

# Idempotent (skips when demo@example.com exists). Never let it take the API
# down — a failed seed is a demo-data problem, not an outage — but say so
# loudly, otherwise a broken demo login boots green and looks identical to the
# normal already-seeded path.
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed \
    || echo "ERROR: demo seed failed — API is up but demo login will not work" >&2
fi

# PORT is supplied by the host; default it so the script also works when run by
# hand. --forwarded-allow-ips: the platform's TLS-terminating proxy connects
# from a non-loopback address, and without trusting it request.url_for builds
# http:// URLs — which breaks the OAuth callback with redirect_uri_mismatch.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --forwarded-allow-ips '*'
