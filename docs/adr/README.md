# Architecture decision records

Why the stack is what it is, what each choice costs, and **what should make us
revisit it**. Every ADR ends with explicit revisit triggers and a migration path, so
moving off a provider is a planned step rather than an archaeology exercise.

Start with [`docs/architecture.md`](../architecture.md) for the system view.

## Index

| # | Decision | Status | Layer |
| --- | --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted | Process |
| [0002](0002-monorepo-with-make-as-command-surface.md) | Monorepo with `make` as the single command surface | Accepted | Process |
| [0003](0003-fastapi-async-sqlalchemy-asyncpg.md) | FastAPI + async SQLAlchemy + asyncpg | Accepted | Backend |
| [0004](0004-postgresql-as-the-datastore.md) | PostgreSQL as the datastore | Accepted | Data |
| [0005](0005-alembic-migrations-and-three-databases.md) | Alembic migrations, and three local databases | Accepted | Data |
| [0006](0006-fastapi-users-jwt-auth.md) | fastapi-users with stateless JWTs | Accepted | Backend |
| [0007](0007-react-vite-spa.md) | React 19 + Vite SPA, no SSR | Accepted | Frontend |
| [0008](0008-tanstack-query-and-recharts.md) | TanStack Query + Recharts | Accepted | Frontend |
| [0009](0009-uv-for-python-tooling.md) | `uv` for Python dependency management | Accepted | Tooling |
| [0010](0010-frontend-hosting-github-pages.md) | Frontend on GitHub Pages | Accepted | Hosting |
| [0011](0011-backend-hosting-render.md) | Backend on Render free web service | Accepted | Hosting |
| [0012](0012-database-hosting-neon.md) | Database on Neon serverless Postgres | Accepted | Hosting |
| [0013](0013-co-locate-api-and-database-region.md) | Co-locate the API and database in one region | Accepted | Hosting |
| [0014](0014-split-liveness-and-readiness-health-checks.md) | Split liveness and readiness health checks | Accepted | Ops |
| [0015](0015-demo-seed-in-production.md) | Ship a public demo account | **Accepted (time-boxed)** | Security |
| [0016](0016-verify-api-url-at-deploy-time.md) | Verify `API_URL` answers before building the frontend | Accepted | Ops |

## Status legend

| Status | Meaning |
| --- | --- |
| **Proposed** | Under discussion, not yet acted on |
| **Accepted** | In force; the code reflects it |
| **Accepted (time-boxed)** | In force, but with a known expiry condition stated in the ADR |
| **Superseded by NNNN** | Replaced; kept for history, never deleted or edited into the new decision |
| **Deprecated** | No longer applies, with nothing replacing it |

An ADR is **immutable once accepted**. Changing your mind means writing a new ADR
that supersedes the old one — that is the whole point of the format, and the only
way the record stays trustworthy as a history.

## Format

Copy [`TEMPLATE.md`](TEMPLATE.md). Every ADR carries:

- **Context** — the forces in play *at the time*, including constraints that were
  non-negotiable. Written so it still makes sense years later.
- **Decision** — what was chosen, stated actively ("We use X").
- **Consequences** — what follows, good and bad. An ADR with no negative
  consequences is not finished.
- **Limitations** — the concrete ceilings. Numbers, not adjectives.
- **Alternatives considered** — with the actual reason each was rejected.
- **Revisit when** — the triggers that should reopen this. Cost, scale, security,
  and vendor-risk thresholds where they can be quantified.
- **Migration path** — the rough shape of moving off, and what it would touch.

## Cost model

Current total: **$0/month.** Where the money starts, per component:

| Component | Free ceiling | First paid step |
| --- | --- | --- |
| GitHub Pages | 100 GB/mo bandwidth, public repo | private repo needs GitHub Pro |
| Render | 512 MB, sleeps when idle | `starter` $7/mo — always-on, no other change |
| Neon | 0.5 GB storage | Launch plan, ~$19/mo |

The realistic first bill is Render's $7/mo to remove cold starts, and it is a
one-line change to `render.yaml`. See
[ADR-0011](0011-backend-hosting-render.md).
