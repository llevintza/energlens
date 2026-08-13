class TestAuth:
    async def test_register_login_me(self, client):
        r = await client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "secret-password"},
        )
        assert r.status_code == 201
        assert r.json()["email"] == "new@example.com"

        r = await client.post(
            "/auth/jwt/login",
            data={"username": "new@example.com", "password": "secret-password"},
        )
        assert r.status_code == 200
        token = r.json()["access_token"]

        r = await client.get(
            "/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        assert r.json()["email"] == "new@example.com"

    async def test_wrong_password_rejected(self, client):
        await client.post(
            "/auth/register",
            json={"email": "u@example.com", "password": "right-password"},
        )
        r = await client.post(
            "/auth/jwt/login",
            data={"username": "u@example.com", "password": "wrong-password"},
        )
        assert r.status_code == 400

    async def test_duplicate_email_rejected(self, client):
        payload = {"email": "dup@example.com", "password": "some-password"}
        r = await client.post("/auth/register", json=payload)
        assert r.status_code == 201
        r = await client.post("/auth/register", json=payload)
        assert r.status_code == 400

    async def test_me_requires_token(self, client):
        r = await client.get("/users/me")
        assert r.status_code == 401


class TestDeleteOwnAccount:
    """`DELETE /users/me`.

    fastapi-users only generates a superuser-gated `DELETE /users/{id}`, so this route
    exists to give the settings screen something real behind its delete control.
    """

    async def _register_and_login(self, client, email: str) -> str:
        await client.post(
            "/auth/register", json={"email": email, "password": "secret-password"}
        )
        r = await client.post(
            "/auth/jwt/login",
            data={"username": email, "password": "secret-password"},
        )
        return r.json()["access_token"]

    async def test_deletes_the_account_and_its_data(self, client):
        token = await self._register_and_login(client, "goodbye@example.com")
        auth = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/places",
            headers=auth,
            json={
                "name": "Flat",
                "address_line1": "1 Example St",
                "city": "Lisbon",
                "postal_code": "1100-123",
                "country_code": "PT",
                "currency_code": "EUR",
            },
        )
        assert r.status_code == 201
        place_id = r.json()["id"]
        r = await client.post(
            f"/places/{place_id}/bills",
            headers=auth,
            json={
                "period_start": "2026-07-01",
                "period_end": "2026-07-31",
                "total_amount": "46.17",
            },
        )
        assert r.status_code == 201

        r = await client.delete("/users/me", headers=auth)
        assert r.status_code == 204

        # The token still parses, but the user behind it is gone.
        r = await client.get("/users/me", headers=auth)
        assert r.status_code == 401

        # And so are the places, via the FK cascade — not left orphaned.
        r = await client.post(
            "/auth/register",
            json={"email": "goodbye@example.com", "password": "secret-password"},
        )
        assert r.status_code == 201, "the email should be free to register again"
        r = await client.post(
            "/auth/jwt/login",
            data={"username": "goodbye@example.com", "password": "secret-password"},
        )
        r = await client.get(
            "/places", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
        )
        assert r.json() == []

    async def test_requires_authentication(self, client):
        r = await client.delete("/users/me")
        assert r.status_code == 401

    async def test_me_is_not_parsed_as_a_user_id(self, client):
        """Registration order regression.

        fastapi-users' `DELETE /users/{id}` is mounted on the same prefix, so if it were
        registered first it would match this path instead. Verified by inverting the
        order in main.py: this returns **403**, because the generated route's superuser
        dependency rejects before it ever tries to parse "me" as a UUID. Either way the
        user cannot delete their own account, which is what this pins.
        """
        token = await self._register_and_login(client, "ordering@example.com")
        r = await client.delete(
            "/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code not in (403, 422), "generated users router matched first"
        assert r.status_code == 204

    async def test_one_account_cannot_delete_another(self, client):
        keeper = await self._register_and_login(client, "keeper@example.com")
        await self._register_and_login(client, "leaver@example.com")

        # There is no route that takes someone else's id short of being a superuser.
        r = await client.delete(
            "/users/me", headers={"Authorization": f"Bearer {keeper}"}
        )
        assert r.status_code == 204

        r = await client.post(
            "/auth/jwt/login",
            data={"username": "leaver@example.com", "password": "secret-password"},
        )
        assert r.status_code == 200, "deleting one account must not affect another"
