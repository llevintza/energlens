import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models import Bill, Place
from app.routers.deps import get_owned_place
from app.schemas.bill import BillCreate, BillRead, BillUpdate

router = APIRouter(prefix="/places/{place_id}/bills", tags=["bills"])


async def get_owned_bill(
    bill_id: uuid.UUID,
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> Bill:
    bill = await session.get(Bill, bill_id)
    if bill is None or bill.place_id != place.id:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


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
    bill = Bill(
        place_id=place.id,
        currency_code=place.currency_code,  # snapshot; place edits never rewrite history
        **data.model_dump(),
    )
    session.add(bill)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bill for this period already exists",
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
    for field, value in updates.items():
        setattr(bill, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bill for this period already exists",
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
