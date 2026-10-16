"""Test the Entia WebSocket client's reconnect behaviour."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp

from homeassistant.components.entia.api import CannotConnect
from homeassistant.components.entia.client.ws_client import EntiaWsClient

HANDSHAKE_REJECTED = aiohttp.WSServerHandshakeError(
    request_info=Mock(real_url="wss://ws.entia.si/"), history=(), status=401
)


@asynccontextmanager
async def _connection():
    """A WebSocket connection that closes without sending anything."""
    ws = MagicMock()
    ws.__aiter__.return_value = []
    yield ws


def _make_client(*attempts) -> tuple[EntiaWsClient, MagicMock, Mock]:
    """Build a client whose connection attempts fail or succeed in the given order.

    Each attempt is an exception to raise or None for a successful connection.
    """
    api = MagicMock()
    api.get_token = AsyncMock(return_value="token")
    queue = list(attempts)

    def ws_connect(*args, **kwargs):
        attempt = queue.pop(0)
        if attempt is not None:
            raise attempt
        return _connection()

    api.session.ws_connect = Mock(side_effect=ws_connect)
    on_reconnect = Mock()
    client = EntiaWsClient(api, Mock(), on_reconnect)
    return client, api, on_reconnect


async def _run(client: EntiaWsClient, cycles: int) -> list[float]:
    """Run listen() for the given number of connection cycles; return the backoff delays."""
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) >= cycles:
            client.close()

    with patch(
        "homeassistant.components.entia.client.ws_client.asyncio.sleep",
        side_effect=fake_sleep,
    ):
        await client.listen()
    return delays


async def test_rejected_handshake_drops_token() -> None:
    """A refused handshake forces a fresh login before the next attempt."""
    client, api, _ = _make_client(HANDSHAKE_REJECTED)

    await _run(client, cycles=1)

    api.invalidate_token.assert_called_once()


async def test_reconnect_after_failure_notifies() -> None:
    """Reconnecting after a failure asks the coordinator to catch up."""
    client, _, on_reconnect = _make_client(aiohttp.ClientError(), None)

    await _run(client, cycles=2)

    on_reconnect.assert_called_once()


async def test_first_connection_does_not_notify() -> None:
    """The initial connection needs no catch-up refresh."""
    client, _, on_reconnect = _make_client(None)

    await _run(client, cycles=1)

    on_reconnect.assert_not_called()


async def test_login_outage_keeps_retrying() -> None:
    """A login failure during an outage is retried instead of ending the listener."""
    client, api, on_reconnect = _make_client(None)
    api.get_token.side_effect = [CannotConnect("down"), "token"]

    await _run(client, cycles=2)

    api.session.ws_connect.assert_called_once()
    on_reconnect.assert_called_once()


async def test_backoff_is_capped() -> None:
    """Repeated failures back off, but never longer than a minute."""
    client, _, _ = _make_client(*[aiohttp.ClientError()] * 8)

    delays = await _run(client, cycles=8)

    assert delays == [2, 4, 8, 16, 32, 60, 60, 60]


async def test_drop_after_connect_resets_backoff() -> None:
    """A connection that was established resets the backoff to the minimum."""
    client, _, _ = _make_client(aiohttp.ClientError(), aiohttp.ClientError(), None)

    delays = await _run(client, cycles=3)

    assert delays == [2, 4, 2]
