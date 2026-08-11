"""The two health endpoints, and the split between them.

/health is what render.yaml points the platform at, so it must stay a pure
liveness probe. /health/db is the readiness half — it is the only thing that
proves the database is reachable, and it must never leak the DSN while saying so.
"""

import contextlib
import socket

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_async_session
from app.main import app

# A DSN shaped like the real one, planted inside the exception the failing
# session raises. If the endpoint ever returns the exception instead of a fixed
# string, these strings show up in the response body and the leak test fails.
FAKE_DSN = "postgresql+asyncpg://energy:hunter2@db.example.com/energlens"


@contextlib.contextmanager
def session_override(dependency):
    """Swap the session dependency, then put the fixture's own override back.

    Popping instead would leave the rest of the test talking to the real
    module-level engine rather than the per-test one from `db_engine`.
    """
    previous = app.dependency_overrides.get(get_async_session)
    app.dependency_overrides[get_async_session] = dependency
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_async_session, None)
        else:
            app.dependency_overrides[get_async_session] = previous


def failing_session():
    class FailingSession:
        async def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception(f"connect failed: {FAKE_DSN}"))

    async def override():
        # Only execute() raises. A stub that also blew up on teardown would turn
        # the 503 into a 500 after the response was already built, and the test
        # would then pass for the wrong reason.
        yield FailingSession()

    return override


class TestHealth:
    async def test_health_is_ok(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_health_does_not_touch_the_database(self, client):
        """Guards the reason /health is separate from /health/db.

        Wiring a database round-trip into this route would make the platform's
        health check flap whenever Neon is scaled to zero, so acquiring a session
        here is a regression even though the endpoint would still return 200.
        """

        async def refuse():
            raise AssertionError("/health must not open a database session")
            yield  # pragma: no cover — makes this an async generator

        with session_override(refuse):
            r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestHealthDb:
    async def test_reports_ok_on_a_real_round_trip(self, client):
        r = await client.get("/health/db")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "database": "ok"}

    async def test_returns_503_when_the_database_is_unreachable(self, client):
        with session_override(failing_session()):
            r = await client.get("/health/db")
        # 503, not 500: a live API with a dead database is a distinct state, and
        # the exact body is what tells the two health endpoints apart.
        assert r.status_code == 503
        assert r.json() == {"status": "error", "database": "unreachable"}

    async def test_does_not_leak_the_connection_string(self, client):
        """The failure path is unauthenticated and public.

        SQLAlchemy error reprs embed the connection URL, password and all, so
        returning the exception — the obvious way to write this endpoint — would
        publish the Neon credentials to anyone who could take the database down.
        """
        with session_override(failing_session()):
            r = await client.get("/health/db")
        body = r.text.lower()
        for leak in ("postgresql", "asyncpg", "hunter2", "db.example.com"):
            assert leak not in body, f"/health/db leaked {leak!r}: {r.text}"

    async def test_503_when_the_server_is_not_listening(self, client):
        """The failure that actually happens, reproduced rather than simulated.

        A suspended or misaddressed Neon endpoint fails at the socket, before any
        connection exists, so asyncpg's ConnectionRefusedError reaches the route
        unwrapped — SQLAlchemy only translates what the driver raises once
        connected. An `except SQLAlchemyError` therefore missed it and returned a
        bare 500, and the stub-based tests above all passed while it did. Nothing
        listens on the port below, which is the same shape as a suspended Neon.
        """
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = probe.getsockname()[1]

        engine = create_async_engine(
            f"postgresql+asyncpg://energy:hunter2@127.0.0.1:{dead_port}/energlens"
        )
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async def override():
            async with maker() as session:
                yield session

        try:
            with session_override(override):
                r = await client.get("/health/db")
        finally:
            await engine.dispose()

        assert r.status_code == 503
        assert r.json() == {"status": "error", "database": "unreachable"}
        assert "hunter2" not in r.text

    async def test_recovers_once_the_database_comes_back(self, client):
        """Nothing is cached or latched: the next probe reflects reality again."""
        with session_override(failing_session()):
            assert (await client.get("/health/db")).status_code == 503
        r = await client.get("/health/db")
        assert r.status_code == 200


@pytest.mark.parametrize("path", ["/health", "/health/db"])
async def test_health_needs_no_token(client, path):
    """Both are probed by infrastructure that holds no credentials."""
    r = await client.get(path)
    assert r.status_code != 401
