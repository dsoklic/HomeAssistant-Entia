# Entia Home Assistant Integration

A custom integration for the [Entia](https://entia.si/) smart home platform.

## Supported entities

| Platform | Description |
|---|---|
| `light` | On/off control for Entia lights |
| `cover` | Blind position and tilt control |
| `fan` | Heat recovery ventilation units |
| `sensor` | Temperature sensors |
| `select` | Mode/setting selectors |

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

The integration re-authenticates automatically on token expiry.

## Running tests

Tests depend on the Home Assistant custom component test framework:

```bash
pip install pytest-homeassistant-custom-component
pytest tests/
```
