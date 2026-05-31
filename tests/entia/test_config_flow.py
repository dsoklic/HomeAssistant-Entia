"""Test the Entia config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.components.entia.api import AuthError, CannotConnect
from homeassistant.components.entia.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

USER_INPUT = {
    CONF_USERNAME: "test@example.com",
    CONF_PASSWORD: "test-password",
}

FLAT_RESPONSE = {
    "flat": {"floors": [{"rooms": [{"id": 1, "label": "Living Room", "devices": []}]}]}
}


@pytest.fixture(autouse=True)
def api_mocks() -> Generator[tuple[AsyncMock, AsyncMock]]:
    """Patch EntiaApiClient.authenticate and get_flat for all config flow tests."""
    with (
        patch(
            "homeassistant.components.entia.config_flow.EntiaApiClient.authenticate",
            new_callable=AsyncMock,
        ) as mock_auth,
        patch(
            "homeassistant.components.entia.config_flow.EntiaApiClient.get_flat",
            new_callable=AsyncMock,
            return_value=FLAT_RESPONSE,
        ) as mock_flat,
    ):
        yield mock_auth, mock_flat


async def test_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test the config form is shown and an entry is created on valid input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Entia ({USER_INPUT[CONF_USERNAME]})"
    assert result["data"] == USER_INPUT
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_invalid_auth(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, api_mocks: tuple
) -> None:
    """Test that invalid credentials show the correct error and allow retry."""
    mock_auth, _mock_flat = api_mocks
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_auth.side_effect = AuthError
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_auth.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_connect(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, api_mocks: tuple
) -> None:
    """Test that a connection error shows the correct error and allows retry."""
    mock_auth, _mock_flat = api_mocks
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_auth.side_effect = CannotConnect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_auth.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_duplicate_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test that a duplicate flat ID aborts the flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"], USER_INPUT
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
