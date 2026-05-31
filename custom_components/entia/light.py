"""Entia light entities."""

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_LIGHT_STATE, DOMAIN
from .coordinator import EntiaConfigEntry, EntiaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntiaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Entia light entities from a config entry."""
    coordinator: EntiaCoordinator = entry.runtime_data
    async_add_entities(
        EntiaLight(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if ATTR_LIGHT_STATE in device["attributes"]
    )


class EntiaLight(CoordinatorEntity[EntiaCoordinator], LightEntity):
    """Representation of an Entia light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: EntiaCoordinator, device_id: int) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=coordinator.data[device_id]["name"],
            manufacturer="Entia",
        )

    @property
    def available(self) -> bool:
        """Return True if the device is present in the latest coordinator data."""
        return super().available and self._device_id in self.coordinator.data

    @property
    def is_on(self) -> bool | None:
        """Return True if the light is on."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        return device["attributes"].get(ATTR_LIGHT_STATE) == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_LIGHT_STATE, 1
        )
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_LIGHT_STATE, 0
        )
        await self.coordinator.async_refresh()
