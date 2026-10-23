from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.bolna_client import BolnaError, HttpBolnaClient

API_KEY = "test-bolna-key-do-not-leak"
AGENT_ID = "123e4567-e89b-12d3-a456-426655440000"
RUN_ID = "b7140255-af33-4608-8e97-04dd944b8e48"
PRIVATE_BODY = '{"message": "account acct-private-77 has no balance"}'

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    @property
    def only(self) -> httpx.Request:
        (request,) = self.requests
        return request


def _client(handler: Handler, agent_id: str | None = AGENT_ID, **kwargs) -> tuple:
    recorder = Recorder(handler)
    client = HttpBolnaClient(
        SecretStr(API_KEY), agent_id, transport=httpx.MockTransport(recorder), **kwargs
    )
    return client, recorder


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _reply(status: int, body: object | None = None) -> Handler:
    return lambda _: httpx.Response(status, json=body)


async def test_start_call_posts_agent_recipient_and_user_data_only() -> None:
    client, rec = _client(_reply(200, {"status": "queued", "execution_id": RUN_ID}))
    run_id = await client.start_call("+910000000001", {"ishara_call_id": "c1"})
    assert run_id == RUN_ID
    assert rec.only.method == "POST"
    assert str(rec.only.url) == "https://api.bolna.ai/call"
    assert rec.only.headers["authorization"] == f"Bearer {API_KEY}"
    assert _body(rec.only) == {
        "agent_id": AGENT_ID,
        "recipient_phone_number": "+910000000001",
        "user_data": {"ishara_call_id": "c1"},
    }


@pytest.mark.parametrize(
    "handler",
    [
        _reply(200, {"status": "queued"}),
        _reply(200, {"execution_id": ""}),
        _reply(200, ["not", "an", "object"]),
        lambda _: httpx.Response(200, text="not json"),
    ],
)
async def test_start_call_without_execution_id_raises(handler: Handler) -> None:
    client, _ = _client(handler)
    with pytest.raises(BolnaError) as error:
        await client.start_call("+910000000001", {})
    assert error.value.operation == "start_call"


async def test_start_call_without_agent_id_fails_before_any_request() -> None:
    client, rec = _client(_reply(200, {"execution_id": RUN_ID}), agent_id=None)
    with pytest.raises(ValueError):
        await client.start_call("+910000000001", {})
    assert rec.requests == []


async def test_send_event_posts_event_and_properties_to_run() -> None:
    client, rec = _client(_reply(202, {"status": "accepted"}))
    await client.send_event(RUN_ID, "user_reply", {"reply_text": "Yes.", "turn_id": "t1"})
    assert rec.only.method == "POST"
    assert str(rec.only.url) == f"https://api.bolna.ai/v1/call/{RUN_ID}/events"
    assert rec.only.headers["authorization"] == f"Bearer {API_KEY}"
    assert _body(rec.only) == {
        "event": "user_reply",
        "properties": {"reply_text": "Yes.", "turn_id": "t1"},
    }


async def test_send_event_to_ended_call_raises_with_status() -> None:
    client, _ = _client(_reply(404, {"detail": "No active call found for this run_id"}))
    with pytest.raises(BolnaError) as error:
        await client.send_event(RUN_ID, "end_call", {})
    assert (error.value.status_code, error.value.operation) == (404, "send_event")


@pytest.mark.parametrize("bad_id", ["../agent", "a/b", "", "id?x=1"])
async def test_ids_that_could_change_the_path_are_rejected(bad_id: str) -> None:
    client, rec = _client(_reply(200, {}))
    with pytest.raises(ValueError):
        await client.send_event(bad_id, "end_call", {})
    with pytest.raises(ValueError):
        await client.update_agent(bad_id, {})
    with pytest.raises(ValueError):
        await client.get_agent(bad_id)
    assert rec.requests == []


async def test_create_agent_posts_payload_and_returns_new_id() -> None:
    payload = {"agent_config": {"agent_name": "x"}, "agent_prompts": {}}
    client, rec = _client(_reply(201, {"agent_id": "new-agent", "state": "created"}))
    assert await client.create_agent(payload) == "new-agent"
    assert (rec.only.method, str(rec.only.url)) == ("POST", "https://api.bolna.ai/v2/agent")
    assert _body(rec.only) == payload


async def test_update_agent_puts_full_payload() -> None:
    payload = {"agent_config": {"agent_name": "x"}, "agent_prompts": {}}
    client, rec = _client(_reply(200, {"status": "updated"}))
    await client.update_agent(AGENT_ID, payload)
    assert rec.only.method == "PUT"
    assert str(rec.only.url) == f"https://api.bolna.ai/v2/agent/{AGENT_ID}"
    assert _body(rec.only) == payload


async def test_get_agent_returns_config() -> None:
    client, rec = _client(_reply(200, {"agent_name": "Ishara relay"}))
    assert await client.get_agent(AGENT_ID) == {"agent_name": "Ishara relay"}
    assert rec.only.method == "GET"
    assert str(rec.only.url) == f"https://api.bolna.ai/v2/agent/{AGENT_ID}"


async def test_register_custom_model_sends_endpoint_and_bearer_key() -> None:
    client, rec = _client(_reply(200, {"status": "added"}))
    await client.register_custom_model(
        "ishara-relay", "https://x.example.com/v1", SecretStr("llm-token"), "llama"
    )
    assert (rec.only.method, rec.only.url.path) == ("POST", "/user/model/custom")
    assert _body(rec.only) == {
        "custom_model_name": "ishara-relay",
        "custom_model_url": "https://x.example.com/v1",
        "custom_model_key": "llm-token",
        "custom_model_family": "llama",
    }


async def test_error_text_never_holds_key_or_response_body() -> None:
    client, _ = _client(lambda _: httpx.Response(401, text=PRIVATE_BODY))
    with pytest.raises(BolnaError) as error:
        await client.create_agent({})
    text = str(error.value) + repr(error.value)
    assert "401" in text and "create_agent" in text
    assert API_KEY not in text
    assert "acct-private-77" not in text


async def test_redirects_are_not_followed() -> None:
    redirect = httpx.Response(307, headers={"Location": "https://evil.example.com/call"})
    client, rec = _client(lambda _: redirect)
    with pytest.raises(BolnaError) as error:
        await client.start_call("+910000000001", {})
    assert error.value.status_code == 307
    assert len(rec.requests) == 1


async def test_network_failure_becomes_bolna_error_without_key() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client, _ = _client(fail)
    with pytest.raises(BolnaError) as error:
        await client.send_event(RUN_ID, "user_reply", {})
    assert error.value.status_code is None
    assert API_KEY not in str(error.value)


async def test_every_request_carries_the_configured_timeout() -> None:
    client, rec = _client(_reply(202, {}), timeout_s=3.5)
    await client.send_event(RUN_ID, "end_call", {})
    assert rec.only.extensions["timeout"] == {
        "connect": 3.5,
        "read": 3.5,
        "write": 3.5,
        "pool": 3.5,
    }
