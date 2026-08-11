from datetime import date
from decimal import Decimal

import pytest

from app.services.series import bill_series, monthly_series
from tests.conftest import bill_payload


class FakeBill:
    def __init__(self, start, end, kwh, total):
        self.period_start = date.fromisoformat(start)
        self.period_end = date.fromisoformat(end)
        self.consumption = Decimal(kwh) if kwh is not None else None
        self.total_amount = Decimal(total)


class TestProration:
    def test_single_month_bill_maps_exactly(self):
        bills = [FakeBill("2026-03-01", "2026-03-31", "300", "60")]
        points = monthly_series(bills, "cost")
        assert [(p.period, p.value) for p in points] == [("2026-03", 60.0)]

    def test_cross_month_bill_splits_by_days(self):
        # Mar 15 – Apr 13 = 30 days: 17 in March, 13 in April
        bills = [FakeBill("2026-03-15", "2026-04-13", "300", "60")]
        points = monthly_series(bills, "consumption")
        assert [p.period for p in points] == ["2026-03", "2026-04"]
        assert points[0].value == pytest.approx(300 * 17 / 30, abs=0.01)
        assert points[1].value == pytest.approx(300 * 13 / 30, abs=0.01)

    def test_multiple_bills_in_month_sum(self):
        bills = [
            FakeBill("2026-03-01", "2026-03-15", "100", "20"),
            FakeBill("2026-03-16", "2026-03-31", "150", "30"),
        ]
        points = monthly_series(bills, "cost")
        assert [(p.period, p.value) for p in points] == [("2026-03", 50.0)]

    def test_unit_price_is_weighted_average(self):
        # 100 kWh at 0.20 effective + 300 kWh at 0.40 effective
        bills = [
            FakeBill("2026-03-01", "2026-03-31", "100", "20"),
            FakeBill("2026-04-01", "2026-04-30", "300", "120"),
        ]
        points = monthly_series(bills, "unit_price")
        assert points[0].value == pytest.approx(0.20)
        assert points[1].value == pytest.approx(0.40)

    def test_gap_months_emit_no_point(self):
        bills = [
            FakeBill("2026-01-01", "2026-01-31", "100", "20"),
            FakeBill("2026-04-01", "2026-04-30", "100", "20"),
        ]
        points = monthly_series(bills, "cost")
        assert [p.period for p in points] == ["2026-01", "2026-04"]

    def test_month_from_to_filter(self):
        bills = [FakeBill("2026-01-01", "2026-06-30", "600", "120")]
        points = monthly_series(bills, "cost", month_from="2026-02", month_to="2026-03")
        assert [p.period for p in points] == ["2026-02", "2026-03"]

    def test_missing_consumption_skipped_for_unit_price(self):
        bills = [FakeBill("2026-03-01", "2026-03-31", None, "60")]
        assert monthly_series(bills, "unit_price") == []
        assert monthly_series(bills, "consumption") == []
        assert monthly_series(bills, "cost")[0].value == 60.0

    def test_bill_granularity_is_exact(self):
        bills = [FakeBill("2026-03-15", "2026-04-13", "300", "60")]
        points = bill_series(bills, "consumption")
        assert [(p.period, p.value) for p in points] == [("2026-04-13", 300.0)]
        assert bill_series(bills, "unit_price")[0].value == pytest.approx(0.20)


class TestSeriesEndpoints:
    async def test_place_series_cost(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        await client.post(url, json=bill_payload(), headers=auth_headers)
        await client.post(
            url,
            json=bill_payload(
                period_start="2026-04-01",
                period_end="2026-04-30",
                total_amount="80.00",
            ),
            headers=auth_headers,
        )

        r = await client.get(
            f"/places/{place['id']}/series",
            params={"metric": "cost"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["unit"] == "EUR"
        assert body["currency_code"] == "EUR"
        assert [(p["period"], p["value"]) for p in body["points"]] == [
            ("2026-03", 60.69),
            ("2026-04", 80.0),
        ]

    async def test_place_series_bill_granularity(self, client, auth_headers, place):
        await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        r = await client.get(
            f"/places/{place['id']}/series",
            params={"metric": "consumption", "granularity": "bill"},
            headers=auth_headers,
        )
        body = r.json()
        assert body["unit"] == "kWh"
        assert body["currency_code"] is None
        assert body["points"] == [{"period": "2026-03-31", "value": 250.5}]

    async def test_invalid_month_rejected(self, client, auth_headers, place):
        for params in ({"from": "2026-13"}, {"to": "2026-00"}):
            r = await client.get(
                f"/places/{place['id']}/series",
                params={"metric": "cost", **params},
                headers=auth_headers,
            )
            assert r.status_code == 422, params

    async def test_series_isolation(
        self, client, auth_headers, second_auth_headers, place
    ):
        r = await client.get(
            f"/places/{place['id']}/series", headers=second_auth_headers
        )
        assert r.status_code == 404

    async def test_compare(self, client, auth_headers, place):
        r = await client.post(
            "/places",
            json={
                "name": "Second Home",
                "address_line1": "Strada Exemplu 5",
                "city": "Cluj-Napoca",
                "postal_code": "400001",
                "country_code": "RO",
                "currency_code": "RON",
            },
            headers=auth_headers,
        )
        second_place = r.json()
        for p in (place, second_place):
            await client.post(
                f"/places/{p['id']}/bills",
                json=bill_payload(),
                headers=auth_headers,
            )

        r = await client.get(
            "/series/compare",
            params={"metric": "consumption"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["series"]) == 2
        names = {s["place_name"] for s in body["series"]}
        assert names == {"Main Residence", "Second Home"}
        for s in body["series"]:
            assert s["points"][0]["value"] == 250.5

    async def test_summary(self, client, auth_headers, place):
        await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        r = await client.get(
            f"/places/{place['id']}/stats/summary", headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["bill_count"] == 1
        assert body["last_period_end"] == "2026-03-31"
        assert float(body["avg_effective_unit_price"]) == pytest.approx(
            60.69 / 250.5, abs=0.0001
        )
