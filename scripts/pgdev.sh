#!/usr/bin/env bash
# Local PostgreSQL without Docker (macOS/Homebrew fallback).
# Runs a project-local data directory in .pgdata/ — nothing global is registered.
#
#   scripts/pgdev.sh init    # one-time: initdb + create user/databases
#   scripts/pgdev.sh start
#   scripts/pgdev.sh stop
#   scripts/pgdev.sh status
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGDATA="$ROOT/.pgdata"
PGBIN="${PGBIN:-$(brew --prefix postgresql@16 2>/dev/null)/bin}"
PGPORT="${PGPORT:-5432}"
LOG="$ROOT/.pglog"

case "${1:-}" in
  init)
    if [ -d "$PGDATA" ]; then echo ".pgdata already exists"; exit 0; fi
    "$PGBIN/initdb" -D "$PGDATA" -U energy --auth=trust --encoding=UTF8 >/dev/null
    "$PGBIN/pg_ctl" -D "$PGDATA" -l "$LOG" -o "-p $PGPORT" start >/dev/null
    "$PGBIN/createdb" -h localhost -p "$PGPORT" -U energy energlens
    "$PGBIN/createdb" -h localhost -p "$PGPORT" -U energy energlens_test
    echo "initialized: energlens + energlens_test on port $PGPORT (user: energy)"
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
