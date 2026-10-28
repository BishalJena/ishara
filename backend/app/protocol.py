"""Wire contract between the app (iOS / Mac bridge) and the backend. See PLAN.md §3.

Every WebSocket message is a JSON object with a `type` field. The iOS app mirrors
these shapes in Swift; change both sides together.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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


CallMode = Literal["live", "delegated"]
BriefId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class StartCallRequest(_Message):
    contact_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    purpose: Purpose
    # Decision D9. "live": every sentence is composed from signs and approved with SEND.
    # "delegated": the agent pursues an approved brief; `brief_id` is required and its
    # approval is this request. `attended` lets the agent ask the user yes/no/wait
    # questions during the call; unattended calls never ask.
    mode: CallMode = "live"
    brief_id: BriefId | None = None
    attended: bool = False


class StartCallResponse(_Message):
    call_id: str
    state: CallState
    mode: CallMode = "live"


# ---- delegated calls (D9) ----


class Profile(_Message):
    """What the agent may share about the caller. Nothing else is ever said."""

    name: str = Field(min_length=1, max_length=60)
    callback: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=200)


class BriefRequest(_Message):
    purpose: Purpose
    chips: list[Sign] = Field(default_factory=list, max_length=MAX_CHIPS)
    profile: Profile


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


# ---- app -> backend (WebSocket) ----


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
    ChipsMessage | ApproveMessage | StopMessage | EndMessage | AnswerMessage,
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


ServerMessage = Annotated[
    StatusMessage
    | CaptionMessage
    | DraftMessage
    | SpokenMessage
    | NotDeliveredMessage
    | ErrorMessage
    | AskMessage
    | AskResolvedMessage,
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
