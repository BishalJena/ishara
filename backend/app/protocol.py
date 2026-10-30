"""Wire contract between the app (iOS / Mac bridge) and the backend. See PLAN.md §3.

Every WebSocket message is a JSON object with a `type` field. The iOS app mirrors
these shapes in Swift; change both sides together.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

# Decision D8: the recognizer is the public ASL Signs model (250 glosses). TEMPLATE_SIGNS are
# the original twelve the fixed templates know in full; ASL_SIGNS are the service-call glosses
# of that model the composer accepts generically (templates say them plainly, Groq phrases them,
# the validator checks their meaning). Change spikes/recognition/vocabulary.py and
# ios/Packages/CallSession/.../Vocabulary.swift together with this.
TEMPLATE_SIGNS = (
    "hello",
    "thankyou",
    "yes",
    "no",
    "sorry",
    "doctor",
    "today",
    "tomorrow",
    "morning",
    "afternoon",
    "evening",
    "time",
)
ASL_SIGNS = (
    "please",
    "now",
    "wait",
    "night",
    "yesterday",
    "later",
    "can",
    "where",
    "who",
    "why",
    "have",
    "finish",
    "callonphone",
    "sick",
    "hungry",
    "drink",
    "water",
    "home",
    "go",
    "see",
    "hear",
    "read",
)
SIGNS = TEMPLATE_SIGNS + ASL_SIGNS
Sign = Literal[
    "hello",
    "thankyou",
    "yes",
    "no",
    "sorry",
    "doctor",
    "today",
    "tomorrow",
    "morning",
    "afternoon",
    "evening",
    "time",
    "please",
    "now",
    "wait",
    "night",
    "yesterday",
    "later",
    "can",
    "where",
    "who",
    "why",
    "have",
    "finish",
    "callonphone",
    "sick",
    "hungry",
    "drink",
    "water",
    "home",
    "go",
    "see",
    "hear",
    "read",
]
PURPOSES = ("doctor_appointment",)
Purpose = Literal["doctor_appointment"]

MAX_CHIPS = 8
MAX_SPOKEN_CHARS = 300
CaptionSpeaker = Literal["receptionist", "agent"]
TurnId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class CallState(StrEnum):
    DIALING = "dialing"
    RINGING = "ringing"
    IN_CALL = "in_call"
    SPEAKING = "speaking"
    ENDED = "ended"
    ERROR = "error"


class DraftSource(StrEnum):
    LLM = "llm"
    TEMPLATE = "template"


class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- REST ----


# "steer": the agent runs the whole call from the brief and the user may step in at any
# moment by typing or signing. While the app is in front, each agent line is proposed to
# the app first and spoken when its window runs out; while it is away, lines are spoken
# at once. The agent accepts an offer only when it fits the brief, shares only the
# brief's details, and defers anything else as a follow-up. It never asks a question.
CallMode = Literal["live", "delegated", "steer"]
BriefId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
PhoneNumber = Annotated[str, Field(pattern=r"^\+[1-9]\d{6,14}$")]
MAX_REQUEST_CHARS = 600


class StartCallRequest(_Message):
    # Who to call: an allowlisted contact id, or an E.164 number that must equal one of
    # the allowlisted numbers (the app may let the user paste any number; the backend
    # still dials only consenting recipients).
    contact_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    phone_number: PhoneNumber | None = None
    purpose: Purpose
    # Decision D9. "live": every sentence is composed from signs and approved with SEND.
    # "delegated": the agent pursues an approved brief; `brief_id` is required and its
    # approval is this request. `attended` lets the agent ask the user yes/no/wait
    # questions during the call; unattended calls never ask. "steer": see CallMode.
    mode: CallMode = "live"
    brief_id: BriefId | None = None
    attended: bool = False

    @model_validator(mode="after")
    def _one_recipient(self) -> StartCallRequest:
        if (self.contact_id is None) == (self.phone_number is None):
            raise ValueError("give exactly one of contact_id and phone_number")
        return self


class StartCallResponse(_Message):
    call_id: str
    state: CallState
    mode: CallMode = "live"


# ---- delegated calls (D9) ----


class Detail(_Message):
    """One fact the user approved for sharing ("Date of birth" -> "12 March 1998"). The
    agent says it only when the receptionist asks for something its label names."""

    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=80)


class Profile(_Message):
    """What the agent may share about the caller. Nothing else is ever said."""

    name: str = Field(min_length=1, max_length=60)
    callback: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=200)
    details: list[Detail] = Field(default_factory=list, max_length=12)


class BriefRequest(_Message):
    purpose: Purpose
    chips: list[Sign] = Field(default_factory=list, max_length=MAX_CHIPS)
    profile: Profile
    # Steer calls: what the user typed the call is about. The agent pursues exactly this;
    # its days and parts of day are the only times the agent may agree to.
    request: str | None = Field(default=None, min_length=1, max_length=MAX_REQUEST_CHARS)


class BriefResponse(_Message):
    brief_id: str
    text: str  # what the user approves; the agent pursues exactly this
    goal: str  # one line, used in the agent prompt and the notes
    constraints: list[str]  # when/what the caller signed, as plain facts


# An answer is a sign the user can make (or tap): yes / no / wait for an offered time, or
# a time word for an open "when?" question. Each is also a `Sign`, so a recognised chip
# equal to an option's choice answers the question. Change AskChoice in
# ios/Packages/CallSession/.../Messages.swift together with this.
AskChoice = Literal["yes", "no", "wait", "tomorrow", "morning", "now"]


class AskOption(_Message):
    choice: AskChoice
    spoken: str  # exactly what the agent will say if this is chosen


class AskMessage(_Message):
    """Attended delegated call: the agent paused ("one moment, please") and needs the
    user's answer: yes / no / wait for an offered time, or a time word (+ wait) for an
    open "when?" question. Sign or tap one of the options; after `timeout_s` with no answer
    the agent says the `fallback` line instead."""

    type: Literal["ask"] = "ask"
    ask_id: str
    question: str
    options: list[AskOption]
    fallback: str
    timeout_s: float


class AnswerMessage(_Message):
    type: Literal["answer"] = "answer"
    ask_id: str
    choice: AskChoice


class AskResolvedMessage(_Message):
    type: Literal["ask_resolved"] = "ask_resolved"
    ask_id: str
    spoken: str
    source: Literal["user", "timeout"]


class TranscriptEntry(_Message):
    speaker: CaptionSpeaker
    text: str
    at: float


class CallNotes(_Message):
    call_id: str
    mode: CallMode
    ready: bool
    brief: str | None = None
    outcome: str | None = None  # "booked", "declined", "callback", "unclear", "no_answer"
    summary: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    bolna_summary: str | None = None
    # Steer calls: what the receptionist asked for that the brief didn't carry, and how
    # many times the user stepped in (typed or signed a line).
    follow_ups: list[str] = Field(default_factory=list)
    stepped_in: int = 0


# ---- app -> backend (WebSocket) ----


class PresenceMessage(_Message):
    """Steer calls: whether the call screen is in front on an unlocked phone. Present,
    the agent proposes each line and waits its window; away, it speaks at once."""

    type: Literal["presence"] = "presence"
    present: bool


class HoldMessage(_Message):
    """Steer calls. `composing` true: the user started typing or signing, so the
    proposed line is dropped and the agent covers the pause with filler lines until a
    `say`, an `approve` or `composing` false (which speaks the held line after all)."""

    type: Literal["hold"] = "hold"
    turn_id: TurnId
    composing: bool = True


class SayMessage(_Message):
    """Steer calls: a line the user typed. It is polished (reworded, never given new
    facts), proposed back briefly, then spoken unless the user holds it."""

    type: Literal["say"] = "say"
    text: str = Field(min_length=1, max_length=MAX_SPOKEN_CHARS)


class ChipsMessage(_Message):
    type: Literal["chips"] = "chips"
    turn_id: TurnId
    chips: list[Sign] = Field(max_length=MAX_CHIPS)


class ApproveMessage(_Message):
    """User tapped SEND with exactly this text. Single use per turn_id."""

    type: Literal["approve"] = "approve"
    turn_id: TurnId
    text: str = Field(min_length=1, max_length=MAX_SPOKEN_CHARS)


class StopMessage(_Message):
    type: Literal["stop"] = "stop"


class EndMessage(_Message):
    type: Literal["end"] = "end"


AppMessage = Annotated[
    ChipsMessage
    | ApproveMessage
    | StopMessage
    | EndMessage
    | AnswerMessage
    | PresenceMessage
    | HoldMessage
    | SayMessage,
    Field(discriminator="type"),
]
app_message_adapter: TypeAdapter[AppMessage] = TypeAdapter(AppMessage)


# ---- backend -> app (WebSocket) ----


class StatusMessage(_Message):
    type: Literal["status"] = "status"
    state: CallState


class CaptionMessage(_Message):
    """A line said on the call (Path B only). `at` is a unix timestamp in seconds.

    `speaker` is always serialised:
    - "receptionist": the other person's words from Bolna's transcript.
    - "agent": a line the voice says without a SEND (the opening disclosure, the
      holding line during a long pause, the goodbye after `end`, a delegated agent's
      own lines; its opening once Bolna has said it), so the Deaf user sees the whole
      conversation. Approved replies are not echoed as agent captions: the app already
      shows them once `spoken` arrives.
    """

    type: Literal["caption"] = "caption"
    text: str
    at: float
    speaker: CaptionSpeaker = "receptionist"


class DraftMessage(_Message):
    type: Literal["draft"] = "draft"
    turn_id: TurnId
    text: str
    source: DraftSource


class SpokenMessage(_Message):
    type: Literal["spoken"] = "spoken"
    turn_id: TurnId


class NotDeliveredMessage(_Message):
    """No `spoken` confirmation arrived in time. The app shows "not delivered, tap SEND
    again"; the backend never resends on its own."""

    type: Literal["not_delivered"] = "not_delivered"
    turn_id: TurnId
    reason: str


class ErrorMessage(_Message):
    type: Literal["error"] = "error"
    code: str
    message: str


ProposalOrigin = Literal["agent", "user"]


class ProposalMessage(_Message):
    """Steer calls: a line about to be spoken. "agent": the agent's next line, spoken
    when `window_s` runs out unless the app approves it sooner or holds it. "user": the
    polished form of what the user typed, with a short window to catch a bad rewording."""

    type: Literal["proposal"] = "proposal"
    turn_id: TurnId
    text: str
    window_s: float
    origin: ProposalOrigin = "agent"


ProposalOutcome = Literal["spoken", "held", "cancelled"]


class ProposalResolvedMessage(_Message):
    type: Literal["proposal_resolved"] = "proposal_resolved"
    turn_id: TurnId
    outcome: ProposalOutcome


class FollowUpMessage(_Message):
    """Steer calls: the receptionist asked for something the brief doesn't carry. The
    agent deferred it instead of guessing; the notes list it for the user to act on."""

    type: Literal["follow_up"] = "follow_up"
    text: str


ServerMessage = Annotated[
    StatusMessage
    | CaptionMessage
    | DraftMessage
    | SpokenMessage
    | NotDeliveredMessage
    | ErrorMessage
    | AskMessage
    | AskResolvedMessage
    | ProposalMessage
    | ProposalResolvedMessage
    | FollowUpMessage,
    Field(discriminator="type"),
]
server_message_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)


# ---- composer ----


class ComposeRequest(_Message):
    turn_id: TurnId
    chips: list[Sign] = Field(min_length=1, max_length=MAX_CHIPS)
    purpose: Purpose
    last_caption: str | None = None


class Draft(_Message):
    turn_id: TurnId
    text: str
    source: DraftSource
