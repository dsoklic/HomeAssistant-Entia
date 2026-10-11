"""Test the Entia climate (per-room heating) platform."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.entia.const import (
    ATTR_HMI_HVAC_MODE,
    ATTR_HMI_INSIDE_TEMP,
    ATTR_HMI_TARGET_TEMP,
    DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry

MOCK_DEVICE_ID = 42487

# Room 2978 HMI from a real /flat/device dump: inside 52 -> 26.0 °C,
# target 46 -> 23.0 °C, mode 2 -> heat.
MOCK_DEVICES_HMI = [
    {
        "id": MOCK_DEVICE_ID,
        "attributes": [
            {"id": ATTR_HMI_INSIDE_TEMP, "value": 52},
            {"id": ATTR_HMI_TARGET_TEMP, "value": 46},
            {"id": ATTR_HMI_HVAC_MODE, "value": 2},
        ],
    }
]


def _entity_id(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        CLIMATE_DOMAIN, DOMAIN, f"{DOMAIN}_{MOCK_DEVICE_ID}_climate"
    )
    assert entity_id is not None, "Climate entity was not registered"
    return entity_id


async def _setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    devices: list | None = None,
) -> None:
    mock_api_client.get_devices.return_value = (
        MOCK_DEVICES_HMI if devices is None else devices
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


async def test_climate_temperatures(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Current and target temperatures are scaled from raw half-degree units."""
    await _setup(hass, mock_config_entry, mock_api_client)

    state = hass.states.get(_entity_id(hass))
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 26.0
    assert state.attributes[ATTR_TEMPERATURE] == 23.0
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING


@pytest.mark.parametrize(
    ("raw_value", "expected_mode", "expected_action"),
    [
        pytest.param(0, HVACMode.OFF, HVACAction.OFF, id="0->off"),
        pytest.param(1, HVACMode.COOL, HVACAction.COOLING, id="1->cool"),
        pytest.param(2, HVACMode.HEAT, HVACAction.HEATING, id="2->heat"),
    ],
)
async def test_hvac_mode_mapping(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    raw_value: int,
    expected_mode: HVACMode,
    expected_action: HVACAction,
) -> None:
    """Raw HMI_HVAC_MODE values map to HA modes and actions (0=off,1=cool,2=heat)."""
    await _setup(
        hass,
        mock_config_entry,
        mock_api_client,
        devices=[
            {
                "id": MOCK_DEVICE_ID,
                "attributes": [
                    {"id": ATTR_HMI_INSIDE_TEMP, "value": 52},
                    {"id": ATTR_HMI_TARGET_TEMP, "value": 46},
                    {"id": ATTR_HMI_HVAC_MODE, "value": raw_value},
                ],
            }
        ],
    )

    state = hass.states.get(_entity_id(hass))
    assert state.state == expected_mode
    assert state.attributes[ATTR_HVAC_ACTION] == expected_action


@pytest.mark.parametrize(
    ("mode", "expected_value"),
    [
        pytest.param(HVACMode.OFF, 0, id="off->0"),
        pytest.param(HVACMode.COOL, 1, id="cool->1"),
        pytest.param(HVACMode.HEAT, 2, id="heat->2"),
    ],
)
async def test_set_hvac_mode_writes_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mode: HVACMode,
    expected_value: int,
) -> None:
    """Selecting a mode writes the matching value to HMI_HVAC_MODE."""
    await _setup(hass, mock_config_entry, mock_api_client)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: _entity_id(hass), ATTR_HVAC_MODE: mode},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HMI_HVAC_MODE, expected_value
    )


async def test_set_temperature_writes_scaled_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Setting 21.5 °C writes the raw value 43 to the target-temp attribute."""
    await _setup(hass, mock_config_entry, mock_api_client)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 21.5},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HMI_TARGET_TEMP, 43
    )


async def test_climate_not_created_without_hmi_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """A device lacking the HMI temp attributes yields no climate entity."""
    await _setup(
        hass,
        mock_config_entry,
        mock_api_client,
        devices=[{"id": 99999, "attributes": [{"id": 401, "value": 1}]}],
    )

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            CLIMATE_DOMAIN, DOMAIN, f"{DOMAIN}_99999_climate"
        )
        is None
    )


async def test_climate_unavailable_when_missing_from_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """The entity becomes unavailable when the device disappears."""
    await _setup(hass, mock_config_entry, mock_api_client)
    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == HVACMode.HEAT

    mock_api_client.get_devices.return_value = []
    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("raw_value", "expected_temp"),
    [
        pytest.param(40, 20.0, id="40->20.0"),
        pytest.param(46, 23.0, id="46->23.0"),
        pytest.param(47, 23.5, id="47->23.5"),
    ],
)
async def test_target_temperature_conversion(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    raw_value: int,
    expected_temp: float,
) -> None:
    """Raw target-temp values convert to °C correctly."""
    await _setup(
        hass,
        mock_config_entry,
        mock_api_client,
        devices=[
            {
                "id": MOCK_DEVICE_ID,
                "attributes": [
                    {"id": ATTR_HMI_INSIDE_TEMP, "value": 52},
                    {"id": ATTR_HMI_TARGET_TEMP, "value": raw_value},
                    {"id": ATTR_HMI_HVAC_MODE, "value": 2},
                ],
            }
        ],
    )

    assert hass.states.get(_entity_id(hass)).attributes[ATTR_TEMPERATURE] == expected_temp
