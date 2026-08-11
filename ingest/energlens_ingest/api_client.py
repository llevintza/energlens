"""Thin client for the Energlens API — always the API, never direct DB writes."""

import os

import httpx


class ApiError(Exception):
    pass


class EnerglensClient:
    def __init__(self, api_url: str, token: str | None = None):
        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(timeout=30)
        self._token = token or os.environ.get("ET_TOKEN")

    def login(self, email: str | None = None, password: str | None = None) -> None:
        email = email or os.environ.get("ET_EMAIL")
        password = password or os.environ.get("ET_PASSWORD")
        if not email or not password:
            raise ApiError(
                "No credentials: set ET_TOKEN, or ET_EMAIL and ET_PASSWORD"
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

    def get_place(self, place_id: str) -> dict:
        response = self._client.get(
            f"{self.api_url}/places/{place_id}", headers=self._headers
        )
        if response.status_code != 200:
            raise ApiError(f"Place {place_id} not found ({response.status_code})")
        return response.json()

    def create_bill(self, place_id: str, payload: dict) -> str:
        """Returns 'created', 'skipped' (duplicate period), or raises."""
        response = self._client.post(
            f"{self.api_url}/places/{place_id}/bills",
            json=payload,
            headers=self._headers,
        )
        if response.status_code == 201:
            return "created"
        if response.status_code == 409:
            return "skipped"
        raise ApiError(
            f"Upload failed ({response.status_code}): {response.text[:300]}"
        )
