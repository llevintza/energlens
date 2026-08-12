# 0004. Use PostgreSQL as the datastore

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** llevintza
- **Landed in:** PR #1 (`81b373b`)
- **Related:** [ADR-0005](0005-alembic-migrations-and-three-databases.md), [ADR-0012](0012-database-hosting-neon.md)

## Context

The data is small but not simple. Bills are *periods* with arbitrary boundaries — a
Portuguese bill runs calendar months, a Romanian one runs the 15th to the 14th — and
monthly series are derived by day-overlap proration rather than stored. Money and
consumption must not suffer floating-point drift. Imports must be idempotent, because
the same PDF may be ingested twice.

Total volume for two properties over a decade is on the order of a few hundred rows.

## Decision

We use **PostgreSQL**, relying specifically on four features:

| Feature | Used for |
| --- | --- |
| `NUMERIC` | Money and kWh — exact decimal, no float drift |
| `DATE` + range arithmetic | Period overlap proration in `services/series.py` |
| `UNIQUE (place_id, utility_type, period_start, period_end)` | Idempotent ingestion — a re-import conflicts instead of duplicating |
| `ON DELETE CASCADE` | Deleting a user or place removes its bills without application code |

## Consequences

### What this buys

- **Correct money arithmetic by default.** `NUMERIC` is the single most important
  reason for this choice; a float-based store would accumulate error across
  proration and aggregation.
- **The uniqueness constraint makes ingestion safe to retry**, which is what allows
  the ingest CLI to be dumb about deduplication.
- Portable: `pg_dump` output moves to any Postgres anywhere, which keeps
  [ADR-0012](0012-database-hosting-neon.md) cheap to reverse.
- Universally available as a managed service, so hosting stays a commodity decision.

### What this costs

- **A server is required.** Local development needs a running Postgres, which is why
  `scripts/pgdev.sh` and a docker-compose service both exist and why `make db-up`
  has to paper over two provisioning paths.
- Heavier than the dataset strictly justifies — a few hundred rows do not need a
  relational server. The justification is correctness and portability, not scale.
- Async access needs a separate driver (`asyncpg`) and its own dialect quirks
  ([ADR-0003](0003-fastapi-async-sqlalchemy-asyncpg.md)).

## Limitations

- Concurrency and connection count are bounded by the host tier; on Neon free this
  interacts badly with pgbouncer ([ADR-0012](0012-database-hosting-neon.md)).
- No built-in time-series features; proration is application code
  (`services/series.py`), which is the right place for it but is hand-written and
  therefore worth its unit tests.
- Schema changes require migrations ([ADR-0005](0005-alembic-migrations-and-three-databases.md)).

## Alternatives considered

| Option | Why not |
| --- | --- |
| **SQLite** | Tempting at this size and needs no server — but Render free has no persistent disk, and `NUMERIC` is not a real type in SQLite (it stores as REAL/TEXT), which undermines the main reason for the choice |
| **MySQL / MariaDB** | `DECIMAL` is fine, but date-range handling is clumsier and the managed free-tier ecosystem is thinner |
| **MongoDB** | No schema enforcement and no cheap uniqueness across a compound period key; the data is inherently relational |
| **DuckDB** | Excellent analytics, wrong shape for a transactional web app |
| **A time-series database** (Influx, Timescale) | Bills are irregular periods, not evenly spaced samples; the proration logic is the hard part and TSDBs do not help with it |

## Revisit when

- [ ] **Query patterns become analytical** over millions of rows → a columnar store
      alongside Postgres, not instead of it.
- [ ] **Multi-tenant scale arrives** → partitioning or sharding, still Postgres.
- [ ] **The proration logic outgrows hand-written SQL/Python** → consider TimescaleDB,
      which is a Postgres extension and therefore not a migration.
- [ ] **Offline-first or on-device storage becomes a requirement** → SQLite returns to
      the table, with the `NUMERIC` caveat handled explicitly in application code.

## Migration path

Moving *hosts* is easy and covered in [ADR-0012](0012-database-hosting-neon.md).
Moving *engines* is not: `NUMERIC` semantics, `ON DELETE CASCADE`, and the compound
unique constraint would all need equivalents, and `services/series.py` assumes exact
decimal arithmetic. Treat an engine change as a rewrite of the data layer, not a
configuration change.
