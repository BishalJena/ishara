from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_app_token, require_custom_llm_token
from app.config import REQUIRED_PATH_B, Settings
from app.main import create_app
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, make_settings


def test_health_ok_and_reports_no_missing_config(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "missing_config": []}


def test_health_lists_missing_names_without_values() -> None:
    empty = Settings(_env_file=None)
    body = TestClient(create_app(empty)).get("/health").json()
    assert body["missing_config"] == list(REQUIRED_PATH_B)


def test_blank_values_count_as_missing() -> None:
    settings = make_settings(app_token="  ", bolna_agent_id="")
    assert settings.missing_required() == ["APP_TOKEN", "BOLNA_AGENT_ID"]


def test_allowed_recipients_parsed_from_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_RECIPIENTS", " +910000000001, +910000000002 ,")
    settings = Settings(_env_file=None)
    assert settings.allowed_recipients == {"+910000000001", "+910000000002"}


def test_presence_never_exposes_secret_values(settings: Settings) -> None:
    assert APP_TOKEN not in repr(settings.presence())
    assert APP_TOKEN not in repr(settings)


def _guarded_app(settings: Settings) -> TestClient:
    app = create_app(settings)
    probe = FastAPI()
    probe.state = app.state

    @probe.get("/app", dependencies=[Depends(require_app_token)])
    def app_route() -> dict[str, bool]:
        return {"ok": True}

    @probe.get("/llm", dependencies=[Depends(require_custom_llm_token)])
    def llm_route() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(probe)


@pytest.mark.parametrize(
    ("path", "token", "expected"),
    [
        ("/app", APP_TOKEN, 200),
        ("/app", CUSTOM_LLM_TOKEN, 401),
        ("/app", None, 401),
        ("/llm", CUSTOM_LLM_TOKEN, 200),
        ("/llm", APP_TOKEN, 401),
        ("/llm", "wrong", 401),
    ],
)
def test_bearer_tokens_are_not_interchangeable(
    settings: Settings, path: str, token: str | None, expected: int
) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    assert _guarded_app(settings).get(path, headers=headers).status_code == expected


def test_unset_server_token_rejects_everything() -> None:
    client = _guarded_app(make_settings(app_token=None))
    assert client.get("/app", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/app", headers={"Authorization": "Bearer None"}).status_code == 401
