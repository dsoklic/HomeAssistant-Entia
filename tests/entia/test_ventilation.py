"""Test the Entia heat recovery ventilation (fan-only climate) entity."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_TURN_ON,
    HVACAction,
    HVACMode,
)
from homeassistant.components.entia.const import (
    ATTR_HRV_MODE,
    ATTR_HRV_SPEED,
    DOMAIN,
    HRV_MODE_HEAT_RECOVERY,
    HRV_MODE_PASS_THROUGH,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry

MOCK_DEVICE_ID = 42530


def _hrv(speed: int = 2, mode: int = 1) -> dict:
    """Return an HRV device (defaults: medium speed, heat recovery)."""
    return {
        "id": MOCK_DEVICE_ID,
        "attributes": [
            {"id": ATTR_HRV_MODE, "value": mode},
            {"id": ATTR_HRV_SPEED, "value": speed},
        ],
    }


def _entity_id(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        CLIMATE_DOMAIN, DOMAIN, f"{DOMAIN}_{MOCK_DEVICE_ID}_ventilation"
    )
    assert entity_id is not None, "Ventilation entity was not registered"
    return entity_id


async def _setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    devices: list | None = None,
) -> None:
    mock_api_client.get_devices.return_value = [_hrv()] if devices is None else devices
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


async def _set_devices(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, devices: list
) -> None:
    mock_config_entry.runtime_data.client.get_devices.return_value = devices
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_ventilation_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """A running unit is fan-only with its speed as fan mode and mode as preset."""
    await _setup(hass, mock_config_entry, mock_api_client)

    state = hass.states.get(_entity_id(hass))
    assert state.state == HVACMode.FAN_ONLY
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.FAN
    assert state.attributes[ATTR_FAN_MODE] == FAN_MEDIUM
    assert state.attributes[ATTR_PRESET_MODE] == HRV_MODE_HEAT_RECOVERY
    assert ATTR_TEMPERATURE not in state.attributes


async def test_ventilation_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Speed 0 means off."""
    await _setup(
        hass, mock_config_entry, mock_api_client, devices=[_hrv(speed=0, mode=0)]
    )

    state = hass.states.get(_entity_id(hass))
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF
    assert state.attributes[ATTR_PRESET_MODE] == HRV_MODE_PASS_THROUGH


@pytest.mark.parametrize(
    ("fan_mode", "expected_speed"),
    [
        pytest.param(FAN_LOW, 1, id="low->1"),
        pytest.param(FAN_MEDIUM, 2, id="medium->2"),
        pytest.param(FAN_HIGH, 3, id="high->3"),
    ],
)
async def test_set_fan_mode_writes_speed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    fan_mode: str,
    expected_speed: int,
) -> None:
    """Selecting a fan mode writes the matching speed."""
    await _setup(hass, mock_config_entry, mock_api_client)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: _entity_id(hass), ATTR_FAN_MODE: fan_mode},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HRV_SPEED, expected_speed
    )


@pytest.mark.parametrize(
    ("preset", "expected_value"),
    [
        pytest.param(HRV_MODE_PASS_THROUGH, 0, id="pass_through->0"),
        pytest.param(HRV_MODE_HEAT_RECOVERY, 1, id="heat_recovery->1"),
    ],
)
async def test_set_preset_writes_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    preset: str,
    expected_value: int,
) -> None:
    """Selecting a preset writes the matching HRV mode."""
    await _setup(hass, mock_config_entry, mock_api_client)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: _entity_id(hass), ATTR_PRESET_MODE: preset},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HRV_MODE, expected_value
    )


async def test_set_hvac_mode_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Switching to off writes speed 0."""
    await _setup(hass, mock_config_entry, mock_api_client)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: _entity_id(hass), ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HRV_SPEED, 0
    )


async def test_turn_on_restores_last_speed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Turning on after off resumes the speed the unit was last running at."""
    await _setup(hass, mock_config_entry, mock_api_client, devices=[_hrv(speed=3)])
    entity_id = _entity_id(hass)
    await _set_devices(hass, mock_config_entry, [_hrv(speed=0)])
    assert hass.states.get(entity_id).state == HVACMode.OFF

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HRV_SPEED, 3
    )


async def test_turn_on_defaults_to_low(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """With no speed seen yet, turning on starts at low."""
    await _setup(hass, mock_config_entry, mock_api_client, devices=[_hrv(speed=0)])

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: _entity_id(hass), ATTR_HVAC_MODE: HVACMode.FAN_ONLY},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_DEVICE_ID, ATTR_HRV_SPEED, 1
    )


async def test_no_separate_fan_or_select_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """The HRV is exposed only as the climate entity."""
    await _setup(hass, mock_config_entry, mock_api_client)

    assert hass.states.async_entity_ids("fan") == []
    assert hass.states.async_entity_ids("select") == []
