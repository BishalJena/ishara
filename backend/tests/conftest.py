from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

APP_TOKEN = "test-app-token"
CUSTOM_LLM_TOKEN = "test-custom-llm-token"


def make_settings(**overrides: object) -> Settings:
    """Settings that ignore the developer's real .env and environment."""
    values: dict[str, object] = {
        "app_token": APP_TOKEN,
        "custom_llm_token": CUSTOM_LLM_TOKEN,
        "bolna_api_key": "test-bolna-key",
        "bolna_agent_id": "test-agent",
        "groq_api_key": "test-groq-key",
        "allowed_recipients": "clinic=+910000000001",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
