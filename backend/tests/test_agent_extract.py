"""The extraction agent end to end, over a recorded transport (#57).

No test here reaches the network or needs a key: ``ANTHROPIC_API_KEY`` is
deleted by an autouse fixture, and every response comes from a hand-built
fixture in tests/fixtures/agent/ replayed through the real SDK client. The run
record goes to the real test database, because the statuses the issue asks
for — refused, failed, over_budget — are properties of the agent_runs row.
"""

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent import extract as extract_module
from app.agent.context import ExtractionContext, PlaceContext, PriorBill
from app.agent.extract import FALLBACK_BETA, extract_bill
from app.agent.regions import load_profiles
from app.config import settings
from app.models import AgentRun, AgentStep
from app.services import bill_math
from tests.agent_transport import RecordedTransport, load_case, make_text_pdf


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


@pytest.fixture
def maker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


RO_PLACE = PlaceContext(
    country_code="RO", currency_code="RON", known_provider_name="PPC Energie S.A."
)
PRIOR = PriorBill(
    provider_invoice_series="SYN",
    provider_invoice_number="2025050001",
    document_type="invoice",
    period_start=date(2025, 4, 1),
    period_end=date(2025, 4, 30),
    consumption=Decimal("240"),
    total_amount=Decimal("310.20"),
    effective_price=Decimal("1.2925"),
    meter_readings=[
        {"register": None, "index_current": Decimal("10250"), "read_method": "actual"}
    ],
)


async def run_case(name, maker, *, context=None, upload_status=200):
    case = load_case(name)
    transport = RecordedTransport(case, upload_status=upload_status)
    result = await extract_bill(
        make_text_pdf(case["pages"]),
        context=context or ExtractionContext(place=RO_PLACE, prior_bill=PRIOR),
        client=transport.client(),
        session_factory=maker,
    )
    return case, transport, result


async def stored(maker, run_id):
    async with maker() as session:
        run = await session.get(AgentRun, run_id)
        steps = (
            await session.scalars(
                select(AgentStep)
                .where(AgentStep.run_id == run_id)
                .order_by(AgentStep.seq)
            )
        ).all()
        return run, list(steps)


def test_the_suite_runs_without_an_api_key():
    assert "ANTHROPIC_API_KEY" not in os.environ


# --- the corpus cases ------------------------------------------------------


async def test_2025_06_extracts_twelve_lines_with_their_kinds_and_reconciles(maker):
    case, transport, result = await run_case("clean_2025_06", maker)

    assert result.status == "succeeded"
    env = result.envelope
    assert [item.charge_kind for item in env.line_items] == [
        "energy",
        "energy",
        "green_certificates",
        "cogeneration",
        "excise",
        "standing_charge",
        "other",
        "transmission",
        "transmission",
        "system_services",
        "distribution",
        "other",
    ]
    assert [i.line_no for i in env.line_items if i.is_subtotal] == [7, 12]
    # Energy at two prices is two lines with their own sub-periods, not an average.
    first, second = env.line_items[0], env.line_items[1]
    assert first.unit_price != second.unit_price
    assert first.period_end < second.period_start

    recon = bill_math.reconcile(
        SimpleNamespace(net_amount=env.net_amount.value), env.line_items
    )
    assert recon.within_tolerance is True
    assert env.total_amount.value == Decimal("338.42")
    assert env.total_due.value == Decimal("350.92")
    assert env.balance_brought_forward.value == Decimal("12.50")

    # Every source span quotes its page: the text the model copied is on it.
    for item in env.line_items:
        assert item.source_text in "\n".join(case["pages"][item.source_page - 1])
    assert transport.unused == 0


async def test_2024_12_1_is_a_credit_note_linked_to_the_invoice_it_reverses(maker):
    _, _, result = await run_case("credit_note_2024_12_1", maker)

    env = result.envelope
    assert result.status == "succeeded"
    assert env.document_type.value == "credit_note"
    assert env.consumption.value < 0
    assert all(item.net_amount < 0 for item in env.line_items)
    assert env.corrects_invoice_number.value == "2024110007"


async def test_2024_02_keeps_its_417_day_period_as_printed(maker):
    _, _, result = await run_case("long_period_2024_02", maker)

    env = result.envelope
    assert result.status == "succeeded"
    assert str(env.period_start.value) == "2023-01-01"
    assert str(env.period_end.value) == "2024-02-21"
    assert (env.period_end.value - env.period_start.value).days + 1 == 417
    assert env.read_method.value == "regularisation"


async def test_2026_07_reads_21_percent_vat_and_a_base_apart_from_the_net(maker):
    _, _, result = await run_case("vat21_2026_07", maker)

    env = result.envelope
    assert env.vat_rate.value == Decimal("0.21")
    assert env.net_amount.value != env.vat_base.value


# --- spans: a value without one is rejected --------------------------------


async def test_a_submission_without_a_span_is_rejected_and_the_retry_accepted(maker):
    _, transport, result = await run_case("long_period_2024_02", maker)

    run, steps = await stored(maker, result.run_id)
    submits = [s for s in steps if s.tool_name == "submit_extraction"]
    assert [s.ok for s in submits] == [False, True]
    assert "period_end" in submits[0].detail["error"]
    # The rejection went back to the model as an error result it could act on.
    sent = transport.message_requests[2]["messages"][-1]["content"][0]
    assert sent["is_error"] is True and "source_page" in sent["content"]
    assert run.status == "succeeded"


# --- the run record --------------------------------------------------------


async def test_a_clean_run_records_turns_tokens_and_one_step_per_tool_call(maker):
    _, _, result = await run_case("clean_2025_06", maker)

    run, steps = await stored(maker, result.run_id)
    assert run.status == "succeeded"
    assert run.model == settings.agent_model
    assert run.profile == "ro_ppc"
    assert run.prompt_version.startswith("extract-v1+")
    assert run.effort == settings.agent_effort
    assert run.turns == 4
    assert run.output_tokens == 210 + 95 + 640 + 4210
    assert run.cache_read_input_tokens == 6050 + 6400 + 7100
    assert run.cost_usd is not None

    tool_steps = [s for s in steps if s.kind == "tool_use"]
    assert [s.tool_name for s in tool_steps] == [
        "get_page_text",
        "get_place_context",
        "get_prior_bill",
        "get_page_text",
        "check_arithmetic",
        "submit_extraction",
    ]
    assert all(s.ok for s in tool_steps)
    assert all(s.duration_ms is not None for s in tool_steps)
    assert [s.kind for s in steps].count("assistant") == 4


async def test_a_refusal_is_recorded_as_refused_with_its_category(maker):
    _, transport, result = await run_case("refusal", maker)

    assert result.status == "refused" and result.envelope is None
    run, _ = await stored(maker, result.run_id)
    assert run.status == "refused"
    assert run.stop_reason == "refusal"
    assert run.refusal_category == "cyber"
    assert len(transport.message_requests) == 1


async def test_a_max_tokens_stop_is_recorded_as_failed(maker):
    _, transport, result = await run_case("max_tokens", maker)

    assert result.status == "failed" and result.envelope is None
    run, _ = await stored(maker, result.run_id)
    assert run.status == "failed"
    assert run.stop_reason == "max_tokens"
    assert "max_tokens" in run.error_detail
    # A truncated turn's tool calls are never run.
    assert len(transport.message_requests) == 1


async def test_a_tool_that_raises_costs_a_turn_not_the_run(maker):
    class BrokenContext(ExtractionContext):
        def place_dict(self):
            raise RuntimeError("synthetic failure in get_place_context")

    _, transport, result = await run_case(
        "tool_raises", maker, context=BrokenContext(place=RO_PLACE)
    )

    assert result.status == "succeeded"
    _, steps = await stored(maker, result.run_id)
    place_step = next(s for s in steps if s.tool_name == "get_place_context")
    assert place_step.ok is False
    assert "synthetic failure" in str(place_step.detail["error"])
    sent = transport.message_requests[1]["messages"][-1]["content"][0]
    assert sent["is_error"] is True


async def test_running_out_of_turns_is_recorded_as_over_budget(maker, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_iterations", 2)
    _, transport, result = await run_case("over_budget", maker)

    assert result.status == "over_budget" and result.envelope is None
    run, _ = await stored(maker, result.run_id)
    assert run.status == "over_budget"
    assert len(transport.message_requests) == 2


# --- the request -----------------------------------------------------------


async def test_the_request_uses_the_files_api_config_and_the_profile(maker):
    _, transport, _ = await run_case("vat21_2026_07", maker)

    first = transport.message_requests[0]
    assert first["model"] == settings.agent_model
    assert first["max_tokens"] == settings.agent_max_tokens
    assert first["output_config"] == {"effort": settings.agent_effort}
    # Adaptive thinking is this model's default; the agent sends no override.
    assert "thinking" not in first
    assert first["cache_control"] == {"type": "ephemeral"}
    assert first["fallbacks"] == "default"
    assert FALLBACK_BETA in transport.message_headers[0]["anthropic-beta"]
    assert {t["name"] for t in first["tools"]} == {
        "get_page_text",
        "get_place_context",
        "get_prior_bill",
        "check_arithmetic",
        "submit_extraction",
    }
    # Uploaded once, referenced by id, deleted at the end.
    assert transport.uploads == 1
    document = first["messages"][0]["content"][0]
    assert document["source"] == {"type": "file", "file_id": RecordedTransport.FILE_ID}
    assert transport.deleted == [RecordedTransport.FILE_ID]
    # Later turns continue the server-held thread: only the new tool results
    # go up, never the document again.
    later = transport.message_requests[1]
    assert later["thread"]["type"] == "continue"
    assert [b["type"] for b in later["messages"][0]["content"]] == ["tool_result"]
    ro_ppc = next(p for p in load_profiles() if p.id == "ro_ppc")
    assert ro_ppc.text in first["system"]


async def test_without_the_files_api_the_pdf_goes_inline(maker):
    _, transport, result = await run_case("vat21_2026_07", maker, upload_status=500)

    assert result.status == "succeeded"
    source = transport.message_requests[0]["messages"][0]["content"][0]["source"]
    assert source["type"] == "base64" and source["media_type"] == "application/pdf"
    assert transport.deleted == []


async def test_the_fallback_can_be_turned_off(maker, monkeypatch):
    monkeypatch.setattr(settings, "agent_refusal_fallback", False)
    _, transport, _ = await run_case("vat21_2026_07", maker)

    assert "fallbacks" not in transport.message_requests[0]
    assert FALLBACK_BETA not in transport.message_headers[0].get("anthropic-beta", "")


async def test_a_place_with_no_profile_runs_on_the_base_prompt(maker):
    context = ExtractionContext(
        place=PlaceContext(country_code="PT", currency_code="EUR")
    )
    _, transport, result = await run_case("vat21_2026_07", maker, context=context)

    assert result.profile is None
    run, _ = await stored(maker, result.run_id)
    assert run.profile is None
    assert transport.message_requests[0]["system"] == extract_module.system_prompt(None)
