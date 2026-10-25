# 0024. Extract bills with a tool-using agent loop on the SDK's beta tool runner

- **Status:** Accepted
- **Date:** 2026-10-25
- **Deciders:** llevintza
- **Landed in:** PR #TBD
- **Related:** [ADR-0023](0023-postgres-job-queue-in-process-worker.md), issues #57, #50, #53, #56, #58, #60, #62, #65

## Context

The ingest CLI extracts a bill with one `client.messages.parse()` call: the whole PDF
base64'd into one user turn, ten output fields and one free-text `confidence_notes`
(`ingest/energlens_ingest/claude_extractor.py`). It works on the easy bills. It has
one turn and no tools, so it cannot:

- look at the previous bill — the only way to tell a `Stornare` from a data-entry
  error, or an estimated read from a real one (index continuity);
- add up its own twelve line items and notice they miss the printed total;
- produce anything to measure: epic #50 wants turns and tool calls per run.

The corpus also needs per-value provenance: #24 highlights the source line of each
value, so every value must say where on the bill it was read.

At the time of writing the Anthropic Python SDK (2.3.0) ships a beta *tool runner*
(`client.beta.messages.tool_runner`) that drives the request → tools → request loop,
and by default continues each conversation over a server-held message thread
(beta `message-threads-2026-08-12`), sending only the new turn. Claude Opus 5.5 runs
adaptive thinking that cannot be disabled; effort is its only depth control, and it
rejects forced `tool_choice`.

## Decision

We extract with an agent loop in `backend/app/agent/`, run by the SDK's beta tool
runner over five `@beta_async_tool` tools — `get_page_text`, `get_place_context`,
`get_prior_bill`, `check_arithmetic` (which calls `app/services/bill_math.py`) and
`submit_extraction`, whose input schema is the Pydantic `ExtractionEnvelope`. Every
extracted value carries `confidence`, `source_page` and `source_text`, and a value
without a span is rejected back to the model as a tool error. The model is
`settings.agent_model`; thinking is left at the model's adaptive default and depth
is set by `settings.agent_effort` (default `medium`). The PDF is uploaded once via
the Files API (now GA, no beta header) and referenced by `file_id`, falling back
to an inline base64 document if the upload fails. Country- and provider-specific
knowledge lives in region profiles — Markdown files plus a TOML registry under
`app/agent/profiles/` — appended to the system prompt; they are data, never code.
Each run is recorded through `AgentRecorder` (#56), with one step per assistant
turn and per tool call.

The runner's `async for` body is used as the per-turn hook: it records each
message, checks `stop_reason` (refusal, max_tokens) before reading content, runs
the tools via `generate_tool_call_response()` so each outcome can be recorded,
and stops as soon as `submit_extraction` accepts — without paying for a closing
"done" turn. No manual loop was needed.

## Consequences

### What this buys

- The model can self-check: it sums its lines against the printed totals and
  corrects itself before submitting, and a rejected submission comes back with
  the exact fields to fix.
- History is available to the model (prior bill, known provider), so credit notes
  are linked and provider changes noticed.
- Every value has provenance for #24, and every run has turns, tool mix,
  `ok`/`duration_ms` per call, tokens and cost for #62.
- A new country is a Markdown file and a registry row; `tests/test_agent_profiles.py`
  proves it needs no Python.

### What this costs

- **The tool runner is a beta SDK surface, and so is the message thread it uses.**
  Either can change shape between SDK releases. The loop leans on two runner
  behaviours — the `async for` body runs before tools do, and
  `generate_tool_call_response()` is cached so tools run once — both pinned by the
  recorded-transport tests, which fail on a breaking change rather than in
  production. `thread=False` is the escape hatch if threads misbehave.
- Several turns cost more than one call: an estimated **~$0.10–0.15 per bill** at
  `claude-opus-5-5` rates against ~$0.04 for the single `parse()` call, from the
  fixtures' token shapes (not yet measured — #58 will).
- Higher latency: four or five turns instead of one. Acceptable behind the job
  queue (ADR-0023); not acceptable in a request path.
- The server-side refusal fallback (`fallbacks: "default"`, on by default via
  `agent_refusal_fallback`) can serve a turn from another model, but the recorder
  prices every token at `agent_model`'s rate. A fallback turn is mispriced by the
  rate difference until the recorder reads `usage.iterations`.

## Limitations

- `max_tokens` 16,000 per turn, thinking and answer together. A truncated turn
  records the run `failed` (`stop_reason='max_tokens'`, `error_kind='internal'` —
  #56's `error_kind` list has no closer value).
- `agent_max_iterations` 12 turns. Hitting it without a submission records the run
  `over_budget`.
- Files API storage is 100 GB per organization; the agent deletes its upload at
  the end of each run, best effort. Files API is not available on Bedrock or Vertex.
- `get_page_text` depends on the PDF's text layer. A scanned bill has none; the
  model still reads the attached document but has nothing to quote verbatim.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep the single `messages.parse()` call | Cheapest and fastest, but cannot self-check, cannot see the prior bill, and yields no turn or tool metrics — the three things the epic needs. |
| The Batches API | 50 % cheaper, but up to 24-hour turnaround: wrong for 1–3 interactive uploads someone is waiting on. |
| The Claude Agent SDK | A different package: the Claude Code harness with built-in filesystem and shell tools. A server-side extractor wants five narrow tools of its own, not a coding agent. |
| A hand-written `while stop_reason == "tool_use"` loop | No beta dependency, but re-implements what the runner gives (tool dispatch, schema from signatures, input validation, error results). The runner's loop body already offers every hook this needs. |
| Forced `tool_choice` to make `submit_extraction` the answer | Rejected with a 400 by Claude Opus 5.5. The prompt names the tool instead, and a run that ends without a submission is recorded `failed`. |
| `strict: true` on `submit_extraction` | Would guarantee schema-shaped input, but cannot express the conditional rule that matters ("a non-null value needs a span"), so validation would still be ours. Validating in the tool returns errors the model can act on. Worth re-testing once #58 can measure rejection rates. |

## Revisit when

- [ ] The tool runner or message threads leave beta, or an SDK upgrade breaks the
      recorded-transport tests.
- [ ] #58's eval shows a single call at higher effort matches the loop's accuracy
      — then the extra turns are not paying for themselves.
- [ ] Median turns per run (agent_runs.turns) exceeds 8, or more than 5 % of runs
      end `over_budget` or `failed` on `max_tokens`.
- [ ] A fallback model serves more than a few percent of turns — then price
      `usage.iterations` per model.

## Migration path

Back to one call: `extract_bill` keeps its signature and returns the same
`ExtractionEnvelope`; replace `_run` with one `messages.parse()` using the envelope
as `output_format`, and drop the tools. The envelope, profiles and recorder are
unaffected. To a manual loop: replace the runner with a `while` over
`client.beta.messages.create`, keeping the same body.

## Cost model

Current total: **$0/month** — nothing calls the agent until #60 wires it into the
job worker. Per bill, the estimate above (~$0.10–0.15). At 1–3 bills a month that
is under $1/month; the realistic first jump is an eval loop (#58) run on every
commit, at ~$0.15 × corpus size per run.
