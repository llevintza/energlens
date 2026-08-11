from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.clients.google import GoogleOAuth2

from app.config import settings

google_oauth_client = (
    GoogleOAuth2(settings.google_client_id, settings.google_client_secret)
    if settings.google_client_id and settings.google_client_secret
    else None
)

github_oauth_client = (
    GitHubOAuth2(settings.github_client_id, settings.github_client_secret)
    if settings.github_client_id and settings.github_client_secret
    else None
)
