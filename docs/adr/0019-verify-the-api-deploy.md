# 0019. Verify the API deploy, and pin auto-deploy in the Blueprint

- **Status:** Accepted
- **Date:** 2026-08-13
- **Deciders:** llevintza
- **Landed in:** PR #66 (`c314070`)
- **Related:** [ADR-0011](0011-backend-hosting-render.md),
  [ADR-0016](0016-verify-api-url-at-deploy-time.md),
  [ADR-0017](0017-verify-the-pages-deploy.md), issue #48

## Context

[ADR-0011](0011-backend-hosting-render.md) chose Render and stated that it watches
`main` and auto-deploys on push. [`render.yaml`](../../render.yaml) never recorded
`branch` or an auto-deploy field. For an *existing* service, Render retains the
dashboard value when `autoDeployTrigger` is omitted — so the Blueprint can say
nothing while auto-deploy is off, and a `backend/` merge leaves production on the
previous commit.

That is exactly what happened after #46: `DELETE /users/me` landed on `main`,
Pages redeployed, `/health` stayed 200, and OpenAPI still listed only `get` and
`patch` for `/users/me` (issue #48). The Settings delete-account control talked to
a route that was not in production. A bare `curl -X DELETE` returning 401 was
misleading — that is fastapi-users' superuser-gated `DELETE /users/{id}` matching
`"me"`.

The frontend already had deploy-time and daily smoke ([ADR-0017](0017-verify-the-pages-deploy.md)).
The backend had only [`scripts/api.sh preflight`](../../scripts/api.sh), which
asserts `/health` — the check that stayed green through the whole incident.

## Decision

**We pin auto-deploy in the Blueprint, and we assert the OpenAPI contract from
outside.**

- **`branch: main`** and **`autoDeployTrigger: commit`** in `render.yaml`, so the
  repo — not only the dashboard — owns the policy. (`autoDeployTrigger` replaces
  the deprecated `autoDeploy: true`.)
- **`scripts/api.sh smoke`** runs the preflight reachability path, then fetches
  `/openapi.json` and asserts `info.title` is `Energlens API` and `/users/me`
  exposes `delete` — the probe that would have failed during #48.
- **`.github/workflows/api-smoke.yml`** runs that smoke on push to `main` when
  `backend/**` or `render.yaml` changes, on a daily cron, and via
  `workflow_dispatch`. Failures file a `ci:api-smoke` issue through
  `scripts/ci-alert.sh` and close it on the next green run.
- **`make api-smoke`** is the local half. Like `api-preflight` and `smoke-web`,
  it is **not** part of `make check`.

`preflight` stays the lighter check used by the frontend deploy guard
([ADR-0016](0016-verify-api-url-at-deploy-time.md)); folding OpenAPI into it would
couple every Pages build to a contract assertion that is about *backend*
freshness, not about whether `API_URL` points at a live host.

## Consequences

### What this buys

- Auto-deploy intent is visible and syncable from the Blueprint.
- A stale API with a green `/health` fails a run and opens an issue, instead of
  waiting for someone to probe OpenAPI by hand.
- `make api-smoke` reproduces the red job locally.

### What this costs

- The smoke still runs **after** merge — louder, not earlier. Render owns the
  deploy; GitHub Actions can only poll.
- One more scheduled workflow and a second `ci:*` alert topic.
- The OpenAPI contract hard-codes `DELETE /users/me`. That is deliberate for the
  failure mode we just hit; a future public route that must not silently lag
  production needs an explicit addition here (or a stronger revision signal).

## Limitations

- **Omitting `autoDeployTrigger` still preserves dashboard state on existing
  services.** Writing the field only helps once the Blueprint syncs (Auto Sync or
  Manual Sync). A first merge of this YAML may need one human click if Auto Sync
  is off.
- **No git SHA comparison.** Without exposing `RENDER_GIT_COMMIT` (which would
  change `/health`'s exact `{"status":"ok"}` body that preflight matches), smoke
  cannot prove "equals `origin/main`" — only that the named contract is present.
- **Cron granularity is 24h**, with the same GitHub schedule caveats as ADR-0017.
- **Free-tier builds need a long retry budget** in the workflow (~20 minutes). A
  permanently stale API still fails; a slow build must not look like one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Manual deploys only, document in README** | Leaves the ADR-0011 auto-deploy promise false and recreates #48 whenever someone forgets to click |
| **Fold OpenAPI into `preflight`** | Wrong blast radius: Blocks frontend deploys on backend-contract drift; preflight's job is "is `API_URL` a live Energlens host?" |
| **Expose `RENDER_GIT_COMMIT` on `/health`** | Breaks preflight's exact body match and expands [ADR-0014](0014-split-liveness-and-readiness-health-checks.md); revisit if contract checks proliferate |
| **`autoDeployTrigger: checksPass`** | Would wait on CI before Render builds; fine later, but #48 was "never deployed", not "deployed before checks" |
| **Render deploy hook from Actions** | Needs a deploy hook secret and pushes credentials into CI; Blueprint pull stays the smaller surface |

## Revisit when

- [ ] **Blueprint Auto Sync is off and a `render.yaml` change does not apply** →
      document Manual Sync in the runbook, or flip Auto Sync on.
- [ ] **Another route silently missing from production hurts users** → extend the
      OpenAPI contract list, or add a revision field to `/health` and compare to
      `GITHUB_SHA`.
- [ ] **`ci:api-smoke` fires without a real defect more than once a quarter** →
      lengthen the retry budget or drop the cron and keep push-triggered smoke only.
- [ ] **`api-smoke` is proposed for `make check`** → it is not a gate; it checks a
      deployment, not a build.

## Migration path

Dropping the smoke means deleting `api-smoke.yml`, the `smoke` subcommand (or
leaving it for local use), and the ADR index row. Pinning auto-deploy is one
Blueprint field — set `autoDeployTrigger: off` if the policy changes. Moving off
Render means replacing the workflow's wait/poll assumptions; the OpenAPI
assertions themselves are host-agnostic.
