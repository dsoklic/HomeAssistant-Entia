"""DataUpdateCoordinator for the Entia integration."""

from datetime import timedelta
import html
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, CannotConnect, EntiaApiClient
from .client.ws_client import EntiaWsClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=5)

type EntiaConfigEntry = ConfigEntry[EntiaCoordinator]


def _build_label_map(flat_response: dict[str, Any]) -> dict[int, str]:
    """Build a {device_id: label} map from the /flat response."""
    label_map: dict[int, str] = {}
    for floor in flat_response.get("flat", {}).get("floors", []):
        for room in floor.get("rooms", []):
            for device in room.get("devices", []):
                label_map[int(device["id"])] = html.unescape(device.get("label", ""))
    return label_map


class EntiaCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Coordinator that polls state for all Entia devices."""

    config_entry: EntiaConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: EntiaConfigEntry) -> None:
        """Initialize the coordinator and API client."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=config_entry,
        )
        self.client = EntiaApiClient(
            session=async_get_clientsession(hass),
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
        )
        self.ws_client = EntiaWsClient(self.client, self._on_ws_event)

    @callback
    def _on_ws_event(self, device_id: int, attribute_id: int, value: Any) -> None:
        """Apply a single attribute update from the WebSocket to coordinator data."""
        if self.data is None or device_id not in self.data:
            return
        device = {
            **self.data[device_id],
            "attributes": {**self.data[device_id]["attributes"], attribute_id: value},
        }
        self.async_set_updated_data({**self.data, device_id: device})

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        """Fetch current state for all devices."""
        try:
            label_map = _build_label_map(await self.client.get_flat())
            devices = await self.client.get_devices()
            result: dict[int, dict[str, Any]] = {}
            for device in devices:
                device_id = int(device["id"])
                attributes = {
                    int(attr["id"]): attr.get("value")
                    for attr in device.get("attributes", [])
                }
                result[device_id] = {
                    "id": device_id,
                    "name": label_map.get(device_id) or str(device_id),
                    "attributes": attributes,
                }
        except AuthError as err:
            raise ConfigEntryAuthFailed from err
        except CannotConnect as err:
            raise UpdateFailed(f"Cannot connect to Entia API: {err}") from err
        return result
