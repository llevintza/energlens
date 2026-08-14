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

    # Bill-document storage. "local" or "s3"; see app/storage/ and ADR-0021.
    # Local is the default so a clone with no object-store account can run the
    # whole app and the whole suite. Every field below has a default for the
    # same reason the ones above do: the app must boot with nothing set.
    storage_backend: str = "local"
    storage_local_dir: str = str(_REPO_ROOT / ".storage")
    # Any S3-compatible endpoint (Cloudflare R2, Backblaze B2, MinIO, AWS).
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    # R2 ignores the region and wants "auto"; AWS and B2 want a real one.
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # Upload limits. 10 MB is ~40x the largest bill in the corpus (~265 KB) and
    # is enforced while streaming, so an oversized body is never fully read.
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_daily_limit: int = 20
    # Signed download URLs are capability URLs — they carry no auth of their
    # own, so they expire fast.
    signed_url_expires_in: int = 300

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
