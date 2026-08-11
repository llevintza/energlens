#!/usr/bin/env sh
# Database lifecycle and diagnostics for local development.
#
#   scripts/db.sh up               start Postgres (pgdev, or docker compose)
#   scripts/db.sh down             stop it
#   scripts/db.sh ensure           create any missing databases (idempotent)
#   scripts/db.sh reset            DROP and recreate both databases
#   scripts/db.sh scratch          DROP and recreate the migrations scratch database
#   scripts/db.sh url <dev|test|scratch>   print the DSN for that database
#   scripts/db.sh preflight test   check the test database is usable
#   scripts/db.sh preflight dev    check the database alembic/uvicorn will use
#   scripts/db.sh shell [dev|test] open psql
#
# Every failure path prints the command that fixes it. Agents recover from
# actionable errors and thrash on raw ConnectionRefusedError / asyncpg
# tracebacks, which is the whole reason this script exists.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Defines and exports PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE/PGDATABASE_TEST/
# PGDATABASE_MIGRATIONS. The environment wins over the file, so
# `PGPORT=5433 make db-up` works.
. "$ROOT/scripts/db.env"

COMPOSE_FILE="$ROOT/docker-compose.yml"

# -f explicitly: recipes run in the caller's cwd, so `make -C .. db-up` from a
# subdirectory would otherwise fail compose's file discovery.
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# Names used before the energlens rename. Kept only so the preflight can
# recognise a pre-rename clone and say so, instead of reporting a bare
# "database does not exist" for a database the user believes they created.
LEGACY_MAIN=energy_tracker
LEGACY_TEST=energy_tracker_test

say() { printf '%s\n' "$*" >&2; }
die() { printf '%s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

# Homebrew's postgresql@16 is keg-only, so its binaries are never linked into
# PATH. pgdev.sh already resolves them through `brew --prefix`; do the same here
# rather than assuming psql happens to be on PATH.
if ! have psql && have brew; then
  if _brew_prefix="$(brew --prefix postgresql@16 2>/dev/null)"; then
    if [ -x "$_brew_prefix/bin/psql" ]; then
      PATH="$_brew_prefix/bin:$PATH"
      export PATH
    fi
  fi
fi

# README offers Docker as an alternative to installing Postgres, so a
# Docker-only machine legitimately has no client binaries. Run them inside the
# container instead of demanding an install the README never asked for.
IN_CONTAINER=""
if ! have psql && have docker && [ -f "$COMPOSE_FILE" ]; then
  if compose ps --status running db >/dev/null 2>&1; then
    IN_CONTAINER=1
  fi
fi

# PGHOST/PGPORT are deliberately not forwarded: inside the container the server
# is local, and passing the host's port would send it somewhere that isn't there.
pg() {
  if [ -n "$IN_CONTAINER" ]; then
    compose exec -T -e PGUSER="$PGUSER" -e PGPASSWORD="$PGPASSWORD" db "$@"
  else
    "$@"
  fi
}

client_available() { [ -n "$IN_CONTAINER" ] || have psql; }

# -tAX: tuples only, unaligned, ignore ~/.psqlrc (which can print banners).
query() { pg psql -d "$1" -tAXc "$2" 2>/dev/null; }

db_exists() { [ "$(query postgres "SELECT 1 FROM pg_database WHERE datname='$1'")" = "1" ]; }

server_up() { pg pg_isready -q >/dev/null 2>&1; }

# Accept DSNs with or without userinfo: `postgresql://host/db` has no '@', and a
# pattern that requires one silently yields an empty host, which then reads as
# "local" to every check below.
url_host() {
  printf '%s' "$1" | sed -e 's|^[^:]*://||' -e 's|^[^@/]*@||' -e 's|[:/?].*$||'
}

url_port() {
  hostport=$(printf '%s' "$1" | sed -e 's|^[^:]*://||' -e 's|^[^@/]*@||' -e 's|[/?].*$||')
  case "$hostport" in
    *:*) printf '%s' "${hostport##*:}" ;;
    *) printf '%s' "$PGPORT" ;;
  esac
}

url_db() {
  printf '%s' "$1" | sed -e 's|^[^:]*://||' -e 's|^[^@/]*@||' -e 's|^[^/]*/||' -e 's|?.*$||'
}

is_local_host() {
  case "$1" in
    '' | localhost | 127.0.0.1 | ::1 | 0.0.0.0 | host.docker.internal) return 0 ;;
    *) return 1 ;;
  esac
}

target_db() {
  case "${1:-test}" in
    dev | main) printf '%s' "$PGDATABASE" ;;
    test) printf '%s' "$PGDATABASE_TEST" ;;
    scratch) printf '%s' "$PGDATABASE_MIGRATIONS" ;;
    *) die "usage: $0 <preflight|url|shell> <dev|test|scratch>" ;;
  esac
}

cmd_url() {
  printf 'postgresql+asyncpg://%s:%s@%s:%s/%s\n' \
    "$PGUSER" "$PGPASSWORD" "$PGHOST" "$PGPORT" "$(target_db "${1:-test}")"
}

# The destructive commands connect with libpq's PGHOST, so checking only
# DATABASE_URL leaves the actual connection unguarded. Check both.
refuse_remote() {
  what="$1"
  fix="${2:-make test-backend}"
  bad=""
  is_local_host "$PGHOST" || bad="PGHOST=$PGHOST"
  if [ -z "$bad" ] && [ -n "${DATABASE_URL:-}" ]; then
    is_local_host "$(url_host "$DATABASE_URL")" \
      || bad="DATABASE_URL host $(url_host "$DATABASE_URL")"
  fi
  [ -n "$bad" ] || return 0
  say "Refusing to run destructive database work: $bad is not localhost."
  say "$what drops every table in the target database."
  say ""
  say "Fix: env -u DATABASE_URL PGHOST=localhost $fix"
  exit 1
}

wait_ready() {
  n=0
  while [ "$n" -lt 60 ]; do
    server_up && return 0
    n=$((n + 1))
    sleep 0.5
  done
  return 1
}

cmd_up() {
  if [ -d "$ROOT/.pgdata" ]; then
    # pgdev.sh prints a specific diagnostic when the port is already taken by
    # another postmaster. Swallowing it would let wait_ready succeed against
    # that foreign cluster and cmd_ensure create databases on it.
    if ! "$ROOT/scripts/pgdev.sh" start; then
      say ""
      say "Fix: make db-down, or stop whatever else is listening on $PGHOST:$PGPORT,"
      say "     or run this project's cluster elsewhere with PGPORT=5433 make db-up"
      exit 1
    fi
  elif have docker && [ -f "$COMPOSE_FILE" ]; then
    say "No .pgdata directory — starting the docker-compose 'db' service."
    # POSTGRES_DB explicitly, not --env-file: compose names this variable
    # POSTGRES_DB while db.env calls it PGDATABASE, so an env-file would leave
    # it unset and silently fall back to the literal in docker-compose.yml.
    POSTGRES_DB="$PGDATABASE" PGPORT="$PGPORT" compose up -d
    have psql || IN_CONTAINER=1
  else
    say "First run on this machine — initialising a project-local cluster in .pgdata/"
    "$ROOT/scripts/pgdev.sh" init
  fi

  if ! wait_ready; then
    say "Postgres did not become ready on $PGHOST:$PGPORT within 30s."
    say ""
    say "Fix: check $ROOT/.pglog, or 'docker compose logs db' if you use Docker."
    exit 1
  fi
  cmd_ensure
}

cmd_down() {
  if [ -d "$ROOT/.pgdata" ]; then
    "$ROOT/scripts/pgdev.sh" stop
  elif have docker && [ -f "$COMPOSE_FILE" ]; then
    compose down
  else
    say "Nothing to stop: no .pgdata directory and no docker."
  fi
}

require_client() {
  client_available && return 0
  die "error: no psql on PATH and no running db container.
     Fix: brew install postgresql@16   (or start Docker and rerun 'make db-up')"
}

# Idempotent, and the only creation path used by local dev, Docker and CI
# alike — so a database that exists in one of them exists in all three.
cmd_ensure() {
  require_client
  server_up || {
    say "Postgres is not accepting connections on $PGHOST:$PGPORT."
    say ""
    say "Fix: make db-up"
    exit 1
  }
  for db in "$PGDATABASE" "$PGDATABASE_TEST"; do
    if db_exists "$db"; then
      note "  $db already exists"
    else
      pg createdb "$db"
      note "  $db created"
    fi
  done
}

drop_and_create() {
  if db_exists "$1"; then
    # Idle sessions (a stopped dev server, an open psql) block DROP DATABASE.
    query postgres "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                    WHERE datname='$1' AND pid <> pg_backend_pid()" >/dev/null || true
    pg dropdb "$1"
  fi
  pg createdb "$1"
}

cmd_reset() {
  refuse_remote "make db-reset" "make db-reset"
  require_client
  server_up || { say "Postgres is not running."; say ""; say "Fix: make db-up"; exit 1; }
  for db in "$PGDATABASE" "$PGDATABASE_TEST"; do
    drop_and_create "$db"
    note "  $db recreated"
  done
}

# A throwaway database built only by Alembic. `alembic check` against the test
# database would be vacuous: conftest.py builds that schema with
# Base.metadata.create_all, so it always matches the models it was created from,
# and the drift the check exists to catch is invisible.
cmd_scratch() {
  refuse_remote "make migrate-check" "make migrate-check"
  require_client
  drop_and_create "$PGDATABASE_MIGRATIONS"
}

cmd_shell() { exec psql -d "$(target_db "${1:-dev}")"; }

cmd_preflight() {
  role="${1:-test}"
  db="$(target_db "$role")"

  # Without a client we cannot diagnose anything. Say so and get out of the way
  # rather than blocking a run that might well succeed.
  if ! client_available; then
    say "note: no psql on PATH — skipping database preflight."
    say "      Install postgresql@16 for diagnostics that name the fix."
    return 0
  fi

  if [ "$role" = "test" ]; then
    refuse_remote "The test suite" "make test-backend"
  elif [ -n "${DATABASE_URL:-}" ]; then
    # alembic and uvicorn read DATABASE_URL from .env, not db.env. Validating
    # anything else would gate a working setup on an unrelated connection.
    PGHOST="$(url_host "$DATABASE_URL")"
    PGPORT="$(url_port "$DATABASE_URL")"
    db="$(url_db "$DATABASE_URL")"
    export PGHOST PGPORT
  fi

  if ! server_up; then
    say "Postgres is not accepting connections on $PGHOST:$PGPORT."
    say ""
    say "Fix: make db-up"
    say "     (first run on this machine also creates .pgdata and both databases)"
    exit 1
  fi

  # Reaching the postmaster proves nothing about the role: another cluster on
  # the same port answers just as readily, and then every later error is about
  # a database that "should" exist.
  if ! query postgres "SELECT 1" >/dev/null 2>&1; then
    say "Postgres is running on $PGHOST:$PGPORT but role '$PGUSER' cannot connect."
    say "Something else probably owns this port — Postgres.app, a system cluster,"
    say "or a container left over from another project."
    say ""
    say "Fix: PGPORT=5433 make db-up      # run this project's cluster elsewhere"
    say "     (then set PGPORT in scripts/db.env and DATABASE_URL in .env to match)"
    say "Or:  createuser -s $PGUSER       # if this cluster is the one you want"
    exit 1
  fi

  if db_exists "$db"; then
    return 0
  fi

  # Distinguish "you never created it" from "you created it under its old
  # name", because the second looks identical from inside the application and
  # sends people hunting for a bug that isn't there.
  legacy="$LEGACY_TEST"
  [ "$role" != "test" ] && legacy="$LEGACY_MAIN"
  if db_exists "$legacy"; then
    say "Database '$db' does not exist, but '$legacy' does — this clone predates"
    say "the energlens rename (#5)."
    say ""
    say "Fix: make db-ensure       # create the new databases, leaving the old ones alone"
    say "Or:  psql -d postgres -c 'ALTER DATABASE $legacy RENAME TO $db'   # keep your data"
    say ""
    say "See \"Migrating a pre-rename setup\" in README.md."
    exit 1
  fi

  if [ -f "$ROOT/.env" ] && grep -q "$LEGACY_MAIN" "$ROOT/.env" 2>/dev/null; then
    say "Database '$db' does not exist, and your .env still names '$LEGACY_MAIN'."
    say "A stale DATABASE_URL keeps the app on the old database while the test"
    say "suite uses the new one."
    say ""
    say "Fix: set DATABASE_URL=$(cmd_url dev) in .env (see .env.example),"
    say "     then: make db-ensure"
    exit 1
  fi

  say "Database '$db' does not exist."
  say ""
  say "Fix: make db-ensure"
  exit 1
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  ensure) cmd_ensure ;;
  reset) cmd_reset ;;
  scratch) cmd_scratch ;;
  url) shift; cmd_url "${1:-test}" ;;
  preflight) shift; cmd_preflight "${1:-test}" ;;
  shell) shift; cmd_shell "${1:-dev}" ;;
  *) die "usage: $0 <up|down|ensure|reset|scratch|url|preflight|shell> [dev|test|scratch]" ;;
esac
