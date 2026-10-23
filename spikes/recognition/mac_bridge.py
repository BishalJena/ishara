"""Mac fallback for the demo (PLAN A4): recognised signs become chips on the backend WebSocket.

`TurnState` owns the turn rules from PLAN §4 and holds no I/O, so the iOS app and this
bridge can be checked against the same behaviour. Nothing here speaks on its own: the
only path to an `approve` message is an explicit SEND or quick reply.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

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
            raise ValueError(f"at most {MAX_CHIPS} chips per turn")
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
