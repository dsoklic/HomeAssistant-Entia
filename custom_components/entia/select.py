"""Entia heat recovery ventilation mode select entities."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_HRV_MODE, DOMAIN, HRV_MODE_HEAT_RECOVERY, HRV_MODE_PASS_THROUGH
from .coordinator import EntiaConfigEntry, EntiaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntiaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Entia HRV mode select entities from a config entry."""
    coordinator: EntiaCoordinator = entry.runtime_data
    async_add_entities(
        EntiaHrvModeSelect(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if ATTR_HRV_MODE in device["attributes"]
    )


class EntiaHrvModeSelect(CoordinatorEntity[EntiaCoordinator], SelectEntity):
    """Representation of an Entia HRV operating mode selector."""

    _attr_has_entity_name = True
    _attr_translation_key = "ventilation_mode"
    _attr_options = [HRV_MODE_PASS_THROUGH, HRV_MODE_HEAT_RECOVERY]

    def __init__(self, coordinator: EntiaCoordinator, device_id: int) -> None:
        """Initialize the mode select."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_mode"
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
    def current_option(self) -> str | None:
        """Return the current operating mode."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        value = device["attributes"].get(ATTR_HRV_MODE, 0)
        return HRV_MODE_HEAT_RECOVERY if value == 1 else HRV_MODE_PASS_THROUGH

    async def async_select_option(self, option: str) -> None:
        """Change the operating mode."""
        value = 1 if option == HRV_MODE_HEAT_RECOVERY else 0
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HRV_MODE, value
        )
        await self.coordinator.async_refresh()
