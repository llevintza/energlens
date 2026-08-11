from tests.conftest import bill_payload


class TestBillsCrud:
    async def test_create_snapshots_currency(self, client, auth_headers, place):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        bill = r.json()
        assert bill["currency_code"] == "EUR"
        assert bill["utility_type"] == "electricity"

    async def test_currency_snapshot_survives_place_change(
        self, client, auth_headers, place
    ):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        bill_id = r.json()["id"]

        r = await client.patch(
            f"/places/{place['id']}",
            json={"currency_code": "USD"},
            headers=auth_headers,
        )
        assert r.status_code == 200

        r = await client.get(
            f"/places/{place['id']}/bills/{bill_id}", headers=auth_headers
        )
        assert r.json()["currency_code"] == "EUR"

    async def test_invalid_period_rejected(self, client, auth_headers, place):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(period_start="2026-03-31", period_end="2026-03-01"),
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_duplicate_period_conflict(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        assert r.status_code == 201
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        assert r.status_code == 409

    async def test_update_and_delete(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        bill_id = r.json()["id"]

        r = await client.patch(
            f"{url}/{bill_id}",
            json={"total_amount": "99.99", "notes": "corrected"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["total_amount"] == "99.99"

        r = await client.patch(
            f"{url}/{bill_id}",
            json={"period_end": "2026-02-01"},
            headers=auth_headers,
        )
        assert r.status_code == 422

        r = await client.delete(f"{url}/{bill_id}", headers=auth_headers)
        assert r.status_code == 204
        r = await client.get(f"{url}/{bill_id}", headers=auth_headers)
        assert r.status_code == 404

    async def test_list_filters(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        await client.post(url, json=bill_payload(), headers=auth_headers)
        await client.post(
            url,
            json=bill_payload(period_start="2026-04-01", period_end="2026-04-30"),
            headers=auth_headers,
        )

        r = await client.get(url, headers=auth_headers)
        assert len(r.json()) == 2
        # newest first
        assert r.json()[0]["period_start"] == "2026-04-01"

        r = await client.get(
            url, params={"from": "2026-04-01"}, headers=auth_headers
        )
        assert len(r.json()) == 1


class TestBillIsolation:
    async def test_foreign_place_bills_are_404(
        self, client, auth_headers, second_auth_headers, place
    ):
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        bill_id = r.json()["id"]

        r = await client.get(url, headers=second_auth_headers)
        assert r.status_code == 404
        r = await client.get(f"{url}/{bill_id}", headers=second_auth_headers)
        assert r.status_code == 404
