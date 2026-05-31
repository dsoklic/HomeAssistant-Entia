"""Common fixtures for the Entia tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.entia.const import ATTR_LIGHT_STATE, DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

MOCK_ENTRY_DATA = {
    CONF_USERNAME: "test@example.com",
    CONF_PASSWORD: "test-password",
}

MOCK_DEVICE_ID = 42474
MOCK_FLAT = {
    "flat": {
        "floors": [
            {
                "rooms": [
                    {
                        "id": 1,
                        "label": "Living Room",
                        "devices": [
                            {"id": MOCK_DEVICE_ID, "label": "Living Room Light"}
                        ],
                    }
                ]
            }
        ]
    }
}
MOCK_DEVICES_ON = [
    {"id": MOCK_DEVICE_ID, "attributes": [{"id": ATTR_LIGHT_STATE, "value": 1}]}
]
MOCK_DEVICES_OFF = [
    {"id": MOCK_DEVICE_ID, "attributes": [{"id": ATTR_LIGHT_STATE, "value": 0}]}
]


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.entia.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_ENTRY_DATA,
        unique_id=MOCK_ENTRY_DATA[CONF_USERNAME],
    )


@pytest.fixture
def mock_api_client():
    """Patch EntiaApiClient with default light-on state."""
    with patch("homeassistant.components.entia.coordinator.EntiaApiClient") as mock_cls:
        instance = mock_cls.return_value
        instance.get_flat = AsyncMock(return_value=MOCK_FLAT)
        instance.get_devices = AsyncMock(return_value=MOCK_DEVICES_ON)
        instance.set_device_attribute = AsyncMock(return_value={"value": 1})
        yield instance


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> MockConfigEntry:
    """Set up the Entia integration for testing."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
