from __future__ import annotations

import asyncio

import pytest

from app.protocol import (
    AppMessage,
    ApproveMessage,
    CaptionMessage,
    ChipsMessage,
)
from tests.fake_backend import FakeBackend, FakeClock, FakeTransport, drain, running, template_text
from tools.app_client import NOT_DELIVERED_NOTICE, AppSession
from tools.demo_script import DEMO_SCRIPT, Pacing, ScriptAbortedError, run_demo_script

FAST = Pacing(
    first_caption_wait_s=1,
    caption_timeout_s=1,
    sign_gap_s=0,
    draft_timeout_s=1,
    spoken_timeout_s=1,
)
RECEPTIONIST = ["We have 4 pm tomorrow. Does that work?", "Yes, 10:30 tomorrow morning."]


def _chips(message: AppMessage) -> tuple[str, ...]:
    assert isinstance(message, ChipsMessage)
    return tuple(message.chips)


async def test_script_plays_t1_t3_t5_in_order_with_the_3b_correction() -> None:
    transport = FakeTransport(FakeBackend(captions=RECEPTIONIST).respond)
    session = AppSession(transport, clock=FakeClock())
    log: list[str] = []
    async with running(session, transport):
        transport.push(CaptionMessage(text="Hello, City Clinic.", at=0.0))
        turns = await run_demo_script(session, FAST, log.append)
    sent = transport.sent
    kinds = [m.type for m in sent]
    assert kinds == ["chips"] * 3 + ["approve"] + ["chips"] * 4 + ["approve"] + ["chips"] * 2 + [
        "approve"
    ]
    assert [_chips(m) for m in sent if m.type == "chips"] == [
        ("hello",),
        ("hello", "doctor"),
        ("hello", "doctor", "tomorrow"),
        ("no",),
        ("no", "evening"),
        ("no",),
        ("no", "morning"),
        ("yes",),
        ("yes", "thankyou"),
    ]
    approvals = [m for m in sent if isinstance(m, ApproveMessage)]
    assert [a.text for a in approvals] == [
        template_text(["hello", "doctor", "tomorrow"]),
        template_text(["no", "morning"]),
        template_text(["yes", "thankyou"]),
    ]
    # Each turn uses one id for all its chips and its approval; turns never share ids.
    turn_ids: list[str] = []
    for message in sent:
        if not turn_ids or message.turn_id != turn_ids[-1]:
            turn_ids.append(message.turn_id)
    assert len(turn_ids) == len(set(turn_ids)) == 3
    assert [(t.label, t.outcome) for t in turns] == [
        ("T1", "spoken"),
        ("T3", "spoken"),
        ("T5", "spoken"),
    ]
    assert all(t.draft_latency_s is not None for t in turns)
    assert not [line for line in log if "no " in line]


async def test_script_waits_for_the_receptionist_caption_before_each_later_turn() -> None:
    transport = FakeTransport(FakeBackend().respond)
    session = AppSession(transport)
    patient = Pacing(first_caption_wait_s=0, caption_timeout_s=5, sign_gap_s=0, draft_timeout_s=1)
    async with running(session, transport):
        task = asyncio.create_task(run_demo_script(session, patient, lambda _: None))
        for expected_approvals in (1, 2):
            await drain(transport)
            for _ in range(20):
                await asyncio.sleep(0)
            assert [m.type for m in transport.sent].count("approve") == expected_approvals
            assert transport.sent[-1].type == "approve"  # holding until the receptionist speaks
            transport.push(CaptionMessage(text="Receptionist reply.", at=0.0))
        await asyncio.wait_for(task, timeout=1)
    assert [m.type for m in transport.sent].count("approve") == 3


async def test_not_delivered_turn_is_logged_and_never_resent() -> None:
    transport = FakeTransport(FakeBackend(captions=RECEPTIONIST, undeliverable={1}).respond)
    session = AppSession(transport)
    log: list[str] = []
    fast_no_caption = Pacing(
        first_caption_wait_s=0.01,
        caption_timeout_s=0.01,
        sign_gap_s=0,
        draft_timeout_s=1,
        spoken_timeout_s=1,
    )
    async with running(session, transport):
        turns = await run_demo_script(session, fast_no_caption, log.append)
    approvals = [m for m in transport.sent if isinstance(m, ApproveMessage)]
    assert len(approvals) == len(DEMO_SCRIPT)
    assert len({a.turn_id for a in approvals}) == len(DEMO_SCRIPT)
    assert [t.outcome for t in turns] == ["spoken", "not_delivered", "spoken"]
    assert f"T3: {NOT_DELIVERED_NOTICE} (the script never resends)" in log
    assert "no first caption within 0.01 s, continuing" in log


async def test_missing_draft_aborts_before_any_approval() -> None:
    transport = FakeTransport(lambda _: [])
    session = AppSession(transport)
    quick = Pacing(first_caption_wait_s=0, sign_gap_s=0, draft_timeout_s=0.01)
    async with running(session, transport):
        with pytest.raises(ScriptAbortedError, match="T1: no draft"):
            await run_demo_script(session, quick, lambda _: None)
    assert [m.type for m in transport.sent] == ["chips"]
