"""Deleting the objects, not just the rows.

``bill_documents.place_id`` and ``places.user_id`` are both ON DELETE CASCADE, so
deleting a place or an account removes the rows on its own — silently, and
without touching a single stored byte. Left there, every deletion would leak its
objects forever, and "delete my account" would be a promise the API does not
keep. ADR-0021 makes removing the bytes part of the decision to store them.

The keys therefore have to be read *before* the delete and purged *after* the
commit, which is why this is three explicit functions called from three routers
rather than an ORM event. A SQLAlchemy ``after_delete`` listener is synchronous
and fires inside the flush; awaiting an S3 round-trip from there is how you get
a half-committed transaction.
"""

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BillDocument, Place
from app.storage import StorageBackend

logger = logging.getLogger(__name__)


async def storage_keys_for_place(session: AsyncSession, place_id) -> list[str]:
    result = await session.execute(
        select(BillDocument.storage_key).where(BillDocument.place_id == place_id)
    )
    return list(result.scalars().all())


async def storage_keys_for_user(session: AsyncSession, user_id) -> list[str]:
    """Every object this user's deletion is about to strand.

    Both paths, on purpose. Today they are the same set — a document can only be
    uploaded to a place its owner owns, because get_owned_place says so. But
    ``uploaded_by`` carries its own ON DELETE CASCADE, so the day places are
    shared, the ownership join alone would miss rows the database still removes.
    The union is free now and correct later.
    """
    result = await session.execute(
        select(BillDocument.storage_key)
        .join(Place, Place.id == BillDocument.place_id)
        .where(or_(Place.user_id == user_id, BillDocument.uploaded_by == user_id))
    )
    return list(result.scalars().all())


async def purge_objects(storage: StorageBackend, keys: list[str]) -> None:
    """Best-effort delete, called after the rows are already committed away.

    Failures are logged and swallowed on purpose. The row is gone either way, so
    raising here would turn a successful account deletion into a 500 and invite
    the user to retry something that already worked. What is left behind is a
    stored object nobody can reach — a cost leak, not a correctness bug. There is
    no reconciliation sweep yet; ADR-0021 records that as a known gap.
    """
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logger.exception("failed to delete stored object %s", key)
