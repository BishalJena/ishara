"""FakeBolna against a tiny stub custom LLM, so the fake is trusted before the E2E uses it."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.markers import (
    DISCLOSURE,
    GOODBYE,
    HOLDING_LINE,
    SILENCE_MARKER,
    MarkerBlock,
    parse_marker_block,
)
from fakes.fake_bolna import (
    LLM_PATH,
    WEBHOOK_PATH,
    FakeBolna,
    RunEnded,
    SentEvent,
    asgi_client,
    substitute,
)
from fakes.sse import collect_stream_text

TOKEN = "stub-llm-token"
CALL_ID = "call-1"
RECIPIENT = "+910000000011"
REPLY = "No, sorry, 4 pm doesn't work.\nIs there anything tomorrow morning?"


def _sse(text: str) -> Iterator[str]:
    def chunk(delta: dict[str, str]) -> str:
        return "data: " + json.dumps({"choices": [{"index": 0, "delta": delta}]}) + "\n\n"

    yield chunk({"role": "assistant"})
    for start in range(0, len(text), 3):
        yield chunk({"content": text[start : start + 3]})
    yield "data: [DONE]\n\n"


class StubLLM:
    """Minimal custom LLM: quiet on listen, holding line on silence, echo on speak."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.media_type = "text/event-stream"
        self.fail_status: int | None = None
        self.webhooks: list[dict] = []
        self.app = FastAPI()
        self.app.post(LLM_PATH)(self._chat)
        self.app.post(WEBHOOK_PATH)(self._webhook)

    async def _webhook(self, secret: str, request: Request) -> None:
        if secret != TOKEN:
            raise HTTPException(404)
        self.webhooks.append(await request.json())

    async def _chat(self, request: Request) -> StreamingResponse:
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            raise HTTPException(401)
        if self.fail_status:
            raise HTTPException(self.fail_status)
        body = await request.json()
        self.received.append(body)
        block = parse_marker_block(body["messages"][0]["content"])
        assert block is not None
        if block.node == "speak":
            reply = block.reply_text or ""
        elif body["messages"][-1] == {"role": "user", "content": SILENCE_MARKER}:
            reply = HOLDING_LINE
        else:
            reply = ""
        return StreamingResponse(_sse(reply), media_type=self.media_type)

    def blocks(self) -> list[MarkerBlock | None]:
        return [parse_marker_block(body["messages"][0]["content"]) for body in self.received]


@pytest.fixture
def stub() -> StubLLM:
    return StubLLM()


@pytest.fixture
def fake(stub: StubLLM) -> FakeBolna:
    return FakeBolna(TOKEN, asgi_client(stub.app))


async def _start(fake: FakeBolna) -> str:
    return await fake.start_call(RECIPIENT, {"ishara_call_id": CALL_ID})


def _reply_props(turn_id: str = "t1", text: str = REPLY) -> dict[str, str]:
    return {"reply_text": text, "turn_id": turn_id}


# ---- calls and the listen node ----


async def test_start_call_records_recipient_and_speaks_disclosure(fake: FakeBolna) -> None:
    user_data = {"ishara_call_id": CALL_ID}
    first = await fake.start_call(RECIPIENT, user_data)
    second = await fake.start_call("+910000000012", {"ishara_call_id": "call-2"})
    user_data["ishara_call_id"] = "mutated"

    assert first != second
    assert fake.recipients == [RECIPIENT, "+910000000012"]
    assert fake.spoken == [DISCLOSURE, DISCLOSURE]
    assert fake.run(first).user_data == {"ishara_call_id": CALL_ID}
    assert fake.run(first).node == "listen"


async def test_answered_call_reports_ringing_then_in_progress_to_the_webhook(
    fake: FakeBolna, stub: StubLLM
) -> None:
    run_id = await _start(fake)
    assert stub.webhooks == [], "statuses arrive after start_call returns the run id"

    run = await fake.run_for_call(CALL_ID)

    assert run.run_id == run_id
    assert stub.webhooks == [
        {"id": run_id, "status": "ringing"},
        {"id": run_id, "status": "in-progress"},
    ]
    assert fake.statuses == [(run_id, "ringing"), (run_id, "in-progress")]


async def test_status_reports_can_be_turned_off(stub: StubLLM) -> None:
    fake = FakeBolna(TOKEN, asgi_client(stub.app), report_status=False)
    run_id = await _start(fake)
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()

    assert stub.webhooks == []
    assert fake.statuses == []


async def test_rejected_status_report_fails_the_run(stub: StubLLM) -> None:
    fake = FakeBolna("wrong-token", asgi_client(stub.app))
    await _start(fake)

    with pytest.raises(httpx.HTTPStatusError):
        await fake.run_for_call(CALL_ID)
    assert fake.statuses == []


async def test_receptionist_utterance_posts_listen_prompt_and_stays_quiet(
    fake: FakeBolna, stub: StubLLM
) -> None:
    run_id = await _start(fake)

    reply = await fake.receptionist_says(run_id, "We have 4 pm tomorrow.")

    assert reply == ""
    assert fake.spoken == [DISCLOSURE]
    (body,) = stub.received
    assert body["stream"] is True
    assert stub.blocks() == [MarkerBlock(CALL_ID, "listen")]
    assert body["messages"][1:] == [
        {"role": "assistant", "content": DISCLOSURE},
        {"role": "user", "content": "We have 4 pm tomorrow."},
    ]


async def test_silence_marker_gets_holding_line_spoken(fake: FakeBolna, stub: StubLLM) -> None:
    run_id = await _start(fake)

    assert await fake.silence(run_id) == HOLDING_LINE

    assert stub.received[-1]["messages"][-1] == {"role": "user", "content": SILENCE_MARKER}
    assert fake.spoken == [DISCLOSURE, HOLDING_LINE]
    assert fake.run(run_id).history[-1] == {"role": "assistant", "content": HOLDING_LINE}


async def test_receptionist_cannot_talk_on_unknown_run(fake: FakeBolna) -> None:
    with pytest.raises(KeyError):
        await fake.receptionist_says("no-such-run", "Hello?")


# ---- user_reply events and the speak node ----


async def test_user_reply_is_published_first_then_spoken_verbatim(
    fake: FakeBolna, stub: StubLLM
) -> None:
    run_id = await _start(fake)

    await fake.send_event(run_id, "user_reply", _reply_props())
    assert fake.spoken == [DISCLOSURE], "send_event must return before anything is spoken"
    await fake.wait_idle()

    assert fake.spoken == [DISCLOSURE, REPLY]
    assert stub.blocks() == [MarkerBlock(CALL_ID, "speak", "t1", REPLY)]
    assert fake.events == [SentEvent(run_id, "user_reply", _reply_props())]
    assert fake.run(run_id).node == "listen"


async def test_spoken_reply_is_in_the_next_listen_history(fake: FakeBolna, stub: StubLLM) -> None:
    run_id = await _start(fake)
    await fake.send_event(run_id, "user_reply", _reply_props())
    await fake.wait_idle()

    await fake.receptionist_says(run_id, "Yes, 10:30 tomorrow morning.")

    assert stub.blocks()[-1] == MarkerBlock(CALL_ID, "listen")
    assert stub.received[-1]["messages"][-2:] == [
        {"role": "assistant", "content": REPLY},
        {"role": "user", "content": "Yes, 10:30 tomorrow morning."},
    ]


async def test_mid_speech_event_moves_to_speak_without_speaking(
    fake: FakeBolna, stub: StubLLM
) -> None:
    run_id = await _start(fake)
    fake.receptionist_mid_speech = True

    await fake.send_event(run_id, "user_reply", _reply_props())
    await fake.wait_idle()

    assert stub.received == []
    assert fake.spoken == [DISCLOSURE]
    assert fake.run(run_id).node == "speak"
    assert len(fake.events) == 1


async def test_after_mid_speech_skip_next_utterance_uses_stale_speak_prompt(
    fake: FakeBolna, stub: StubLLM
) -> None:
    run_id = await _start(fake)
    fake.receptionist_mid_speech = True
    await fake.send_event(run_id, "user_reply", _reply_props())
    await fake.wait_idle()
    fake.receptionist_mid_speech = False

    await fake.receptionist_says(run_id, "Sorry, go ahead.")

    assert stub.blocks() == [MarkerBlock(CALL_ID, "speak", "t1", REPLY)]
    assert fake.run(run_id).node == "listen"


async def test_duplicate_delivery_posts_the_speak_request_twice(
    fake: FakeBolna, stub: StubLLM
) -> None:
    run_id = await _start(fake)
    fake.duplicate_events = True

    await fake.send_event(run_id, "user_reply", _reply_props())
    await fake.wait_idle()

    assert stub.blocks() == [MarkerBlock(CALL_ID, "speak", "t1", REPLY)] * 2
    assert len(fake.events) == 1


async def test_new_reply_replaces_previous_reply_text(fake: FakeBolna, stub: StubLLM) -> None:
    run_id = await _start(fake)
    await fake.send_event(run_id, "user_reply", _reply_props("t1", "First."))
    await fake.send_event(run_id, "user_reply", _reply_props("t2", "Second."))
    await fake.wait_idle()

    assert [block.turn_id for block in stub.blocks() if block] == ["t1", "t2"]
    assert fake.spoken == [DISCLOSURE, "First.", "Second."]


@pytest.mark.parametrize(
    ("event", "properties"),
    [
        ("speak_now", {}),
        ("user_reply", {"reply_text": "Hi"}),
        ("user_reply", {"turn_id": "t1"}),
    ],
)
async def test_events_outside_the_agent_graph_are_rejected(
    fake: FakeBolna, event: str, properties: dict[str, str]
) -> None:
    run_id = await _start(fake)

    with pytest.raises(ValueError):
        await fake.send_event(run_id, event, properties)

    assert fake.events == []


# ---- end of call ----


async def test_end_call_says_goodbye_and_ends_the_run(fake: FakeBolna, stub: StubLLM) -> None:
    run_id = await _start(fake)

    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()

    run = fake.run(run_id)
    assert (run.ended, run.node) == (True, "goodbye")
    assert fake.spoken == [DISCLOSURE, GOODBYE]
    assert stub.received == []
    assert stub.webhooks[-1] == {"id": run_id, "status": "completed"}


async def test_nothing_is_spoken_or_requested_after_the_end(fake: FakeBolna, stub: StubLLM) -> None:
    run_id = await _start(fake)
    await fake.send_event(run_id, "end_call", {})
    await fake.send_event(run_id, "user_reply", _reply_props())
    await fake.wait_idle()

    assert fake.spoken == [DISCLOSURE, GOODBYE]
    assert stub.received == []
    assert [sent.event for sent in fake.events] == ["end_call", "user_reply"]
    with pytest.raises(RunEnded):
        await fake.receptionist_says(run_id, "Hello?")


# ---- transport and failures ----


async def test_wrong_custom_llm_token_fails(stub: StubLLM) -> None:
    fake = FakeBolna("wrong-token", asgi_client(stub.app), report_status=False)
    run_id = await _start(fake)

    with pytest.raises(httpx.HTTPStatusError):
        await fake.receptionist_says(run_id, "Hello?")


async def test_non_streaming_reply_is_rejected(fake: FakeBolna, stub: StubLLM) -> None:
    stub.media_type = "application/json"
    run_id = await _start(fake)

    with pytest.raises(RuntimeError, match="SSE"):
        await fake.receptionist_says(run_id, "Hello?")


async def test_wait_idle_reraises_a_failed_delivery(fake: FakeBolna, stub: StubLLM) -> None:
    run_id = await _start(fake)
    stub.fail_status = 500

    await fake.send_event(run_id, "user_reply", _reply_props())

    with pytest.raises(httpx.HTTPStatusError):
        await fake.wait_idle()
    assert fake.spoken == [DISCLOSURE]


async def test_client_can_be_attached_after_construction(stub: StubLLM) -> None:
    fake = FakeBolna(TOKEN, report_status=False)
    run_id = await _start(fake)
    with pytest.raises(RuntimeError, match="attach"):
        await fake.silence(run_id)

    fake.attach(asgi_client(stub.app))

    assert await fake.silence(run_id) == HOLDING_LINE


async def test_latency_delays_each_custom_llm_request(fake: FakeBolna) -> None:
    run_id = await _start(fake)
    fake.latency_s = 0.05
    loop = asyncio.get_running_loop()

    started = loop.time()
    await fake.receptionist_says(run_id, "Hello?")

    assert loop.time() - started >= 0.05


async def test_run_for_call_finds_the_run_by_ishara_call_id(fake: FakeBolna) -> None:
    run_id = await _start(fake)

    assert (await fake.run_for_call(CALL_ID)).run_id == run_id
    with pytest.raises(TimeoutError):
        await fake.run_for_call("other-call", timeout_s=0.05)


# ---- helpers ----


def test_substitute_fills_known_variables_and_keeps_unknown() -> None:
    template = "{{ishara_call_id}} / {{turn_id}} / {{missing}}"

    assert (
        substitute(template, {"ishara_call_id": "c1", "turn_id": "t1"}) == "c1 / t1 / {{missing}}"
    )


async def _lines(*lines: str) -> AsyncIterator[str]:
    for line in lines:
        yield line


async def test_stream_text_joins_deltas_and_skips_non_text_chunks() -> None:
    lines = _lines(
        ": keep-alive",
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        "",
        'data: {"choices":[{"delta":{"content":"Hello, "}}]}',
        'data: {"choices":[{"delta":{"content":null}}]}',
        'data: {"choices":[{"delta":{"content":"doctor."},"finish_reason":"stop"}]}',
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":" after done"}}]}',
    )

    assert await collect_stream_text(lines) == "Hello, doctor."


async def test_stream_text_is_empty_for_a_quiet_reply() -> None:
    assert await collect_stream_text(_lines("data: [DONE]")) == ""


async def test_stream_text_rejects_malformed_chunks() -> None:
    with pytest.raises(json.JSONDecodeError):
        await collect_stream_text(_lines("data: {not json"))
