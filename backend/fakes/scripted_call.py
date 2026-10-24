"""ScriptedBolna: FakeBolna plus a receptionist who plays the PLAN.md §1 clinic call.

FakeBolna only talks when a test tells it to. For the local demo server nobody does,
so this subclass acts on its own, with pauses that feel like a phone call:

- start_call: `ringing`, then `in-progress` after `Pauses.ring_s`.
- every approved reply the agent speaks: after `Pauses.reply_s` the receptionist says
  the next line of `RECEPTIONIST_LINES` (T2 after T1, T4 after T3), then stays quiet.
- `talk_over_once` (ledger B24): the first SEND of each call lands while the
  receptionist is talking, so Bolna skips it. `Pauses.talk_over_s` later she finishes
  with `TALK_OVER_LINE`, which reaches the stale speak node and must stay silent.
- everything the agent says and the receptionist says goes to `log` (stdout by default).

`receptionist_mid_speech` is shared by every run, so B24 mode assumes one call at a time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, replace
from typing import Any

import httpx

from app.markers import EVENT_USER_REPLY
from fakes.fake_bolna import FakeBolna, FakeRun, RunEnded

RECEPTIONIST_LINES = (
    "We have 4 pm tomorrow. Does that work?",
    "Yes, 10:30 tomorrow morning.",
)
TALK_OVER_LINE = "Sorry, go ahead."
ANSWERED_STATUS = "in-progress"


@dataclass(frozen=True)
class Pauses:
    ring_s: float = 2.0
    reply_s: float = 2.5
    # Must outlast the backend's delivery timeout (CallManager, 10 s by default), so
    # the app has shown "not delivered" before the receptionist finishes talking.
    talk_over_s: float = 12.0

    def scaled(self, factor: float) -> Pauses:
        if factor < 0:
            raise ValueError("the pause factor can't be negative")
        return replace(
            self,
            ring_s=self.ring_s * factor,
            reply_s=self.reply_s * factor,
            talk_over_s=self.talk_over_s * factor,
        )


CALL_PAUSES = Pauses()


class ScriptedBolna(FakeBolna):
    def __init__(
        self,
        custom_llm_token: str,
        http: httpx.AsyncClient | None = None,
        *,
        webhook_secret: str | None = None,
        lines: Sequence[str] = RECEPTIONIST_LINES,
        pauses: Pauses = CALL_PAUSES,
        talk_over_once: bool = False,
        log: Callable[[str], None] = print,
    ) -> None:
        super().__init__(custom_llm_token, http, webhook_secret=webhook_secret)
        self.lines = tuple(lines)
        self.pauses = pauses
        self.talk_over_once = talk_over_once
        self._log = log
        self._lines_said: dict[str, int] = {}
        self._talked_over: set[str] = set()

    # ---- FakeBolna hooks ----

    async def _report(self, run: FakeRun, *statuses: str) -> None:
        for status in statuses:
            if status == ANSWERED_STATUS:
                await asyncio.sleep(self.pauses.ring_s)
            await super()._report(run, status)
            self._log(f"bolna status: {status}")

    async def _deliver(self, run: FakeRun, event: str, properties: dict[str, str]) -> None:
        talk_over = (
            self.talk_over_once
            and event == EVENT_USER_REPLY
            and run.run_id not in self._talked_over
        )
        if not talk_over:
            await super()._deliver(run, event, properties)
            return
        self._talked_over.add(run.run_id)
        self._log("receptionist is talking over that SEND, so Bolna skips it (B24)")
        self.receptionist_mid_speech = True
        try:
            await super()._deliver(run, event, properties)
        finally:
            self.receptionist_mid_speech = False
        self._spawn(self._receptionist_turn(run, TALK_OVER_LINE, self.pauses.talk_over_s))

    async def _respond(self, run: FakeRun) -> str:
        approved_reply = run.node == "speak"
        reply = await super()._respond(run)
        if approved_reply and reply:
            self._answer_later(run)
        return reply

    def _say(self, run: FakeRun, text: str) -> None:
        super()._say(run, text)
        self._log(f"agent says: {text}")

    def _spawn(self, work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = super()._spawn(work)
        task.add_done_callback(self._log_failure)
        return task

    # ---- the receptionist ----

    def _answer_later(self, run: FakeRun) -> None:
        said = self._lines_said.get(run.run_id, 0)
        if said == len(self.lines):
            return
        self._lines_said[run.run_id] = said + 1
        self._spawn(self._receptionist_turn(run, self.lines[said], self.pauses.reply_s))

    async def _receptionist_turn(self, run: FakeRun, text: str, pause_s: float) -> None:
        await asyncio.sleep(pause_s)
        self._log(f"receptionist says: {text}")
        try:
            await self.receptionist_says(run.run_id, text)
        except RunEnded:
            self._log("the call ended before the receptionist finished")

    def _log_failure(self, task: asyncio.Task[None]) -> None:
        # wait_idle() re-raises these in tests; the demo server only has the log.
        if not task.cancelled() and (error := task.exception()) is not None:
            self._log(f"fake Bolna failed: {error!r}")
