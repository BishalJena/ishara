"""Network edge of the app tools: `POST /calls` over httpx and the call WebSocket."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosedOK

from app.protocol import Purpose, StartCallRequest, StartCallResponse

WS_PING_INTERVAL_S = 20  # Heroku's router drops idle sockets; PLAN §3 asks for pings.


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def call_socket_url(base_url: str, call_id: str) -> str:
    """http(s)://host[/prefix] -> ws(s)://host[/prefix]/calls/{call_id}/ws"""
    parts = urlsplit(base_url)
    schemes = {"http": "ws", "https": "wss"}
    if parts.scheme not in schemes:
        raise ValueError(f"base URL must be http or https, got {parts.scheme!r}")
    path = f"{parts.path.rstrip('/')}/calls/{quote(call_id, safe='')}/ws"
    return urlunsplit((schemes[parts.scheme], parts.netloc, path, "", ""))


async def start_call(
    client: httpx.AsyncClient, contact_id: str, purpose: Purpose = "doctor_appointment"
) -> StartCallResponse:
    """POST /calls. `client` carries the base URL and bearer header. Raises
    httpx.HTTPStatusError on a refused call (unknown contact, bad token)."""
    body = StartCallRequest(contact_id=contact_id, purpose=purpose)
    response = await client.post("/calls", json=body.model_dump())
    response.raise_for_status()
    return StartCallResponse.model_validate_json(response.content)


class WebSocketTransport:
    def __init__(self, connection: ClientConnection) -> None:
        self._connection = connection

    async def send_text(self, data: str) -> None:
        await self._connection.send(data)

    async def receive_text(self) -> str | None:
        try:
            frame = await self._connection.recv()
        except ConnectionClosedOK:
            return None
        if isinstance(frame, bytes):
            raise ValueError("backend sent a binary frame; the call protocol is JSON text")
        return frame


@asynccontextmanager
async def open_call_socket(
    base_url: str, call_id: str, token: str
) -> AsyncIterator[WebSocketTransport]:
    async with connect(
        call_socket_url(base_url, call_id),
        additional_headers=auth_headers(token),
        ping_interval=WS_PING_INTERVAL_S,
    ) as connection:
        yield WebSocketTransport(connection)
