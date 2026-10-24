from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

APP_TOKEN = "test-app-token"
CUSTOM_LLM_TOKEN = "test-custom-llm-token"
WEBHOOK_SECRET = "test-webhook-secret"


def make_settings(**overrides: object) -> Settings:
    """Settings that ignore the developer's real .env and environment."""
    values: dict[str, object] = {
        "app_token": APP_TOKEN,
        "custom_llm_token": CUSTOM_LLM_TOKEN,
        "bolna_webhook_secret": WEBHOOK_SECRET,
        "bolna_api_key": "test-bolna-key",
        "bolna_agent_id": "test-agent",
        "groq_api_key": "test-groq-key",
        "allowed_recipients": "clinic=+910000000001",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@pytest.fixture(autouse=True)
def no_internet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any lookup of a non-loopback host, so a test (or a mutant under mutation
    testing) that loses its fake transport can't reach Bolna, Groq or Sarvam."""
    real_getaddrinfo = socket.getaddrinfo

    def loopback_only(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        if name not in LOOPBACK_HOSTS:
            raise OSError(f"tests must not reach the network (tried {name!r})")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", loopback_only)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
