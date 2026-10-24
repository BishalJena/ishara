"""Sign Lab server over real HTTP and WebSockets on a free loopback port.

Groq and Sarvam are httpx.MockTransports or fakes, afplay is a fake player, and the
real `.env` is never read: every key file here is a tmp_path stand-in.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.markers import DISCLOSURE, GOODBYE, HOLDING_LINE
from app.protocol import CallState, CaptionMessage, DraftSource, SpokenMessage
from fakes.fake_bolna import FakeRun
from fakes.scripted_call import RECEPTIONIST_LINES, Pauses
from scripts import sign_lab
from scripts.lab_composer import build_lab_composer
from scripts.lab_voice import VoiceQueue
from scripts.local_demo import HOST, bind_socket
from scripts.sign_lab import (
    LabKeys,
    LabSetupError,
    SignLab,
    build_sign_lab,
    build_voice,
    read_lab_keys,
    running_lab,
)
from tools.app_client import AppSession
from tools.call_runner import live_call
from tools.connection import auth_headers, open_call_socket

TOKEN = sign_lab.DEV_APP_TOKEN
FAST = Pauses(ring_s=0.05, reply_s=0.05)
WAIT_S = 3.0
T1_TEMPLATE = "Hello, I'd like a doctor's appointment tomorrow."
T2 = RECEPTIONIST_LINES[0]


# ---- keys: read only for the flags that need them, only from the given file ----


def env_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_free_mode_reads_no_keys_even_when_the_file_has_them(tmp_path: Path) -> None:
    keys_file = env_file(tmp_path, "GROQ_API_KEY=g\nSARVAM_API_KEY=s\n")
    assert read_lab_keys(keys_file, "templates", "none") == LabKeys()
    assert read_lab_keys(tmp_path / "missing.env", "templates", "none") == LabKeys()


def test_groq_flag_reads_the_key_and_default_model_from_the_file(tmp_path: Path) -> None:
    keys = read_lab_keys(env_file(tmp_path, "GROQ_API_KEY=g-key\n"), "groq", "none")
    assert keys.groq_key == SecretStr("g-key")
    assert keys.groq_model == "openai/gpt-oss-120b"
    assert keys.sarvam_key is None


def test_groq_model_can_be_overridden_in_the_file(tmp_path: Path) -> None:
    keys = read_lab_keys(env_file(tmp_path, "GROQ_API_KEY=g\nGROQ_MODEL=m/x\n"), "groq", "none")
    assert keys.groq_model == "m/x"


def test_groq_flag_without_a_key_in_the_file_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "exported-is-ignored")
    keys_file = env_file(tmp_path, "GROQ_API_KEY=  \nSARVAM_API_KEY=s\n")
    with pytest.raises(LabSetupError) as raised:
        read_lab_keys(keys_file, "groq", "none")
    assert str(raised.value) == (
        f"--composer groq needs GROQ_API_KEY in {keys_file}. Add it there, or drop --composer groq."
    )


def test_voice_flag_needs_the_sarvam_key(tmp_path: Path) -> None:
    keys_file = env_file(tmp_path, "GROQ_API_KEY=g\n")
    assert read_lab_keys(keys_file, "groq", "none").groq_key is not None
    with pytest.raises(LabSetupError, match=r"--voice sarvam needs SARVAM_API_KEY"):
        read_lab_keys(keys_file, "groq", "sarvam")
    keys = read_lab_keys(env_file(tmp_path, "SARVAM_API_KEY=s\n"), "templates", "sarvam")
    assert (keys.groq_key, keys.sarvam_key) == (None, SecretStr("s"))


def test_paid_flags_with_a_missing_file_name_the_fix(tmp_path: Path) -> None:
    with pytest.raises(LabSetupError) as raised:
        read_lab_keys(tmp_path / "nope.env", "groq", "none")
    message = str(raised.value)
    assert "nope.env not found" in message
    assert "--env-file" in message
    assert "--composer templates --voice none" in message


def test_voice_needs_afplay() -> None:
    assert build_voice("none", None, log=print) is None
    with pytest.raises(LabSetupError, match="afplay"):
        build_voice("sarvam", SecretStr("s"), log=print, which=lambda _: None)
    voice = build_voice("sarvam", SecretStr("s"), log=print, which=lambda _: "/usr/bin/afplay")
    assert isinstance(voice, VoiceQueue)


def test_main_refuses_paid_flags_without_keys_before_serving(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.env"
    code = sign_lab.main(["--composer", "groq", "--env-file", str(missing), "--port", "1"])
    assert code == 2
    assert capsys.readouterr().err.startswith(f"sign_lab: {missing} not found")


def test_parser_defaults_are_free() -> None:
    args = sign_lab.build_parser().parse_args([])
    assert (args.composer, args.voice, args.receptionist) == ("templates", "none", "script")
    assert args.env_file == sign_lab.DEFAULT_ENV_FILE


# ---- the running lab ----


class FakeTTS:
    async def synthesize(self, text: str) -> bytes:
        return text.encode()


class RecordingPlayer:
    def __init__(self) -> None:
        self.played: list[str] = []

    async def __call__(self, wav: bytes) -> int:
        self.played.append(wav.decode())
        return 0


class LineFeed:
    """Stands in for the terminal: the test pushes lines, the lab reads them."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()

    async def __aiter__(self) -> AsyncIterator[str]:
        while True:
            yield await self.queue.get()


@asynccontextmanager
async def app_for(lab: SignLab, lines: LineFeed | None = None) -> AsyncIterator[str]:
    async with running_lab(lab, bind_socket(HOST, 0), lines) as live:
        yield live.base_url


@asynccontextmanager
async def call_on(base_url: str, lab: SignLab) -> AsyncIterator[tuple[AppSession, FakeRun]]:
    async with (
        httpx.AsyncClient(base_url=base_url, headers=auth_headers(TOKEN)) as client,
        live_call(
            client,
            "clinic",
            lambda call_id: open_call_socket(base_url, call_id, TOKEN),
            out=lambda _: None,
        ) as call,
    ):
        await call.session.wait_for_status(CallState.IN_CALL, since=0, timeout=WAIT_S)
        yield call.session, await lab.fake.run_for_call(call.call_id)


async def send_chips(session: AppSession, chips: list[str]) -> tuple[str, str]:
    since = session.mark()
    await session.set_chips(chips)
    draft = await session.wait_for_draft(since=since, timeout=WAIT_S)
    turn_id = await session.send()
    outcome = await session.wait_for_outcome(turn_id, since=since, timeout=WAIT_S)
    assert isinstance(outcome, SpokenMessage)
    return draft.text, draft.source


async def until(condition, timeout: float = WAIT_S) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.005)


async def test_everything_the_agent_says_is_voiced_in_order_and_every_event_is_logged() -> None:
    logs: list[str] = []
    player = RecordingPlayer()
    voice = VoiceQueue(FakeTTS(), player, log=logs.append, clock=lambda: 0.0)
    lab = build_sign_lab(
        composer=build_lab_composer("templates", log=logs.append),
        voice=voice,
        pauses=FAST,
        log=logs.append,
    )
    async with app_for(lab) as base_url:
        async with call_on(base_url, lab) as (session, run):
            text, source = await send_chips(session, ["hello", "doctor", "tomorrow"])
            caption = await session.wait_for_caption(since=0, timeout=WAIT_S)
        await until(lambda: GOODBYE in run.spoken)
        await asyncio.wait_for(voice.drain(), WAIT_S)

    assert (text, source) == (T1_TEMPLATE, DraftSource.TEMPLATE)
    assert caption.text == T2
    assert player.played == [DISCLOSURE, T1_TEMPLATE, GOODBYE]
    order = [
        "chips: hello · doctor · tomorrow (receptionist last said: nothing yet)",
        f"approved (SEND): {T1_TEMPLATE}",
        f"agent says: {T1_TEMPLATE}",
        f"receptionist says: {T2}",
        "end requested",
        f"agent says: {GOODBYE}",
    ]
    assert [line for line in logs if line in order] == order
    assert any(line.startswith("draft (template, ") for line in logs)
    assert [line for line in logs if line.startswith("voice: playing")] == [
        f"voice: playing (Sarvam TTS 0.00 s): {text}" for text in player.played
    ]


async def test_the_lab_drafts_with_the_given_composer() -> None:
    def groq(_: httpx.Request) -> httpx.Response:
        content = "Hi, I'd like to see a doctor tomorrow."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    composer = build_lab_composer(
        "groq",
        log=lambda _: None,
        groq_key=SecretStr("k"),
        groq_model="m",
        transport=httpx.MockTransport(groq),
    )
    lab = build_sign_lab(composer=composer, pauses=FAST, log=lambda _: None)
    async with app_for(lab) as base_url, call_on(base_url, lab) as (session, run):
        text, source = await send_chips(session, ["hello", "doctor", "tomorrow"])
    assert (text, source) == ("Hi, I'd like to see a doctor tomorrow.", DraftSource.LLM)
    assert run.spoken[1] == text


async def test_manual_receptionist_lines_become_captions_and_the_script_stays_quiet() -> None:
    logs: list[str] = []
    lines = LineFeed()
    lab = build_sign_lab(
        composer=build_lab_composer("templates", log=logs.append),
        receptionist="manual",
        pauses=FAST,
        log=logs.append,
    )
    async with app_for(lab, lines) as base_url:
        await lines.queue.put("hello?\n")
        await until(lambda: any(line.startswith("no call is up yet") for line in logs))

        async with call_on(base_url, lab) as (session, run):
            await send_chips(session, ["hello", "doctor", "tomorrow"])
            await asyncio.sleep(FAST.reply_s * 4)
            assert not any(isinstance(m, CaptionMessage) for m in session.history)

            await lines.queue.put("  We only have Friday at 5. Is that okay?  \n")
            caption = await session.wait_for_caption(since=0, timeout=WAIT_S)
            assert caption.text == "We only have Friday at 5. Is that okay?"

            since = session.mark()
            await session.set_chips(["no"])
            draft = await session.wait_for_draft(since=since, timeout=WAIT_S)
            assert draft.text  # drafted with her typed words as the context

            await lines.queue.put("/silence\n")
            await until(lambda: HOLDING_LINE in run.spoken)

    assert "receptionist says: We only have Friday at 5. Is that okay?" in logs
    assert "receptionist stays silent (Bolna's silence repeat)" in logs
    assert any(
        'receptionist last said: "We only have Friday at 5. Is that okay?"' in line for line in logs
    )
    captions = [m.text for m in session.history if isinstance(m, CaptionMessage)]
    assert captions == ["We only have Friday at 5. Is that okay?"]


async def test_manual_receptionist_after_the_call_ended_says_so() -> None:
    logs: list[str] = []
    lines = LineFeed()
    lab = build_sign_lab(
        composer=build_lab_composer("templates", log=lambda _: None),
        receptionist="manual",
        pauses=FAST,
        log=logs.append,
    )
    async with app_for(lab, lines) as base_url:
        async with call_on(base_url, lab) as (_, run):
            pass
        await until(lambda: run.ended)
        await lines.queue.put("Hello?\n")
        await until(lambda: any(line.startswith("no call is up yet") for line in logs))
