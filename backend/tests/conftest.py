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
from app.storage import get_storage
from app.storage.local import LocalStorage

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
def storage_root(tmp_path):
    """Where the suite's uploaded objects go. Per-test, and thrown away."""
    return tmp_path / "storage"


@pytest.fixture
async def client(db_engine, storage_root):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session
    # LocalStorage rooted in tmp_path rather than a fake: it is the production
    # default, so faking it here would leave the only backend this repo ships
    # by default untested. The override is also what keeps the suite from
    # writing into the real .storage/ directory.
    app.dependency_overrides[get_storage] = lambda: LocalStorage(storage_root)
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


# --- bill-document fixtures -------------------------------------------------
#
# Generated, never committed. AGENTS.md forbids committing a real bill and
# .gitignore has `*.pdf`, so every PDF the suite touches is built in memory here
# and nothing reaches disk except the storage root under tmp_path.


def make_pdf(pages: int = 2, marker: str = "") -> bytes:
    """A minimal, valid, multi-page PDF with a correct cross-reference table.

    The xref matters: without it pypdf falls back to rebuilding one by scanning
    the file, which succeeds but proves nothing about the page tree. With it,
    ``len(reader.pages)`` is exactly ``pages``, so a test can assert a real
    number rather than "not None".

    ``marker`` is a PDF comment — legal anywhere, ignored by parsers — so it
    changes the sha256 without changing the page count. That is what the
    (place_id, sha256) dedupe tests need to tell "same file" from "same shape".
    """
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
    ]
    # A page with no /Contents is a valid blank page; nothing here draws.
    objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"] * pages

    out = bytearray(b"%PDF-1.4\n")
    if marker:
        out += f"% {marker}\n".encode()
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        # Offsets are taken after the marker is written, so they stay correct.
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def make_png() -> bytes:
    """A real 1x1 PNG, for the "renamed to .pdf" rejection test.

    Built rather than pasted as a base64 blob so a reader can see it is a PNG.
    A browser sets Content-Type from the *extension*, so a .png renamed .pdf
    arrives declared as application/pdf — the magic-byte check is the only thing
    that catches it, and this fixture is what proves that check is load-bearing.
    """
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit RGB
    idat = zlib.compress(b"\x00\xff\x00\x00")  # filter byte + one red pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def make_corrupt_pdf() -> bytes:
    """Valid header, unparseable body: accepted, stored, page_count NULL.

    Storing and understanding are separate concerns, and this fixture is the
    only thing pinning that — from outside, a file that was rejected and a file
    stored with a null page count are indistinguishable unless a test asserts on
    the row.
    """
    return b"%PDF-1.7\n" + b"garbage that is not an object graph\n" * 4 + b"%%EOF\n"


def pdf_upload(data: bytes | None = None, name: str = "bill.pdf"):
    """The `files=` argument for an httpx multipart POST."""
    return {"file": (name, data if data is not None else make_pdf(), "application/pdf")}
