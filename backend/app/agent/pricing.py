"""What a model call costs, in USD. The only place in the repo that knows.

Rates are USD per million tokens for the four ``usage`` counters the API
returns. Source: Anthropic's first-party API price list as carried by the
``claude-api`` skill (models table cached 2026-10-06; cache multipliers from
its prompt-caching guide), copied here on 2026-10-25. Confirm against
https://www.anthropic.com/pricing before trusting a bill to the cent.

- ``cache_write`` is the **5-minute** TTL rate, 1.25x input. The 1-hour TTL
  bills at 2x; nothing here asks for it. If the agent ever does, split
  ``usage.cache_creation`` by TTL rather than pricing it all at this rate.
- ``cache_read`` is *not* a fixed multiple across models: 0.1x input on most,
  less on the newest (Opus 5.5 $0.20, Fable 5.1 $0.25).
- Batch (50% off) and fast-mode pricing are not modelled; the agent uses
  neither.

Only models whose four rates are all published are listed — a guessed rate is
worse than a missing one, because tests/test_agent_pricing.py turns a missing
rate for ``settings.agent_model`` into a red build, and a guess into nothing.
"""

from dataclasses import dataclass
from decimal import Decimal

_MILLION = Decimal(1_000_000)
_SIX_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class Rate:
    """USD per million tokens."""

    input: Decimal
    output: Decimal
    cache_write: Decimal
    cache_read: Decimal


PRICES: dict[str, Rate] = {
    "claude-fable-5-1": Rate(
        Decimal("10.00"), Decimal("50.00"), Decimal("12.50"), Decimal("0.25")
    ),
    "claude-opus-5-5": Rate(
        Decimal("4.00"), Decimal("20.00"), Decimal("5.00"), Decimal("0.20")
    ),
    "claude-opus-5": Rate(
        Decimal("5.00"), Decimal("25.00"), Decimal("6.25"), Decimal("0.50")
    ),
    "claude-sonnet-5-5": Rate(
        Decimal("2.00"), Decimal("10.00"), Decimal("2.50"), Decimal("0.20")
    ),
}


class UnpricedModel(KeyError):
    """The model has no entry in PRICES."""


def rate_for(model: str) -> Rate:
    try:
        return PRICES[model]
    except KeyError:
        raise UnpricedModel(
            f"no price for model {model!r} in app/agent/pricing.py — add its "
            f"input, output, cache-write and cache-read rates"
        ) from None


def cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
) -> Decimal:
    """Cost of the given usage, rounded to six decimals (the column's scale).

    Raises UnpricedModel rather than returning zero.
    """
    rate = rate_for(model)
    total = (
        input_tokens * rate.input
        + output_tokens * rate.output
        + cache_creation_input_tokens * rate.cache_write
        + cache_read_input_tokens * rate.cache_read
    ) / _MILLION
    return total.quantize(_SIX_PLACES)
