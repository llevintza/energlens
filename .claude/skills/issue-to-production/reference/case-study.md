# Case study: energlens issue #7

The run this skill was extracted from. Read it when you want the evidence behind a
phase, or when a rule in `SKILL.md` seems like overhead and you want to know what it
cost to learn.

**The task:** stand up a backend — Neon Postgres + Render — for a live frontend whose
every API call was failing.

---

## Phase 1 — the thread contained the diagnosis

The issue carried a comment recording `x-render-routing: no-server`, already proving
nothing was deployed. Re-running that one `curl` at the start confirmed the blocker was
still live, cost ten seconds, and meant no time was spent re-diagnosing a known cause.

The same comment also **contradicted the issue's own checklist**: the checklist assumed
a hostname that was in fact a guess. Reading only the issue body would have inherited
that assumption silently.

## Phase 3 — the issue's decisions were genuinely open

The issue named two, and defaulting either would have been wrong:

**`/health` doing a `SELECT 1`.** The obvious answer is yes. It is wrong here: `/health`
is the platform's `healthCheckPath`, polled on a schedule, so a database round-trip
would pay a scale-to-zero cold start on every probe and let a *sleeping* database look
like a *dead process* — an outage caused by the monitoring. The resolution was a second
endpoint, `/health/db`, leaving `/health` untouched.

**A public demo account.** Kept, deliberately, and recorded with a hard expiry
condition rather than left implicit in a config flag.

## Phase 5 — the bug a green test suite could not see

The readiness endpoint caught `SQLAlchemyError`. Nine tests passed, including one that
asserted a 503 by raising a hand-built `OperationalError`.

Run against a genuinely unreachable database, it returned **500 with no log line**:

```console
$ curl -sS -w ' [%{http_code}]' http://localhost:8001/health/db
Internal Server Error [500]
```

SQLAlchemy only wraps what the driver raises *after* a connection exists. A socket-level
failure — suspended database, wrong hostname, TLS error, timeout — arrives raw as an
`OSError` subclass and never becomes a SQLAlchemy exception. **The stub could not
express the real failure mode, which is exactly why the stubs passed.**

The fix was a test that binds a socket, closes it, and points a real engine at the dead
port:

```python
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
engine = create_async_engine(f"postgresql+asyncpg://u:p@127.0.0.1:{dead_port}/db")
```

It fails against the old narrow `except`. That is the property that makes it a
regression test rather than a restatement of the implementation.

## Phase 5 — mutation-checking the leak guard

The endpoint must never return the exception, because SQLAlchemy error reprs embed the
connection URL, password included, on an unauthenticated endpoint.

The test planted a realistic DSN inside the raised exception and asserted it never
reached the body. To confirm the test was not vacuous, the endpoint was temporarily
changed to `return {"database": repr(exc)}` — the test went red, naming the leak. Then
it was restored.

Cost: one minute. Without it, "the leak guard passes" would have been an untested claim.

## Phase 8 — validating an input before it was pasted anywhere

Neon's connection string needs three rewrites, none of which fail at paste time. The
non-obvious one:

| Candidate | Result |
| --- | --- |
| `ep-xxx.c-4.us-east-2…` (delete only `-pooler`) | connects |
| `ep-xxx.us-east-2…` (also delete `c-4`) | `InvalidPasswordError` |
| `?sslmode=require` | `TypeError: … unexpected keyword argument 'sslmode'` |

"Use the direct endpoint, not `-pooler`" reads as *strip the pooler prefix*, and the
adjacent `c-N` looks like part of the region. It is not — it is endpoint identity, and
the provider routes by SNI. Strip it and the host **still resolves and still completes
a TLS handshake**, then fails on the password, sending you to inspect a credential that
was never wrong. DNS is no help: all three candidate names resolve.

Testing all three took two minutes and replaced a plausible guess with a verified fact.

## Phase 9 — measuring an intermittent fault

After the service reported live, requests alternated between the app and a `no-server`
404. Successive samples:

| Elapsed | Routed |
| --- | --- |
| t+0 | 4/10 |
| t+5m | 8/10 |
| t+8m | 15/20 |
| t+12m | 8/20 |

**Oscillating, not converging** — which is what distinguished "still propagating, wait"
from "actually broken, act". No single request could have shown this. Acting on the
first 404 would have meant debugging a non-existent config problem; acting on the first
200 would have meant declaring success on a half-broken service.

Resolution was a cache-clearing redeploy; steady state 30/30.

## Phase 9 — two false alarms from bad probes

Both produced confident, wrong statements before being caught.

**`HEAD /health` returning 405.** Read as a routing failure. It was FastAPI declining to
auto-register `HEAD` for a `@app.get` route — those requests were reaching the app
perfectly. The `allow: GET` response header was the tell, and it was in the output all
along.

**A per-connection probe that corrupted its own count.** It passed several URLs to one
`curl` with a single `-o /dev/null`. curl applies `-o` to the *first* URL only, so the
remaining response bodies went to stdout and broke the `^200$` token match — healthy
connections were counted as degraded. The reported baseline ("0/12 fully working")
overstated the severity, and had to be corrected.

The corrected probe supplies `-o /dev/null` per URL. Both errors would have been caught
by running the probe against a known-good case first.

## Outcome

Merged, deployed, verified: migrations applied, seed landed, CORS and JWT confirmed
cross-origin, 30/30 routing. Two issues filed for defects found on the way (one already
resolved, recorded so it is not re-diagnosed), constraints added to a third, and the
original closed with the checklist showing real results.
