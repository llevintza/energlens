from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

from app.auth.transport import OAuthRedirectTransport
from app.config import settings


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.jwt_secret, lifetime_seconds=settings.jwt_lifetime_seconds
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=BearerTransport(tokenUrl="auth/jwt/login"),
    get_strategy=get_jwt_strategy,
)

# Same JWTs, different delivery: OAuth callbacks redirect the browser back to the
# SPA with the token in the URL fragment.
oauth_redirect_backend = AuthenticationBackend(
    name="jwt-redirect",
    transport=OAuthRedirectTransport(tokenUrl="auth/jwt/login"),
    get_strategy=get_jwt_strategy,
)
