from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://energy:energy@localhost:5432/energlens"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_lifetime_seconds: int = 60 * 60 * 24 * 7

    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    # Set false only for plain-http local testing in browsers that reject
    # Secure cookies on http://localhost (e.g. Safari).
    oauth_cookie_secure: bool = True

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
