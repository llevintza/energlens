"""What the agent may know besides the PDF: the place and the bill before (#57).

Loaded once, before the loop starts, and handed to the tools as plain data. The
tools never touch the database: a turn that waits on a query is a turn that
holds a connection while a model thinks, and plain data is what lets the tests
replay a run without one.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Bill, Place


@dataclass(frozen=True)
class PlaceContext:
    country_code: str | None
    currency_code: str | None
    # From the latest bill on file: what the provider was last time, so a
    # change (PPC Energie Muntenia → PPC Energie at 2025-03) is noticeable.
    known_provider_name: str | None = None
    known_provider_tax_id: str | None = None
    # Not modelled yet (no column on places). Kept in the tool's answer as
    # null so the model is told "unknown", not left to guess.
    contracted_power_kw: Decimal | None = None
    tariff_name: str | None = None


@dataclass(frozen=True)
class PriorBill:
    provider_invoice_series: str | None
    provider_invoice_number: str | None
    document_type: str
    period_start: date
    period_end: date
    consumption: Decimal | None
    total_amount: Decimal
    # total_amount / consumption, or the printed unit price where there is no
    # consumption to divide by.
    effective_price: Decimal | None
    # Per register, from bill_meter_readings: index continuity is how an
    # estimate is told from a real read.
    meter_readings: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionContext:
    place: PlaceContext
    prior_bill: PriorBill | None = None

    def place_dict(self) -> dict:
        return _jsonable(asdict(self.place))

    def prior_bill_dict(self) -> dict | None:
        return _jsonable(asdict(self.prior_bill)) if self.prior_bill else None


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal | date):
        return str(value)
    return value


def _effective_price(bill: Bill) -> Decimal | None:
    if bill.consumption:
        return (bill.total_amount / bill.consumption).quantize(Decimal("0.000001"))
    return bill.unit_price


async def load_context(
    session: AsyncSession,
    place_id: uuid.UUID,
    *,
    exclude_document_id: uuid.UUID | None = None,
) -> ExtractionContext:
    """The place and its most recent bill, latest ``period_end`` first.

    ``exclude_document_id`` leaves out a bill already made from the document
    being extracted, so a re-run does not compare a bill with itself.
    """
    place = await session.get(Place, place_id)
    if place is None:
        raise LookupError(f"place {place_id} not found")

    query = (
        select(Bill)
        .where(Bill.place_id == place_id)
        .options(selectinload(Bill.meter_readings))
        .order_by(Bill.period_end.desc(), Bill.created_at.desc())
        .limit(1)
    )
    if exclude_document_id is not None:
        query = query.where(
            (Bill.document_id.is_(None)) | (Bill.document_id != exclude_document_id)
        )
    latest = (await session.scalars(query)).first()

    place_ctx = PlaceContext(
        country_code=place.country_code,
        currency_code=place.currency_code,
        known_provider_name=latest.provider_name if latest else None,
        known_provider_tax_id=latest.provider_tax_id if latest else None,
    )
    if latest is None:
        return ExtractionContext(place=place_ctx)

    prior = PriorBill(
        provider_invoice_series=latest.provider_invoice_series,
        provider_invoice_number=latest.provider_invoice_number,
        document_type=latest.document_type,
        period_start=latest.period_start,
        period_end=latest.period_end,
        consumption=latest.consumption,
        total_amount=latest.total_amount,
        effective_price=_effective_price(latest),
        meter_readings=[
            {
                "register": r.register,
                "meter_serial": r.meter_serial,
                "index_current": r.index_current,
                "read_method": r.read_method,
                "read_on": r.read_on,
            }
            for r in latest.meter_readings
        ],
    )
    return ExtractionContext(place=place_ctx, prior_bill=prior)
