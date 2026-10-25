"""AgentRecorder: the context manager the agent runtime (#57) wraps its loop in.

    async with AgentRecorder(kind="extract", document_id=doc.id) as rec:
        response = await client.messages.create(...)
        rec.message(response)          # usage, stop_reason, refusal category
        rec.step(kind="tool_use", tool_name="get_page_text", duration_ms=12, ok=True)

Two rules shape everything here:

- **The run row exists even when the run crashes.** ``__aexit__`` writes
  ``status='failed'`` with ``error_kind``/``error_detail`` and lets the
  exception propagate. A run that blew up is the most interesting row in the
  table; losing it is how a dashboard ends up showing a 100 % success rate.
- **Recording never fails the run.** Every write is wrapped: on a database
  error it logs and carries on.

Both follow from the recorder owning its own sessions, opened from a session
*factory* rather than borrowed from the caller — a rollback in the caller's
transaction must not take the telemetry with it. The run row is committed on
entry, so a process killed mid-run still leaves a ``running`` row behind, and
written again in full on exit (a merge, so it also lands if the entry write
failed). Steps are buffered in memory and written on exit with the final row:
``step()`` stays synchronous, and a run's dozen steps are not worth a round
trip each.
"""

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.pricing import UnpricedModel, cost_usd
from app.config import settings
from app.models.agent_run import (
    RUN_FAILED,
    RUN_REFUSED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    AgentRun,
    AgentStep,
)

logger = logging.getLogger(__name__)

# Per string value in a step's detail, and per list. A few KB: enough to debug
# a tool call, too little to smuggle a page of the PDF into the table.
DETAIL_MAX_CHARS = 2048
DETAIL_MAX_ITEMS = 50
ERROR_DETAIL_MAX_CHARS = 4000


def truncate_detail(value: Any, max_chars: int = DETAIL_MAX_CHARS) -> Any:
    """A JSON-safe copy of ``value`` with every string and list capped.

    Anything that is not JSON already is stored as its ``str()``, so a stray
    object in a detail dict costs a debugging hint, not the whole run row.
    """
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, dict):
        return {str(k): truncate_detail(v, max_chars) for k, v in value.items()}
    if isinstance(value, list | tuple):
        items = [truncate_detail(v, max_chars) for v in value[:DETAIL_MAX_ITEMS]]
        if len(value) > DETAIL_MAX_ITEMS:
            items.append(f"…[{len(value) - DETAIL_MAX_ITEMS} more items]")
        return items
    text = value if isinstance(value, str) else str(value)
    if len(text) > max_chars:
        return text[:max_chars] + f"…[truncated {len(text) - max_chars} chars]"
    return text


def classify_error(exc: BaseException) -> str:
    """Map an exception onto agent_runs.error_kind.

    Duck-typed on ``status_code`` rather than importing the Anthropic SDK's
    error classes, so the backend does not depend on the SDK to record a run.
    An exception may also carry its own ``error_kind`` attribute — that wins.
    """
    if kind := getattr(exc, "error_kind", None):
        return kind
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "rate_limit"
    if status == 529:
        return "overloaded"
    if isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__:
        return "timeout"
    if type(exc).__name__ == "ValidationError":
        return "schema_invalid"
    return "internal"


class AgentRecorder:
    def __init__(
        self,
        *,
        kind: str,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        model: str | None = None,
        is_eval: bool = False,
        job_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        profile: str | None = None,
        prompt_version: str | None = None,
        effort: str | None = None,
    ) -> None:
        if session_factory is None:
            # Imported here so importing this module does not build an engine.
            from app.db import async_session_maker

            session_factory = async_session_maker
        self._session_factory = session_factory
        self.run_id = uuid.uuid4()
        self.kind = kind
        self.model = model or settings.agent_model
        self.is_eval = is_eval
        self.job_id = job_id
        self.document_id = document_id
        self.profile = profile
        self.prompt_version = prompt_version
        self.effort = effort
        # Set by message()/usage(), or directly by the runtime. ``status`` set
        # explicitly (over_budget, say) is kept on a clean exit.
        self.status: str | None = None
        self.stop_reason: str | None = None
        self.refusal_category: str | None = None
        self.turns = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        self._steps: list[AgentStep] = []
        self._started_at: datetime | None = None
        self._t0 = 0.0

    # --- what the runtime calls --------------------------------------------

    def usage(self, usage: Any) -> None:
        """Add one response's ``usage`` to the run and count it as a turn.

        A counter the response does not carry (or carries as None — cache
        counters on a request with no caching) counts as zero.
        """
        self.turns += 1
        self.input_tokens += getattr(usage, "input_tokens", None) or 0
        self.output_tokens += getattr(usage, "output_tokens", None) or 0
        self.cache_creation_input_tokens += (
            getattr(usage, "cache_creation_input_tokens", None) or 0
        )
        self.cache_read_input_tokens += (
            getattr(usage, "cache_read_input_tokens", None) or 0
        )

    def message(self, response: Any) -> None:
        """Record one Messages API response: its usage, its stop reason, and
        — on ``refusal`` — the ``stop_details.category``."""
        self.usage(response.usage)
        self.stop_reason = getattr(response, "stop_reason", None)
        if self.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            self.refusal_category = getattr(details, "category", None)

    def step(
        self,
        *,
        kind: str,
        tool_name: str | None = None,
        ok: bool | None = None,
        duration_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Append a step. ``seq`` is assigned here, from 1, so it is gapless."""
        self._steps.append(
            AgentStep(
                id=uuid.uuid4(),
                run_id=self.run_id,
                seq=len(self._steps) + 1,
                kind=kind,
                tool_name=tool_name,
                ok=ok,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                detail=truncate_detail(detail) if detail is not None else None,
                created_at=datetime.now(UTC),
            )
        )

    # --- the context manager -----------------------------------------------

    async def __aenter__(self) -> "AgentRecorder":
        self._started_at = datetime.now(UTC)
        self._t0 = time.monotonic()
        try:
            async with self._session_factory() as session:
                session.add(self._row(RUN_RUNNING))
                await session.commit()
        except Exception:
            # Not fatal: __aexit__ merges the full row and gets a second try.
            logger.exception("agent run %s: could not write the run row", self.run_id)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            status = RUN_FAILED
            error_kind = classify_error(exc)
            error_detail = truncate_detail(
                f"{type(exc).__name__}: {exc}", ERROR_DETAIL_MAX_CHARS
            )
        else:
            status = self.status or (
                RUN_REFUSED if self.stop_reason == "refusal" else RUN_SUCCEEDED
            )
            error_kind = error_detail = None

        row = self._row(status)
        row.ended_at = datetime.now(UTC)
        row.latency_ms = int((time.monotonic() - self._t0) * 1000)
        row.error_kind = error_kind
        row.error_detail = error_detail
        try:
            row.cost_usd = cost_usd(
                self.model,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                cache_creation_input_tokens=self.cache_creation_input_tokens,
                cache_read_input_tokens=self.cache_read_input_tokens,
            )
        except UnpricedModel:
            # NULL, not 0: unknown must not read as free.
            logger.warning("agent run %s: no price for %s", self.run_id, self.model)

        try:
            async with self._session_factory() as session:
                await session.merge(row)
                # The run row first: the steps' foreign key needs it.
                await session.flush()
                session.add_all(self._steps)
                await session.commit()
        except Exception:
            logger.exception(
                "agent run %s: could not record the run (status %s)",
                self.run_id,
                status,
            )
        # Never swallow the run's own exception.
        return False

    def _row(self, status: str) -> AgentRun:
        return AgentRun(
            id=self.run_id,
            kind=self.kind,
            is_eval=self.is_eval,
            job_id=self.job_id,
            document_id=self.document_id,
            model=self.model,
            profile=self.profile,
            prompt_version=self.prompt_version,
            effort=self.effort,
            status=status,
            stop_reason=self.stop_reason,
            refusal_category=self.refusal_category,
            turns=self.turns,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens,
            started_at=self._started_at,
        )
