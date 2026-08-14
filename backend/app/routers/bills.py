import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models import Bill, BillDocument, Place
from app.routers.deps import get_owned_place
from app.schemas.bill import BillCreate, BillRead, BillUpdate

router = APIRouter(prefix="/places/{place_id}/bills", tags=["bills"])


DUPLICATE_INVOICE = "A bill with this invoice number already exists"
DUPLICATE_PERIOD = "A bill for this period already exists"


async def get_owned_bill(
    bill_id: uuid.UUID,
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> Bill:
    bill = await session.get(Bill, bill_id)
    if bill is None or bill.place_id != place.id:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


async def _duplicate_detail(
    session: AsyncSession,
    place_id: uuid.UUID,
    values: dict,
    exclude_id: uuid.UUID | None = None,
) -> str | None:
    """Which uniqueness rule this bill would break, if any.

    Identity lives on the invoice number now (uq_bills_place_invoice), because a
    Stornare reverses an invoice and reprints its period — the period constraint
    this replaces made the correction unstorable.

    PostgreSQL exempts NULLs from a UNIQUE tuple, so bills with no invoice number
    would be unconstrained entirely. Every bill the ingest CLI sends is one of
    those, and README's promise that its re-runs skip what is already uploaded
    rests on the 409. So the old period rule survives here, in application code,
    for exactly those bills: deliberate and tested, rather than silently dropped.
    """
    query = select(Bill.id).where(Bill.place_id == place_id)
    if values.get("provider_invoice_number"):
        query = query.where(
            Bill.provider_invoice_number == values["provider_invoice_number"],
            # IS NOT DISTINCT FROM: two bills with the same number and no series
            # are the same bill, but `= NULL` would never say so.
            Bill.provider_invoice_series.is_not_distinct_from(
                values.get("provider_invoice_series")
            ),
        )
        detail = DUPLICATE_INVOICE
    else:
        query = query.where(
            Bill.utility_type == values["utility_type"],
            Bill.period_start == values["period_start"],
            Bill.period_end == values["period_end"],
        )
        detail = DUPLICATE_PERIOD
    if exclude_id is not None:
        query = query.where(Bill.id != exclude_id)
    existing = await session.execute(query.limit(1))
    return detail if existing.scalar_one_or_none() else None


async def _check_corrects_bill(
    session: AsyncSession,
    place_id: uuid.UUID,
    corrects_bill_id: uuid.UUID | None,
    self_id: uuid.UUID | None = None,
) -> None:
    """Refuse a correction pointing at a bill that is not on this place.

    The foreign key names bills.id globally, so without this any signed-in user
    could link their credit note to a stranger's bill. 422 rather than 404: the
    response must not confirm that the id exists somewhere else.

    A bill correcting itself is refused here too — it is a cycle of one, and
    anything walking the chain later would have to defend against it.
    """
    if corrects_bill_id is None:
        return
    target = await session.get(Bill, corrects_bill_id)
    if target is None or target.place_id != place_id or corrects_bill_id == self_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="corrects_bill_id does not refer to a bill on this place",
        )


async def _check_document(
    session: AsyncSession,
    place_id: uuid.UUID,
    document_id: uuid.UUID | None,
) -> None:
    """Refuse a link to a document that is not on this place.

    Same reasoning as _check_corrects_bill: bill_documents.id is global, so
    without this any signed-in user could attach a stranger's PDF to their own
    bill — and then read it back through the bill. 422, not 404, so the response
    never confirms the id exists elsewhere.
    """
    if document_id is None:
        return
    document = await session.get(BillDocument, document_id)
    if document is None or document.place_id != place_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_id does not refer to a document on this place",
        )


@router.get("", response_model=list[BillRead])
async def list_bills(
    utility_type: str | None = None,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> list[Bill]:
    query = select(Bill).where(Bill.place_id == place.id)
    if utility_type:
        query = query.where(Bill.utility_type == utility_type)
    if date_from:
        query = query.where(Bill.period_end >= date_from)
    if date_to:
        query = query.where(Bill.period_start <= date_to)
    result = await session.execute(query.order_by(Bill.period_start.desc()))
    return list(result.scalars().all())


@router.post("", response_model=BillRead, status_code=status.HTTP_201_CREATED)
async def create_bill(
    data: BillCreate,
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> Bill:
    values = data.model_dump()
    await _check_corrects_bill(session, place.id, values["corrects_bill_id"])
    await _check_document(session, place.id, values["document_id"])
    if detail := await _duplicate_detail(session, place.id, values):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    bill = Bill(
        place_id=place.id,
        currency_code=place.currency_code,  # snapshot; place edits never rewrite history
        **values,
    )
    session.add(bill)
    try:
        await session.commit()
    except IntegrityError:
        # The check above answers with a message; this catches the race between
        # it and the commit, where only uq_bills_place_invoice can still fire.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_INVOICE
        )
    await session.refresh(bill)
    return bill


@router.get("/{bill_id}", response_model=BillRead)
async def get_bill(bill: Bill = Depends(get_owned_bill)) -> Bill:
    return bill


@router.patch("/{bill_id}", response_model=BillRead)
async def update_bill(
    data: BillUpdate,
    bill: Bill = Depends(get_owned_bill),
    session: AsyncSession = Depends(get_async_session),
) -> Bill:
    updates = data.model_dump(exclude_unset=True)
    new_start = updates.get("period_start", bill.period_start)
    new_end = updates.get("period_end", bill.period_end)
    if new_end < new_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_end must not be before period_start",
        )
    if "corrects_bill_id" in updates:
        await _check_corrects_bill(
            session, bill.place_id, updates["corrects_bill_id"], self_id=bill.id
        )
    if "document_id" in updates:
        await _check_document(session, bill.place_id, updates["document_id"])
    # Against the values the bill would end up with, not the patch: the same
    # rule as create, so an edit cannot reach a state a create would refuse.
    merged = {
        field: updates.get(field, getattr(bill, field))
        for field in (
            "utility_type",
            "period_start",
            "period_end",
            "provider_invoice_series",
            "provider_invoice_number",
        )
    }
    if detail := await _duplicate_detail(
        session, bill.place_id, merged, exclude_id=bill.id
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    for field, value in updates.items():
        setattr(bill, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_INVOICE
        )
    await session.refresh(bill)
    return bill


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill: Bill = Depends(get_owned_bill),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await session.delete(bill)
    await session.commit()
