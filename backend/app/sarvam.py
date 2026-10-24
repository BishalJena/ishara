"""Sarvam text-to-speech client for Path A (task A5).

Contract, from Sarvam's API reference (read 23 Oct 2026):
https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert
https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/rest-api
https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/best-practices

- `POST https://api.sarvam.ai/text-to-speech`, auth header `api-subscription-key`.
- JSON body: `text` (max 2500 chars on v3/v4-flash), `language_code` (BCP-47; the
  older `target_language_code` name is gone from the reference), `speaker`, `model`,
  `speech_sample_rate` (default 22050), `output_audio_codec` (default wav), `pace`.
- Models on REST: `bulbul:v4-flash` (latest, persona speakers such as
  `simran_en_customer`), `bulbul:v3` (API default when `model` is omitted, short
  speaker names) and legacy `bulbul:v2`. Speakers must match the model.
- 200 response: `{"request_id": ..., "audios": [<base64 WAV>, ...]}`, one entry per
  input text. Errors are JSON `{"error": {"message", "code", "request_id"}}`.

We use the same Bulbul v4 Flash family PLAN D2 picks for Bolna's voice, so Path A and
Path B sound alike. 16 kHz is Sarvam's suggested rate for voice agents; the call leg
is narrower than that anyway.
"""

from __future__ import annotations

import base64
import binascii

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

TTS_URL = "https://api.sarvam.ai/text-to-speech"
MODEL = "bulbul:v4-flash"
SPEAKER = "simran_en_customer"
LANGUAGE = "en-IN"
SAMPLE_RATE = 16000
TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class SarvamError(Exception):
    """Sarvam could not produce audio. Messages name the failure kind only, never the
    key or the provider's response body."""


class _TTSResponse(BaseModel):
    audios: list[str] = Field(min_length=1)


def is_wav(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"


class SarvamTTS:
    def __init__(
        self,
        api_key: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout

    async def synthesize(self, text: str) -> bytes:
        """Return WAV bytes for `text`. Raises SarvamError on any provider failure."""
        payload = {
            "text": text,
            "language_code": LANGUAGE,
            "speaker": SPEAKER,
            "model": MODEL,
            "speech_sample_rate": SAMPLE_RATE,
            "output_audio_codec": "wav",
        }
        headers = {"api-subscription-key": self._api_key.get_secret_value()}
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            try:
                response = await client.post(TTS_URL, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                raise SarvamError(f"request failed: {type(exc).__name__}") from None
        if response.status_code != httpx.codes.OK:
            raise SarvamError(f"HTTP {response.status_code}")
        return _decode_wav(response.content)


def _decode_wav(body: bytes) -> bytes:
    # `from None` keeps the provider body (inside ValidationError) out of tracebacks.
    try:
        audios = _TTSResponse.model_validate_json(body).audios
    except ValidationError:
        raise SarvamError("unexpected response shape") from None
    try:
        wav = base64.b64decode("".join(audios), validate=True)
    except binascii.Error:
        raise SarvamError("audio is not base64") from None
    if not is_wav(wav):
        raise SarvamError("audio is not WAV")
    return wav
