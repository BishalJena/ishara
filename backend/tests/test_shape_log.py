from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.openai_chat import ChatCompletionRequest
from app.shape_log import SHAPE_LOG_ENV, log_shape, request_shape

SECRET_WORDS = "Doctor Rao is free at 4 pm"


def _body() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "m",
            "stream": True,
            "messages": [
                {"role": "system", "content": "prompt"},
                {"role": "user", "content": SECRET_WORDS},
            ],
            "tools": [{"type": "function", "function": {"name": "stay_on_current_node"}}],
            "tool_choice": {"type": "function", "function": {"name": "end_call"}},
            "response_format": {"type": "text"},
            "stop": ["User:"],
        }
    )


def test_shape_has_structure_but_no_text() -> None:
    shape = request_shape(_body(), kind="routing", node=None, outcome="silent")
    assert shape == {
        "event": "custom_llm_request",
        "kind": "routing",
        "node": None,
        "outcome": "silent",
        "stream": True,
        "top_level_keys": [
            "messages",
            "model",
            "response_format",
            "stop",
            "stream",
            "tool_choice",
            "tools",
        ],
        "message_count": 2,
        "roles": ["system", "user"],
        "content_lengths": [6, len(SECRET_WORDS)],
        "tools": ["stay_on_current_node"],
        "tool_choice": "end_call",
        "response_format": "text",
    }


def test_log_shape_appends_json_lines_when_path_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    target = tmp_path / "artifacts" / "shapes.jsonl"
    monkeypatch.setenv(SHAPE_LOG_ENV, str(target))
    with caplog.at_level(logging.INFO, logger="app.shape_log"):
        log_shape({"kind": "listen"})
        log_shape({"kind": "speak"})
    lines = target.read_text().splitlines()
    assert [json.loads(line) for line in lines] == [{"kind": "listen"}, {"kind": "speak"}]
    assert [record.getMessage() for record in caplog.records] == lines


def test_log_shape_writes_no_file_without_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SHAPE_LOG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    log_shape({"kind": "listen"})
    assert list(tmp_path.iterdir()) == []
