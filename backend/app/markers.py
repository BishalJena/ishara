"""Markers that tie Bolna's custom-LLM requests back to our call and node.

The Bolna graph agent (backend/bolna/agent.json) puts a marker block in each node
prompt: the call id and the node. Bolna fills `{{var}}` only from `user_data` (set when
we start the call). Event properties never reach the prompt, whatever Bolna's docs say
(first real call, 28 Oct), so the speak node carries no turn or text: the backend
speaks the call's one approved in-flight turn.
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
# Sent on user_reply only so Bolna's logs name the turn; never read back.
PROP_TURN_ID = "turn_id"
# Bolna's agent-level status webhook posts to WEBHOOK_PATH/<BOLNA_WEBHOOK_SECRET>; the
# payloads are unsigned, so the secret path segment is the only check. It is its own
# secret because request paths end up in router logs.
WEBHOOK_PATH = "/bolna/webhook"

_BLOCK = re.compile(
    r"ISHARA_CALL_ID: (?P<call_id>[^\n]*)\nISHARA_NODE: (?P<node>listen|speak)(?:\n|$)"
)


@dataclass(frozen=True)
class MarkerBlock:
    call_id: str
    node: Node


def render_marker_block(node: Node) -> str:
    """Template text placed in a node prompt; Bolna fills `{{ishara_call_id}}`."""
    return f"ISHARA_CALL_ID: {{{{{USER_DATA_CALL_ID}}}}}\nISHARA_NODE: {node}"


def parse_marker_block(prompt: str) -> MarkerBlock | None:
    """Find a filled-in marker block. Returns None if absent or the call id is still a
    placeholder (Bolna leaves an unfilled `{{var}}` as `{var}`)."""
    match = _BLOCK.search(prompt)
    if not match:
        return None
    call_id = match["call_id"].strip()
    if not call_id or "{" in call_id or "}" in call_id:
        return None
    node: Node = "listen" if match["node"] == "listen" else "speak"
    return MarkerBlock(call_id=call_id, node=node)
