"""Where bill PDFs live.

Two implementations behind one Protocol, chosen by ``settings.storage_backend``.
The Protocol is the point: ``make check`` must never open a socket, and someone
with no object-store account has to be able to run the whole application. So
``local`` is the default and ``s3`` is the deployment-time upgrade.

See docs/adr/0021-pdf-blob-storage.md for why the bytes are kept at all.
"""

from typing import Protocol

from app.config import settings

# The four values an S3-compatible backend cannot work without. s3_region is
# absent deliberately: it has a usable default ("auto", which is what R2 wants)
# and blanking it is not a misconfiguration.
S3_REQUIRED_SETTINGS = (
    "s3_endpoint_url",
    "s3_bucket",
    "s3_access_key_id",
    "s3_secret_access_key",
)


class StorageConfigError(RuntimeError):
    """Raised at import time, so a half-configured deployment never boots."""


class StorageObjectNotFound(LookupError):
    """The row survives, its bytes do not.

    Not hypothetical: with ``storage_backend="local"`` on Render, which declares
    no disk, every object is lost at the next deploy or spin-down while the rows
    stay. Both backends raise this rather than leaking ``FileNotFoundError`` or
    botocore's ``ClientError``, so the router has one thing to catch.
    """


class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, media_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def signed_url(self, key: str, expires_in: int) -> str | None:
        """A URL the browser can fetch directly, or None for "stream it yourself"."""
        ...


def build_storage() -> StorageBackend:
    """Construct the configured backend, or explain what is missing.

    Both imports are local: ``s3`` pulls in boto3 (and botocore, which is not
    small), and a deployment running on local storage should not pay for it.
    """
    backend = settings.storage_backend.strip().lower()

    if backend == "local":
        from app.storage.local import LocalStorage

        return LocalStorage(settings.storage_local_dir)

    if backend == "s3":
        missing = [
            name.upper()
            for name in S3_REQUIRED_SETTINGS
            if not getattr(settings, name).strip()
        ]
        if missing:
            raise StorageConfigError(
                "STORAGE_BACKEND=s3 but these are unset or blank: "
                f"{', '.join(missing)}. Set them, or set STORAGE_BACKEND=local. "
                "See the Deployment section of README.md."
            )
        from app.storage.s3 import S3Storage

        return S3Storage(
            endpoint_url=settings.s3_endpoint_url,
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )

    raise StorageConfigError(
        f"STORAGE_BACKEND={settings.storage_backend!r} is not a backend. "
        "Use 'local' or 's3'."
    )


_backend: StorageBackend | None = None


def configure_storage() -> StorageBackend:
    """Build the backend once, at import, so a bad config fails at boot.

    ``start.sh`` runs under ``set -e`` and this is reached while uvicorn imports
    the app, so a missing bucket credential aborts the deploy with the message
    above — the same way a bad DATABASE_URL already aborts on ``alembic upgrade
    head``. The alternative, discovering it on somebody's first upload, is how a
    deployment looks healthy for a week.
    """
    global _backend
    if _backend is None:
        _backend = build_storage()
    return _backend


def get_storage() -> StorageBackend:
    """FastAPI dependency. Overridable in tests, like ``get_async_session``."""
    return configure_storage()


def reset_storage() -> None:
    """Drop the memoised backend. For tests that change the settings."""
    global _backend
    _backend = None
