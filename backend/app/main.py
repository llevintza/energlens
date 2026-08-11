import logging

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import auth_backend, oauth_redirect_backend
from app.auth.oauth import github_oauth_client, google_oauth_client
from app.auth.users import fastapi_users
from app.config import settings
from app.db import get_async_session
from app.routers.bills import router as bills_router
from app.routers.oauth_login import router as oauth_login_router
from app.routers.places import router as places_router
from app.routers.series import router as series_router
from app.schemas.user import UserCreate, UserRead, UserUpdate

logger = logging.getLogger(__name__)

app = FastAPI(title="Energlens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

for _client, _prefix in (
    (google_oauth_client, "/auth/google"),
    (github_oauth_client, "/auth/github"),
):
    if _client is not None:
        app.include_router(
            fastapi_users.get_oauth_router(
                _client,
                oauth_redirect_backend,
                settings.jwt_secret,
                associate_by_email=True,
                is_verified_by_default=True,
                csrf_token_cookie_secure=settings.oauth_cookie_secure,
            ),
            prefix=_prefix,
            tags=["auth"],
        )

if google_oauth_client is not None or github_oauth_client is not None:
    app.include_router(oauth_login_router)

app.include_router(places_router)
app.include_router(bills_router)
app.include_router(series_router)


# Liveness only, and deliberately so: this is render.yaml's healthCheckPath, and
# the platform polls it on a schedule. Touching Neon here would make every probe
# after an idle gap pay a scale-to-zero cold start, and a slow or suspended
# database would then read as a dead process and get the service restarted.
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# The readiness half, kept off the platform's health check path. A green /health
# only proves the process is up; a bad DSN is caught at boot by `alembic upgrade
# head` (start.sh), but nothing covers losing the database *after* boot, where
# every real endpoint 500s while /health stays 200.
@app.get("/health/db")
async def health_db(
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    # Deliberately broad. SQLAlchemy only wraps what the driver raises *after* a
    # connection exists; the failures this endpoint is for happen before that and
    # arrive raw — ConnectionRefusedError, TimeoutError, socket.gaierror on a
    # wrong Neon hostname, ssl.SSLError. Catching SQLAlchemyError alone let a
    # refused connection through as an unhandled 500. The body is one SELECT 1,
    # so there is no real logic here for a bare `except` to mask, and a probe
    # with an unhandled path is worse than a probe that over-catches.
    except Exception:
        # Log the cause, never return it: this endpoint is unauthenticated, and
        # SQLAlchemy error reprs carry the connection URL — password included.
        logger.exception("health check: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}
