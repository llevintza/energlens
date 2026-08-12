---
name: issue-to-production
description: >-
  Take a GitHub issue all the way to a verified production deployment: read the issue and
  its thread, surface the decisions it leaves open, land the code behind the repo's gate,
  verify against the real running system rather than only tests, open a PR, merge, deploy,
  verify from outside, and record what was learned back on the tracker. Built for issues
  that end in a deploy or a config change a human must click through.
when_to_use: >-
  Invoke with /issue-to-production <issue-number-or-url> when picking up a GitHub issue that
  ends in something running in production. For a change that only needs commit-push-PR, the
  lighter `ship` skill is the right tool.
argument-hint: "<issue number or URL>"
---

# Issue → production

Carry one GitHub issue from unread to verified-in-production, leaving a record good
enough that nobody re-derives any of it.

The organising principle: **tests prove the code does what you told it to; only running
the real thing proves you told it the right thing.** Most of the value in this workflow
sits in phases 5 and 9, where those two diverge.

---

## Phase 1 — Read the whole thread, not just the issue

```sh
gh issue view <N> --comments
```

Then read the issues it references. A well-written issue often contains a comment
that has already diagnosed the problem, or a caveat that invalidates its own
checklist — skipping the thread means re-doing that work.

Extract three things before touching code:

1. **What already exists.** Issues frequently say "do not rebuild X". Believe them,
   then verify — `git log` the files they name.
2. **The decisions the issue leaves open.** Good issues name them explicitly
   ("two decisions to make while deploying"). These are *not* yours to default.
3. **The claims worth re-checking.** An issue written days ago may describe a state
   that has changed. Confirm the problem still reproduces before fixing it.

> **Worked example (energlens #7).** The issue's own comment recorded
> `x-render-routing: no-server`, proving nothing was deployed. Re-running that one
> `curl` at the start confirmed the blocker was still live and cost ten seconds.

## Phase 2 — Explore before planning

Map the code the issue touches. Where the repo has an agents file (`AGENTS.md`,
`CLAUDE.md`), read it first — it usually encodes the gate, the conventions, and the
traps.

Identify what to **reuse** rather than write. New code that duplicates an existing
helper will be caught in review, or worse, will not be.

## Phase 3 — Put the open decisions to the user

Do not silently pick defaults for decisions the issue flagged. Present each with its
real trade-off and a recommendation.

This is also the point to raise anything the issue got *wrong*. State it in a sentence
or two, give your recommendation, and proceed — do not stop the work over it.

> **Worked example.** #7 raised whether `/health` should do a `SELECT 1`. The
> recommendation — add a separate `/health/db` and leave `/health` alone, because it
> is the platform's `healthCheckPath` and a database round-trip there would let a
> sleeping database look like a dead process — was accepted. Defaulting either way
> without asking would have been wrong.

## Phase 4 — Sequence the work

When an issue mixes code with infrastructure someone must click through, **land the
code first**, so the first deploy already contains it and any runbook you write is in
the repo while it is being followed.

Check what the deploy pipeline's path filters mean for your change. A docs-only or
config-only commit often triggers nothing at all.

## Phase 5 — Implement, then gate

Run the repo's gate, not a subset of tests.

```sh
make check          # energlens: the union of the merge-gating CI jobs
```

Prefer a gate defined so that **local and CI cannot disagree**. If the repo has no
such target, run exactly what CI runs.

### Write the test that would catch the real failure

A test that mocks the failure proves your handler works on your mock. That is not the
same claim.

> **Worked example — the bug that survived a green suite.** A readiness endpoint
> caught `SQLAlchemyError`. Nine tests passed, including one asserting a 503 by
> raising a hand-built `OperationalError`. Run against a genuinely unreachable
> database it returned **500 with no log line**: SQLAlchemy only wraps what the driver
> raises *after* a connection exists, so asyncpg's `ConnectionRefusedError` arrived
> raw as an `OSError`. The stub could not express the real failure mode.
>
> The fix was a test that binds a socket, closes it, and points a real engine at the
> dead port. It fails against the old narrow `except`.

### Mutation-check any test that guards a security property

If a test asserts "the response must not contain the password", break the code
deliberately and confirm the test fails. A guard that has never failed is not known
to be a guard.

```sh
# make the endpoint leak, run the test, confirm RED, then restore
```

Do this for leak guards, authz checks, and input validation — not for everything.

> Restore with your editor or a backup copy, **not** `git checkout <file>` if you have
> uncommitted work in that file; it will discard the change you are testing.

## Phase 6 — Pull request

Explain **why**, not what — the diff already says what. Record what you verified and
how, so a reviewer can judge the evidence rather than re-gather it.

Note surprises explicitly. A PR saying "this caught a real bug that the tests missed,
here is the repro" is worth more than one asserting everything is fine.

```sh
gh pr create --title "..." --body "..."
gh pr checks <N>        # confirm green before asking for a merge
```

For commit-message style and the mechanics of branch → commit → PR, defer to the
repo's conventions or the `ship` skill.

## Phase 7 — Merge

Respect branch protection; if merging is the user's call, say the PR is ready and why,
and stop there. After merge, confirm what landed:

```sh
git fetch origin && git log --oneline origin/main -1
git diff --stat origin/main          # empty = your worktree matches
```

## Phase 8 — Deploy

For steps behind someone else's credentials, hand over **exact** instructions — the
literal value to paste, the literal button to click, and what a healthy log looks
like. Name the thing that should make them stop and come back (a payment prompt, a
refused plan, an unexpected region).

Prepare and validate every input you can before it is pasted anywhere.

> **Worked example.** Before a connection string went into a dashboard, all three
> candidate rewrites were tested against the real database. The "obvious" rewrite —
> stripping what looked like a region prefix — failed with `InvalidPasswordError` from
> a host that still resolved and still completed a TLS handshake. Testing cost two
> minutes; the alternative was debugging a credential that was never wrong.

## Phase 9 — Verify from outside

The deploy platform saying "live" is not verification. Check the thing users touch.

**Verify each layer separately**, so a failure localises itself:

| Layer | Question it answers |
| --- | --- |
| Liveness endpoint | Is the process up? |
| Readiness endpoint | Can it reach its database? |
| CORS preflight with the real `Origin` | Will the browser be allowed to call it? |
| Authenticated round-trip | Do auth, database and serialization work together? |
| The deployed frontend asset | Is it built against the URL you think? |

Grep the deployed bundle for the API URL rather than assuming the variable is live —
build-time inlining means the variable and the bundle can disagree indefinitely.

### Measure before concluding, and re-measure before reporting

Intermittent failures need a sample, not an anecdote. Count, then state the count.

> **Worked example.** After the service went live, requests alternated between the app
> and a `no-server` 404. Successive samples read 4/10, 8/10, 15/20, 8/20 — oscillating,
> not converging, which distinguished "still propagating" (wait) from "actually broken"
> (act). It was not visible from any single request.

### Distrust your own measurement first

Before reporting a fault, confirm the probe is sound.

> **Two false alarms from one session.** `HEAD /health` returning 405 was read as a
> routing failure; it was FastAPI declining to auto-register `HEAD` for a `@app.get`
> route, and those requests were reaching the app perfectly. Separately, a
> per-connection probe used one `curl -o /dev/null` for several URLs — curl applies it
> to the first only, so the other bodies landed in stdout and corrupted the count,
> making healthy connections read as degraded.
>
> Both produced confident, wrong statements to the user. Sanity-check a probe against
> a known-good case before trusting what it says about a suspected-bad one.

## Phase 10 — Record, then close

Write back what a future reader needs:

- **On the issue:** the verified end state, the checklist with real results, and
  anything that differed from the plan — especially instructions in the issue that
  turned out to be wrong.
- **On related issues:** constraints you discovered that change their scope.
- **New issues:** for defects found along the way, including ones already resolved, so
  the diagnosis is not repeated.
- **In the repo:** if a decision was made — a provider, a limit, a trade-off — record
  it where it will be found. An ADR if the repo keeps them.

Close with a summary that states what was verified and what remains.

```sh
gh issue close <N> --reason completed
```

---

## Standing rules

**Report faithfully.** If something is unverified, say so. If a check was skipped, say
which. "The backend is up; the UI path is unverified" is a useful sentence — "it works"
is not.

**Correct yourself plainly.** When a measurement turns out to be wrong, say what was
wrong, give the corrected figure, and move on. Do not bury it and do not dwell on it.

**Never put a credential anywhere durable.** Not in a committed file, not in a
harness-local settings file, not in a scratch script left on disk. Delete temp files
that held one, and verify:

```sh
grep -rn "<secret-prefix>" . --exclude-dir=.git --exclude-dir=node_modules
```

If a secret passed through a chat or a log, say so plainly and recommend rotating it.

**Prefer the confirmable over the plausible.** DNS resolving, a page loading, a status
saying "live" — none of these prove the thing you actually care about. Find the check
that does.
