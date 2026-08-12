# 0016. Verify `API_URL` answers before building the frontend

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** llevintza
- **Landed in:** PR #TBD (`TBD`)
- **Related:** [ADR-0010](0010-frontend-hosting-github-pages.md), [ADR-0011](0011-backend-hosting-render.md), [ADR-0014](0014-split-liveness-and-readiness-health-checks.md), issue #11, issue #13

## Context

`deploy-frontend.yml` validated that the `API_URL` repository variable *looked like* an
absolute `https://` URL and stopped there. That guard was correct and remains necessary
— a scheme-less value passes `test -n` and then throws `Invalid URL` from `new URL()` on
every request — but `https://?*` matches any syntactically valid string, `https://x`
included.

Three properties of this stack combine to make that gap invisible rather than noisy:

- **`*.onrender.com` is a wildcard.** A guessed, typo'd, or decommissioned hostname
  returns an ordinary HTTP `404` with `x-render-routing: no-server`, not a DNS failure
  or a connection refusal. There is nothing for a client to notice.
- **`API_URL` is inlined at *build* time.** Nothing downstream of the build can catch a
  wrong value; by the time a browser is involved, the bundle is already published.
- **The frontend cannot tell the cases apart.** `client.ts` turns that 404 into an
  `ApiError(404)`, which `LoginPage.tsx` reports as `Login failed — is the API running?`
  — identical to a backend that is genuinely down and to a route that does not exist.

This is not hypothetical. `API_URL` was set to a *guess* at the Render hostname while
the backend did not yet exist (issue #7), and every check stayed green while the
deployed site could not log anybody in.

Two platform behaviours constrain any check, and they pull in opposite directions:

- **Cold start hangs.** The free tier sleeps after 15 minutes; the waking request
  produces no bytes for a long time. Measured twice while designing this: a single GET
  timed out at 40s, and separately at 20s, each time succeeding seconds later. Giving up
  client-side does not cancel the wake.
- **Edge flap fails fast.** For ~12 minutes after service creation, Render's edge
  alternated between the app and a `no-server` 404 at roughly 50% (issue #13). Those
  failures return in ~0.1s, so a longer timeout contributes nothing — only a *new
  connection* helps.

A single request with a generous `--max-time` handles the first and is useless against
the second.

## Decision

**We verify at deploy time that `GET <API_URL>/health` returns `{"status":"ok"}`, in a
dedicated workflow step that runs before `npm ci`.**

The check lives in `scripts/api.sh`, so the same code runs locally as
`make api-preflight`, and the shape check moved there too — one command owns `API_URL`
validation in both places.

Four properties are load-bearing:

- **It asserts the body, not just a 2xx.** `curl -sS` without `-f` exits **0** on a 404,
  so the exit status is not a signal at all. Comparing the body is also what
  distinguishes *our* API from any other server that happens to answer on that host.
- **It retries across fresh connections** — 10 attempts of 30s, 5s apart, ~345s total.
  That is >5× the documented 30–60s cold start, and at a 50% flap rate the odds of ten
  consecutive false failures are 1 in 1024.
- **It uses `GET`.** `HEAD /health` returns 405 against a healthy service
  ([ADR-0014](0014-split-liveness-and-readiness-health-checks.md)), so a `curl -I` check
  would fail 100% of the time on a working backend.
- **It gates on `/health`, never `/health/db`.** `/health/db` *should* go red during a
  Neon outage; gating on it would block a frontend-only deploy for a backend-only fault.
  It is probed advisory-only, as a warning.

Because each of the failure modes above produces a *plausible* response rather than an
obvious error, every branch names what is actually wrong — plain-text `Not Found` (the
edge claims no service) versus JSON `{"detail":"Not Found"}` (our app is up, the route
is wrong) versus an HTML body (`API_URL` points at a website). A check that failed with
"HTTP 404" would reproduce the ambiguity issue #11 was filed about.

## Consequences

### What this buys

- A guessed or stale backend hostname can no longer ship green. The deploy fails, and
  the failure names the repository variable and the command that fixes it.
- The failure is attributed correctly: a red X on "Verify API_URL" rather than on
  "Build", and it fires in seconds instead of after a cache restore and a Vite build.
- The same check runs locally, so `make api-preflight` answers "is the value I just set
  correct?" without a push, a branch, or Actions minutes.
- The deploy runbook gains a verification step between setting the variable and
  dispatching the workflow.

### What this costs

- **The frontend deploy now depends on backend availability.** A genuine Render outage
  blocks shipping a frontend-only fix. Mitigated by a `workflow_dispatch` input,
  `skip_api_check` — unreachable from a `push`, since a push cannot supply inputs. Two
  properties keep that hatch from becoming the hole it is guarding: it skips only the
  *probe* (the run still executes `scripts/api.sh validate`, the offline half, because a
  backend outage is no reason to ship a bundle pointed at an empty or scheme-less URL),
  and it is never silent — the run is annotated with a warning that this bundle's
  `API_URL` was never probed.

  The hatch is still a compromise worth naming: a wrong-host failure is *permanent* and
  an outage failure is *transient*, and the flag cannot tell them apart. Re-running the
  job remains the cheaper recovery for anything transient.
- A *failing* deploy now takes up to ~6 minutes instead of failing instantly, which
  widens the window in which `concurrency: cancel-in-progress` cancels it. Harmless — a
  cancelled build publishes nothing.
- A backend and frontend change pushed together can race: Render's free tier has one
  instance and no zero-downtime deploy, so the API may be restarting while the Pages job
  probes it. The retry budget covers a normal boot; a genuinely failed backend deploy
  now also fails the frontend deploy, and re-running the job is the recovery.
- One more script and one more `make` target to keep working.

## Limitations

- **`{"status":"ok"}` is a generic health body.** This proves an Energlens-*shaped* API
  answers, not that it is ours. The stronger assertion is `GET /openapi.json` containing
  `"title":"Energlens API"` — one more round trip, and a coupling to `openapi_url`
  staying enabled. Not implemented.
- **It says nothing about the database.** Deliberate — see the Decision. `/health/db` is
  reported as a warning and never enforced.
- **It is a point-in-time check.** A backend decommissioned *after* the last frontend
  deploy stays invisible, because the workflow's `paths` filter is `frontend/**` and
  `API_URL` is inlined at build time. That drift window is issue #10's shape, and it is
  not closed here.
- Redirects are not followed. A 3xx is treated as a failure, because browsers do not
  follow redirects on a CORS preflight — an `API_URL` that 301s would pass a `curl -L`
  check and then break every write in the browser.
- Timing bounds: 10 × 30s per attempt + 9 × 5s between = ~345s worst case, with
  `timeout-minutes: 10` as the hard stop.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Single `curl -fsS --max-time 15`** | No retry, so the #13 edge flap fails it ~50% of the time; `-f` also discards the body, which is the entire diagnosis |
| **Assert 2xx only, not the body** | `curl -sS` exits 0 on a 404 anyway, and any server answering on that host would pass |
| **`curl -I` / `HEAD`** | Returns 405 against a *healthy* API — it would fail 100% of the time (ADR-0014) |
| **One long `--max-time` instead of retries** | Handles the cold start, does nothing for the edge flap, which fails fast on every attempt |
| **Gate on `/health/db`** | Wrong blast radius: a Neon outage would block frontend-only deploys (ADR-0014) |
| **Assert `/openapi.json` contains `"title":"Energlens API"`** | Stronger identity proof, but an extra round trip and it breaks if `openapi_url` is ever disabled. Recorded as a limitation instead |
| **Inline the loop in the workflow's `run:` block** | Cannot be exercised locally, which is exactly what issue #11's checklist asks for; also puts branching shell inside a YAML string, which the Makefile's own rule rules out |
| **Add the check to `frontend-ci.yml`** | `frontend-build` is a required check on `main`; a third-party outage would block merges |

## Revisit when

- [ ] **Render moves to `plan: starter`** ($7/mo, always-on) → the cold-start half of the
      retry budget is unnecessary; `ATTEMPTS` can drop and the check gets faster.
- [ ] **A post-deploy drift check lands** (issue #10) → a `schedule:` workflow running
      this same `scripts/api.sh preflight` daily would close the window this ADR
      explicitly leaves open.
- [ ] **`skip_api_check` gets used more than once** → the escape hatch is papering over a
      real availability problem; that is the signal to fix the backend's uptime, not the
      gate.
- [ ] **The backend stops being the only consumer of `API_URL`** → a multi-service
      frontend needs one probe per service, not one.
- [ ] **`/health`'s contract changes** (different body, different path, `healthCheckPath`
      moves) → the asserted string in `scripts/api.sh` must move with it.

## Migration path

Not applicable — this is an internal gate, not a vendor dependency. Removing it is
deleting one workflow step, one `make` target, and `scripts/api.sh`; the shape check
would have to move back into `deploy-frontend.yml`, because that part is load-bearing on
its own.
