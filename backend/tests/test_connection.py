from __future__ import annotations

import json

import httpx
import pytest
from websockets.asyncio.server import ServerConnection, serve

from app.protocol import CallState, StartCallResponse
from tools.connection import auth_headers, call_socket_url, open_call_socket, start_call


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("http://127.0.0.1:8000", "ws://127.0.0.1:8000/calls/c1/ws"),
        ("https://x.example.com/", "wss://x.example.com/calls/c1/ws"),
        ("https://x.example.com/api", "wss://x.example.com/api/calls/c1/ws"),
    ],
)
def test_socket_url_maps_scheme_and_path(base: str, expected: str) -> None:
    assert call_socket_url(base, "c1") == expected


def test_socket_url_escapes_call_id_and_rejects_other_schemes() -> None:
    assert call_socket_url("http://h", "a/b?c").endswith("/calls/a%2Fb%3Fc/ws")
    with pytest.raises(ValueError, match="http or https"):
        call_socket_url("ftp://h", "c1")


async def test_start_call_posts_contact_and_purpose_with_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"call_id": "c1", "state": "dialing"})

    async with httpx.AsyncClient(
        base_url="http://backend",
        headers=auth_headers("tok"),
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await start_call(client, "clinic")
    assert response == StartCallResponse(call_id="c1", state=CallState.DIALING)
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/calls"
    assert seen[0].headers["authorization"] == "Bearer tok"
    assert json.loads(seen[0].content) == {"contact_id": "clinic", "purpose": "doctor_appointment"}


async def test_start_call_raises_when_backend_refuses() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(403, json={"detail": "no"}))
    async with httpx.AsyncClient(base_url="http://backend", transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await start_call(client, "stranger")


async def test_call_socket_sends_bearer_and_exchanges_text_frames() -> None:
    seen: dict[str, object] = {}

    async def handler(connection: ServerConnection) -> None:
        seen["path"] = connection.request.path
        seen["auth"] = connection.request.headers["Authorization"]
        await connection.send('{"type":"status","state":"in_call"}')
        seen["received"] = await connection.recv()
        await connection.close()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with open_call_socket(f"http://127.0.0.1:{port}", "c1", "tok") as transport:
            assert await transport.receive_text() == '{"type":"status","state":"in_call"}'
            await transport.send_text('{"type":"end"}')
            assert await transport.receive_text() is None
    assert seen == {"path": "/calls/c1/ws", "auth": "Bearer tok", "received": '{"type":"end"}'}


async def test_binary_frame_is_a_protocol_error() -> None:
    async def handler(connection: ServerConnection) -> None:
        await connection.send(b"\x00")
        await connection.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with open_call_socket(f"http://127.0.0.1:{port}", "c1", "tok") as transport:
            with pytest.raises(ValueError, match="binary"):
                await transport.receive_text()
