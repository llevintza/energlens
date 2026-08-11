#!/usr/bin/env sh
# Database lifecycle and diagnostics for local development.
#
#   scripts/db.sh up               start Postgres (pgdev, or docker compose)
#   scripts/db.sh down             stop it
#   scripts/db.sh ensure           create any missing databases (idempotent)
#   scripts/db.sh reset            DROP and recreate both databases
#   scripts/db.sh preflight test   check the test database is usable
#   scripts/db.sh preflight dev    check the app database is usable
#   scripts/db.sh shell [dev|test] open psql
#
# Every failure path prints the command that fixes it. Agents recover from
# actionable errors and thrash on raw ConnectionRefusedError / asyncpg
# tracebacks, which is the whole reason this script exists.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Defines and exports PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE/PGDATABASE_TEST,
# letting everything below call bare psql/createdb/pg_isready. The environment
# wins over the file, so `PGPORT=5433 make db-up` works.
. "$ROOT/scripts/db.env"

# Names used before the energlens rename. Kept only so the preflight can
# recognise a pre-rename clone and say so, instead of reporting a bare
# "database does not exist" for a database the user believes they created.
LEGACY_MAIN=energy_tracker
LEGACY_TEST=energy_tracker_test

say() { printf '%s\n' "$*" >&2; }
die() { printf '%s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# -tAX: tuples only, unaligned, ignore ~/.psqlrc (which can print banners).
query() { psql -d "$1" -tAXc "$2" 2>/dev/null; }

db_exists() { [ "$(query postgres "SELECT 1 FROM pg_database WHERE datname='$1'")" = "1" ]; }

server_up() { pg_isready -q >/dev/null 2>&1; }

target_db() {
  case "${1:-test}" in
    dev|main) printf '%s' "$PGDATABASE" ;;
    test)     printf '%s' "$PGDATABASE_TEST" ;;
    *)        die "usage: $0 preflight <dev|test>" ;;
  esac
}

# A DATABASE_URL aimed at a remote host plus a command that drops tables is the
# one combination in this repo that can destroy something irreplaceable. The
# test suite drops every table on every run.
refuse_remote() {
  url="${DATABASE_URL:-}"
  [ -n "$url" ] || return 0
  host=$(printf '%s' "$url" | sed -n 's|^[^:]*://[^@]*@\([^:/?]*\).*|\1|p')
  case "$host" in
    ''|localhost|127.0.0.1|::1|0.0.0.0) return 0 ;;
  esac
  say "Refusing to run destructive database work: DATABASE_URL points at '$host',"
  say "not localhost. $1 drops every table in the target database."
  say ""
  say "Fix: env -u DATABASE_URL make ${MAKE_TARGET:-test-backend}"
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
    "$ROOT/scripts/pgdev.sh" start >/dev/null 2>&1 || true
  elif have docker && [ -f "$ROOT/docker-compose.yml" ]; then
    say "No .pgdata directory — starting the docker-compose 'db' service."
    # POSTGRES_DB explicitly, not --env-file: compose names this variable
    # POSTGRES_DB while db.env calls it PGDATABASE, so an env-file would leave
    # it unset and silently fall back to the literal in docker-compose.yml.
    POSTGRES_DB="$PGDATABASE" docker compose up -d
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
  elif have docker && [ -f "$ROOT/docker-compose.yml" ]; then
    docker compose down
  else
    say "Nothing to stop: no .pgdata directory and no docker."
  fi
}

# Idempotent, and the only creation path used by local dev, Docker and CI
# alike — so a database that exists in one of them exists in all three.
cmd_ensure() {
  have psql || die "error: psql not found. Install postgresql@16, or use Docker."
  server_up || {
    say "Postgres is not accepting connections on $PGHOST:$PGPORT."
    say ""
    say "Fix: make db-up"
    exit 1
  }
  for db in "$PGDATABASE" "$PGDATABASE_TEST"; do
    if db_exists "$db"; then
      say "  $db already exists"
    else
      createdb "$db"
      say "  $db created"
    fi
  done
}

cmd_reset() {
  MAKE_TARGET=db-reset refuse_remote "make db-reset"
  server_up || { say "Postgres is not running."; say ""; say "Fix: make db-up"; exit 1; }
  for db in "$PGDATABASE" "$PGDATABASE_TEST"; do
    if db_exists "$db"; then
      # Idle sessions (a stopped dev server, an open psql) block DROP DATABASE.
      query postgres "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                      WHERE datname='$db' AND pid <> pg_backend_pid()" >/dev/null || true
      dropdb "$db"
    fi
    createdb "$db"
    say "  $db recreated"
  done
}

cmd_shell() { exec psql -d "$(target_db "${1:-dev}")"; }

cmd_preflight() {
  role="${1:-test}"
  db="$(target_db "$role")"

  # Without psql we cannot diagnose anything. Say so and get out of the way
  # rather than blocking a run that might well succeed.
  if ! have psql; then
    say "note: psql not found — skipping database preflight."
    say "      Install postgresql@16 for diagnostics that name the fix."
    return 0
  fi

  [ "$role" = "test" ] && MAKE_TARGET=test-backend refuse_remote "The test suite"

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
    say "Fix: set DATABASE_URL=postgresql+asyncpg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE"
    say "     in .env (see .env.example), then: make db-ensure"
    exit 1
  fi

  say "Database '$db' does not exist."
  say ""
  say "Fix: make db-ensure"
  exit 1
}

case "${1:-}" in
  up)        cmd_up ;;
  down)      cmd_down ;;
  ensure)    cmd_ensure ;;
  reset)     cmd_reset ;;
  preflight) shift; cmd_preflight "${1:-test}" ;;
  shell)     shift; cmd_shell "${1:-dev}" ;;
  *) die "usage: $0 <up|down|ensure|reset|preflight [dev|test]|shell [dev|test]>" ;;
esac
