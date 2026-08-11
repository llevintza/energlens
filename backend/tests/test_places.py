from tests.conftest import PLACE_PAYLOAD


class TestPlacesCrud:
    async def test_create_and_list(self, client, auth_headers):
        r = await client.post("/places", json=PLACE_PAYLOAD, headers=auth_headers)
        assert r.status_code == 201
        created = r.json()
        assert created["currency_code"] == "EUR"

        r = await client.get("/places", headers=auth_headers)
        assert r.status_code == 200
        assert [p["id"] for p in r.json()] == [created["id"]]

    async def test_currency_code_normalized(self, client, auth_headers):
        r = await client.post(
            "/places",
            json={**PLACE_PAYLOAD, "currency_code": "ron", "country_code": "ro"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        assert r.json()["currency_code"] == "RON"
        assert r.json()["country_code"] == "RO"

    async def test_invalid_currency_rejected(self, client, auth_headers):
        r = await client.post(
            "/places",
            json={**PLACE_PAYLOAD, "currency_code": "E1R"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_update(self, client, auth_headers, place):
        r = await client.patch(
            f"/places/{place['id']}",
            json={"name": "Renamed", "city": "Porto"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"
        assert r.json()["city"] == "Porto"
        assert r.json()["address_line1"] == PLACE_PAYLOAD["address_line1"]

    async def test_delete(self, client, auth_headers, place):
        r = await client.delete(f"/places/{place['id']}", headers=auth_headers)
        assert r.status_code == 204
        r = await client.get(f"/places/{place['id']}", headers=auth_headers)
        assert r.status_code == 404


class TestPlaceIsolation:
    async def test_foreign_place_is_404(
        self, client, auth_headers, second_auth_headers, place
    ):
        for method, kwargs in (
            ("get", {}),
            ("patch", {"json": {"name": "hacked"}}),
            ("delete", {}),
        ):
            r = await getattr(client, method)(
                f"/places/{place['id']}", headers=second_auth_headers, **kwargs
            )
            assert r.status_code == 404, method

    async def test_list_only_shows_own(
        self, client, auth_headers, second_auth_headers, place
    ):
        r = await client.get("/places", headers=second_auth_headers)
        assert r.json() == []

    async def test_unauthenticated_rejected(self, client, place):
        r = await client.get("/places")
        assert r.status_code == 401
