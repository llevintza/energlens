"""Seed the database with a demo user and two years of plausible bills.

Run with:  python -m app.seed
Login:     demo@example.com / demo1234
"""

import asyncio
import math
from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi_users.password import PasswordHelper
from sqlalchemy import inspect, select

from app.db import async_session_maker, engine
from app.models import Base, Bill, Place, User

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo1234"
MONTHS = 24


def _last_month() -> tuple[int, int]:
    """Newest seeded bill period — the month before the current one.

    Derived rather than pinned: the dashboard's range filters are computed from
    the current date, so a hardcoded window would silently drift out of view
    (the 12-month filter first, then the 24-month default) on a long-lived
    deployment that only ever seeds once.
    """
    today = date.today()
    return (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _months_back(count: int) -> list[tuple[int, int]]:
    year, month = _last_month()
    out = []
    for _ in range(count):
        out.append((year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(out))


def _seasonal_factor(month: int) -> float:
    """1.0 in January, ~0.0 in July."""
    return (1 + math.cos(2 * math.pi * (month - 1) / 12)) / 2


def _make_bills(
    place: Place,
    base_kwh: float,
    winter_extra_kwh: float,
    start_price: float,
    price_step: float,
    fixed: float,
    provider: str,
    day_offset: int,
) -> list[Bill]:
    bills = []
    for index, (year, month) in enumerate(_months_back(MONTHS)):
        first = date(year, month, 1)
        if day_offset:
            period_start = first + timedelta(days=day_offset - 1)
            period_end = period_start + timedelta(
                days=monthrange(year, month)[1] - 1
            )
        else:
            period_start = first
            period_end = date(year, month, monthrange(year, month)[1])
        kwh = round(base_kwh + winter_extra_kwh * _seasonal_factor(month), 1)
        price = round(start_price + price_step * index, 4)
        subtotal = kwh * price + fixed
        taxes = subtotal * 0.19
        bills.append(
            Bill(
                place_id=place.id,
                period_start=period_start,
                period_end=period_end,
                consumption=Decimal(str(kwh)),
                unit_price=Decimal(str(price)),
                fixed_charges=_money(fixed),
                taxes=_money(taxes),
                total_amount=_money(subtotal + taxes),
                # No balance is carried forward in the demo, so what is payable
                # is what the bill is worth. Stated rather than left NULL, so a
                # fresh seed matches a database the migration backfilled.
                total_due=_money(subtotal + taxes),
                currency_code=place.currency_code,
                provider_name=provider,
                source="script",
            )
        )
    return bills


async def _is_migration_managed(conn) -> bool:
    return await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table("alembic_version")
    )


async def seed() -> None:
    async with engine.begin() as conn:
        # Only build the schema directly on a database Alembic has never touched
        # (a fresh local dev DB). Where migrations own the schema, issuing DDL
        # here would create tables behind Alembic's back — a model added before
        # its migration would then make the next `upgrade head` fail with
        # "already exists".
        if await _is_migration_managed(conn):
            print("alembic_version present — leaving schema to migrations")
        else:
            await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # Select the id, not the entity: User carries a joined eager load for
        # oauth_accounts, and scalar_one_or_none() on that raises
        # InvalidRequestError ("the unique() method must be invoked") — which
        # made every re-run of this supposedly idempotent seeder fail.
        existing = await session.execute(
            select(User.id).where(User.email == DEMO_EMAIL)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"{DEMO_EMAIL} already exists — nothing to do")
            return

        user = User(
            email=DEMO_EMAIL,
            hashed_password=PasswordHelper().hash(DEMO_PASSWORD),
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        main = Place(
            user_id=user.id,
            name="Main Residence",
            address_line1="Rua do Exemplo 12",
            city="Lisbon",
            postal_code="1100-123",
            country_code="PT",
            currency_code="EUR",
        )
        second = Place(
            user_id=user.id,
            name="Second Home",
            address_line1="Strada Exemplu 5",
            city="Cluj-Napoca",
            postal_code="400001",
            country_code="RO",
            currency_code="RON",
        )
        session.add_all([main, second])
        await session.flush()

        # Main residence: calendar-month bills. Second home: 15th-to-14th
        # periods so the monthly proration path shows up in the charts.
        session.add_all(
            _make_bills(main, 160, 190, 0.155, 0.0022, 5.90, "EDP Comercial", 0)
        )
        session.add_all(
            _make_bills(second, 45, 90, 0.65, 0.008, 12.0, "Electrica Furnizare", 15)
        )
        await session.commit()
        print(
            f"Seeded {DEMO_EMAIL} / {DEMO_PASSWORD} with 2 places × {MONTHS} bills"
        )


if __name__ == "__main__":
    asyncio.run(seed())
