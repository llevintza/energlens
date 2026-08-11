from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.db import get_async_session
from app.models import Place, User
from app.routers.deps import get_owned_place
from app.schemas.place import PlaceCreate, PlaceRead, PlaceUpdate

router = APIRouter(prefix="/places", tags=["places"])


@router.get("", response_model=list[PlaceRead])
async def list_places(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[Place]:
    result = await session.execute(
        select(Place).where(Place.user_id == user.id).order_by(Place.created_at)
    )
    return list(result.scalars().all())


@router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
async def create_place(
    data: PlaceCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Place:
    place = Place(user_id=user.id, **data.model_dump())
    session.add(place)
    await session.commit()
    await session.refresh(place)
    return place


@router.get("/{place_id}", response_model=PlaceRead)
async def get_place(place: Place = Depends(get_owned_place)) -> Place:
    return place


@router.patch("/{place_id}", response_model=PlaceRead)
async def update_place(
    data: PlaceUpdate,
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> Place:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    await session.commit()
    await session.refresh(place)
    return place


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_place(
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await session.delete(place)
    await session.commit()
