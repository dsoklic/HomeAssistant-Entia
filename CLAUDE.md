# Entia Integration

Integration for the Entia smart home platform at `https://api.entia.si/`.

## API overview

Authentication: `POST /login` → JWT bearer token. If a request is rejected with 401 or 403 (e.g. the server restarted after an outage and no longer accepts the old token), the client logs in again once and retries; a 401/403 from `/login` itself, or on the retry, raises `AuthError`, which the coordinator turns into `ConfigEntryAuthFailed` (permanent, handled by the reauth flow). Requests time out after 30 s; timeouts and a login response without a token raise `CannotConnect`.

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
| 1107 | HMI (climate) | HVAC mode: 0=off, 1=cool, 2=heat; writable |
| 3701 | HRV (ventilation) | Mode: 0=pass-through (bypass), 1=heat recovery; writable |
| 3702 | HRV (ventilation) | Fan speed: 0=off, 1=low, 2=medium, 3=high; writable |
| 2101 | Heating output (`device_type_id 2100`, one per room) | Valve state: 1=open (actively heating), 0=closed |

### Architecture
`EntiaWsClient` (`client/ws_client.py`) connects via aiohttp WebSocket, reconnects with exponential backoff (2–60 s), and calls `EntiaCoordinator._on_ws_event()` on each `attribute_event`. A rejected handshake drops the cached token (`invalidate_token()`) so the next attempt logs in again. After any reconnect following a drop or failure it calls `EntiaCoordinator._on_ws_reconnect()`, which requests an immediate REST refresh to catch up on missed events. The coordinator merges the single attribute change into a shallow copy of its data and calls `async_set_updated_data()` to immediately notify all entities.

REST polling (5-minute fallback) handles initial load and any events missed during reconnection.

## Coordinator update cycle

Each 5-minute fallback poll makes two requests:
1. `GET /flat` → build `{device_id: label}` map via `_build_label_map()`
2. `GET /flat/device` → device states with inline attributes

Lights are identified by the presence of `attribute_id 401` in their attributes dict. Climate (per-room heating) entities are identified by the presence of both `1103` (inside temp) and `1105` (target temp), i.e. the HMI device (`device_type_id 1100`). The climate entity exposes current + target temperature and HVAC mode (off/heat/cool via attribute 1107: 0=off, 1=cool, 2=heat), with `hvac_action`. `hvac_action` comes from the valve attribute `2101` on the device in the same `room_id` (open → heating/cooling, closed → idle); if a room has no such device it is estimated from current vs target temperature. The coordinator keeps each device's `room_id` for this. Fan-speed (1106) control is still deferred until its value mapping is confirmed.

The heat recovery ventilation unit (identified by attribute `3702`) is a second climate entity, `EntiaHrvClimate`, that can only blow air: HVAC modes off/fan_only (speed 0 = off), fan modes low/medium/high (3702), and presets heat_recovery/pass_through (3701). Turning it on restores the last speed seen running (default low). There are no separate fan or select entities.

## Config flow

Unique ID is the username (no flat-level ID is exposed by the API). Title is `Entia ({username})`.
Connectivity is verified by calling `authenticate()` + `get_flat()` before creating the entry.
Reauth (`reauth_confirm`) asks only for the password, verifies it the same way, then updates the entry and reloads it.
