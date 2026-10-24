from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.markers import (
    MarkerBlock,
    parse_marker_block,
    render_marker_block,
)
from app.protocol import (
    SIGNS,
    ApproveMessage,
    CaptionMessage,
    ChipsMessage,
    DraftMessage,
    DraftSource,
    Sign,
    app_message_adapter,
    server_message_adapter,
)


def test_sign_literal_matches_vocabulary_tuple() -> None:
    assert Sign.__args__ == SIGNS
    assert len(SIGNS) == 12


def test_app_messages_parse_by_type() -> None:
    chips = app_message_adapter.validate_json('{"type":"chips","turn_id":"t1","chips":["no"]}')
    assert chips == ChipsMessage(turn_id="t1", chips=["no"])
    raw = {"type": "approve", "turn_id": "t1", "text": "No."}
    approve = app_message_adapter.validate_python(raw)
    assert isinstance(approve, ApproveMessage)


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "chips", "turn_id": "t1", "chips": ["?"]},
        {"type": "chips", "turn_id": "t1", "chips": ["unknown"]},
        {"type": "approve", "turn_id": "t1", "text": ""},
        {"type": "approve", "turn_id": "t1", "text": "x" * 301},
        {"type": "approve", "turn_id": "bad id!", "text": "Hi"},
        {"type": "approve", "turn_id": "t1", "text": "Hi", "extra": 1},
        {"type": "speak", "text": "Hi"},
    ],
)
def test_invalid_app_messages_rejected(raw: dict) -> None:
    with pytest.raises(ValidationError):
        app_message_adapter.validate_python(raw)


def test_server_message_round_trip() -> None:
    draft = DraftMessage(turn_id="t1", text="Hello.", source=DraftSource.TEMPLATE)
    assert server_message_adapter.validate_json(draft.model_dump_json()) == draft
    assert draft.model_dump()["source"] == "template"


def test_caption_speaker_defaults_to_receptionist_and_is_always_serialised() -> None:
    caption = CaptionMessage(text="We have 4 pm.", at=1.5)

    assert json.loads(caption.model_dump_json()) == {
        "type": "caption",
        "text": "We have 4 pm.",
        "at": 1.5,
        "speaker": "receptionist",
    }


def test_agent_caption_round_trips() -> None:
    caption = CaptionMessage(text="Goodbye.", at=2.0, speaker="agent")

    assert json.loads(caption.model_dump_json())["speaker"] == "agent"
    assert server_message_adapter.validate_json(caption.model_dump_json()) == caption


def test_caption_without_speaker_parses_as_receptionist() -> None:
    raw = '{"type":"caption","text":"Hello?","at":1.0}'

    assert server_message_adapter.validate_json(raw) == CaptionMessage(text="Hello?", at=1.0)


@pytest.mark.parametrize("speaker", ["user", "Agent", "", None])
def test_caption_rejects_unknown_speakers(speaker: str | None) -> None:
    raw = {"type": "caption", "text": "Hi", "at": 1.0, "speaker": speaker}
    with pytest.raises(ValidationError):
        server_message_adapter.validate_python(raw)


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def test_speak_block_round_trips_multiline_reply() -> None:
    reply = "No, sorry, 4 pm doesn't work.\nIs there anything tomorrow morning?"
    prompt = (
        "You are a relay.\n"
        + _fill(render_marker_block("speak"), ishara_call_id="c1", turn_id="t9", reply_text=reply)
        + "\nSay nothing else."
    )
    assert parse_marker_block(prompt) == MarkerBlock("c1", "speak", "t9", reply)


def test_listen_block_parses() -> None:
    prompt = _fill(render_marker_block("listen"), ishara_call_id="c1")
    assert parse_marker_block(prompt) == MarkerBlock("c1", "listen")


@pytest.mark.parametrize(
    "prompt",
    [
        "no markers here",
        render_marker_block("listen"),
        _fill(render_marker_block("speak"), ishara_call_id="c1"),
        _fill(render_marker_block("speak"), ishara_call_id="c1", turn_id="t1"),
        _fill(render_marker_block("speak"), ishara_call_id="c1", reply_text="Yes."),
    ],
)
def test_unfilled_or_missing_blocks_are_ignored(prompt: str) -> None:
    assert parse_marker_block(prompt) is None
