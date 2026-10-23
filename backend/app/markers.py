"""Markers that tie Bolna's custom-LLM requests back to our call and turn.

The Bolna graph agent (backend/bolna/agent.json) puts a marker block in each node
prompt. Bolna substitutes `{{var}}` from `user_data` (set when we start the call) and
from event `properties` (`user_reply` carries reply_text and turn_id), so every
custom-LLM request tells us which call, node and turn it belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Node = Literal["listen", "speak"]

DISCLOSURE = (
    "Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. "
    "Their replies may take a few seconds."
)
HOLDING_LINE = "One moment please, I'm signing my reply."
GOODBYE = "Thank you for your time. Goodbye."
SILENCE_MARKER = "[silence]"

USER_DATA_CALL_ID = "ishara_call_id"
EVENT_USER_REPLY = "user_reply"
EVENT_END_CALL = "end_call"
PROP_REPLY_TEXT = "reply_text"
PROP_TURN_ID = "turn_id"
# Bolna's agent-level status webhook posts to WEBHOOK_PATH/<CUSTOM_LLM_TOKEN>; the
# payloads are unsigned, so the secret path segment is the only check.
WEBHOOK_PATH = "/bolna/webhook"

_BLOCK = re.compile(
    r"ISHARA_CALL_ID: (?P<call_id>[^\n]*)\n"
    r"ISHARA_NODE: (?P<node>listen|speak)(?:\n|$)"
    r"(?:ISHARA_TURN_ID: (?P<turn_id>[^\n]*)\n"
    r"ISHARA_REPLY_START\n(?P<reply>.*?)\nISHARA_REPLY_END)?",
    re.DOTALL,
)


@dataclass(frozen=True)
class MarkerBlock:
    call_id: str
    node: Node
    turn_id: str | None = None
    reply_text: str | None = None


def render_marker_block(node: Node) -> str:
    """Template text placed in a node prompt; Bolna fills the `{{...}}` variables."""
    lines = [f"ISHARA_CALL_ID: {{{{{USER_DATA_CALL_ID}}}}}", f"ISHARA_NODE: {node}"]
    if node == "speak":
        lines += [
            f"ISHARA_TURN_ID: {{{{{PROP_TURN_ID}}}}}",
            "ISHARA_REPLY_START",
            f"{{{{{PROP_REPLY_TEXT}}}}}",
            "ISHARA_REPLY_END",
        ]
    return "\n".join(lines)


def parse_marker_block(prompt: str) -> MarkerBlock | None:
    """Find a filled-in marker block. Returns None if absent or still unsubstituted."""
    match = _BLOCK.search(prompt)
    if not match:
        return None
    call_id = match["call_id"].strip()
    if not call_id or "{{" in call_id:
        return None
    node = match["node"]
    if node == "listen":
        return MarkerBlock(call_id=call_id, node="listen")
    turn_id, reply = match["turn_id"], match["reply"]
    if turn_id is None or reply is None or "{{" in turn_id or "{{" in reply:
        return None
    return MarkerBlock(call_id=call_id, node="speak", turn_id=turn_id.strip(), reply_text=reply)
