"""AgentRecorder and the agent_runs / agent_steps / agent_scores tables (#56).

Driven against the real test database: the properties that matter — a run row
that survives the caller's rollback, cascades, the (run_id, seq) uniqueness —
live in Postgres, and a fake session would prove none of them.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.recorder import DETAIL_MAX_CHARS, AgentRecorder, classify_error
from app.models import AgentRun, AgentScore, AgentStep


@pytest.fixture
def maker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


def response(input_tokens, output_tokens, cache_write=0, cache_read=0, stop="end_turn"):
    """The shape of a Messages API response, as far as the recorder reads it."""
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_write,
            cache_read_input_tokens=cache_read,
        ),
        stop_reason=stop,
        stop_details=None,
    )


async def runs(maker) -> list[AgentRun]:
    async with maker() as session:
        return list((await session.scalars(select(AgentRun))).all())


async def steps(maker, run_id) -> list[AgentStep]:
    async with maker() as session:
        return list(
            (
                await session.scalars(
                    select(AgentStep)
                    .where(AgentStep.run_id == run_id)
                    .order_by(AgentStep.seq)
                )
            ).all()
        )


async def test_a_successful_run_writes_one_row_with_usage_and_cost(maker):
    async with AgentRecorder(
        kind="extract", session_factory=maker, model="claude-opus-5-5", effort="high"
    ) as rec:
        rec.message(response(1000, 200, cache_write=3000, stop="tool_use"))
        rec.step(kind="tool_use", tool_name="get_page_text", duration_ms=12, ok=True)
        rec.message(response(234, 5478, cache_read=10000))

    [run] = await runs(maker)
    assert run.id == rec.run_id
    assert run.status == "succeeded"
    assert run.stop_reason == "end_turn"
    assert run.turns == 2
    assert (
        run.input_tokens,
        run.output_tokens,
        run.cache_creation_input_tokens,
        run.cache_read_input_tokens,
    ) == (1234, 5678, 3000, 10000)
    # 0.004936 + 0.113560 + 3000 x 5.00/1e6 (0.015) + 0.002 — see test_agent_pricing.
    assert run.cost_usd == Decimal("0.135496")
    assert run.cost_usd > 0
    assert run.ended_at is not None and run.ended_at >= run.started_at
    assert run.latency_ms is not None and run.latency_ms >= 0
    assert run.error_kind is None and run.is_eval is False


async def test_the_run_row_exists_while_the_run_is_in_flight(maker):
    """Committed on entry, so a process killed mid-run still leaves a trace."""
    async with AgentRecorder(kind="extract", session_factory=maker) as rec:
        [run] = await runs(maker)
        assert run.id == rec.run_id
        assert run.status == "running"


async def test_a_run_that_raises_still_writes_a_failed_row(maker):
    class Overloaded(Exception):
        status_code = 529

    with pytest.raises(Overloaded):
        async with AgentRecorder(kind="extract", session_factory=maker) as rec:
            rec.message(response(500, 20, stop="tool_use"))
            rec.step(kind="tool_use", tool_name="get_page_text", ok=True)
            raise Overloaded("API overloaded")

    [run] = await runs(maker)
    assert run.status == "failed"
    assert run.error_kind == "overloaded"
    assert "API overloaded" in run.error_detail
    # What it spent before it died is still recorded, and still priced.
    assert run.input_tokens == 500 and run.cost_usd > 0
    assert [s.seq for s in await steps(maker, rec.run_id)] == [1]


async def test_the_run_row_survives_the_callers_rollback(maker):
    """The recorder has its own session, so the caller's rollback is not its."""
    async with maker() as caller:
        await caller.execute(select(1))  # the caller's transaction is open
        async with AgentRecorder(kind="extract", session_factory=maker):
            pass
        await caller.rollback()

    assert [r.status for r in await runs(maker)] == ["succeeded"]


class _BrokenSession:
    async def __aenter__(self):
        raise ConnectionError("database is down")

    async def __aexit__(self, *exc):
        return False


def _broken_factory():
    return _BrokenSession()


async def test_a_recorder_that_cannot_write_does_not_fail_the_run(caplog):
    async with AgentRecorder(kind="extract", session_factory=_broken_factory) as rec:
        rec.message(response(10, 10))
        rec.step(kind="assistant")
        extraction = {"total_amount": "60.69"}

    assert extraction == {"total_amount": "60.69"}
    assert "could not record the run" in caplog.text


async def test_a_broken_recorder_does_not_mask_the_runs_own_exception():
    with pytest.raises(ValueError, match="the real failure"):
        async with AgentRecorder(kind="extract", session_factory=_broken_factory):
            raise ValueError("the real failure")


async def test_the_exit_write_lands_even_if_the_entry_write_failed(maker):
    calls = 0

    def flaky():
        nonlocal calls
        calls += 1
        return _BrokenSession() if calls == 1 else maker()

    async with AgentRecorder(kind="extract", session_factory=flaky) as rec:
        rec.message(response(10, 10))

    [run] = await runs(maker)
    assert run.id == rec.run_id and run.status == "succeeded"


async def test_steps_are_ordered_and_gapless_and_detail_is_truncated(maker):
    huge = "x" * (DETAIL_MAX_CHARS * 10)
    async with AgentRecorder(kind="extract", session_factory=maker) as rec:
        rec.step(kind="assistant", input_tokens=100, output_tokens=50)
        rec.step(
            kind="tool_use",
            tool_name="get_page_text",
            detail={"input": {"page": 1}, "nested": [{"text": huge}], "obj": object()},
        )
        rec.step(
            kind="tool_result",
            tool_name="get_page_text",
            ok=True,
            detail={"text": huge},
        )
        rec.step(kind="assistant")

    saved = await steps(maker, rec.run_id)
    assert [s.seq for s in saved] == [1, 2, 3, 4]
    assert [s.kind for s in saved] == [
        "assistant",
        "tool_use",
        "tool_result",
        "assistant",
    ]

    text = saved[2].detail["text"]
    assert len(text) < DETAIL_MAX_CHARS + 50
    assert text.startswith("x" * DETAIL_MAX_CHARS) and "truncated" in text
    assert len(saved[1].detail["nested"][0]["text"]) < DETAIL_MAX_CHARS + 50
    assert saved[1].detail["input"] == {"page": 1}
    assert isinstance(saved[1].detail["obj"], str)


async def test_a_refusal_is_recorded_with_its_category(maker):
    refused = response(100, 5, stop="refusal")
    refused.stop_details = SimpleNamespace(type="refusal", category="cyber")
    async with AgentRecorder(kind="extract", session_factory=maker) as rec:
        rec.message(refused)

    [run] = await runs(maker)
    assert (run.status, run.stop_reason, run.refusal_category) == (
        "refused",
        "refusal",
        "cyber",
    )


async def test_an_explicit_status_is_kept(maker):
    async with AgentRecorder(kind="extract", session_factory=maker) as rec:
        rec.message(response(10, 10, stop="tool_use"))
        rec.status = "over_budget"

    assert [r.status for r in await runs(maker)] == ["over_budget"]


async def test_an_unpriced_model_records_null_cost_not_zero(maker):
    async with AgentRecorder(
        kind="extract", session_factory=maker, model="claude-not-a-model"
    ):
        pass

    [run] = await runs(maker)
    assert run.cost_usd is None and run.status == "succeeded"


async def test_deleting_a_run_deletes_its_steps_and_scores(maker):
    async with AgentRecorder(kind="extract", session_factory=maker) as rec:
        rec.step(kind="assistant")
        rec.step(kind="assistant")
    async with maker() as session:
        session.add(
            AgentScore(
                run_id=rec.run_id,
                field="total_amount",
                kind="human_accepted",
                value=Decimal("1"),
                confidence_at_propose=Decimal("0.9312"),
            )
        )
        await session.commit()

        await session.execute(delete(AgentRun).where(AgentRun.id == rec.run_id))
        await session.commit()

        for model in (AgentStep, AgentScore):
            count = await session.scalar(select(func.count()).select_from(model))
            assert count == 0, model.__name__


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (type("RateLimitError", (Exception,), {"status_code": 429})(), "rate_limit"),
        (type("OverloadedError", (Exception,), {"status_code": 529})(), "overloaded"),
        (TimeoutError(), "timeout"),
        (type("APITimeoutError", (Exception,), {})(), "timeout"),
        (type("ValidationError", (Exception,), {})(), "schema_invalid"),
        (RuntimeError("boom"), "internal"),
    ],
)
def test_classify_error(exc, kind):
    assert classify_error(exc) == kind
