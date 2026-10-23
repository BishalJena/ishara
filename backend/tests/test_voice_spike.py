from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from app.protocol import EndMessage
from scripts import voice_spike
from tests.conftest import make_settings
from tests.fake_backend import FakeBackend, FakeSockets, ScriptedObserver, mock_backend_client
from tools.cost import CONFIRM_HINT, COST_HEADS_UP
from tools.voice_checks import SpikeTiming

TEMPLATE = "# Voice\n\n## Runs\n\nNo runs yet.\n"
QUICK = SpikeTiming(spoken_timeout_s=0.5, duplicate_settle_s=0, end_timeout_s=0.5)


async def _no_sleep(_: float) -> None:
    return None


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        pytest.fail("no call may be started")

    monkeypatch.setattr(voice_spike, "live_call", refuse)
    monkeypatch.setattr(voice_spike.asyncio, "run", refuse)


def test_without_confirm_cost_prints_heads_up_and_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_network(monkeypatch)
    assert voice_spike.main(["--contact", "clinic"], settings=make_settings()) == 2
    assert capsys.readouterr().out.splitlines() == [COST_HEADS_UP, CONFIRM_HINT]


def test_missing_app_token_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_network(monkeypatch)
    argv = ["--contact", "clinic", "--confirm-cost"]
    assert voice_spike.main(argv, settings=make_settings(app_token=None)) == 2
    assert "APP_TOKEN is not set" in capsys.readouterr().out


def test_checks_default_to_all_nine_and_are_validated() -> None:
    parser = voice_spike.build_parser()
    assert parser.parse_args(["--contact", "c"]).checks == list(range(1, 10))
    assert parser.parse_args(["--contact", "c", "--checks", "5, 2"]).checks == [5, 2]
    for bad in ("0", "1,10", "a", ","):
        with pytest.raises(SystemExit):
            parser.parse_args(["--contact", "c", "--checks", bad])


def test_default_results_path_is_the_voice_record() -> None:
    assert voice_spike.DEFAULT_RESULTS.parts[-3:] == ("docs", "experiments", "voice.md")


async def test_run_appends_a_redacted_section_after_the_call_ends(tmp_path: Path) -> None:
    record = tmp_path / "voice.md"
    record.write_text(TEMPLATE, encoding="utf-8")
    sockets = FakeSockets(FakeBackend().respond)
    observer = ScriptedObserver(["y", "teammate on +91 00000 12345 heard it", "y", "call-secret-1"])
    args = voice_spike.build_parser().parse_args(
        ["--contact", "clinic", "--checks", "5,2", "--results", str(record)]
    )
    async with mock_backend_client(call_id="call-secret-1") as client:
        code = await voice_spike.run(
            args,
            client,
            sockets.open,
            observer.observer(),
            timing=QUICK,
            sleep=_no_sleep,
            now=lambda: datetime(2026, 10, 24, 14, 5),
        )
    assert code == 0
    assert sockets.transport.sent[-1] == EndMessage()
    text = record.read_text(encoding="utf-8")
    assert text.startswith(TEMPLATE)
    section = text[len(TEMPLATE) :]
    assert "## Run 2026-10-24 14:05 (local time)" in section
    assert [
        line.split(" | ")[0] for line in section.splitlines() if line.startswith("| check")
    ] == [
        "| check 2",
        "| check 5",
    ]
    assert "call-secret-1" not in text
    assert "12345" not in text
    assert not re.search(r"[0-9a-f]{32}", text)
    assert "heard it" in section


async def test_refused_call_writes_nothing(tmp_path: Path) -> None:
    record = tmp_path / "voice.md"
    record.write_text(TEMPLATE, encoding="utf-8")
    observer = ScriptedObserver([])
    args = voice_spike.build_parser().parse_args(["--contact", "clinic", "--results", str(record)])
    async with mock_backend_client(status=403) as client:
        code = await voice_spike.run(args, client, FakeSockets(None).open, observer.observer())
    assert code == 1
    assert observer.out == ["POST /calls refused: HTTP 403"]
    assert record.read_text(encoding="utf-8") == TEMPLATE
