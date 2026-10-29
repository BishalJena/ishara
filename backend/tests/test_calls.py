from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.bolna_agent import SPEAK_PROMPT
from app.bolna_client import HttpBolnaClient
from app.calls import FINISHED_CALL_TTL_S, CallManager
from app.contacts import InvalidContacts, parse_contacts
from app.main import create_app
from app.markers import (
    DISCLOSURE,
    EVENT_END_CALL,
    EVENT_USER_REPLY,
    GOODBYE,
    HOLDING_LINE,
    USER_DATA_CALL_ID,
)
from app.ports import BolnaClient, BolnaError, ClaimedReply
from app.protocol import ComposeRequest, Draft
from fakes.fake_bolna import EVENT_NOTICE, bolna_render
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, WEBHOOK_SECRET, make_settings

CLINIC = "+910000000001"
PHARMACY = "+910000000002"
TEXT = "Hello, I'd like a doctor's appointment tomorrow."


def test_contacts_map_ids_to_numbers() -> None:
    entries = [f"clinic={CLINIC}", f" pharmacy = {PHARMACY} "]
    assert parse_contacts(entries) == {"clinic": CLINIC, "pharmacy": PHARMACY}


@pytest.mark.parametrize(
    "entry",
    [
        CLINIC,
        f"={CLINIC}",
        f"bad id={CLINIC}",
        "clinic=910000000001",
        "clinic=+010000000001",
        "clinic=+91000",
        "clinic=+9100000000011234",
        "clinic=+91000000000a",
        "clinic=",
    ],
)
def test_malformed_contact_entries_fail_loudly(entry: str) -> None:
    with pytest.raises(InvalidContacts):
        parse_contacts([entry])


def test_duplicate_contact_ids_rejected() -> None:
    with pytest.raises(InvalidContacts, match="twice"):
        parse_contacts([f"clinic={CLINIC}", f"clinic={PHARMACY}"])


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (CLINIC, "ALLOWED_RECIPIENTS entries must look like contact_id=+E164 (value not shown)"),
        ("clinic=+91000000000a", "ALLOWED_RECIPIENTS contact 'clinic' is not E.164"),
    ],
)
def test_contact_errors_tell_the_operator_what_to_fix(entry: str, message: str) -> None:
    with pytest.raises(InvalidContacts) as error:
        parse_contacts([entry])
    assert str(error.value) == message


@pytest.mark.parametrize("entry", [CLINIC, "clinic=+91000000000a"])
def test_contact_errors_never_echo_the_number(entry: str) -> None:
    with pytest.raises(InvalidContacts) as error:
        parse_contacts([entry])
    assert "910000000" not in str(error.value)


# ---- session layer: fakes and harness ----


class FakeBolna:
    def __init__(self) -> None:
        self.started: list[tuple[str, dict[str, str]]] = []
        self.events: list[tuple[str, str, dict[str, str]]] = []
        self.fail_start = False
        self.fail_events = False
        # Bolna never sees a reply's text. Tests that check which line would be spoken
        # set this to read the backend's in-flight text when a user_reply is published.
        self.in_flight_text: Callable[[str], str | None] | None = None
        self.injected: list[str | None] = []

    async def start_call(self, recipient: str, user_data: dict[str, str]) -> str:
        self.started.append((recipient, user_data))
        if self.fail_start:
            raise BolnaError(None, "start_call")
        return f"run-{len(self.started)}"

    async def send_event(self, run_id: str, event: str, properties: dict[str, str]) -> None:
        self.events.append((run_id, event, properties))
        if event == EVENT_USER_REPLY and self.in_flight_text is not None:
            self.injected.append(self.in_flight_text(run_id))
        if self.fail_events:
            raise BolnaError(503, "send_event")

    def replies(self) -> list[dict[str, str]]:
        return [props for _, event, props in self.events if event == EVENT_USER_REPLY]


class FakeComposer:
    def __init__(self) -> None:
        self.requests: list[ComposeRequest] = []
        self.gates: dict[tuple[str, ...], asyncio.Event] = {}

    async def compose(self, request: ComposeRequest) -> Draft:
        self.requests.append(request)
        gate = self.gates.get(tuple(request.chips))
        if gate is not None:
            await gate.wait()
        return Draft(turn_id=request.turn_id, text=draft_text(request.chips), source="template")


def draft_text(chips: list[str]) -> str:
    return "draft:" + "+".join(chips)


AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}


@dataclass
class Harness:
    client: TestClient
    manager: CallManager
    bolna: FakeBolna
    composer: FakeComposer
    seen: list[str] = field(default_factory=list)

    def start(self, contact_id: str = "clinic") -> str:
        response = self.client.post(
            "/calls", json={"contact_id": contact_id, "purpose": "doctor_appointment"}, headers=AUTH
        )
        self.seen.append(response.text)
        assert response.status_code == 200, response.text
        return response.json()["call_id"]

    def webhook(self, run_id: str, bolna_status: str, secret: str = WEBHOOK_SECRET) -> int:
        payload = {"id": run_id, "status": bolna_status, "telephony_data": {"to_number": CLINIC}}
        response = self.client.post(f"/bolna/webhook/{secret}", json=payload)
        self.seen.append(response.text)
        return response.status_code

    def live_call(self) -> str:
        call_id = self.start()
        assert self.webhook(f"run-{len(self.bolna.started)}", "in-progress") == 204
        return call_id

    def socket(self, call_id: str, headers: dict[str, str] | None = None):
        return self.client.websocket_connect(f"/calls/{call_id}/ws", headers=headers or AUTH)

    def receive(self, ws, timeout: float = 2.0) -> dict:
        # TestClient's receive blocks forever; read its stream with a deadline instead.
        async def next_message() -> dict:
            with anyio.fail_after(timeout):
                return await ws._send_rx.receive()

        message = ws.portal.call(next_message)
        ws._raise_on_close(message)
        self.seen.append(message["text"])
        return json.loads(message["text"])

    def probe(self, ws) -> dict:
        """Stop with nothing in flight answers with the status, so anything received
        before it (a stale draft, a second event) shows up first."""
        ws.send_json({"type": "stop"})
        return self.receive(ws)

    def run(self, function, *args):
        return self.client.portal.call(function, *args)


@pytest.fixture
def make_harness():
    stack = contextlib.ExitStack()

    def build(
        delivery_timeout_s: float = 5.0,
        bolna: BolnaClient | None = None,
        clock: Callable[[], float] | None = None,
    ) -> Harness:
        settings = make_settings(allowed_recipients=f"clinic={CLINIC},pharmacy={PHARMACY}")
        bolna, composer = bolna or FakeBolna(), FakeComposer()
        timing = {"clock": clock} if clock is not None else {}
        manager = CallManager(
            settings, composer, bolna, delivery_timeout_s=delivery_timeout_s, **timing
        )
        app = create_app(settings, composer=composer, bolna=bolna, ledger=manager)
        client = stack.enter_context(TestClient(app))
        return Harness(client, manager, bolna, composer)

    with stack:
        yield build


@pytest.fixture
def harness(make_harness) -> Harness:
    return make_harness()


def status(state: str) -> dict:
    return {"type": "status", "state": state}


def error(code: str) -> dict:
    return {"type": "error", "code": code}


def approve(ws, turn_id: str, text: str = TEXT) -> None:
    ws.send_json({"type": "approve", "turn_id": turn_id, "text": text})


def without_message(message: dict) -> dict:
    return {key: value for key, value in message.items() if key != "message"}


def caption(text: str, speaker: str = "receptionist") -> dict:
    return {"type": "caption", "text": text, "speaker": speaker}


def without_at(message: dict) -> dict:
    assert isinstance(message.get("at"), float), message
    return {key: value for key, value in message.items() if key != "at"}


def test_manager_rejects_malformed_allowlist_at_startup() -> None:
    settings = make_settings(allowed_recipients=CLINIC)
    with pytest.raises(InvalidContacts):
        CallManager(settings, FakeComposer(), FakeBolna())


# ---- POST /calls ----


def test_start_call_dials_allowlisted_contact_with_call_id_marker(harness: Harness) -> None:
    response = harness.client.post(
        "/calls", json={"contact_id": "pharmacy", "purpose": "doctor_appointment"}, headers=AUTH
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"call_id": body["call_id"], "state": "dialing", "mode": "live"}
    assert len(body["call_id"]) == 32 and int(body["call_id"], 16) >= 0
    assert harness.bolna.started == [(PHARMACY, {"ishara_call_id": body["call_id"]})]


def test_each_call_gets_a_fresh_id(harness: Harness) -> None:
    assert harness.start() != harness.start()


def test_unknown_contact_is_forbidden_and_bolna_untouched(harness: Harness) -> None:
    response = harness.client.post(
        "/calls", json={"contact_id": "stranger", "purpose": "doctor_appointment"}, headers=AUTH
    )
    assert response.status_code == 403
    assert harness.bolna.started == []


@pytest.mark.parametrize("token", [None, "wrong", CUSTOM_LLM_TOKEN])
def test_start_call_requires_app_token(harness: Harness, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = harness.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=headers
    )
    assert response.status_code == 401
    assert harness.bolna.started == []


def test_bolna_start_failure_is_502_and_call_in_error(harness: Harness) -> None:
    harness.bolna.fail_start = True
    response = harness.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=AUTH
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "could not start the call"}
    call_id = harness.bolna.started[0][1]["ishara_call_id"]
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("error")


def _real_client_harness(make_harness, handler, agent_id: str | None = "agent-1") -> Harness:
    """The session layer with the real HttpBolnaClient, so its error type is the one
    the session layer handles (it raises BolnaError, never bare httpx errors)."""
    client = HttpBolnaClient(
        SecretStr("test-bolna-key"), agent_id, transport=httpx.MockTransport(handler)
    )
    return make_harness(bolna=client)


@pytest.mark.parametrize(
    ("handler", "agent_id"),
    [
        (lambda _: httpx.Response(500, json={"error": "down"}), "agent-1"),
        (lambda _: httpx.Response(200, json={"execution_id": "run-1"}), None),
    ],
    ids=["bolna_500", "no_agent_id"],
)
def test_real_bolna_client_start_failure_is_502(make_harness, handler, agent_id) -> None:
    harness = _real_client_harness(make_harness, handler, agent_id)
    response = harness.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=AUTH
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "could not start the call"}


def test_real_bolna_client_event_failure_is_not_delivered(make_harness) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/call":
            return httpx.Response(200, json={"execution_id": "run-1"})
        return httpx.Response(500, json={"error": "down"})

    harness = _real_client_harness(make_harness, handler)
    call_id = harness.start()
    assert harness.webhook("run-1", "in-progress") == 204
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
        assert without_message(harness.receive(ws)) == {
            "type": "not_delivered",
            "turn_id": "t1",
            "reason": "bolna_unreachable",
        }
        assert harness.receive(ws) == status("in_call")
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert without_message(harness.receive(ws)) == error("end_failed")


# ---- WebSocket connection ----


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": f"Bearer {CUSTOM_LLM_TOKEN}"},
        {"Authorization": APP_TOKEN},
        {"Authorization": f"Basic {APP_TOKEN}"},
    ],
)
def test_socket_rejects_bad_token(harness: Harness, headers: dict[str, str]) -> None:
    call_id = harness.start()
    socket = harness.socket(call_id, headers=headers or {"X": "y"})
    with socket as ws, pytest.raises(WebSocketDisconnect) as closed:
        harness.receive(ws)
    assert closed.value.code == 4401


def test_socket_accepts_lowercase_bearer_scheme(harness: Harness) -> None:
    call_id = harness.start()
    with harness.socket(call_id, headers={"Authorization": f"bearer {APP_TOKEN}"}) as ws:
        assert harness.receive(ws) == status("dialing")


def test_socket_for_unknown_call_closes(harness: Harness) -> None:
    with harness.socket("nope") as ws, pytest.raises(WebSocketDisconnect) as closed:
        harness.receive(ws)
    assert closed.value.code == 4404


def test_socket_sends_current_status_on_connect(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("in_call")


def test_new_socket_replaces_old_one(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as old:
        harness.receive(old)
        with harness.socket(call_id) as new:
            assert harness.receive(new) == status("in_call")
            with pytest.raises(WebSocketDisconnect) as closed:
                harness.receive(old)
            assert closed.value.code == 4409
            harness.run(harness.manager.record_caption, call_id, "Hello?")
            assert harness.receive(new)["type"] == "caption"


def test_replaced_socket_messages_are_ignored(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as old:
        harness.receive(old)
        with harness.socket(call_id) as new:
            harness.receive(new)
            approve(old, "t1")
            assert harness.probe(new) == status("in_call")
    assert harness.bolna.events == []


def test_malformed_message_gets_error_and_nothing_else(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_text("not json")
        assert without_message(harness.receive(ws)) == error("bad_message")
        ws.send_json({"type": "speak", "text": TEXT})
        assert without_message(harness.receive(ws)) == error("bad_message")
    assert harness.bolna.events == []


# ---- chips and drafts ----


def test_chips_compose_a_draft_for_the_turn(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["hello", "doctor"]})
        assert harness.receive(ws) == {
            "type": "draft",
            "turn_id": "t1",
            "text": "draft:hello+doctor",
            "source": "template",
        }
    request = harness.composer.requests[0]
    assert request.purpose == "doctor_appointment" and request.last_caption is None


def test_empty_chips_do_not_compose(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": []})
        assert harness.probe(ws) == status("in_call")
    assert harness.composer.requests == []


def test_stale_draft_dropped_when_chips_change_during_slow_compose(harness: Harness) -> None:
    gate = asyncio.Event()
    harness.composer.gates[("hello",)] = gate
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["hello"]})
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["hello", "doctor"]})
        assert harness.receive(ws)["text"] == "draft:hello+doctor"
        harness.run(gate.set)
        assert harness.probe(ws) == status("in_call")
    assert len(harness.composer.requests) == 2


def test_draft_for_superseded_turn_dropped(harness: Harness) -> None:
    gate = asyncio.Event()
    harness.composer.gates[("hello",)] = gate
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["hello"]})
        ws.send_json({"type": "chips", "turn_id": "t2", "chips": ["no"]})
        assert harness.receive(ws)["turn_id"] == "t2"
        harness.run(gate.set)
        assert harness.probe(ws) == status("in_call")


def test_caption_forwarded_and_used_as_last_caption(harness: Harness) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("dialing")
        harness.run(harness.manager.record_caption, call_id, "We have 4 pm tomorrow.")
        assert harness.receive(ws) == status("in_call")
        assert without_at(harness.receive(ws)) == caption(DISCLOSURE, "agent")
        assert without_at(harness.receive(ws)) == caption("We have 4 pm tomorrow.")
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["no", "morning"]})
        harness.receive(ws)
    assert harness.composer.requests[0].last_caption == "We have 4 pm tomorrow."


def test_stale_chips_rejected(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": []})
        ws.send_json({"type": "chips", "turn_id": "t2", "chips": []})
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["yes"]})
        assert without_message(harness.receive(ws)) == error("stale_turn")
    assert harness.composer.requests == []


# ---- approval (SEND) ----


def test_send_publishes_one_user_reply_event(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
    # Bolna never puts event properties in a prompt; the turn id is only for its logs.
    assert harness.bolna.events == [("run-1", EVENT_USER_REPLY, {"turn_id": "t1"})]


# ---- Bolna's speak-node request ----

# What Bolna's execution log showed our custom LLM receive for the speak node on the
# first real call (28 Oct): `user_data` filled, the user_reply properties not, each
# `{{var}}` left as `{var}`, and an event notice without the properties.
LIVE_SPEAK_PROMPT = (
    "ISHARA_CALL_ID: {call_id}\nISHARA_NODE: speak\nISHARA_TURN_ID: {{turn_id}}\n"
    "ISHARA_REPLY_START\n{{reply_text}}\nISHARA_REPLY_END\n\n"
    "Say exactly the text between ISHARA_REPLY_START and ISHARA_REPLY_END, word for "
    "word, and nothing else."
)
SPEAK_PROMPTS = {
    "live log": lambda call_id: LIVE_SPEAK_PROMPT.format(call_id=call_id),
    "agent.json": lambda call_id: bolna_render(SPEAK_PROMPT, {USER_DATA_CALL_ID: call_id}),
}


def speak_request(harness: Harness, call_id: str, prompt: str | None = None) -> str:
    """Bolna's speak-node request after a user_reply event; returns the streamed text."""
    messages = [
        {"role": "system", "content": prompt or SPEAK_PROMPTS["live log"](call_id)},
        {"role": "assistant", "content": DISCLOSURE},
        {"role": "system", "content": EVENT_NOTICE.format(event=EVENT_USER_REPLY)},
    ]
    response = harness.client.post(
        "/v1/chat/completions",
        json={"model": "ishara-relay", "stream": True, "messages": messages},
        headers={"Authorization": f"Bearer {CUSTOM_LLM_TOKEN}"},
    )
    assert response.status_code == 200, response.text
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    return "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)


@pytest.mark.parametrize("prompt", SPEAK_PROMPTS.values(), ids=SPEAK_PROMPTS.keys())
def test_bolna_speak_request_speaks_the_approved_turn(harness: Harness, prompt) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
        assert speak_request(harness, call_id, prompt(call_id)) == TEXT
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}
        assert harness.receive(ws) == status("in_call")


def test_second_speak_request_for_the_same_turn_says_nothing(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert speak_request(harness, call_id) == TEXT
        assert speak_request(harness, call_id) == ""
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}
        assert harness.receive(ws) == status("in_call")
        assert harness.probe(ws) == status("in_call")


def test_speak_request_without_an_approved_turn_says_nothing(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["yes"]})
        assert harness.receive(ws)["type"] == "draft"
        assert speak_request(harness, call_id) == ""
        assert harness.probe(ws) == status("in_call")


def test_speak_request_claims_only_its_own_calls_turn(harness: Harness) -> None:
    quiet, busy = harness.live_call(), harness.live_call()
    with harness.socket(busy) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert speak_request(harness, quiet) == ""
        assert speak_request(harness, busy) == TEXT
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}


def test_speak_request_after_stop_says_nothing(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "stop"})
        assert harness.receive(ws) == status("in_call")
        assert speak_request(harness, call_id) == ""
        assert harness.probe(ws) == status("in_call")


def test_speak_request_after_not_delivered_says_nothing(make_harness) -> None:
    harness = make_harness(delivery_timeout_s=0.05)
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert harness.receive(ws)["type"] == "not_delivered"
        assert harness.receive(ws) == status("in_call")
        assert speak_request(harness, call_id) == ""
        assert harness.probe(ws) == status("in_call")


def test_speak_request_after_the_end_says_nothing(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert speak_request(harness, call_id) == ""
        assert without_at(harness.receive(ws)) == caption(GOODBYE, "agent")
        assert harness.probe(ws) == status("ended")


def test_double_send_speaks_once(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        approve(ws, "t1")
        assert without_message(harness.receive(ws)) == error("already_approved")
        assert len(harness.bolna.replies()) == 1
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        assert harness.run(harness.manager.claim_in_flight, call_id) is None


def test_stale_approval_rejected(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": []})
        ws.send_json({"type": "chips", "turn_id": "t2", "chips": []})
        approve(ws, "t1")
        assert without_message(harness.receive(ws)) == error("stale_turn")
        assert harness.bolna.events == []
        assert harness.run(harness.manager.claim_in_flight, call_id) is None


@pytest.mark.parametrize("bolna_status", [None, "ringing"])
def test_approval_before_live_rejected(harness: Harness, bolna_status: str | None) -> None:
    call_id = harness.start()
    if bolna_status:
        harness.webhook("run-1", bolna_status)
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert without_message(harness.receive(ws)) == error("call_not_live")
    assert harness.bolna.events == []


def test_approval_after_end_rejected(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert without_at(harness.receive(ws)) == caption(GOODBYE, "agent")
        approve(ws, "t1")
        assert without_message(harness.receive(ws)) == error("call_ended")
    assert harness.bolna.replies() == []


def test_quick_reply_approval_needs_no_chips(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "quick-1", "Sorry, could you please repeat that?")
        assert harness.receive(ws) == status("speaking")
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply(
            "quick-1", "Sorry, could you please repeat that?"
        )
    assert harness.bolna.replies() == [{"turn_id": "quick-1"}]


def test_unknown_call_ids_are_ignored_by_the_ledger(harness: Harness) -> None:
    manager = harness.manager
    assert harness.run(manager.claim_in_flight, "nope") is None
    assert harness.run(manager.record_caption, "nope", "Hi") is None
    assert harness.run(manager.record_agent_line, "nope", HOLDING_LINE) is None
    assert harness.run(manager.mark_spoken, "nope", "t1") is None


def test_mark_spoken_confirms_delivery(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}
        assert harness.receive(ws) == status("in_call")


def test_mark_spoken_without_claim_is_ignored(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}
        assert harness.receive(ws) == status("in_call")


def test_not_delivered_after_timeout_and_late_claim_false(make_harness) -> None:
    harness = make_harness(delivery_timeout_s=0.05)
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
        assert harness.receive(ws) == {
            "type": "not_delivered",
            "turn_id": "t1",
            "reason": "no_confirmation",
        }
        assert harness.receive(ws) == status("in_call")
        assert harness.run(harness.manager.claim_in_flight, call_id) is None
        approve(ws, "t1")
        assert without_message(harness.receive(ws)) == error("already_approved")
    assert len(harness.bolna.replies()) == 1


def test_resend_with_new_turn_after_not_delivered(make_harness) -> None:
    harness = make_harness(delivery_timeout_s=0.05)
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert harness.receive(ws)["type"] == "not_delivered"
        harness.receive(ws)
        approve(ws, "t1-retry")
        assert harness.receive(ws) == status("speaking")
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply(
            "t1-retry", TEXT
        )
        harness.run(harness.manager.mark_spoken, call_id, "t1-retry")
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1-retry"}
    assert [reply["turn_id"] for reply in harness.bolna.replies()] == ["t1", "t1-retry"]


def test_confirmed_delivery_never_reports_not_delivered(make_harness) -> None:
    harness = make_harness(delivery_timeout_s=0.1)
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        harness.receive(ws)
        harness.receive(ws)
        harness.run(anyio.sleep, 0.2)
        assert harness.probe(ws) == status("in_call")


def test_superseding_approval_keeps_its_own_delivery_timer(make_harness) -> None:
    harness = make_harness(delivery_timeout_s=0.05)
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        approve(ws, "t2", "No.")
        assert harness.receive(ws) == {
            "type": "not_delivered",
            "turn_id": "t2",
            "reason": "no_confirmation",
        }
        assert harness.receive(ws) == status("in_call")
        assert harness.run(harness.manager.claim_in_flight, call_id) is None
    assert [reply["turn_id"] for reply in harness.bolna.replies()] == ["t1", "t2"]


def test_send_event_failure_reports_not_delivered(harness: Harness) -> None:
    harness.bolna.fail_events = True
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
        assert harness.receive(ws) == {
            "type": "not_delivered",
            "turn_id": "t1",
            "reason": "bolna_unreachable",
        }
        assert harness.receive(ws) == status("in_call")
        assert harness.run(harness.manager.claim_in_flight, call_id) is None


def test_busy_while_a_reply_is_being_spoken(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        approve(ws, "t2", "No.")
        assert without_message(harness.receive(ws)) == error("busy_speaking")
    assert len(harness.bolna.replies()) == 1


# ---- stop, new turn, disconnect, end ----


def test_stop_before_claim_cancels(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "stop"})
        assert harness.receive(ws) == status("in_call")
        assert harness.run(harness.manager.claim_in_flight, call_id) is None


def test_stop_reports_the_new_status_exactly_once(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "stop"})
        assert harness.receive(ws) == status("in_call")
        ws.send_json({"type": "chips", "turn_id": "t2", "chips": ["yes"]})
        assert harness.receive(ws)["type"] == "draft", "a second status was sent for one stop"


def test_stop_after_claim_cannot_interrupt(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        ws.send_json({"type": "stop"})
        assert without_message(harness.receive(ws)) == error("cannot_interrupt")
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}


def test_new_turn_revokes_unclaimed_approval(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t2", "chips": []})
        assert harness.receive(ws) == status("in_call")
        assert harness.run(harness.manager.claim_in_flight, call_id) is None


def test_app_disconnect_revokes_unclaimed_approval(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
    assert harness.run(harness.manager.claim_in_flight, call_id) is None
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("in_call")


def test_replaced_socket_does_not_revoke_approval(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as old:
        harness.receive(old)
        approve(old, "t1")
        harness.receive(old)
        with harness.socket(call_id) as new:
            assert harness.receive(new) == status("speaking")
            assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)


def test_end_sends_end_call_and_wipes_state(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert without_at(harness.receive(ws)) == caption(GOODBYE, "agent")
        ws.send_json({"type": "chips", "turn_id": "t2", "chips": ["no"]})
        assert without_message(harness.receive(ws)) == error("call_ended")
        harness.run(harness.manager.record_caption, call_id, "Hello?")
        assert harness.probe(ws) == status("ended")
        assert harness.bolna.events[-1] == ("run-1", EVENT_END_CALL, {})
        assert harness.run(harness.manager.claim_in_flight, call_id) is None
    assert harness.composer.requests == []


def test_second_end_does_not_hang_up_twice(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert without_at(harness.receive(ws)) == caption(GOODBYE, "agent")
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended"), "no second goodbye"
    assert [event for _, event, _ in harness.bolna.events] == [EVENT_END_CALL]


def test_end_failure_is_reported(harness: Harness) -> None:
    harness.bolna.fail_events = True
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert without_message(harness.receive(ws)) == error("end_failed")
        assert harness.probe(ws) == status("ended"), "no goodbye when Bolna was not reached"


# ---- agent lines (said without a SEND) ----


def test_disclosure_is_shown_once_when_the_call_goes_live(harness: Harness) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("dialing")
        harness.webhook("run-1", "ringing")
        assert harness.receive(ws) == status("ringing")
        harness.webhook("run-1", "in-progress")
        assert harness.receive(ws) == status("in_call")
        assert without_at(harness.receive(ws)) == caption(DISCLOSURE, "agent")
        harness.webhook("run-1", "in-progress")
        harness.webhook("run-1", "ringing")
        harness.run(harness.manager.record_caption, call_id, "Hello?")
        assert without_at(harness.receive(ws)) == caption("Hello?")
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}
        assert harness.receive(ws) == status("in_call"), "speaking → in_call is not going live"
        assert harness.probe(ws) == status("in_call")
    with harness.socket(call_id) as again:
        assert harness.receive(again) == status("in_call")
        assert harness.probe(again) == status("in_call"), "a reconnect gets no second disclosure"
    assert sum(DISCLOSURE in seen for seen in harness.seen) == 1


@pytest.mark.parametrize("bolna_status", ["no-answer", "busy", "failed"])
def test_no_disclosure_when_the_call_never_connects(harness: Harness, bolna_status: str) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.webhook("run-1", "ringing")
        harness.receive(ws)
        harness.webhook("run-1", bolna_status)
        harness.receive(ws)
        harness.webhook("run-1", "in-progress")
        assert harness.probe(ws)["type"] == "status"
    assert not any(DISCLOSURE in seen for seen in harness.seen)


def test_agent_line_is_an_agent_caption_and_changes_no_state(harness: Harness) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("dialing")
        harness.run(harness.manager.record_agent_line, call_id, HOLDING_LINE)
        assert without_at(harness.receive(ws)) == caption(HOLDING_LINE, "agent")
        assert harness.probe(ws) == status("dialing"), "an agent line doesn't prove the line"


def test_agent_line_leaves_approvals_alone(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        assert harness.receive(ws) == status("speaking")
        harness.run(harness.manager.record_agent_line, call_id, HOLDING_LINE)
        assert without_at(harness.receive(ws)) == caption(HOLDING_LINE, "agent")
        assert harness.run(harness.manager.claim_in_flight, call_id) == ClaimedReply("t1", TEXT)
        harness.run(harness.manager.mark_spoken, call_id, "t1")
        assert harness.receive(ws) == {"type": "spoken", "turn_id": "t1"}


def test_composer_context_stays_the_receptionist_caption(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.run(harness.manager.record_caption, call_id, "We have 4 pm tomorrow.")
        harness.receive(ws)
        harness.run(harness.manager.record_agent_line, call_id, HOLDING_LINE)
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["no", "morning"]})
        assert harness.receive(ws)["type"] == "draft"
    assert harness.composer.requests[0].last_caption == "We have 4 pm tomorrow."


def test_agent_line_with_no_receptionist_caption_leaves_composer_context_empty(
    harness: Harness,
) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.webhook("run-1", "in-progress")
        harness.receive(ws)
        assert without_at(harness.receive(ws)) == caption(DISCLOSURE, "agent")
        harness.run(harness.manager.record_agent_line, call_id, HOLDING_LINE)
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["hello"]})
        assert harness.receive(ws)["type"] == "draft"
    assert harness.composer.requests[0].last_caption is None


def test_agent_line_after_the_call_ended_is_dropped(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.webhook("run-1", "completed")
        assert harness.receive(ws) == status("ended")
        harness.run(harness.manager.record_agent_line, call_id, HOLDING_LINE)
        assert harness.probe(ws) == status("ended")


def test_no_goodbye_when_bolna_ends_the_call(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.webhook("run-1", "call-disconnected")
        assert harness.receive(ws) == status("ended")
        assert harness.probe(ws) == status("ended")
    assert not any(GOODBYE in seen for seen in harness.seen)


def test_goodbye_is_sent_only_after_end_call_reached_bolna(harness: Harness) -> None:
    order: list[str] = []
    send_event = harness.bolna.send_event

    async def recording_send_event(run_id: str, event: str, properties: dict[str, str]) -> None:
        order.append(f"event {event}")
        await send_event(run_id, event, properties)

    harness.bolna.send_event = recording_send_event
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        ws.send_json({"type": "end"})
        assert harness.receive(ws) == status("ended")
        assert without_at(harness.receive(ws)) == caption(GOODBYE, "agent")
        order.append("goodbye shown")
    assert order == [f"event {EVENT_END_CALL}", "goodbye shown"]


# ---- Bolna status webhook ----


def test_webhook_maps_bolna_statuses(harness: Harness) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("dialing")
        assert harness.webhook("run-1", "queued") == 204
        assert harness.webhook("run-1", "ringing") == 204
        assert harness.receive(ws) == status("ringing")
        assert harness.webhook("run-1", "in-progress") == 204
        assert harness.receive(ws) == status("in_call")
        assert without_at(harness.receive(ws)) == caption(DISCLOSURE, "agent")
        assert harness.webhook("run-1", "ringing") == 204
        assert harness.webhook("run-1", "completed") == 204
        assert harness.receive(ws) == status("ended")


@pytest.mark.parametrize(
    ("bolna_status", "state"),
    [
        ("call-disconnected", "ended"),
        ("no-answer", "ended"),
        ("busy", "ended"),
        ("failed", "error"),
        ("error", "error"),
        ("balance-low", "error"),
    ],
)
def test_webhook_terminal_statuses(harness: Harness, bolna_status: str, state: str) -> None:
    call_id = harness.start()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.webhook("run-1", bolna_status)
        assert harness.receive(ws) == status(state)


def test_webhook_end_revokes_pending_approval(harness: Harness) -> None:
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        harness.webhook("run-1", "call-disconnected")
        assert harness.receive(ws) == status("ended")
        assert harness.run(harness.manager.claim_in_flight, call_id) is None
        assert harness.bolna.events[-1][1] == EVENT_USER_REPLY


def test_webhook_secret_checked(harness: Harness) -> None:
    call_id = harness.start()
    assert harness.webhook("run-1", "in-progress", secret="wrong") == 404
    assert harness.webhook("run-1", "in-progress", secret=APP_TOKEN) == 404
    assert harness.webhook("run-1", "in-progress", secret=CUSTOM_LLM_TOKEN) == 404
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("dialing")


def test_webhook_ignores_unknown_runs(harness: Harness) -> None:
    call_id = harness.start()
    assert harness.webhook("run-999", "in-progress") == 204
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("dialing")


def test_webhook_accepts_numeric_execution_ids(harness: Harness) -> None:
    harness.bolna.start_call = _numeric_start(harness.bolna)
    call_id = harness.start()
    response = harness.client.post(
        f"/bolna/webhook/{WEBHOOK_SECRET}", json={"id": 7432382142914, "status": "ringing"}
    )
    assert response.status_code == 204
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("ringing")


def _numeric_start(bolna: FakeBolna):
    async def start_call(recipient: str, user_data: dict[str, str]) -> str:
        bolna.started.append((recipient, user_data))
        return "7432382142914"

    return start_call


def test_webhook_bad_payload_does_not_echo_it(harness: Harness) -> None:
    response = harness.client.post(
        f"/bolna/webhook/{WEBHOOK_SECRET}", json={"telephony_data": {"to_number": CLINIC}}
    )
    assert response.status_code == 422
    assert CLINIC not in response.text


# ---- finished calls leave memory ----


@dataclass
class FakeClock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def notes_status(harness: Harness, call_id: str) -> int:
    return harness.client.get(f"/calls/{call_id}/notes", headers=AUTH).status_code


def test_finished_call_stays_readable_until_the_ttl_then_is_dropped(make_harness) -> None:
    clock = FakeClock()
    harness = make_harness(clock=clock)
    call_id = harness.live_call()
    assert harness.webhook("run-1", "call-disconnected") == 204

    clock.now += FINISHED_CALL_TTL_S - 1
    # The app polls for Bolna's late summary: reading the notes doesn't drop the call.
    for _ in range(11):
        assert notes_status(harness, call_id) == 200
    assert harness.manager.has_call(call_id)

    clock.now += 1
    assert notes_status(harness, call_id) == 404
    assert not harness.manager.has_call(call_id)


def test_the_ttl_counts_from_the_end_of_the_call(make_harness) -> None:
    clock = FakeClock()
    harness = make_harness(clock=clock)
    call_id = harness.live_call()
    clock.now += 2 * FINISHED_CALL_TTL_S
    assert harness.webhook("run-1", "call-disconnected") == 204
    # A later webhook (Bolna's `completed`) doesn't restart the clock.
    clock.now += FINISHED_CALL_TTL_S / 2
    assert harness.webhook("run-1", "completed") == 204

    clock.now += FINISHED_CALL_TTL_S / 2 - 1
    assert notes_status(harness, call_id) == 200
    clock.now += 1
    assert notes_status(harness, call_id) == 404


def test_active_calls_are_never_dropped(make_harness) -> None:
    clock = FakeClock()
    harness = make_harness(clock=clock)
    dialing = harness.start()
    live = harness.live_call()
    ended = harness.start("pharmacy")
    assert harness.webhook("run-3", "completed") == 204

    clock.now += 10 * FINISHED_CALL_TTL_S
    assert notes_status(harness, ended) == 404
    assert notes_status(harness, dialing) == 200
    assert notes_status(harness, live) == 200
    with harness.socket(live) as ws:
        assert harness.receive(ws) == status("in_call")


def test_a_call_that_failed_to_start_is_dropped_after_the_ttl(make_harness) -> None:
    clock = FakeClock()
    harness = make_harness(clock=clock)
    harness.bolna.fail_start = True
    response = harness.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=AUTH
    )
    assert response.status_code == 502
    (failed,) = harness.manager._sessions
    clock.now += FINISHED_CALL_TTL_S
    harness.bolna.fail_start = False
    harness.start()
    assert failed not in harness.manager._sessions


def test_a_dropped_call_ignores_late_webhooks_and_its_socket(make_harness) -> None:
    clock = FakeClock()
    harness = make_harness(clock=clock)
    call_id = harness.live_call()
    with harness.socket(call_id) as ws:
        assert harness.receive(ws) == status("in_call")
        assert harness.webhook("run-1", "completed") == 204
        assert harness.receive(ws) == status("ended")
        clock.now += FINISHED_CALL_TTL_S
        assert notes_status(harness, call_id) == 404
        # The app leaving after the call was dropped is no error.

    assert harness.webhook("run-1", "completed") == 204
    assert notes_status(harness, call_id) == 404
    with pytest.raises(WebSocketDisconnect) as closed, harness.socket(call_id) as ws:
        harness.receive(ws)
    assert closed.value.code == 4404


# ---- privacy ----


def test_number_never_in_any_response_message_or_log(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    call_id = harness.live_call()
    forbidden = harness.client.post(
        "/calls", json={"contact_id": "stranger", "purpose": "doctor_appointment"}, headers=AUTH
    )
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        harness.run(harness.manager.record_caption, call_id, "Hello?")
        harness.receive(ws)
        ws.send_json({"type": "chips", "turn_id": "t1", "chips": ["hello"]})
        harness.receive(ws)
        approve(ws, "t1")
        harness.receive(ws)
        ws.send_json({"type": "end"})
        harness.receive(ws)
    harness.bolna.fail_start = True
    failed = harness.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=AUTH
    )
    seen = harness.seen + [forbidden.text, failed.text]
    assert len(seen) == 9
    for text in seen + [caplog.text]:
        assert "910000000" not in text


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if r.name == "app.calls" and r.levelname == "WARNING"
    ]


def test_bolna_failures_are_logged_with_call_id_and_error_kind(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    # Demo-day debugging relies on these lines in the Heroku log: which call, which
    # step, which error kind, and never the number or Bolna's response body.
    caplog.set_level(logging.INFO)
    call_id = harness.live_call()
    assert f"call {call_id}: dialing contact clinic" in [r.getMessage() for r in caplog.records]
    harness.bolna.fail_events = True
    with harness.socket(call_id) as ws:
        harness.receive(ws)
        approve(ws, "t1")
        for _ in range(3):  # speaking, not_delivered, in_call
            harness.receive(ws)
        ws.send_json({"type": "end"})
        harness.receive(ws)
        harness.receive(ws)
    harness.bolna.fail_start = True
    harness.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=AUTH
    )
    failed_call = harness.bolna.started[-1][1]["ishara_call_id"]

    assert _warnings(caplog) == [
        f"call {call_id}: user_reply failed (BolnaError)",
        f"call {call_id}: end_call failed (BolnaError)",
        f"call {failed_call}: Bolna start failed (BolnaError)",
    ]
