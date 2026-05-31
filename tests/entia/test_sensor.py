"""Test the Entia temperature sensor platform."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.components.entia.const import ATTR_TEMPERATURE, DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry

MOCK_DEVICE_ID = 42474

MOCK_DEVICES_TEMP = [
    {"id": MOCK_DEVICE_ID, "attributes": [{"id": ATTR_TEMPERATURE, "value": 51}]}
]


def _entity_id(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        SENSOR_DOMAIN, DOMAIN, f"{DOMAIN}_{MOCK_DEVICE_ID}_temperature"
    )
    assert entity_id is not None, "Temperature sensor entity was not registered"
    return entity_id


async def test_temperature_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that a temperature sensor converts raw value to °C correctly."""
    mock_api_client.get_devices.return_value = MOCK_DEVICES_TEMP
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass))
    assert state.state == "25.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"


async def test_temperature_unavailable_when_missing_from_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that the entity becomes unavailable when the device disappears."""
    mock_api_client.get_devices.return_value = MOCK_DEVICES_TEMP
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == "25.5"

    mock_api_client.get_devices.return_value = []
    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("raw_value", "expected_temp"),
    [
        pytest.param(46, "23.0", id="46->23.0"),
        pytest.param(48, "24.0", id="48->24.0"),
        pytest.param(50, "25.0", id="50->25.0"),
        pytest.param(51, "25.5", id="51->25.5"),
    ],
)
async def test_temperature_conversion(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    raw_value: int,
    expected_temp: str,
) -> None:
    """Test raw-to-celsius conversion for known values."""
    mock_api_client.get_devices.return_value = [
        {
            "id": MOCK_DEVICE_ID,
            "attributes": [{"id": ATTR_TEMPERATURE, "value": raw_value}],
        }
    ]
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(_entity_id(hass)).state == expected_temp
