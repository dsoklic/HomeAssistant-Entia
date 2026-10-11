# Entia Integration

Integration for the Entia smart home platform at `https://api.entia.si/`.

## API overview

Authentication: `POST /login` → JWT bearer token. The client re-authenticates once on 401 before raising `AuthError`.

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /flat` | Flat structure with device labels (see below) |
| `GET /flat/device` | Device list with current attribute values (see below) |
| `PUT /flat/device/{id}/attribute/{attrId}/rt` | Set attribute value, body `{"value": ...}` (the `/rt` suffix actuates the device and triggers the WebSocket broadcast) |

### `GET /flat` response shape
```json
{
  "flat": {
    "floors": [{
      "rooms": [{
        "id": 2978,
        "label": "Dnevna",
        "devices": [{"id": 42467, "label": "1.1 dnevna", "type": 4}]
      }]
    }]
  }
}
```
Device labels use HTML entities (e.g. `&#381;` = Ž). The coordinator decodes them with `html.unescape()`.
`type: 4` = light device. There is no flat-level `id` or `name` in the response.

### `GET /flat/device` response shape
```json
{
  "connected": 1,
  "timezone": "Europe/Ljubljana",
  "devices": [{"id": 42467, "device_type_id": 400, "room_id": 2978,
               "attributes": [{"id": 401, "timestamp": 1780034143, "value": 0}],
               "settings": [...]}]
}
```
Attributes are inline — no per-device requests needed. `attribute_id 401` = light on/off state (1 = on, 0 = off).

## WebSocket API

Real-time push updates via `wss://ws.entia.si/?token={jwt}` (token as query param, **not** a header).

No subscription message needed — the server streams all `attribute_event` messages for the flat immediately on connection.

```json
{"event": "attribute_event", "data": {"flat_id": 621, "device_id": 42519, "attribute_id": 601, "timestamp": 1780163836, "value": 98, "nvalue": 98}}
```

`value` is the raw attribute value (same scale as REST). `nvalue` mirrors `value` except for temperature where `nvalue = value / 2` (the actual °C).

### Known attribute IDs
| ID | Device type | Meaning |
|---|---|---|
| 401 | Light | On/off state (1=on, 0=off) |
| 601 | Blind | Position (0=open, 100=closed) |
| 602 | Blind | Mirrors position during movement |
| 603 | Blind | Moving indicator (1=moving, 0=idle) |
| 801 | Sensor | Temperature raw value (÷2 → °C) |
| 1103 | HMI (climate) | Inside/current temperature, raw (÷2 → °C) |
| 1104 | HMI (climate) | Outside temperature, raw (÷2 → °C) |
| 1105 | HMI (climate) | Target temperature, raw (÷2 → °C); writable |
| 1106 | HMI (climate) | Fan speed (value mapping not yet confirmed) |
| 1107 | HMI (climate) | HVAC mode (value mapping not yet confirmed) |

### Architecture
`EntiaWsClient` (`client/ws_client.py`) connects via aiohttp WebSocket, reconnects with exponential backoff (2–300 s), and calls `EntiaCoordinator._on_ws_event()` on each `attribute_event`. The coordinator merges the single attribute change into a shallow copy of its data and calls `async_set_updated_data()` to immediately notify all entities.

REST polling (5-minute fallback) handles initial load and any events missed during reconnection.

## Coordinator update cycle

Each 5-minute fallback poll makes two requests:
1. `GET /flat` → build `{device_id: label}` map via `_build_label_map()`
2. `GET /flat/device` → device states with inline attributes

Lights are identified by the presence of `attribute_id 401` in their attributes dict. Climate (per-room heating) entities are identified by the presence of both `1103` (inside temp) and `1105` (target temp), i.e. the HMI device (`device_type_id 1100`). The climate entity exposes current + target temperature with a fixed `HEAT` mode; HVAC-mode (1107) and fan (1106) control are deferred until their value mappings are confirmed.

## Config flow

Unique ID is the username (no flat-level ID is exposed by the API). Title is `Entia ({username})`.
Connectivity is verified by calling `authenticate()` + `get_flat()` before creating the entry.
