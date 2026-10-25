"""app/agent/pricing.py: the only place in the repo that knows what a run costs."""

from decimal import Decimal

import pytest

from app.agent.pricing import PRICES, UnpricedModel, cost_usd, rate_for
from app.config import Settings, settings


def test_the_configured_agent_model_has_a_price():
    """A model bump that silently reports $0.00 is worse than a red build."""
    rate_for(settings.agent_model)


def test_the_default_agent_model_has_a_price():
    # The check above reads whatever .env says; this one pins the shipped
    # default, which is what production runs when nothing is set.
    rate_for(Settings.model_fields["agent_model"].default)


def test_an_unpriced_model_fails_rather_than_costing_nothing(monkeypatch):
    monkeypatch.setattr(settings, "agent_model", "claude-not-a-model")
    with pytest.raises(UnpricedModel, match="claude-not-a-model"):
        rate_for(settings.agent_model)
    with pytest.raises(UnpricedModel):
        cost_usd(
            "claude-not-a-model",
            input_tokens=1,
            output_tokens=1,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )


def test_cost_matches_a_hand_calculation_to_six_decimals():
    # claude-opus-5-5: $4 in, $20 out, $5 cache write (1.25x), $0.20 cache read.
    #   1 234 input        x  4.00 / 1e6 = 0.004936
    #   5 678 output       x 20.00 / 1e6 = 0.113560
    #   2 000 cache write  x  5.00 / 1e6 = 0.010000
    #  10 000 cache read   x  0.20 / 1e6 = 0.002000
    #                                      --------
    #                                      0.130496
    assert cost_usd(
        "claude-opus-5-5",
        input_tokens=1234,
        output_tokens=5678,
        cache_creation_input_tokens=2000,
        cache_read_input_tokens=10000,
    ) == Decimal("0.130496")


def test_cost_rounds_to_the_column_scale():
    # One input token on opus-5-5 is $0.000004; on sonnet-5-5 a single cache
    # read is $0.0000002, which rounds to zero at six places.
    assert cost_usd(
        "claude-sonnet-5-5",
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=1,
    ) == Decimal("0.000000")


@pytest.mark.parametrize("model", sorted(PRICES))
def test_cache_writes_bill_at_one_and_a_quarter_times_input(model):
    rate = PRICES[model]
    assert rate.cache_write == rate.input * Decimal("1.25")
    assert rate.cache_read < rate.input
