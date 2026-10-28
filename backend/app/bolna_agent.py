"""Builds the Bolna graph agent for Path B (PLAN.md §3). Pure: no network, no secrets.

The custom-LLM bearer token is registered with Bolna separately
(`POST /user/model/custom`); the agent only names the model, so the payload and the
committed `backend/bolna/agent.json` never hold a token. See backend/bolna/README.md.
"""

from __future__ import annotations

import json
from typing import Any

from app.markers import (
    DISCLOSURE,
    EVENT_END_CALL,
    EVENT_USER_REPLY,
    GOODBYE,
    HOLDING_LINE,
    SILENCE_MARKER,
    render_marker_block,
)

AGENT_NAME = "Ishara relay"
PLACEHOLDER_PUBLIC_BASE_URL = "https://YOUR-BACKEND.herokuapp.com"

LISTEN_NODE = "listen"
SPEAK_NODE = "speak"
GOODBYE_NODE = "goodbye"

# Name under which our endpoint is registered as a Bolna custom model; agents resolve
# the model by this name.
CUSTOM_LLM_MODEL = "ishara-relay"
CUSTOM_LLM_FAMILY = "llama"

SILENCE_REPEAT_S = 15
CALL_TIMEOUT_S = 600
# Bolna documents no "off" value for hangup-on-silence; matching the call timeout means
# it can never fire before the call ends anyway.
HANGUP_AFTER_SILENCE_S = CALL_TIMEOUT_S

# Bolna rejects "en-IN" for nova-3 (HTTP 400 on create, 23 Oct); plain "en" is accepted.
TRANSCRIBER_LANGUAGE = "en"
SARVAM_VOICE = "Simran (Sales)"
SARVAM_VOICE_ID = "simran_en_sales"
SARVAM_MODEL = "bulbul:v4-flash"
TELEPHONY_PROVIDER = "plivo"

AGENT_INFORMATION = (
    "You speak on a phone call for a Deaf caller who replies by signing in the Ishara "
    "app. Never add, guess or rephrase anything. Follow the current step exactly."
)

LISTEN_PROMPT = (
    f"{render_marker_block('listen')}\n\n"
    "Listen only. The caller is signing a reply. Reply with an empty message. "
    f"If the last message is {SILENCE_MARKER}, say exactly: {HOLDING_LINE}"
)

SPEAK_PROMPT = (
    f"{render_marker_block('speak')}\n\n"
    "Say exactly the text between ISHARA_REPLY_START and ISHARA_REPLY_END, word for "
    "word, and nothing else."
)


def custom_llm_base_url(public_base_url: str) -> str:
    """Bolna appends `/chat/completions` to the base URL; our route is under `/v1`."""
    return public_base_url.rstrip("/") + "/v1"


def _event_edge(event: str, to_node: str) -> dict[str, str]:
    return {"to_node_id": to_node, "condition_type": "event", "event_name": event}


def _nodes() -> list[dict[str, Any]]:
    return [
        {
            "id": LISTEN_NODE,
            "prompt": LISTEN_PROMPT,
            "repeat_after_silence_seconds": SILENCE_REPEAT_S,
            "edges": [
                _event_edge(EVENT_USER_REPLY, SPEAK_NODE),
                _event_edge(EVENT_END_CALL, GOODBYE_NODE),
            ],
        },
        {
            "id": SPEAK_NODE,
            "prompt": SPEAK_PROMPT,
            "number_of_words_for_interruption": 0,
            "edges": [
                # A second SEND before the receptionist answers must still match an edge;
                # an unmatched event is dropped without speech.
                _event_edge(EVENT_USER_REPLY, SPEAK_NODE),
                _event_edge(EVENT_END_CALL, GOODBYE_NODE),
                {"to_node_id": LISTEN_NODE, "condition_type": "unconditional"},
            ],
        },
        {
            "id": GOODBYE_NODE,
            "node_type": "static",
            "static_message": GOODBYE,
            "function_call": "end_call",
            "edges": [],
        },
    ]


def build_agent_payload(custom_llm_base_url: str, webhook_url: str | None) -> dict[str, Any]:
    """Body for `POST /v2/agent` and `PUT /v2/agent/{id}`."""
    if not custom_llm_base_url.startswith("https://") or custom_llm_base_url.endswith("/"):
        raise ValueError("custom_llm_base_url must be https:// with no trailing slash")
    llm_agent = {
        "agent_type": "graph_agent",
        "agent_flow_type": "streaming",
        "llm_config": {
            "provider": "custom",
            "model": CUSTOM_LLM_MODEL,
            "family": CUSTOM_LLM_FAMILY,
            "base_url": custom_llm_base_url,
            "max_tokens": 150,
            "temperature": 0,
            "agent_information": AGENT_INFORMATION,
            "current_node_id": LISTEN_NODE,
            "nodes": _nodes(),
        },
    }
    task = {
        "task_type": "conversation",
        "toolchain": {
            "execution": "parallel",
            "pipelines": [["transcriber", "llm", "synthesizer"]],
        },
        "tools_config": {
            "llm_agent": llm_agent,
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-3",
                "language": TRANSCRIBER_LANGUAGE,
                "stream": True,
                "encoding": "linear16",
            },
            "synthesizer": {
                "provider": "sarvam",
                "provider_config": {
                    "voice": SARVAM_VOICE,
                    "voice_id": SARVAM_VOICE_ID,
                    "model": SARVAM_MODEL,
                    "language": "en",
                    "speed": 1.0,
                },
                "stream": True,
                "caching": True,
                "buffer_size": 150,
                "audio_format": "wav",
            },
            "input": {"provider": TELEPHONY_PROVIDER, "format": "wav"},
            "output": {"provider": TELEPHONY_PROVIDER, "format": "wav"},
        },
        "task_config": {
            "call_terminate": CALL_TIMEOUT_S,
            "hangup_after_silence": HANGUP_AFTER_SILENCE_S,
            "check_if_user_online": False,
            "hangup_after_LLMCall": False,
            "voicemail": False,
            "backchanneling": False,
            # The receptionist's "Hello?" must not cut the disclosure or reach `listen`
            # while the Call-for-me opening is queued. Name taken from the live GET; the
            # create schema doesn't list it (dashboard: "Ignore user speech before
            # welcome message").
            "discard_pre_welcome_utterance": True,
        },
    }
    return {
        "agent_config": {
            "agent_name": AGENT_NAME,
            "agent_type": "other",
            "agent_welcome_message": DISCLOSURE,
            "webhook_url": webhook_url,
            # Off by default; Call-for-me notes read `summary` from the final webhook.
            "call_summary_enabled": True,
            "tasks": [task],
        },
        "agent_prompts": {"task_1": {"system_prompt": AGENT_INFORMATION}},
    }


def render_agent_json(payload: dict[str, Any]) -> str:
    """The exact text of the committed agent.json."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def placeholder_payload() -> dict[str, Any]:
    return build_agent_payload(custom_llm_base_url(PLACEHOLDER_PUBLIC_BASE_URL), None)
