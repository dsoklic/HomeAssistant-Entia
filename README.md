# Entia Home Assistant Integration

A custom integration for the [Entia](https://api.entia.si/) smart home platform.

## Supported entities

| Platform | Description |
|---|---|
| `light` | On/off control for Entia lights |
| `cover` | Blind position and tilt control |
| `fan` | Heat recovery ventilation units |
| `sensor` | Temperature sensors |
| `select` | Mode/setting selectors |

Real-time state updates are delivered via WebSocket (`wss://ws.entia.si`). A 5-minute REST polling fallback handles any events missed during reconnection.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** → ⋮ → **Custom repositories**.
3. Add `https://github.com/dsoklic/HomeAssistant-Entia` with category **Integration**.
4. Install **Entia** from HACS and restart Home Assistant.

### Manual

Copy the `custom_components/entia/` directory into your Home Assistant config directory under `custom_components/`, then restart Home Assistant.

## Configuration

Add the integration via **Settings → Devices & Services → Add integration → Entia**.

You will be prompted for:
- **Username** — your Entia account email
- **Password** — your Entia account password

Authentication uses a JWT bearer token obtained from `POST /login`. The integration re-authenticates automatically on token expiry.

## API

The integration communicates with `https://api.entia.si/`:

| Endpoint | Purpose |
|---|---|
| `POST /login` | Obtain JWT token |
| `GET /flat` | Flat/room/device structure with labels |
| `GET /flat/device` | Device list with current attribute values |
| `PUT /flat/device/{id}/attribute/{attrId}` | Set an attribute value |

### Attribute IDs

| ID | Device type | Meaning |
|---|---|---|
| 401 | Light | On/off state (1 = on, 0 = off) |
| 601 | Blind | Position (0 = open, 100 = closed) |
| 602 | Blind | Mirrors position during movement |
| 603 | Blind | Moving indicator (1 = moving, 0 = idle) |
| 801 | Sensor | Temperature raw value (÷ 2 → °C) |

## Running tests

Tests depend on the Home Assistant custom component test framework:

```bash
pip install pytest-homeassistant-custom-component
pytest tests/
```
