"""ScriptedBolna: FakeBolna plus a receptionist who plays the PLAN.md §1 clinic call.

FakeBolna only talks when a test tells it to. For the local demo server nobody does,
so this subclass acts on its own, with pauses that feel like a phone call:

- start_call: `ringing`, then `in-progress` after `Pauses.ring_s`.
- every approved reply the agent speaks: after `Pauses.reply_s` the receptionist says
  the next line of `RECEPTIONIST_LINES` (T2 after T1, T4 after T3), then stays quiet.
- `talk_over_once` (ledger B24): the first SEND of each call lands while the
  receptionist is talking, so Bolna skips it. `Pauses.talk_over_s` later she finishes
  with `TALK_OVER_LINE`, which reaches the stale speak node and must stay silent.
- silence repeat: like the listen node's `repeat_after_silence_seconds`, after
  `Pauses.silence_s` with nobody talking Bolna asks the custom LLM again with
  `[silence]`, so the holding line is said (and shown in the app). The wait starts
  once the call is answered (`in-progress`), anything said restarts it, and 0 turns it
  off. It never fires while ringing or on the speak node.
- everything the agent says and the receptionist says goes to `log` (stdout by default).

`receptionist_mid_speech` is shared by every run, so B24 mode assumes one call at a time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, replace
from typing import Any

import httpx

from app.bolna_agent import SILENCE_REPEAT_S
from app.markers import EVENT_USER_REPLY, HOLDING_LINE
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
    silence_s: float = SILENCE_REPEAT_S

    def scaled(self, factor: float) -> Pauses:
        if factor < 0:
            raise ValueError("the pause factor can't be negative")
        return replace(
            self,
            ring_s=self.ring_s * factor,
            reply_s=self.reply_s * factor,
            talk_over_s=self.talk_over_s * factor,
            silence_s=self.silence_s * factor,
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
        self._answered: set[str] = set()
        # Not in FakeBolna's task set: wait_idle() must not wait for (or re-arm) them.
        self._silence_timers: dict[str, asyncio.Task[None]] = {}

    # ---- FakeBolna hooks ----

    async def _report(self, run: FakeRun, *statuses: str) -> None:
        for status in statuses:
            if status == ANSWERED_STATUS:
                await asyncio.sleep(self.pauses.ring_s)
            await super()._report(run, status)
            self._log(f"bolna status: {status}")
            if status == ANSWERED_STATUS:
                self._answered.add(run.run_id)
                self._reset_silence(run)

    async def _deliver(self, run: FakeRun, event: str, properties: dict[str, str]) -> None:
        talk_over = (
            self.talk_over_once
            and event == EVENT_USER_REPLY
            and run.run_id not in self._talked_over
        )
        if not talk_over:
            await super()._deliver(run, event, properties)
            if run.ended:
                self._reset_silence(run)
            return
        self._talked_over.add(run.run_id)
        self._log("receptionist is talking over that SEND, so Bolna skips it (B24)")
        self.receptionist_mid_speech = True
        try:
            await super()._deliver(run, event, properties)
        finally:
            self.receptionist_mid_speech = False
        self._spawn(self._receptionist_turn(run, TALK_OVER_LINE, self.pauses.talk_over_s))

    async def _respond(self, run: FakeRun, event_notice: str | None = None) -> str:
        approved_reply = run.node == "speak"
        reply = await super()._respond(run, event_notice)
        # The receptionist answers approved replies and, on a delegated call (D9), the
        # agent's own lines from the listen node; never the holding line.
        if reply and (approved_reply or reply != HOLDING_LINE):
            self._answer_later(run)
        return reply

    async def _user_turn(self, run: FakeRun, text: str) -> str:
        reply = await super()._user_turn(run, text)
        self._reset_silence(run)
        return reply

    def _say(self, run: FakeRun, text: str) -> None:
        super()._say(run, text)
        self._log(f"agent says: {text}")
        self._reset_silence(run)

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

    # ---- silence repeat ----

    def _reset_silence(self, run: FakeRun) -> None:
        """Drop the pending silence repeat and, once answered and while the call is up,
        start a new wait. Nobody can be silent at Bolna before the callee picks up."""
        timer = self._silence_timers.pop(run.run_id, None)
        # A firing timer restarts the wait through the holding line; it must not cancel itself.
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        if self.pauses.silence_s and run.run_id in self._answered and not run.ended:
            timer = asyncio.get_running_loop().create_task(self._silence_later(run))
            timer.add_done_callback(self._log_failure)
            self._silence_timers[run.run_id] = timer

    async def _silence_later(self, run: FakeRun) -> None:
        await asyncio.sleep(self.pauses.silence_s)
        if run.ended or run.node != "listen":
            return
        self._log(f"{self.pauses.silence_s:g} s of silence: Bolna repeats the listen node")
        try:
            await self.silence(run.run_id)
        except RunEnded:
            return

    def _log_failure(self, task: asyncio.Task[None]) -> None:
        # wait_idle() re-raises these in tests; the demo server only has the log.
        if not task.cancelled() and (error := task.exception()) is not None:
            self._log(f"fake Bolna failed: {error!r}")
