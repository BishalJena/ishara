from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.protocol import ApproveMessage, CaptionMessage, EndMessage
from scripts import fake_app
from tests.conftest import make_settings
from tests.fake_backend import FakeBackend, FakeSockets, drain, mock_backend_client
from tools.cost import CONFIRM_HINT, COST_HEADS_UP

RECEPTIONIST = ["We have 4 pm tomorrow. Does that work?", "Yes, 10:30 tomorrow morning."]
FAST_SCRIPT = [
    "script",
    "--contact",
    "clinic",
    "--confirm-cost",
    "--first-caption-wait",
    "1",
    "--caption-timeout",
    "1",
    "--sign-gap",
    "0",
    "--spoken-timeout",
    "1",
]


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        pytest.fail("no call may be started")

    monkeypatch.setattr(fake_app, "live_call", refuse)
    monkeypatch.setattr(fake_app.asyncio, "run", refuse)


@pytest.mark.parametrize("command", ["interactive", "script"])
def test_without_confirm_cost_prints_heads_up_and_starts_nothing(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_network(monkeypatch)
    code = fake_app.main([command, "--contact", "clinic"], settings=make_settings())
    assert code == 2
    assert capsys.readouterr().out.splitlines() == [COST_HEADS_UP, CONFIRM_HINT]


def test_missing_app_token_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_network(monkeypatch)
    argv = ["interactive", "--contact", "clinic", "--confirm-cost"]
    assert fake_app.main(argv, settings=make_settings(app_token=None)) == 2
    assert "APP_TOKEN is not set" in capsys.readouterr().out


def test_contact_is_required() -> None:
    with pytest.raises(SystemExit):
        fake_app.build_parser().parse_args(["script", "--confirm-cost"])


async def test_script_mode_runs_the_demo_and_prints_the_timing_table() -> None:
    sockets = FakeSockets(FakeBackend(captions=RECEPTIONIST).respond)
    sockets.transport.push(CaptionMessage(text="Hello, City Clinic.", at=0.0))
    out: list[str] = []
    args = fake_app.build_parser().parse_args(FAST_SCRIPT)
    async with mock_backend_client() as client:
        code = await fake_app.run(args, client, sockets.open, out.append)
    assert code == 0
    sent = sockets.transport.sent
    assert [m.type for m in sent].count("approve") == 3
    assert sent[-1] == EndMessage()
    table = out[-1].splitlines()
    assert [row.split(" | ")[0] for row in table[2:]] == ["| T1", "| T3", "| T5"]
    assert all(row.endswith("| spoken |") for row in table[2:])
    assert not any("call-secret-1" in line for line in out)


async def test_script_abort_still_ends_the_call_and_returns_1() -> None:
    sockets = FakeSockets(lambda m: FakeBackend().respond(m) if m.type == "end" else [])
    out: list[str] = []
    args = fake_app.build_parser().parse_args([*FAST_SCRIPT, "--draft-timeout", "0.01"])
    async with mock_backend_client() as client:
        code = await fake_app.run(args, client, sockets.open, out.append)
    assert code == 1
    assert "script stopped: T1: no draft within 0.01 s" in out
    assert [m.type for m in sockets.transport.sent] == ["chips", "end"]


async def test_interactive_mode_reads_commands_until_end() -> None:
    sockets = FakeSockets(FakeBackend().respond)
    feed: Iterator[str] = iter(["chips hello ?", "send", "end"])
    out: list[str] = []

    async def read_line() -> str | None:
        await drain(sockets.transport)
        return next(feed, None)

    args = fake_app.build_parser().parse_args(
        ["interactive", "--contact", "clinic", "--confirm-cost"]
    )
    async with mock_backend_client() as client:
        code = await fake_app.run(args, client, sockets.open, out.append, read_line)
    assert code == 0
    sent = sockets.transport.sent
    assert [m.type for m in sent] == ["chips", "approve", "end"]
    assert sent[0].chips == ["hello"]
    assert sent[1] == ApproveMessage(turn_id=sent[0].turn_id, text="Hello.")
    assert "SEND: Hello." in out


async def test_refused_call_reports_status_code() -> None:
    sockets = FakeSockets(None)
    out: list[str] = []
    args = fake_app.build_parser().parse_args(FAST_SCRIPT)
    async with mock_backend_client(status=403) as client:
        code = await fake_app.run(args, client, sockets.open, out.append)
    assert code == 1
    assert out == ["POST /calls refused: HTTP 403"]
    assert sockets.opened == []
