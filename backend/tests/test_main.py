"""Production wiring in app/main.py: build_app from settings and the lazy module app."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.bolna_client import HttpBolnaClient
from app.calls import CallManager
from app.composer import GroqComposer, TemplateComposer
from app.config import Settings
from app.contacts import InvalidContacts
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, make_settings

AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}
START = {"contact_id": "clinic", "purpose": "doctor_appointment"}


def test_build_app_wires_groq_bolna_and_the_call_manager() -> None:
    app = main.build_app(make_settings())

    assert isinstance(app.state.composer, GroqComposer)
    assert isinstance(app.state.bolna, HttpBolnaClient)
    assert isinstance(app.state.ledger, CallManager)
    assert app.state.ledger._composer is app.state.composer
    assert app.state.ledger._bolna is app.state.bolna


def test_build_app_uses_templates_without_a_groq_key() -> None:
    app = main.build_app(make_settings(groq_api_key=None))

    assert isinstance(app.state.composer, TemplateComposer)
    assert app.state.ledger._composer is app.state.composer


def test_boots_without_an_agent_id_and_refuses_calls_cleanly() -> None:
    client = TestClient(main.build_app(make_settings(bolna_agent_id=None)))

    assert client.get("/health").json() == {"status": "ok", "missing_config": ["BOLNA_AGENT_ID"]}
    response = client.post("/calls", json=START, headers=AUTH)
    assert response.status_code == 502
    assert response.json() == {"detail": "could not start the call"}


def test_custom_llm_is_live_before_the_agent_exists() -> None:
    client = TestClient(main.build_app(make_settings(bolna_agent_id=None)))
    body = {"model": "m", "stream": False, "messages": [{"role": "user", "content": "hi"}]}

    response = client.post(
        "/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {CUSTOM_LLM_TOKEN}"}
    )

    assert response.status_code == 200


@pytest.mark.parametrize("recipients", ["", "  "])
def test_empty_allowlist_boots_and_forbids_every_contact(recipients: str) -> None:
    client = TestClient(main.build_app(make_settings(allowed_recipients=recipients)))

    assert client.get("/health").status_code == 200
    assert client.post("/calls", json=START, headers=AUTH).status_code == 403


def test_malformed_allowlist_fails_at_boot() -> None:
    with pytest.raises(InvalidContacts):
        main.build_app(make_settings(allowed_recipients="+910000000001"))


def test_without_a_bolna_key_calls_are_unavailable() -> None:
    client = TestClient(main.build_app(make_settings(bolna_api_key=None)))

    assert client.get("/health").status_code == 200
    assert client.post("/calls", json=START, headers=AUTH).status_code == 503


def test_each_app_gets_its_own_turn_claims_and_tracker() -> None:
    first, second = main.create_app(make_settings()), main.create_app(make_settings())

    assert first.state.tts_turn_claims is not second.state.tts_turn_claims
    assert first.state.utterance_tracker is not second.state.utterance_tracker


@pytest.fixture
def fresh_production_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Settings]]:
    """`main.app` with fake settings instead of the real environment."""
    built: list[Settings] = []

    def fake_settings() -> Settings:
        settings = make_settings(groq_api_key=None)
        built.append(settings)
        return settings

    monkeypatch.setattr(main, "get_settings", fake_settings)
    monkeypatch.setattr(main, "configure_logging", lambda: None)
    main._production_app.cache_clear()
    yield built
    main._production_app.cache_clear()


def test_module_app_is_built_once_from_settings(fresh_production_app: list[Settings]) -> None:
    app = main.app

    assert main.app is app
    assert len(fresh_production_app) == 1
    assert app.state.settings is fresh_production_app[0]
    assert isinstance(app.state.ledger, CallManager)


def test_importing_main_does_not_build_the_production_app() -> None:
    assert "app" not in vars(main)
    with pytest.raises(AttributeError, match="no attribute 'missing'"):
        _ = main.missing


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


def test_configure_logging_lets_app_info_lines_through(root_logger: logging.Logger) -> None:
    # pytest attaches its capture handlers for the test body, so clear them here.
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)

    main.configure_logging()

    (handler,) = root_logger.handlers
    assert handler.formatter is not None and handler.formatter._fmt == main.LOG_FORMAT
    assert logging.getLogger("app.shape_log").isEnabledFor(logging.INFO)
