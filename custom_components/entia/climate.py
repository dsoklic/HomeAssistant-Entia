"""Entia climate (per-room heating) entities."""

from typing import Any

from homeassistant.components.climate import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_HEATING_VALVE,
    ATTR_HMI_HVAC_MODE,
    ATTR_HMI_INSIDE_TEMP,
    ATTR_HMI_TARGET_TEMP,
    ATTR_HRV_MODE,
    ATTR_HRV_SPEED,
    DOMAIN,
    HMI_MAX_TEMP,
    HMI_MIN_TEMP,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    HRV_MODE_HEAT_RECOVERY,
    HRV_MODE_PASS_THROUGH,
    TEMP_SCALE,
)
from .coordinator import EntiaConfigEntry, EntiaCoordinator

# Entia HMI_HVAC_MODE (attribute 1107) value <-> Home Assistant mode.
_VALUE_TO_HVAC_MODE: dict[int, HVACMode] = {
    HVAC_MODE_OFF: HVACMode.OFF,
    HVAC_MODE_COOL: HVACMode.COOL,
    HVAC_MODE_HEAT: HVACMode.HEAT,
}
_HVAC_MODE_TO_VALUE: dict[HVACMode, int] = {
    mode: value for value, mode in _VALUE_TO_HVAC_MODE.items()
}
# Action while the room's valve is open; a closed valve means idle.
_VALUE_TO_ACTIVE_ACTION: dict[int, HVACAction] = {
    HVAC_MODE_COOL: HVACAction.COOLING,
    HVAC_MODE_HEAT: HVACAction.HEATING,
}

# Entia HRV_SPEED (attribute 3702) value <-> Home Assistant fan mode; 0 = off.
_SPEED_TO_FAN_MODE: dict[int, str] = {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH}
_FAN_MODE_TO_SPEED: dict[str, int] = {
    mode: speed for speed, mode in _SPEED_TO_FAN_MODE.items()
}
# Entia HRV_MODE (attribute 3701) value <-> preset.
_VALUE_TO_HRV_PRESET: dict[int, str] = {
    0: HRV_MODE_PASS_THROUGH,
    1: HRV_MODE_HEAT_RECOVERY,
}
_HRV_PRESET_TO_VALUE: dict[str, int] = {
    preset: value for value, preset in _VALUE_TO_HRV_PRESET.items()
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntiaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Entia climate entities from a config entry."""
    coordinator: EntiaCoordinator = entry.runtime_data
    entities: list[ClimateEntity] = []
    for device_id, device in coordinator.data.items():
        attributes = device["attributes"]
        if ATTR_HMI_INSIDE_TEMP in attributes and ATTR_HMI_TARGET_TEMP in attributes:
            entities.append(EntiaClimate(coordinator, device_id))
        if ATTR_HRV_SPEED in attributes:
            entities.append(EntiaHrvClimate(coordinator, device_id))
    async_add_entities(entities)


class EntiaClimate(CoordinatorEntity[EntiaCoordinator], ClimateEntity):
    """Representation of an Entia per-room heating controller (HMI)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False
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

    def _attr(self, attribute_id: int) -> Any:
        """Return a raw attribute value, or None if the device/attr is absent."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        return device["attributes"].get(attribute_id)

    def _valve_open(self) -> bool | None:
        """Return the room's valve state, or None if no valve device is known."""
        device = self.coordinator.data.get(self._device_id)
        if device is None or device.get("room_id") is None:
            return None
        for other in self.coordinator.data.values():
            if (
                other.get("room_id") == device["room_id"]
                and ATTR_HEATING_VALVE in other["attributes"]
            ):
                return bool(other["attributes"][ATTR_HEATING_VALVE])
        return None

    def _temp(self, attribute_id: int) -> float | None:
        """Return a scaled temperature attribute, or None if absent."""
        raw = self._attr(attribute_id)
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

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        raw = self._attr(ATTR_HMI_HVAC_MODE)
        if raw is None:
            return None
        return _VALUE_TO_HVAC_MODE.get(raw, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the device is currently doing."""
        raw = self._attr(ATTR_HMI_HVAC_MODE)
        if raw is None:
            return None
        active_action = _VALUE_TO_ACTIVE_ACTION.get(raw)
        if active_action is None:
            return HVACAction.OFF
        valve_open = self._valve_open()
        if valve_open is None:
            # No valve device in this room: estimate from the temperatures.
            current = self.current_temperature
            target = self.target_temperature
            if current is None or target is None:
                return None
            if raw == HVAC_MODE_HEAT:
                valve_open = current < target
            else:
                valve_open = current > target
        return active_action if valve_open else HVACAction.IDLE

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
        """Set a new HVAC mode."""
        value = _HVAC_MODE_TO_VALUE[hvac_mode]
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HMI_HVAC_MODE, value
        )
        await self.coordinator.async_refresh()

    async def async_turn_on(self) -> None:
        """Turn the heating on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the heating off."""
        await self.async_set_hvac_mode(HVACMode.OFF)


class EntiaHrvClimate(CoordinatorEntity[EntiaCoordinator], ClimateEntity):
    """Representation of an Entia heat recovery ventilation unit.

    The unit can only move air, so it is exposed as a fan-only thermostat: the
    fan mode is the speed and the preset is heat recovery vs. pass-through.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "ventilation"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY]
    _attr_fan_modes = list(_FAN_MODE_TO_SPEED)
    _attr_preset_modes = [HRV_MODE_HEAT_RECOVERY, HRV_MODE_PASS_THROUGH]
    _attr_supported_features = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: EntiaCoordinator, device_id: int) -> None:
        """Initialize the ventilation entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        # Speed to restore on turn on; updated whenever the unit is seen running.
        self._last_speed = _FAN_MODE_TO_SPEED[FAN_LOW]
        self._attr_unique_id = f"{DOMAIN}_{device_id}_ventilation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=coordinator.data[device_id]["name"],
            manufacturer="Entia",
        )

    @property
    def available(self) -> bool:
        """Return True if the device is present in the latest coordinator data."""
        return super().available and self._device_id in self.coordinator.data

    def _attr(self, attribute_id: int) -> Any:
        """Return a raw attribute value, or None if the device/attr is absent."""
        device = self.coordinator.data.get(self._device_id)
        if device is None:
            return None
        return device["attributes"].get(attribute_id)

    def _speed(self) -> int | None:
        """Return the raw speed, remembering it if the unit is running."""
        speed = self._attr(ATTR_HRV_SPEED)
        if speed in _SPEED_TO_FAN_MODE:
            self._last_speed = speed
        return speed

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return fan-only while the unit is running, otherwise off."""
        speed = self._speed()
        if speed is None:
            return None
        return HVACMode.OFF if speed == 0 else HVACMode.FAN_ONLY

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the unit is currently doing."""
        speed = self._speed()
        if speed is None:
            return None
        return HVACAction.OFF if speed == 0 else HVACAction.FAN

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan speed (the last one used while off)."""
        speed = self._speed()
        if speed is None:
            return None
        return _SPEED_TO_FAN_MODE.get(speed, _SPEED_TO_FAN_MODE[self._last_speed])

    @property
    def preset_mode(self) -> str | None:
        """Return heat recovery or pass-through."""
        raw = self._attr(ATTR_HRV_MODE)
        if raw is None:
            return None
        return _VALUE_TO_HRV_PRESET.get(raw, HRV_MODE_PASS_THROUGH)

    async def _async_set_speed(self, speed: int) -> None:
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HRV_SPEED, speed
        )
        await self.coordinator.async_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the unit off, or on at the last used speed."""
        await self._async_set_speed(0 if hvac_mode == HVACMode.OFF else self._last_speed)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed; this also turns the unit on."""
        await self._async_set_speed(_FAN_MODE_TO_SPEED[fan_mode])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between heat recovery and pass-through."""
        await self.coordinator.client.set_device_attribute(
            self._device_id, ATTR_HRV_MODE, _HRV_PRESET_TO_VALUE[preset_mode]
        )
        await self.coordinator.async_refresh()

    async def async_turn_on(self) -> None:
        """Turn the ventilation on."""
        await self.async_set_hvac_mode(HVACMode.FAN_ONLY)

    async def async_turn_off(self) -> None:
        """Turn the ventilation off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
