import asyncio
import os
import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DB_ENV = _REPO_ROOT / "scripts" / "db.env"
_DB_SH = _REPO_ROOT / "scripts" / "db.sh"


def _read_db_env() -> dict[str, str]:
    """Read the defaults out of scripts/db.env, the single source of truth.

    That file is a sourceable shell fragment of `: "${NAME:=value}"` lines, so
    the environment can override it and both shell scripts load it with one `.`
    line. Only the defaults are wanted here — an exported PGDATABASE aimed at
    the development database must not redirect a suite that drops every table.
    """
    pattern = re.compile(r'^:\s*"\$\{(\w+):=([^}]*)\}"')
    values: dict[str, str] = {}
    for line in _DB_ENV.read_text().splitlines():
        if match := pattern.match(line.strip()):
            values[match.group(1)] = match.group(2)
    return values


_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}


def _refuse_remote(url: str) -> None:
    """This suite drops every table it connects to. Keep it on localhost.

    scripts/db.sh makes the same refusal for the shell entry points; without it
    here, the one path that can name an arbitrary host would be the one path
    with no guard at all.
    """
    host = re.sub(r"[:/?].*$", "", re.sub(r"^[^:]*://(?:[^@/]*@)?", "", url))
    if host not in _LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing to run the test suite against '{host}': it is not localhost,\n"
            f"and every table in the target database is dropped on each run.\n\n"
            f"Fix: unset ENERGLENS_TEST_DATABASE_URL"
        )


def _test_database_url() -> str:
    if override := os.environ.get("ENERGLENS_TEST_DATABASE_URL"):
        _refuse_remote(override)
        return override
    # Environment over file, matching what scripts/db.sh does when it sources
    # db.env — otherwise `PGPORT=5433 make test-backend` preflights one cluster
    # and then connects to another. Only PGDATABASE_TEST is consulted for the
    # database name, so an exported PGDATABASE aimed at development is inert.
    env = _read_db_env()

    def setting(key: str) -> str:
        return os.environ.get(key) or env[key]

    url = (
        f"postgresql+asyncpg://{setting('PGUSER')}:{setting('PGPASSWORD')}"
        f"@{setting('PGHOST')}:{setting('PGPORT')}/{setting('PGDATABASE_TEST')}"
    )
    _refuse_remote(url)
    return url


# Set before importing app.*, which reads the environment at import time.
# DATABASE_URL is overwritten unconditionally: whatever is exported points at
# the development database, and every table in this one gets dropped.
os.environ["DATABASE_URL"] = _test_database_url()
os.environ["JWT_SECRET"] = "test-secret"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_async_session
from app.main import app
from app.models import Base

TEST_DB_URL = os.environ["DATABASE_URL"]


def pytest_configure(config):
    """Fail with the fix rather than an asyncpg traceback.

    scripts/db.sh owns these diagnostics, so `make test-backend` and a bare
    `uv run pytest` — what an agent that ignores the Makefile will type — give
    identical advice. Skipped only when the URL was overridden, since the script
    checks the database named in scripts/db.env; _refuse_remote has already
    established that the override is local.
    """
    if os.environ.get("ENERGLENS_TEST_DATABASE_URL") or not _DB_SH.exists():
        return
    result = subprocess.run(
        [str(_DB_SH), "preflight", "test"], capture_output=True, text=True
    )
    if result.returncode != 0:
        pytest.exit(result.stderr.rstrip() or "database preflight failed", returncode=1)


@pytest.fixture(scope="session", autouse=True)
def create_schema():
    async def _run():
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_run())


@pytest.fixture
async def db_engine():
    # NullPool keeps connections from leaking across pytest-asyncio event loops.
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    yield engine
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()


@pytest.fixture
async def client(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def register_and_login(client: AsyncClient, email: str) -> dict[str, str]:
    password = "password-123"
    r = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/auth/jwt/login", data={"username": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def auth_headers(client):
    return await register_and_login(client, "alice@example.com")


@pytest.fixture
async def second_auth_headers(client):
    return await register_and_login(client, "bob@example.com")


PLACE_PAYLOAD = {
    "name": "Main Residence",
    "address_line1": "Rua do Exemplo 12",
    "city": "Lisbon",
    "postal_code": "1100-123",
    "country_code": "PT",
    "currency_code": "EUR",
}


@pytest.fixture
async def place(client, auth_headers):
    r = await client.post("/places", json=PLACE_PAYLOAD, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def bill_payload(**overrides):
    payload = {
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "consumption": "250.5",
        "unit_price": "0.18",
        "fixed_charges": "5.90",
        "taxes": "9.70",
        "total_amount": "60.69",
        "provider_name": "EDP",
        "source": "manual",
    }
    payload.update(overrides)
    return payload
