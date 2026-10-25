# 0023. Queue background jobs in Postgres, and run the worker inside the API process

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** llevintza
- **Landed in:** PR #TBD
- **Related:** [ADR-0003](0003-fastapi-async-sqlalchemy-asyncpg.md), [ADR-0005](0005-alembic-migrations-and-three-databases.md), [ADR-0011](0011-backend-hosting-render.md), [ADR-0012](0012-database-hosting-neon.md), [ADR-0021](0021-pdf-blob-storage.md), issues #55, #50, #59, #51

## Context

Bill extraction (#59) takes 20–60 seconds per PDF and calls a paid API. It cannot
run in the request path, and ADR-0003 already said so twice, in its revisit triggers:
*"Background jobs are needed … do not grow it inside the request path"* and *"The
event loop is blocked by CPU-bound work (PDF parsing in-process) → move it to a
worker rather than threading it into the API"*.

The obvious reading of "a worker" is a second service, and the hosting rules out
exactly that (ADR-0011):

- Render's free instance type covers **web services only**; a background worker
  starts at a paid instance type.
- Free instances draw on **750 instance-hours per month, workspace-wide**. Two
  always-on services need ~1,460.
- The web service **spins down after 15 minutes idle** and takes 30–60 s to wake.
  Any process inside it can die at any moment, mid-job, with no shutdown hook that
  is guaranteed to run.

The real load is **1–3 bills at a time**, uploaded by one person. Nothing about this
needs throughput; everything about it needs a job to survive its process.

## Decision

We queue jobs as rows in a `bill_jobs` table in the existing Postgres, and consume
them with **one `asyncio` task inside the API process**, started from the FastAPI
lifespan when `WORKER_ENABLED` is true. Durability comes from the row, not the
process.

- **Claim** is a single `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1)
  RETURNING *`, so a second consumer — if one ever exists — skips a row another has
  locked instead of taking it or waiting on it. Concurrency is 1 today.
- **Poll** every 5 seconds. Not `LISTEN/NOTIFY`: a listener needs a connection held out
  of SQLAlchemy's pool for its whole life, which fights pool sizing, Neon's idle
  suspends (ADR-0012) and Render's spin-down, to save at most 5 s on a 20–60 s job.
  A `NOTIFY` on insert may be added later as a latency optimisation *on top of*
  polling; polling stays the mechanism that guarantees a job runs.
- **Heartbeat** every 10 s while a handler runs. A **reaper** — on boot, every 60 s,
  and on `POST /internal/jobs/sweep` — requeues `claimed`/`running` jobs whose
  heartbeat is over 2 minutes old. That is the spin-down story: the process dies, the
  row stays claimed, the next boot rescues it.
- **Retries** back off `2^attempts` minutes. At `max_attempts` (3) the job is `dead`,
  with `last_error` kept. `dead` (never got a verdict) is distinct from `failed` (ran,
  produced a bad result).
- **Waking**: `.github/workflows/agent-sweep.yml` calls `POST /internal/jobs/sweep`
  every 15 minutes, guarded by a shared secret (`INTERNAL_TOKEN`; when blank the
  route is not registered). The request wakes a sleeping instance; the boot starts
  the worker; the sweep reaps. Persistent failure files a tracking issue through
  `scripts/ci-alert.sh agent-sweep`.

This *satisfies* ADR-0003's triggers rather than violating them: the work leaves the
request path, and it runs in a worker — one that happens to share the process. It is
also **safer** than a separate worker against ADR-0005's warning that *"a second
service starts writing to this database → boot-time migration by two processes
races"*: `backend/start.sh` runs `alembic upgrade head` in exactly one process, and
this design keeps it that way.

## Consequences

### What this buys

- $0/month, and no new service, credential or vendor.
- A job outlives any process that touches it: upload, spin-down, deploy and crash
  all leave a row that the next boot or sweep picks up.
- Enqueueing writes to the database the upload already depends on, so there is no
  broker that can be down while the API is up.
- The queue ships with a no-op handler and is fully tested without an API key; #59
  registers the real one.

### What this costs

- **Extraction shares 512 MB and one event loop with the API.** A handler that does
  CPU-bound parsing on the loop stalls requests; it must offload to a thread.
- **Latency up to 5 s** from enqueue to claim, by design.
- **A job interrupted by a spin-down waits** until the next boot *and* until its
  heartbeat is 2 minutes stale — up to ~15 minutes on the sweep clock if the user
  has left.
- **The sweep keeps the free instance warm.** A request every 15 minutes against a
  15-minute idle timeout means the instance rarely sleeps: ~744 of the workspace's
  750 instance-hours in a 31-day month. That leaves no room for a second free
  service in the same Render workspace. Lengthening the cron (e.g. hourly) trades
  hours back for slower recovery of abandoned jobs.
- **Production now depends on GitHub Actions' scheduler** for recovering a job when
  nobody visits — but only for *when* it runs, never *whether*: any request that
  wakes the instance does the same.
- One-active-job-per-document is enforced in application code under a row lock, not
  by the database (see `BillJob`'s docstring for why a partial unique index was not
  used).

## Limitations

- **Concurrency 1.** One job at a time; three bills take 1–3 minutes end to end.
- **Poll interval 5 s, heartbeat 10 s, stale after 2 min, reap every 60 s.**
- **Backoff 2, 4 minutes; dead after 3 attempts** (`max_attempts` default).
- **Scheduled Actions are best-effort**: GitHub may delay or drop a `*/15` run, and
  disables schedules after 60 days without repository activity.
- **Render's SIGTERM grace on deploy** is short; a job in flight is left for the
  reaper rather than finished.
- **An interrupted job spends an attempt.** The attempt is counted on claim, so
  every deploy or spin-down that catches a job mid-run costs it one. With
  `max_attempts` at 3, two unlucky redeploys plus one real upstream error end a
  job `dead`. Accepted at this volume; raise `max_attempts` if it shows up.
- **A handler must not block the event loop.** A synchronous PDF parse or SDK
  call longer than `STALE_AFTER` (2 min) stops the heartbeat task too, and the
  reaper requeues a job that is still running. Every post-claim write is fenced
  on `attempts`, so the stale run cannot overwrite the new claim, but the work
  is still done twice — handlers (#59 first) run blocking calls through
  `asyncio.to_thread`.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Redis + arq / Celery** | A paid Redis *and* a paid worker instance, plus a second store to keep consistent with Postgres — for 1–3 jobs at a time |
| **Render background worker** | Paid instance type; and a second free web service would need ~1,460 of 750 instance-hours |
| **Render Cron Job** (~$1/mo) | The honest runner-up: cheap and isolated from the API. Rejected for now because it is not $0, still needs the queue table, and runs on a schedule rather than when work arrives |
| **GitHub Actions as the worker** | Free, but moves `ANTHROPIC_API_KEY` into GitHub secrets and makes production *processing* — not just waking — depend on Actions uptime and queue delays |
| **`LISTEN/NOTIFY` instead of polling** | A permanently checked-out connection through a pooled async engine, Neon idle suspends and spin-downs, to save ≤5 s on a 20–60 s job |
| **`BackgroundTasks` / bare `asyncio.create_task` per request** | Not durable: a spin-down mid-job loses the work with no record it existed |

## Revisit when

- [ ] **A second consumer is needed** (concurrency > 1, or a separate process) — the
      claim is already `SKIP LOCKED`-safe, but heartbeat/reaper timings and the
      ADR-0005 migration race need a fresh look.
- [ ] **A job kind takes minutes rather than seconds** — it no longer belongs in the
      web process's memory and event loop.
- [ ] **The 750-hour cap binds** — e.g. a second free service is wanted in the
      workspace — lengthen the sweep or move to a paid always-on instance.
- [ ] **Render's `starter` plan is adopted** (ADR-0011) — no spin-down, so the sweep's
      wake-up role disappears and only its reaper role remains.
- [ ] **Load grows past ~100 jobs/day**, or polling shows up in Neon compute hours —
      add `NOTIFY` on top, or a partial index on `status = 'queued'`.

## Migration path

The queue's contract is three functions in `app/services/jobs.py` (`enqueue_job`,
`claim_job`, the finishing writes) and the `HANDLERS` registry in `app/worker.py`.
Moving the consumer to a separate process — a Render worker or Cron Job — is running
`Worker(...).run()` from a new entry point and setting `WORKER_ENABLED=false` on the
web service; the table, claim and reaper are unchanged. Moving to a broker means
replacing `enqueue_job` and `claim_job` and dropping `bill_jobs`; the handlers do not
change.
