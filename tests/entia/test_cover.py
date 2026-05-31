"""Test the Entia cover platform."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_CLOSE_COVER,
    SERVICE_CLOSE_COVER_TILT,
    SERVICE_OPEN_COVER,
    SERVICE_OPEN_COVER_TILT,
    SERVICE_SET_COVER_POSITION,
    SERVICE_SET_COVER_TILT_POSITION,
    CoverState,
)
from homeassistant.components.entia.const import (
    ATTR_BLIND_POSITION,
    BLIND_TILT_RANGE,
    DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry


def _setup_auto_update(mock_api_client: AsyncMock) -> None:
    """Make set_device_attribute automatically reflect in get_devices return value.

    This simulates the real API behaviour where a subsequent GET after a PUT
    returns the newly written value, so _handle_coordinator_update receives the
    position we commanded (matching _pending_api_value) rather than stale data.
    """

    async def _side_effect(device_id: int, attr_id: int, value: int) -> None:
        mock_api_client.get_devices.return_value = [
            {"id": device_id, "attributes": [{"id": attr_id, "value": value}]}
        ]

    mock_api_client.set_device_attribute.side_effect = _side_effect


MOCK_COVER_ID = 42475
MOCK_COVER_FLAT = {
    "flat": {
        "floors": [
            {
                "rooms": [
                    {
                        "id": 2,
                        "label": "Bedroom",
                        "devices": [{"id": MOCK_COVER_ID, "label": "Bedroom Blind"}],
                    }
                ]
            }
        ]
    }
}
MOCK_DEVICES_COVER_OPEN = [
    {"id": MOCK_COVER_ID, "attributes": [{"id": ATTR_BLIND_POSITION, "value": 0}]}
]
MOCK_DEVICES_COVER_CLOSED = [
    {"id": MOCK_COVER_ID, "attributes": [{"id": ATTR_BLIND_POSITION, "value": 100}]}
]
MOCK_DEVICES_COVER_PARTIAL = [
    {"id": MOCK_COVER_ID, "attributes": [{"id": ATTR_BLIND_POSITION, "value": 30}]}
]


def _entity_id(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        COVER_DOMAIN, DOMAIN, f"{DOMAIN}_{MOCK_COVER_ID}_cover"
    )
    assert entity_id is not None, "Cover entity was not registered"
    return entity_id


@pytest.fixture
async def init_cover_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> MockConfigEntry:
    """Set up the Entia integration with a cover device."""
    mock_api_client.get_flat.return_value = MOCK_COVER_FLAT
    mock_api_client.get_devices.return_value = MOCK_DEVICES_COVER_OPEN
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


@pytest.mark.usefixtures("init_cover_integration")
async def test_cover_open_state(hass: HomeAssistant) -> None:
    """Test that API value 0 (fully open) reports CoverState.OPEN and position 100."""
    state = hass.states.get(_entity_id(hass))
    assert state.state == CoverState.OPEN
    assert state.attributes[ATTR_CURRENT_POSITION] == 100


async def test_cover_closed_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that API value 100 (fully closed) reports CoverState.CLOSED and position 0."""
    mock_api_client.get_flat.return_value = MOCK_COVER_FLAT
    mock_api_client.get_devices.return_value = MOCK_DEVICES_COVER_CLOSED
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass))
    assert state.state == CoverState.CLOSED
    assert state.attributes[ATTR_CURRENT_POSITION] == 0


async def test_cover_partial_position(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that API value 30 maps to HA position 70."""
    mock_api_client.get_flat.return_value = MOCK_COVER_FLAT
    mock_api_client.get_devices.return_value = MOCK_DEVICES_COVER_PARTIAL
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass))
    assert state.state == CoverState.OPEN
    assert state.attributes[ATTR_CURRENT_POSITION] == 70


@pytest.mark.usefixtures("init_cover_integration")
async def test_open_cover(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that open_cover calls set_device_attribute with API value 0."""
    entity_id = _entity_id(hass)
    await hass.services.async_call(
        COVER_DOMAIN, SERVICE_OPEN_COVER, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, 0
    )


@pytest.mark.usefixtures("init_cover_integration")
async def test_close_cover(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that close_cover calls set_device_attribute with API value 100."""
    entity_id = _entity_id(hass)
    await hass.services.async_call(
        COVER_DOMAIN, SERVICE_CLOSE_COVER, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, 100
    )


@pytest.mark.usefixtures("init_cover_integration")
async def test_set_cover_position(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that set_cover_position inverts HA position to the API value."""
    entity_id = _entity_id(hass)
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 70},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, 30
    )


async def test_cover_unavailable_when_missing_from_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test that the entity becomes unavailable when device disappears from coordinator data."""
    mock_api_client.get_flat.return_value = MOCK_COVER_FLAT
    mock_api_client.get_devices.return_value = MOCK_DEVICES_COVER_OPEN
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == CoverState.OPEN

    mock_api_client.get_devices.return_value = []
    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("initial_api", "target_api", "tilt_pos", "expected_api_value"),
    [
        # Downward moves: last direction is down, tilt nudges toward open (API value decreases)
        pytest.param(0, 50, 100, 47, id="full_tilt_down"),
        pytest.param(0, 50, 50, 48, id="half_tilt_down"),
        pytest.param(0, 50, 0, 50, id="no_tilt_down"),
        pytest.param(0, 99, 100, 96, id="full_tilt_near_closed_down"),
        pytest.param(0, 1, 100, 0, id="full_tilt_clamped_at_open_down"),
        # Upward moves: last direction is up, tilt nudges toward closed (API value increases)
        pytest.param(100, 50, 100, 53, id="full_tilt_up"),
        pytest.param(100, 50, 50, 52, id="half_tilt_up"),
        pytest.param(100, 99, 100, 100, id="full_tilt_clamped_at_closed_up"),
    ],
)
async def test_set_cover_tilt_position(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    initial_api: int,
    target_api: int,
    tilt_pos: int,
    expected_api_value: int,
) -> None:
    """Test that set_cover_tilt_position nudges in the reverse of the last move direction."""
    mock_api_client.get_flat.return_value = MOCK_COVER_FLAT
    mock_api_client.get_devices.return_value = [
        {
            "id": MOCK_COVER_ID,
            "attributes": [{"id": ATTR_BLIND_POSITION, "value": initial_api}],
        }
    ]
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    _setup_auto_update(mock_api_client)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 100 - target_api},
        blocking=True,
    )
    mock_api_client.set_device_attribute.reset_mock()

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_TILT_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_TILT_POSITION: tilt_pos},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, expected_api_value
    )
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == tilt_pos


@pytest.mark.usefixtures("init_cover_integration")
async def test_open_cover_tilt(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that open_cover_tilt levels the slats (2 API units back from base)."""
    _setup_auto_update(mock_api_client)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 50},
        blocking=True,
    )
    mock_api_client.set_device_attribute.reset_mock()

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_OPEN_COVER_TILT,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, 50 - BLIND_TILT_RANGE
    )
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == 100


@pytest.mark.usefixtures("init_cover_integration")
async def test_close_cover_tilt(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that close_cover_tilt returns slats to base position."""
    _setup_auto_update(mock_api_client)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 50},
        blocking=True,
    )
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_OPEN_COVER_TILT,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    mock_api_client.set_device_attribute.reset_mock()

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_CLOSE_COVER_TILT,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, 50
    )
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == 0


@pytest.mark.usefixtures("init_cover_integration")
async def test_open_cover_tilt_after_upward_move(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that open_cover_tilt nudges toward closed after an upward move."""
    _setup_auto_update(mock_api_client)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_CLOSE_COVER,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 50},
        blocking=True,
    )
    mock_api_client.set_device_attribute.reset_mock()

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_OPEN_COVER_TILT,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    mock_api_client.set_device_attribute.assert_called_once_with(
        MOCK_COVER_ID, ATTR_BLIND_POSITION, 50 + BLIND_TILT_RANGE
    )
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == 100


@pytest.mark.usefixtures("init_cover_integration")
async def test_position_command_resets_tilt(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test that a position command resets tilt state to 0."""
    _setup_auto_update(mock_api_client)
    entity_id = _entity_id(hass)

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 50},
        blocking=True,
    )
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_OPEN_COVER_TILT,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    assert hass.states.get(entity_id).attributes[ATTR_CURRENT_TILT_POSITION] == 100

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: entity_id, ATTR_POSITION: 30},
        blocking=True,
    )
    assert hass.states.get(entity_id).attributes[ATTR_CURRENT_TILT_POSITION] == 0
