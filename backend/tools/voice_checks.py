"""The nine V4 checks from PLAN.md §6, run on a live call with a human tester.

Each check tells the tester what to ask the teammate (on a side channel), drives the
backend through the app session, measures what WebSocket events can show, then asks
the tester for a y/n/skip verdict and an optional note. `end_call` (check 7) always
runs last because it ends the call.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field

from app.protocol import (
    CallState,
    CaptionMessage,
    ErrorMessage,
    NotDeliveredMessage,
    ServerMessage,
    SpokenMessage,
    StatusMessage,
)
from tools.app_client import AppSession, SessionClosedError
from tools.results import CheckResult, Verdict

Measured = tuple[tuple[str, str], ...]

EXACT_SENTENCE = "This is the Ishara voice test. Please repeat these exact words back."
DUPLICATE_SENTENCE = "Please count how many times you hear this sentence."
LONG_SENTENCE = (
    "This is a longer Ishara test sentence, spoken slowly on purpose, so that there is "
    "enough time to talk over it or to press stop before it reaches the very end."
)
TALKING_SENTENCE = "Sorry to interrupt, this sentence was sent while you were still talking."
CAPTION_PHRASE = "We have four pm tomorrow. Does that work?"
CALL_ENDED_EARLY = "call ended before this check"

_VERDICTS: dict[str, Verdict] = {
    "y": "yes",
    "yes": "yes",
    "n": "no",
    "no": "no",
    "s": "skipped",
    "skip": "skipped",
}


@dataclass(frozen=True)
class Observer:
    """The human at the terminal. `ask` shows a prompt and returns one typed line."""

    ask: Callable[[str], Awaitable[str]]
    out: Callable[[str], None]

    async def wait_enter(self, instruction: str) -> None:
        await self.ask(f"{instruction} [Enter] ")

    async def verdict(self, question: str) -> Verdict:
        while True:
            answer = (await self.ask(f"{question} [y/n/s] ")).strip().lower()
            if answer in _VERDICTS:
                return _VERDICTS[answer]
            self.out("please answer y, n or s (skip)")

    async def note(self, prompt: str) -> str:
        return (await self.ask(f"{prompt} (optional note) ")).strip()


@dataclass(frozen=True)
class SpikeTiming:
    quiet_window_s: float = 12.0
    silence_wait_s: float = 25.0
    caption_timeout_s: float = 15.0
    spoken_timeout_s: float = 30.0
    duplicate_settle_s: float = 8.0
    stop_after_s: float = 1.5
    talk_lead_s: float = 3.0
    end_timeout_s: float = 15.0


@dataclass
class CheckContext:
    session: AppSession
    observer: Observer
    timing: SpikeTiming = field(default_factory=SpikeTiming)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic


@dataclass(frozen=True)
class Check:
    number: int
    title: str
    question: str
    note_prompt: str
    measure: Callable[[CheckContext], Awaitable[Measured]]


def _count(session: AppSession, since: int, match: Callable[[ServerMessage], bool]) -> int:
    return sum(1 for message in session.history[since:] if match(message))


def _is_caption(message: ServerMessage) -> bool:
    return isinstance(message, CaptionMessage)


def _is_spoken(message: ServerMessage) -> bool:
    return isinstance(message, SpokenMessage)


async def _send_and_measure(ctx: CheckContext, text: str, label: str) -> Measured:
    session = ctx.session
    since = session.mark()
    turn_id = await session.say(text, label)
    timeout = ctx.timing.spoken_timeout_s
    try:
        outcome = await session.wait_for_outcome(turn_id, since=since, timeout=timeout)
    except TimeoutError:
        return (("outcome", f"no confirmation within {timeout:g} s"),)
    if isinstance(outcome, NotDeliveredMessage):
        return (("outcome", "not delivered"), ("reason", outcome.reason))
    latency = session.timing_for(turn_id).spoken_latency_s
    return (("outcome", "spoken"), ("SEND → spoken", f"{latency:.2f} s"))


async def _quiet(ctx: CheckContext) -> Measured:
    window = ctx.timing.quiet_window_s
    await ctx.observer.wait_enter(
        f"Ask the teammate to talk normally for about {window:g} s. Press Enter when they start"
    )
    since = ctx.session.mark()
    await ctx.sleep(window)
    session = ctx.session
    speaking = _count(
        session, since, lambda m: isinstance(m, StatusMessage) and m.state == CallState.SPEAKING
    )
    return (
        ("captions", str(_count(session, since, _is_caption))),
        ("spoken events", str(_count(session, since, _is_spoken))),
        ("speaking status", str(speaking)),
    )


async def _exact(ctx: CheckContext) -> Measured:
    await ctx.observer.wait_enter("Ask the teammate to repeat back exactly what they hear")
    return await _send_and_measure(ctx, EXACT_SENTENCE, "check 2")


async def _holding(ctx: CheckContext) -> Measured:
    wait = ctx.timing.silence_wait_s
    await ctx.observer.wait_enter(
        f"Everyone stays silent for about {wait:g} s. Press Enter to start"
    )
    since = ctx.session.mark()
    await ctx.sleep(wait)
    return (
        ("captions during silence", str(_count(ctx.session, since, _is_caption))),
        ("spoken events", str(_count(ctx.session, since, _is_spoken))),
    )


async def _captions(ctx: CheckContext) -> Measured:
    session = ctx.session
    since = session.mark()
    await ctx.observer.wait_enter(
        f'Ask the teammate to say: "{CAPTION_PHRASE}" Press Enter when they finish'
    )
    if _count(session, since, _is_caption):
        first = "arrived before Enter"
    else:
        entered = ctx.clock()
        timeout = ctx.timing.caption_timeout_s
        try:
            await session.wait_for_caption(since=since, timeout=timeout)
            first = f"{ctx.clock() - entered:.2f} s after Enter"
        except TimeoutError:
            first = f"none within {timeout:g} s"
    return (("first caption", first), ("captions", str(_count(session, since, _is_caption))))


async def _duplicate(ctx: CheckContext) -> Measured:
    session = ctx.session
    await ctx.observer.wait_enter("Ask the teammate to count how often they hear the next sentence")
    since = session.mark()
    turn_id = await session.send_twice(DUPLICATE_SENTENCE, "check 5")
    with suppress(TimeoutError):  # no confirmation shows up below as zero spoken events
        await session.wait_for_outcome(turn_id, since=since, timeout=ctx.timing.spoken_timeout_s)
    await ctx.sleep(ctx.timing.duplicate_settle_s)
    errors = [m.code for m in session.history[since:] if isinstance(m, ErrorMessage)]
    not_delivered = _count(
        session, since, lambda m: isinstance(m, NotDeliveredMessage) and m.turn_id == turn_id
    )
    return (
        ("approvals sent", "2 (same turn id)"),
        ("spoken events", str(session.spoken_counts[turn_id])),
        ("not delivered", str(not_delivered)),
        ("error codes", ", ".join(errors) or "none"),
    )


async def _stop(ctx: CheckContext) -> Measured:
    session = ctx.session
    stop_after = ctx.timing.stop_after_s
    await ctx.observer.wait_enter(
        f"A long sentence goes out and STOP follows after {stop_after:g} s. "
        "Ask the teammate to note what they hear"
    )
    since = session.mark()
    turn_id = await session.say(LONG_SENTENCE, "check 6")
    await ctx.sleep(stop_after)
    await session.stop()
    try:
        outcome = await session.wait_for_outcome(
            turn_id, since=since, timeout=ctx.timing.spoken_timeout_s
        )
        result = "spoken" if isinstance(outcome, SpokenMessage) else "not delivered"
    except TimeoutError:
        result = "no confirmation"
    states = [m.state.value for m in session.history[since:] if isinstance(m, StatusMessage)]
    return (("outcome after STOP", result), ("statuses", " → ".join(states) or "none"))


async def _send_while_talking(ctx: CheckContext) -> Measured:
    lead = ctx.timing.talk_lead_s
    await ctx.observer.wait_enter(
        "Ask the teammate to keep talking for about 15 s. Press Enter when they start"
    )
    await ctx.sleep(lead)
    measured = await _send_and_measure(ctx, TALKING_SENTENCE, "check 8")
    return (("sent after", f"{lead:g} s of talking"), *measured)


async def _talk_over(ctx: CheckContext) -> Measured:
    await ctx.observer.wait_enter(
        'Ask the teammate to talk over the next sentence and say "wait" half-way. '
        "Press Enter to send"
    )
    return await _send_and_measure(ctx, LONG_SENTENCE, "check 9")


async def _end_call(ctx: CheckContext) -> Measured:
    await ctx.observer.wait_enter("Ask the teammate to say when their call drops. Press Enter")
    started = ctx.clock()
    timeout = ctx.timing.end_timeout_s
    if await ctx.session.hang_up(timeout):
        return (("ended status", f"{ctx.clock() - started:.2f} s after end"),)
    return (("ended status", f"not within {timeout:g} s"),)


CHECKS: tuple[Check, ...] = (
    Check(
        1,
        "Agent stays quiet while the teammate talks",
        "Did the agent stay silent the whole time?",
        "Anything it said?",
        _quiet,
    ),
    Check(
        2,
        "user_reply speaks the exact text",
        f'Did the teammate hear exactly: "{EXACT_SENTENCE}"?',
        "If not, what did they hear?",
        _exact,
    ),
    Check(
        3,
        "Holding line after silence",
        'Did "One moment please, I\'m signing my reply." play during the silence?',
        "After roughly how many seconds?",
        _holding,
    ),
    Check(
        4,
        "Captions arrive at the backend",
        "Did the caption text match what the teammate said?",
        "Differences?",
        _captions,
    ),
    Check(
        5,
        "Same turn_id twice speaks once",
        "Did the teammate hear the sentence only once?",
        "How many times?",
        _duplicate,
    ),
    Check(
        6,
        "STOP cancels unspoken or in-progress speech",
        "Was the sentence cut off or never spoken after STOP?",
        "What exactly did the teammate hear?",
        _stop,
    ),
    Check(
        7,
        "end_call event ends the call",
        "Did the teammate hear the goodbye and then the call ended?",
        "Anything odd?",
        _end_call,
    ),
    Check(
        8,
        "SEND while the teammate is talking (B24)",
        "Was the sentence spoken while the teammate was still talking?",
        "Spoken over them, after they stopped, or never?",
        _send_while_talking,
    ),
    Check(
        9,
        'Talk-over with "wait" (B25)',
        'Did the sentence play to the end despite "wait"?',
        "Where did it pause or stop, if at all?",
        _talk_over,
    ),
)
CHECK_NUMBERS = tuple(check.number for check in CHECKS)
END_CALL_CHECK = 7


def run_order(numbers: Sequence[int]) -> list[Check]:
    """Selected checks in PLAN order, with end_call moved to the end."""
    unknown = sorted(set(numbers) - set(CHECK_NUMBERS))
    if unknown:
        raise ValueError(f"unknown check numbers: {unknown}")
    chosen = [check for check in CHECKS if check.number in set(numbers)]
    return sorted(chosen, key=lambda check: check.number == END_CALL_CHECK)


async def run_checks(ctx: CheckContext, numbers: Sequence[int]) -> list[CheckResult]:
    results: list[CheckResult] = []
    order = run_order(numbers)
    for index, check in enumerate(order):
        ctx.observer.out(f"\n== Check {check.number}: {check.title} ==")
        try:
            measured = await check.measure(ctx)
        except SessionClosedError:
            ctx.observer.out("the call socket closed; remaining checks are recorded as skipped")
            results += [
                CheckResult(rest.number, rest.title, "skipped", (), CALL_ENDED_EARLY)
                for rest in order[index:]
            ]
            break
        for name, value in measured:
            ctx.observer.out(f"   {name}: {value}")
        verdict = await ctx.observer.verdict(check.question)
        note = await ctx.observer.note(check.note_prompt)
        results.append(CheckResult(check.number, check.title, verdict, measured, note))
    return results
