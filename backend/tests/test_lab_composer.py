"""The Sign Lab composer: production drafting with every decision logged.
Groq is an httpx.MockTransport; nothing reaches the network."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.composer import GroqComposer, TemplateComposer
from app.protocol import ComposeRequest, DraftSource
from scripts.lab_composer import LabGroqClient, build_lab_composer

TEMPLATE_T1 = "Hello, I'd like a doctor's appointment tomorrow."
LLM_T1 = "Hi, could I book a doctor's appointment for tomorrow?"
T2 = "We have 4 pm tomorrow. Does that work?"


def request(*chips: str, caption: str | None = None) -> ComposeRequest:
    return ComposeRequest(
        turn_id="t1", chips=list(chips), purpose="doctor_appointment", last_caption=caption
    )


def groq_says(content: str, seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handler(http_request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(http_request)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


def groq_composer(transport: httpx.MockTransport, logs: list[str], model: str = "m/test"):
    return build_lab_composer(
        "groq", log=logs.append, groq_key=SecretStr("k"), groq_model=model, transport=transport
    )


async def test_templates_choice_uses_the_production_template_composer() -> None:
    logs: list[str] = []
    composer = build_lab_composer("templates", log=logs.append)
    assert isinstance(composer.inner, TemplateComposer)
    draft = await composer.compose(request("hello", "doctor", "tomorrow"))
    assert (draft.text, draft.source) == (TEMPLATE_T1, DraftSource.TEMPLATE)
    assert logs[0] == "chips: hello · doctor · tomorrow (receptionist last said: nothing yet)"
    assert logs[1].startswith("draft (template, ")
    assert logs[1].endswith(f" s): {TEMPLATE_T1}")
    assert len(logs) == 2


async def test_groq_choice_uses_the_production_groq_composer_with_the_given_key_and_model() -> None:
    seen: list[httpx.Request] = []
    logs: list[str] = []
    composer = groq_composer(groq_says(f"  {LLM_T1}\n", seen), logs, model="openai/gpt-oss-120b")
    assert isinstance(composer.inner, GroqComposer)
    draft = await composer.compose(request("hello", "doctor", "tomorrow"))
    assert (draft.text, draft.source) == (LLM_T1, DraftSource.LLM)
    [sent] = seen
    assert sent.headers["authorization"] == "Bearer k"
    assert json.loads(sent.content)["model"] == "openai/gpt-oss-120b"
    assert logs[1].startswith("groq answered in ")
    assert logs[1].endswith(f" s: {LLM_T1}")
    assert logs[2].startswith("draft (llm, ")
    assert len(logs) == 3


async def test_rejected_llm_draft_falls_back_with_the_validator_reasons_logged() -> None:
    logs: list[str] = []
    invented = "No, sorry. Is Friday at 9 possible?"
    composer = groq_composer(groq_says(invented), logs)
    draft = await composer.compose(request("no", "morning", caption=T2))
    assert draft.source == DraftSource.TEMPLATE
    assert logs[0] == f'chips: no · morning (receptionist last said: "{T2}")'
    assert logs[1].endswith(f" s: {invented}")  # the raw answer, before the validator
    assert logs[2].startswith("draft (template, ")
    [fallback] = logs[3:]
    assert fallback.startswith("  fallback: LLM draft rejected (")
    assert "invented day: friday" in fallback
    assert "missing meaning: morning" in fallback
    assert fallback.endswith("), using template")


async def test_slow_groq_falls_back_after_the_production_budget() -> None:
    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        raise AssertionError("cancelled before this")

    logs: list[str] = []
    composer = groq_composer(httpx.MockTransport(slow), logs)
    assert isinstance(composer.inner, GroqComposer)
    composer.inner.timeout_s = 0.05
    draft = await composer.compose(request("hello"))
    assert draft.source == DraftSource.TEMPLATE
    assert logs[-1] == "  fallback: LLM slower than 0.1 s, using template"


async def test_fallback_notes_stay_with_their_own_compose() -> None:
    """Two drafts in flight: each logs only its own fallback reason."""

    async def handler(http_request: httpx.Request) -> httpx.Response:
        user = json.loads(json.loads(http_request.content)["messages"][1]["content"])
        # The rejected draft answers last, after the good one has already logged.
        bad = user["chips"] == ["hello"]
        await asyncio.sleep(0.02 if bad else 0)
        content = "Hello, see you on Monday." if bad else "A doctor, please."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    logs: list[str] = []
    composer = groq_composer(httpx.MockTransport(handler), logs)
    rejected, accepted = await asyncio.gather(
        composer.compose(request("hello")), composer.compose(request("doctor"))
    )
    assert (rejected.source, accepted.source) == (DraftSource.TEMPLATE, DraftSource.LLM)
    drafts_and_notes = [line for line in logs if line.startswith(("draft", "  fallback"))]
    assert [line.split(" (")[0] for line in drafts_and_notes] == [
        "draft",  # doctor, llm: no fallback line after it
        "draft",  # hello, template
        "  fallback: LLM draft rejected",
    ]
    assert drafts_and_notes[0].startswith("draft (llm, ")
    assert drafts_and_notes[1].startswith("draft (template, ")


def test_groq_choice_without_a_key_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="key and a model"):
        build_lab_composer("groq", log=print, groq_key=None, groq_model="m")


async def test_lab_groq_client_logs_latency_from_its_clock() -> None:
    ticks = iter([1.0, 1.42])
    logs: list[str] = []
    client = LabGroqClient(
        SecretStr("k"), "m", log=logs.append, transport=groq_says("Hi"), clock=lambda: next(ticks)
    )
    assert await client.complete("system", "user") == "Hi"
    assert logs == ["groq answered in 0.42 s: Hi"]
