# Verifying a deployment from outside

Load at phase 9, once something is deployed and you need to decide whether it works.

The platform reporting "live" is not verification. Neither is one successful request.

---

## Verify each layer separately

A single end-to-end check that fails tells you nothing about *where*. Separate probes
localise the fault themselves.

| Layer | Question it answers | Fails when |
| --- | --- | --- |
| Liveness endpoint | Is the process up? | Build or boot failed |
| Readiness endpoint | Can it reach its database? | DSN wrong, database asleep or unreachable |
| CORS preflight with the real `Origin` | Will a browser be allowed to call it? | Origin misconfigured |
| Authenticated round-trip | Do auth, database and serialization work together? | Migrations, secrets or schema |
| The deployed frontend asset | Is it built against the URL you think? | Build-time variable is stale |

That last row catches a whole class of silent failure. Where config is inlined at build
time, the variable and the shipped bundle can disagree indefinitely — **grep the
deployed asset** rather than trusting the variable:

```sh
PAGE=$(curl -sS "$SITE/")
ASSET=$(printf '%s' "$PAGE" | grep -o '/assets/index-[A-Za-z0-9_-]*\.js' | head -1)
curl -sS "$SITE$ASSET" | grep -o 'https://[a-z0-9.-]*\.example\.com' | sort -u
```

## Distinguish "not deployed" from "wrong route"

These look identical in a browser and are frequently confused. The response body tells
them apart:

| Response | Meaning |
| --- | --- |
| `404`, plain-text body, platform routing header | Edge — nothing claims this hostname |
| `404` with the framework's JSON error shape | App is up, route is wrong |
| `405` plus an `Allow` header | App is up, **method** is wrong |

Wildcard hostnames (`*.onrender.com`, `*.vercel.app`) make this worse: a typo'd or
guessed host resolves and returns a plausible 404 rather than failing to resolve. There
is no DNS error to give the game away.

## Measure before concluding

Intermittent failures need a sample, not an anecdote. Count, then state the count.

```sh
ok=0; for i in $(seq 1 20); do
  c=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 45 "$H/health?i=$i")
  [ "$c" = "200" ] && ok=$((ok+1))
done; echo "routed: $ok/20"
```

Take **successive** samples over several minutes. A rising series is propagation —
wait. A flat or oscillating series is a fault — act. One request cannot tell you which,
and acting on it picks a random one of two opposite actions.

## Sanity-check the probe before trusting it

Before reporting a fault, confirm the probe is sound — run it against a case you know
is good. A wrong probe produces a confident, specific, wrong report.

Two that have actually happened, both in `case-study.md`:

- **`curl -I` against a framework that does not auto-register `HEAD`** returns 405 on a
  perfectly healthy endpoint. Use `GET` for reachability checks.
- **One `-o /dev/null` with several URLs** applies to the first URL only; the remaining
  bodies land in stdout and corrupt any parsing of the output. Supply `-o` per URL.

Also: allow for cold starts (`--max-time 90` where a free tier sleeps), defeat caching
(`-H 'Cache-Control: no-cache'` plus a varying query parameter), and remember that a
reused connection and a fresh one can route differently.

## Deploy-time reachability checks

If you add one to a pipeline, it must:

- use `GET`, for the reason above;
- assert the *body*, not just a 2xx — that distinguishes your service from any other
  server answering on that host;
- **retry across fresh connections** rather than using one long timeout. Where routing
  is flapping or the host is cold, each attempt fails fast, so a longer timeout does
  not help and only a retry does;
- point at **liveness**, not readiness — gating a frontend deploy on the database being
  up blocks shipping for an unrelated fault.
