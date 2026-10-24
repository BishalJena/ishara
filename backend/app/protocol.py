"""Wire contract between the app (iOS / Mac bridge) and the backend. See PLAN.md §3.

Every WebSocket message is a JSON object with a `type` field. The iOS app mirrors
these shapes in Swift; change both sides together.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

SIGNS = (
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
]
PURPOSES = ("doctor_appointment",)
Purpose = Literal["doctor_appointment"]

MAX_CHIPS = 8
MAX_SPOKEN_CHARS = 300
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


class StartCallRequest(_Message):
    contact_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    purpose: Purpose


class StartCallResponse(_Message):
    call_id: str
    state: CallState


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
    ChipsMessage | ApproveMessage | StopMessage | EndMessage, Field(discriminator="type")
]
app_message_adapter: TypeAdapter[AppMessage] = TypeAdapter(AppMessage)


# ---- backend -> app (WebSocket) ----


class StatusMessage(_Message):
    type: Literal["status"] = "status"
    state: CallState


class CaptionMessage(_Message):
    """The receptionist's words (Path B only). `at` is a unix timestamp in seconds."""

    type: Literal["caption"] = "caption"
    text: str
    at: float


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
    | ErrorMessage,
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
