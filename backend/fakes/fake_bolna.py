"""FakeBolna: a `BolnaClient` that also plays Bolna's graph runtime against our backend.

It follows what Bolna documents and what PLAN.md §3 expects (ledger B24, B25):

- `start_call`: the callee answers and hears the static welcome (DISCLOSURE). Like the
  agent-level webhook, the run reports `ringing` then, `ring_s` later (0 by default),
  `in-progress` to our `/bolna/webhook/{secret}` (secret = BOLNA_WEBHOOK_SECRET; defaults
  to the custom-LLM token for stand-alone use). A ring lets a test connect the app
  socket before the call goes live, as the iPhone does.
- listen node: each receptionist utterance, or the `[silence]` repeat, becomes a user
  message and Bolna asks our custom LLM for a reply using the listen prompt.
- `user_reply` event: its properties merge into the call context, the node moves to
  speak and Bolna asks the custom LLM again with the speak prompt, whose `{{var}}`
  slots are now filled. Afterwards the node goes back to listen.
- B24: if the receptionist is mid-utterance when the event lands, the node moves to
  speak but nothing is requested or spoken. The node stays on speak, so the next
  receptionist utterance is answered with the (stale) speak prompt.
- `end_call` event: static goodbye, then the run ends and reports `completed`.
- `send_event` returns before anything is spoken, like Bolna's 202 "published, not
  spoken"; `wait_idle()` waits for the deliveries and re-raises their errors.

The HTTP client is injectable: `asgi_client(app)` for in-process tests, or a plain
`httpx.AsyncClient(base_url=...)` to point the same calls at a running backend.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Literal

import httpx
from fastapi import FastAPI

from app.markers import (
    DISCLOSURE,
    EVENT_END_CALL,
    EVENT_USER_REPLY,
    GOODBYE,
    PROP_REPLY_TEXT,
    PROP_TURN_ID,
    SILENCE_MARKER,
    USER_DATA_CALL_ID,
    render_marker_block,
)
from app.markers import WEBHOOK_PATH as BOLNA_WEBHOOK_PATH
from fakes.sse import collect_stream_text

LLM_PATH = "/v1/chat/completions"
WEBHOOK_PATH = BOLNA_WEBHOOK_PATH + "/{secret}"
ANSWER_STATUSES = ("ringing", "in-progress")
END_STATUS = "completed"
LISTEN_PROMPT = (
    "You relay a phone call for a Deaf caller. Stay quiet while the other person talks.\n"
    + render_marker_block("listen")
)
SPEAK_PROMPT = (
    "You relay a phone call for a Deaf caller. Say the approved reply exactly.\n"
    + render_marker_block("speak")
)

NodeName = Literal["listen", "speak", "goodbye"]
Message = dict[str, str]
_VARIABLE = re.compile(r"\{\{(\w+)\}\}")


class RunEnded(RuntimeError):
    """The fake call is over; the receptionist can no longer talk on it."""


@dataclass(frozen=True)
class SentEvent:
    run_id: str
    event: str
    properties: dict[str, str]


@dataclass
class FakeRun:
    run_id: str
    recipient: str
    user_data: dict[str, str]
    context: dict[str, str]
    node: NodeName = "listen"
    ended: bool = False
    history: list[Message] = field(default_factory=list)
    spoken: list[str] = field(default_factory=list)
    llm_requests: list[dict[str, Any]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    answered: asyncio.Task[None] | None = None


def substitute(template: str, context: Mapping[str, str]) -> str:
    """Fill `{{name}}` like Bolna; unknown names stay as written."""
    return _VARIABLE.sub(lambda match: context.get(match[1], match[0]), template)


def asgi_client(app: FastAPI, base_url: str = "http://ishara.test") -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url)


class FakeBolna:
    def __init__(
        self,
        custom_llm_token: str,
        http: httpx.AsyncClient | None = None,
        *,
        listen_prompt: str = LISTEN_PROMPT,
        speak_prompt: str = SPEAK_PROMPT,
        latency_s: float = 0.0,
        duplicate_events: bool = False,
        receptionist_mid_speech: bool = False,
        report_status: bool = True,
        webhook_secret: str | None = None,
        ring_s: float = 0.0,
    ) -> None:
        self._token = custom_llm_token
        self._webhook_secret = webhook_secret or custom_llm_token
        self._http = http
        self._prompts: dict[NodeName, str] = {"listen": listen_prompt, "speak": speak_prompt}
        self.latency_s = latency_s
        self.duplicate_events = duplicate_events
        self.receptionist_mid_speech = receptionist_mid_speech
        self.report_status = report_status
        self.ring_s = ring_s
        self.statuses: list[tuple[str, str]] = []
        self.runs: dict[str, FakeRun] = {}
        self.recipients: list[str] = []
        self.events: list[SentEvent] = []
        self.spoken: list[str] = []
        self._run_ids = count(1)
        self._tasks: set[asyncio.Task[None]] = set()

    def attach(self, http: httpx.AsyncClient) -> None:
        """Set the client after construction (the app needs the fake first)."""
        self._http = http

    # ---- BolnaClient ----

    async def start_call(self, recipient: str, user_data: dict[str, str]) -> str:
        run_id = f"fake-run-{next(self._run_ids)}"
        run = FakeRun(run_id, recipient, dict(user_data), context=dict(user_data))
        self.runs[run_id] = run
        self.recipients.append(recipient)
        self._say(run, DISCLOSURE)
        if self.report_status:
            # Runs after the caller has stored the run id, like a webhook arriving later.
            run.answered = self._spawn(self._answer(run))
        return run_id

    async def send_event(self, run_id: str, event: str, properties: dict[str, str]) -> None:
        run = self.run(run_id)
        _check_event(event, properties)
        self.events.append(SentEvent(run_id, event, dict(properties)))
        for _ in range(2 if self.duplicate_events else 1):
            self._spawn(self._deliver(run, event, dict(properties)))

    # ---- the receptionist's side ----

    async def receptionist_says(self, run_id: str, text: str) -> str:
        """The receptionist finishes an utterance. Returns what the agent said back."""
        return await self._user_turn(self.run(run_id), text)

    async def silence(self, run_id: str) -> str:
        """The listen node's silence repeat fires. Returns what the agent said."""
        return await self._user_turn(self.run(run_id), SILENCE_MARKER)

    # ---- inspection ----

    def run(self, run_id: str) -> FakeRun:
        return self.runs[run_id]

    def events_for(self, event: str) -> list[SentEvent]:
        return [sent for sent in self.events if sent.event == event]

    async def run_for_call(self, call_id: str, timeout_s: float = 2.0) -> FakeRun:
        """The run whose user_data carries this Ishara call id. Waits for the dial and
        for the answer statuses to reach the backend."""
        async with asyncio.timeout(timeout_s):
            while True:
                for run in self.runs.values():
                    if run.user_data.get(USER_DATA_CALL_ID) == call_id:
                        if run.answered is not None:
                            await run.answered
                        return run
                await asyncio.sleep(0.01)

    async def wait_idle(self) -> None:
        """Wait for every background event delivery; re-raise the first failure."""
        while self._tasks:
            await asyncio.gather(*self._tasks)

    # ---- runtime ----

    def _spawn(self, work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.get_running_loop().create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _deliver(self, run: FakeRun, event: str, properties: dict[str, str]) -> None:
        async with run.lock:
            if run.ended:
                return
            if event == EVENT_END_CALL:
                run.node = "goodbye"
                self._say(run, GOODBYE)
                run.ended = True
                if self.report_status:
                    await self._report(run, END_STATUS)
                return
            run.context.update(properties)
            run.node = "speak"
            if self.receptionist_mid_speech:
                return
            await self._respond(run)

    async def _user_turn(self, run: FakeRun, text: str) -> str:
        async with run.lock:
            if run.ended:
                raise RunEnded(run.run_id)
            run.history.append({"role": "user", "content": text})
            return await self._respond(run)

    async def _respond(self, run: FakeRun) -> str:
        """One custom-LLM request with the current node's prompt, then back to listen."""
        assert run.node in ("listen", "speak"), run.node
        prompt = substitute(self._prompts[run.node], run.context)
        reply = await self._ask_llm(run, prompt)
        run.node = "listen"
        if reply:
            self._say(run, reply)
        return reply

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("FakeBolna has no HTTP client; call attach() first")
        return self._http

    async def _answer(self, run: FakeRun) -> None:
        ringing, answered = ANSWER_STATUSES
        await self._report(run, ringing)
        if self.ring_s:
            await asyncio.sleep(self.ring_s)
        await self._report(run, answered)

    async def _report(self, run: FakeRun, *statuses: str) -> None:
        """POST each execution status to the backend's webhook, in order."""
        path = WEBHOOK_PATH.format(secret=self._webhook_secret)
        for status in statuses:
            response = await self._client().post(path, json={"id": run.run_id, "status": status})
            response.raise_for_status()
            self.statuses.append((run.run_id, status))

    async def _ask_llm(self, run: FakeRun, system_prompt: str) -> str:
        http = self._client()
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        payload = {
            "model": "ishara-custom-llm",
            "stream": True,
            "messages": [{"role": "system", "content": system_prompt}, *run.history],
        }
        run.llm_requests.append(payload)
        headers = {"Authorization": f"Bearer {self._token}"}
        async with http.stream("POST", LLM_PATH, json=payload, headers=headers) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("text/event-stream"):
                raise RuntimeError(f"custom LLM must stream SSE, got {content_type!r}")
            return await collect_stream_text(response.aiter_lines())

    def _say(self, run: FakeRun, text: str) -> None:
        run.history.append({"role": "assistant", "content": text})
        run.spoken.append(text)
        self.spoken.append(text)


def _check_event(event: str, properties: Mapping[str, str]) -> None:
    """Reject events our agent graph has no edge for, so backend bugs fail loudly."""
    if event == EVENT_USER_REPLY:
        missing = {PROP_REPLY_TEXT, PROP_TURN_ID} - properties.keys()
        if missing:
            raise ValueError(f"user_reply is missing {sorted(missing)}")
    elif event != EVENT_END_CALL:
        raise ValueError(f"unknown event {event!r}")
