from __future__ import annotations

import asyncio
import re
import uuid

import pytest
from pydantic import ValidationError

from app.protocol import (
    ApproveMessage,
    CallState,
    CaptionMessage,
    ChipsMessage,
    DraftMessage,
    DraftSource,
    EndMessage,
    NotDeliveredMessage,
    SpokenMessage,
    StatusMessage,
    StopMessage,
)
from tests.fakes import FakeBackend, FakeClock, FakeTransport, drain, running
from tools.app_client import (
    NOT_DELIVERED_NOTICE,
    STALE_DRAFT_NOTICE,
    UNEXPECTED_SPOKEN_NOTICE,
    AppSession,
    NoDraftError,
    SessionClosedError,
)


def _draft(turn_id: str, text: str = "Hello.") -> DraftMessage:
    return DraftMessage(turn_id=turn_id, text=text, source=DraftSource.TEMPLATE)


def _session(transport: FakeTransport, clock: FakeClock | None = None) -> AppSession:
    return AppSession(transport, clock=clock or FakeClock())


async def test_turn_ids_are_fresh_uuid4_hex() -> None:
    session = _session(FakeTransport())
    seen = set()
    for _ in range(3):
        assert re.fullmatch(r"[0-9a-f]{32}", session.turn_id)
        assert uuid.UUID(hex=session.turn_id).version == 4
        seen.add(session.turn_id)
        session.new_turn()
    assert len(seen) == 3


async def test_unsure_chips_are_never_sent() -> None:
    transport = FakeTransport()
    session = _session(transport)
    assert await session.set_chips(["no", "?", "morning"]) is True
    assert transport.sent == [ChipsMessage(turn_id=session.turn_id, chips=["no", "morning"])]
    assert session.chips == ["no", "?", "morning"]
    assert "?" not in transport.raw_sent[0]


async def test_only_unsure_chips_send_nothing_on_a_fresh_turn() -> None:
    transport = FakeTransport()
    session = _session(transport)
    assert await session.set_chips(["?"]) is False
    assert transport.raw_sent == []


async def test_adding_or_removing_an_unsure_chip_does_not_resend() -> None:
    transport = FakeTransport()
    session = _session(transport)
    await session.add_chip("hello")
    assert await session.add_chip("?") is False
    assert await session.remove_chip("?") is False
    assert len(transport.raw_sent) == 1
    assert session.chips == ["hello"]


async def test_removing_a_chip_resends_the_rest_with_the_same_turn_id() -> None:
    transport = FakeTransport()
    session = _session(transport)
    turn_id = session.turn_id
    await session.set_chips(["no", "evening", "morning"])
    assert await session.remove_chip("evening") is True
    assert transport.sent[-1] == ChipsMessage(turn_id=turn_id, chips=["no", "morning"])
    assert session.turn_id == turn_id


async def test_removing_a_repeated_chip_drops_the_latest_one() -> None:
    transport = FakeTransport()
    session = _session(transport)
    await session.set_chips(["no", "?", "no"])
    await session.remove_chip("no")
    assert session.chips == ["no", "?"]
    assert transport.sent[-1] == ChipsMessage(turn_id=session.turn_id, chips=["no"])


async def test_unknown_chip_rejected_and_nothing_sent() -> None:
    transport = FakeTransport()
    session = _session(transport)
    with pytest.raises(ValueError, match="banana"):
        await session.set_chips(["hello", "banana"])
    with pytest.raises(ValueError, match="no chip"):
        await session.remove_chip("hello")
    assert transport.raw_sent == []
    assert session.chips == []


async def test_draft_for_another_turn_is_ignored_and_cannot_be_sent() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport) as log:
        await session.set_chips(["hello"])
        transport.push(_draft("someoneelse", "Stale text."))
        await drain(transport)
        assert session.draft is None
        assert log[-1][1] == [STALE_DRAFT_NOTICE]
        with pytest.raises(NoDraftError):
            await session.send()
    assert [type(m) for m in transport.sent] == [ChipsMessage]


async def test_send_approves_current_draft_then_starts_a_clean_turn() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        await session.set_chips(["hello", "?"])
        first = session.turn_id
        transport.push(_draft(first, "Hello there."))
        await drain(transport)
        approved = await session.send()
        assert approved == first
        assert transport.sent[-1] == ApproveMessage(turn_id=first, text="Hello there.")
        assert session.turn_id != first
        assert session.chips == []
        assert session.draft is None
        # A late draft for the approved turn must not become the new turn's draft.
        transport.push(_draft(first, "Late."))
        await drain(transport)
        assert session.draft is None
        with pytest.raises(NoDraftError):
            await session.send()


async def test_changing_chips_invalidates_the_shown_draft() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        await session.set_chips(["no"])
        transport.push(_draft(session.turn_id, "No."))
        await drain(transport)
        assert session.draft is not None
        await session.add_chip("morning")
        assert session.draft is None
        with pytest.raises(NoDraftError):
            await session.send()


async def test_say_uses_a_fresh_turn_and_leaves_another_fresh_turn() -> None:
    transport = FakeTransport()
    session = _session(transport)
    await session.set_chips(["hello"])
    before = session.turn_id
    approved = await session.say("Sorry, could you please repeat that?")
    assert transport.sent[-1] == ApproveMessage(
        turn_id=approved, text="Sorry, could you please repeat that?"
    )
    assert approved not in (before, session.turn_id)
    assert session.chips == []


async def test_overlong_text_is_rejected_before_sending() -> None:
    transport = FakeTransport()
    session = _session(transport)
    with pytest.raises(ValidationError):
        await session.say("x" * 301)
    assert transport.raw_sent == []


async def test_not_delivered_is_reported_and_never_resent() -> None:
    transport = FakeTransport(FakeBackend(undeliverable={0}).respond)
    session = _session(transport)
    async with running(session, transport) as log:
        turn_id = await session.say("Is there anything tomorrow morning?")
        outcome = await session.wait_for_outcome(turn_id, since=0, timeout=1)
        assert isinstance(outcome, NotDeliveredMessage)
        await drain(transport)
    assert [n for _, n in log if n] == [[NOT_DELIVERED_NOTICE]]
    approvals = [m for m in transport.sent if isinstance(m, ApproveMessage)]
    assert len(approvals) == 1
    assert session.turns[0].outcome == "not_delivered"


async def test_latencies_measured_from_chips_and_from_send() -> None:
    clock = FakeClock(100.0)
    transport = FakeTransport()
    session = _session(transport, clock)
    async with running(session, transport):
        await session.set_chips(["hello"])
        clock.now = 100.4
        transport.push(_draft(session.turn_id))
        await drain(transport)
        clock.now = 101.0
        turn_id = await session.send()
        clock.now = 102.5
        transport.push(SpokenMessage(turn_id=turn_id))
        await drain(transport)
        # A second spoken for the same turn must not overwrite the first latency.
        clock.now = 109.0
        transport.push(SpokenMessage(turn_id=turn_id))
        await drain(transport)
    timing = session.turns[0]
    assert timing.draft_latency_s == pytest.approx(0.4)
    assert timing.spoken_latency_s == pytest.approx(1.5)
    assert timing.outcome == "spoken"
    assert session.spoken_counts[turn_id] == 2


async def test_draft_latency_uses_the_latest_chips_send() -> None:
    clock = FakeClock(10.0)
    transport = FakeTransport()
    session = _session(transport, clock)
    async with running(session, transport):
        await session.set_chips(["no"])
        clock.now = 12.0
        await session.add_chip("morning")
        clock.now = 12.25
        transport.push(_draft(session.turn_id))
        await drain(transport)
    assert session.turns[0].draft_latency_s == pytest.approx(0.25)


async def test_spoken_without_open_send_is_flagged() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport) as log:
        transport.push(SpokenMessage(turn_id="unknown"))
        await drain(transport)
    assert log[0][1] == [UNEXPECTED_SPOKEN_NOTICE]
    assert session.turns == []


async def test_turn_rows_only_for_turns_that_sent_something() -> None:
    session = _session(FakeTransport())
    session.new_turn("idle")
    await session.say("Yes.", label="quick")
    await session.set_chips(["yes"])
    assert [t.label for t in session.turns] == ["quick", "turn 2"]
    assert [t.outcome for t in session.turns] == ["pending", "not_sent"]


async def test_stop_and_end_send_their_messages_and_end_status_is_tracked() -> None:
    transport = FakeTransport(FakeBackend().respond)
    session = _session(transport)
    async with running(session, transport):
        await session.stop()
        await session.end()
        await session.wait_for_status(CallState.ENDED, since=0, timeout=1)
        assert session.ended is True
    assert transport.sent == [StopMessage(), EndMessage()]


async def test_wait_for_only_sees_events_after_the_mark() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        transport.push(CaptionMessage(text="old", at=1.0))
        await drain(transport)
        mark = session.mark()
        with pytest.raises(TimeoutError):
            await session.wait_for_caption(since=mark, timeout=0.01)
        transport.push(CaptionMessage(text="new", at=2.0))
        caption = await session.wait_for_caption(since=mark, timeout=1)
        assert caption.text == "new"


async def test_wait_raises_when_socket_closes_and_sending_fails_after() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        transport.push(StatusMessage(state=CallState.IN_CALL))
        transport.push(None)
        with pytest.raises(SessionClosedError):
            await session.wait_for_caption(since=0, timeout=1)
    with pytest.raises(SessionClosedError):
        await session.end()


async def test_hang_up_sends_end_once_and_waits_for_ended() -> None:
    transport = FakeTransport(FakeBackend().respond)
    session = _session(transport)
    async with running(session, transport):
        assert await session.hang_up(timeout=1) is True
        assert await session.hang_up(timeout=1) is True
    assert transport.sent == [EndMessage()]


async def test_hang_up_reports_false_without_ended_status() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        assert await session.hang_up(timeout=0.01) is False
    assert transport.sent == [EndMessage()]


async def test_hang_up_on_closed_socket_sends_nothing() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        transport.push(None)
        await drain(transport)
        assert await session.hang_up(timeout=1) is False
    assert transport.raw_sent == []


async def test_turn_label_never_exposes_ids() -> None:
    session = _session(FakeTransport())
    approved = await session.say("Yes.", label="T5")
    assert session.turn_label(approved) == "T5"
    assert session.turn_label(session.turn_id) == "current turn"
    assert session.turn_label("other") == "unknown turn"


async def test_hang_up_after_end_waits_without_sending_end_again() -> None:
    transport = FakeTransport()
    session = _session(transport)
    async with running(session, transport):
        await session.end()
        waiting = asyncio.create_task(session.hang_up(timeout=1))
        await drain(transport)
        transport.push(StatusMessage(state=CallState.ENDED))
        assert await waiting is True
    assert transport.sent == [EndMessage()]


async def test_timing_for_returns_the_turn_record_or_raises() -> None:
    session = _session(FakeTransport())
    approved = await session.say("Yes.", label="check 2")
    assert session.timing_for(approved) is session.turns[0]
    with pytest.raises(KeyError):
        session.timing_for(session.turn_id)
