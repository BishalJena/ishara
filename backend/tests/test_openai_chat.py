from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.openai_chat import SSE_DONE, ChatCompletionRequest, completion, sse_events

TRICKY = [
    "No, sorry — 4 pm doesn't work.\nIs there anything tomorrow morning?",
    "  leading and trailing spaces  ",
    "tabs\tand\r\nCRLF\n\n",
    "Quotes \"double\" and 'single', a backslash \\ and {{braces}}",
    "Hindi नमस्ते and emoji 🙏",
    "x",
    "   ",
]


def _chunks(events: list[str]) -> list[dict]:
    assert events[-1] == SSE_DONE
    assert all(event.startswith("data: ") and event.endswith("\n\n") for event in events)
    return [json.loads(event.removeprefix("data: ")) for event in events[:-1]]


@pytest.mark.parametrize("text", TRICKY)
def test_streamed_pieces_join_back_to_the_exact_text(text: str) -> None:
    chunks = _chunks(list(sse_events("m", text)))
    joined = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    assert joined == text


def test_stream_has_openai_role_and_finish_framing() -> None:
    chunks = _chunks(list(sse_events("m", "Hello there.")))
    assert {chunk["object"] for chunk in chunks} == {"chat.completion.chunk"}
    assert len({chunk["id"] for chunk in chunks}) == 1
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert [chunk["choices"][0]["finish_reason"] for chunk in chunks[1:]] == [None, None, "stop"]
    assert chunks[-1]["choices"][0]["delta"] == {}


def test_empty_stream_has_no_content_pieces() -> None:
    chunks = _chunks(list(sse_events("m", "")))
    assert [chunk["choices"][0]["delta"].get("content") for chunk in chunks] == ["", None]


def test_completion_object_shape() -> None:
    body = completion("m", "Hi.")
    assert body["object"] == "chat.completion"
    assert body["model"] == "m"
    assert body["choices"] == [
        {"index": 0, "message": {"role": "assistant", "content": "Hi."}, "finish_reason": "stop"}
    ]


def test_request_keeps_unknown_fields_and_reads_content_parts() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "m",
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "a"}, {"type": "image"}]},
                {"role": "assistant", "content": None, "tool_calls": []},
            ],
            "tools": [{"type": "function", "function": {"name": "end_call"}}],
            "chat_template_kwargs": {"enable_thinking": False},
        }
    )
    assert request.texts_by_role("system") == ["a"]
    assert request.texts_by_role("assistant") == [""]
    assert request.tool_names() == ["end_call"]
    assert request.top_level_keys() == ["chat_template_kwargs", "messages", "model", "tools"]


@pytest.mark.parametrize(
    "raw",
    [
        {"messages": []},
        {"model": "m"},
        {"messages": [{"content": "no role"}]},
        {"messages": [{"role": "user", "content": 5}]},
        {"messages": "hi"},
    ],
)
def test_malformed_requests_rejected(raw: dict) -> None:
    with pytest.raises(ValidationError):
        ChatCompletionRequest.model_validate(raw)
