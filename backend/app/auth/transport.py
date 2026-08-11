from fastapi import Response
from fastapi.responses import RedirectResponse
from fastapi_users.authentication import BearerTransport

from app.config import settings


class OAuthRedirectTransport(BearerTransport):
    """Sends OAuth login responses back to the SPA instead of returning JSON.

    The token travels in the URL fragment, which browsers never send to servers,
    so it cannot leak into access logs along the way.
    """

    async def get_login_response(self, token: str) -> Response:
        url = f"{settings.frontend_url.rstrip('/')}/auth/callback#access_token={token}"
        return RedirectResponse(url, status_code=302)
