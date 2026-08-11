#!/bin/sh
# Runs once, inside the postgres container, when the data volume is empty.
#
# POSTGRES_DB creates a single database, so without this the Docker path gives
# you energlens but never energlens_test, and the first `pytest` on a Docker
# setup dies on InvalidCatalogNameError for a database the user was never told
# to create. scripts/pgdev.sh (the no-Docker path) creates both, so the two
# backends behaved differently for no reason.
#
# Like POSTGRES_DB, this only fires on an empty volume. An existing volume needs
# `make db-ensure` — see "Migrating a pre-rename setup" in README.md.
set -eu

TEST_DB="${PGDATABASE_TEST:-energlens_test}"

# Bound as a psql variable, not interpolated by the shell: :'db' quotes it as a
# literal for the lookup and format('%I') quotes it as an identifier for the
# CREATE, so a name needing quotes (energlens-test) works and one containing a
# quote cannot rewrite the statement.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
     -v db="$TEST_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'db')
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db')\gexec
SQL

echo "created $TEST_DB"
