from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi_users.router.oauth import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    generate_csrf_token,
    generate_state_token,
)

from app.auth.oauth import github_oauth_client, google_oauth_client
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_CLIENTS = {"google": google_oauth_client, "github": github_oauth_client}


@router.get("/{provider}/login")
async def oauth_login(provider: str, request: Request) -> RedirectResponse:
    """Browser-navigation entry point for OAuth.

    fastapi-users' /authorize endpoint returns JSON and sets a CSRF cookie —
    fine for same-origin apps, but a cross-origin SPA fetch would make that a
    third-party cookie (blocked by Safari). Navigating here top-level sets the
    cookie first-party on the API origin, then forwards to the provider; the
    provider's redirect back to /callback carries the cookie (SameSite=Lax
    allows top-level navigations).
    """
    client = _CLIENTS.get(provider)
    if client is None:
        raise HTTPException(status_code=404, detail="Unknown or unconfigured provider")

    callback_url = str(request.url_for(f"oauth:{client.name}.jwt-redirect.callback"))
    csrf_token = generate_csrf_token()
    state = generate_state_token({CSRF_TOKEN_KEY: csrf_token}, settings.jwt_secret)
    authorization_url = await client.get_authorization_url(callback_url, state)

    response = RedirectResponse(authorization_url, status_code=302)
    response.set_cookie(
        CSRF_TOKEN_COOKIE_NAME,
        csrf_token,
        max_age=3600,
        path="/",
        secure=settings.oauth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
