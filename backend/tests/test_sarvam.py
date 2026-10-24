from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app import sarvam
from app.sarvam import SarvamError, SarvamTTS

KEY = "test-sarvam-key-0123"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24


def ok_body(*audios: bytes) -> dict[str, object]:
    return {"request_id": "r1", "audios": [base64.b64encode(a).decode() for a in audios]}


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> SarvamTTS:
    return SarvamTTS(SecretStr(KEY), transport=httpx.MockTransport(handler))


async def test_sends_documented_request_and_returns_wav() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ok_body(WAV))

    assert await client_for(handler).synthesize("No, sorry.") == WAV
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.sarvam.ai/text-to-speech"
    assert request.headers["api-subscription-key"] == KEY
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "text": "No, sorry.",
        "language_code": "en-IN",
        "speaker": "simran_en_customer",
        "model": "bulbul:v4-flash",
        "speech_sample_rate": 16000,
        "output_audio_codec": "wav",
    }


async def test_request_carries_explicit_timeout() -> None:
    seen: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json=ok_body(WAV))

    await client_for(handler).synthesize("Hi.")
    assert seen == [{"connect": 3.0, "read": 10.0, "write": 10.0, "pool": 10.0}]


async def test_split_audio_chunks_are_joined_before_decoding() -> None:
    encoded = base64.b64encode(WAV).decode()
    body = {"request_id": "r1", "audios": [encoded[:8], encoded[8:]]}
    result = await client_for(lambda _: httpx.Response(200, json=body)).synthesize("Hi.")
    assert result == WAV


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        (lambda _: httpx.Response(500, json={"error": {"message": KEY}}), "HTTP 500"),
        (lambda _: httpx.Response(403, text=f"bad key {KEY}"), "HTTP 403"),
        (lambda _: httpx.Response(201, json=ok_body(WAV)), "HTTP 201"),
        (_raise(httpx.ReadTimeout("slow")), "request failed: ReadTimeout"),
        (_raise(httpx.ConnectError("down")), "request failed: ConnectError"),
        (lambda _: httpx.Response(200, text=f"<html>{KEY}</html>"), "unexpected response shape"),
        (lambda _: httpx.Response(200, json={"audios": []}), "unexpected response shape"),
        (lambda _: httpx.Response(200, json={"audios": ["%%%"]}), "audio is not base64"),
        (lambda _: httpx.Response(200, json=ok_body(b"ID3" + WAV)), "audio is not WAV"),
        (lambda _: httpx.Response(200, json=ok_body(b"RIFF....AVI ")), "audio is not WAV"),
        (lambda _: httpx.Response(200, json=ok_body(b"RIFX....WAVE")), "audio is not WAV"),
    ],
)
async def test_failures_raise_typed_error_without_key_or_body(
    handler: Callable[[httpx.Request], httpx.Response], message: str
) -> None:
    with pytest.raises(SarvamError) as caught:
        await client_for(handler).synthesize("Hi.")
    assert str(caught.value) == message
    # No chained exception, so tracebacks can't carry the provider body either.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ or caught.value.__context__ is None


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (WAV, True),
        (b"RIFF\x00\x00\x00\x00WAVE", True),
        (b"RIFF\x00\x00\x00\x00WAV", False),
        (b"riff\x00\x00\x00\x00WAVE", False),
        (b"", False),
    ],
)
def test_is_wav_checks_riff_and_wave_tags(data: bytes, expected: bool) -> None:
    assert sarvam.is_wav(data) is expected
