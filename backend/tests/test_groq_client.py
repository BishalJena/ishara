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


async def test_planner_uses_a_closed_strict_schema_and_separate_token_budget() -> None:
    from app.groq_client import PLANNER_COMPLETION_TOKENS
    from app.steer_planner import PlannerTurn

    seen = []
    turn = {
        "action": {"kind": "need_caller", "question_id": "receiver:0"},
        "resolutions": [],
    }

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion(json.dumps(turn)))

    client = client_for(handler)
    try:
        assert (
            await client.complete_structured("system", "data", PlannerTurn)
        ).action.kind == "need_caller"
    finally:
        await client.aclose()
    body = seen[0]
    assert body["max_completion_tokens"] == PLANNER_COMPLETION_TOKENS > MAX_COMPLETION_TOKENS
    response_format = body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True

    def check_objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for child in node.values():
                check_objects(child)
        elif isinstance(node, list):
            for child in node:
                check_objects(child)

    check_objects(response_format["json_schema"]["schema"])


@pytest.mark.parametrize(
    "body", ["private provider response", '{"action":"secret-invalid-action"}']
)
async def test_structured_errors_never_expose_provider_text_in_traceback(body):
    import traceback

    from app.steer_planner import PlannerTurn

    client = client_for(lambda _: httpx.Response(200, json=completion(body)))
    try:
        with pytest.raises(GroqError) as error:
            await client.complete_structured("system", "data", PlannerTurn)
        assert error.value.category == "schema"
        rendered = "".join(traceback.format_exception(error.value))
        assert body not in rendered
        assert "secret-invalid-action" not in rendered
        assert "private provider response" not in rendered
    finally:
        await client.aclose()


async def test_unsupported_strict_model_never_makes_a_network_request():
    from app.steer_planner import PlannerTurn

    def unexpected_request(_):
        pytest.fail("An unsupported structured model must fail before HTTP")

    client = client_for(unexpected_request, model="unsupported")
    try:
        with pytest.raises(GroqError) as error:
            await client.complete_structured("system", "data", PlannerTurn)
        assert error.value.category == "unsupported_model"
    finally:
        await client.aclose()


async def test_unexpected_finish_reason_is_categorized_without_logging_provider_text(caplog):
    client = client_for(
        lambda _: httpx.Response(200, json=completion(finish_reason="private-finish-value"))
    )
    try:
        with caplog.at_level("INFO"), pytest.raises(GroqError) as error:
            await client.complete("system", "data")
        assert error.value.category == "finish_reason"
        assert "private-finish-value" not in caplog.text
        assert "finish=unexpected" in caplog.text
    finally:
        await client.aclose()


async def test_qwen_structured_planning_explicitly_hides_reasoning_and_uses_low_effort():
    from app.steer_planner import PlannerTurn

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        turn = {"action": {"kind": "need_caller", "question_id": "receiver:0"}, "resolutions": []}
        return httpx.Response(200, json=completion(json.dumps(turn)))

    client = client_for(handler, model="qwen/qwen3.8-27b")
    try:
        await client.complete_structured("system", "data", PlannerTurn)
    finally:
        await client.aclose()
    assert seen[0]["reasoning_format"] == "hidden"
    assert seen[0]["reasoning_effort"] == "low"
    assert "include_reasoning" not in seen[0]


async def test_validation_diagnostics_contain_only_schema_paths_and_error_types():
    from app.steer_planner import PlannerTurn

    turn = {
        "action": {"kind": "finish", "private-unknown-key": "private-input-value"},
        "resolutions": [],
    }
    client = client_for(lambda _: httpx.Response(200, json=completion(json.dumps(turn))))
    try:
        with pytest.raises(GroqError) as error:
            await client.complete_structured("system", "data", PlannerTurn)
        diagnostics = error.value.validation_errors
        assert diagnostics
        assert any("Finish.blocked:missing" in value for value in diagnostics)
        assert "private-unknown-key" not in repr(diagnostics)
        assert "private-input-value" not in repr(diagnostics)
        assert error.value.status_code is None
    finally:
        await client.aclose()


def test_action_specific_requirements_are_visible_in_nested_json_schema():
    from app.steer_planner import PlannerTurn

    schema = PlannerTurn.model_json_schema()
    assert "anyOf" not in schema
    assert len(schema["properties"]["action"]["anyOf"]) == 7
    assert set(schema["$defs"]["AnswerQuestion"]["required"]) == {"kind", "question_id", "spans"}
    assert set(schema["$defs"]["Finish"]["required"]) == {"kind", "blocked"}
    assert set(schema["$defs"]["NeedCaller"]["required"]) == {"kind", "question_id"}


async def test_compact_provider_schema_keeps_named_fields_and_validation_constraints():
    from pydantic import BaseModel, Field

    class Record(BaseModel):
        title: str = Field(min_length=2, max_length=40, description="A human-readable title")
        description: str | None = Field(default=None, description="An optional explanation")

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"title":"A task","description":null}'))

    client = client_for(handler)
    try:
        result = await client.complete_structured("Return a task record.", "Synthetic data", Record)
    finally:
        await client.aclose()
    assert result.title == "A task" and result.description is None
    schema = seen[0]["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == {"title", "description"}
    assert set(schema["required"]) == {"title", "description"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["title"] == {
        "minLength": 2,
        "maxLength": 40,
        "type": "string",
        "description": "A human-readable title",
    }
    assert schema["properties"]["description"]["description"] == "An optional explanation"
    assert "title" not in schema


@pytest.mark.parametrize(
    "header,expected",
    [("2", 2), ("120", 60), ("private-header", None), ("nan", None), ("-1", None)],
)
async def test_quota_retry_metadata_is_bounded_and_never_exposes_raw_headers(header, expected):
    client = client_for(lambda _: httpx.Response(429, headers={"retry-after": header}))
    try:
        with pytest.raises(GroqError) as error:
            await client.complete("system", "data")
        assert error.value.retry_after_s == expected
        assert str(error.value) == "HTTP 429"
    finally:
        await client.aclose()
