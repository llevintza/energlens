#!/usr/bin/env bash
# Local PostgreSQL without Docker (macOS/Homebrew fallback).
# Runs a project-local data directory in .pgdata/ — nothing global is registered.
#
#   scripts/pgdev.sh init    # initdb + create user/databases (safe to re-run)
#   scripts/pgdev.sh start
#   scripts/pgdev.sh stop
#   scripts/pgdev.sh status
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGDATA="$ROOT/.pgdata"
PGPORT="${PGPORT:-5432}"
LOG="$ROOT/.pglog"

# The database names live here only; everything else derives from them.
DB_MAIN="${PGDATABASE:-energlens}"
DB_TEST="${PGDATABASE_TEST:-${DB_MAIN}_test}"

if [ -z "${PGBIN:-}" ]; then
  if ! brew_prefix="$(brew --prefix postgresql@16 2>/dev/null)"; then
    echo "error: Homebrew not found on PATH — install postgresql@16 and set PGBIN" >&2
    echo "       to its bin directory, or use Docker (docker compose up -d)." >&2
    exit 1
  fi
  PGBIN="$brew_prefix/bin"
fi
if [ ! -x "$PGBIN/pg_ctl" ]; then
  echo "error: no Postgres binaries in $PGBIN — run 'brew install postgresql@16'" >&2
  exit 1
fi

# Server must be up before createdb; safe to call when it is already running.
ensure_running() {
  if "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then return 0; fi
  if ! "$PGBIN/pg_ctl" -D "$PGDATA" -l "$LOG" -o "-p $PGPORT" start >/dev/null; then
    echo "error: Postgres failed to start on port $PGPORT — see $LOG" >&2
    echo "       (is the docker-compose 'db' service already bound to it?)" >&2
    exit 1
  fi
}

# createdb errors when the database exists, which must not fail a re-run.
ensure_db() {
  if "$PGBIN/psql" -h localhost -p "$PGPORT" -U energy -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname = '$1'" | grep -q 1; then
    echo "  $1 already exists"
  else
    "$PGBIN/createdb" -h localhost -p "$PGPORT" -U energy "$1"
    echo "  $1 created"
  fi
}

case "${1:-}" in
  init)
    # Idempotent by design: a rename, an interrupted first run, or a half
    # initialized .pgdata all have to be repairable by re-running init.
    if [ ! -d "$PGDATA" ]; then
      "$PGBIN/initdb" -D "$PGDATA" -U energy --auth=trust --encoding=UTF8 >/dev/null
    fi
    ensure_running
    ensure_db "$DB_MAIN"
    ensure_db "$DB_TEST"
    echo "ready: $DB_MAIN + $DB_TEST on port $PGPORT (user: energy)"
    ;;
  start)
    "$PGBIN/pg_ctl" -D "$PGDATA" -l "$LOG" -o "-p $PGPORT" start
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGDATA" stop
    ;;
  status)
    "$PGBIN/pg_ctl" -D "$PGDATA" status
    ;;
  *)
    echo "usage: $0 {init|start|stop|status}" >&2
    exit 1
    ;;
esac
