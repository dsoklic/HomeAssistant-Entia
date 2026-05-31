"""The Entia integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EntiaConfigEntry, EntiaCoordinator

_PLATFORMS: list[Platform] = [
    Platform.COVER,
    Platform.FAN,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: EntiaConfigEntry) -> bool:
    """Set up Entia from a config entry."""
    coordinator = EntiaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    entry.async_create_background_task(
        hass,
        coordinator.ws_client.listen(),
        f"entia_websocket_{entry.entry_id}",
    )
    entry.async_on_unload(coordinator.ws_client.close)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EntiaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
