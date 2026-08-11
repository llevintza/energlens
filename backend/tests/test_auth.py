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
