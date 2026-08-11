"""Thin client for the Energlens API — always the API, never direct DB writes."""

import os

import httpx


class ApiError(Exception):
    pass


def _env(name: str) -> str | None:
    """ENERGLENS_* is the current name; ET_* is kept as a legacy alias."""
    return os.environ.get(f"ENERGLENS_{name}") or os.environ.get(f"ET_{name}")


class EnerglensClient:
    def __init__(self, api_url: str, token: str | None = None):
        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(timeout=30)
        self._token = token or _env("TOKEN")

    def login(self, email: str | None = None, password: str | None = None) -> None:
        email = email or _env("EMAIL")
        password = password or _env("PASSWORD")
        if not email or not password:
            raise ApiError(
                "No credentials: set ENERGLENS_TOKEN, or ENERGLENS_EMAIL and "
                "ENERGLENS_PASSWORD"
            )
        response = self._client.post(
            f"{self.api_url}/auth/jwt/login",
            data={"username": email, "password": password},
        )
        if response.status_code != 200:
            raise ApiError(f"Login failed ({response.status_code}): {response.text}")
        self._token = response.json()["access_token"]

    @property
    def _headers(self) -> dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Send an authenticated request, refreshing an expired token once.

        A long upload run can outlive its JWT; without the retry the run dies
        partway through even though the credentials to renew it are present.
        """
        response = self._client.request(
            method, f"{self.api_url}{path}", headers=self._headers, **kwargs
        )
        if response.status_code == 401 and (_env("EMAIL") and _env("PASSWORD")):
            self._token = None
            response = self._client.request(
                method, f"{self.api_url}{path}", headers=self._headers, **kwargs
            )
        return response

    def get_place(self, place_id: str) -> dict:
        response = self._request("GET", f"/places/{place_id}")
        if response.status_code == 200:
            return response.json()
        # Distinguish the causes: reporting a 401 or a 500 as "not found" sends
        # people hunting for a bad UUID when the real fault is elsewhere.
        if response.status_code == 404:
            raise ApiError(f"Place {place_id} not found")
        if response.status_code in (401, 403):
            raise ApiError(
                f"Not authorized ({response.status_code}) — check ENERGLENS_TOKEN "
                "or ENERGLENS_EMAIL/ENERGLENS_PASSWORD"
            )
        raise ApiError(
            f"Could not fetch place {place_id} ({response.status_code}): "
            f"{response.text[:300]}"
        )

    def create_bill(self, place_id: str, payload: dict) -> str:
        """Returns 'created', 'skipped' (duplicate period), or raises."""
        response = self._request("POST", f"/places/{place_id}/bills", json=payload)
        if response.status_code == 201:
            return "created"
        if response.status_code == 409:
            return "skipped"
        raise ApiError(
            f"Upload failed ({response.status_code}): {response.text[:300]}"
        )
