---
name: issue-to-production
description: >-
  Take a GitHub issue to a verified production deployment: read the issue thread, surface
  the decisions it leaves open, land the code behind the repo's gate, verify against the
  real running system rather than only tests, open a PR, merge, deploy, verify from
  outside, and record the outcome back on the tracker. For issues ending in a deploy or a
  config change a human must click through.
when_to_use: >-
  Use when picking up a GitHub issue that ends in something running in production, or on
  requests like "pick up issue 14", "implement and deploy this issue". For a change needing
  only commit-push-PR, use the lighter `ship` skill instead.
argument-hint: "[issue-number-or-url]"
allowed-tools: Bash(gh issue view *) Bash(gh pr view *) Bash(gh pr checks *) Bash(gh pr diff *) Bash(git log *) Bash(git status *) Bash(git diff *) Bash(git show *)
---

# Issue → production

Carry one GitHub issue from unread to verified-in-production, leaving a record good
enough that nobody re-derives any of it.

**Tests prove the code does what you told it to. Only running the real thing proves you
told it the right thing.** Phases 5 and 9 are where those diverge, and where most of
the value here sits.

## Reference files

Load these when you reach the phase that needs them — not up front.

- **[reference/verification.md](reference/verification.md)** — verifying a deployment
  from outside. Read at phase 9, or whenever a probe disagrees with expectations.
- **[reference/case-study.md](reference/case-study.md)** — the run this was extracted
  from, with the failures behind each rule. Read when a rule looks like overhead.

---

## 1. Read the whole thread

```sh
gh issue view <N> --comments
```

Read the issues it references too. Extract, before touching code:

- **What already exists.** Issues often say "do not rebuild X" — believe them, then
  verify with `git log` on the files they name.
- **The decisions the issue leaves open.** These are not yours to default.
- **Claims worth re-checking.** Confirm the problem still reproduces before fixing it;
  an issue written days ago may describe a state that has changed.

Where a comment contradicts the issue body, the comment is usually newer. Reconcile
explicitly rather than picking one.

## 2. Explore before planning

Map the code the issue touches. Read `AGENTS.md` / `CLAUDE.md` first if present — they
usually encode the gate, the conventions and the traps. Identify what to **reuse**
rather than write.

## 3. Put the open decisions to the user

Present each decision the issue flagged with its real trade-off and a recommendation.
Do not silently pick defaults.

Raise anything the issue got *wrong* in a sentence or two, give a recommendation, and
keep going — do not stop the work over it.

## 4. Sequence the work

When an issue mixes code with infrastructure someone must click through, **land the
code first**, so the first deploy already contains it and any runbook you write is in
the repo while it is being followed.

Check what the deploy pipeline's path filters mean for your change — docs-only or
config-only commits often trigger nothing.

## 5. Implement, then gate

Run the repo's full gate, not a subset:

```sh
make check          # or exactly what CI runs
```

**Write the test that reproduces the real failure**, not a mock of it. A stub proves
your handler works on your stub. Where a failure comes from outside the process — a
dead socket, a missing file, an unreachable service — reproduce that condition; the
real error often takes a different path than the one you would mock.

Then confirm the test is not vacuous: **break the code deliberately and check the test
goes red.** Do this for tests guarding a security property — credential leaks, authz,
input validation — not for everything.

> Restore with your editor or a saved copy. `git checkout <file>` discards the change
> you are testing.

## 6. Pull request

Explain **why**; the diff already says what. Record what you verified and how, so a
reviewer can judge the evidence instead of re-gathering it. Note surprises explicitly —
a PR saying "this caught a real bug the tests missed, here is the repro" is worth more
than one asserting all is well.

```sh
gh pr create --title "..." --body "..."
gh pr checks <N>
```

Defer to the repo's conventions or the `ship` skill for commit-message style.

## 7. Merge

Respect branch protection. If merging is the user's call, say the PR is ready and why,
then stop. After merge, confirm what landed:

```sh
git fetch origin && git log --oneline origin/main -1
git diff --stat origin/main       # empty = your worktree matches
```

## 8. Deploy

For steps behind someone else's credentials, hand over **exact** instructions: the
literal value to paste, the literal control to click, what a healthy log looks like,
and what should make them stop and come back (a payment prompt, a refused plan, an
unexpected region).

**Validate every input you can before it is pasted anywhere.** Connection strings,
hostnames and tokens can be tested directly, and a verified value costs minutes where a
plausible guess costs an afternoon.

## 9. Verify from outside

→ **[reference/verification.md](reference/verification.md)**

The platform saying "live" is not verification. Check each layer separately so a
failure localises itself, sample intermittent behaviour rather than trusting one
request, and sanity-check your probe against a known-good case before reporting a
fault.

## 10. Record, then close

- **On the issue:** verified end state, the checklist with real results, and anything
  that differed from the plan — especially instructions in the issue that proved wrong.
- **On related issues:** constraints you discovered that change their scope.
- **New issues:** for defects found along the way, *including ones already resolved*,
  so the diagnosis is not repeated.
- **In the repo:** decisions made — a provider, a limit, a trade-off — recorded where
  they will be found. An ADR if the repo keeps them.

```sh
gh issue close <N> --reason completed
```

---

## Standing rules

Apply these throughout, not once.

**Report faithfully.** If something is unverified, say so; if a check was skipped, say
which. "The backend is up; the UI path is unverified" is useful. "It works" is not.

**Correct yourself plainly.** When a measurement turns out wrong, state the correction
and the corrected figure, then continue. Do not bury it, do not dwell on it.

**Prefer the confirmable over the plausible.** DNS resolving, a page loading, a status
reading "live" — none prove the thing you care about. Find the check that does.

**Never put a credential anywhere durable** — not a committed file, not a harness
settings file, not a scratch script left on disk. Delete temp files that held one and
verify:

```sh
grep -rn "<secret-prefix>" . --exclude-dir=.git --exclude-dir=node_modules
```

If a secret passed through a chat or a log, say so plainly and recommend rotating it.
