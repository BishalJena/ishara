"""In-memory stand-ins for the call WebSocket and the V6 session layer.

Built only from `app/protocol.py` models, so the tools can be tested before the real
routes exist.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Collection, Sequence
from contextlib import asynccontextmanager

import httpx

from app.protocol import (
    AppMessage,
    ApproveMessage,
    CallState,
    CaptionMessage,
    ChipsMessage,
    DraftMessage,
    DraftSource,
    EndMessage,
    ErrorMessage,
    NotDeliveredMessage,
    ServerMessage,
    SpokenMessage,
    StartCallRequest,
    StatusMessage,
    StopMessage,
    app_message_adapter,
)
from tools.app_client import AppSession, pump
from tools.voice_checks import Observer

Responder = Callable[[AppMessage], list[ServerMessage | None]]


class FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakeTransport:
    """Records what the app sends; replies come from `push` or an optional responder.
    Pushing None closes the socket like a normal server close."""

    def __init__(self, responder: Responder | None = None) -> None:
        self.raw_sent: list[str] = []
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()
        self._responder = responder

    async def send_text(self, data: str) -> None:
        self.raw_sent.append(data)
        if self._responder:
            for reply in self._responder(app_message_adapter.validate_json(data)):
                self.push(reply)

    async def receive_text(self) -> str | None:
        return await self.inbox.get()

    def push(self, message: ServerMessage | None) -> None:
        self.inbox.put_nowait(None if message is None else message.model_dump_json())

    @property
    def sent(self) -> list[AppMessage]:
        return [app_message_adapter.validate_json(raw) for raw in self.raw_sent]


def template_text(chips: Sequence[str]) -> str:
    return " ".join(chips).capitalize() + "."


class FakeBackend:
    """Single-use approvals; each spoken reply is followed by the next receptionist
    caption. Approvals whose 0-based index is in `undeliverable` get `not_delivered`."""

    def __init__(self, captions: Sequence[str] = (), undeliverable: Collection[int] = ()) -> None:
        self.captions = list(captions)
        self.undeliverable = set(undeliverable)
        self.claimed: set[str] = set()
        self.approvals = 0

    def respond(self, message: AppMessage) -> list[ServerMessage | None]:
        match message:
            case ChipsMessage(turn_id=turn_id, chips=chips) if chips:
                return [
                    DraftMessage(
                        turn_id=turn_id, text=template_text(chips), source=DraftSource.TEMPLATE
                    )
                ]
            case ApproveMessage(turn_id=turn_id) if turn_id in self.claimed:
                return [ErrorMessage(code="already_approved", message="turn already used")]
            case ApproveMessage(turn_id=turn_id):
                self.claimed.add(turn_id)
                index, self.approvals = self.approvals, self.approvals + 1
                if index in self.undeliverable:
                    return [NotDeliveredMessage(turn_id=turn_id, reason="callee speaking")]
                replies: list[ServerMessage | None] = [
                    StatusMessage(state=CallState.SPEAKING),
                    SpokenMessage(turn_id=turn_id),
                    StatusMessage(state=CallState.IN_CALL),
                ]
                if self.captions:
                    replies.append(CaptionMessage(text=self.captions.pop(0), at=0.0))
                return replies
            case StopMessage():
                return [StatusMessage(state=CallState.IN_CALL)]
            case EndMessage():
                return [StatusMessage(state=CallState.ENDED), None]
        return []


@asynccontextmanager
async def running(
    session: AppSession, transport: FakeTransport
) -> AsyncIterator[list[tuple[ServerMessage, list[str]]]]:
    """Run the pump in the background; yields the (message, notices) log."""
    log: list[tuple[ServerMessage, list[str]]] = []
    task = asyncio.create_task(pump(transport, session, lambda m, n: log.append((m, n))))
    try:
        yield log
    finally:
        transport.push(None)
        await task


async def drain(transport: FakeTransport) -> None:
    """Let the pump handle everything queued so far."""
    for _ in range(50):
        await asyncio.sleep(0)
        if transport.inbox.empty():
            break
    for _ in range(5):
        await asyncio.sleep(0)


def mock_backend_client(status: int = 200, call_id: str = "call-secret-1") -> httpx.AsyncClient:
    """httpx client whose POST /calls answers like the session layer (or refuses)."""

    def handler(request: httpx.Request) -> httpx.Response:
        StartCallRequest.model_validate_json(request.content)
        return httpx.Response(status, json={"call_id": call_id, "state": "dialing"})

    return httpx.AsyncClient(base_url="http://backend", transport=httpx.MockTransport(handler))


class FakeSockets:
    """`open_socket` stand-in: records which call id was opened, yields one transport."""

    def __init__(self, responder: Responder | None) -> None:
        self.transport = FakeTransport(responder)
        self.opened: list[str] = []

    @asynccontextmanager
    async def open(self, call_id: str) -> AsyncIterator[FakeTransport]:
        self.opened.append(call_id)
        yield self.transport


class ScriptedObserver:
    """Answers prompts in order; Enter prompts get "" and may trigger a side effect."""

    def __init__(self, answers: list[str], on_enter: Callable[[str], None] | None = None) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []
        self.out: list[str] = []
        self.on_enter = on_enter or (lambda _: None)

    async def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if prompt.endswith("[Enter] "):
            self.on_enter(prompt)
            return ""
        return self.answers.pop(0)

    def observer(self) -> Observer:
        return Observer(ask=self.ask, out=self.out.append)
