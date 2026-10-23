"""What the iOS app does on the call WebSocket (PLAN.md §3-4), minus the UI.

Rules mirrored from the app:
- Every turn has a fresh uuid4-hex `turn_id`; chips, draft and approval belong to it.
- `?` chips are shown to the user but never sent.
- SEND approves the latest draft of the current turn only, then starts a new turn,
  so old text can never be replayed. Drafts for any other turn are ignored.
- `not_delivered` is reported to the user; nothing is ever resent automatically.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar, cast

from pydantic import BaseModel

from app.protocol import (
    SIGNS,
    ApproveMessage,
    CallState,
    CaptionMessage,
    ChipsMessage,
    DraftMessage,
    EndMessage,
    NotDeliveredMessage,
    ServerMessage,
    SpokenMessage,
    StatusMessage,
    StopMessage,
    server_message_adapter,
)
from tools.timing import TurnTiming

M = TypeVar("M", bound=BaseModel)

UNSURE_CHIP = "?"
NOT_DELIVERED_NOTICE = "not delivered, tap SEND again"
STALE_DRAFT_NOTICE = "ignored a draft for another turn"
UNEXPECTED_SPOKEN_NOTICE = "spoken for a turn with no open SEND"


class Transport(Protocol):
    async def send_text(self, data: str) -> None: ...

    async def receive_text(self) -> str | None:
        """Next server frame, or None once the server closed the socket normally."""
        ...


class NoDraftError(Exception):
    """SEND was tapped before a draft arrived for the current turn."""


class SessionClosedError(Exception):
    """The backend closed the call socket."""


def new_turn_id() -> str:
    return uuid.uuid4().hex


class AppSession:
    def __init__(
        self,
        transport: Transport,
        *,
        clock: Callable[[], float] = time.monotonic,
        make_turn_id: Callable[[], str] = new_turn_id,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._make_turn_id = make_turn_id
        self._changed = asyncio.Condition()
        self.history: list[ServerMessage] = []
        self.closed = False
        self.ended = False
        self.turns: list[TurnTiming] = []
        self.spoken_counts: Counter[str] = Counter()
        self._timings: dict[str, TurnTiming] = {}
        self._approved_at: dict[str, float] = {}
        self.new_turn()

    # ---- turn state ----

    @property
    def turn_id(self) -> str:
        return self._turn_id

    def new_turn(self, label: str | None = None) -> None:
        """Wipe chips and draft and start a fresh turn id (Clear, after SEND, quick reply)."""
        self._turn_id = self._make_turn_id()
        self._label = label
        self.chips: list[str] = []
        self.draft: DraftMessage | None = None
        self._sent_chips: list[str] = []
        self._chips_sent_at: float | None = None

    def turn_label(self, turn_id: str) -> str:
        """Label for display; ids themselves are never printed."""
        if turn_id == self._turn_id:
            return "current turn"
        timing = self._timings.get(turn_id)
        return timing.label if timing else "unknown turn"

    def _current_timing(self) -> TurnTiming:
        timing = self._timings.get(self._turn_id)
        if timing is None:
            label = self._label or f"turn {len(self.turns) + 1}"
            timing = TurnTiming(label=label, turn_id=self._turn_id)
            self.turns.append(timing)
            self._timings[self._turn_id] = timing
        return timing

    # ---- app -> backend ----

    async def set_chips(self, chips: Sequence[str]) -> bool:
        """Replace the chips. Sends the recognised ones if they changed; returns whether
        a `chips` message went out. A changed chip list invalidates the shown draft."""
        unknown = [chip for chip in chips if chip != UNSURE_CHIP and chip not in SIGNS]
        if unknown:
            raise ValueError(f"not in the 12-sign vocabulary: {', '.join(unknown)}")
        self.chips = list(chips)
        recognised = [chip for chip in chips if chip != UNSURE_CHIP]
        if recognised == self._sent_chips:
            return False
        self.draft = None
        self._current_timing()
        self._chips_sent_at = self._clock()
        self._sent_chips = recognised
        await self._send(ChipsMessage(turn_id=self._turn_id, chips=recognised))
        return True

    async def add_chip(self, chip: str) -> bool:
        return await self.set_chips([*self.chips, chip])

    async def remove_chip(self, chip: str) -> bool:
        """The user tapped ✕ on a chip (the most recent one if it appears twice)."""
        if chip not in self.chips:
            raise ValueError(f"no chip {chip!r} in this turn")
        index = len(self.chips) - 1 - self.chips[::-1].index(chip)
        return await self.set_chips(self.chips[:index] + self.chips[index + 1 :])

    async def send(self) -> str:
        """SEND: approve this turn's draft, then start a new turn. Returns the approved id."""
        if self.draft is None:
            raise NoDraftError("no draft for this turn yet")
        turn_id = self._turn_id
        await self._approve(self.draft.text)
        self.new_turn()
        return turn_id

    async def say(self, text: str, label: str | None = None) -> str:
        """Quick reply: approve exact text on a fresh turn, then start another fresh turn."""
        self.new_turn(label)
        turn_id = self._turn_id
        await self._approve(text)
        self.new_turn()
        return turn_id

    async def send_twice(self, text: str, label: str | None = None) -> str:
        """V4 check 5 only: the same approval sent twice. The real app never does this."""
        self.new_turn(label)
        turn_id = self._turn_id
        await self._approve(text)
        await self._send(ApproveMessage(turn_id=turn_id, text=text))
        self.new_turn()
        return turn_id

    async def stop(self) -> None:
        await self._send(StopMessage())

    async def end(self) -> None:
        await self._send(EndMessage())

    async def hang_up(self, timeout: float) -> bool:
        """End the call unless it already ended; True once `status ended` arrives.
        Tools call this on every exit path so an aborted run never leaves a paid call up."""
        if self.ended:
            return True
        if self.closed:
            return False
        since = self.mark()
        await self.end()
        try:
            await self.wait_for_status(CallState.ENDED, since=since, timeout=timeout)
        except (TimeoutError, SessionClosedError):
            return self.ended
        return True

    async def _approve(self, text: str) -> None:
        message = ApproveMessage(turn_id=self._turn_id, text=text)
        timing = self._current_timing()
        timing.outcome = "pending"
        # Stamp before sending: the reply can be handled while send_text is awaited.
        self._approved_at[self._turn_id] = self._clock()
        await self._send(message)

    async def _send(
        self, message: ChipsMessage | ApproveMessage | StopMessage | EndMessage
    ) -> None:
        if self.closed:
            raise SessionClosedError("the call socket is closed")
        await self._transport.send_text(message.model_dump_json())

    # ---- backend -> app ----

    async def handle(self, message: ServerMessage) -> list[str]:
        """Apply one server message. Returns notices to show the user."""
        notices = self._apply(message)
        async with self._changed:
            self.history.append(message)
            self._changed.notify_all()
        return notices

    def _apply(self, message: ServerMessage) -> list[str]:
        match message:
            case DraftMessage(turn_id=turn_id) if turn_id == self._turn_id:
                self.draft = message
                if self._chips_sent_at is not None:
                    latency = self._clock() - self._chips_sent_at
                    self._timings[turn_id].draft_latency_s = latency
                    self._chips_sent_at = None
            case DraftMessage():
                return [STALE_DRAFT_NOTICE]
            case SpokenMessage(turn_id=turn_id):
                self.spoken_counts[turn_id] += 1
                approved_at = self._approved_at.pop(turn_id, None)
                if approved_at is None:
                    return [UNEXPECTED_SPOKEN_NOTICE]
                timing = self._timings[turn_id]
                timing.spoken_latency_s = self._clock() - approved_at
                timing.outcome = "spoken"
            case NotDeliveredMessage(turn_id=turn_id):
                if self._approved_at.pop(turn_id, None) is not None:
                    self._timings[turn_id].outcome = "not_delivered"
                return [NOT_DELIVERED_NOTICE]
            case StatusMessage(state=CallState.ENDED):
                self.ended = True
        return []

    async def mark_closed(self) -> None:
        async with self._changed:
            self.closed = True
            self._changed.notify_all()

    # ---- waiting for events ----

    def mark(self) -> int:
        """Position in the event history; pass it as `since` to wait only for newer events."""
        return len(self.history)

    async def wait_for(
        self, predicate: Callable[[ServerMessage], bool], *, since: int, timeout: float
    ) -> ServerMessage:
        """First message after `since` matching `predicate`. Raises TimeoutError, or
        SessionClosedError if the socket closes first."""

        def find() -> ServerMessage | None:
            return next((m for m in self.history[since:] if predicate(m)), None)

        async with asyncio.timeout(timeout), self._changed:
            await self._changed.wait_for(lambda: find() is not None or self.closed)
        found = find()
        if found is None:
            raise SessionClosedError("the backend closed the call socket")
        return found

    async def wait_for_kind(
        self,
        kind: type[M],
        *,
        since: int,
        timeout: float,
        where: Callable[[M], bool] = lambda _: True,
    ) -> M:
        message = await self.wait_for(
            lambda m: isinstance(m, kind) and where(m), since=since, timeout=timeout
        )
        return cast(M, message)

    async def wait_for_caption(self, *, since: int, timeout: float) -> CaptionMessage:
        return await self.wait_for_kind(CaptionMessage, since=since, timeout=timeout)

    async def wait_for_draft(self, *, since: int, timeout: float) -> DraftMessage:
        """A draft for the turn that is current when this is called."""
        turn_id = self._turn_id
        return await self.wait_for_kind(
            DraftMessage, since=since, timeout=timeout, where=lambda m: m.turn_id == turn_id
        )

    async def wait_for_outcome(
        self, turn_id: str, *, since: int, timeout: float
    ) -> SpokenMessage | NotDeliveredMessage:
        """`spoken` or `not_delivered` for one approved turn."""
        message = await self.wait_for(
            lambda m: isinstance(m, SpokenMessage | NotDeliveredMessage) and m.turn_id == turn_id,
            since=since,
            timeout=timeout,
        )
        return cast(SpokenMessage | NotDeliveredMessage, message)

    async def wait_for_status(
        self, state: CallState, *, since: int, timeout: float
    ) -> StatusMessage:
        return await self.wait_for_kind(
            StatusMessage, since=since, timeout=timeout, where=lambda m: m.state == state
        )


async def pump(
    transport: Transport,
    session: AppSession,
    on_message: Callable[[ServerMessage, list[str]], None],
) -> None:
    """Feed server frames into the session until the socket closes. Invalid frames
    raise (the contract is ours, so a bad frame is a bug, not something to skip)."""
    try:
        while (raw := await transport.receive_text()) is not None:
            message = server_message_adapter.validate_json(raw)
            on_message(message, await session.handle(message))
    finally:
        await session.mark_closed()
