"""Test the Entia light platform."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.components.entia.const import ATTR_LIGHT_STATE, DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry

MOCK_DEVICE_ID = 42474

MOCK_DEVICES_OFF = [
    {
        "id": MOCK_DEVICE_ID,
        "name": "Living Room Light",
        "attributes": [{"id": ATTR_LIGHT_STATE, "value": 0}],
    }
]


def _entity_id(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        LIGHT_DOMAIN, DOMAIN, f"{DOMAIN}_{MOCK_DEVICE_ID}"
    )
    assert entity_id is not None, "Light entity was not registered"
    return entity_id


@pytest.mark.usefixtures("init_integration")
async def test_light_on_state(hass: HomeAssistant) -> None:
    """Test that a light with value 1 reports STATE_ON."""
    assert hass.states.get(_entity_id(hass)).state == STATE_ON


async def test_light_off_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that a light with value 0 reports STATE_OFF."""
    mock_api_client.get_devices.return_value = MOCK_DEVICES_OFF
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(_entity_id(hass)).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_turn_off(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that turn_off calls set_device_attribute with value 0."""
    entity_id = _entity_id(hass)
    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_LIGHT_STATE, 0
    )


async def test_turn_on(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that turn_on calls set_device_attribute with value 1."""
    mock_api_client.get_devices.return_value = MOCK_DEVICES_OFF
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_LIGHT_STATE, 1
    )


async def test_light_unavailable_when_missing_from_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that the entity becomes unavailable when the device disappears from the flat."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == STATE_ON

    mock_api_client.get_devices.return_value = []
    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
