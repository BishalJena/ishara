"""Start a call, stream its events to the terminal and always hang up afterwards."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.config import Settings
from app.protocol import ServerMessage
from tools.app_client import AppSession, Transport, pump
from tools.connection import start_call
from tools.console import format_event

OpenSocket = Callable[[str], AbstractAsyncContextManager[Transport]]
HANG_UP_TIMEOUT_S = 15.0
UNCONFIRMED_END = "! could not confirm the call ended; check it in the Bolna dashboard now"


class MissingTokenError(Exception):
    """APP_TOKEN is not set in the environment or the repo-root .env."""


def app_token(settings: Settings) -> str:
    if settings.app_token is None:
        raise MissingTokenError("APP_TOKEN is not set (environment or repo-root .env)")
    return settings.app_token.get_secret_value()


@dataclass(frozen=True)
class LiveCall:
    """`call_id` is only for scrubbing results; never print or save it."""

    session: AppSession
    call_id: str


@asynccontextmanager
async def live_call(
    client: httpx.AsyncClient,
    contact_id: str,
    open_socket: OpenSocket,
    out: Callable[[str], None] = print,
    hang_up_timeout: float = HANG_UP_TIMEOUT_S,
) -> AsyncIterator[LiveCall]:
    """POST /calls, connect the socket and print every event. On exit, hang up even
    if the body raised, so an aborted run never leaves a paid call running."""
    started = await start_call(client, contact_id)
    out(f"call requested ({started.state.value})")
    async with open_socket(started.call_id) as transport:
        session = AppSession(transport)

        def show(message: ServerMessage, notices: list[str]) -> None:
            out(format_event(message, notices, session.turn_label, datetime.now()))

        reader = asyncio.create_task(pump(transport, session, show))
        try:
            yield LiveCall(session=session, call_id=started.call_id)
        finally:
            if not await session.hang_up(hang_up_timeout):
                out(UNCONFIRMED_END)
            if not reader.done():
                reader.cancel()
            with suppress(asyncio.CancelledError):
                await reader
