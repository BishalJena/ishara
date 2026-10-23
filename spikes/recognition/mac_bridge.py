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
