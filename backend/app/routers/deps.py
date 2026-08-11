import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.db import get_async_session
from app.models import Place, User


async def get_owned_place(
    place_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Place:
    """Single choke point for user isolation: missing and foreign places are
    indistinguishable (404), so place ids can't be probed for existence."""
    place = await session.get(Place, place_id)
    if place is None or place.user_id != user.id:
        raise HTTPException(status_code=404, detail="Place not found")
    return place
