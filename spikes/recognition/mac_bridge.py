"""Mac fallback for the demo (PLAN A4): recognised signs become chips on the backend WebSocket.

`TurnState` owns the turn rules from PLAN §4 and holds no I/O, so the iOS app and this
bridge can be checked against the same behaviour. Nothing here speaks on its own: the
only path to an `approve` message is an explicit SEND or quick reply.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

SIGNS = ("hello", "thankyou", "yes", "no", "sorry", "doctor",
         "today", "tomorrow", "morning", "afternoon", "evening", "time")
MAX_CHIPS = 8  # backend ChipsMessage limit
QUICK_REPLIES = {
    "yes": "Yes.",
    "no": "No.",
    "wait": "Please wait a moment, I'm signing my reply.",
    "repeat": "Sorry, could you please repeat that?",
}

Result = str | None  # a sign from SIGNS, or None when recognition is unsure ("?")
Message = dict[str, object]


def new_turn_id() -> str:
    return uuid.uuid4().hex


class ChipLimit(ValueError):
    """The turn already holds MAX_CHIPS sendable chips."""


@dataclass(frozen=True)
class Draft:
    turn_id: str
    text: str
    source: str


@dataclass
class TurnState:
    """Chips, draft and approvals for one call. Methods return the message to send, or None."""

    new_id: Callable[[], str] = new_turn_id
    chips: list[Result] = field(default_factory=list)
    draft: Draft | None = None
    ended: bool = False
    undelivered: tuple[str, str] | None = None  # (turn_id, text) awaiting a manual re-SEND
    awaiting: dict[str, str] = field(default_factory=dict)  # approved turn_id -> text
    turn_id: str = ""

    def __post_init__(self) -> None:
        self.turn_id = self.turn_id or self.new_id()

    @property
    def sendable(self) -> list[str]:
        """Chips the backend may see; unsure entries stay local."""
        return [chip for chip in self.chips if chip is not None]

    def add(self, result: Result) -> Message | None:
        if result is not None and result not in SIGNS:
            raise ValueError(f"unknown sign {result!r}")
        if self.ended:
            return None
        if result is not None and len(self.sendable) >= MAX_CHIPS:
            raise ChipLimit(f"at most {MAX_CHIPS} chips per turn; remove one (x) or clear (c)")
        before = self.sendable
        self.chips.append(result)
        return self._chips_message(before)

    def remove_last(self) -> Message | None:
        if self.ended or not self.chips:
            return None
        before = self.sendable
        self.chips.pop()
        return self._chips_message(before)

    def clear(self) -> None:
        """Clear wipes the turn; late drafts for it are ignored because the id changes."""
        if not self.ended:
            self._new_turn()

    def on_draft(self, turn_id: str, text: str, source: str) -> Draft | None:
        if self.ended or turn_id != self.turn_id or not self.sendable:
            return None
        self.draft = Draft(turn_id, text, source)
        return self.draft

    def approve(self) -> Message | None:
        """SEND: the current turn's draft, else the text that was not delivered. Single use."""
        if self.ended:
            return None
        if self.draft is not None:  # on_draft only keeps drafts for the current turn
            text = self.draft.text
        elif self.undelivered is not None:
            text = self.undelivered[1]
        else:
            return None
        return self._approve(text)

    def quick_reply(self, name: str) -> Message | None:
        text = QUICK_REPLIES[name]
        if self.ended:
            return None
        self._new_turn()
        return self._approve(text)

    def on_spoken(self, turn_id: str) -> str | None:
        """Returns the delivered text. A late confirmation also cancels the pending re-SEND."""
        if self.undelivered is not None and self.undelivered[0] == turn_id:
            text, self.undelivered = self.undelivered[1], None
            return text
        return self.awaiting.pop(turn_id, None)

    def on_not_delivered(self, turn_id: str) -> str | None:
        """Remember the text for a manual re-SEND; never resend here."""
        text = self.awaiting.pop(turn_id, None)
        if text is not None and not self.ended:
            self.undelivered = (turn_id, text)
        return text

    def stop(self) -> Message | None:
        """STOP cancels unspoken output on the backend; it never queues anything new."""
        return None if self.ended else {"type": "stop"}

    def end(self) -> Message | None:
        if self.ended:
            return None
        self.on_ended()
        return {"type": "end"}

    def on_ended(self) -> None:
        """The call is over: wipe everything so nothing can be sent afterwards."""
        self.ended = True
        self.chips, self.draft, self.undelivered = [], None, None
        self.awaiting.clear()

    def _chips_message(self, before: list[str]) -> Message | None:
        after = self.sendable
        if after == before:
            return None
        self.draft = None  # the old draft no longer matches the chips
        return {"type": "chips", "turn_id": self.turn_id, "chips": after}

    def _approve(self, text: str) -> Message:
        message: Message = {"type": "approve", "turn_id": self.turn_id, "text": text}
        self.awaiting[self.turn_id] = text
        self.undelivered = None
        self._new_turn()
        return message

    def _new_turn(self) -> None:
        self.turn_id, self.chips, self.draft = self.new_id(), [], None


# ---- recognition sources ----


class RecognitionSource(Protocol):
    """One `Result` per finished sign segment; the stream ends when the source is done.

    A live recognizer (detector segments -> SignCLIP -> frozen cut-off) is just another
    source: yield the matched sign, or None when no reference is close enough.
    """

    def results(self) -> AsyncIterator[Result]: ...


class _End(Enum):
    DONE = 0  # sentinel that ends a stream


def parse_result(token: str) -> Result:
    token = token.strip().lower()
    if token == "?":
        return None
    if token not in SIGNS:
        raise ValueError(f"unknown sign {token!r}; use one of {', '.join(SIGNS)} or ?")
    return token


class ManualSource:
    """Signs typed in the terminal; the terminal loop feeds each parsed token."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Result | _End] = asyncio.Queue()

    def feed(self, result: Result) -> None:
        self._queue.put_nowait(result)

    def close(self) -> None:
        self._queue.put_nowait(_End.DONE)

    async def results(self) -> AsyncIterator[Result]:
        while (item := await self._queue.get()) is not _End.DONE:
            yield item


@dataclass(frozen=True)
class ReplaySource:
    """Scripted results for rehearsals: each step waits `delay` seconds, then yields."""

    steps: tuple[tuple[float, Result], ...]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    @classmethod
    def from_json(cls, text: str,
                  sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> ReplaySource:
        """`["hello", "?", null, {"sign": "doctor", "delay": 1.5}]`; "?" and null are unsure."""
        steps = []
        for item in json.loads(text):
            if isinstance(item, dict):
                if set(item) - {"sign", "delay"} or "sign" not in item:
                    raise ValueError(f"replay step needs 'sign' and optional 'delay': {item}")
                delay, sign = float(item.get("delay", 0)), item["sign"]
                if delay < 0:
                    raise ValueError(f"negative delay in {item}")
            else:
                delay, sign = 0.0, item
            steps.append((delay, None if sign is None else parse_result(sign)))
        return cls(tuple(steps), sleep)

    async def results(self) -> AsyncIterator[Result]:
        for delay, result in self.steps:
            if delay:
                await self.sleep(delay)
            yield result


class BlockingSource:
    """Runs a blocking iterator (webcam loop, model inference) off the event loop."""

    def __init__(self, make_iterator: Callable[[], Iterator[Result]]) -> None:
        self._make_iterator = make_iterator

    async def results(self) -> AsyncIterator[Result]:
        iterator = await asyncio.to_thread(self._make_iterator)
        while (item := await asyncio.to_thread(next, iterator, _End.DONE)) is not _End.DONE:
            yield item


# ---- backend client ----


class Transport(Protocol):
    """The slice of a websockets ClientConnection the bridge uses; tests pass a fake."""

    async def send(self, message: str) -> None: ...

    def __aiter__(self) -> AsyncIterator[str | bytes]: ...

    async def close(self) -> None: ...


HELP = (f"signs: {' '.join(SIGNS)}  (? = unsure, never sent)\n"
        "x remove last chip | c clear turn | s SEND draft | q yes|no|wait|repeat quick reply\n"
        "stop cancel unspoken output | e end call | h help")


class Bridge:
    """Connects recognition sources and terminal commands to one call's WebSocket."""

    def __init__(self, transport: Transport, state: TurnState | None = None,
                 out: Callable[[str], None] = print) -> None:
        self.transport, self.out = transport, out
        self.state = state or TurnState()
        self.manual = ManualSource()
        self._tasks: list[asyncio.Task[None]] = []

    async def send(self, message: Message | None) -> None:
        if message is not None:
            await self.transport.send(json.dumps(message))

    async def on_result(self, result: Result) -> None:
        try:
            message = self.state.add(result)
        except ChipLimit as error:
            self.out(f"! {error}")
            return
        self._show_chips()
        await self.send(message)

    async def handle_line(self, line: str) -> bool:
        """Runs one terminal line. Returns False when the user ended the call."""
        words = line.split()
        if not words:
            return True
        command, args = words[0].lower(), words[1:]
        if command == "x":
            message = self.state.remove_last()
            self._show_chips()
            await self.send(message)
        elif command == "c":
            self.state.clear()
            self.out("turn cleared")
        elif command == "s":
            await self._send_approval(self.state.approve())
        elif command == "q":
            name = args[0].lower() if len(args) == 1 else ""
            if name not in QUICK_REPLIES:
                self.out(f"! quick reply is one of: {' '.join(QUICK_REPLIES)}")
                return True
            await self._send_approval(self.state.quick_reply(name))
        elif command == "stop":
            await self.send(self.state.stop())
        elif command == "e":
            await self.send(self.state.end())
            self.out("call ended by you; nothing more will be sent")
            return False
        elif command in ("h", "help"):
            self.out(HELP)
        else:
            try:
                results = [parse_result(word) for word in words]
            except ValueError as error:
                self.out(f"! {error}")
                return True
            for result in results:
                self.manual.feed(result)
        return True

    async def on_server(self, raw: str | bytes) -> None:
        message = json.loads(raw)
        kind = message["type"]
        if kind == "status":
            self.out(f"[status] {message['state']}")
            if message["state"] == "speaking":
                self.out("Speaking now...")
            elif message["state"] == "ended":
                self.state.on_ended()
                self.out("call ended; nothing more will be sent")
        elif kind == "caption":
            self.out(f"receptionist: {message['text']}")
        elif kind == "draft":
            draft = self.state.on_draft(message["turn_id"], message["text"], message["source"])
            if draft is not None:
                self.out(f"draft ({draft.source}): {draft.text}   [s = SEND]")
        elif kind == "spoken":
            if (text := self.state.on_spoken(message["turn_id"])) is not None:
                self.out(f"Delivered: {text}")
        elif kind == "not_delivered":
            if (text := self.state.on_not_delivered(message["turn_id"])) is not None:
                self.out(f"! not delivered ({message['reason']}), tap SEND again (s): {text}")
        elif kind == "error":
            self.out(f"! backend error {message['code']}: {message['message']}")
        else:
            self.out(f"(ignored unknown message type {kind!r})")

    async def run(self, lines: AsyncIterator[str],
                  sources: tuple[RecognitionSource, ...] = ()) -> None:
        """Runs until the user ends the call, the terminal closes or the backend hangs up."""
        self.out(HELP)
        try:
            async with asyncio.TaskGroup() as group:
                self._tasks = [group.create_task(self._pump_server()),
                               group.create_task(self._pump_lines(lines)),
                               *(group.create_task(self._pump_source(source))
                                 for source in (self.manual, *sources))]
        finally:
            await self.transport.close()

    async def _send_approval(self, message: Message | None) -> None:
        if message is None:
            self.out("nothing to send yet: wait for a draft" if not self.state.ended
                     else "call ended; nothing will be sent")
            return
        self.out(f"SEND: {message['text']}")
        await self.send(message)

    def _show_chips(self) -> None:
        chips = " ".join(f"[{chip or '?'}]" for chip in self.state.chips) or "(none)"
        self.out(f"chips: {chips}")

    async def _pump_server(self) -> None:
        try:
            async for raw in self.transport:
                await self.on_server(raw)
        finally:
            if not self.state.ended:
                self.state.on_ended()
                self.out("connection closed; nothing will be sent")
            self._stop_others()

    async def _pump_lines(self, lines: AsyncIterator[str]) -> None:
        async for line in lines:
            if not await self.handle_line(line):
                break
        self._stop_others()

    async def _pump_source(self, source: RecognitionSource) -> None:
        async for result in source.results():
            await self.on_result(result)

    def _stop_others(self) -> None:
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()
