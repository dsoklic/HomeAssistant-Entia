"""Entia REST API client."""

from typing import Any

import aiohttp

BASE_URL = "https://api.entia.si/"


class AuthError(Exception):
    """Authentication failed."""


class CannotConnect(Exception):
    """Cannot connect to the API."""


class EntiaApiClient:
    """Async client for the Entia REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    async def authenticate(self) -> None:
        """Obtain a bearer token and store it."""
        try:
            async with self._session.post(
                f"{BASE_URL}login",
                json={
                    "username": self._username,
                    "password": self._password,
                    "platform": "home_assistant",
                    "device_model": "home_assistant",
                    "device_serial": "0000",
                },
            ) as resp:
                if resp.status in (401, 403):
                    raise AuthError("Invalid credentials")
                resp.raise_for_status()
                data = await resp.json()
                self._token = data["token"]
        except aiohttp.ClientError as err:
            raise CannotConnect(f"Cannot connect: {err}") from err

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request, re-authenticating once on 401."""
        if self._token is None:
            await self.authenticate()

        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with self._session.request(
                method, f"{BASE_URL}{path}", headers=headers, **kwargs
            ) as resp:
                if resp.status == 401:
                    await self.authenticate()
                    headers = {"Authorization": f"Bearer {self._token}"}
                    async with self._session.request(
                        method, f"{BASE_URL}{path}", headers=headers, **kwargs
                    ) as retry_resp:
                        if retry_resp.status == 401:
                            raise AuthError("Re-authentication failed")
                        retry_resp.raise_for_status()
                        return await retry_resp.json()
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise CannotConnect(f"Cannot connect: {err}") from err

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the underlying HTTP session."""
        return self._session

    async def get_token(self) -> str:
        """Return the current token, authenticating first if necessary."""
        if self._token is None:
            await self.authenticate()
        assert self._token is not None
        return self._token

    async def get_flat(self) -> dict[str, Any]:
        """Return the flat metadata (id, name, etc.)."""
        return await self._request("GET", "flat")

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return all devices with their current attribute values.

        The API returns {"connected": ..., "devices": [...]} — extract the list.
        """
        response = await self._request("GET", "flat/device")
        if isinstance(response, dict):
            return list(response.get("devices", []))
        return list(response)

    async def set_device_attribute(
        self, device_id: int, attribute_id: int, value: Any
    ) -> dict[str, Any]:
        """Set a device attribute value."""
        return await self._request(
            "PUT",
            f"flat/device/{device_id}/attribute/{attribute_id}",
            json={"value": value},
        )
