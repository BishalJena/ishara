"""Read an OpenAI chat-completions stream (server-sent events) the way Bolna does."""

from __future__ import annotations

import json
from collections.abc import AsyncIterable

DATA_PREFIX = "data:"
DONE = "[DONE]"


async def collect_stream_text(lines: AsyncIterable[str]) -> str:
    """Join every `choices[].delta.content` until `data: [DONE]` or the stream ends.

    Blank lines, comments and role-only chunks carry no text and are skipped. A
    malformed `data:` payload raises, so a broken stream fails the test loudly.
    """
    parts: list[str] = []
    async for line in lines:
        if not line.startswith(DATA_PREFIX):
            continue
        payload = line.removeprefix(DATA_PREFIX).strip()
        if payload == DONE:
            break
        for choice in json.loads(payload)["choices"]:
            content = choice.get("delta", {}).get("content")
            if content:
                parts.append(content)
    return "".join(parts)
