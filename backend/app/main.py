"""FastAPI entry point.

- `create_app` takes every collaborator, so tests pass fakes.
- `build_app` wires the real ones from settings (Groq or templates, the Bolna client,
  the CallManager ledger).
- `app` (what `uvicorn app.main:app` serves) is built on first access, so importing
  this module in tests never reads the environment or a developer's `.env`.
"""

from __future__ import annotations

import logging
from functools import cache

import httpx
from fastapi import FastAPI

from app import calls, custom_llm, tts
from app.bolna_client import HttpBolnaClient
from app.calls import CallManager
from app.composer import build_composer
from app.config import Settings, get_settings
from app.delegate import build_brain
from app.ports import BolnaClient, CallLedger, Composer
from app.utterances import UtteranceTracker

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def create_app(
    settings: Settings | None = None,
    *,
    composer: Composer | None = None,
    bolna: BolnaClient | None = None,
    ledger: CallLedger | None = None,
    sarvam_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    app = FastAPI(title="Ishara backend")
    app.state.settings = settings or get_settings()
    app.state.composer = composer
    app.state.bolna = bolna
    app.state.ledger = ledger
    app.state.utterance_tracker = UtteranceTracker()
    # None means the real Sarvam API; tests pass an httpx.MockTransport.
    app.state.sarvam_transport = sarvam_transport
    app.state.tts_turn_claims = tts.TurnClaims()

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "missing_config": app.state.settings.missing_required()}

    app.include_router(calls.router)
    app.include_router(custom_llm.router)
    app.include_router(tts.router)
    return app


def build_app(settings: Settings) -> FastAPI:
    """The production wiring. Without BOLNA_API_KEY there is no ledger, so /calls and
    the custom LLM answer 503. BOLNA_AGENT_ID may still be unset (the custom LLM has to
    be live before the agent can be created); POST /calls then fails with 502. A
    malformed ALLOWED_RECIPIENTS raises here, so a bad config fails at boot; an empty
    one boots and every contact gets 403."""
    composer = build_composer(settings)
    bolna = None
    ledger = None
    if settings.bolna_api_key is not None:
        bolna = HttpBolnaClient(settings.bolna_api_key, settings.bolna_agent_id)
        ledger = CallManager(settings, composer, bolna, brain=build_brain(settings))
    return create_app(settings, composer=composer, bolna=bolna, ledger=ledger)


def configure_logging() -> None:
    """INFO to stderr for `app.*` loggers (custom-LLM shape lines, composer fallbacks),
    so they reach Heroku logs. uvicorn's own loggers don't propagate to the root, so
    nothing is printed twice."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


@cache
def _production_app() -> FastAPI:
    configure_logging()
    return build_app(get_settings())


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _production_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
