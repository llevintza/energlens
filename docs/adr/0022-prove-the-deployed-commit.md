# 0022. Prove the deployed commit before smoking the API

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Leo Levintza
- **Landed in:** PR for issue #91
- **Related:** ADR-0014, ADR-0016, ADR-0019, issues #48, #91, #97

## Context

[ADR-0019](0019-verify-the-api-deploy.md) added `api-smoke.yml` to catch "API up,
revision stale" (#48). It asserted `/health`, the OpenAPI title and
`DELETE /users/me` — three facts that also hold on the *previous* revision. The run
for PR #90 smoked ten seconds after the merge and went green against the old deploy
(#91); production then stayed two merges stale with every run green (#97). The check
could only ever detect a rollback past #46, never a deploy that silently stopped.

ADR-0019 had rejected exposing the deployed commit on `/health` because preflight
matched the body `{"status":"ok"}` exactly. That cost turned out to be one `case`
pattern; the cost of not doing it was a detector that cannot detect.

Render sets `RENDER_GIT_COMMIT` at build time and at runtime for every runtime
(<https://render.com/docs/environment-variables>). `render.yaml` sets
`rootDir: backend`, and Render only auto-deploys pushes that change files under the
root directory (<https://render.com/docs/monorepo-support>).

## Decision

`/health` answers `{"status":"ok","commit":"<RENDER_GIT_COMMIT>"}`, with `"unknown"`
anywhere the variable is unset. `scripts/api.sh smoke` computes the newest commit
under `backend/` reachable from the commit under test (`GITHUB_SHA` in Actions,
`origin/main` locally, `API_EXPECT_COMMIT` to override), and retries until the served
commit *contains* it (`git merge-base --is-ancestor`). Only then does it assert the
OpenAPI contract. When the retry budget runs out first it fails with "Deploy is
stale", naming both commits. Preflight accepts `{"status":"ok"}` with or without
further fields.

## Consequences

### What this buys

- "Is it stale?" becomes an ancestry check instead of an inference from the API
  surface. It catches every stale deploy, not only those that change routes.
- "Did it deploy?" is answerable by hand: `curl <API_URL>/health`.
- A later merge that deploys first passes rather than timing out, and a commit that
  touches nothing under `backend/` is never waited for.

### What this costs

- `api-smoke.yml` checks out full history (`fetch-depth: 0`) to walk `backend/`.
- `/health` is no longer a fixed string. It is still fixed per process and touches
  no database, so ADR-0014's liveness reasoning holds.
- The first run after this lands is red until Render actually deploys: production
  serves a revision without the field (#97), and smoke treats that as stale. That is
  the point, but it means the alert fires until someone fixes the deploy.
- The commit is public. It is already public — the repository is — so this exposes
  nothing new, but a private fork should weigh that.

## Limitations

- Retry budget is the workflow's: 24 attempts × 45 s plus curl time, ~20 min. A
  free-tier build slower than that reads as stale.
- The `backend/` pathspec mirrors `rootDir` in `render.yaml` by hand. Moving the root
  directory, or adding Render build filters, means changing `expected_commit` in
  `scripts/api.sh` too.
- A `render.yaml`-only change triggers a Blueprint sync, not necessarily a deploy, so
  it is not waited for — smoke still verifies the newest `backend/` commit.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Equality with `github.sha`** | Times out on every push that changes nothing under `backend/`, and fails when a later merge has already deployed |
| **Poll the Render Deploys API** | Needs a Render API key in Actions secrets; the served commit answers the same question with no credential |
| **Fixed delay before asserting** | Still a race; #91 would have needed several minutes, and a deploy that never happens still passes |
| **A separate `/version` endpoint** | One more public route for a value that belongs with liveness; preflight's body match was the only reason to split it |

## Revisit when

- [ ] **`rootDir` or Render build filters change** → update the pathspec in
      `expected_commit`.
- [ ] **Free-tier builds routinely exceed ~20 min** → raise the workflow's attempts,
      or move to `plan: starter`.
- [ ] **Render stops setting `RENDER_GIT_COMMIT`, or the API moves host** → inject the
      SHA at build time instead; the smoke only reads `/health`'s `commit`.

## Migration path

Revert the `commit` field and the `expected_commit`/`commit_is_live` half of
`scripts/api.sh`; smoke falls back to ADR-0019's contract check. Preflight's relaxed
body match can stay, since it accepts the old body too.
