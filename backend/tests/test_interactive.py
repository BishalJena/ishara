from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

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
    ErrorMessage,
    NotDeliveredMessage,
    ServerMessage,
    SpokenMessage,
    StatusMessage,
    StopMessage,
)
from tests.fake_backend import FakeBackend, FakeTransport, drain, running, template_text
from tools.app_client import NOT_DELIVERED_NOTICE, AppSession, NoDraftError
from tools.console import format_event
from tools.interactive import Chips, Remove, Say, Simple, parse_command, run_commands

RECOVERABLE = (ValueError, NoDraftError, ValidationError)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("chips no morning", Chips(("no", "morning"))),
        ("chips no ? morning", Chips(("no", "?", "morning"))),
        ("rm morning", Remove("morning")),
        ('say "Yes, that works."', Say("Yes, that works.")),
        ("say hold on please", Say("hold on please")),
        ("SEND", Simple("send")),
        ("new", Simple("new")),
        ("stop", Simple("stop")),
        ("end", Simple("end")),
        ("help", Simple("help")),
    ],
)
def test_parse_command(line: str, expected: object) -> None:
    assert parse_command(line) == expected


@pytest.mark.parametrize("line", ["chips", "rm", "rm a b", "say", "send now", "dance", '"'])
def test_bad_commands_raise_value_error(line: str) -> None:
    with pytest.raises(ValueError):
        parse_command(line)


def _lines(*lines: str | None) -> Iterator[str | None]:
    return iter(lines)


async def _run(transport: FakeTransport, *lines: str | None) -> tuple[AppSession, list[str]]:
    session = AppSession(transport)
    feed = _lines(*lines)
    out: list[str] = []

    async def read_line() -> str | None:
        await drain(transport)
        return next(feed, None)

    async with running(session, transport):
        await run_commands(session, read_line, out.append, RECOVERABLE)
    return session, out


async def test_interactive_turn_flow_against_fake_backend() -> None:
    transport = FakeTransport(FakeBackend().respond)
    session, out = await _run(
        transport,
        "chips no ? evening",
        "rm evening",
        "chips no morning",
        "send",
        "send",
        'say "Sorry, could you please repeat that?"',
        "stop",
        "end",
        "chips yes",  # never reached: end quits the loop
    )
    sent = transport.sent
    assert [m.type for m in sent] == [
        "chips",
        "chips",
        "chips",
        "approve",
        "approve",
        "stop",
        "end",
    ]
    first_turn = sent[0].turn_id
    assert sent[1] == ChipsMessage(turn_id=first_turn, chips=["no"])
    assert sent[3] == ApproveMessage(turn_id=first_turn, text=template_text(["no", "morning"]))
    assert sent[4].text == "Sorry, could you please repeat that?"
    assert sent[4].turn_id != first_turn
    assert isinstance(sent[5], StopMessage) and isinstance(sent[6], EndMessage)
    assert "! no draft for this turn yet" in out  # the second send had no fresh draft
    assert session.ended


async def test_bad_input_is_reported_and_loop_continues() -> None:
    transport = FakeTransport()
    _, out = await _run(transport, "chips banana", "dance", 'say "' + "x" * 301 + '"', None)
    assert transport.raw_sent == []
    assert out[0] == "! not in the 12-sign vocabulary: banana"
    assert out[1].startswith("! cannot parse")
    assert len(out) == 3


async def test_only_unsure_chip_change_tells_user_nothing_was_sent() -> None:
    transport = FakeTransport()
    _, out = await _run(transport, "chips ?", None)
    assert transport.raw_sent == []
    assert out == ["chips unchanged for the backend (only '?' changed); nothing sent"]


async def test_eof_stops_without_sending_end() -> None:
    transport = FakeTransport()
    _, _ = await _run(transport, None)
    assert transport.raw_sent == []


async def test_not_delivered_after_send_is_never_resent() -> None:
    transport = FakeTransport(FakeBackend(undeliverable={0}).respond)
    session, _ = await _run(transport, "chips yes", "send", None)
    await drain(transport)
    assert [m.type for m in transport.sent] == ["chips", "approve"]
    assert session.turns[0].outcome == "not_delivered"


NOW = datetime(2026, 10, 24, 11, 5, 9, 123456)


def _label(turn_id: str) -> str:
    return {"t1": "T1"}.get(turn_id, "unknown turn")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (StatusMessage(state=CallState.IN_CALL), "11:05:09.123  status        in_call"),
        (
            CaptionMessage(text="We have 4 pm.", at=1.0),
            '11:05:09.123  caption       "We have 4 pm."',
        ),
        (
            DraftMessage(turn_id="t1", text="No.", source=DraftSource.LLM),
            "11:05:09.123  draft         [T1, llm] No.",
        ),
        (SpokenMessage(turn_id="t1"), "11:05:09.123  spoken        [T1]"),
        (
            ErrorMessage(code="stale_turn", message="old"),
            "11:05:09.123  error         stale_turn: old",
        ),
    ],
)
def test_format_event_lines(message: ServerMessage, expected: str) -> None:
    assert format_event(message, [], _label, NOW) == expected


def test_format_event_appends_notices_and_hides_turn_ids() -> None:
    message = NotDeliveredMessage(turn_id="abc123secret", reason="callee speaking")
    text = format_event(message, [NOT_DELIVERED_NOTICE], _label, NOW)
    assert text.splitlines() == [
        "11:05:09.123  not_delivered [unknown turn] callee speaking",
        f"{' ' * 12}  ! {NOT_DELIVERED_NOTICE}",
    ]
    assert "abc123secret" not in text
