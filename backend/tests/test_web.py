from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.web_auth import COOKIE, SESSION_SECONDS, issue_session, valid_session
from app.web_recognition import decision, load_bundle
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, make_settings

ORIGIN = {"Origin": "http://testserver"}


def socket_client() -> TestClient:
    from app.calls import CallManager
    from app.composer import TemplateComposer

    class NoDial:
        async def start_call(self, *args):
            raise AssertionError("browser auth tests must not dial")

        async def send_event(self, *args):
            raise AssertionError("browser auth tests must not send events")

    settings = make_settings()
    manager = CallManager(settings, TemplateComposer(), NoDial())
    return TestClient(create_app(settings, ledger=manager))


def test_browser_session_cookie_is_signed_http_only_and_expires() -> None:
    settings = make_settings()
    token = issue_session(settings, now=100)
    assert APP_TOKEN not in token
    assert valid_session(settings, token, now=101)
    assert not valid_session(settings, token, now=100 + SESSION_SECONDS)
    assert not valid_session(settings, token, now=99)
    assert not valid_session(settings, token + "x", now=101)
    assert not valid_session(make_settings(app_token="rotated"), token, now=101)
    assert not valid_session(settings, "100." + "a" * 32 + ".☃", now=101)


def test_login_uses_a_cookie_without_exposing_credentials() -> None:
    client = TestClient(create_app(make_settings()))
    assert client.get("/web/session").json() == {"authenticated": False}
    response = client.post("/web/session", headers=ORIGIN, json={"code": APP_TOKEN})
    assert response.status_code == 204
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header and "SameSite=strict" in header
    assert APP_TOKEN not in header and APP_TOKEN not in response.text
    assert client.get("/web/session").json() == {"authenticated": True}
    assert client.get("/web/contacts").status_code == 200
    assert client.post("/web/logout", headers=ORIGIN).status_code == 204
    assert client.get("/web/session").json() == {"authenticated": False}


def test_https_deployment_issues_secure_cookie_behind_http_proxy() -> None:
    client = TestClient(create_app(make_settings(public_base_url="https://demo.example.invalid")))
    response = client.post(
        "/web/session", headers={"Origin": "https://demo.example.invalid"}, json={"code": APP_TOKEN}
    )
    assert "Secure" in response.headers["set-cookie"]


@pytest.mark.parametrize("origin", [None, "null", "https://other.example.invalid"])
def test_cookie_authenticated_writes_and_websockets_reject_other_origins(origin) -> None:
    client = socket_client()
    client.cookies.set(COOKIE, issue_session(make_settings()))
    headers = {"Origin": origin} if origin is not None else {}
    assert client.post("/briefs", headers=headers, json={}).status_code == 401
    with client.websocket_connect("/calls/unknown/ws", headers=headers) as ws:
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401


def test_browser_cookie_authenticates_socket_before_missing_call_check() -> None:
    from starlette.websockets import WebSocketDisconnect

    client = socket_client()
    client.cookies.set(COOKIE, issue_session(make_settings()))
    with client.websocket_connect("/calls/unknown/ws", headers=ORIGIN) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4404


def test_login_rejects_invalid_or_oversized_payloads_without_echoing_them() -> None:
    client = TestClient(create_app(make_settings()))
    secret = "private-invalid-code"
    for body in [[], {"code": [secret]}, {"code": secret * 300}]:
        response = client.post("/web/session", headers=ORIGIN, json=body)
        assert response.status_code in {400, 401}
        assert secret not in response.text
    assert (
        client.post("/web/session", headers=ORIGIN, json={"code": CUSTOM_LLM_TOKEN}).status_code
        == 401
    )
    assert client.post("/web/session", json={"code": APP_TOKEN}).status_code == 403


def test_browser_cookie_does_not_authenticate_bolna_custom_llm() -> None:
    client = TestClient(create_app(make_settings()))
    client.cookies.set(COOKIE, issue_session(make_settings()))
    assert client.post("/v1/chat/completions", headers=ORIGIN, json={}).status_code == 401


def test_allowlist_is_never_public() -> None:
    client = TestClient(create_app(make_settings()))
    assert client.get("/web/contacts").status_code == 401


def test_model_bundle_matches_the_existing_iphone_bundle() -> None:
    from pathlib import Path

    iphone = Path(__file__).resolve().parents[2] / "ios/Ishara/Resources/asl-bundle.json"
    assert load_bundle() == json.loads(iphone.read_text())


def test_full_model_winner_outside_vocabulary_cannot_become_a_chip() -> None:
    bundle = load_bundle()
    logits = [-20.0] * len(bundle["glosses"])
    logits[bundle["glosses"].index("hello")] = 1
    outsider = next(g for g in bundle["glosses"] if g not in bundle["vocabulary"])
    logits[bundle["glosses"].index(outsider)] = 12
    assert decision(logits, bundle)["kind"] == "unsure"


def test_recognition_requires_margin_and_never_accepts_nan() -> None:
    bundle = load_bundle()
    logits = [-20.0] * len(bundle["glosses"])
    logits[bundle["glosses"].index("hello")] = 5
    assert decision(logits, bundle)["kind"] == "chip"
    logits[bundle["glosses"].index("yes")] = 5
    assert decision(logits, bundle)["kind"] == "candidate"
    logits[0] = float("nan")
    assert decision(logits, bundle)["kind"] == "unsure"
