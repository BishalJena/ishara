from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

import httpx
import pytest
from pydantic import SecretStr

from app.composer import (
    LLM_TIMEOUT_S,
    SYSTEM_PROMPT,
    GroqComposer,
    TemplateComposer,
    build_composer,
)
from app.groq_client import GroqClient
from app.protocol import ComposeRequest, DraftSource, Sign
from app.templates import compose_template
from tests.conftest import make_settings

T3_CAPTION = "We have 4 pm tomorrow. Does that work?"
T5_CAPTION = "Yes, 10:30 tomorrow morning."

# (turn, chips, caption, PLAN §1 LLM wording, template wording)
SCRIPT = [
    (
        "T1",
        ["hello", "doctor", "tomorrow"],
        None,
        "Hello, I'd like a doctor's appointment tomorrow.",
        "Hello, I'd like a doctor's appointment tomorrow.",
    ),
    (
        "T3",
        ["no", "morning"],
        T3_CAPTION,
        "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
        "No, sorry, that doesn't work. Is there anything in the morning?",
    ),
    (
        "T5",
        ["yes", "thankyou"],
        T5_CAPTION,
        "Yes, 10:30 tomorrow morning works. Thank you.",
        "Yes, that works. Thank you.",
    ),
]
SCRIPT_IDS = [row[0] for row in SCRIPT]

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def request_for(
    chips: list[Sign], caption: str | None = None, turn_id: str = "turn-7"
) -> ComposeRequest:
    return ComposeRequest(
        turn_id=turn_id, chips=chips, purpose="doctor_appointment", last_caption=caption
    )


def reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def composer_with(handler: Handler, timeout_s: float = LLM_TIMEOUT_S) -> GroqComposer:
    client = GroqClient(
        SecretStr("test-key"), "openai/gpt-oss-120b", transport=httpx.MockTransport(handler)
    )
    return GroqComposer(client, timeout_s=timeout_s)


# ---- script turns ----


@pytest.mark.parametrize(("turn", "chips", "caption", "llm", "template"), SCRIPT, ids=SCRIPT_IDS)
async def test_script_turn_llm_wording_is_used(
    turn: str, chips: list[Sign], caption: str | None, llm: str, template: str
) -> None:
    composer = composer_with(lambda _: reply(f"  {llm}\n"))
    draft = await composer.compose(request_for(chips, caption, turn_id=turn))
    assert (draft.turn_id, draft.text, draft.source) == (turn, llm, DraftSource.LLM)


@pytest.mark.parametrize(("turn", "chips", "caption", "llm", "template"), SCRIPT, ids=SCRIPT_IDS)
async def test_script_turn_template_path(
    turn: str, chips: list[Sign], caption: str | None, llm: str, template: str
) -> None:
    request = request_for(chips, caption, turn_id=turn)
    for composer in (GroqComposer(None), TemplateComposer()):
        draft = await composer.compose(request)
        assert (draft.turn_id, draft.text, draft.source) == (turn, template, DraftSource.TEMPLATE)


@pytest.mark.parametrize(
    "bad_llm",
    [
        "No, sorry, 5 pm doesn't work. Is there anything tomorrow morning?",
        "No, sorry. Is there anything on Monday morning?",
        "Sorry, 4 pm is hard. Is there anything tomorrow morning?",
        '"No, sorry, 4 pm doesn\'t work. Is there anything tomorrow morning?"',
    ],
    ids=["invented-time", "invented-day", "missing-no", "quoted"],
)
async def test_rejected_llm_draft_falls_back_to_template(bad_llm: str) -> None:
    draft = await composer_with(lambda _: reply(bad_llm)).compose(
        request_for(["no", "morning"], T3_CAPTION)
    )
    assert draft.source == DraftSource.TEMPLATE
    assert draft.text == "No, sorry, that doesn't work. Is there anything in the morning?"


# Issue #62: the 25-word limit applies to LLM drafts only. With many plain-phrase signs the
# template itself runs longer (40 words here) and is still the fallback.
LONG_CHIPS: list[Sign] = ["no", "doctor", "time", "callonphone", "can", "see", "who", "drink"]
LLM_25_WORDS = (
    "No, sorry, that slot is hard. Can I see a doctor? "
    "What time is free, who should I call, and can I bring a drink?"
)
LLM_26_WORDS = LLM_25_WORDS.replace("is hard", "is really hard")


async def test_llm_draft_of_25_words_is_used() -> None:
    assert len(LLM_25_WORDS.split()) == 25
    draft = await composer_with(lambda _: reply(LLM_25_WORDS)).compose(request_for(LONG_CHIPS))
    assert (draft.text, draft.source) == (LLM_25_WORDS, DraftSource.LLM)


async def test_llm_draft_over_25_words_falls_back_to_the_longer_template() -> None:
    assert len(LLM_26_WORDS.split()) == 26
    draft = await composer_with(lambda _: reply(LLM_26_WORDS)).compose(request_for(LONG_CHIPS))
    assert draft.source == DraftSource.TEMPLATE
    assert draft.text == compose_template(LONG_CHIPS, "doctor_appointment")
    assert len(draft.text.split()) == 40


async def test_prompt_carries_chips_purpose_and_caption() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return reply("No, sorry. Is there anything in the morning?")

    await composer_with(handler).compose(request_for(["no", "no", "morning"], T3_CAPTION))
    (body,) = bodies
    system, user = body["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert json.loads(user["content"]) == {
        "chips": ["no", "morning"],
        "purpose": "asking a clinic for a doctor's appointment",
        "receptionist_last_said": T3_CAPTION,
    }


# ---- provider failures ----


async def test_timeout_falls_back_to_template_within_budget() -> None:
    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return reply("Hello.")

    started = time.perf_counter()
    draft = await composer_with(slow, timeout_s=0.05).compose(request_for(["hello"]))
    assert time.perf_counter() - started < 1
    assert (draft.text, draft.source) == ("Hello.", DraftSource.TEMPLATE)


def test_default_llm_budget_is_one_and_a_half_seconds() -> None:
    assert LLM_TIMEOUT_S == 1.5
    assert GroqComposer(None).timeout_s == 1.5


async def test_http_500_falls_back_to_template() -> None:
    draft = await composer_with(lambda _: httpx.Response(500)).compose(request_for(["yes"]))
    assert (draft.text, draft.source) == ("Yes, that works.", DraftSource.TEMPLATE)


@pytest.mark.parametrize("body", [b"<html>oops</html>", b'{"choices": []}', b"{}"])
async def test_malformed_response_falls_back_to_template(body: bytes) -> None:
    composer = composer_with(lambda _: httpx.Response(200, content=body))
    draft = await composer.compose(request_for(["yes"]))
    assert (draft.text, draft.source) == ("Yes, that works.", DraftSource.TEMPLATE)


async def test_network_error_falls_back_to_template() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("down", request=request)

    draft = await composer_with(handler).compose(request_for(["no"]))
    assert draft.source == DraftSource.TEMPLATE


# ---- wiring ----


async def test_no_key_uses_templates_without_any_http_call() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return reply("Hello.")

    composer = build_composer(
        make_settings(groq_api_key=None), transport=httpx.MockTransport(handler)
    )
    assert isinstance(composer, TemplateComposer)
    draft = await composer.compose(request_for(["hello"]))
    assert (draft.text, draft.source) == ("Hello.", DraftSource.TEMPLATE)
    assert calls == []


async def test_key_present_uses_groq_with_configured_model() -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        models.append(json.loads(request.content)["model"])
        return reply("Hi.")

    settings = make_settings(groq_model="openai/gpt-oss-20b")
    composer = build_composer(settings, transport=httpx.MockTransport(handler))
    assert isinstance(composer, GroqComposer)
    draft = await composer.compose(request_for(["hello"]))
    assert (draft.text, draft.source) == ("Hi.", DraftSource.LLM)
    assert models == ["openai/gpt-oss-20b"]


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: reply("Hello."),
        lambda _: reply("Hello, 5 pm."),
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(200, content=b"nope"),
    ],
    ids=["llm", "rejected", "http-500", "malformed"],
)
async def test_turn_id_is_preserved_on_every_path(handler: Handler) -> None:
    draft = await composer_with(handler).compose(request_for(["hello"], turn_id="abc_123"))
    assert draft.turn_id == "abc_123"
