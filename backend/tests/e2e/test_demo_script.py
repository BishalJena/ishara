"""PLAN.md §1 demo script end to end, with no network and no paid calls.

Real backend modules (CallManager, the custom-LLM router, build_composer with no Groq
key, so templates only) and FakeBolna playing Bolna's graph runtime over ASGI. The app
side is driven through the TestClient WebSocket exactly like the iPhone would.

The module skips until tasks V2, V5 and V6 have landed, then runs unchanged.
"""

from __future__ import annotations

import importlib
import importlib.util
import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app import custom_llm
from app.main import create_app
from app.markers import DISCLOSURE, GOODBYE, HOLDING_LINE, SILENCE_MARKER
from fakes.fake_bolna import FakeBolna, FakeRun, asgi_client
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, WEBHOOK_SECRET, make_settings


def _module_has(module_name: str, attribute: str) -> bool:
    if importlib.util.find_spec(module_name) is None:
        return False
    return hasattr(importlib.import_module(module_name), attribute)


def _missing_contracts() -> list[str]:
    missing = []
    if not _module_has("app.calls", "CallManager"):
        missing.append("app.calls.CallManager (V6)")
    if not _module_has("app.composer", "build_composer"):
        missing.append("app.composer.build_composer (V5)")
    llm_paths = {getattr(route, "path", None) for route in custom_llm.router.routes}
    if "/v1/chat/completions" not in llm_paths:
        missing.append("POST /v1/chat/completions on app.custom_llm.router (V2)")
    return missing


_MISSING = _missing_contracts()
if _MISSING:
    pytest.skip(
        "E2E demo script waits for backend modules: " + ", ".join(_MISSING),
        allow_module_level=True,
    )

calls_module = importlib.import_module("app.calls")
composer_module = importlib.import_module("app.composer")

CONTACT = "clinic"
NUMBER = "+910000000011"
PURPOSE = "doctor_appointment"
AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}
TIMEOUT_S = 5.0
RING_S = 0.3  # long enough for the app socket to connect before the call is answered

T2_CAPTION = "We have 4 pm tomorrow. Does that work?"
T4_CAPTION = "Yes, 10:30 tomorrow morning."

_CLOSED = object()


class AppSocket:
    """The iPhone's side of `/calls/{id}/ws`. A reader thread fills an inbox so every
    wait has a timeout instead of hanging the suite when a message never comes."""

    def __init__(self, ws: WebSocketTestSession) -> None:
        self._ws = ws
        self._inbox: queue.Queue[Any] = queue.Queue()
        self.seen: list[dict[str, Any]] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        while True:
            try:
                message = self._ws.receive_json()
            except (WebSocketDisconnect, anyio.EndOfStream, anyio.ClosedResourceError):
                self._inbox.put(_CLOSED)
                return
            self._inbox.put(message)

    def send(self, message: dict[str, Any]) -> None:
        self._ws.send_json(message)

    def expect(self, kind: str, timeout_s: float = TIMEOUT_S, **fields: Any) -> dict[str, Any]:
        """Next message of this type with these fields; earlier others are kept in `seen`."""
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                message = self._inbox.get(timeout=max(deadline - time.monotonic(), 0))
            except queue.Empty:
                pytest.fail(f"no {kind} {fields} within {timeout_s}s; seen {self.seen}")
            if message is _CLOSED:
                pytest.fail(f"socket closed while waiting for {kind} {fields}; seen {self.seen}")
            self.seen.append(message)
            if message["type"] == kind and all(message.get(k) == v for k, v in fields.items()):
                return message

    def drain(self) -> None:
        while not self._inbox.empty():
            message = self._inbox.get_nowait()
            if message is not _CLOSED:
                self.seen.append(message)

    def matching(self, kind: str, **fields: Any) -> list[dict[str, Any]]:
        self.drain()
        return [
            message
            for message in self.seen
            if message["type"] == kind and all(message.get(k) == v for k, v in fields.items())
        ]

    def draft(self, turn_id: str, chips: list[str]) -> str:
        self.send({"type": "chips", "turn_id": turn_id, "chips": chips})
        draft = self.expect("draft", turn_id=turn_id)
        assert draft["source"] == "template", "no Groq key, so only templates may draft"
        assert draft["text"]
        return draft["text"]

    def approve(self, turn_id: str, text: str) -> None:
        self.send({"type": "approve", "turn_id": turn_id, "text": text})

    def round_trip(self, turn_id: str) -> None:
        """Barrier: the backend handles messages in order, so once this draft is back,
        every earlier message has been processed."""
        self.draft(turn_id, ["hello"])


@dataclass
class Harness:
    client: TestClient
    fake: FakeBolna

    def portal_call(self, func: Callable[..., Any], *args: Any) -> Any:
        """Run a FakeBolna coroutine on the app's event loop."""
        assert self.client.portal is not None
        return self.client.portal.call(func, *args)

    def start_call(self) -> str:
        response = self.client.post(
            "/calls", json={"contact_id": CONTACT, "purpose": PURPOSE}, headers=AUTH
        )
        assert response.is_success, response.text
        return response.json()["call_id"]

    @contextmanager
    def socket(self, call_id: str) -> Iterator[AppSocket]:
        with self.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
            yield AppSocket(ws)

    def run_for(self, call_id: str) -> FakeRun:
        return self.portal_call(self.fake.run_for_call, call_id)

    def says(self, run: FakeRun, text: str) -> str:
        return self.portal_call(self.fake.receptionist_says, run.run_id, text)

    def silence(self, run: FakeRun) -> str:
        return self.portal_call(self.fake.silence, run.run_id)

    def idle(self) -> None:
        self.portal_call(self.fake.wait_idle)


@pytest.fixture
def make_harness() -> Iterator[Callable[..., Harness]]:
    with ExitStack() as stack:

        def make(delivery_timeout_s: float = TIMEOUT_S) -> Harness:
            settings = make_settings(groq_api_key=None, allowed_recipients=f"{CONTACT}={NUMBER}")
            fake = FakeBolna(CUSTOM_LLM_TOKEN, webhook_secret=WEBHOOK_SECRET)
            composer = composer_module.build_composer(settings)
            manager = calls_module.CallManager(
                settings, composer, fake, delivery_timeout_s=delivery_timeout_s
            )
            app = create_app(settings, composer=composer, bolna=fake, ledger=manager)
            fake.attach(asgi_client(app))
            return Harness(stack.enter_context(TestClient(app)), fake)

        yield make


@pytest.fixture
def harness(make_harness: Callable[..., Harness]) -> Harness:
    return make_harness()


def _transcript(app: AppSocket) -> list[tuple[str, str]]:
    """What the user sees, in order: captions by speaker and spoken turns."""
    app.drain()
    lines = []
    for message in app.seen:
        if message["type"] == "caption":
            lines.append((message["speaker"], message["text"]))
        elif message["type"] == "spoken":
            lines.append(("spoken", message["turn_id"]))
    return lines


def _speak_requests(run: FakeRun) -> int:
    return sum("ISHARA_NODE: speak" in body["messages"][0]["content"] for body in run.llm_requests)


# ---- the rehearsed script ----


def test_plan_demo_script_end_to_end(harness: Harness) -> None:
    harness.fake.ring_s = RING_S
    call_id = harness.start_call()

    with harness.socket(call_id) as app:
        app.expect("status", state="in_call")
        run = harness.run_for(call_id)
        assert harness.fake.recipients == [NUMBER]
        assert run.spoken == [DISCLOSURE]  # turn 0
        app.expect("caption", text=DISCLOSURE, speaker="agent")

        t1 = app.draft("t1", ["hello", "doctor", "tomorrow"])
        assert "doctor" in t1.lower() and "tomorrow" in t1.lower()
        assert run.spoken == [DISCLOSURE], "a draft alone must never be spoken"
        app.approve("t1", t1)
        app.expect("spoken", turn_id="t1")
        harness.idle()
        assert run.spoken == [DISCLOSURE, t1]
        assert harness.fake.events_for("user_reply")[-1].properties == {"turn_id": "t1"}

        harness.says(run, T2_CAPTION)
        app.expect("caption", text=T2_CAPTION, speaker="receptionist")
        # The user takes a while to sign T3: Bolna's silence repeat fills the pause.
        assert harness.silence(run) == HOLDING_LINE
        app.expect("caption", text=HOLDING_LINE, speaker="agent")

        with_wrong_chip = app.draft("t3", ["no", "morning", "afternoon"])
        assert "afternoon" in with_wrong_chip
        t3 = app.draft("t3", ["no", "morning"])  # 3b: wrong chip removed with ✕
        assert "morning" in t3 and "afternoon" not in t3
        app.approve("t3", t3)
        app.expect("spoken", turn_id="t3")

        harness.says(run, T4_CAPTION)
        app.expect("caption", text=T4_CAPTION, speaker="receptionist")

        t5 = app.draft("t5", ["yes", "thankyou"])
        assert "thank" in t5.lower()
        app.approve("t5", t5)
        app.expect("spoken", turn_id="t5")

        app.send({"type": "end"})
        app.expect("status", state="ended")
        app.expect("caption", text=GOODBYE, speaker="agent")
        harness.idle()

    assert run.spoken == [DISCLOSURE, t1, HOLDING_LINE, t3, t5, GOODBYE]
    assert run.ended
    assert harness.fake.events[-1].event == "end_call"
    assert _transcript(app) == [
        ("agent", DISCLOSURE),
        ("spoken", "t1"),
        ("receptionist", T2_CAPTION),
        ("agent", HOLDING_LINE),
        ("spoken", "t3"),
        ("receptionist", T4_CAPTION),
        ("spoken", "t5"),
        ("agent", GOODBYE),
    ]


# ---- safety edge cases ----


def test_nothing_is_spoken_before_send(harness: Harness) -> None:
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        app.draft("t1", ["hello", "doctor", "tomorrow"])
        harness.says(run, T2_CAPTION)
        app.expect("caption", text=T2_CAPTION)
        app.draft("t2", ["no", "morning"])
        harness.idle()

    assert run.spoken == [DISCLOSURE]
    assert harness.fake.events_for("user_reply") == []


def test_double_send_speaks_once(harness: Harness) -> None:
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        text = app.draft("t1", ["hello", "doctor", "tomorrow"])
        app.approve("t1", text)
        app.approve("t1", text)
        app.expect("spoken", turn_id="t1")
        app.round_trip("t2")
        harness.idle()

        assert run.spoken == [DISCLOSURE, text]
        assert len(app.matching("spoken", turn_id="t1")) == 1


def test_duplicate_event_delivery_speaks_once(harness: Harness) -> None:
    harness.fake.duplicate_events = True
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        text = app.draft("t1", ["hello", "doctor", "tomorrow"])
        app.approve("t1", text)
        app.expect("spoken", turn_id="t1")
        harness.idle()
        app.round_trip("t2")

        assert _speak_requests(run) == 2, "both deliveries must reach the custom LLM"
        assert run.spoken == [DISCLOSURE, text]
        assert len(app.matching("spoken", turn_id="t1")) == 1


def test_stale_turn_approval_is_not_spoken(harness: Harness) -> None:
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        stale = app.draft("t1", ["hello", "doctor", "tomorrow"])
        app.draft("t2", ["no", "morning"])
        app.approve("t1", stale)
        app.round_trip("t3")
        harness.idle()

        assert run.spoken == [DISCLOSURE]
        assert app.matching("spoken", turn_id="t1") == []


def test_send_during_receptionist_speech_is_not_delivered_then_resent_once(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(delivery_timeout_s=0.3)
    harness.fake.receptionist_mid_speech = True  # ledger B24
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        text = app.draft("t1", ["hello", "doctor", "tomorrow"])
        app.approve("t1", text)
        app.expect("not_delivered", turn_id="t1")
        assert run.spoken == [DISCLOSURE]
        assert run.node == "speak"

        # The receptionist finishes; Bolna answers from the speak node with the old
        # turn. The app already said "not delivered", so it must stay silent.
        harness.fake.receptionist_mid_speech = False
        assert harness.says(run, "Sorry, go ahead.") == ""
        assert run.spoken == [DISCLOSURE]

        resent = app.draft("t1b", ["hello", "doctor", "tomorrow"])
        app.approve("t1b", resent)
        app.expect("spoken", turn_id="t1b")
        harness.idle()
        time.sleep(0.5)  # past the delivery timeout: a delivered turn must stay delivered

        assert run.spoken == [DISCLOSURE, resent]
        assert app.matching("spoken", turn_id="t1") == []
        assert app.matching("not_delivered", turn_id="t1b") == []


def test_each_silence_shows_the_holding_line_as_an_agent_caption(harness: Harness) -> None:
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        assert harness.silence(run) == HOLDING_LINE
        assert harness.silence(run) == HOLDING_LINE
        app.round_trip("t1")

        assert run.spoken == [DISCLOSURE, HOLDING_LINE, HOLDING_LINE]
        assert all(SILENCE_MARKER not in c["text"] for c in app.matching("caption"))
        assert app.matching("caption", speaker="receptionist") == []
        assert _transcript(app) == [("agent", HOLDING_LINE)] * 2
        assert app.matching("status", state="speaking") == [], "no turn was started"


def test_approve_after_end_is_not_spoken(harness: Harness) -> None:
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        text = app.draft("t1", ["hello", "doctor", "tomorrow"])
        app.send({"type": "end"})
        app.expect("status", state="ended")
        app.approve("t1", text)
        time.sleep(0.2)  # give a wrongly accepted approval time to reach Bolna
        harness.idle()

    assert run.spoken == [DISCLOSURE, GOODBYE]
    assert harness.fake.events_for("user_reply") == []


def test_end_while_reply_is_in_flight_is_not_spoken(harness: Harness) -> None:
    harness.fake.latency_s = 0.3  # Bolna asks for the reply only after End was tapped
    call_id = harness.start_call()
    run = harness.run_for(call_id)

    with harness.socket(call_id) as app:
        text = app.draft("t1", ["hello", "doctor", "tomorrow"])
        app.approve("t1", text)
        app.send({"type": "end"})
        app.expect("status", state="ended")
        harness.idle()

    assert _speak_requests(run) == 1, "the late speak request must reach the backend"
    assert run.spoken == [DISCLOSURE, GOODBYE]


def test_unknown_contact_is_refused_and_never_dialled(harness: Harness) -> None:
    response = harness.client.post(
        "/calls", json={"contact_id": "stranger", "purpose": PURPOSE}, headers=AUTH
    )

    assert response.status_code == 403
    assert harness.fake.recipients == []
    assert harness.fake.runs == {}


def test_start_call_without_app_token_is_refused(harness: Harness) -> None:
    response = harness.client.post("/calls", json={"contact_id": CONTACT, "purpose": PURPOSE})

    assert response.status_code == 401
    assert harness.fake.recipients == []
