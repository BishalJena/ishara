from __future__ import annotations

import pytest

from app.protocol import (
    AppMessage,
    ApproveMessage,
    CaptionMessage,
    EndMessage,
    ServerMessage,
    StopMessage,
)
from tests.fakes import (
    FakeBackend,
    FakeClock,
    FakeTransport,
    ScriptedObserver,
    drain,
    running,
)
from tools.app_client import AppSession
from tools.results import CheckResult
from tools.voice_checks import (
    CALL_ENDED_EARLY,
    CAPTION_PHRASE,
    CHECK_NUMBERS,
    DUPLICATE_SENTENCE,
    EXACT_SENTENCE,
    CheckContext,
    SpikeTiming,
    run_checks,
    run_order,
)

QUICK = SpikeTiming(
    caption_timeout_s=0.05, spoken_timeout_s=0.5, duplicate_settle_s=0, end_timeout_s=0.5
)


async def _no_sleep(_: float) -> None:
    return None


def _by_number(results: list[CheckResult]) -> dict[int, CheckResult]:
    return {result.number: result for result in results}


def test_run_order_puts_end_call_last_and_rejects_unknown_numbers() -> None:
    assert [c.number for c in run_order(CHECK_NUMBERS)] == [1, 2, 3, 4, 5, 6, 8, 9, 7]
    assert [c.number for c in run_order([7, 2])] == [2, 7]
    with pytest.raises(ValueError, match="10"):
        run_order([1, 10])


async def test_all_nine_checks_measure_and_record_verdicts() -> None:
    transport = FakeTransport(FakeBackend().respond)
    session = AppSession(transport, clock=FakeClock())

    def on_enter(prompt: str) -> None:
        if CAPTION_PHRASE in prompt:
            transport.push(CaptionMessage(text="we have four pm tomorrow", at=0.0))

    answers = ["maybe", "y", ""] + ["y", "note"] * 8
    scripted = ScriptedObserver(answers, on_enter)
    ctx = CheckContext(session, scripted.observer(), QUICK, sleep=_no_sleep, clock=FakeClock())
    async with running(session, transport):
        results = await run_checks(ctx, CHECK_NUMBERS)
    by_number = _by_number(results)
    assert [r.number for r in results] == [1, 2, 3, 4, 5, 6, 8, 9, 7]
    assert by_number[1].verdict == "yes" and by_number[1].note == ""
    assert "please answer y, n or s (skip)" in scripted.out
    assert dict(by_number[2].measured)["outcome"] == "spoken"
    assert dict(by_number[2].measured)["SEND → spoken"] == "0.00 s"
    assert dict(by_number[4].measured)["captions"] == "1"
    duplicate = dict(by_number[5].measured)
    assert duplicate["spoken events"] == "1"
    assert duplicate["error codes"] == "already_approved"
    assert dict(by_number[6].measured)["statuses"] == "speaking → in_call → in_call"
    assert dict(by_number[7].measured)["ended status"].endswith("s after end")
    assert session.ended

    sent: list[AppMessage] = transport.sent
    approvals = [m for m in sent if isinstance(m, ApproveMessage)]
    assert [a.text for a in approvals][:3] == [
        EXACT_SENTENCE,
        DUPLICATE_SENTENCE,
        DUPLICATE_SENTENCE,
    ]
    assert approvals[1].turn_id == approvals[2].turn_id
    assert len({a.turn_id for a in approvals}) == len(approvals) - 1
    assert any(isinstance(m, StopMessage) for m in sent)
    assert sent[-1] == EndMessage()
    assert [t.label for t in session.turns] == [
        "check 2",
        "check 5",
        "check 6",
        "check 8",
        "check 9",
    ]


async def test_quiet_check_counts_events_inside_the_window_only() -> None:
    transport = FakeTransport()
    session = AppSession(transport)
    events: list[ServerMessage] = [CaptionMessage(text="hello", at=0.0)]

    async def talk(_: float) -> None:
        for event in events:
            transport.push(event)
        await drain(transport)

    transport.push(CaptionMessage(text="before the window", at=0.0))
    scripted = ScriptedObserver(["n", "it spoke"])
    ctx = CheckContext(session, scripted.observer(), QUICK, sleep=talk)
    async with running(session, transport):
        await drain(transport)
        results = await run_checks(ctx, [1])
    assert results == [
        CheckResult(
            1,
            "Agent stays quiet while the teammate talks",
            "no",
            (("captions", "1"), ("spoken events", "0"), ("speaking status", "0")),
            "it spoke",
        )
    ]


async def test_missing_caption_and_missing_spoken_are_reported() -> None:
    transport = FakeTransport()  # backend that never answers
    session = AppSession(transport)
    scripted = ScriptedObserver(["n", "", "n", ""])
    ctx = CheckContext(session, scripted.observer(), QUICK, sleep=_no_sleep)
    async with running(session, transport):
        results = _by_number(await run_checks(ctx, [2, 4]))
    assert results[2].measured == (("outcome", "no confirmation within 0.5 s"),)
    assert dict(results[4].measured)["first caption"] == "none within 0.05 s"


async def test_not_delivered_send_is_recorded_without_resending() -> None:
    transport = FakeTransport(FakeBackend(undeliverable={0}).respond)
    session = AppSession(transport)
    scripted = ScriptedObserver(["n", "dropped"])
    ctx = CheckContext(session, scripted.observer(), QUICK, sleep=_no_sleep)
    async with running(session, transport):
        results = await run_checks(ctx, [8])
    assert results[0].measured == (
        ("sent after", "3 s of talking"),
        ("outcome", "not delivered"),
        ("reason", "callee speaking"),
    )
    assert [m.type for m in transport.sent] == ["approve"]


async def test_socket_closing_mid_run_skips_the_remaining_checks() -> None:
    def respond(message: AppMessage) -> list[ServerMessage | None]:
        return [None] if isinstance(message, ApproveMessage) else []

    transport = FakeTransport(respond)
    session = AppSession(transport)
    scripted = ScriptedObserver(["y", ""])
    ctx = CheckContext(session, scripted.observer(), QUICK, sleep=_no_sleep)
    async with running(session, transport):
        results = await run_checks(ctx, [1, 2, 5, 7])
    assert [(r.number, r.verdict, r.note) for r in results] == [
        (1, "yes", ""),
        (2, "skipped", CALL_ENDED_EARLY),
        (5, "skipped", CALL_ENDED_EARLY),
        (7, "skipped", CALL_ENDED_EARLY),
    ]
