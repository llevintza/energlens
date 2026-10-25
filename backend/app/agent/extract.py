"""The extraction agent: one bill PDF in, one validated envelope out (#57).

    context = await load_context(session, place_id, exclude_document_id=doc.id)
    result = await extract_bill(pdf_bytes, context=context, document_id=doc.id)
    if result.status == "succeeded":
        ...result.envelope...

The loop is the SDK's beta tool runner (ADR-0024). Its ``async for`` body is
the per-turn hook: each assistant message is recorded there *before* its tool
calls run, the stop reason is checked there before anything reads
``content``, and the tools are run there explicitly so that each call's
outcome becomes an agent_steps row. No manual ``while stop_reason ==
"tool_use"`` loop was needed.

Every run lands in agent_runs (via AgentRecorder, #56) with one of:

- ``succeeded`` — submit_extraction accepted a payload;
- ``refused`` — ``stop_reason == "refusal"``, after any server-side fallback;
- ``failed`` — ``max_tokens`` truncation, or the model stopped without an
  accepted submission, or an API error (which also propagates);
- ``over_budget`` — ``agent_max_iterations`` turns without a submission.

Model-level outcomes come back as an ``ExtractionResult``; only API and
transport errors raise, so the job worker (#60) has one thing to branch on.
"""

import base64
import logging
import uuid
from dataclasses import dataclass

import anthropic
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.context import ExtractionContext
from app.agent.envelope import ExtractionEnvelope
from app.agent.prompt import prompt_version, system_prompt
from app.agent.recorder import AgentRecorder
from app.agent.regions import select_profile
from app.agent.tools import ExtractionTools, page_texts
from app.config import settings
from app.models.agent_run import RUN_FAILED, RUN_OVER_BUDGET, RUN_REFUSED, RUN_SUCCEEDED

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

USER_TEXT = (
    "Extract this bill. Use the tools, check your arithmetic, and finish by "
    "calling submit_extraction."
)


@dataclass(frozen=True)
class ExtractionResult:
    run_id: uuid.UUID
    status: str
    envelope: ExtractionEnvelope | None
    stop_reason: str | None
    profile: str | None
    error: str | None = None


class _RunEnded(Exception):
    """Raised inside the recorder so the run row gets ``failed`` and an
    ``error_kind``; caught outside it and turned into a result."""

    def __init__(self, error_kind: str, message: str) -> None:
        super().__init__(message)
        self.error_kind = error_kind


async def _document_block(
    client: AsyncAnthropic, pdf: bytes, filename: str
) -> tuple[dict, str | None]:
    """Upload once and reference by file_id on every turn; if the Files API is
    unavailable, fall back to sending the PDF inline."""
    try:
        uploaded = await client.files.upload(file=(filename, pdf, "application/pdf"))
        return {
            "type": "document",
            "source": {"type": "file", "file_id": uploaded.id},
        }, uploaded.id
    except anthropic.APIError as exc:
        logger.warning("Files API upload failed (%s); sending the PDF inline", exc)
        data = base64.standard_b64encode(pdf).decode()
        source = {"type": "base64", "media_type": "application/pdf", "data": data}
        return {"type": "document", "source": source}, None


async def _delete_file(client: AsyncAnthropic, file_id: str) -> None:
    # Uploaded files persist until deleted. Losing this call leaves one stray
    # file in the org's storage, which is not worth failing a run over.
    try:
        await client.files.delete(file_id)
    except anthropic.APIError:
        logger.warning("could not delete uploaded file %s", file_id)


def _record_tool_steps(
    rec: AgentRecorder, tool_uses: list, response: dict, tools: ExtractionTools
) -> None:
    results = {r["tool_use_id"]: r for r in response["content"]}
    for block in tool_uses:
        result = results.get(block.id, {})
        failed = bool(result.get("is_error"))
        duration_ms = None
        # Tools run in order, and only those whose body ran left a timing.
        if tools.timings and tools.timings[0][0] == block.name:
            duration_ms = tools.timings.pop(0)[1]
        detail: dict = {}
        if block.name != "submit_extraction":
            detail["input"] = block.input
        if failed:
            detail["error"] = result.get("content")
        rec.step(
            kind="tool_use",
            tool_name=block.name,
            ok=not failed,
            duration_ms=duration_ms,
            detail=detail or None,
        )
    tools.timings.clear()


async def extract_bill(
    pdf: bytes,
    *,
    context: ExtractionContext,
    client: AsyncAnthropic | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    filename: str = "bill.pdf",
    document_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    is_eval: bool = False,
) -> ExtractionResult:
    pages = page_texts(pdf)
    profile = select_profile(
        context.place.country_code,
        [pages[0] if pages else "", context.place.known_provider_name or ""],
    )
    system = system_prompt(profile)
    tools = ExtractionTools(pages=pages, context=context)
    if client is None:
        client = AsyncAnthropic()

    rec = AgentRecorder(
        kind="extract",
        session_factory=session_factory,
        model=settings.agent_model,
        is_eval=is_eval,
        job_id=job_id,
        document_id=document_id,
        profile=profile.id if profile else None,
        prompt_version=prompt_version(system),
        effort=settings.agent_effort,
    )
    profile_id = profile.id if profile else None
    try:
        async with rec:
            await _run(client, rec, tools, system, pdf, filename)
    except _RunEnded as exc:
        return ExtractionResult(
            rec.run_id, RUN_FAILED, None, rec.stop_reason, profile_id, str(exc)
        )

    status = rec.status or (
        RUN_REFUSED if rec.stop_reason == "refusal" else RUN_SUCCEEDED
    )
    return ExtractionResult(
        rec.run_id, status, tools.submitted, rec.stop_reason, profile_id
    )


async def _run(
    client: AsyncAnthropic,
    rec: AgentRecorder,
    tools: ExtractionTools,
    system: str,
    pdf: bytes,
    filename: str,
) -> None:
    document, file_id = await _document_block(client, pdf, filename)
    fallback: dict = (
        {"fallbacks": "default", "betas": [FALLBACK_BETA]}
        if settings.agent_refusal_fallback
        else {}
    )
    runner = client.beta.messages.tool_runner(
        model=settings.agent_model,
        max_tokens=settings.agent_max_tokens,
        max_iterations=settings.agent_max_iterations,
        system=system,
        tools=tools.all(),
        messages=[
            {"role": "user", "content": [document, {"type": "text", "text": USER_TEXT}]}
        ],
        # Thinking is omitted: adaptive is the default on this model, and
        # effort is the only control it takes.
        output_config={"effort": settings.agent_effort},
        # Every turn resends the PDF; caching the prefix is the difference
        # between paying for it once and paying for it on every turn.
        cache_control={"type": "ephemeral"},
        **fallback,
    )
    last = None
    try:
        async for message in runner:
            last = message
            rec.message(message)
            tool_uses = (
                [b for b in message.content if b.type == "tool_use"]
                if message.stop_reason == "tool_use"
                else []
            )
            rec.step(
                kind="assistant",
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                detail={
                    "stop_reason": message.stop_reason,
                    "tool_calls": [b.name for b in tool_uses],
                },
            )
            # Checked before content is read: a refusal's content is empty or
            # partial, and a truncated turn's last tool call is cut off.
            if message.stop_reason == "refusal":
                return
            if message.stop_reason == "max_tokens":
                raise _RunEnded(
                    "internal",
                    f"max_tokens: the response was cut off at {settings.agent_max_tokens} tokens",
                )
            if not tool_uses:
                continue
            response = await runner.generate_tool_call_response()
            if response is not None:
                _record_tool_steps(rec, tool_uses, response, tools)
            if tools.submitted is not None:
                # Accepted: stop here rather than pay for a turn in which the
                # model says "done".
                return
    finally:
        await runner.close()
        if file_id is not None:
            await _delete_file(client, file_id)

    if last is not None and last.stop_reason == "tool_use":
        rec.status = RUN_OVER_BUDGET
        return
    raise _RunEnded(
        "schema_invalid",
        f"the model stopped ({last.stop_reason if last else 'no response'}) "
        f"without an accepted submit_extraction",
    )
