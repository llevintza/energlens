# 0017. Verify the Pages deploy, and route its failure to an issue

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** llevintza
- **Landed in:** PR #35 (`2475b4b`)
- **Related:** [ADR-0010](0010-frontend-hosting-github-pages.md),
  [ADR-0002](0002-monorepo-with-make-as-command-surface.md),
  [ADR-0014](0014-split-liveness-and-readiness-health-checks.md),
  [ADR-0016](0016-verify-api-url-at-deploy-time.md), issues #10, #11

## Context

[ADR-0010](0010-frontend-hosting-github-pages.md) closed with two open gaps: build-time
configuration is a footgun, and *deploys are not verified*. On 2026-08-11 the second one
collected. The `API_URL` guard failed the deploy at 12:17 and again at 16:59, and nobody
found out until 17:14 — from a browser, not from CI. For five hours `main` contained a
base-path fix that was not live, and the site served the previous bundle, which requested
`/energy-tracker/assets/…`: HTTP 200 on the page, 404 on every asset, empty `#root`.

Three structural facts made that silence inevitable, and none of them is a bug to fix:

1. **The deploy cannot be a required status check.** Required checks gate pull requests.
   `deploy-frontend.yml` triggers on `push` to `main` and `workflow_dispatch`; by the
   time it runs, the PR is merged and there is nothing left to block.
2. **The required check builds a configuration that is never deployed.** `frontend-build`
   has no `env:` block, so it compiles with `VITE_BASE` unset (base `/`) and
   `VITE_API_URL` unset (the `http://localhost:8000` fallback in `src/api/client.ts`).
   Same commit, same minute, opposite verdicts — it is green *precisely* when the deploy
   is red, and it never executes the guard at all.
3. **Nothing reported the failure passively.** No badge, no `if: failure()` handler, no
   step after `actions/deploy-pages@v4`.

The deeper problem is that the original defect — PR #1's wrong base path — is invisible
to build-time checking **by construction**. `vite build` cannot know what path will serve
the output. A bundle with the wrong `base` compiles perfectly and is wrong only once
something serves it, so the only check that can catch it is one that fetches the
deployed URL.

## Decision

**We assert against the published site, and we make a failure arrive uninvited.**

- **`scripts/smoke-pages.sh`** fetches the deployed page, asserts it contains
  `<div id="root">`, extracts the `.js`/`.css` it references, asserts each path sits
  under the base path the site is *served from*, and fetches each one. It resolves the
  URL from the Pages API (`repos/{owner}/{repo}/pages`) rather than hardcoding it, so a
  rename or a custom domain needs no edit. Available locally as `make smoke-web`.
- **A `smoke` job** in `deploy-frontend.yml` runs it against
  `steps.deployment.outputs.page_url` immediately after `deploy-pages`, so the deploy run
  itself goes red when the thing it just published does not load.
- **`pages-smoke.yml`** runs the same script against the live site daily. The deploy's
  `paths` filter is `frontend/**` and both `API_URL` and the base path are inlined at
  build time, so changing a variable, renaming the repo, or adding a custom domain
  triggers *no deploy at all* — the drift ADR-0010 predicted has no other detector.
- **`scripts/ci-alert.sh`** turns `join(needs.*.result, ' ')` into a labelled tracking
  issue, comments on it while it stays red, and **closes it on the next green run**.

Three details are load-bearing:

- **The asset is resolved against the origin, not against the page URL.** Vite emits
  root-absolute paths (`src="/energlens/assets/index-*.js"`). The obvious
  `"${PAGE_URL%/}$asset"` yields `…github.io/energlens/energlens/assets/…` and fails on
  a perfectly good deploy. Issue #10's sketch has this bug; it was caught by running the
  check against the real site before wiring it up.
- **The base-path assertion is separate from the 200.** A stale base already fails the
  fetch, but as a bare 404. Comparing the referenced path against the served base lets
  the error name both — which is the difference between a diagnosis and a mystery, and
  the reason it is worth the extra ten lines (issue #2, principle 5).
- **The page fetch carries a cache-buster.** Without it a stale edge copy of
  `index.html` would let a broken deploy pass by validating the *previous* bundle. A
  false green is the one outcome a smoke test must not produce; a false red is merely
  annoying.

`smoke-web` is deliberately **not** in `make check`. Per
[ADR-0002](0002-monorepo-with-make-as-command-surface.md), `make check` is exactly the
merge-gating CI jobs; a check against a deployed site says nothing about the branch in
front of you, and wiring it in would make the gate fail for reasons the PR cannot fix.

Two topics — `ci:pages-deploy` and `ci:pages-drift` — rather than one shared issue.
A build that dies on the `API_URL` guard never republishes, so the old (working) bundle
stays live and the drift check keeps passing; one shared issue would let that green drift
run auto-close a still-broken deploy.

## Consequences

### What this buys

- The class of defect that started this — a bundle that builds and then does not load —
  now fails a run instead of a user's browser.
- A red deploy reaches a human three ways without anyone deciding to look: the run, the
  badges, and an issue in the tracker.
- The alert closes itself, so an open `ci:*` issue always means "still broken". An alert
  that only ever opens degrades into an ignored one.
- `make smoke-web` reproduces a red `smoke` job locally, without redeploying.
- Build-time-config drift, called out in ADR-0010 as undetectable, is now detected
  within a day.

### What this costs

- **The check still runs after merge.** It is louder, not earlier. A base-path
  regression is caught minutes after landing on `main`, not on the PR — inherent to
  verifying a deployed artifact, and the reason issue #10's option A stays open.
- A second `issues: write` surface in CI, and a bot that can open issues in this repo.
- One scheduled run a day, and the noise it implies while the backend is still down
  (#7/#11) — this check ignores the API entirely, but a human seeing `ci:pages-drift`
  will still go look.
- Two more jobs on every deploy: roughly +30s wall clock, two extra checkouts.
- More CI surface to keep honest. The deploy workflow is now four jobs, and the
  `permissions:` blocks are per-job on purpose — the `pages`/`id-token` grants must not
  reach `alert`.

## Limitations

- **Behind a custom domain the base-path assertion degrades to a tautology.**
  `configure-pages` emits `""` there, so the served base is `/` and every root-absolute
  asset matches it trivially. Only the asset `200` catches a stale base in that setup.
- **It proves the bundle loads, not that it works.** No JavaScript is executed, so a
  runtime crash on first render passes. It never touches `API_URL` either — whether the
  backend answers belongs to
  [ADR-0016](0016-verify-api-url-at-deploy-time.md) and `scripts/api.sh preflight`. So
  the daily run closes the *frontend* half of the build-time-config drift window and
  leaves ADR-0016's half open: a backend decommissioned after the last deploy still goes
  unnoticed until someone runs `make api-preflight`.
- **Cron granularity is 24h**, and GitHub drops scheduled runs under queue congestion
  and disables them entirely after 60 days without repository activity. This is a
  backstop, not monitoring.
- **Issues opened with `GITHUB_TOKEN` do not trigger further workflow runs**, so nothing
  can be chained off the alert. Notification depends on the repo's watch settings.
- `--retry-all-errors` requires curl ≥ 7.71 (ubuntu-latest ships 8.x, macOS 15 ships
  8.7).
- The smoke job cannot run on a pull request: there is nothing deployed to check.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Make the deploy a required check** | Not available. Required checks gate PRs; this workflow runs on push to `main`, after the PR is gone |
| **Shift the `API_URL` guard into `frontend-build`** (issue #10, option A) | Couples PR CI to production-only variables — no PR can go green until the variable is set — and breaks the documented `make check == CI` invariant unless a matching local target lands too. Catches the guard failure but *not* the base-path defect, which no build-time check can see. Still open |
| **Assert the 200 only, skip the base-path comparison** | Fails identically but reports a bare 404; the operator has to work out why an asset that exists in `dist/` is missing |
| **`workflow_run`-triggered smoke in its own workflow** | Decouples the result from the deploy run, so the deploy badge stays green while the site is broken. `workflow_run` also only fires from the default branch, so it cannot be tested before merging |
| **Headless browser (Playwright) asserting rendered content** | Catches runtime crashes too, but adds a browser download to every deploy and a dependency the repo has no other use for. Revisit if the SPA grows past "does it load" |
| **External uptime monitor** (UptimeRobot, Better Stack) | Needs an account and lives outside the repo, so no PR can change it. Would supersede the scheduled half of this, not the deploy-time half |
| **Alert to email/Slack instead of an issue** | Needs a secret and an external service; an issue is free, is already where this project's work lives, and can carry a comment thread |

## Revisit when

- [ ] **A custom domain is added** → the base-path assertion goes tautological; replace
      it by comparing against `steps.pages.outputs.base_path` passed through as a job
      output.
- [ ] **Issue #10's option A lands** → the `API_URL` guard would then fail on the PR, and
      the deploy-time guard becomes a backstop rather than the only check.
- [ ] **The backend half of the drift window is worth closing too** → add
      `scripts/api.sh preflight` to `pages-smoke.yml`'s daily job. That is the trigger
      [ADR-0016](0016-verify-api-url-at-deploy-time.md) names for itself, and the cron
      that would carry it already exists. Deliberately not done here: it would make a
      Render cold start able to file an issue about the *frontend*, so it wants its own
      topic and its own tolerance for a sleeping free-tier service.
- [ ] **`smoke-pages.sh` is proposed for `make check`** → it is not a gate. It checks a
      deployment, not a build; the frontend's vitest suite is the thing that belongs in
      the gate.
- [ ] **The `ci:pages-drift` issue fires more than once a quarter without a real defect**
      → the cron is noise; drop it and rely on deploy-time smoke alone.
- [ ] **A second deployed surface appears** (staging, preview deploys) → generalise the
      script's URL argument rather than copying the workflow.

## Migration path

Both halves are plain `curl` in POSIX `sh` with no vendor coupling beyond `gh`. Moving
off GitHub Pages means changing where `smoke-pages.sh` gets its URL (one function) and
which workflow calls it; the assertions are about HTML and HTTP and carry over unchanged.
Moving off GitHub Actions means reimplementing the two workflows — the scripts run
anywhere, which is why the logic lives in `scripts/` rather than in YAML. Dropping the
alerting means deleting `ci-alert.sh` and the two `alert` jobs; the smoke check stands on
its own.
