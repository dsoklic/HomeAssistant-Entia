"""Entia heat recovery ventilation fan entities."""

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_HRV_SPEED, DOMAIN
from .coordinator import EntiaConfigEntry, EntiaCoordinator

_SPEED_TO_PRESET: dict[int, str] = {1: "low", 2: "medium", 3: "high"}
_PRESET_TO_SPEED: dict[str, int] = {"low": 1, "medium": 2, "high": 3}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntiaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Entia HRV fan entities from a config entry."""
    coordinator: EntiaCoordinator = entry.runtime_data
    async_add_entities(
        EntiaHrvFan(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if ATTR_HRV_SPEED in device["attributes"]
    )


class EntiaHrvFan(CoordinatorEntity[EntiaCoordinator], FanEntity):
    """Representation of an Entia heat recovery ventilation unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_preset_modes = ["low", "medium", "high"]
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: EntiaCoordinator, device_id: int) -> None:
        """Initialize the HRV fan."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_fan"
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
        """Return True if the fan is running."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        return device["attributes"].get(ATTR_HRV_SPEED, 0) != 0

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        return _SPEED_TO_PRESET.get(device["attributes"].get(ATTR_HRV_SPEED, 0))

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan, optionally at a specific preset."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
            return
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HRV_SPEED, 1
        )
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HRV_SPEED, 0
        )
        await self.coordinator.async_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a specific speed preset."""
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HRV_SPEED, _PRESET_TO_SPEED[preset_mode]
        )
        await self.coordinator.async_refresh()
