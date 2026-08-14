from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.db import get_async_session
from app.models import User
from app.services.documents import purge_objects, storage_keys_for_user
from app.storage import StorageBackend, get_storage

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_account(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    """Delete the signed-in user, and everything of theirs.

    fastapi-users' generated users router only offers ``DELETE /users/{id}``, which is
    superuser-gated — so without this there is no way for someone to remove their own
    account, and the settings screen would be offering a control with nothing behind it.

    Deletion cascades: ``places.user_id`` and ``bills.place_id`` are both
    ``ON DELETE CASCADE``, and ``oauth_account.user_id`` likewise, so removing the row
    takes the places, the bills and any linked provider accounts with it.

    **The cascade stops at the database.** ``bill_documents`` rows go with the user,
    but the PDFs themselves live outside Postgres and no foreign key reaches them.
    ADR-0021 makes removing them part of the decision to store them at all: keeping
    someone's electricity bills after they asked to be forgotten is the failure mode
    that decision has to answer for. So the keys are collected before the row is
    destroyed and purged after the commit.

    **Registration order matters.** This must be mounted *before* the generated users
    router, or that router's ``DELETE /users/{id}`` matches first and rejects with 403 —
    its superuser dependency runs before it ever tries to read ``"me"`` as a UUID. There
    is a test pinning the order.
    """
    keys = await storage_keys_for_user(session, user.id)
    await session.delete(user)
    await session.commit()
    await purge_objects(storage, keys)
