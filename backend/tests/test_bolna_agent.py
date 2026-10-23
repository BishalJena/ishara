from __future__ import annotations

from typing import Any

import pytest

from app.bolna_agent import (
    CALL_TIMEOUT_S,
    CUSTOM_LLM_MODEL,
    build_agent_payload,
    custom_llm_base_url,
)
from app.markers import (
    DISCLOSURE,
    GOODBYE,
    HOLDING_LINE,
    SILENCE_MARKER,
    MarkerBlock,
    parse_marker_block,
)

BASE_URL = "https://ishara.example.com/v1"


@pytest.fixture
def payload() -> dict[str, Any]:
    return build_agent_payload(BASE_URL, None)


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    (task,) = payload["agent_config"]["tasks"]
    return task


def _llm_config(payload: dict[str, Any]) -> dict[str, Any]:
    return _task(payload)["tools_config"]["llm_agent"]["llm_config"]


def _nodes(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in _llm_config(payload)["nodes"]}


def _edges(node: dict[str, Any]) -> set[tuple[str, str | None, str]]:
    return {
        (edge["condition_type"], edge.get("event_name"), edge["to_node_id"])
        for edge in node["edges"]
    }


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def test_is_a_graph_agent_starting_on_listen_with_disclosure_welcome(payload) -> None:
    llm_agent = _task(payload)["tools_config"]["llm_agent"]
    assert llm_agent["agent_type"] == "graph_agent"
    assert llm_agent["llm_config"]["current_node_id"] == "listen"
    assert payload["agent_config"]["agent_welcome_message"] == DISCLOSURE
    assert set(_nodes(payload)) == {"listen", "speak", "goodbye"}


def test_llm_is_our_registered_custom_model(payload) -> None:
    config = _llm_config(payload)
    assert config["provider"] == "custom"
    assert config["model"] == CUSTOM_LLM_MODEL
    assert config["base_url"] == BASE_URL


def test_custom_llm_base_url_points_at_v1_for_chat_completions() -> None:
    assert custom_llm_base_url("https://x.herokuapp.com/") == "https://x.herokuapp.com/v1"
    assert custom_llm_base_url("https://x.herokuapp.com") == "https://x.herokuapp.com/v1"


@pytest.mark.parametrize("url", ["http://x.com/v1", "https://x.com/v1/", "x.com/v1"])
def test_rejects_non_https_or_trailing_slash_base_url(url: str) -> None:
    with pytest.raises(ValueError):
        build_agent_payload(url, None)


def test_listen_node_repeats_after_15s_silence_and_carries_listen_marker(payload) -> None:
    listen = _nodes(payload)["listen"]
    assert listen["repeat_after_silence_seconds"] == 15
    assert listen.get("node_type", "llm") == "llm"
    assert parse_marker_block(_fill(listen["prompt"], ishara_call_id="c1")) == MarkerBlock(
        "c1", "listen"
    )
    assert SILENCE_MARKER in listen["prompt"]
    assert HOLDING_LINE in listen["prompt"]


def test_speak_prompt_substitutes_reply_and_turn(payload) -> None:
    speak = _nodes(payload)["speak"]
    filled = _fill(speak["prompt"], ishara_call_id="c1", turn_id="t7", reply_text="Yes, 10:30.")
    assert parse_marker_block(filled) == MarkerBlock("c1", "speak", "t7", "Yes, 10:30.")


def test_speak_node_cannot_be_interrupted(payload) -> None:
    assert _nodes(payload)["speak"]["number_of_words_for_interruption"] == 0
    assert "number_of_words_for_interruption" not in _nodes(payload)["listen"]


def test_listen_routes_only_on_events(payload) -> None:
    assert _edges(_nodes(payload)["listen"]) == {
        ("event", "user_reply", "speak"),
        ("event", "end_call", "goodbye"),
    }


def test_speak_accepts_another_send_or_end_and_otherwise_returns_to_listen(payload) -> None:
    assert _edges(_nodes(payload)["speak"]) == {
        ("event", "user_reply", "speak"),
        ("event", "end_call", "goodbye"),
        ("unconditional", None, "listen"),
    }


def test_goodbye_is_static_and_ends_the_call(payload) -> None:
    goodbye = _nodes(payload)["goodbye"]
    assert goodbye["node_type"] == "static"
    assert goodbye["static_message"] == GOODBYE
    assert goodbye["function_call"] == "end_call"
    assert goodbye["edges"] == []


def test_no_llm_routing_edges_anywhere(payload) -> None:
    for node in _nodes(payload).values():
        for edge in node["edges"]:
            assert edge["condition_type"] in {"event", "unconditional"}


def test_call_settings_keep_a_silent_receptionist_on_the_line(payload) -> None:
    config = _task(payload)["task_config"]
    assert config["call_terminate"] == CALL_TIMEOUT_S == 600
    assert config["hangup_after_silence"] >= config["call_terminate"]
    assert config["check_if_user_online"] is False


def test_agent_never_speaks_on_its_own(payload) -> None:
    config = _task(payload)["task_config"]
    assert config["backchanneling"] is False
    assert config["hangup_after_LLMCall"] is False
    assert config["voicemail"] is False


def test_voice_is_sarvam_bulbul_v4_flash_english(payload) -> None:
    synth = _task(payload)["tools_config"]["synthesizer"]
    assert synth["provider"] == "sarvam"
    assert synth["provider_config"]["model"] == "bulbul:v4-flash"
    assert synth["provider_config"]["language"] == "en"
    assert synth["provider_config"]["voice_id"].split("_")[1] == "en"


def test_transcriber_is_deepgram_nova3_indian_english(payload) -> None:
    transcriber = _task(payload)["tools_config"]["transcriber"]
    assert (transcriber["provider"], transcriber["model"], transcriber["language"]) == (
        "deepgram",
        "nova-3",
        "en-IN",
    )


def test_webhook_url_passes_through() -> None:
    hook = "https://ishara.example.com/bolna/webhook"
    assert build_agent_payload(BASE_URL, hook)["agent_config"]["webhook_url"] == hook
    assert build_agent_payload(BASE_URL, None)["agent_config"]["webhook_url"] is None


def _keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [k for key, item in value.items() for k in [key, *_keys(item)]]
    if isinstance(value, list):
        return [k for item in value for k in _keys(item)]
    return []


def test_payload_holds_no_credential_fields(payload) -> None:
    suspicious = [k for k in _keys(payload) if "key" in k or "token" in k or "auth" in k]
    assert suspicious == ["max_tokens"]
