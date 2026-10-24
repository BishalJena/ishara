"""Minimal async client for Groq's OpenAI-compatible chat completions API.

Only the fields Groq accepts are sent (no logprobs, logit_bias, message names, n).
For openai/gpt-oss-* models reasoning is kept low and left out of the response,
so `message.content` holds just the sentence. The API key goes only into the
Authorization header and never into errors or logs.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Reasoning tokens count towards the completion budget, so leave room beyond the sentence.
MAX_COMPLETION_TOKENS = 256
HTTP_TIMEOUT_S = 5.0  # backstop only; the composer enforces its own 1.5 s budget


class GroqError(Exception):
    """Groq could not produce a usable completion (HTTP, network or response shape)."""


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message
    finish_reason: str | None = None


class _Completion(BaseModel):
    choices: list[_Choice] = Field(min_length=1)


class GroqClient:
    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = GROQ_BASE_URL,
    ) -> None:
        self.model = model
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=HTTP_TIMEOUT_S,
            transport=transport,
        )

    def payload(self, system: str, user: str) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "stream": False,
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
            body["include_reasoning"] = False
        return body

    async def complete(self, system: str, user: str) -> str:
        """The assistant's text for one system + user exchange. Raises GroqError."""
        try:
            response = await self._http.post("/chat/completions", json=self.payload(system, user))
        except httpx.HTTPError as exc:
            raise GroqError(f"request failed: {type(exc).__name__}") from exc
        if response.status_code != httpx.codes.OK:
            raise GroqError(f"HTTP {response.status_code}")
        try:
            completion = _Completion.model_validate_json(response.content)
        except ValidationError as exc:
            raise GroqError("malformed response") from exc
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise GroqError("completion cut off at the token limit")
        if not choice.message.content:
            raise GroqError("empty completion")
        return choice.message.content

    async def aclose(self) -> None:
        await self._http.aclose()
