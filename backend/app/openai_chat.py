"""OpenAI chat-completions wire shapes for the custom-LLM endpoint.

Requests are parsed leniently (unknown fields allowed) because Bolna forwards an
agent's `extra_body` keys as top-level fields. Responses follow OpenAI's
`chat.completion` and `chat.completion.chunk` objects.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL = "ishara-relay"
SSE_DONE = "data: [DONE]\n\n"
# Every character is either \S or \s, so the pieces always join back to the input.
_PIECE = re.compile(r"\S+\s*|\s+")


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


class FunctionSpec(_Lenient):
    name: str


class Tool(_Lenient):
    type: str = "function"
    function: FunctionSpec | None = None


class ContentPart(_Lenient):
    type: str
    text: str | None = None


class ChatMessage(_Lenient):
    role: str
    content: str | list[ContentPart] | None = None

    @property
    def text(self) -> str:
        if isinstance(self.content, list):
            return "".join(part.text or "" for part in self.content if part.type == "text")
        return self.content or ""


class ChatCompletionRequest(_Lenient):
    model: str | None = None
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    tools: list[Tool] | None = None
    functions: list[FunctionSpec] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None

    def texts_by_role(self, role: str) -> list[str]:
        return [message.text for message in self.messages if message.role == role]

    def tool_names(self) -> list[str]:
        names = [tool.function.name for tool in self.tools or [] if tool.function]
        return names + [function.name for function in self.functions or []]

    def top_level_keys(self) -> list[str]:
        return sorted(self.model_fields_set | set(self.model_extra or {}))


def completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def completion(model: str, content: str) -> dict[str, Any]:
    return {
        "id": completion_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def sse_events(model: str, content: str) -> Iterator[str]:
    """SSE lines for a streamed reply: role, content pieces, finish, then [DONE]."""
    base = {
        "id": completion_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
    }

    def chunk(delta: dict[str, str], finish_reason: str | None = None) -> str:
        choice = {"index": 0, "delta": delta, "finish_reason": finish_reason}
        return f"data: {json.dumps({**base, 'choices': [choice]})}\n\n"

    yield chunk({"role": "assistant", "content": ""})
    for piece in _PIECE.findall(content):
        yield chunk({"content": piece})
    yield chunk({}, "stop")
    yield SSE_DONE
