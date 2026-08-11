import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.db import get_async_session
from app.models import Bill, Place, User
from app.routers.deps import get_owned_place
from app.schemas.series import (
    CompareResponse,
    CompareSeries,
    Granularity,
    Metric,
    PlaceSummary,
    SeriesPoint,
    SeriesResponse,
)
from app.services.series import bill_series, monthly_series

router = APIRouter(tags=["series"])

MONTH_PATTERN = r"^\d{4}-\d{2}$"


def _parse_month(value: str) -> tuple[int, int]:
    year, month = int(value[:4]), int(value[5:7])
    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail=f"Invalid month: {value}")
    return year, month


def _month_bounds(month_from: str | None, month_to: str | None) -> tuple[date | None, date | None]:
    start = end = None
    if month_from:
        year, month = _parse_month(month_from)
        start = date(year, month, 1)
    if month_to:
        year, month = _parse_month(month_to)
        end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, end


async def _fetch_bills(
    session: AsyncSession,
    place_id: uuid.UUID,
    utility_type: str,
    month_from: str | None,
    month_to: str | None,
) -> list[Bill]:
    query = select(Bill).where(
        Bill.place_id == place_id, Bill.utility_type == utility_type
    )
    range_start, range_end = _month_bounds(month_from, month_to)
    if range_start:
        query = query.where(Bill.period_end >= range_start)
    if range_end:
        query = query.where(Bill.period_start < range_end)
    result = await session.execute(query.order_by(Bill.period_start))
    return list(result.scalars().all())


def _series_unit(metric: Metric, currency_code: str, consumption_unit: str) -> str:
    if metric == "consumption":
        return consumption_unit
    if metric == "cost":
        return currency_code
    return f"{currency_code}/{consumption_unit}"


def _build_points(
    bills: list[Bill],
    metric: Metric,
    granularity: Granularity,
    month_from: str | None,
    month_to: str | None,
) -> list[SeriesPoint]:
    if granularity == "bill":
        return bill_series(bills, metric)
    return monthly_series(bills, metric, month_from, month_to)


@router.get("/places/{place_id}/series", response_model=SeriesResponse)
async def get_place_series(
    metric: Metric = "cost",
    granularity: Granularity = "month",
    month_from: str | None = Query(default=None, alias="from", pattern=MONTH_PATTERN),
    month_to: str | None = Query(default=None, alias="to", pattern=MONTH_PATTERN),
    utility_type: str = "electricity",
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> SeriesResponse:
    bills = await _fetch_bills(session, place.id, utility_type, month_from, month_to)
    consumption_unit = bills[0].unit if bills else "kWh"
    return SeriesResponse(
        place_id=place.id,
        metric=metric,
        granularity=granularity,
        unit=_series_unit(metric, place.currency_code, consumption_unit),
        currency_code=place.currency_code if metric != "consumption" else None,
        points=_build_points(bills, metric, granularity, month_from, month_to),
    )


@router.get("/series/compare", response_model=CompareResponse)
async def compare_series(
    metric: Metric = "consumption",
    granularity: Granularity = "month",
    month_from: str | None = Query(default=None, alias="from", pattern=MONTH_PATTERN),
    month_to: str | None = Query(default=None, alias="to", pattern=MONTH_PATTERN),
    utility_type: str = "electricity",
    place_ids: str | None = Query(
        default=None, description="Comma-separated place ids; defaults to all"
    ),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> CompareResponse:
    result = await session.execute(
        select(Place).where(Place.user_id == user.id).order_by(Place.created_at)
    )
    places = list(result.scalars().all())
    if place_ids:
        try:
            wanted = {uuid.UUID(p.strip()) for p in place_ids.split(",") if p.strip()}
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid place id")
        places = [p for p in places if p.id in wanted]

    series: list[CompareSeries] = []
    for place in places:
        bills = await _fetch_bills(session, place.id, utility_type, month_from, month_to)
        series.append(
            CompareSeries(
                place_id=place.id,
                place_name=place.name,
                currency_code=place.currency_code,
                points=_build_points(bills, metric, granularity, month_from, month_to),
            )
        )
    return CompareResponse(metric=metric, granularity=granularity, series=series)


@router.get("/places/{place_id}/stats/summary", response_model=PlaceSummary)
async def place_summary(
    utility_type: str = "electricity",
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> PlaceSummary:
    bills = await _fetch_bills(session, place.id, utility_type, None, None)
    consumptions = [b.consumption for b in bills if b.consumption is not None]
    total_consumption = sum(consumptions, Decimal(0)) if consumptions else None
    total_cost = sum((b.total_amount for b in bills), Decimal(0)) if bills else None
    avg_price = None
    if total_cost is not None and total_consumption:
        avg_price = (total_cost / total_consumption).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    last_bill = max(bills, key=lambda b: b.period_end) if bills else None
    return PlaceSummary(
        place_id=place.id,
        currency_code=place.currency_code,
        bill_count=len(bills),
        total_consumption=total_consumption,
        total_cost=total_cost,
        avg_effective_unit_price=avg_price,
        first_period_start=min((b.period_start for b in bills), default=None),
        last_period_end=last_bill.period_end if last_bill else None,
        last_bill_total=last_bill.total_amount if last_bill else None,
        last_bill_consumption=last_bill.consumption if last_bill else None,
    )
