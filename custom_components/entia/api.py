"""Entia REST API client."""

from typing import Any

import aiohttp

BASE_URL = "https://api.entia.si/"

# A hung server must not block a poll for aiohttp's default five minutes.
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Status codes for a rejected token or login.
_AUTH_REJECTED = (401, 403)


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
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in _AUTH_REJECTED:
                    raise AuthError("Invalid credentials")
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"Cannot connect: {err}") from err
        if not isinstance(data, dict) or not data.get("token"):
            raise CannotConnect("Login response did not contain a token")
        self._token = data["token"]

    def invalidate_token(self) -> None:
        """Forget the current token so the next request logs in again."""
        self._token = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request, logging in again if the token is rejected.

        After a server restart the old token may be refused with 401 or 403; a
        fresh login fixes that. A rejection of the fresh token raises AuthError.
        """
        await self.get_token()
        status, data = await self._send(method, path, **kwargs)
        if status in _AUTH_REJECTED:
            await self.authenticate()
            status, data = await self._send(method, path, **kwargs)
            if status in _AUTH_REJECTED:
                raise AuthError("Re-authentication failed")
        return data

    async def _send(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        """Send one request; return (status, body), body None if auth was rejected."""
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as resp:
                if resp.status in _AUTH_REJECTED:
                    return resp.status, None
                resp.raise_for_status()
                return resp.status, await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
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
            f"flat/device/{device_id}/attribute/{attribute_id}/rt",
            json={"value": value},
        )
