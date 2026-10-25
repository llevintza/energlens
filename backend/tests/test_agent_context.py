"""load_context (#57): the place and its latest bill, as the tools see them."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.context import load_context
from app.models import Bill, BillDocument, BillMeterReading, Place


@pytest.fixture
def sessions(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


def bill(place_id, start, end, **kw) -> Bill:
    return Bill(
        id=uuid.uuid4(),
        place_id=uuid.UUID(place_id),
        period_start=start,
        period_end=end,
        total_amount=kw.pop("total_amount", Decimal("100.00")),
        currency_code="EUR",
        **kw,
    )


async def test_a_place_with_no_bills_has_no_prior(sessions, place):
    async with sessions() as session:
        ctx = await load_context(session, uuid.UUID(place["id"]))
    assert ctx.place.country_code == "PT" and ctx.place.currency_code == "EUR"
    assert ctx.prior_bill is None
    assert ctx.prior_bill_dict() is None


async def test_the_latest_bill_is_the_prior_with_its_index(sessions, place):
    older = bill(place["id"], date(2026, 1, 1), date(2026, 1, 31), provider_name="Old Co")
    latest = bill(
        place["id"], date(2026, 2, 1), date(2026, 2, 28),
        provider_name="New Co", provider_tax_id="PT000",
        provider_invoice_series="SYN", provider_invoice_number="0002",
        consumption=Decimal("200"), total_amount=Decimal("50.00"),
    )
    latest.meter_readings = [
        BillMeterReading(read_method="actual", index_current=Decimal("1234.000"), quantity=Decimal("200"))
    ]
    async with sessions() as session:
        session.add_all([older, latest])
        await session.commit()

    async with sessions() as session:
        ctx = await load_context(session, uuid.UUID(place["id"]))
    assert ctx.place.known_provider_name == "New Co"
    assert ctx.prior_bill.provider_invoice_number == "0002"
    assert ctx.prior_bill.effective_price == Decimal("0.250000")
    as_json = ctx.prior_bill_dict()
    assert as_json["meter_readings"][0]["index_current"] == "1234.000"
    assert as_json["period_end"] == "2026-02-28"


async def test_a_rerun_does_not_compare_a_bill_with_itself(sessions, place):
    place_id = uuid.UUID(place["id"])
    async with sessions() as session:
        owner = (await session.get(Place, place_id)).user_id
        doc = BillDocument(
            place_id=place_id,
            sha256="0" * 64,
            filename="bill.pdf",
            media_type="application/pdf",
            byte_size=10,
            storage_key=f"test/{uuid.uuid4()}",
            uploaded_by=owner,
        )
        session.add(doc)
        await session.flush()
        session.add_all([
            bill(place["id"], date(2026, 1, 1), date(2026, 1, 31), provider_invoice_number="0001"),
            bill(place["id"], date(2026, 2, 1), date(2026, 2, 28), provider_invoice_number="0002",
                 document_id=doc.id),
        ])
        await session.commit()

    async with sessions() as session:
        ctx = await load_context(session, place_id, exclude_document_id=doc.id)
    assert ctx.prior_bill.provider_invoice_number == "0001"


async def test_an_unknown_place_raises(sessions):
    async with sessions() as session:
        with pytest.raises(LookupError):
            await load_context(session, uuid.uuid4())
