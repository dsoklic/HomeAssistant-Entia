"""Test the Entia coordinator's recovery from server outages."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.entia.api import BASE_URL
from homeassistant.components.entia.const import ATTR_LIGHT_STATE, DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

from .conftest import MOCK_DEVICE_ID, MOCK_FLAT


@pytest.fixture
def mock_ws_client() -> Generator[MagicMock]:
    """Replace the WebSocket client so tests control its callbacks."""
    with patch("homeassistant.components.entia.coordinator.EntiaWsClient") as mock_cls:
        mock_cls.return_value.listen = AsyncMock()
        yield mock_cls


def _light_state(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        LIGHT_DOMAIN, DOMAIN, f"{DOMAIN}_{MOCK_DEVICE_ID}"
    )
    assert entity_id is not None
    return hass.states.get(entity_id).state


async def test_ws_reconnect_refreshes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_ws_client: MagicMock,
) -> None:
    """When the WebSocket comes back, missed changes are fetched over REST."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_api_client.get_devices.reset_mock()

    on_reconnect = mock_ws_client.call_args.args[2]
    on_reconnect()
    await hass.async_block_till_done()

    mock_api_client.get_devices.assert_awaited_once()


class FakeEntiaServer:
    """Entia REST API that can go down and come back with its tokens wiped."""

    def __init__(self, aioclient_mock: AiohttpClientMocker) -> None:
        """Register the endpoints."""
        self.up = True
        self._issued = 0
        self._valid_tokens: set[str] = set()
        aioclient_mock.post(f"{BASE_URL}login", side_effect=self._login)
        aioclient_mock.get(f"{BASE_URL}flat/device", side_effect=self._authorized)
        aioclient_mock.get(f"{BASE_URL}flat", side_effect=self._authorized)
        self._mock = aioclient_mock

    def restart(self) -> None:
        """Come back up, no longer accepting tokens issued before the outage."""
        self.up = True
        self._valid_tokens.clear()

    async def _login(self, method, url, data):
        if not self.up:
            return AiohttpClientMockResponse(method, url, status=503)
        self._issued += 1
        token = f"token-{self._issued}"
        self._valid_tokens.add(token)
        return AiohttpClientMockResponse(method, url, json={"token": token})

    async def _authorized(self, method, url, data):
        if not self.up:
            return AiohttpClientMockResponse(method, url, status=503)
        # The mocker does not pass headers to side effects; read the latest call.
        token = self._mock.mock_calls[-1][3]["Authorization"].removeprefix("Bearer ")
        if token not in self._valid_tokens:
            return AiohttpClientMockResponse(method, url, status=403)
        if str(url).endswith("flat/device"):
            body = {
                "devices": [
                    {
                        "id": MOCK_DEVICE_ID,
                        "attributes": [{"id": ATTR_LIGHT_STATE, "value": 1}],
                    }
                ]
            }
        else:
            body = MOCK_FLAT
        return AiohttpClientMockResponse(method, url, json=body)


@pytest.mark.usefixtures("mock_ws_client")
async def test_recovers_after_outage_with_rejected_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Entities come back after an outage even though the old token is refused."""
    server = FakeEntiaServer(aioclient_mock)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    assert _light_state(hass) == STATE_ON

    server.up = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _light_state(hass) == STATE_UNAVAILABLE

    server.restart()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _light_state(hass) == STATE_ON
