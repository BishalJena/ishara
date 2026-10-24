"""The Sign Lab voice queue: in order, one line at a time, never blocking the loop.
Sarvam and afplay are fakes here; nothing reaches the network or the speakers."""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import pytest

from app.sarvam import SarvamError
from scripts.lab_voice import VoiceQueue, play_with_afplay

WAIT_S = 2.0


class FakeTTS:
    def __init__(self, fail_on: frozenset[str] = frozenset()) -> None:
        self.fail_on = fail_on
        self.requests: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.requests.append(text)
        await asyncio.sleep(0)
        if text in self.fail_on:
            raise SarvamError("HTTP 500")
        return f"wav:{text}".encode()


class GatedPlayer:
    """Plays a line only when the test opens the gate; records start and end order."""

    def __init__(self) -> None:
        self.started: list[bytes] = []
        self.finished: list[bytes] = []
        self.gate = asyncio.Event()
        self.cancelled = False

    async def __call__(self, wav: bytes) -> int:
        self.started.append(wav)
        try:
            await self.gate.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        self.finished.append(wav)
        return 0


async def until(condition, timeout: float = WAIT_S) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.001)


async def test_lines_play_in_order_one_at_a_time_without_blocking_the_loop() -> None:
    player = GatedPlayer()
    logs: list[str] = []
    async with VoiceQueue(FakeTTS(), player, log=logs.append, clock=lambda: 0.0) as voice:
        voice.say("first")
        voice.say("second")
        await until(lambda: player.started)
        # The loop keeps serving other work while "first" is still playing.
        other_work = asyncio.create_task(asyncio.sleep(0.01, result="served"))
        assert await asyncio.wait_for(other_work, WAIT_S) == "served"
        assert not player.gate.is_set()
        assert player.started == [b"wav:first"]  # "second" waits for "first" to finish
        player.gate.set()
        await asyncio.wait_for(voice.drain(), WAIT_S)
    assert player.finished == [b"wav:first", b"wav:second"]
    assert logs == [
        "voice: playing (Sarvam TTS 0.00 s): first",
        "voice: done (afplay exit 0)",
        "voice: playing (Sarvam TTS 0.00 s): second",
        "voice: done (afplay exit 0)",
    ]


async def test_logs_tts_latency_from_the_clock() -> None:
    ticks = iter([10.0, 10.75])
    logs: list[str] = []

    async def play(_: bytes) -> int:
        return 3

    async with VoiceQueue(FakeTTS(), play, log=logs.append, clock=lambda: next(ticks)) as voice:
        voice.say("Hello")
        await asyncio.wait_for(voice.drain(), WAIT_S)
    assert logs == ["voice: playing (Sarvam TTS 0.75 s): Hello", "voice: done (afplay exit 3)"]


async def test_sarvam_failure_skips_that_line_and_the_next_still_plays() -> None:
    played: list[bytes] = []
    logs: list[str] = []

    async def play(wav: bytes) -> int:
        played.append(wav)
        return 0

    tts = FakeTTS(fail_on=frozenset({"broken"}))
    async with VoiceQueue(tts, play, log=logs.append) as voice:
        voice.say("broken")
        voice.say("fine")
        await asyncio.wait_for(voice.drain(), WAIT_S)
    assert tts.requests == ["broken", "fine"]
    assert played == [b"wav:fine"]
    assert "voice: Sarvam failed (HTTP 500), nothing played for: broken" in logs


async def test_closing_stops_the_line_that_is_playing() -> None:
    player = GatedPlayer()
    async with VoiceQueue(FakeTTS(), player, log=lambda _: None) as voice:
        voice.say("long line")
        await until(lambda: player.started)
    assert player.cancelled
    assert player.finished == []


@pytest.fixture
def fake_afplay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An `afplay` on PATH that copies the file it was given and exits 7."""
    copy = tmp_path / "played.wav"
    script = tmp_path / "bin" / "afplay"
    script.parent.mkdir()
    script.write_text(f'#!/bin/sh\ncp "$1" "{copy}"\nexit 7\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{script.parent}{os.pathsep}{os.environ['PATH']}")
    return copy


async def test_afplay_player_plays_the_wav_and_returns_the_exit_code(fake_afplay: Path) -> None:
    assert await play_with_afplay(b"RIFF....WAVE") == 7
    assert fake_afplay.read_bytes() == b"RIFF....WAVE"
