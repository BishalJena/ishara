from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from app.protocol import EndMessage
from tests.conftest import make_settings
from tests.fakes import FakeBackend, FakeTransport, Responder
from tools.call_runner import (
    UNCONFIRMED_END,
    MissingTokenError,
    app_token,
    live_call,
)


def _client(status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["contact_id"] == "clinic"
        return httpx.Response(status, json={"call_id": "call-secret-1", "state": "dialing"})

    return httpx.AsyncClient(base_url="http://backend", transport=httpx.MockTransport(handler))


class Sockets:
    def __init__(self, responder: Responder | None) -> None:
        self.transport = FakeTransport(responder)
        self.opened: list[str] = []

    @asynccontextmanager
    async def open(self, call_id: str) -> AsyncIterator[FakeTransport]:
        self.opened.append(call_id)
        yield self.transport


async def test_live_call_connects_to_the_started_call_and_hangs_up() -> None:
    sockets = Sockets(FakeBackend().respond)
    out: list[str] = []
    async with _client() as client, live_call(client, "clinic", sockets.open, out.append) as call:
        assert call.call_id == "call-secret-1"
    assert sockets.opened == ["call-secret-1"]
    assert sockets.transport.sent == [EndMessage()]
    assert out[0] == "call requested (dialing)"
    assert out[-1].endswith("status        ended")
    assert not any("call-secret-1" in line for line in out)


async def test_live_call_hangs_up_even_when_the_body_fails() -> None:
    sockets = Sockets(FakeBackend().respond)
    async with _client() as client:
        with pytest.raises(RuntimeError, match="boom"):
            async with live_call(client, "clinic", sockets.open, lambda _: None):
                raise RuntimeError("boom")
    assert sockets.transport.sent == [EndMessage()]


async def test_unconfirmed_end_is_called_out() -> None:
    sockets = Sockets(None)
    out: list[str] = []
    async with (
        _client() as client,
        live_call(client, "clinic", sockets.open, out.append, hang_up_timeout=0.01),
    ):
        pass
    assert out[-1] == UNCONFIRMED_END


async def test_refused_call_never_opens_a_socket() -> None:
    sockets = Sockets(None)
    async with _client(status=403) as client:
        with pytest.raises(httpx.HTTPStatusError):
            async with live_call(client, "clinic", sockets.open, lambda _: None):
                pytest.fail("body must not run")
    assert sockets.opened == []


def test_app_token_read_from_settings_or_refused() -> None:
    assert app_token(make_settings(app_token="tok")) == "tok"
    with pytest.raises(MissingTokenError):
        app_token(make_settings(app_token=None))
