from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.bolna_agent import CUSTOM_LLM_MODEL, build_agent_payload
from app.config import Settings
from scripts.bolna_agent import main
from tests.conftest import CUSTOM_LLM_TOKEN, make_settings

AGENT_JSON = Path(__file__).resolve().parents[1] / "bolna" / "agent.json"
PUBLIC_URL = "https://ishara-test.example.com"
BOLNA_KEY = "test-bolna-key"


class Recorder:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def _ready(**overrides: object) -> Settings:
    return make_settings(**{"public_base_url": PUBLIC_URL, **overrides})


def test_render_prints_the_committed_agent_json(capsys) -> None:
    assert main(["render"]) == 0
    assert capsys.readouterr().out == AGENT_JSON.read_text()


def test_render_uses_a_given_backend_url(capsys) -> None:
    assert main(["render", "--public-base-url", PUBLIC_URL]) == 0
    assert json.loads(capsys.readouterr().out) == build_agent_payload(PUBLIC_URL + "/v1", None)


@pytest.mark.parametrize("command", ["register-llm", "create", "update"])
def test_write_commands_refuse_without_yes(command: str, capsys) -> None:
    recorder = Recorder(httpx.Response(200, json={"agent_id": "x"}))
    assert main([command], settings=_ready(), transport=recorder.transport) == 2
    assert "--yes" in capsys.readouterr().err
    assert recorder.requests == []


@pytest.mark.parametrize(
    ("command", "unset", "name"),
    [
        ("create", "public_base_url", "PUBLIC_BASE_URL"),
        ("create", "bolna_api_key", "BOLNA_API_KEY"),
        ("update", "public_base_url", "PUBLIC_BASE_URL"),
        ("update", "bolna_api_key", "BOLNA_API_KEY"),
        ("update", "bolna_agent_id", "BOLNA_AGENT_ID"),
        ("register-llm", "public_base_url", "PUBLIC_BASE_URL"),
        ("register-llm", "bolna_api_key", "BOLNA_API_KEY"),
        ("register-llm", "custom_llm_token", "CUSTOM_LLM_TOKEN"),
    ],
)
def test_write_commands_refuse_without_required_env(
    command: str, unset: str, name: str, capsys
) -> None:
    recorder = Recorder(httpx.Response(200, json={"agent_id": "x"}))
    settings = _ready(**{unset: None})
    assert main([command, "--yes"], settings=settings, transport=recorder.transport) == 2
    assert name in capsys.readouterr().err
    assert recorder.requests == []


def test_create_posts_the_agent_for_our_backend_and_prints_only_the_id(capsys) -> None:
    recorder = Recorder(httpx.Response(201, json={"agent_id": "new-agent", "state": "created"}))
    assert main(["create", "--yes"], settings=_ready(), transport=recorder.transport) == 0
    (request,) = recorder.requests
    assert (request.method, request.url.path) == ("POST", "/v2/agent")
    assert json.loads(request.content) == build_agent_payload(PUBLIC_URL + "/v1", None)
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "new-agent"
    assert "BOLNA_AGENT_ID" in out
    assert BOLNA_KEY not in out


def test_update_puts_to_the_configured_agent(capsys) -> None:
    recorder = Recorder(httpx.Response(200, json={"status": "updated"}))
    argv = ["update", "--yes", "--webhook-url", PUBLIC_URL + "/bolna/webhook"]
    assert main(argv, settings=_ready(), transport=recorder.transport) == 0
    (request,) = recorder.requests
    assert (request.method, request.url.path) == ("PUT", "/v2/agent/test-agent")
    assert json.loads(request.content)["agent_config"]["webhook_url"] == (
        PUBLIC_URL + "/bolna/webhook"
    )


def test_register_llm_sends_the_token_but_never_prints_it(capsys) -> None:
    recorder = Recorder(httpx.Response(200, json={"status": "added"}))
    assert main(["register-llm", "--yes"], settings=_ready(), transport=recorder.transport) == 0
    (request,) = recorder.requests
    body = json.loads(request.content)
    assert body["custom_model_key"] == CUSTOM_LLM_TOKEN
    assert body["custom_model_name"] == CUSTOM_LLM_MODEL
    assert body["custom_model_url"] == PUBLIC_URL + "/v1"
    captured = capsys.readouterr()
    assert CUSTOM_LLM_TOKEN not in captured.out + captured.err


def test_bolna_failure_exits_1_without_echoing_the_response(capsys) -> None:
    recorder = Recorder(httpx.Response(400, text='{"message": "acct-private-77"}'))
    assert main(["create", "--yes"], settings=_ready(), transport=recorder.transport) == 1
    captured = capsys.readouterr()
    assert "create_agent" in captured.err and "400" in captured.err
    assert "acct-private-77" not in captured.out + captured.err
