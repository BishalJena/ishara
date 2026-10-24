from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, make_settings

SARVAM_KEY = "test-sarvam-key-0123"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24
AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}

Handler = Callable[[httpx.Request], httpx.Response]


def wav_response(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"request_id": "r1", "audios": [base64.b64encode(WAV).decode()]}
    )


class FakeSarvam:
    """Records every request that would have reached Sarvam."""

    def __init__(self, handler: Handler = wav_response) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make_client(fake: FakeSarvam, sarvam_api_key: str | None = SARVAM_KEY) -> TestClient:
    app = create_app(
        make_settings(sarvam_api_key=sarvam_api_key), sarvam_transport=httpx.MockTransport(fake)
    )
    return TestClient(app)


def post(client: TestClient, body: dict[str, object], headers: dict[str, str] = AUTH):
    return client.post("/tts", json=body, headers=headers)


def test_returns_wav_bytes_from_sarvam() -> None:
    fake = FakeSarvam()
    response = post(make_client(fake), {"turn_id": "t1", "text": "No, sorry."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == WAV
    [request] = fake.requests
    assert request.headers["api-subscription-key"] == SARVAM_KEY
    sent = json.loads(request.content)
    assert sent["text"] == "No, sorry."
    assert sent["language_code"] == "en-IN"
    assert sent["speaker"] == "simran_en_customer"
    assert sent["model"] == "bulbul:v4-flash"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": f"Bearer {CUSTOM_LLM_TOKEN}"}, {"Authorization": "Bearer wrong"}],
)
def test_requires_app_token(headers: dict[str, str]) -> None:
    fake = FakeSarvam()
    response = post(make_client(fake), {"turn_id": "t1", "text": "Hi."}, headers)
    assert response.status_code == 401
    assert fake.requests == []


@pytest.mark.parametrize(
    "body",
    [
        {"turn_id": "t1", "text": ""},
        {"turn_id": "t1", "text": "x" * 301},
        {"turn_id": "bad id!", "text": "Hi."},
        {"turn_id": "", "text": "Hi."},
        {"turn_id": "t" * 65, "text": "Hi."},
        {"turn_id": "t1"},
        {"text": "Hi."},
        {"turn_id": "t1", "text": "Hi.", "voice": "other"},
    ],
)
def test_invalid_body_rejected_without_provider_call(body: dict[str, object]) -> None:
    fake = FakeSarvam()
    assert post(make_client(fake), body).status_code == 422
    assert fake.requests == []


def test_boundary_lengths_accepted() -> None:
    fake = FakeSarvam()
    client = make_client(fake)
    assert post(client, {"turn_id": "t" * 64, "text": "x" * 300}).status_code == 200
    assert post(client, {"turn_id": "a-B_9", "text": "x"}).status_code == 200


def test_second_request_for_same_turn_conflicts_without_provider_call() -> None:
    fake = FakeSarvam()
    client = make_client(fake)
    assert post(client, {"turn_id": "t1", "text": "Yes."}).status_code == 200
    again = post(client, {"turn_id": "t1", "text": "Something else."})
    assert again.status_code == 409
    assert len(fake.requests) == 1
    assert post(client, {"turn_id": "t2", "text": "Yes."}).status_code == 200
    assert len(fake.requests) == 2


def test_turns_are_tracked_per_app() -> None:
    first, second = FakeSarvam(), FakeSarvam()
    assert post(make_client(first), {"turn_id": "t1", "text": "Yes."}).status_code == 200
    assert post(make_client(second), {"turn_id": "t1", "text": "Yes."}).status_code == 200


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_sarvam_key_is_503_without_provider_call(key: str | None) -> None:
    fake = FakeSarvam()
    response = post(make_client(fake, sarvam_api_key=key), {"turn_id": "t1", "text": "Yes."})
    assert response.status_code == 503
    # The app tells "not configured" (fix the backend) apart from "failed" (tap again).
    assert response.json() == {"detail": "text-to-speech not configured"}
    assert fake.requests == []


def test_missing_key_does_not_use_up_the_turn() -> None:
    fake = FakeSarvam()
    app = create_app(make_settings(sarvam_api_key=None), sarvam_transport=httpx.MockTransport(fake))
    client = TestClient(app)
    assert post(client, {"turn_id": "t1", "text": "Yes."}).status_code == 503
    app.state.settings = make_settings(sarvam_api_key=SARVAM_KEY)
    assert post(client, {"turn_id": "t1", "text": "Yes."}).status_code == 200


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(500, json={"error": {"message": f"boom {SARVAM_KEY}"}}),
        lambda _: httpx.Response(403, text=f"invalid key {SARVAM_KEY}"),
        _timeout,
        lambda _: httpx.Response(200, json={"audios": [base64.b64encode(b"ID3 mp3").decode()]}),
        lambda _: httpx.Response(200, text=f"not json {SARVAM_KEY}"),
    ],
)
def test_provider_failure_is_generic_502_without_key_or_body(
    handler: Handler, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = post(make_client(FakeSarvam(handler)), {"turn_id": "t1", "text": "Yes."})
    assert response.status_code == 502
    assert response.json() == {"detail": "text-to-speech failed"}
    assert SARVAM_KEY not in caplog.text
    assert "boom" not in caplog.text
    assert "not json" not in caplog.text
    assert "invalid key" not in caplog.text


def test_failed_turn_can_be_retried_once_it_succeeds() -> None:
    outcomes = iter([httpx.Response(500), None, None])

    def flaky(request: httpx.Request) -> httpx.Response:
        return next(outcomes) or wav_response(request)

    fake = FakeSarvam(flaky)
    client = make_client(fake)
    assert post(client, {"turn_id": "t1", "text": "Yes."}).status_code == 502
    assert post(client, {"turn_id": "t1", "text": "Yes."}).status_code == 200
    assert post(client, {"turn_id": "t1", "text": "Yes."}).status_code == 409
    assert len(fake.requests) == 2
