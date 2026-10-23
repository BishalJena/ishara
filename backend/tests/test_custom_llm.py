from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.custom_llm import stream_completion
from app.main import create_app
from app.markers import HOLDING_LINE, SILENCE_MARKER, render_marker_block
from app.shape_log import SHAPE_LOG_ENV
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, make_settings

URL = "/v1/chat/completions"
CALL = "call-1"
TURN = "t1"
REPLY = "No, sorry — 4 pm doesn't work.\nIs there anything tomorrow morning?"


class FakeLedger:
    """Single-use approvals, like the real CallLedger contract."""

    def __init__(self, approvals: dict[tuple[str, str], str] | None = None) -> None:
        self.approvals = dict(approvals or {})
        self.claimed: set[tuple[str, str]] = set()
        self.events: list[tuple[str, ...]] = []

    @property
    def captions(self) -> list[str]:
        return [event[2] for event in self.events if event[0] == "caption"]

    @property
    def spoken(self) -> list[tuple[str, str]]:
        return [(event[1], event[2]) for event in self.events if event[0] == "spoken"]

    async def record_caption(self, call_id: str, text: str) -> None:
        self.events.append(("caption", call_id, text))

    async def claim_reply(self, call_id: str, turn_id: str, text: str) -> bool:
        self.events.append(("claim", call_id, turn_id, text))
        key = (call_id, turn_id)
        if key in self.claimed or self.approvals.get(key) != text:
            return False
        self.claimed.add(key)
        return True

    async def mark_spoken(self, call_id: str, turn_id: str) -> None:
        self.events.append(("spoken", call_id, turn_id))


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def speak_prompt(reply: str = REPLY, call_id: str = CALL, turn_id: str = TURN) -> str:
    block = _fill(
        render_marker_block("speak"), ishara_call_id=call_id, turn_id=turn_id, reply_text=reply
    )
    return f"You relay a Deaf caller's approved reply.\n\n{block}\n\n## Conversation History"


def listen_prompt(call_id: str = CALL) -> str:
    block = _fill(render_marker_block("listen"), ishara_call_id=call_id)
    return f"Stay quiet.\n\n{block}\n\n## Conversation History"


def body(system: str, *turns: tuple[str, str], stream: bool = True, **extra: object) -> dict:
    messages = [{"role": "system", "content": system}]
    messages += [{"role": role, "content": content} for role, content in turns]
    return {"model": "ishara", "messages": messages, "stream": stream, **extra}


@pytest.fixture
def ledger() -> FakeLedger:
    return FakeLedger({(CALL, TURN): REPLY})


@pytest.fixture
def client(ledger: FakeLedger) -> TestClient:
    return TestClient(create_app(make_settings(), ledger=ledger))


def post(client: TestClient, payload: dict, token: str | None = CUSTOM_LLM_TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(URL, json=payload, headers=headers)


def reply_text(response) -> str:
    assert response.status_code == 200, response.text
    if response.headers["content-type"].startswith("text/event-stream"):
        events = [line for line in response.text.split("\n\n") if line]
        assert events[-1] == "data: [DONE]"
        chunks = [json.loads(event.removeprefix("data: ")) for event in events[:-1]]
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
        return "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["choices"][0]["finish_reason"] == "stop"
    return payload["choices"][0]["message"]["content"]


# ---- auth and request validation ----


@pytest.mark.parametrize("token", [None, "wrong", APP_TOKEN])
def test_rejects_missing_wrong_or_app_token(
    client: TestClient, ledger: FakeLedger, token: str | None
) -> None:
    assert post(client, body(speak_prompt()), token=token).status_code == 401
    assert ledger.events == []


def test_rejects_everything_when_server_token_unset(ledger: FakeLedger) -> None:
    client = TestClient(create_app(make_settings(custom_llm_token=None), ledger=ledger))
    assert post(client, body(speak_prompt()), token="None").status_code == 401
    assert ledger.events == []


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "m", "messages": []},
        {"model": "m"},
        {"messages": [{"content": "no role"}]},
        {"messages": "hello"},
        {"messages": [{"role": "user", "content": "hi"}], "stream": "sometimes"},
    ],
)
def test_malformed_body_is_422(client: TestClient, ledger: FakeLedger, payload: dict) -> None:
    assert post(client, payload).status_code == 422
    assert ledger.events == []


def test_unknown_fields_are_tolerated(client: TestClient, ledger: FakeLedger) -> None:
    payload = body(
        speak_prompt(),
        stream_options={"include_usage": True},
        stop=["User:"],
        chat_template_kwargs={"enable_thinking": False},
        max_tokens=150,
    )
    assert reply_text(post(client, payload)) == REPLY


# ---- speak node ----


@pytest.mark.parametrize(
    "text",
    [
        REPLY,
        "  spaces around  ",
        "Quotes \"double\", 'single', back\\slash, tab\tand CRLF\r\n",
        "Hindi नमस्ते and 🙏",
        "Yes.",
    ],
)
def test_speak_streams_approved_text_verbatim_then_marks_spoken(text: str) -> None:
    ledger = FakeLedger({(CALL, TURN): text})
    client = TestClient(create_app(make_settings(), ledger=ledger))
    response = post(client, body(speak_prompt(text), ("user", "Which day suits you?")))
    assert response.headers["content-type"].startswith("text/event-stream")
    assert reply_text(response) == text
    assert ledger.events[-2:] == [("claim", CALL, TURN, text), ("spoken", CALL, TURN)]


def test_speak_non_stream_returns_completion_and_marks_spoken(
    client: TestClient, ledger: FakeLedger
) -> None:
    response = post(client, body(speak_prompt(), stream=False))
    assert response.headers["content-type"] == "application/json"
    assert reply_text(response) == REPLY
    assert response.json()["model"] == "ishara"
    assert ledger.spoken == [(CALL, TURN)]


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    ("turn_id", "text"),
    [("unknown-turn", REPLY), (TURN, REPLY + " And one more thing.")],
    ids=["unapproved turn", "text differs from approval"],
)
def test_refused_claim_speaks_nothing(
    client: TestClient, ledger: FakeLedger, stream: bool, turn_id: str, text: str
) -> None:
    response = post(client, body(speak_prompt(text, turn_id=turn_id), stream=stream))
    assert reply_text(response) == ""
    assert ledger.spoken == []


def test_stale_speak_request_still_forwards_the_new_caption(
    client: TestClient, ledger: FakeLedger
) -> None:
    # Ledger B24: after a skipped speak, Bolna stays on the speak node and answers the
    # receptionist's next words with the old prompt. The claim is refused, but the
    # words must still reach the app as a caption.
    payload = body(speak_prompt(turn_id="undelivered-turn"), ("user", "Sorry, go ahead."))

    assert reply_text(post(client, payload)) == ""
    assert ledger.captions == ["Sorry, go ahead."]
    assert ledger.spoken == []


@pytest.mark.parametrize("stream", [True, False])
def test_same_turn_is_spoken_only_once(
    client: TestClient, ledger: FakeLedger, stream: bool
) -> None:
    first = post(client, body(speak_prompt(), stream=stream))
    second = post(client, body(speak_prompt(), ("assistant", REPLY), stream=stream))
    assert [reply_text(first), reply_text(second)] == [REPLY, ""]
    assert ledger.spoken == [(CALL, TURN)]


async def test_mark_spoken_runs_only_after_the_whole_stream() -> None:
    calls: list[str] = []

    async def on_complete() -> None:
        calls.append("done")

    stream = stream_completion("m", "One two three.", on_complete)
    events = [await anext(stream) for _ in range(4)]
    assert calls == []
    events += [event async for event in stream]
    assert events[-1] == "data: [DONE]\n\n"
    assert calls == ["done"]


async def test_abandoned_stream_never_marks_spoken() -> None:
    calls: list[str] = []

    async def on_complete() -> None:
        calls.append("done")

    stream = stream_completion("m", "One two three.", on_complete)
    await anext(stream)
    await stream.aclose()
    assert calls == []


def test_unfilled_reply_block_is_not_a_speak_request(
    client: TestClient, ledger: FakeLedger
) -> None:
    unfilled = _fill(render_marker_block("speak"), ishara_call_id=CALL, turn_id=TURN)
    assert "{{reply_text}}" in unfilled
    response = post(client, body(unfilled, ("user", "Hello?")))
    assert reply_text(response) == ""
    assert ledger.events == []


def test_marker_found_in_a_later_system_message(client: TestClient, ledger: FakeLedger) -> None:
    payload = body("Speak in English.", ("system", speak_prompt()))
    assert reply_text(post(client, payload)) == REPLY


# ---- listen node and captions ----


def test_listen_stays_quiet_and_forwards_caption(client: TestClient, ledger: FakeLedger) -> None:
    response = post(client, body(listen_prompt(), ("user", "City Clinic, how can I help?")))
    assert reply_text(response) == ""
    assert ledger.events == [("caption", CALL, "City Clinic, how can I help?")]


@pytest.mark.parametrize("marker", [SILENCE_MARKER, f"  {SILENCE_MARKER}\n"])
def test_silence_gets_holding_line_and_no_caption(
    client: TestClient, ledger: FakeLedger, marker: str
) -> None:
    first = post(client, body(listen_prompt(), ("user", "Hello?")))
    assert reply_text(first) == ""
    silence = body(listen_prompt(), ("user", "Hello?"), ("assistant", ""), ("user", marker))
    assert reply_text(post(client, silence)) == HOLDING_LINE
    assert ledger.captions == ["Hello?"]
    assert all(event[0] == "caption" for event in ledger.events)


def test_holding_line_only_when_latest_user_message_is_silence(
    client: TestClient, ledger: FakeLedger
) -> None:
    payload = body(listen_prompt(), ("user", SILENCE_MARKER), ("user", "Are you there?"))
    assert reply_text(post(client, payload)) == ""
    assert ledger.captions == ["Are you there?"]


def test_caption_forwarded_once_across_resent_history(
    client: TestClient, ledger: FakeLedger
) -> None:
    history = [("user", "Hello?"), ("assistant", HOLDING_LINE)]
    post(client, body(listen_prompt(), *history[:1]))
    post(client, body(listen_prompt(), *history))
    post(client, body(listen_prompt(), *history, ("user", SILENCE_MARKER)))
    assert ledger.captions == ["Hello?"]

    post(client, body(listen_prompt(), *history, ("user", "Is 4 pm okay?")))
    post(client, body(listen_prompt(), *history, ("user", "Is 4 pm okay?")))
    assert ledger.captions == ["Hello?", "Is 4 pm okay?"]


def test_same_words_said_again_are_a_new_caption(client: TestClient, ledger: FakeLedger) -> None:
    post(client, body(listen_prompt(), ("user", "Okay.")))
    post(client, body(listen_prompt(), ("user", "Okay."), ("assistant", "Yes."), ("user", "Okay.")))
    assert ledger.captions == ["Okay.", "Okay."]


def test_assistant_messages_are_never_forwarded(client: TestClient, ledger: FakeLedger) -> None:
    payload = body(
        listen_prompt(),
        ("assistant", "Hello, I'm calling for a Deaf caller."),
        ("user", "Sure."),
        ("assistant", REPLY),
    )
    post(client, payload)
    assert ledger.captions == ["Sure."]


def test_captions_are_tracked_per_call(client: TestClient, ledger: FakeLedger) -> None:
    post(client, body(listen_prompt("call-a"), ("user", "Hello?")))
    post(client, body(listen_prompt("call-b"), ("user", "Hello?")))
    callers = [event[1] for event in ledger.events if event[0] == "caption"]
    assert callers == ["call-a", "call-b"]


def test_speak_request_also_records_new_captions(client: TestClient, ledger: FakeLedger) -> None:
    post(client, body(listen_prompt(), ("user", "Which day?")))
    payload = body(speak_prompt(), ("user", "Which day?"), ("user", "Morning or evening?"))
    assert reply_text(post(client, payload)) == REPLY
    assert ledger.captions == ["Which day?", "Morning or evening?"]
    assert ledger.events.index(("caption", CALL, "Morning or evening?")) < ledger.events.index(
        ("claim", CALL, TURN, REPLY)
    )


# ---- requests without a marker block ----


ROUTING_TOOLS = [
    {"type": "function", "function": {"name": "transition_to_speak"}},
    {"type": "function", "function": {"name": "stay_on_current_node"}},
]


@pytest.mark.parametrize(
    "payload",
    [
        body(f"Routing Guidelines: \n x\n Node Objective: {speak_prompt()}", ("user", "Hi")),
        body(speak_prompt(), ("user", "Hi"), tools=ROUTING_TOOLS[:1]),
        body(speak_prompt(), ("user", "Hi"), tools=ROUTING_TOOLS[1:]),
        body(speak_prompt(), ("user", "Hi"), tool_choice="required"),
        body(listen_prompt(), ("user", SILENCE_MARKER), tools=ROUTING_TOOLS),
    ],
    ids=["routing prompt", "transition tool", "stay tool", "tool_choice required", "listen"],
)
@pytest.mark.parametrize("stream", [True, False])
def test_routing_requests_never_speak_claim_or_caption(
    client: TestClient, ledger: FakeLedger, payload: dict, stream: bool
) -> None:
    response = post(client, {**payload, "stream": stream})
    text = reply_text(response)
    assert text == ""
    assert "tool_calls" not in response.text
    assert ledger.events == []


def test_other_tools_do_not_block_a_speak_reply(client: TestClient) -> None:
    tools = [{"type": "function", "function": {"name": "end_call"}}]
    assert reply_text(post(client, body(speak_prompt(), tools=tools, tool_choice="auto"))) == REPLY


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        (
            'Is the call complete?\nRespond only in this JSON format: {"hangup": "Yes" or "No"}',
            {"hangup": "No"},
        ),
        (
            'Voicemail?\nRespond only in this JSON format: {"is_voicemail": "Yes" or "No"}',
            {"is_voicemail": "No"},
        ),
    ],
    ids=["hangup check", "voicemail check"],
)
def test_checks_get_a_json_no(
    client: TestClient, ledger: FakeLedger, system: str, expected: dict
) -> None:
    payload = body(system, ("user", f"assistant: {REPLY}\nuser: Okay bye"), stream=False)
    assert json.loads(reply_text(post(client, payload))) == expected
    assert ledger.events == []


def test_unknown_request_gets_empty_reply(client: TestClient, ledger: FakeLedger) -> None:
    payload = body("Summarise this call.", ("user", f"assistant: {REPLY}"))
    assert reply_text(post(client, payload)) == ""
    assert ledger.events == []


# ---- shape log ----


def test_shape_log_has_no_transcript_reply_or_token(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = tmp_path / "shapes.jsonl"
    monkeypatch.setenv(SHAPE_LOG_ENV, str(target))
    caption = "Doctor Rao is free at 4 pm"
    with caplog.at_level(logging.INFO, logger="app.shape_log"):
        post(client, body(listen_prompt(), ("user", caption)))
        post(client, body(speak_prompt(), ("user", caption)))
        post(client, body(listen_prompt(), ("user", caption), ("user", SILENCE_MARKER)))
    lines = target.read_text().splitlines()
    shapes = [json.loads(line) for line in lines]
    assert [(s["kind"], s["node"], s["outcome"]) for s in shapes] == [
        ("listen", "listen", "silent"),
        ("speak", "speak", "reply"),
        ("listen", "listen", "holding_line"),
    ]
    logged = "\n".join(lines + [record.getMessage() for record in caplog.records])
    for secret in (caption, "Doctor Rao", REPLY, "4 pm doesn't", HOLDING_LINE, CUSTOM_LLM_TOKEN):
        assert secret not in logged
