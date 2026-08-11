"""Pure aggregation logic for chart series.

Bills cover arbitrary periods (often mid-month to mid-month). Monthly series are
derived by prorating each bill across the calendar months it overlaps, weighted
by day count. The unit_price metric is the *effective* price — prorated cost
divided by prorated kWh — which reflects what was actually paid per kWh
(including fixed charges and taxes), not the tariff printed on the bill.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Protocol

from app.schemas.series import Metric, SeriesPoint


class BillLike(Protocol):
    period_start: date
    period_end: date
    consumption: Decimal | None
    total_amount: Decimal


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _iter_months(start: date, end: date) -> Iterable[tuple[date, date]]:
    """Yield (first_day, last_day) for every calendar month from start to end."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        last_day = monthrange(year, month)[1]
        yield date(year, month, 1), date(year, month, last_day)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return (end - start).days + 1 if end >= start else 0


def _round(value: Decimal, places: int) -> float:
    exp = Decimal(1).scaleb(-places)
    return float(value.quantize(exp, rounding=ROUND_HALF_UP))


def monthly_series(
    bills: list[BillLike],
    metric: Metric,
    month_from: str | None = None,
    month_to: str | None = None,
) -> list[SeriesPoint]:
    cost_acc: dict[str, Decimal] = defaultdict(Decimal)
    kwh_acc: dict[str, Decimal] = defaultdict(Decimal)

    for bill in bills:
        bill_days = (bill.period_end - bill.period_start).days + 1
        for month_start, month_end in _iter_months(bill.period_start, bill.period_end):
            overlap = _overlap_days(
                bill.period_start, bill.period_end, month_start, month_end
            )
            if overlap == 0:
                continue
            share = Decimal(overlap) / Decimal(bill_days)
            key = _month_key(month_start)
            cost_acc[key] += bill.total_amount * share
            if bill.consumption is not None:
                kwh_acc[key] += bill.consumption * share

    if metric == "consumption":
        raw = {k: _round(v, 2) for k, v in kwh_acc.items()}
    elif metric == "cost":
        raw = {k: _round(v, 2) for k, v in cost_acc.items()}
    else:  # unit_price: weighted average, only months with real consumption
        raw = {
            k: _round(cost_acc[k] / kwh, 4)
            for k, kwh in kwh_acc.items()
            if kwh > 0
        }

    keys = sorted(raw)
    if month_from:
        keys = [k for k in keys if k >= month_from]
    if month_to:
        keys = [k for k in keys if k <= month_to]
    # Months with no overlapping bill are simply absent: charts show honest gaps.
    return [SeriesPoint(period=k, value=raw[k]) for k in keys]


def bill_series(bills: list[BillLike], metric: Metric) -> list[SeriesPoint]:
    """Exact per-bill points (no proration), plotted at period_end."""
    points: list[SeriesPoint] = []
    for bill in sorted(bills, key=lambda b: b.period_end):
        if metric == "consumption":
            if bill.consumption is None:
                continue
            value = _round(bill.consumption, 2)
        elif metric == "cost":
            value = _round(bill.total_amount, 2)
        else:  # unit_price
            if not bill.consumption:
                continue
            value = _round(bill.total_amount / bill.consumption, 4)
        points.append(SeriesPoint(period=bill.period_end.isoformat(), value=value))
    return points
