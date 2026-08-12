# 0014. Split liveness and readiness health checks

- **Status:** Accepted
- **Date:** 2026-08-11
- **Deciders:** llevintza
- **Landed in:** PR #12 (`1963057`)
- **Related:** [ADR-0011](0011-backend-hosting-render.md), [ADR-0012](0012-database-hosting-neon.md), issue #11

## Context

`/health` returned a static `{"status": "ok"}` without touching the database. A green
Render health check therefore proved only that the process was up — not that
PostgreSQL was reachable.

That gap is narrower than it first appears, because a bad `DATABASE_URL` is already
caught at boot: `start.sh` runs `alembic upgrade head` under `set -e`, so the service
never starts with an unreachable database. **The real gap is losing the database
*after* boot** — Neon suspended, credentials rotated, network partition — where every
real endpoint returns 500 while `/health` cheerfully returns 200.

The obvious fix, making `/health` do a `SELECT 1`, is wrong on this platform. It is
`healthCheckPath`, so Render polls it on a schedule; a database round-trip there
would pay a Neon scale-to-zero cold start on *every probe*, and a slow or suspended
database would read as a dead process and get the service restarted. That is an
outage caused by the monitoring rather than by the fault.

## Decision

**Two endpoints with two different jobs.**

| Endpoint | Touches DB | Used by | Semantics |
| --- | --- | --- | --- |
| `GET /health` | no | Render `healthCheckPath`, deploy gates | Liveness — the process is up |
| `GET /health/db` | yes, `SELECT 1` | humans, monitoring | Readiness — PostgreSQL is reachable |

`/health/db` returns `200 {"status":"ok","database":"ok"}` or
`503 {"status":"error","database":"unreachable"}`. Together they distinguish *"the API
is down"* from *"the API is up but the database is not"*, which neither endpoint can
do alone.

Three properties of the implementation are load-bearing:

- **The failure body never carries the exception.** The endpoint is unauthenticated,
  and SQLAlchemy error reprs embed the connection URL — password included. Returning
  the error, which is the obvious way to write this, would publish the database
  credentials to anyone able to take the database down. The cause is logged
  server-side instead.
- **503, not 500.** A live API with a dead database is a distinct, correct state, and
  503 keeps the endpoint meaningful to monitoring.
- **The `except` is deliberately broad.** SQLAlchemy only wraps what the driver raises
  *after* a connection exists. The failures this endpoint is for — suspended Neon,
  wrong hostname, TLS failure, timeout — happen before that and arrive raw as `OSError`
  subclasses.

That last point was a real bug, not a hypothetical. The first implementation caught
`SQLAlchemyError` and **every unit test passed**; run against an actually unreachable
database it returned `500` with no log line, because asyncpg's `ConnectionRefusedError`
never became a SQLAlchemy exception. The regression test now reproduces it with a real
engine pointed at a closed port rather than a hand-built `OperationalError` — a stub
cannot express this failure mode, which is precisely why the stub-based tests passed.

## Consequences

### What this buys

- Render's probe stays cheap and cannot be made to flap by a sleeping database.
- A single `curl` distinguishes the two failure modes during an incident.
- Deploy-time reachability checks (issue #11) get a target that means something.

### What this costs

- Two endpoints to keep in sync conceptually; someone will eventually "simplify" them
  back into one. The code comments and this ADR exist to make that a deliberate act.
- `/health/db` is public and unauthenticated, so it is a (trivial) availability
  oracle: anyone can learn whether our database is up. Accepted — it returns no detail
  beyond a boolean.
- It opens a real connection, so it can itself wake a suspended Neon instance.

## Limitations

- **`SELECT 1` proves connectivity, not correctness.** It says nothing about schema
  version, replication lag, disk pressure, or whether migrations have run.
- It checks the pool the *dependency* hands out, not every possible connection path.
- **`HEAD /health` returns 405, not 200.** FastAPI does not auto-register `HEAD` for
  `@app.get` routes the way plain Starlette does, so `curl -I` fails against a
  perfectly healthy service. Any external monitor must use `GET`. The `allow: GET`
  header is the tell.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Make `/health` do `SELECT 1`** | It is `healthCheckPath`; a Neon cold start would look like a dead process and trigger restarts |
| **Leave it static, document the gap** | A post-boot database loss would still be invisible; the whole point is a signal that exists |
| **Return the exception in the body** | Publishes the DSN and password on an unauthenticated endpoint |
| **Full readiness check** (migration version, disk, dependencies) | Over-engineered for one service and one database; revisit if the surface grows |
| **Push metrics to an external monitor** | Needs an account and a scraper; `/health/db` is free and sufficient at this size |

## Revisit when

- [ ] **Render's health check path is changed** to `/health/db` — do not do this
      without re-reading the Context above; it reintroduces the restart-loop risk.
- [ ] **A real monitoring system arrives** (UptimeRobot, Better Stack) → point it at
      `/health/db` with `GET`, and alert on 503 rather than on timeout.
- [ ] **More dependencies are added** (cache, queue, object storage) → `/health/db`
      becomes `/health/ready` reporting per-dependency status.
- [ ] **The service scales past one instance** → per-instance readiness starts to
      matter for load-balancer decisions.
- [ ] **Schema-version drift becomes a real risk** → extend the readiness check to
      compare `alembic_version` against the code's head revision.

## Migration path

Not applicable — this is an internal contract, not a vendor dependency. If the
platform changes, the only coupling is `healthCheckPath` in `render.yaml`, which must
keep pointing at the **liveness** endpoint.
