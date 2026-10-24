"""The Sign Lab's voice: what the scripted Bolna speaks, synthesised by Sarvam and
played on this Mac's speakers.

`VoiceQueue.say` only queues the line and returns, so the backend's event loop never
waits for audio. One worker synthesises and plays the lines in order, one at a time,
like a phone line that can't speak two sentences at once. A Sarvam failure skips that
line (logged) and the call goes on, as a silent Bolna turn would.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Protocol

from app.sarvam import SarvamError

Player = Callable[[bytes], Awaitable[int]]


class Synthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


async def play_with_afplay(wav: bytes) -> int:
    """Play WAV bytes with macOS `afplay` and return its exit code. Cancelling stops
    the audio."""
    with tempfile.NamedTemporaryFile(prefix="ishara-lab-", suffix=".wav") as file:
        file.write(wav)
        file.flush()
        process = await asyncio.create_subprocess_exec("afplay", file.name)
        try:
            return await process.wait()
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise


class VoiceQueue:
    def __init__(
        self,
        tts: Synthesizer,
        play: Player = play_with_afplay,
        *,
        log: Callable[[str], None] = print,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._tts = tts
        self._play = play
        self._log = log
        self._clock = clock
        self._lines: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def say(self, text: str) -> None:
        """Queue a line; never waits."""
        self._lines.put_nowait(text)

    async def drain(self) -> None:
        """Wait until every queued line has been played (or skipped)."""
        await self._lines.join()

    async def __aenter__(self) -> VoiceQueue:
        self._worker = asyncio.create_task(self._run())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            # Ours, from cancel() above; re-raise only if this task is being cancelled.
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise

    async def _run(self) -> None:
        while True:
            text = await self._lines.get()
            try:
                await self._speak(text)
            finally:
                self._lines.task_done()

    async def _speak(self, text: str) -> None:
        started = self._clock()
        try:
            wav = await self._tts.synthesize(text)
        except SarvamError as error:
            self._log(f"voice: Sarvam failed ({error}), nothing played for: {text}")
            return
        self._log(f"voice: playing (Sarvam TTS {self._clock() - started:.2f} s): {text}")
        code = await self._play(wav)
        self._log(f"voice: done (afplay exit {code})")
