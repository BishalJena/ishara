"""Minimal async client for Groq's OpenAI-compatible chat completions API.

Only the fields Groq accepts are sent (no logprobs, logit_bias, message names, n).
For openai/gpt-oss-* models reasoning is kept low and left out of the response,
so `message.content` holds just the sentence. The API key goes only into the
Authorization header and never into errors or logs.
"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Reasoning tokens count towards the completion budget, so leave room beyond the sentence.
MAX_COMPLETION_TOKENS = 256
PLANNER_COMPLETION_TOKENS = 2048
STRICT_MODELS = frozenset(("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"))
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
log = logging.getLogger(__name__)
HTTP_TIMEOUT_S = 5.0  # backstop only; the composer enforces its own 1.5 s budget


class GroqError(Exception):
    """Groq could not produce a usable completion, without response contents."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "unavailable",
        status_code: int | None = None,
        validation_errors: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.validation_errors = validation_errors


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message
    finish_reason: str | None = None


class _Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class _Completion(BaseModel):
    usage: _Usage | None = None
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
        """The assistant's plain text for composer, polish and classic calls."""
        return await self._request(self.payload(system, user))

    async def complete_structured(
        self, system: str, user: str, response_model: type[ResponseModel]
    ) -> ResponseModel:
        if self.model not in STRICT_MODELS:
            raise GroqError("strict structured output unsupported", category="unsupported_model")
        schema = response_model.model_json_schema()
        _strict_schema(schema)
        body = self.payload(system, user)
        body["max_completion_tokens"] = PLANNER_COMPLETION_TOKENS
        if self.model == "qwen/qwen3.8-27b":
            body["reasoning_format"] = "hidden"
            body["reasoning_effort"] = "low"
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
        }
        raw = await self._request(body)
        try:
            return response_model.model_validate_json(raw, strict=True)
        except ValidationError as exc:
            raise GroqError(
                "invalid structured output",
                category="schema",
                validation_errors=_validation_errors(exc, schema),
            ) from None

    async def _request(self, body: dict[str, object]) -> str:
        started = time.monotonic()
        try:
            response = await self._http.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise GroqError(f"request failed: {type(exc).__name__}", category="network") from None
        if response.status_code != httpx.codes.OK:
            raise GroqError(
                f"HTTP {response.status_code}",
                category="http",
                status_code=response.status_code,
            )
        try:
            completion = _Completion.model_validate_json(response.content)
        except ValidationError as exc:
            raise GroqError(
                "malformed response",
                category="response",
                validation_errors=_validation_errors(exc, _Completion.model_json_schema()),
            ) from None
        choice = completion.choices[0]
        log.info(
            "groq completion finish=%s prompt_tokens=%s completion_tokens=%s latency_ms=%d",
            choice.finish_reason
            if choice.finish_reason in (None, "stop", "length")
            else "unexpected",
            completion.usage.prompt_tokens if completion.usage else None,
            completion.usage.completion_tokens if completion.usage else None,
            (time.monotonic() - started) * 1000,
        )
        if choice.finish_reason == "length":
            raise GroqError("completion cut off at the token limit", category="truncated")
        if choice.finish_reason not in (None, "stop"):
            raise GroqError("completion did not stop normally", category="finish_reason")
        if not choice.message.content:
            raise GroqError("empty completion", category="empty")
        return choice.message.content

    async def aclose(self) -> None:
        await self._http.aclose()


def _strict_schema(node: object) -> None:
    """Every object is closed and every property required, including nullable fields."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            node["additionalProperties"] = False
            node["required"] = list(node.get("properties", {}))
        for value in node.values():
            _strict_schema(value)
    elif isinstance(node, list):
        for value in node:
            _strict_schema(value)


def _validation_errors(error: ValidationError, schema: dict) -> tuple[str, ...]:
    allowed = set(schema.get("$defs", {}))

    def collect(node: object) -> None:
        if isinstance(node, dict):
            allowed.update(node.get("properties", {}))
            for child in node.values():
                collect(child)
        elif isinstance(node, list):
            for child in node:
                collect(child)

    collect(schema)
    failures = error.errors(include_input=False, include_context=False, include_url=False)
    wrong_variants = {
        failure["loc"][1]
        for failure in failures
        if failure["type"] == "literal_error"
        and len(failure["loc"]) == 3
        and failure["loc"][0] == "action"
        and failure["loc"][-1] == "kind"
    }
    matching = [
        failure
        for failure in failures
        if not (
            len(failure["loc"]) >= 2
            and failure["loc"][0] == "action"
            and failure["loc"][1] in wrong_variants
        )
    ]
    return tuple(
        ".".join(
            "item" if isinstance(part, int) else part if part in allowed else "unknown_field"
            for part in failure["loc"]
        )
        + ":"
        + failure["type"]
        for failure in (matching or failures)[:12]
    )
