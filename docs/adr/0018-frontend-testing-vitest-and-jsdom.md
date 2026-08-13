# 18. Frontend testing: Vitest for logic, jsdom for behaviour, a browser for layout

Date: 2026-08-13

## Status

Accepted. Supersedes the "No test runner for the frontend" limitation recorded in
[ADR-0007](0007-react-vite-spa.md), whose revisit trigger — *"the frontend needs real
tests → Vitest + Testing Library"* — is what this closes.

## Context

Until [#33](https://github.com/llevintza/energlens/pull/33) the frontend had no test
runner and `tsc -b` was the whole gate. That was defensible while the frontend was view
code over an API that did its own arithmetic.

The redesign ([#15](https://github.com/llevintza/energlens/issues/15)) changes the shape
of the problem. `frontend/src/lib/metrics.ts` now computes every figure the product
exists to show — effective price, trailing-12 comparisons, composition shares,
cumulative excess — and it must agree with `backend/app/services/series.py` to the digit,
because the dashboard derives months from `/bills` while other views read `/series`. Two
bucketing implementations that disagree put two different numbers for one month on one
screen.

The screens also carry behavioural requirements the handoff states as requirements
because they were live bugs in the prototype: a control that is dimmed but still fires, a
metric selector whose two views drift out of sync, an empty state shown for a request
that actually failed.

## Decision

Three tiers, matched to what each can actually settle.

**Vitest in the `node` environment** for pure logic — the metrics module, the axis
helpers, error description. Default environment, no DOM, fast.

**Vitest in `jsdom` with `@testing-library/react`** for component behaviour that does not
depend on layout: a control being genuinely `disabled`, two views of one state staying in
sync, an error state not being rendered as an empty one. Opted into per file with a
`@vitest-environment jsdom` docblock, so logic specs keep paying nothing for it.

**A real browser** for anything involving layout, colour or geometry, recorded as a
checklist in the PR that introduces it.

Config lives in `frontend/vitest.config.ts`, separate from `vite.config.ts`. Fixtures for
the metrics specs replay `backend/app/seed.py` in TypeScript, pinned to the 24 months
ending July 2026.

## Consequences

- `make check` and the required `frontend-build` job both run the suite, unchanged —
  `ci-frontend` already depended on `test-frontend` so that adding a runner would land in
  the gate rather than escape it.
- The handoff's own figures are assertions. A regression in the arithmetic fails the
  build rather than being noticed on a chart.
- Three new devDependencies: `jsdom`, `@testing-library/react`,
  `@testing-library/user-event`.
- The suite takes about 0.8s, of which roughly 0.45s is standing up jsdom for one file.
- Test fixtures are a second implementation of the seed generator. They can drift from
  the Python one; the parity check below is what catches it.

## Limitations

- **jsdom has no layout engine.** `getBoundingClientRect()` returns all zeros and
  `document.elementFromPoint` does not exist. Anything about hit-testing, stacking order,
  overflow or responsive breakpoints is unanswerable here, and a test that appears to
  answer it is lying.
- No visual regression testing. Colour, contrast and spacing are reviewed by eye.
- The `/bills` ÷ `/series` parity check is run by hand against a seeded local API, not in
  CI, because CI's frontend job has no database. Drift between the two bucketing
  implementations would therefore survive a green build.
- Component specs cover primitives, not screens. A screen can still be assembled wrongly
  out of correct parts.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Keep `tsc -b` only** | Types cannot express "3,060 kWh in both windows" or "this month must equal what the API returns for it". The arithmetic is the product |
| **jsdom for the hit-test requirement too** | It cannot do it — see Limitations. Writing the test anyway would produce a passing suite over a shipped bug, which is worse than no test |
| **Vitest browser mode (Playwright)** | Real layout, so it *could* settle the hit-test. Rejected for now: a browser download in a job that currently runs in ~21s, to gate one assertion. This is the escalation path if component tests multiply |
| **Cypress / Playwright end-to-end** | Needs a running API and database; duplicates what the backend suite already covers, and the deploy smoke already checks the built site loads |
| **Snapshot tests** | Would freeze the markup of screens being actively redesigned, and record bugs as expectations |

## Revisit when

- [ ] **A layout or hit-testing bug ships that a test could have caught** → adopt Vitest
      browser mode with the Playwright provider; the specs mostly port across, since
      Testing Library queries are the same.
- [ ] **The parity check fails, or the seed generator changes** → move parity into CI by
      giving the frontend job the backend's Postgres service, or generate the fixture
      from Python at build time so there is one generator.
- [ ] **jsdom setup cost exceeds the logic suite's runtime** → split into two Vitest
      projects so `make test-frontend` can run the fast half on its own.
- [ ] **Contrast or spacing regressions become common** → visual regression tooling,
      which is a different decision with real hosting cost.

## Migration path

Moving to browser mode means adding `@vitest/browser` and a Playwright provider, changing
`environment` to a `browser` block, and dropping the jsdom docblocks. Testing Library
queries and every assertion in the component specs carry over. The node-environment logic
specs are unaffected and should stay in the node project for speed.

Dropping testing entirely would mean deleting `frontend/src/**/*.test.{ts,tsx}` and
`vitest.config.ts`; `make test-frontend` falls back to typecheck alone, which is where
this started.
