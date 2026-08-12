# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-08-11
- **Deciders:** llevintza
- **Related:** all subsequent ADRs

## Context

The stack was assembled quickly across PRs #1 and #3, and the reasoning lived in three
places that do not survive: pull request descriptions, chat transcripts, and the
author's memory. Standing up the backend (issue #7) made the cost of that concrete —
several decisions had to be reconstructed from `git log` and file comments to
understand whether they were deliberate or incidental.

The specific need is not documentation for its own sake. It is being able to answer,
when a provider gets expensive, slow, or breached: **why did we pick this, what
exactly does it cost us, and what does moving off look like?**

Provider choices in particular are made under conditions — free tiers, regions,
limits — that change without notice. A decision that was correct in August may be
wrong in November for reasons entirely outside the codebase.

## Decision

We keep **architecture decision records** in [`docs/adr/`](README.md), one file per
decision, numbered sequentially, in the repository alongside the code they describe.

Beyond the conventional Context / Decision / Consequences, every ADR here must carry
three sections, because they are the ones that make the record actionable rather than
archival:

| Section | Why it is mandatory |
| --- | --- |
| **Limitations** | Concrete ceilings, in numbers. Tells a future reader whether they have hit the edge of the decision or merely a bug |
| **Revisit when** | Named triggers. Turns "we should review this sometime" into something you can notice firing |
| **Migration path** | The cost of reversing. This is the number that matters when a trigger fires |

**ADRs are immutable once accepted.** A changed mind means a new ADR that supersedes
the old one, with the old one left intact. Editing history to match the present
destroys the only thing the record is for.

Retroactive ADRs are legitimate and expected — most of the initial set documents
decisions made before this ADR existed. They record the reasoning as it was, with
provenance from git history, not a reconstruction that flatters it.

## Consequences

### What this buys

- Provider and stack choices carry their own migration plans, so moving is a planned
  step rather than an investigation.
- New contributors — and coding agents — get the *why*, which is the part neither the
  code nor `git log` reliably preserves.
- Writing down the negative consequences forces them to be confronted while the
  decision is still cheap to change.

### What this costs

- **ADRs go stale if statuses are not maintained.** A superseded decision still marked
  Accepted is worse than no ADR, because it is actively misleading.
- Writing a good one takes real time, which biases toward skipping it under pressure.
- Judgement is needed about what deserves one; over-recording buries the decisions
  that matter.

## Limitations

- Only captures decisions someone chose to write down. Implicit and accidental
  choices stay invisible.
- Nothing enforces that code matches its ADR — no test asserts `render.yaml` still
  says what [ADR-0011](0011-backend-hosting-render.md) claims.
- Numbers quoted from provider free tiers will drift; treat them as "as of the ADR
  date".

## Alternatives considered

| Option | Why not |
| --- | --- |
| **A wiki or Notion** | Decouples decisions from the code they describe; drifts silently and is invisible in review |
| **PR descriptions only** | Where the reasoning already was — unsearchable in practice, and no place to record a *later* revisit trigger |
| **Comments in code** | Good for local "why" (this repo uses them well), but cannot hold alternatives, costs, or migration paths |
| **A single ARCHITECTURE.md** | Describes the present; loses the history and the superseded reasoning, which is the point |
| **No records** | The status quo that made issue #7 more expensive than it needed to be |

## Revisit when

- [ ] **ADRs are consistently not written** for significant decisions → the format is
      too heavy; simplify it rather than abandoning it.
- [ ] **The set grows past ~30** → add grouping or an index by topic.
- [ ] **A decision is found contradicting its ADR** → consider a test that asserts the
      config matches the record, as `test_config.py` already does for database identity.

## Migration path

Plain Markdown with no tooling, so any ADR tool (adr-tools, Log4brains) can adopt the
directory as-is, and any static site generator can publish it.
