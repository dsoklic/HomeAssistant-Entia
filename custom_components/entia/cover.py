"""Entia cover entities."""

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_BLIND_MOVING, ATTR_BLIND_POSITION, BLIND_TILT_RANGE, DOMAIN
from .coordinator import EntiaConfigEntry, EntiaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntiaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Entia cover entities from a config entry."""
    coordinator: EntiaCoordinator = entry.runtime_data
    async_add_entities(
        EntiaCover(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if ATTR_BLIND_POSITION in device["attributes"]
    )


class EntiaCover(CoordinatorEntity[EntiaCoordinator], CoverEntity):
    """Representation of an Entia window blind."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )

    def __init__(self, coordinator: EntiaCoordinator, device_id: int) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_cover"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=coordinator.data[device_id]["name"],
            manufacturer="Entia",
        )
        self._base_api_position: int = coordinator.data[device_id]["attributes"][
            ATTR_BLIND_POSITION
        ]
        self._tilt_position: int = 0
        self._last_moved_down: bool = True
        self._pending_api_value: int | None = None

    @property
    def available(self) -> bool:
        """Return True if the device is present in the latest coordinator data."""
        return super().available and self._device_id in self.coordinator.data

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=fully open)."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        raw = device["attributes"].get(ATTR_BLIND_POSITION)
        if raw is None:
            return None
        return 100 - raw  # API is inverted: 0=open, 100=closed

    @property
    def current_cover_tilt_position(self) -> int:
        """Return current tilt position (0=slats pointing down, 100=slats level)."""
        return self._tilt_position

    @property
    def is_closed(self) -> bool | None:
        """Return True if the cover is fully closed."""
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        self._pending_api_value = 0
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_BLIND_POSITION, 0
        )
        self._base_api_position = 0
        self._last_moved_down = False
        self._tilt_position = 0
        await self.coordinator.async_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        self._pending_api_value = 100
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_BLIND_POSITION, 100
        )
        self._base_api_position = 100
        self._last_moved_down = True
        self._tilt_position = 0
        await self.coordinator.async_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        api_value = 100 - kwargs[ATTR_POSITION]
        if api_value != self._base_api_position:
            self._last_moved_down = api_value > self._base_api_position
        self._pending_api_value = api_value
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_BLIND_POSITION, api_value
        )
        self._base_api_position = api_value
        self._tilt_position = 0
        await self.coordinator.async_refresh()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Tilt the slats to the given position (0=pointing down, 100=level)."""
        tilt = kwargs[ATTR_TILT_POSITION]
        offset = round(tilt / 100 * BLIND_TILT_RANGE)
        sign = -1 if self._last_moved_down else 1
        api_value = max(0, min(100, self._base_api_position + sign * offset))
        self._pending_api_value = api_value
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_BLIND_POSITION, api_value
        )
        self._tilt_position = tilt
        await self.coordinator.async_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Resync derived tilt state when position changes externally."""
        device = self.coordinator.data.get(self._device_id)
        if device is not None:
            attrs = device["attributes"]
            new_raw = attrs.get(ATTR_BLIND_POSITION)
            is_moving = bool(attrs.get(ATTR_BLIND_MOVING, 0))
            if new_raw is not None and not is_moving:
                if (
                    self._pending_api_value is not None
                    and new_raw == self._pending_api_value
                ):
                    self._pending_api_value = None
                else:
                    sign = -1 if self._last_moved_down else 1
                    delta = (new_raw - self._base_api_position) * sign
                    if 0 <= delta <= BLIND_TILT_RANGE:
                        self._tilt_position = round(delta / BLIND_TILT_RANGE * 100)
                    else:
                        self._last_moved_down = new_raw > self._base_api_position
                        self._base_api_position = new_raw
                        self._tilt_position = 0
        super()._handle_coordinator_update()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Level the slats (parallel = max light)."""
        await self.async_set_cover_tilt_position(**{ATTR_TILT_POSITION: 100})

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Return slats to base position (pointing down)."""
        await self.async_set_cover_tilt_position(**{ATTR_TILT_POSITION: 0})
