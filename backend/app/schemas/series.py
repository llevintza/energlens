import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Metric = Literal["consumption", "cost", "unit_price"]
Granularity = Literal["month", "bill"]


class SeriesPoint(BaseModel):
    period: str  # "YYYY-MM" for month granularity, "YYYY-MM-DD" (period_end) for bill
    value: float


class SeriesResponse(BaseModel):
    place_id: uuid.UUID
    metric: Metric
    granularity: Granularity
    unit: str  # e.g. "kWh", "EUR", "EUR/kWh"
    currency_code: str | None
    points: list[SeriesPoint]


class CompareSeries(BaseModel):
    place_id: uuid.UUID
    place_name: str
    currency_code: str
    points: list[SeriesPoint]


class CompareResponse(BaseModel):
    metric: Metric
    granularity: Granularity
    series: list[CompareSeries]


class PlaceSummary(BaseModel):
    place_id: uuid.UUID
    currency_code: str
    bill_count: int
    total_consumption: Decimal | None
    total_cost: Decimal | None
    avg_effective_unit_price: Decimal | None  # total cost / total kWh
    first_period_start: date | None
    last_period_end: date | None
    last_bill_total: Decimal | None
    last_bill_consumption: Decimal | None
