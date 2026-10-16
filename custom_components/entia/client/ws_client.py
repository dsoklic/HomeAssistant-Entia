"""Entia WebSocket client.

Connects to wss://ws.entia.si/?token=<jwt> and pushes attribute_event messages
as they arrive. No subscription is required — the server streams all events for
the authenticated flat automatically.
"""

import asyncio
from collections.abc import Callable
import json
import logging
from typing import Any

import aiohttp

from ..api import AuthError, CannotConnect, EntiaApiClient

WS_URL = "wss://ws.entia.si/"

_LOGGER = logging.getLogger(__name__)

_RECONNECT_DELAY_MIN = 2
_RECONNECT_DELAY_MAX = 60


class EntiaWsClient:
    """WebSocket client that delivers attribute_event callbacks to the coordinator."""

    def __init__(
        self,
        api_client: EntiaApiClient,
        on_event: Callable[[int, int, Any], None],
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        """Store the API client (for token and session) and the callbacks.

        on_reconnect is called when a connection is re-established after a
        failure, so events missed in between can be fetched over REST.
        """
        self._api = api_client
        self._on_event = on_event
        self._on_reconnect = on_reconnect
        self._running = False

    async def listen(self) -> None:
        """Connect and stream events, reconnecting on failure."""
        self._running = True
        delay = _RECONNECT_DELAY_MIN
        catch_up = False
        while self._running:
            try:
                token = await self._api.get_token()
                async with self._api.session.ws_connect(
                    f"{WS_URL}?token={token}",
                    heartbeat=30,
                ) as ws:
                    _LOGGER.debug("Entia WebSocket connected")
                    delay = _RECONNECT_DELAY_MIN
                    if catch_up and self._on_reconnect is not None:
                        self._on_reconnect()
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._handle_message(msg.data)
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
            except asyncio.CancelledError:
                return
            except aiohttp.WSServerHandshakeError as err:
                # After a server restart the old token may no longer be accepted.
                self._api.invalidate_token()
                _LOGGER.debug(
                    "WebSocket handshake rejected (%s); retry in %ss", err.status, delay
                )
            except (aiohttp.ClientError, CannotConnect, AuthError) as err:
                _LOGGER.debug(
                    "WebSocket connection error: %s; retry in %ss", err, delay
                )
            except Exception:
                _LOGGER.exception("Unexpected WebSocket error; retry in %ss", delay)
            # A dropped or failed connection may have missed events.
            catch_up = True

            if self._running:
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_DELAY_MAX)

        _LOGGER.debug("Entia WebSocket listener stopped")

    def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if msg.get("event") != "attribute_event":
            return
        data = msg.get("data", {})
        try:
            self._on_event(
                int(data["device_id"]),
                int(data["attribute_id"]),
                data["value"],
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.debug("Malformed attribute_event: %s", err)

    def close(self) -> None:
        """Signal the listen loop to stop reconnecting after the current cycle ends."""
        self._running = False
