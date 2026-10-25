# Recorded-transport fixtures for the extraction agent

Each `*.json` is one agent run, replayed by `tests/agent_transport.py` through a
real `AsyncAnthropic` client whose HTTP layer is an `httpx2.MockTransport`. No
test reaches the network or needs `ANTHROPIC_API_KEY`.

**Every value here is synthetic.** These are hand-built in the real Messages API
response shape, not recordings: the corpus bills are real invoices and must
never be committed (AGENTS.md), and recording them would mean paying for API
calls in order to commit personal data. Names, tax ids, customer codes, invoice
numbers and meter serials are placeholders (`SYN…`, `RO00000000`). Each case
reproduces the *property* of a corpus bill that breaks a naive extraction:

| Case | Stands in for | What it pins |
| --- | --- | --- |
| `clean_2025_06` | 2025-06 | 12 lines, 7 and 12 subtotals, energy at two prices, carried balance; reconciles |
| `credit_note_2024_12_1` | 2024-12-1 | a Stornare: `credit_note`, negative amounts, `corrects_invoice_number` |
| `long_period_2024_02` | 2024-02 | a 417-day printed period kept as printed; a span-less submit rejected, then fixed |
| `vat21_2026_07` | 2026-07 | `vat_rate = 0.21`, `net_amount ≠ vat_base` |
| `tool_raises` | — | a tool exception becomes an `is_error` result, not a failed run |
| `refusal` | — | `stop_reason: refusal`, empty content → run `refused` |
| `max_tokens` | — | truncation → run `failed`, no tool runs |
| `over_budget` | — | never submits → run `over_budget` at the iteration cap |

Shape of a case:

```json
{
  "description": "…",
  "pages": [["line", "line"], ["page 2 line"]],
  "responses": [ { "id": "msg_…", "type": "message", "role": "assistant",
                   "content": [...], "stop_reason": "tool_use", "usage": {...} } ]
}
```

- `pages` is the bill's text layer; the test builds a PDF from it in memory
  (`make_text_pdf`), so `get_page_text` returns exactly these lines and every
  `source_text` in a submission can be checked against them. Keep it ASCII —
  the in-memory PDF uses Helvetica's standard encoding.
- `responses` are returned in order, one per `POST /v1/messages`. A run that
  makes more calls than there are responses fails the test.
- Thinking blocks are empty strings with a signature, as Claude Opus 5.5
  returns them by default (`display: "omitted"`).

To add a case: write the JSON by hand (or with a throwaway script — do not
commit one that reads a real bill), keep the arithmetic in it consistent, and
add a test in `tests/test_agent_extract.py`. `tests/test_agent_envelope.py`
validates every accepted submission against the envelope.
