# 0012. Host the database on Neon serverless Postgres

- **Status:** Accepted
- **Date:** 2026-08-10 (decided), 2026-08-11 (provisioned)
- **Deciders:** llevintza
- **Landed in:** PR #3 (`d1caed3`) — provisioned during issue #7
- **Related:** [ADR-0004](0004-postgresql-as-the-datastore.md), [ADR-0011](0011-backend-hosting-render.md), [ADR-0013](0013-co-locate-api-and-database-region.md)

## Context

[ADR-0004](0004-postgresql-as-the-datastore.md) commits us to PostgreSQL. This decision
is only about *who runs it*.

Requirements: a genuinely free tier with no expiry, real managed Postgres (not a
Postgres-compatible dialect), reachable over TLS from a third-party host, and — since
the workload is one user and a periodic ingest — something that does not charge for
idle capacity. Storage needs are tiny: a decade of bills for two properties is
kilobytes.

Render offers its own managed Postgres, which would have been the obvious pairing.
Its free tier **expires after 30 days**, which disqualified it outright: the failure
mode is total data loss on a date nobody remembers.

## Decision

We use **Neon serverless Postgres on the free tier**, in AWS `us-east-2`, connected
via `asyncpg` over TLS.

The connection string is the entire integration surface, and it must be rewritten
from what the Neon console produces:

```
# What Neon gives you
postgresql://user:pass@ep-xxx-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require

# What this application needs
postgresql+asyncpg://user:pass@ep-xxx.c-4.us-east-2.aws.neon.tech/neondb?ssl=require
```

| Rewrite | Why it is mandatory |
| --- | --- |
| `postgresql://` → `postgresql+asyncpg://` | SQLAlchemy driver selection |
| delete `-pooler` — **and nothing else** | pgbouncer's transaction mode breaks asyncpg's prepared-statement cache |
| `?sslmode=…&channel_binding=…` → `?ssl=require` | Both are libpq-only; asyncpg raises `TypeError: connect() got an unexpected keyword argument 'sslmode'` |

**The middle row has a trap that cost real time.** The `c-N` segment sitting next to
`-pooler` looks like part of the region, and "use the direct endpoint" reads as
"strip the pooler prefix". It is not: `c-N` is part of the endpoint identity, and
Neon routes by SNI. Remove it and the hostname still resolves, still completes a TLS
handshake, and *then* fails with `InvalidPasswordError` — sending you to inspect the
credential instead of the hostname. DNS offers no help; every candidate name
resolves. Verified against the live endpoint:

| Candidate | Result |
| --- | --- |
| `ep-xxx.c-4.us-east-2…` (drop only `-pooler`) | connects |
| `ep-xxx.us-east-2…` (also drop `c-4`) | `InvalidPasswordError` |
| `?sslmode=require` | `TypeError … 'sslmode'` |

Two pieces of application code exist specifically for this provider:

- **`pool_pre_ping=True`** ([`backend/app/db.py`](../../backend/app/db.py)) — Neon
  suspends after ~5 minutes idle and drops the server side of pooled connections
  while our process stays alive. Without a liveness check, the first query after an
  idle gap fails with `ConnectionDoesNotExistError` rather than reconnecting.
- **`%` escaping in Alembic** ([`backend/alembic/env.py`](../../backend/alembic/env.py))
  — the DSN passes through ConfigParser, which treats `%` as interpolation syntax, so
  a percent-encoded character in a generated password raises `InterpolationSyntaxError`
  even though the same DSN works everywhere else.

## Consequences

### What this buys

- **Free with no expiry clock**, unlike Render Postgres.
- **Real PostgreSQL 18** — no dialect compromises, and `pg_dump` output is portable
  to any other Postgres anywhere.
- **Scale-to-zero** matches a workload that is idle almost always.
- **Branching** (a Neon feature we do not yet use) would give per-PR database copies
  cheaply if integration testing ever needs them.

### What this costs

- **A second cold start stacked on Render's.** A first request after a long idle
  wakes Render *and* Neon.
- **The DSN is easy to get wrong in three separate ways**, none of which fail at paste
  time — all fail at runtime, and two of them fail *misleadingly*. This is why the
  rewrite table above is in the README runbook as well.
- **Connection pooling is unavailable to us.** The `-pooler` endpoint exists precisely
  to conserve connections, and asyncpg's prepared-statement cache cannot use it. With
  one instance this is irrelevant; it becomes a real constraint the moment we scale
  horizontally.
- **No automated backup that we control.** Neon's free tier retains a limited
  restore window; there is no `pg_dump` to storage we own.

## Limitations

| Limit | Free tier | Consequence |
| --- | --- | --- |
| Storage | 0.5 GB | Thousands of years of bills for two properties — not a real constraint |
| Compute | 0.25 vCPU, autosuspend ~5 min | Cold-start latency on the first query |
| Projects | 1 | No separate staging database without a second account |
| Point-in-time restore | short window | **The real gap** — see below |
| Connection pooling | pgbouncer only, unusable with asyncpg | Blocks horizontal scaling |

**Backups are the genuine risk here, not storage.** Free-tier history retention is
short, and nothing currently exports data anywhere we control. Today the only data is
regenerable demo seed, so the exposure is zero — but it becomes material the moment
real bills are entered. That is a revisit trigger below, not a theoretical concern.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Render Postgres** | Free tier **expires after 30 days** — data loss on a forgotten date. Disqualifying |
| **Supabase** | Comparable free Postgres, but bundles auth/storage/realtime we do not use, and free projects pause after inactivity; we already have auth ([ADR-0006](0006-fastapi-users-jwt-auth.md)) |
| **AWS RDS** | No perpetual free tier; needs VPC and networking work. The intended destination *later*, not now |
| **SQLite on a volume** | Render free has no persistent disk; loses the concurrency and type guarantees of [ADR-0004](0004-postgresql-as-the-datastore.md) |
| **CockroachDB Serverless** | Generous free tier, but Postgres-*compatible*, not Postgres; risks subtle divergence in migrations and `numeric` handling |
| **Self-hosted on a VPS** | We would own backups, patching and TLS — the thing we are avoiding |

## Revisit when

- [ ] **Real bills are entered** → backups stop being optional. Cheapest fix: a
      scheduled `pg_dump` to object storage or a private repo. **This is the trigger
      most likely to fire first.**
- [ ] **Storage approaches 0.5 GB** — implausible for this data shape, but free.
- [ ] **More than one API instance is needed** → the no-pooling constraint becomes
      binding; needs either the pooler with `statement_cache_size=0` on asyncpg, or a
      different host.
- [ ] **A staging environment is wanted** → free tier is one project; Neon branching
      or a second account.
- [ ] **Compliance requires data residency, encryption-at-rest attestation, or an
      audit log.**
- [ ] **Query latency degrades** → check region co-location first
      ([ADR-0013](0013-co-locate-api-and-database-region.md)), which is the usual cause.

## Migration path

The cleanest exit in the whole stack, because nothing outside the DSN is
Neon-specific.

```sh
pg_dump "$NEON_DSN" -Fc -f energlens.dump      # from the direct endpoint
pg_restore -d "$NEW_DSN" energlens.dump
# swap DATABASE_URL on the API host, then:
alembic upgrade head                            # no-op if the dump was current
```

Then remove the two provider-specific accommodations if the new host does not need
them — `pool_pre_ping` is harmless to keep, and the `%` escaping in `env.py` is
correct regardless.

**To AWS RDS specifically:** create the instance in the same region as the API
([ADR-0013](0013-co-locate-api-and-database-region.md)), dump/restore as above, and
delete `?ssl=require` in favour of RDS's certificate configuration. Estimated effort:
**a couple of hours**, dominated by verifying row counts rather than by the move.
