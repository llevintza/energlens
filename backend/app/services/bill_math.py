"""Pure arithmetic over a bill's charge lines.

The server-side half of ``frontend/src/components/places/ArithmeticCheck.tsx``,
which already checks a bill's sum live in the Add-bill form. #24 asks for that
computation to be shared rather than rewritten, so the tolerance is the same one
and lives here once; the extraction agent calls these as tools (#57).

Reconciliation is **advisory**. A bill that does not add up is still a bill
someone received: it gets flagged, never rejected, and nothing here raises on a
mismatch.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Protocol

# Strictly less than: a cent either way is rounding on the provider's own unit
# price, not a mistake. Matches ArithmeticCheck.tsx's `< 0.015`.
RECONCILE_TOLERANCE = Decimal("0.015")


class LineItemLike(Protocol):
    charge_kind: str
    net_amount: Decimal
    is_subtotal: bool


class BillLike(Protocol):
    net_amount: Decimal | None


@dataclass(frozen=True)
class Reconciliation:
    computed_net: Decimal
    # None when the bill states no net: there is nothing to check against, which
    # is not the same as failing the check.
    stated_net: Decimal | None
    # stated − computed, the same sign ArithmeticCheck.tsx shows.
    delta: Decimal | None
    within_tolerance: bool | None


def _charges(items: Iterable[LineItemLike]) -> list[LineItemLike]:
    # Subtotals restate the lines above them; counting them double-counts.
    return [item for item in items if not item.is_subtotal]


def line_total(items: Iterable[LineItemLike]) -> Decimal:
    """Sum of net_amount over the charge lines, subtotals excluded."""
    return sum((item.net_amount for item in _charges(items)), Decimal(0))


def reconcile(bill: BillLike, items: Iterable[LineItemLike]) -> Reconciliation:
    computed = line_total(items)
    stated = bill.net_amount
    if stated is None:
        return Reconciliation(computed, None, None, None)
    delta = stated - computed
    return Reconciliation(computed, stated, delta, abs(delta) < RECONCILE_TOLERANCE)


def by_charge_kind(items: Iterable[LineItemLike]) -> dict[str, Decimal]:
    """Net amount per canonical charge kind — what cross-region analytics group by."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for item in _charges(items):
        totals[item.charge_kind] += item.net_amount
    return dict(totals)
