import asyncio
import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://energy:energy@localhost:5432/energy_tracker_test"
)
os.environ["JWT_SECRET"] = "test-secret"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_async_session
from app.main import app
from app.models import Base

TEST_DB_URL = os.environ["DATABASE_URL"]


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
