"""FastAPI entry point. `create_app` takes the collaborators so tests can pass fakes."""

from __future__ import annotations

from fastapi import FastAPI

from app import calls, custom_llm, tts
from app.config import Settings, get_settings
from app.ports import BolnaClient, CallLedger, Composer


def create_app(
    settings: Settings | None = None,
    *,
    composer: Composer | None = None,
    bolna: BolnaClient | None = None,
    ledger: CallLedger | None = None,
) -> FastAPI:
    app = FastAPI(title="Ishara backend")
    app.state.settings = settings or get_settings()
    app.state.composer = composer
    app.state.bolna = bolna
    app.state.ledger = ledger

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "missing_config": app.state.settings.missing_required()}

    app.include_router(calls.router)
    app.include_router(custom_llm.router)
    app.include_router(tts.router)
    return app


app = create_app()
