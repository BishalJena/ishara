"""Redacted shape of each custom-LLM request, for the day-1 Bolna spike.

The shape records structure only: roles, counts, lengths, keys and tool names.
It never contains message text, the reply, or any header. If CUSTOM_LLM_SHAPE_LOG
names a file, each shape is also appended there as one JSON line; keep that file
under an ignored directory such as `backend/artifacts/`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.openai_chat import ChatCompletionRequest

SHAPE_LOG_ENV = "CUSTOM_LLM_SHAPE_LOG"

logger = logging.getLogger(__name__)


def request_shape(
    body: ChatCompletionRequest, *, kind: str, node: str | None, outcome: str
) -> dict[str, Any]:
    tool_choice = body.tool_choice
    if isinstance(tool_choice, dict):
        tool_choice = tool_choice.get("function", {}).get("name", "object")
    return {
        "event": "custom_llm_request",
        "kind": kind,
        "node": node,
        "outcome": outcome,
        "stream": body.stream,
        "top_level_keys": body.top_level_keys(),
        "message_count": len(body.messages),
        "roles": [message.role for message in body.messages],
        "content_lengths": [len(message.text) for message in body.messages],
        "tools": body.tool_names(),
        "tool_choice": tool_choice,
        "response_format": (body.response_format or {}).get("type"),
    }


def log_shape(shape: dict[str, Any]) -> None:
    line = json.dumps(shape, sort_keys=True)
    logger.info(line)
    path = os.environ.get(SHAPE_LOG_ENV)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
