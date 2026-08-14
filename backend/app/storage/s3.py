"""S3-compatible object storage — Cloudflare R2, Backblaze B2, MinIO, AWS.

boto3 is synchronous, so every call goes through ``run_in_threadpool`` rather
than adding an async S3 client. At one to three files at a time that is the
right trade, and it is one fewer dependency in a 512 MB process.
"""

from typing import Any

from fastapi.concurrency import run_in_threadpool

from app.storage import StorageObjectNotFound


def build_client(
    *,
    endpoint_url: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
) -> Any:
    """Construct the boto3 S3 client.

    ``signature_version="s3v4"`` is not decoration. boto3 still presigns with
    SigV2 by default for some client configurations, and a SigV2 URL is rejected
    outright by Cloudflare R2 and Backblaze B2 — the two backends this exists
    for. The failure would appear only as a broken download against a real
    bucket, which is the hardest place to notice it.

    boto3 is imported here rather than at module scope: a deployment on local
    storage never calls this, and botocore is not a small import to pay for on a
    512 MB instance.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,  # unset means real AWS S3
        region_name=region or None,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        # `client` is the one seam the tests need: botocore's Stubber wraps a
        # real client object, and injecting it here keeps `make check` off the
        # network without mocking out any of our own code.
        self._client = client if client is not None else build_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    def _is_missing(self, exc: Exception) -> bool:
        """Tell "no such object" apart from every other S3 failure.

        Providers disagree on the code — AWS says NoSuchKey for get_object and
        404 for head_object, R2 and B2 say either — so match on both rather than
        turning a credentials error into a 410.
        """
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        return str(code) in {"NoSuchKey", "NoSuchBucket", "404"}

    async def put(self, key: str, data: bytes, media_type: str) -> None:
        await run_in_threadpool(
            lambda: self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=media_type
            )
        )

    async def get(self, key: str) -> bytes:
        def _read() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

        try:
            return await run_in_threadpool(_read)
        except Exception as exc:
            if self._is_missing(exc):
                raise StorageObjectNotFound(key) from exc
            raise

    async def delete(self, key: str) -> None:
        # S3 delete_object is already idempotent — a missing key is a 204.
        await run_in_threadpool(
            lambda: self._client.delete_object(Bucket=self._bucket, Key=key)
        )

    async def signed_url(self, key: str, expires_in: int) -> str | None:
        """A time-limited URL the browser fetches directly.

        Signing is local HMAC — no network call — so this is cheap and cannot
        fail on a slow bucket. The URL carries no auth of its own, which is why
        the expiry is short.
        """
        return await run_in_threadpool(
            lambda: self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        )
