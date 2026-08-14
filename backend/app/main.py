import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import auth_backend, oauth_redirect_backend
from app.auth.oauth import github_oauth_client, google_oauth_client
from app.auth.users import fastapi_users
from app.config import settings
from app.db import get_async_session
from app.middleware import MaxBodySizeMiddleware
from app.routers.account import router as account_router
from app.routers.bill_documents import router as bill_documents_router
from app.routers.bills import router as bills_router
from app.routers.oauth_login import router as oauth_login_router
from app.routers.places import router as places_router
from app.routers.series import router as series_router
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.storage import configure_storage

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Fail the boot, not the first upload.

    ``settings = Settings()`` is evaluated at import and every field has a
    default — that invariant is load-bearing in config.py — so nothing at import
    time can refuse a half-configured deployment. This runs before uvicorn binds
    the port, so on Render a STORAGE_BACKEND=s3 with a blank bucket crash-loops
    with the variable names in the log, the same shape as start.sh refusing to
    boot without DATABASE_URL. The alternative is a service that looks healthy
    until somebody uploads a file.

    Deliberately not a module-level call: that would make `import app.main`
    itself throw on a config error, turning every test collection and every
    tooling import into a config gate.

    httpx's ASGITransport — what tests/conftest.py uses — does not run the
    lifespan, so this is inert during the suite. tests/test_storage.py drives it
    directly for that reason.
    """
    configure_storage()
    yield


app = FastAPI(title="Energlens API", lifespan=lifespan)

# Order matters, and not in the obvious direction: add_middleware inserts at the
# front and Starlette wraps the list in reverse, so the LAST call here is the
# OUTERMOST layer. The size guard is registered first so that CORS stays outside
# it — otherwise a 413 would come back without Access-Control-Allow-Origin and
# the browser would report an opaque network error instead of the status code.
app.add_middleware(MaxBodySizeMiddleware)

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
# Before the generated users router, deliberately: its DELETE /users/{id} would
# otherwise match /users/me first and 422 trying to read "me" as a UUID.
app.include_router(account_router)
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
app.include_router(bill_documents_router)
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
