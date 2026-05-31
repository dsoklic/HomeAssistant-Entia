"""Constants for the Entia integration."""

DOMAIN = "entia"
ATTR_LIGHT_STATE = 401
ATTR_BLIND_POSITION = 601
ATTR_BLIND_MOVING = 603  # 1 = moving, 0 = idle
BLIND_TILT_RANGE = (
    3  # API units: 0 = slats pointing down, 3 = slats parallel (max light)
)
ATTR_TEMPERATURE = 801
ATTR_HRV_MODE = 3701  # 0=pass-through, 1=heat_recovery
ATTR_HRV_SPEED = 3702  # 0=off, 1=low, 2=medium, 3=high

HRV_MODE_PASS_THROUGH = "pass_through"
HRV_MODE_HEAT_RECOVERY = "heat_recovery"
