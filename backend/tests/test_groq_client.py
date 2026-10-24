from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.groq_client import MAX_COMPLETION_TOKENS, GroqClient, GroqError

KEY = "test-groq-secret"
MODEL = "openai/gpt-oss-120b"


def completion(content: object = "Hello.", finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }


def client_for(
    handler: Callable[[httpx.Request], httpx.Response], model: str = MODEL
) -> GroqClient:
    return GroqClient(SecretStr(KEY), model, transport=httpx.MockTransport(handler))


async def test_sends_an_openai_compatible_request_groq_accepts() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completion("Hello."))

    assert await client_for(handler).complete("sys", "usr") == "Hello."
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": MODEL,
        "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
        "temperature": 0,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "stream": False,
        "reasoning_effort": "low",
        "include_reasoning": False,
    }


def test_reasoning_fields_only_for_gpt_oss_models() -> None:
    body = GroqClient(SecretStr(KEY), "llama-3.3-70b-versatile").payload("s", "u")
    assert "reasoning_effort" not in body and "include_reasoning" not in body


def test_never_sends_fields_groq_rejects() -> None:
    body = GroqClient(SecretStr(KEY), MODEL).payload("s", "u")
    assert not {"logprobs", "logit_bias", "top_logprobs", "n"} & body.keys()
    assert all(set(m) == {"role", "content"} for m in body["messages"])


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
async def test_http_errors_raise_groq_error(status: int) -> None:
    client = client_for(lambda _: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(GroqError, match=f"HTTP {status}"):
        await client.complete("s", "u")


async def test_network_error_raises_groq_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(GroqError, match="ConnectError"):
        await client_for(handler).complete("s", "u")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"not json", "malformed"),
        (json.dumps({"choices": []}).encode(), "malformed"),
        (json.dumps({"object": "chat.completion"}).encode(), "malformed"),
        (json.dumps({"choices": [{"text": "Hi"}]}).encode(), "malformed"),
        (json.dumps(completion(content=None)).encode(), "empty"),
        (json.dumps(completion(content="")).encode(), "empty"),
        (json.dumps(completion(finish_reason="length")).encode(), "token limit"),
    ],
)
async def test_unusable_responses_raise_groq_error(body: bytes, message: str) -> None:
    client = client_for(lambda _: httpx.Response(200, content=body))
    with pytest.raises(GroqError, match=message):
        await client.complete("s", "u")


async def test_key_never_appears_in_errors_or_repr() -> None:
    errors: list[str] = []
    for status in (401, 500):
        client = client_for(lambda _, s=status: httpx.Response(s, text=f"bad key {KEY}"))
        with pytest.raises(GroqError) as info:
            await client.complete("s", "u")
        errors.append(str(info.value))
    assert all(KEY not in e for e in errors)
    assert KEY not in repr(GroqClient(SecretStr(KEY), MODEL).__dict__)
