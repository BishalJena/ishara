"""The local demo server over real HTTP and WebSockets on a free loopback port.

The app side is the voice-spike tooling (tools/): `live_call`, `AppSession` and the
PLAN §1 `run_demo_script`, exactly as `scripts.fake_app` drives a deployed backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.delegate import CALLBACK_LINE, PAUSE_LINE
from app.markers import DISCLOSURE, GOODBYE, HOLDING_LINE
from app.protocol import (
    CallState,
    CaptionMessage,
    NotDeliveredMessage,
    ServerMessage,
    SpokenMessage,
)
from fakes.fake_bolna import FakeRun
from fakes.scripted_call import RECEPTIONIST_LINES, RECEPTIONIST_SCRIPTS, TALK_OVER_LINE, Pauses
from scripts import local_demo
from scripts.local_demo import HOST, LocalDemo, bind_socket, build_local_demo, running
from tools.app_client import AppSession
from tools.call_runner import LiveCall, live_call
from tools.connection import WebSocketTransport, auth_headers, open_call_socket
from tools.demo_script import Pacing, run_demo_script

T2, T4 = RECEPTIONIST_LINES
T1_TEXT = "Hello, I'd like a doctor's appointment tomorrow."
T3_TEXT = "No, sorry, that doesn't work. Is there anything in the morning?"
T5_TEXT = "Yes, that works. Thank you."
TOKEN = local_demo.DEV_APP_TOKEN
# The ring gives the app socket time to connect before the call goes live (disclosure).
FAST = Pauses(ring_s=0.3, reply_s=0.05)
PACING = Pacing(
    first_caption_wait_s=0.01,
    caption_timeout_s=3,
    sign_gap_s=0,
    draft_timeout_s=3,
    spoken_timeout_s=3,
)
WAIT_S = 3.0
BACKEND = Path(__file__).resolve().parents[1]
SECRET_NAMES = (
    "APP_TOKEN",
    "BOLNA_API_KEY",
    "BOLNA_AGENT_ID",
    "CUSTOM_LLM_TOKEN",
    "BOLNA_WEBHOOK_SECRET",
    "GROQ_API_KEY",
    "SARVAM_API_KEY",
    "PUBLIC_BASE_URL",
)


@asynccontextmanager
async def demo_call(demo: LocalDemo) -> AsyncIterator[tuple[LiveCall, FakeRun]]:
    """Serve the demo, start a call to `clinic` like the app, wait until it is answered."""
    async with (
        running(demo, bind_socket(HOST, 0)) as live,
        httpx.AsyncClient(base_url=live.base_url, headers=auth_headers(TOKEN)) as client,
    ):
        async with live_call(
            client, "clinic", lambda call_id: open_call_socket(live.base_url, call_id, TOKEN)
        ) as call:
            await call.session.wait_for_status(CallState.IN_CALL, since=0, timeout=WAIT_S)
            yield call, await demo.fake.run_for_call(call.call_id)
        await demo.fake.wait_idle()


def _events(session: AppSession) -> list[str]:
    """Spoken, not-delivered and caption events in arrival order, by text."""

    def label(message: ServerMessage) -> str | None:
        match message:
            case SpokenMessage(turn_id=turn_id):
                return f"spoken {session.turn_label(turn_id)}"
            case NotDeliveredMessage(turn_id=turn_id):
                return f"not_delivered {session.turn_label(turn_id)}"
            case CaptionMessage(text=text, speaker=speaker):
                return f"{speaker}: {text}"
        return None

    return [text for message in session.history if (text := label(message))]


async def _end_and_wait_for_goodbye(session: AppSession) -> None:
    """End like the app and keep reading: the goodbye caption follows `status ended`."""
    since = session.mark()
    await session.end()
    await session.wait_for(
        lambda m: isinstance(m, CaptionMessage) and m.text == GOODBYE, since=since, timeout=WAIT_S
    )


async def _send_chips(session: AppSession, label: str, chips: list[str]) -> str:
    session.new_turn(label)
    since = session.mark()
    await session.set_chips(chips)
    await session.wait_for_draft(since=since, timeout=WAIT_S)
    return await session.send()


async def test_plan_script_runs_end_to_end_over_http() -> None:
    logged: list[str] = []
    demo = build_local_demo(pauses=FAST, log=logged.append)

    async with demo_call(demo) as (call, run):
        timings = await run_demo_script(call.session, PACING, log=logged.append)
        session = call.session
        await _end_and_wait_for_goodbye(session)

    assert [timing.outcome for timing in timings] == ["spoken", "spoken", "spoken"]
    assert run.spoken == [DISCLOSURE, T1_TEXT, T3_TEXT, T5_TEXT, GOODBYE]
    assert _events(session) == [
        f"agent: {DISCLOSURE}",
        "spoken T1",
        f"receptionist: {T2}",
        "spoken T3",
        f"receptionist: {T4}",
        "spoken T5",
        f"agent: {GOODBYE}",
    ]
    assert session.ended
    assert demo.fake.statuses[-1] == (run.run_id, "completed")
    assert demo.fake.recipients == [local_demo.synthetic_number(0)]
    assert logged.index(f"agent says: {T1_TEXT}") < logged.index(f"receptionist says: {T2}")
    assert logged.index(f"receptionist says: {T4}") < logged.index(f"agent says: {T5_TEXT}")


async def test_b24_talk_over_is_not_delivered_then_a_resend_is_spoken_once() -> None:
    logged: list[str] = []
    demo = build_local_demo(
        pauses=FAST, talk_over_once=True, delivery_timeout_s=0.3, log=logged.append
    )

    async with demo_call(demo) as (call, run):
        session = call.session
        first = await _send_chips(session, "T1", ["hello", "doctor", "tomorrow"])
        outcome = await session.wait_for_outcome(first, since=0, timeout=WAIT_S)
        assert isinstance(outcome, NotDeliveredMessage)

        # She finishes talking; the stale speak request for T1 must stay silent.
        caption = await session.wait_for_caption(since=0, timeout=WAIT_S)
        assert caption.text == TALK_OVER_LINE
        assert run.spoken == [DISCLOSURE]

        since = session.mark()
        resent = await _send_chips(session, "T1 again", ["hello", "doctor", "tomorrow"])
        outcome = await session.wait_for_outcome(resent, since=since, timeout=WAIT_S)
        assert isinstance(outcome, SpokenMessage)
        await session.wait_for(
            lambda m: isinstance(m, CaptionMessage) and m.text == T2, since=since, timeout=WAIT_S
        )
        await demo.fake.wait_idle()
        await _end_and_wait_for_goodbye(session)

    assert run.spoken == [DISCLOSURE, T1_TEXT, GOODBYE]
    assert _events(session) == [
        f"agent: {DISCLOSURE}",
        "not_delivered T1",
        f"receptionist: {TALK_OVER_LINE}",
        "spoken T1 again",
        f"receptionist: {T2}",
        f"agent: {GOODBYE}",
    ]
    assert session.spoken_counts[first] == 0
    assert session.spoken_counts[resent] == 1


async def test_a_long_pause_shows_the_holding_line_in_the_app() -> None:
    demo = build_local_demo(pauses=replace(FAST, silence_s=0.2), log=lambda _: None)

    async with demo_call(demo) as (call, run):
        session = call.session
        await session.wait_for(
            lambda m: isinstance(m, CaptionMessage) and m.text == HOLDING_LINE,
            since=0,
            timeout=WAIT_S,
        )
        await _end_and_wait_for_goodbye(session)

    assert run.spoken[:2] == [DISCLOSURE, HOLDING_LINE]
    events = _events(session)
    assert events[:2] == [f"agent: {DISCLOSURE}", f"agent: {HOLDING_LINE}"]
    assert events[-1] == f"agent: {GOODBYE}"
    assert set(events) == {f"agent: {line}" for line in (DISCLOSURE, HOLDING_LINE, GOODBYE)}


# ---- Call for me (D9) with the delegated receptionist scripts ----

QUESTION, OFFER, BYE = RECEPTIONIST_SCRIPTS["open-question"]
OPENING = "I'd like to book a doctor's appointment for Riya, tomorrow."
TOMORROW_LINE = "Tomorrow, please. What times are available?"
YES_LINE = "Yes, 4 pm tomorrow works. Thank you."
Message = dict[str, Any]


class DelegatedApp:
    """The app's side of a delegated call: every message it got, in order."""

    def __init__(self, socket: WebSocketTransport) -> None:
        self.socket = socket
        self.history: list[Message] = []

    async def expect(self, match: Callable[[Message], bool], timeout: float = WAIT_S) -> Message:
        async with asyncio.timeout(timeout):
            while True:
                raw = await self.socket.receive_text()
                assert raw is not None, "the backend closed the socket"
                message = json.loads(raw)
                self.history.append(message)
                if match(message):
                    return message

    async def quiet_for(self, seconds: float) -> list[Message]:
        """Everything that arrives within `seconds`."""
        start = len(self.history)
        with contextlib.suppress(TimeoutError):
            await self.expect(lambda _: False, timeout=seconds)
        return self.history[start:]

    async def answer(self, ask: Message, choice: str) -> Message:
        await self.socket.send_text(
            json.dumps({"type": "answer", "ask_id": ask["ask_id"], "choice": choice})
        )
        return await self.expect(lambda m: m["type"] == "ask_resolved")

    def captions(self, speaker: str) -> list[str]:
        return [
            m["text"] for m in self.history if m["type"] == "caption" and m["speaker"] == speaker
        ]


def _is_ask(message: Message) -> bool:
    return message["type"] == "ask"


async def _delegated_call(
    demo: LocalDemo, attended: bool, script: Callable[[DelegatedApp], Any]
) -> Message:
    """Brief for [tomorrow], place the delegated call, run `script` as the app, then
    return the notes once ready."""
    async with (
        running(demo, bind_socket(HOST, 0)) as live,
        httpx.AsyncClient(base_url=live.base_url, headers=auth_headers(TOKEN)) as client,
    ):
        brief = await client.post(
            "/briefs",
            json={
                "purpose": "doctor_appointment",
                "chips": ["tomorrow"],
                "profile": {"name": "Riya"},
            },
        )
        call = await client.post(
            "/calls",
            json={
                "contact_id": "clinic",
                "purpose": "doctor_appointment",
                "mode": "delegated",
                "brief_id": brief.json()["brief_id"],
                "attended": attended,
            },
        )
        call_id = call.json()["call_id"]
        async with open_call_socket(live.base_url, call_id, TOKEN) as socket:
            await script(DelegatedApp(socket))
        await demo.fake.wait_idle()
        for _ in range(50):
            notes = (await client.get(f"/calls/{call_id}/notes")).json()
            if notes["ready"]:
                return notes
            await asyncio.sleep(0.05)
    pytest.fail("the notes never became ready")


async def test_open_question_waits_for_the_users_time_word_then_offers_and_books() -> None:
    """Regression: the receptionist used to answer the agent's "One moment, please." with
    her next line, so the offer came (and was dropped) before the user had answered."""
    logged: list[str] = []
    demo = build_local_demo(pauses=FAST, receptionist="open-question", log=logged.append)

    async def app(call: DelegatedApp) -> None:
        ask = await call.expect(_is_ask)
        assert ask["question"] == QUESTION
        assert [o["choice"] for o in ask["options"]] == ["tomorrow", "morning", "now", "wait"]
        # She waits on "One moment, please." however long the user takes.
        assert not [m for m in await call.quiet_for(10 * FAST.reply_s) if m["type"] == "caption"]

        assert (await call.answer(ask, "tomorrow"))["spoken"] == TOMORROW_LINE
        offer = await call.expect(_is_ask)
        assert offer["question"] == OFFER
        assert (await call.answer(offer, "yes"))["spoken"] == YES_LINE
        await call.expect(lambda m: m["type"] == "caption" and m["text"] == BYE)
        await call.socket.send_text(json.dumps({"type": "end"}))
        await call.expect(lambda m: m["type"] == "status" and m["state"] == "ended")
        assert call.captions("receptionist") == [QUESTION, OFFER, BYE]

    notes = await _delegated_call(demo, attended=True, script=app)

    assert notes["outcome"] == "booked"
    spoken = [line.removeprefix("agent says: ") for line in logged if "agent says: " in line]
    assert spoken == [DISCLOSURE, OPENING, PAUSE_LINE, TOMORROW_LINE, PAUSE_LINE, YES_LINE, GOODBYE]


async def test_unattended_offer_ends_in_a_callback() -> None:
    logged: list[str] = []
    demo = build_local_demo(pauses=FAST, receptionist="offer", log=logged.append)
    offer, bye = RECEPTIONIST_SCRIPTS["offer"]

    async def app(call: DelegatedApp) -> None:
        await call.expect(lambda m: m["type"] == "caption" and m["text"] == bye)
        await call.socket.send_text(json.dumps({"type": "end"}))
        await call.expect(lambda m: m["type"] == "status" and m["state"] == "ended")
        assert not [m for m in call.history if _is_ask(m)], "an unattended call never asks"
        assert call.captions("receptionist") == [offer, bye]

    notes = await _delegated_call(demo, attended=False, script=app)

    assert notes["outcome"] == "callback"
    spoken = [line.removeprefix("agent says: ") for line in logged if "agent says: " in line]
    assert spoken == [DISCLOSURE, OPENING, CALLBACK_LINE, GOODBYE]


def test_local_settings_ignore_dotenv_and_exported_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("".join(f"{name}=from-dotenv\n" for name in SECRET_NAMES))
    monkeypatch.setitem(local_demo.Settings.model_config, "env_file", dotenv)
    assert local_demo.Settings().groq_api_key is not None, "the .env stand-in must be read"
    for name in SECRET_NAMES:
        monkeypatch.setenv(name, "from-environment")

    settings = local_demo.local_settings("dev-token", ["clinic", "mehta-office"])

    assert settings.groq_api_key is None
    assert settings.bolna_api_key is None
    assert settings.bolna_agent_id is None
    assert settings.sarvam_api_key is None
    assert settings.public_base_url is None
    assert settings.app_token is not None
    assert settings.app_token.get_secret_value() == "dev-token"
    internal = (settings.custom_llm_token, settings.bolna_webhook_secret)
    assert all(s is not None and "from-" not in s.get_secret_value() for s in internal)
    assert settings.allowed_recipients == {"clinic=+910000000000", "mehta-office=+910000000001"}


def test_internal_tokens_differ_per_server() -> None:
    first, second = (local_demo.local_settings("t", ["clinic"]) for _ in range(2))
    assert first.custom_llm_token != second.custom_llm_token
    assert first.bolna_webhook_secret != second.bolna_webhook_secret


def test_talk_over_outlasts_the_delivery_timeout() -> None:
    demo = build_local_demo(pauses=Pauses(reply_s=2), delivery_timeout_s=7)
    assert demo.fake.pauses.talk_over_s == 9


def test_banner_prints_what_the_app_and_bridge_need() -> None:
    text = local_demo.banner("http://127.0.0.1:8123", "tok", ["clinic"], talk_over=False)

    assert "  base URL   http://127.0.0.1:8123" in text
    assert "  ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8123" in text
    assert "  ISHARA_APP_TOKEN = tok" in text
    assert "APP_TOKEN=tok artifacts/bridge/.venv/bin/python mac_bridge.py " in text
    assert "--base-url http://127.0.0.1:8123 --contact clinic --confirm-cost" in text
    assert "--contact clinic" in text
    assert "B24" not in text
    assert "B24" in local_demo.banner("http://h:1", "tok", ["clinic"], talk_over=True)


def test_parser_defaults_and_rejections() -> None:
    parser = local_demo.build_parser()
    args = parser.parse_args([])
    assert (args.port, args.app_token, args.contact, args.b24, args.delay) == (
        8000,
        TOKEN,
        None,
        False,
        1.0,
    )
    assert args.receptionist == "clinic"
    args = parser.parse_args(["--contact", "clinic", "--contact", "mehta-office", "--b24"])
    assert args.contact == ["clinic", "mehta-office"]
    assert args.b24
    assert parser.parse_args(["--receptionist", "open-question"]).receptionist == "open-question"
    for bad in (["--delay", "-1"], ["--app-token", " "], ["--receptionist", "nobody"]):
        with pytest.raises(SystemExit):
            parser.parse_args(bad)


def test_busy_port_exits_with_a_hint(capsys: pytest.CaptureFixture[str]) -> None:
    taken = bind_socket(HOST, 0)
    taken.listen()
    port = taken.getsockname()[1]
    try:
        assert local_demo.main(["--port", str(port)]) == 1
    finally:
        taken.close()
    assert f"can't listen on {HOST}:{port}" in capsys.readouterr().out


def test_command_serves_health_and_stops_on_ctrl_c() -> None:
    probe = bind_socket(HOST, 0)
    port = probe.getsockname()[1]
    probe.close()
    env = {k: v for k, v in os.environ.items() if k not in SECRET_NAMES}
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.local_demo", "--port", str(port)],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert process.stdout is not None
        first = process.stdout.readline()
        assert first.startswith("Ishara local demo backend")
        health = _wait_for_health(f"http://{HOST}:{port}/health")
        assert "GROQ_API_KEY" in health["missing_config"]
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=WAIT_S) == 0
    finally:
        if process.poll() is None:
            process.kill()


def _wait_for_health(url: str, timeout_s: float = 20.0) -> dict[str, list[str]]:
    # A refused connection fails instantly, so poll against a deadline rather than a
    # fixed number of tries; cold CI runners take seconds to import the app.
    deadline = time.monotonic() + timeout_s
    with httpx.Client(timeout=0.5) as client:
        while time.monotonic() < deadline:
            try:
                return client.get(url).json()
            except httpx.TransportError:
                time.sleep(0.1)
    pytest.fail("the local demo server never answered /health")
