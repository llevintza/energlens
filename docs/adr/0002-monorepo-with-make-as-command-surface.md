# 0002. One repository, with `make` as the single command surface

- **Status:** Accepted
- **Date:** 2026-08-10 (monorepo), 2026-08-11 (Makefile)
- **Deciders:** llevintza
- **Landed in:** PR #1 (`81b373b`), PR #6 (`84c284d`)
- **Related:** [ADR-0005](0005-alembic-migrations-and-three-databases.md), [ADR-0009](0009-uv-for-python-tooling.md)

## Context

Three deliverables — `backend/`, `frontend/`, `ingest/` — share an API contract and
ship together. Each has its own toolchain (uv, npm, uv), its own working directory,
and its own idea of how to run things.

The practical problem that produced the Makefile: **every command needed the right
working directory and the right tool**, and a database command run without Postgres
up failed with `ConnectionRefusedError` rather than anything actionable. Contributors
— human or agent — had to know a dozen incantations that lived only in the README.

## Decision

**One repository**, and **`make` as the only interface** to it. Targets know their
working directories; database targets run a preflight that explains failures.

The gate is defined as the union of the merge-gating CI jobs:

```make
check: ci-backend ci-frontend      ## Run everything CI runs. The gate.
ci-backend:  lock-check migrate-check test-backend test-ingest
ci-frontend: test-frontend build-web
```

**`make check` and CI cannot disagree**, because CI runs these same targets. That is
the property being bought, and it is why the Makefile is not just convenience.

`deploy-frontend.yml` is deliberately *excluded* — it is a deploy, not a gate, and it
depends on production-only repository variables.

## Consequences

### What this buys

- **One thing to learn**: `make help` lists everything. AGENTS.md points every agent
  at it rather than at raw `uv`/`npm`/`alembic`.
- **The local gate is the CI gate**, by construction rather than by convention.
- Atomic cross-cutting changes: an API contract change touches backend, frontend and
  ingest in one reviewable commit.
- Preflight targets turn infrastructure failures into sentences —
  `scripts/db.sh preflight` explains why the test database is unusable instead of
  raising a connection error.

### What this costs

- **`make` is another layer.** A contributor debugging a test still needs to know it
  is `pytest` underneath, and the indirection can obscure the real command.
- Written for GNU Make 3.81 (Apple stock), so newer Make features are unavailable and
  `.NOTPARALLEL:` forces serial execution — correct here, but slower than it could be.
- Monorepo CI runs everything on every change; the workflows deliberately have **no
  paths filter** so required checks never hang waiting for a job that was skipped.
- Independent versioning and independent release cadence are not possible.

## Limitations

- No incremental build graph beyond a couple of stamp files; most targets re-run
  fully.
- Node and Python toolchains remain separate — `make` wraps them, it does not unify
  them.
- `make check` runs `build-web` **without** `VITE_BASE` or `VITE_API_URL`, so it only
  exercises the localhost fallback. The production base path and the `https://`
  validation in `deploy-frontend.yml` have **no local reproduction** — a real gap in
  the gate, and the reason issues #10 and #11 exist.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Separate repositories** | API contract changes would span repos and lose atomicity; three sets of CI for one deployable product |
| **Just (`justfile`)** | Nicer syntax and better argument handling; `make` is preinstalled everywhere, which matters for agents and fresh clones |
| **npm scripts as the top level** | Would make Node the entry point for a mostly-Python repo |
| **Task / Mage / Nx / Turborepo** | Extra dependency; Nx/Turborepo are aimed at JS monorepos and this is polyglot |
| **Documented raw commands only** | What existed before PR #6 — the README drifted from reality and nothing enforced the gate |

## Revisit when

- [ ] **`make check` gets slow enough to be skipped** → that is when a real build
      graph with caching starts paying for itself.
- [ ] **A fourth component is added**, or one needs independent versioning and
      release.
- [ ] **The Makefile grows past comfortable reading** (~300 lines) → split into
      includes or move to a task runner with better composition.
- [ ] **CI and `make check` diverge for any reason** → that is a defect in this
      decision, not an inconvenience; fix by making CI call the targets.
- [ ] **The production build path needs local reproduction** → add a target that runs
      the frontend build with production-shaped variables.

## Migration path

Splitting the repo later is mechanical with `git filter-repo` (history preserved per
component), but the API contract would then need versioning and the three
deliverables would need coordinated releases — which is precisely the cost this ADR
avoids paying now.
