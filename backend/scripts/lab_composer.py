"""The Sign Lab's composer: production drafting, made visible.

The composer itself is the production one (`GroqComposer` with its 1.5 s budget,
validator and template fallback, or `TemplateComposer`). This module only watches it:

- `ObservedComposer` logs the chips, the receptionist's last words, the final draft
  with its source and latency, and why an LLM draft fell back to the template (the
  same reason `app.composer` logs in production).
- `LabGroqClient` logs Groq's raw answer before the validator sees it, so a rejected
  draft can be compared with its reasons.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Literal

import httpx
from pydantic import SecretStr

from app import composer as production
from app.composer import GroqComposer, TemplateComposer
from app.groq_client import GroqClient
from app.ports import Composer
from app.protocol import ComposeRequest, Draft

ComposerChoice = Literal["templates", "groq"]
Log = Callable[[str], None]

# Fallback reasons logged by app.composer while the current compose task runs.
_fallback_notes: ContextVar[list[str] | None] = ContextVar("fallback_notes", default=None)


class _FallbackNotes(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        notes = _fallback_notes.get()
        if notes is not None:
            # "turn <id>: LLM draft rejected (...), using template" → drop the turn id.
            notes.append(record.getMessage().split(": ", 1)[-1])


_NOTES_HANDLER = _FallbackNotes()


def _watch_production_logger() -> None:
    logger = logging.getLogger(production.__name__)
    if _NOTES_HANDLER not in logger.handlers:
        logger.addHandler(_NOTES_HANDLER)
    # The rejection reasons are INFO records; without this they never reach a handler.
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)


class ObservedComposer:
    def __init__(
        self, inner: Composer, log: Log, clock: Callable[[], float] = time.perf_counter
    ) -> None:
        self.inner = inner
        self._log = log
        self._clock = clock
        _watch_production_logger()

    async def compose(self, request: ComposeRequest) -> Draft:
        heard = f'"{request.last_caption}"' if request.last_caption else "nothing yet"
        self._log(f"chips: {' · '.join(request.chips)} (receptionist last said: {heard})")
        notes: list[str] = []
        token = _fallback_notes.set(notes)
        started = self._clock()
        try:
            draft = await self.inner.compose(request)
        finally:
            _fallback_notes.reset(token)
        elapsed = self._clock() - started
        self._log(f"draft ({draft.source.value}, {elapsed:.2f} s): {draft.text}")
        for note in notes:
            self._log(f"  fallback: {note}")
        return draft


class LabGroqClient(GroqClient):
    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        *,
        log: Log,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        super().__init__(api_key, model, transport=transport)
        self._log = log
        self._clock = clock

    async def complete(self, system: str, user: str) -> str:
        started = self._clock()
        text = await super().complete(system, user)
        self._log(f"groq answered in {self._clock() - started:.2f} s: {text.strip()}")
        return text


def build_lab_composer(
    choice: ComposerChoice,
    *,
    log: Log,
    groq_key: SecretStr | None = None,
    groq_model: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ObservedComposer:
    """Templates, or Groq with the production timeout, validator and fallback."""
    if choice == "templates":
        return ObservedComposer(TemplateComposer(), log)
    if groq_key is None or not groq_model:
        raise ValueError("the Groq composer needs a key and a model")
    client = LabGroqClient(groq_key, groq_model, log=log, transport=transport)
    return ObservedComposer(GroqComposer(client), log)
