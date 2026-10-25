"""bill_line_items and bill_meter_readings against a real database.

No endpoint writes these rows yet (#60), so rows go in through the ORM and the
bill around them through the API.
"""

import re
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Bill, BillLineItem, BillMeterReading
from app.models.bill import ReadMethod
from app.models.bill_line_item import ChargeKind
from app.schemas.bill_line_item import BillLineItemRead, ChargeKindLiteral
from app.services.bill_math import by_charge_kind, reconcile
from tests.conftest import bill_payload

_TYPES_TS = Path(__file__).resolve().parents[2] / "frontend/src/api/types.ts"

# 2025-06, page 2: (label, kind, kWh, unit price, net, VAT, sub-period).
LINES_2025_06 = [
    ("Energie Activă cf. OUG 27/2022", "energy", "44", "0.250160", "11.00", "2.09", ("2025-05-24", "2025-05-31")),
    ("Energie Activă cf. OUG 27/2022", "energy", "132", "0.254630", "33.61", "6.39", ("2025-06-01", "2025-06-24")),
    ("Tarif de extragere din rețea (TL)", "transmission", "176", "0.033030", "5.82", "1.11", None),
    ("Servicii sistem", "system_services", "44", "0.011510", "0.50", "0.10", ("2025-05-24", "2025-05-31")),
    ("Servicii sistem", "system_services", "132", "0.007040", "0.93", "0.18", ("2025-06-01", "2025-06-24")),
    ("Tarif de distribuție", "distribution", "176", "0.294080", "51.76", "9.83", None),
    ("Energie activă (preț furnizare) (7=1+2+3+4+5+6)", "other", None, None, "103.62", "19.70", None),
    ("Cogenerare", "cogeneration", "176", "0.003500", "0.62", "0.12", None),
    ("Contribuție CfD", "levy", "176", "0.000206", "0.03", "0.01", None),
    ("Certificate verzi", "green_certificates", "176", "0.0725416", "12.78", "2.43", None),
    ("Acciză", "excise", "176", "0.007240", "1.28", "0.24", None),
    ("Total energie electrică activă consumată (12=7+8+9+10+11)", "other", None, None, "118.33", "22.50", None),
]  # fmt: skip


def corpus_lines(bill_id: uuid.UUID) -> list[BillLineItem]:
    lines = []
    for no, (label, kind, qty, price, net, vat, period) in enumerate(
        LINES_2025_06, start=1
    ):
        lines.append(
            BillLineItem(
                bill_id=bill_id,
                line_no=no,
                charge_kind=kind,
                raw_label=label,
                quantity=Decimal(qty) if qty else None,
                unit="kWh" if qty else None,
                unit_price=Decimal(price) if price else None,
                net_amount=Decimal(net),
                tax_amount=Decimal(vat),
                period_start=date.fromisoformat(period[0]) if period else None,
                period_end=date.fromisoformat(period[1]) if period else None,
                is_subtotal=qty is None,
            )
        )
    return lines


@pytest.fixture
def sessions(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def bill_2025_06(client, auth_headers, place):
    r = await client.post(
        f"/places/{place['id']}/bills",
        json=bill_payload(
            period_start="2025-05-24",
            period_end="2025-06-24",
            consumption="176",
            net_amount="118.33",
            total_amount="140.83",
        ),
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestLineItems:
    async def test_corpus_bill_reconciles_from_the_database(
        self, sessions, bill_2025_06
    ):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add_all(corpus_lines(bill_id))
            await session.commit()

        async with sessions() as session:
            bill = await session.get(Bill, bill_id)
            items = (
                await session.scalars(
                    select(BillLineItem).where(BillLineItem.bill_id == bill_id)
                )
            ).all()

        assert len(items) == 12
        result = reconcile(bill, items)
        assert result.computed_net == Decimal("118.33")
        assert result.within_tolerance is True
        totals = by_charge_kind(items)
        assert totals["energy"] == Decimal("44.61")
        assert totals["distribution"] == Decimal("51.76")

    async def test_eight_decimal_unit_price_round_trips(
        self, sessions, bill_2025_06
    ):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add_all(corpus_lines(bill_id))
            await session.commit()

        async with sessions() as session:
            line = await session.scalar(
                select(BillLineItem).where(
                    BillLineItem.bill_id == bill_id, BillLineItem.line_no == 10
                )
            )
        assert line.raw_label == "Certificate verzi"
        assert line.unit_price == Decimal("0.07254160")
        # And on the wire, as a string, with nothing lost.
        wire = BillLineItemRead.model_validate(line).model_dump(mode="json")
        assert wire["unit_price"] == "0.07254160"

    async def test_line_period_narrower_than_the_bill_is_accepted(
        self, sessions, bill_2025_06
    ):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add_all(corpus_lines(bill_id))
            await session.commit()

        async with sessions() as session:
            line = await session.scalar(
                select(BillLineItem).where(
                    BillLineItem.bill_id == bill_id, BillLineItem.line_no == 1
                )
            )
        assert (line.period_start, line.period_end) == (
            date(2025, 5, 24),
            date(2025, 5, 31),
        )

    async def test_line_no_is_unique_per_bill(self, sessions, bill_2025_06):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add_all(corpus_lines(bill_id)[:1] + corpus_lines(bill_id)[:1])
            with pytest.raises(IntegrityError, match="uq_bill_line_items_bill_line"):
                await session.commit()

    async def test_unknown_charge_kind_is_rejected(self, sessions, bill_2025_06):
        line = corpus_lines(uuid.UUID(bill_2025_06["id"]))[0]
        line.charge_kind = "certificate_verzi"
        async with sessions() as session:
            session.add(line)
            with pytest.raises(IntegrityError, match="ck_bill_line_items_charge_kind"):
                await session.commit()

    async def test_reversed_line_period_is_rejected(self, sessions, bill_2025_06):
        line = corpus_lines(uuid.UUID(bill_2025_06["id"]))[0]
        line.period_start, line.period_end = line.period_end, line.period_start
        async with sessions() as session:
            session.add(line)
            with pytest.raises(
                IntegrityError, match="ck_bill_line_items_period_order"
            ):
                await session.commit()


def meter_reading(bill_id: uuid.UUID) -> BillMeterReading:
    return BillMeterReading(
        bill_id=bill_id,
        pod_code="RO001E107927758",
        meter_serial="001000672155312",
        grid_operator_code="107927758",
        index_previous=Decimal("26386"),
        index_current=Decimal("26562"),
        multiplier=Decimal("1"),
        read_method="self_read",
        read_on=date(2025, 6, 24),
        quantity=Decimal("176"),
    )


class TestMeterReadings:
    async def test_reading_round_trips(self, sessions, bill_2025_06):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add(meter_reading(bill_id))
            await session.commit()

        async with sessions() as session:
            reading = await session.scalar(
                select(BillMeterReading).where(BillMeterReading.bill_id == bill_id)
            )
        assert reading.pod_code == "RO001E107927758"
        assert reading.index_current - reading.index_previous == reading.quantity
        assert reading.register is None

    async def test_unknown_read_method_is_rejected(self, sessions, bill_2025_06):
        reading = meter_reading(uuid.UUID(bill_2025_06["id"]))
        reading.read_method = "autocitire"
        async with sessions() as session:
            session.add(reading)
            with pytest.raises(
                IntegrityError, match="ck_bill_meter_readings_read_method"
            ):
                await session.commit()


class TestCascade:
    async def test_deleting_a_bill_deletes_its_lines_and_readings(
        self, client, auth_headers, place, sessions, bill_2025_06
    ):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add_all(corpus_lines(bill_id))
            session.add(meter_reading(bill_id))
            await session.commit()

        r = await client.delete(
            f"/places/{place['id']}/bills/{bill_id}", headers=auth_headers
        )
        assert r.status_code == 204

        async with sessions() as session:
            for model in (BillLineItem, BillMeterReading):
                count = await session.scalar(
                    select(func.count()).select_from(model)
                )
                assert count == 0, model.__tablename__

    async def test_deleting_the_account_deletes_them_too(
        self, client, auth_headers, sessions, bill_2025_06
    ):
        bill_id = uuid.UUID(bill_2025_06["id"])
        async with sessions() as session:
            session.add_all(corpus_lines(bill_id))
            session.add(meter_reading(bill_id))
            await session.commit()

        r = await client.delete("/users/me", headers=auth_headers)
        assert r.status_code == 204

        async with sessions() as session:
            for model in (BillLineItem, BillMeterReading):
                count = await session.scalar(
                    select(func.count()).select_from(model)
                )
                assert count == 0, model.__tablename__


class TestTaxonomyAgrees:
    """The StrEnum, the CheckConstraint, the Literal and types.ts change together."""

    def test_all_four_copies_match(self):
        enum_values = [kind.value for kind in ChargeKind]
        assert list(get_args(ChargeKindLiteral)) == enum_values

        check = next(
            c
            for c in BillLineItem.__table__.constraints
            if c.name == "ck_bill_line_items_charge_kind"
        )
        assert re.findall(r"'(\w+)'", str(check.sqltext)) == enum_values

        ts = _TYPES_TS.read_text()
        union = re.search(r"export type ChargeKind =([^/]*?)\n\n", ts)
        assert union, "ChargeKind union not found in frontend/src/api/types.ts"
        assert re.findall(r"'(\w+)'", union.group(1)) == enum_values

    def test_meter_reading_read_method_matches_bills(self):
        """ck_bill_meter_readings_read_method repeats ck_bills_read_method's list."""

        def values(model, name):
            check = next(c for c in model.__table__.constraints if c.name == name)
            return re.findall(r"'(\w+)'", str(check.sqltext))

        enum_values = [method.value for method in ReadMethod]
        assert values(Bill, "ck_bills_read_method") == enum_values
        assert (
            values(BillMeterReading, "ck_bill_meter_readings_read_method")
            == enum_values
        )
