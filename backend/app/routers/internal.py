"""Operator-only routes. Nothing here is user-facing, and nothing here is
mounted unless ``settings.internal_token`` is set — see app/main.py."""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.services import jobs


def build_internal_router(token: str) -> APIRouter:
    """The router, bound to ``token``. A factory rather than a module-level
    router reading settings so a test can mount it with a token of its own
    without the app under test having one."""
    if not token:
        raise ValueError("refusing to build the internal router with a blank token")

    def require_token(
        x_internal_token: str | None = Header(default=None, include_in_schema=False),
    ) -> None:
        # compare_digest: a plain == leaks how many leading characters matched.
        if x_internal_token is None or not secrets.compare_digest(
            x_internal_token.encode(), token.encode()
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid internal token")

    router = APIRouter(
        prefix="/internal",
        tags=["internal"],
        include_in_schema=False,
        dependencies=[Depends(require_token)],
    )

    @router.post("/jobs/sweep")
    async def sweep(
        session: AsyncSession = Depends(get_async_session),
    ) -> dict:
        """Run the reaper and report the queue.

        Called every 15 minutes by .github/workflows/agent-sweep.yml. The
        request itself is half the point: it wakes a spun-down free instance,
        whose boot starts the worker, whose first act is to reap.
        """
        reaped = await jobs.reap_stale_jobs(session)
        return {"reaped": reaped, "counts": await jobs.count_by_status(session)}

    return router
