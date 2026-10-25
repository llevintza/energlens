"""The submit_extraction envelope (#57): every value carries a confidence and a
span, and a payload that breaks that is rejected — with reasons the model can
act on."""

import asyncio
import json

import pydantic
import pytest
from anthropic.lib.tools import ToolError

from app.agent.context import ExtractionContext, PlaceContext
from app.agent.envelope import ExtractionEnvelope, Field, LineItem, MeterReading
from app.agent.tools import ExtractionTools
from tests.agent_transport import load_case


def submitted(case: str) -> dict:
    """The accepted submit_extraction payload of a fixture case."""
    for response in reversed(load_case(case)["responses"]):
        for block in response["content"]:
            if block["type"] == "tool_use" and block["name"] == "submit_extraction":
                return block["input"]
    raise AssertionError(f"{case} has no submit_extraction")


def test_every_fixture_submission_validates():
    for case in ("clean_2025_06", "credit_note_2024_12_1", "long_period_2024_02", "vat21_2026_07"):
        ExtractionEnvelope.model_validate(submitted(case))


def test_a_value_without_a_span_is_rejected():
    with pytest.raises(pydantic.ValidationError, match="source_page and source_text"):
        Field[str].model_validate({"value": "SYN", "confidence": 0.9, "source_page": 1})


def test_a_missing_value_needs_no_span():
    field = Field[str].model_validate({"value": None, "confidence": 0.4})
    assert field.source_text is None


def test_confidence_is_required_and_bounded():
    with pytest.raises(pydantic.ValidationError, match="confidence"):
        Field[str].model_validate({"value": None})
    with pytest.raises(pydantic.ValidationError):
        Field[str].model_validate({"value": None, "confidence": 1.5})


def test_a_line_item_needs_its_printed_line():
    line = submitted("clean_2025_06")["line_items"][0]
    with pytest.raises(pydantic.ValidationError, match="source_page and source_text"):
        LineItem.model_validate({**line, "source_text": None})


def test_a_meter_reading_needs_its_printed_line():
    reading = submitted("clean_2025_06")["meter_readings"][0]
    assert MeterReading.model_validate(reading).register_ is None
    with pytest.raises(pydantic.ValidationError, match="source_page and source_text"):
        MeterReading.model_validate({**reading, "source_page": None})


def test_an_unknown_charge_kind_is_rejected():
    line = submitted("clean_2025_06")["line_items"][0]
    with pytest.raises(pydantic.ValidationError, match="charge_kind"):
        LineItem.model_validate({**line, "charge_kind": "green_tax"})


def test_vat_rate_as_a_percentage_is_rejected():
    payload = submitted("vat21_2026_07")
    payload["vat_rate"]["value"] = "21"
    with pytest.raises(pydantic.ValidationError, match="fraction"):
        ExtractionEnvelope.model_validate(payload)


def test_duplicate_line_numbers_are_rejected():
    payload = submitted("clean_2025_06")
    payload["line_items"][1]["line_no"] = 1
    with pytest.raises(pydantic.ValidationError, match="line_no"):
        ExtractionEnvelope.model_validate(payload)


def test_an_unexpected_key_is_rejected():
    payload = submitted("vat21_2026_07")
    payload["vendor"] = {"value": None, "confidence": 0.1}
    with pytest.raises(pydantic.ValidationError, match="vendor"):
        ExtractionEnvelope.model_validate(payload)


def test_submit_extraction_returns_the_reasons_and_keeps_nothing():
    tools = ExtractionTools(pages=["x"], context=ExtractionContext(place=PlaceContext("RO", "RON")))
    submit = next(t for t in tools.all() if t.name == "submit_extraction")
    payload = submitted("vat21_2026_07")
    payload["total_amount"]["source_text"] = None

    with pytest.raises(ToolError) as caught:
        asyncio.run(submit.call(payload))
    # One line per problem, naming the path, without pydantic's docs URLs.
    assert "- total_amount:" in str(caught.value.content)
    assert "errors.pydantic.dev" not in str(caught.value.content)
    assert tools.submitted is None


def test_the_tool_schema_is_the_envelope():
    tools = ExtractionTools(pages=["x"], context=ExtractionContext(place=PlaceContext("RO", "RON")))
    submit = next(t for t in tools.all() if t.name == "submit_extraction")
    schema = submit.to_dict()["input_schema"]
    assert set(schema["required"]) == set(ExtractionEnvelope.model_fields)
    assert "line_items" in json.dumps(schema)
