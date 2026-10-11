"""Entia climate (per-room heating) entities."""

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_HMI_INSIDE_TEMP,
    ATTR_HMI_TARGET_TEMP,
    DOMAIN,
    HMI_MAX_TEMP,
    HMI_MIN_TEMP,
    TEMP_SCALE,
)
from .coordinator import EntiaConfigEntry, EntiaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntiaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Entia climate entities from a config entry."""
    coordinator: EntiaCoordinator = entry.runtime_data
    async_add_entities(
        EntiaClimate(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if ATTR_HMI_INSIDE_TEMP in device["attributes"]
        and ATTR_HMI_TARGET_TEMP in device["attributes"]
    )


class EntiaClimate(CoordinatorEntity[EntiaCoordinator], ClimateEntity):
    """Representation of an Entia per-room heating controller (HMI)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 1 / TEMP_SCALE
    _attr_min_temp = HMI_MIN_TEMP
    _attr_max_temp = HMI_MAX_TEMP

    def __init__(self, coordinator: EntiaCoordinator, device_id: int) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=coordinator.data[device_id]["name"],
            manufacturer="Entia",
        )

    @property
    def available(self) -> bool:
        """Return True if the device is present in the latest coordinator data."""
        return super().available and self._device_id in self.coordinator.data

    def _temp(self, attribute_id: int) -> float | None:
        """Return a scaled temperature attribute, or None if absent."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        raw = device["attributes"].get(attribute_id)
        if raw is None:
            return None
        return raw / TEMP_SCALE

    @property
    def current_temperature(self) -> float | None:
        """Return the current room temperature in °C."""
        return self._temp(ATTR_HMI_INSIDE_TEMP)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature in °C."""
        return self._temp(ATTR_HMI_TARGET_TEMP)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HMI_TARGET_TEMP, round(temperature * TEMP_SCALE)
        )
        await self.coordinator.async_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode.

        Only HEAT is supported for now; mode switching will be added once the
        device's HVAC-mode attribute (1107) value mapping is confirmed.
        """
