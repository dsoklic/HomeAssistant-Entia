"""Test the Entia REST API client."""

import pytest

from homeassistant.components.entia.api import (
    BASE_URL,
    AuthError,
    CannotConnect,
    EntiaApiClient,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from tests.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

LOGIN_URL = f"{BASE_URL}login"
DEVICES_URL = f"{BASE_URL}flat/device"
DEVICES = [{"id": 1, "attributes": []}]


def _client(hass: HomeAssistant) -> EntiaApiClient:
    return EntiaApiClient(async_get_clientsession(hass), "user", "pass")


def _token_issuer(aioclient_mock: AiohttpClientMocker) -> None:
    """Register a login endpoint that issues token-1, token-2, ... on each call."""
    issued = 0

    async def login(method, url, data):
        nonlocal issued
        issued += 1
        return AiohttpClientMockResponse(method, url, json={"token": f"token-{issued}"})

    aioclient_mock.post(LOGIN_URL, side_effect=login)


def _devices_responses(aioclient_mock: AiohttpClientMocker, *statuses: int) -> None:
    """Register a device endpoint answering with the given statuses in order."""
    queue = list(statuses)

    async def devices(method, url, data):
        return AiohttpClientMockResponse(
            method, url, status=queue.pop(0), json={"devices": DEVICES}
        )

    aioclient_mock.get(DEVICES_URL, side_effect=devices)


def _bearer(call) -> str:
    _method, _url, _data, headers = call
    return headers["Authorization"]


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_token_logs_in_again(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """A token rejected after a server restart is replaced with a fresh login."""
    _token_issuer(aioclient_mock)
    _devices_responses(aioclient_mock, status, 200)

    assert await _client(hass).get_devices() == DEVICES

    device_calls = [c for c in aioclient_mock.mock_calls if str(c[1]) == DEVICES_URL]
    assert [_bearer(c) for c in device_calls] == ["Bearer token-1", "Bearer token-2"]


async def test_rejected_fresh_token_raises_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A request rejected even with a fresh token is a real auth failure."""
    _token_issuer(aioclient_mock)
    _devices_responses(aioclient_mock, 403, 403)

    with pytest.raises(AuthError):
        await _client(hass).get_devices()


@pytest.mark.parametrize("status", [401, 403])
async def test_login_rejected_raises_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """A login rejected by the server stays a permanent auth failure."""
    aioclient_mock.post(LOGIN_URL, status=status)

    with pytest.raises(AuthError):
        await _client(hass).authenticate()


async def test_login_without_token_raises_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A login answer without a token (e.g. a maintenance page) is an outage."""
    aioclient_mock.post(LOGIN_URL, json={"message": "maintenance"})

    with pytest.raises(CannotConnect):
        await _client(hass).authenticate()


async def test_timeout_raises_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A hung request is reported as an outage, not an unexpected error."""
    _token_issuer(aioclient_mock)
    aioclient_mock.get(DEVICES_URL, exc=TimeoutError())

    with pytest.raises(CannotConnect):
        await _client(hass).get_devices()


async def test_invalidate_token_forces_new_login(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """After invalidate_token(), the next token comes from a fresh login."""
    _token_issuer(aioclient_mock)
    client = _client(hass)

    assert await client.get_token() == "token-1"
    client.invalidate_token()
    assert await client.get_token() == "token-2"
