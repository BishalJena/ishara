"""One timestamped terminal line per server message, without call or turn ids."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.protocol import (
    CaptionMessage,
    DraftMessage,
    ErrorMessage,
    NotDeliveredMessage,
    ServerMessage,
    SpokenMessage,
    StatusMessage,
)


def describe(message: ServerMessage, label_for: Callable[[str], str]) -> str:
    match message:
        case StatusMessage(state=state):
            return f"status        {state.value}"
        case CaptionMessage(text=text, speaker=speaker):
            return f'caption       [{speaker}] "{text}"'
        case DraftMessage(turn_id=turn_id, text=text, source=source):
            return f"draft         [{label_for(turn_id)}, {source.value}] {text}"
        case SpokenMessage(turn_id=turn_id):
            return f"spoken        [{label_for(turn_id)}]"
        case NotDeliveredMessage(turn_id=turn_id, reason=reason):
            return f"not_delivered [{label_for(turn_id)}] {reason}"
        case ErrorMessage(code=code, message=text):
            return f"error         {code}: {text}"


def format_event(
    message: ServerMessage,
    notices: list[str],
    label_for: Callable[[str], str],
    now: datetime,
) -> str:
    stamp = now.strftime("%H:%M:%S.%f")[:-3]
    lines = [f"{stamp}  {describe(message, label_for)}"]
    lines += [f"{' ' * len(stamp)}  ! {notice}" for notice in notices]
    return "\n".join(lines)
