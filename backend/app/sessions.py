"""Pure call, turn and approval state for one call. No I/O; app/calls.py does that.

Rules (PLAN.md §4, docs/WORKFLOW.md edge cases):
- The app picks turn ids. A never-seen id becomes the current turn and closes the
  previous one; messages for closed turns are rejected as stale.
- An approval (SEND) is single use, tied to its turn and only accepted while the
  call is live. At most one approved turn is in flight (sent to Bolna, not yet
  spoken) at a time.
- Bolna's speak-node request claims the in-flight approval exactly once and gets its
  approved text (Bolna can't carry the text itself). Stop, a new turn, a delivery
  timeout or the end of the call revoke an unclaimed approval.

Every rejecting method raises before it mutates anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.protocol import CallMode, CallState, Purpose, Sign, TranscriptEntry


class TurnPhase(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    CLAIMED = "claimed"
    SPOKEN = "spoken"
    CANCELLED = "cancelled"
    UNDELIVERED = "undelivered"


class Rejection(StrEnum):
    STALE_TURN = "stale_turn"
    ALREADY_APPROVED = "already_approved"
    CALL_NOT_LIVE = "call_not_live"
    CALL_ENDED = "call_ended"
    CANNOT_INTERRUPT = "cannot_interrupt"
    BUSY_SPEAKING = "busy_speaking"


_MESSAGES = {
    Rejection.STALE_TURN: "That turn is closed; start a new one.",
    Rejection.ALREADY_APPROVED: "That turn was already sent.",
    Rejection.CALL_NOT_LIVE: "The call is not connected yet.",
    Rejection.CALL_ENDED: "The call has ended. Nothing will be sent.",
    Rejection.CANNOT_INTERRUPT: "Bolna is already speaking; it cannot be interrupted.",
    Rejection.BUSY_SPEAKING: "Wait until the current reply has been spoken.",
}


class TurnRejected(Exception):
    def __init__(self, code: Rejection) -> None:
        super().__init__(code.value)
        self.code = code
        self.message = _MESSAGES[code]


_FINISHED = frozenset({CallState.ENDED, CallState.ERROR})
_LIVE = frozenset({CallState.IN_CALL})
# Bolna status updates may arrive late or out of order; the line only moves forward.
_RANK = {
    CallState.DIALING: 0,
    CallState.RINGING: 1,
    CallState.IN_CALL: 2,
    CallState.ENDED: 3,
    CallState.ERROR: 3,
}


@dataclass
class Turn:
    turn_id: str
    chips: tuple[Sign, ...] = ()
    chips_rev: int = 0
    phase: TurnPhase = TurnPhase.OPEN
    approved_text: str | None = None


@dataclass
class CallSession:
    call_id: str
    purpose: Purpose
    run_id: str | None = None
    last_caption: str | None = None
    # Decision D9: "delegated" calls carry a DelegateState (app/delegate.py) that the
    # custom-LLM endpoint consults instead of staying silent in the listen node.
    mode: CallMode = "live"
    delegate: object | None = None
    transcript: list[TranscriptEntry] = field(default_factory=list)
    bolna_summary: str | None = None
    # Line state from Bolna and captions; never SPEAKING (that is derived from in_flight).
    line: CallState = CallState.DIALING
    current: Turn | None = None
    in_flight: Turn | None = None
    seen_turn_ids: set[str] = field(default_factory=set)

    @property
    def state(self) -> CallState:
        if self.line in _LIVE and self.in_flight is not None:
            return CallState.SPEAKING
        return self.line

    @property
    def finished(self) -> bool:
        return self.line in _FINISHED

    # ---- app messages ----

    def set_chips(self, turn_id: str, chips: Sequence[Sign]) -> Turn:
        if self.finished:
            raise TurnRejected(Rejection.CALL_ENDED)
        turn = self._existing_turn(turn_id)
        if turn is not None and turn.phase is not TurnPhase.OPEN:
            raise TurnRejected(Rejection.ALREADY_APPROVED)
        turn = turn or self._begin_turn(turn_id)
        turn.chips = tuple(chips)
        turn.chips_rev += 1
        return turn

    def draft_is_current(self, turn_id: str, chips_rev: int) -> bool:
        """A composed draft may be shown only if nothing changed while composing."""
        turn = self.current
        return (
            turn is not None
            and turn.turn_id == turn_id
            and turn.chips_rev == chips_rev
            and turn.phase is TurnPhase.OPEN
        )

    def approve(self, turn_id: str, text: str) -> Turn:
        if self.finished:
            raise TurnRejected(Rejection.CALL_ENDED)
        if self.line not in _LIVE or self.run_id is None:
            raise TurnRejected(Rejection.CALL_NOT_LIVE)
        turn = self._existing_turn(turn_id)
        if turn is not None and turn.phase is not TurnPhase.OPEN:
            raise TurnRejected(Rejection.ALREADY_APPROVED)
        if self.in_flight is not None and self.in_flight.phase is TurnPhase.CLAIMED:
            raise TurnRejected(Rejection.BUSY_SPEAKING)
        turn = turn or self._begin_turn(turn_id)
        turn.phase = TurnPhase.APPROVED
        turn.approved_text = text
        self.in_flight = turn
        return turn

    def stop(self) -> Turn | None:
        """Cancel the unclaimed in-flight approval. Returns the cancelled turn."""
        turn = self.in_flight
        if turn is None:
            return None
        if turn.phase is TurnPhase.CLAIMED:
            raise TurnRejected(Rejection.CANNOT_INTERRUPT)
        return self._settle(TurnPhase.CANCELLED)

    def revoke_unclaimed(self) -> Turn | None:
        """Like stop, but silent when a reply is already being spoken."""
        if self.in_flight is None or self.in_flight.phase is not TurnPhase.APPROVED:
            return None
        return self._settle(TurnPhase.CANCELLED)

    # ---- Bolna side ----

    def claim(self) -> Turn | None:
        """Claim the approved in-flight turn for speaking; None if there is none."""
        turn = self.in_flight
        if self.finished or turn is None or turn.phase is not TurnPhase.APPROVED:
            return None
        turn.phase = TurnPhase.CLAIMED
        return turn

    def mark_spoken(self, turn_id: str) -> bool:
        turn = self.in_flight
        if turn is None or turn.turn_id != turn_id or turn.phase is not TurnPhase.CLAIMED:
            return False
        self._settle(TurnPhase.SPOKEN)
        return True

    def fail_delivery(self, turn_id: str) -> bool:
        """No spoken confirmation in time (or the event never reached Bolna)."""
        if self.in_flight is None or self.in_flight.turn_id != turn_id:
            return False
        self._settle(TurnPhase.UNDELIVERED)
        return True

    def hear_caption(self, text: str) -> None:
        """A receptionist utterance proves the line is connected."""
        self.last_caption = text
        self.advance(CallState.IN_CALL)

    def advance(self, line: CallState) -> bool:
        """Move the line forward; finishing wipes every pending turn and draft."""
        if _RANK[line] <= _RANK[self.line]:
            return False
        self.line = line
        if self.finished:
            if self.in_flight is not None:
                self._settle(TurnPhase.CANCELLED)
            self.current = None
        return True

    # ---- internals ----

    def _existing_turn(self, turn_id: str) -> Turn | None:
        if self.current is not None and self.current.turn_id == turn_id:
            return self.current
        if turn_id in self.seen_turn_ids:
            raise TurnRejected(Rejection.STALE_TURN)
        return None

    def _begin_turn(self, turn_id: str) -> Turn:
        self.revoke_unclaimed()
        self.seen_turn_ids.add(turn_id)
        self.current = Turn(turn_id)
        return self.current

    def _settle(self, phase: TurnPhase) -> Turn:
        turn = self.in_flight
        assert turn is not None
        turn.phase = phase
        self.in_flight = None
        return turn
