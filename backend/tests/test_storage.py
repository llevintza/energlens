"""The storage backends, both of them, without opening a socket.

`make check` must never touch the network — that is the entire reason
StorageBackend is a Protocol with two implementations rather than an S3 client
threaded through the routers. So S3Storage is exercised against botocore's
Stubber, which sits between the client and its HTTP layer: the request is still
built, signed and validated against the real S3 service model, and then answered
from a queue instead of the wire. A hand-written fake would only have proved that
our fake matches our calls — it would pass just as happily if we sent `Body=`
where S3 wants `Key=`.
"""

import io
import socket

import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.config import Settings
from app.main import app
from app.storage import (
    StorageConfigError,
    StorageObjectNotFound,
    build_storage,
    reset_storage,
)
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage, build_client

PDF = b"%PDF-1.4\nstub\n"
KEY = "11111111-1111-1111-1111-111111111111/abc123.pdf"


class TestLocalStorage:
    async def test_round_trip(self, tmp_path):
        storage = LocalStorage(tmp_path)
        await storage.put(KEY, PDF, "application/pdf")
        assert await storage.get(KEY) == PDF
        # Nested directories are created, and nothing else is left behind.
        assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["abc123.pdf"]

    async def test_get_missing_raises_the_shared_error(self, tmp_path):
        with pytest.raises(StorageObjectNotFound):
            await LocalStorage(tmp_path).get(KEY)

    async def test_delete_is_idempotent(self, tmp_path):
        """purge_objects retries by hand; deleting twice must not raise."""
        storage = LocalStorage(tmp_path)
        await storage.put(KEY, PDF, "application/pdf")
        await storage.delete(KEY)
        await storage.delete(KEY)

    async def test_signed_url_is_none(self, tmp_path):
        """Which is what tells the router to stream the bytes itself."""
        assert await LocalStorage(tmp_path).signed_url(KEY, 300) is None

    async def test_a_key_cannot_escape_the_root(self, tmp_path):
        """Unreachable today — keys are a UUID and a hex digest — and checked
        anyway, because the day a key is derived from a filename this is the
        line between a bug and a write-anywhere primitive."""
        with pytest.raises(ValueError):
            await LocalStorage(tmp_path).put("../escaped.pdf", PDF, "application/pdf")


@pytest.fixture
def no_sockets(monkeypatch):
    def _refuse(*args, **kwargs):
        raise AssertionError("this test opened a socket")

    monkeypatch.setattr(socket.socket, "connect", _refuse)


@pytest.fixture
def s3(no_sockets):
    # Built the way production builds it, not hand-rolled here: the signature
    # version lives in that function, and a client constructed differently would
    # test a presigning path the deployment never uses.
    client = build_client(
        endpoint_url="https://example.invalid",
        region="us-east-1",
        # Static credentials, deliberately: with blank ones botocore falls back
        # to the EC2 instance-metadata endpoint, which is a real network call.
        access_key_id="stub-key",
        secret_access_key="stub-secret",
    )
    with Stubber(client) as stubber:
        yield S3Storage(
            endpoint_url="https://example.invalid",
            bucket="bills",
            region="us-east-1",
            access_key_id="stub-key",
            secret_access_key="stub-secret",
            client=client,
        ), stubber


class TestS3Storage:
    async def test_put_sends_the_object_with_its_media_type(self, s3):
        storage, stubber = s3
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": "bills",
                "Key": KEY,
                "Body": PDF,
                "ContentType": "application/pdf",
            },
        )
        await storage.put(KEY, PDF, "application/pdf")
        stubber.assert_no_pending_responses()

    async def test_get_returns_the_bytes(self, s3):
        storage, stubber = s3
        stubber.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(PDF), len(PDF))},
            {"Bucket": "bills", "Key": KEY},
        )
        assert await storage.get(KEY) == PDF

    async def test_a_missing_key_becomes_the_shared_error(self, s3):
        """Both backends must report this the same way, or the download route
        has to know which backend it is talking to."""
        storage, stubber = s3
        stubber.add_client_error(
            "get_object", service_error_code="NoSuchKey", http_status_code=404
        )
        with pytest.raises(StorageObjectNotFound):
            await storage.get(KEY)

    async def test_other_errors_are_not_swallowed(self, s3):
        """A credentials failure must not be reported as "file is gone"."""
        storage, stubber = s3
        stubber.add_client_error(
            "get_object", service_error_code="AccessDenied", http_status_code=403
        )
        with pytest.raises(Exception) as excinfo:
            await storage.get(KEY)
        assert not isinstance(excinfo.value, StorageObjectNotFound)

    async def test_delete_is_issued(self, s3):
        storage, stubber = s3
        stubber.add_response("delete_object", {}, {"Bucket": "bills", "Key": KEY})
        await storage.delete(KEY)
        stubber.assert_no_pending_responses()

    async def test_signed_url_is_generated_offline(self, s3):
        """No stub queued: presigning is local HMAC over a canonical request."""
        storage, _ = s3
        url = await storage.signed_url(KEY, expires_in=300)
        assert url.startswith("https://example.invalid/bills/")
        assert "X-Amz-Expires=300" in url
        assert "X-Amz-Signature=" in url


class TestStorageConfiguration:
    def test_local_is_the_default(self):
        assert Settings(_env_file=None).storage_backend == "local"

    def test_s3_without_credentials_refuses_to_build(self, monkeypatch):
        """The check that turns a half-configured deploy into a failed boot."""
        import app.storage as storage_module

        monkeypatch.setattr(
            storage_module,
            "settings",
            Settings(
                _env_file=None,
                storage_backend="s3",
                s3_endpoint_url="",
                s3_bucket="",
                s3_access_key_id="",
                s3_secret_access_key="",
            ),
        )
        reset_storage()
        with pytest.raises(StorageConfigError) as excinfo:
            build_storage()
        message = str(excinfo.value)
        # The message must name the variables, or the operator is left guessing.
        for name in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID"):
            assert name in message
        reset_storage()

    def test_an_unknown_backend_is_refused(self, monkeypatch):
        import app.storage as storage_module

        monkeypatch.setattr(
            storage_module,
            "settings",
            Settings(_env_file=None, storage_backend="dropbox"),
        )
        reset_storage()
        with pytest.raises(StorageConfigError, match="dropbox"):
            build_storage()
        reset_storage()

    async def test_the_app_lifespan_validates_storage(self):
        """Nothing else covers the lifespan.

        httpx's ASGITransport does not run it, which is deliberate — it keeps the
        check out of the suite's way — but it also means this is the only place
        that proves the boot path works at all.
        """
        reset_storage()
        async with app.router.lifespan_context(app):
            pass
        reset_storage()
